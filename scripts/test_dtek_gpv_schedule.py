import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch_dtek_gpv_schedule import normalize


class DtekFactTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 10, 18, 0, tzinfo=timezone.utc)
        self.capture = {
            "source": "https://www.dtek-krem.com.ua",
            "fetchedAt": "2026-11-10T17:59:00+00:00",
            "scheduleFact": {
                "today": "1794261600",
                "update": "10.11.2026 19:58",
                "data": {
                    "1794261600": {
                        "GPV1.2": {str(x): "first" if x == 1 else "yes" for x in range(1, 25)}
                    }
                }
            }
        }

    def test_first_party_fact_normalizes_without_external_fetch(self):
        result = normalize(self.capture, self.now)
        self.assertEqual(result["source"], "https://www.dtek-krem.com.ua/ua/shutdowns")
        self.assertEqual(result["days"]["2026-11-10"]["GPV1.2"][0], "first")
        self.assertEqual(result["dtekPublishedAt"], "10.11.2026 19:58")

    def test_missing_fact_is_rejected(self):
        self.capture.pop("scheduleFact")
        with self.assertRaisesRegex(ValueError, "DisconSchedule"):
            normalize(self.capture, self.now)

    def test_incomplete_group_does_not_become_known_schedule(self):
        self.capture["scheduleFact"]["data"]["1794261600"]["GPV1.2"].pop("24")
        with self.assertRaisesRegex(ValueError, "No valid schedule"):
            normalize(self.capture, self.now)


if __name__ == "__main__":
    unittest.main()
