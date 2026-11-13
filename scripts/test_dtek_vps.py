import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))
from run_dtek_vps import publish_capture, atomic_json


def capture_fixture():
    now = datetime.now(timezone.utc)
    kyiv = now.astimezone(ZoneInfo("Europe/Kyiv"))
    midnight = kyiv.replace(hour=0, minute=0, second=0, microsecond=0)
    date_key = str(int(midnight.timestamp()))
    return {
        "source": "https://www.dtek-krem.com.ua",
        "fetchedAt": now.isoformat(),
        "scheduleFact": {
            "update": "DTEK published",
            "data": {date_key: {"GPV1.2": {str(h): "yes" for h in range(1, 25)}}},
        },
        "responses": [
            {"city": "смт Бородянка", "street": "вул. Тестова",
             "response": {"result": True, "data": {
                 "1": {"type": "", "sub_type_reason": ["GPV1.2"]}}}}
        ]
    }


class DtekVpsPublishTests(unittest.TestCase):
    def test_both_public_files_are_written(self):
        with tempfile.TemporaryDirectory() as directory:
            result = publish_capture(capture_fixture(), directory)
            self.assertTrue(result["schedule"]["ok"])
            self.assertTrue(result["houses"]["ok"])
            schedule = json.loads((Path(directory) / "schedule.json").read_text())
            houses = json.loads((Path(directory) / "houses.json").read_text())
            self.assertEqual(schedule["timezone"], "Europe/Kyiv")
            self.assertEqual(len(houses["addresses"]), 1)
            self.assertEqual(houses["addresses"][0]["raw"]["sub_type_reason"], ["GPV1.2"])
            self.assertNotIn("visicom", json.dumps(houses).lower())

    def test_schedule_publishes_when_houses_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = capture_fixture()
            capture["responses"] = [{"city": "смт Бородянка",
                                     "street": "вул. Тестова", "error": "HTTP 503"}]
            result = publish_capture(capture, directory)
            self.assertTrue(result["schedule"]["ok"])
            self.assertFalse(result["houses"]["ok"])
            self.assertTrue((Path(directory) / "schedule.json").exists())
            self.assertFalse((Path(directory) / "houses.json").exists())

    def test_failed_fact_does_not_overwrite_last_schedule(self):
        with tempfile.TemporaryDirectory() as directory:
            old = {"sentinel": "last-good"}
            atomic_json(Path(directory) / "schedule.json", old)
            capture = capture_fixture()
            capture["scheduleFact"] = None
            result = publish_capture(capture, directory)
            self.assertFalse(result["schedule"]["ok"])
            self.assertTrue(result["houses"]["ok"])
            self.assertEqual(json.loads((Path(directory) / "schedule.json").read_text()), old)

    def test_two_failed_streets_are_explicitly_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = capture_fixture()
            template = capture["responses"][0]
            capture["responses"] = [
                {**template, "street": f"вул. Тестова {i}"} for i in range(98)
            ] + [
                {"city": "смт Бородянка", "street": f"вул. Помилка {i}",
                 "error": "DTEK refused"} for i in range(2)
            ]
            result = publish_capture(capture, directory)
            self.assertTrue(result["houses"]["ok"])
            houses = json.loads((Path(directory) / "houses.json").read_text())
            self.assertFalse(houses["complete"])
            self.assertEqual(houses["successfulPairs"], 98)
            self.assertEqual(len(houses["errors"]), 2)
            self.assertEqual(len(houses["addresses"]), 98)


if __name__ == "__main__":
    unittest.main()
