import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parent))
from match_dtek_buildings import address_records, house_candidate_key, house_key, match_houses, street_key


def feature(source, ident, street, house):
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []},
            "properties": {"source": source, "sourceId": ident, "street": street, "housenumber": house}}


def dtek(city, street, houses):
    return {"city": city, "street": street, "response":
            {"result": True, "data": {name: None for name in houses}}}


class AddressMatchingTests(unittest.TestCase):
    def test_street_type_is_not_ignored(self):
        self.assertEqual(street_key("вул. Жиліна"), ("street", "жиліна"))
        self.assertEqual(street_key("пров. Жиліна"), ("lane", "жиліна"))
        self.assertNotEqual(street_key("вул. Жиліна"), street_key("пров. Жиліна"))

    def test_house_suffixes_not_merged(self):
        self.assertNotEqual(house_key("1А"), house_key("1/А"))
        self.assertNotEqual(house_key("15"), house_key("15А"))
        self.assertNotEqual(house_key("15/1"), house_key("15"))
        self.assertEqual(house_candidate_key("1/А"), house_candidate_key("1A"))

    def test_exact_and_candidates_with_provenance(self):
        fc = {"features": [
            feature("osm", "1", "вулиця Ветеранів", "1/А"),
            feature("visicom", "2", "вулиця Заводська", "1А"),
            feature("osm", "3", "вулиця Жиліна", "2"),
            feature("osm", "4", "провулок Жиліна", "2"),
        ]}
        buildings = list(address_records(fc))
        records = [
            dtek("с-ще Бородянка", "вул. Ветеранів", ["1/А", "3"]),
            dtek("смт Бородянка", "вул. Ветеранів", ["1A"]),
            dtek("с-ще Бородянка", "вул. Заводська", ["1А"]),
            dtek("смт Бородянка", "вул. Заводська", ["1/А"]),
            dtek("смт Бородянка", "вул. Жиліна", ["2"]),
        ]
        result = match_houses(records, buildings)
        self.assertEqual(result["counts"], {"exact": 3, "candidate_house_format": 2, "unmatched": 1})
        exact = next(x for x in result["records"] if x.get("street") == "вул. Жиліна")
        self.assertEqual(exact["links"][0]["id"], "3")
        self.assertEqual(exact["links"][0]["source"], "osm")

    def test_visicom_missing_street_type_is_candidate(self):
        buildings = list(address_records({"features": [
            feature("visicom", "v1", "Заводська", "1А"),
            feature("visicom", "v2", "Ветеранів", "1/А")
        ]}))
        report = match_houses([
            dtek("с-ще Бородянка", "вул. Заводська", ["1А"]),
            dtek("смт Бородянка", "вул. Ветеранів", ["1A"]),
        ], buildings)
        self.assertEqual(report["counts"], {
            "candidate_street_type": 1,
            "candidate_street_and_house_format": 1,
        })
        self.assertTrue(all("links" in r for r in report["records"]))
        self.assertEqual(report["records"][0]["links"][0]["id"], "v1")

    def test_duplicates_are_not_exact(self):
        buildings = list(address_records({"features": [
            feature("osm", "1", "вул. Заводська", "3"),
            feature("visicom", "2", "вул. Заводська", "3")
        ]}))
        report = match_houses([dtek("смт Бородянка", "вул. Заводська", ["3"])], buildings)
        self.assertEqual(report["counts"], {"multiple": 1})

    def test_missing_dtek_response_not_empty(self):
        report = match_houses([{"city": "смт Бородянка", "street": "вул. Заводська",
                               "error": "HTTP 403"}], [])
        self.assertEqual(report["counts"], {"source_error": 1})


if __name__ == "__main__":
    unittest.main()
