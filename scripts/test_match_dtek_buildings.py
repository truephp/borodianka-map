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

    def test_reviewed_dtek_visicom_street_variants(self):
        cases = [
            ("вул. Костенко Ліни", "Ліни Костенко"),
            ("вул. Чорновола В’ячеслава", "Чорновола"),
            ("вул. Хмельницького Богдана", "Богдана Хмельницького"),
        ]
        for index, (dtek_street, visicom_street) in enumerate(cases):
            with self.subTest(dtek_street=dtek_street):
                self.assertEqual(street_key(dtek_street)[1], street_key(visicom_street)[1])
                buildings = list(address_records({"features": [
                    feature("visicom", str(index), visicom_street, "27")
                ]}))
                report = match_houses([dtek("с-ще Бородянка", dtek_street, ["27"])], buildings)
                self.assertEqual(report["counts"], {"exact": 1})
                self.assertEqual(report["records"][0]["links"][0]["id"], str(index))

    def test_unreviewed_person_name_is_not_reordered(self):
        self.assertNotEqual(street_key("вул. Шевченка Тараса")[1],
                            street_key("Тараса Шевченка")[1])

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
        self.assertEqual(result["counts"], {"exact": 2, "candidate_street_type": 1, "candidate_house_format": 2, "unmatched": 1})
        exact = next(x for x in result["records"] if x.get("street") == "вул. Жиліна")
        self.assertEqual(exact["status"], "candidate_street_type")
        self.assertEqual({b["id"] for b in exact["links"]}, {"3", "4"})
        self.assertEqual({b["source"] for b in exact["links"]}, {"osm"})

    def test_visicom_missing_street_type_is_exact_without_conflicts(self):
        buildings = list(address_records({"features": [
            feature("visicom", "v1", "Заводська", "1А"),
            feature("visicom", "v2", "Ветеранів", "1/А")
        ]}))
        report = match_houses([
            dtek("с-ще Бородянка", "вул. Заводська", ["1А"]),
            dtek("смт Бородянка", "вул. Ветеранів", ["1A"]),
        ], buildings)
        self.assertEqual(report["counts"], {
            "exact": 1,
            "candidate_house_format": 1,
        })
        self.assertTrue(all("links" in r for r in report["records"]))
        self.assertEqual(report["records"][0]["links"][0]["id"], "v1")

    def test_visicom_bare_name_uses_osm_and_dtek_type_registry(self):
        buildings = list(address_records({"features": [
            feature("visicom", "v1", "Центральна", "427а"),
            feature("visicom", "v2", "Центральна", "429"),
        ]}))
        roads = {"features": [{"properties": {"name": "Центральна вулиця"}}]}
        directory = {"streets": {"с-ще Бородянка": ["вул. Центральна"]}}
        report = match_houses([
            dtek("с-ще Бородянка", "вул. Центральна", ["427А", "429"]),
        ], buildings, roads=roads, directory=directory)
        self.assertEqual(report["counts"], {"exact": 2})
        self.assertEqual({r["links"][0]["id"] for r in report["records"]}, {"v1", "v2"})

    def test_bare_name_street_vs_lane_conflict(self):
        buildings = list(address_records({"features": [
            feature("visicom", "v1", "Жиліна", "2")
        ]}))
        roads = {"features": [{"properties": {"name": "вулиця Жиліна"}},
                              {"properties": {"name": "провулок Жиліна"}}]}
        report = match_houses([
            dtek("смт Бородянка", "вул. Жиліна", ["2"]),
        ], buildings, roads=roads)
        self.assertEqual(report["counts"], {"candidate_street_type": 1})

    def test_dtek_directory_type_conflict_even_if_only_one_building(self):
        buildings = list(address_records({"features": [
            feature("visicom", "v1", "Будівельників", "10")
        ]}))
        directory = {"streets": {"смт Бородянка": [
            "вул. Будівельників", "пров. Будівельників",
        ]}}
        report = match_houses([
            dtek("смт Бородянка", "пров. Будівельників", ["10"]),
        ], buildings, directory=directory)
        self.assertEqual(report["counts"], {"candidate_street_type": 1})

    def test_two_bare_visicom_polygons_same_address_ambiguous(self):
        buildings = list(address_records({"features": [
            feature("visicom", "v1", "Центральна", "427а"),
            feature("visicom", "v2", "Центральна", "427А"),
        ]}))
        report = match_houses([
            dtek("с-ще Бородянка", "вул. Центральна", ["427а"])
        ], buildings)
        self.assertEqual(report["counts"], {"multiple": 1})

    def test_explicit_type_conflict_not_confirmed(self):
        buildings = list(address_records({"features": [
            feature("visicom", "v1", "провулок Грушевського", "3"),
        ]}))
        report = match_houses([
            dtek("с-ще Бородянка", "вул. Грушевського", ["3"]),
        ], buildings)
        self.assertEqual(report["counts"], {"candidate_street_type": 1})

    def test_duplicates_are_not_exact(self):
        buildings = list(address_records({"features": [
            feature("osm", "1", "вул. Заводська", "3"),
            feature("visicom", "2", "вул. Заводська", "3")
        ]}))
        report = match_houses([dtek("смт Бородянка", "вул. Заводська", ["3"])], buildings)
        self.assertEqual(report["counts"], {"multiple": 1})

    def test_house_metadata_is_preserved_in_exact_match(self):
        buildings = list(address_records({"features": [
            feature("visicom", "v44", "Центральна", "44")
        ]}))
        metadata = {
            "cek": None, "end_date": "", "start_date": "",
            "sub_type": "", "sub_type_reason": ["GPV1.2"],
            "type": "", "voluntarily": None,
        }
        source = {"city": "с-ще Бородянка", "street": "вул. Центральна",
                  "response": {"result": True, "data": {"44": metadata}}}
        report = match_houses([source], buildings)
        self.assertEqual(report["counts"], {"exact": 1})
        self.assertEqual(report["records"][0]["dtek"], metadata)

    def test_missing_dtek_response_not_empty(self):
        report = match_houses([{"city": "смт Бородянка", "street": "вул. Заводська",
                               "error": "HTTP 403"}], [])
        self.assertEqual(report["counts"], {"source_error": 1})


if __name__ == "__main__":
    unittest.main()
