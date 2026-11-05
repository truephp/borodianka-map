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
            ("пров. Здвижовий", "Здвиженський"),
            ("вул. Млинова", "Млиновий"),
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

    def test_two_word_reverse_fallback(self):
        buildings = list(address_records({"features": [
            feature("visicom", "v1", "Тараса Шевченка", "8")
        ]}))
        report = match_houses([dtek("с-ще Бородянка", "вул. Шевченка Тараса", ["8"])], buildings)
        self.assertEqual(report["counts"], {"exact": 1})
        self.assertEqual(report["records"][0]["matchMethod"], "reversed_two_words")
        self.assertEqual(report["records"][0]["links"][0]["id"], "v1")

    def test_reverse_does_not_override_original_street(self):
        buildings = list(address_records({"features": [
            feature("visicom", "normal", "Шевченка Тараса", "2"),
            feature("visicom", "reversed", "Тараса Шевченка", "8"),
        ]}))
        report = match_houses([dtek("с-ще Бородянка", "вул. Шевченка Тараса", ["8"])], buildings)
        self.assertEqual(report["counts"], {"unmatched": 1})

    def test_reverse_requires_matching_type_and_unambiguous_building(self):
        buildings = list(address_records({"features": [
            feature("visicom", "a", "провулок Тараса Шевченка", "8"),
            feature("visicom", "b", "вулиця Тараса Шевченка", "9"),
            feature("visicom", "c", "вулиця Тараса Шевченка", "9"),
        ]}))
        report = match_houses([dtek("с-ще Бородянка", "вул. Шевченка Тараса", ["8", "9"])], buildings)
        self.assertEqual(report["counts"], {"unmatched": 1, "exact": 1})

    def test_reverse_not_applied_to_three_word_names(self):
        buildings = list(address_records({"features": [
            feature("visicom", "a", "Тараса Григоровича Шевченка", "8")
        ]}))
        report = match_houses([dtek("с-ще Бородянка", "вул. Шевченка Григоровича Тараса", ["8"])], buildings)
        self.assertEqual(report["counts"], {"unmatched": 1})

    def test_ukrainky_lesi_matches_lesi_ukrainky(self):
        buildings = list(address_records({"features": [
            feature("visicom", "lesya", "Лесі Українки", "5"),
        ]}))
        report = match_houses([
            dtek("с-ще Бородянка", "вул. Українки Лесі", ["5"])
        ], buildings)
        self.assertEqual(report["counts"], {"exact": 1})
        self.assertEqual(report["records"][0]["matchMethod"], "reversed_two_words")
        self.assertEqual(report["records"][0]["links"][0]["id"], "lesya")

    def test_hrushevskogo_explicit_street_with_namesake_lane(self):
        directory = {"streets": {
            "с-ще Бородянка": ["вул. Грушевського"],
            "смт Бородянка": ["пров. Грушевського"],
        }}
        buildings = list(address_records({"features": [
            feature("visicom", "street", "вул. Грушевського", "7"),
            feature("visicom", "lane", "пров. Грушевського", "7"),
        ]}))
        report = match_houses([
            dtek("с-ще Бородянка", "вул. Грушевського", ["7"])
        ], buildings, directory=directory)
        self.assertEqual(report["counts"], {"exact": 1})
        self.assertEqual([b["id"] for b in report["records"][0]["links"]], ["street"])

    def test_hrushevskogo_explicit_street_unique_number(self):
        directory = {"streets": {
            "с-ще Бородянка": ["вул. Грушевського"],
            "смт Бородянка": ["пров. Грушевського"],
        }}
        buildings = list(address_records({"features": [
            feature("visicom", "street", "вул. Грушевського", "7"),
            feature("visicom", "lane", "пров. Грушевського", "3"),
        ]}))
        report = match_houses([
            dtek("с-ще Бородянка", "вул. Грушевського", ["7"])
        ], buildings, directory=directory)
        self.assertEqual(report["counts"], {"exact": 1})
        self.assertEqual(report["records"][0]["links"][0]["id"], "street")

    def test_hrushevskogo_visicom_explicit_street_type(self):
        directory = {"streets": {
            "с-ще Бородянка": ["вул. Грушевського"],
            "смт Бородянка": ["пров. Грушевського"],
        }}
        building = feature("visicom", "typed", "Грушевського", "7")
        building["properties"]["street_type"] = "вулиця"
        record = list(address_records({"features": [building]}))
        self.assertEqual(record[0]["kind"], "street")
        report = match_houses([
            dtek("с-ще Бородянка", "вул. Грушевського", ["7"])
        ], record, directory=directory)
        self.assertEqual(report["counts"], {"exact": 1})
        self.assertEqual(report["records"][0]["links"][0]["id"], "typed")

    def test_visicom_explicit_lane_does_not_match_street(self):
        building = feature("visicom", "lane", "Грушевського", "7")
        building["properties"]["street_type"] = "провулок"
        record = list(address_records({"features": [building]}))
        self.assertEqual(record[0]["kind"], "lane")
        report = match_houses([
            dtek("с-ще Бородянка", "вул. Грушевського", ["7"])
        ], record)
        self.assertEqual(report["counts"], {"unmatched": 1})
        self.assertEqual(report["records"][0]["links"], [])

    def test_hrushevskogo_untyped_visicom_remains_candidate(self):
        directory = {"streets": {
            "с-ще Бородянка": ["вул. Грушевського"],
            "смт Бородянка": ["пров. Грушевського"],
        }}
        buildings = list(address_records({"features": [
            feature("visicom", "unknown-type", "Грушевського", "7"),
        ]}))
        report = match_houses([
            dtek("с-ще Бородянка", "вул. Грушевського", ["7"])
        ], buildings, directory=directory)
        self.assertEqual(report["counts"], {"candidate_street_type": 1})
        self.assertEqual(report["records"][0]["links"][0]["id"], "unknown-type")

    def test_street_lane_same_number_only_correct_type_linked(self):
        street = feature("visicom", "street-5", "Будівельників", "5")
        lane = feature("visicom", "lane-5", "Будівельників", "5")
        street["properties"]["street_type"] = "вулиця"
        lane["properties"]["street_type"] = "провулок"
        buildings = list(address_records({"features": [street, lane]}))
        report = match_houses([
            dtek("с-ще Бородянка", "вул. Будівельників", ["5"]),
            dtek("с-ще Бородянка", "пров. Будівельників", ["5"]),
        ], buildings)
        self.assertEqual(report["counts"], {"exact": 2})
        self.assertEqual(report["records"][0]["links"][0]["id"], "street-5")
        self.assertEqual(report["records"][1]["links"][0]["id"], "lane-5")

    def test_opposite_kind_candidate_house_format_is_excluded(self):
        lane = feature("visicom", "lane-5a", "Будівельників", "5А")
        lane["properties"]["street_type"] = "провулок"
        buildings = list(address_records({"features": [lane]}))
        report = match_houses([
            dtek("с-ще Бородянка", "вул. Будівельників", ["5/А"]),
        ], buildings)
        self.assertEqual(report["counts"], {"unmatched": 1})
        self.assertEqual(report["records"][0]["links"], [])

    def test_untyped_and_explicit_same_type_with_namesake_lane(self):
        typed = feature("visicom", "street", "Коцюбинського", "9")
        typed["properties"]["street_type"] = "вулиця"
        untyped = feature("osm", "unknown", "Коцюбинського", "9")
        records = list(address_records({"features": [typed, untyped]}))
        directory = {"streets": {"с-ще Бородянка": [
            "вул. Коцюбинського", "пров. Коцюбинського"]}}
        report = match_houses([
            dtek("с-ще Бородянка", "вул. Коцюбинського", ["9"])
        ], records, directory=directory)
        self.assertEqual(report["counts"], {"candidate_street_type": 1})
        self.assertEqual({x["id"] for x in report["records"][0]["links"]}, {"street", "unknown"})

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
        self.assertEqual(exact["status"], "exact")
        self.assertEqual({b["id"] for b in exact["links"]}, {"3"})
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

    def test_two_visicom_polygons_with_same_address_are_both_confirmed(self):
        buildings = list(address_records({"features": [
            feature("visicom", "v1", "Центральна", "427а"),
            feature("visicom", "v2", "Центральна", "427А"),
        ]}))
        report = match_houses([
            dtek("с-ще Бородянка", "вул. Центральна", ["427а"])
        ], buildings)
        self.assertEqual(report["counts"], {"exact": 1})
        self.assertEqual({link["id"] for link in report["records"][0]["links"]}, {"v1", "v2"})

    def test_velyka_87_multiple_visicom_contours_single_address(self):
        buildings = list(address_records({"features": [
            feature("visicom", "ADR3K0MZV5EH5PTGSJ", "Велика", "87"),
            feature("visicom", "ADR3K0MZV5EHJQKK9", "Велика", "87"),
        ]}))
        report = match_houses([
            dtek("с-ще Бородянка", "вул. Велика", ["87"])
        ], buildings)
        self.assertEqual(report["counts"], {"exact": 1})
        self.assertEqual(len(report["records"][0]["links"]), 2)
        self.assertEqual({link["id"] for link in report["records"][0]["links"]},
                         {"ADR3K0MZV5EH5PTGSJ", "ADR3K0MZV5EHJQKK9"})

    def test_explicit_type_conflict_not_confirmed(self):
        buildings = list(address_records({"features": [
            feature("visicom", "v1", "провулок Грушевського", "3"),
        ]}))
        report = match_houses([
            dtek("с-ще Бородянка", "вул. Грушевського", ["3"]),
        ], buildings)
        self.assertEqual(report["counts"], {"unmatched": 1})
        self.assertEqual(report["records"][0]["links"], [])

    def test_same_address_osm_and_visicom_can_both_be_confirmed(self):
        buildings = list(address_records({"features": [
            feature("osm", "1", "вул. Заводська", "3"),
            feature("visicom", "2", "вул. Заводська", "3")
        ]}))
        report = match_houses([dtek("смт Бородянка", "вул. Заводська", ["3"])], buildings)
        self.assertEqual(report["counts"], {"exact": 1})
        self.assertEqual({link["id"] for link in report["records"][0]["links"]}, {"1", "2"})

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
