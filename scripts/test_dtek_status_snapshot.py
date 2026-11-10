import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_dtek_status_snapshot import assemble, FIELDS


class DtekStatusSnapshotTests(unittest.TestCase):
    def test_preserves_all_seven_fields_and_unknown_does_not_mean_power_on(self):
        raw = dict(zip(FIELDS, [None, "", "", "", ["GPV1.2"], "", None]))
        data = {"source": "https://www.dtek-krem.com.ua", "fetchedAt": "2026-11-10T00:00:00Z",
                "responses": [{"city": "с-ще Бородянка", "street": "вул. Тестова",
                               "response": {"result": True, "data": {"44": raw, "45": {}}}}]}
        result = assemble(data)
        self.assertTrue(result["complete"])
        self.assertEqual(len(result["addresses"]), 2)
        self.assertEqual(result["addresses"][0]["raw"], raw)
        self.assertEqual(result["addresses"][0]["signal"], "reported")
        self.assertEqual(result["addresses"][1]["signal"], "unknown")
        self.assertEqual(result["counts"]["no_reported_outage_signal"], 1)

    def test_errors_make_snapshot_incomplete(self):
        result = assemble({"responses": [
            {"city": "с-ще Бородянка", "street": "вул. Тестова", "error": "HTTP 503"},
            {"city": "смт Бородянка", "street": "вул. Інша",
             "response": {"result": True, "data": {"1": {}}}},
        ]})
        self.assertFalse(result["complete"])
        self.assertEqual(result["successfulPairs"], 1)
        self.assertEqual(len(result["errors"]), 1)

    def test_original_settlement_keys_are_kept(self):
        result = assemble({"responses": [
            {"city": "с-ще Бородянка", "street": "вул. Тестова",
             "response": {"result": True, "data": {"1": {}}}},
            {"city": "смт Бородянка", "street": "вул. Тестова",
             "response": {"result": True, "data": {"1": {}}}},
        ]})
        self.assertEqual(len(result["addresses"]), 2)
        self.assertNotEqual(result["addresses"][0]["city"], result["addresses"][1]["city"])


if __name__ == "__main__":
    unittest.main()
