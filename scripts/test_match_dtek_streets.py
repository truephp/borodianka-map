import unittest

from scripts.match_dtek_streets import compare_streets, load_dtek_streets, normalize_street


def road(name):
    return {"type": "Feature", "properties": {"name": name},
            "geometry": {"type": "LineString", "coordinates": [[29.9, 50.6], [29.91, 50.61]]}}


class DtekStreetMatchingTests(unittest.TestCase):
    def test_normalize_street_type_prefix_and_suffix(self):
        self.assertEqual(normalize_street("вулиця Семашка"), "семашка")
        self.assertEqual(normalize_street("Семашка вул."), "семашка")
        self.assertEqual(normalize_street("Центральна вулиця"), "центральна")
        self.assertEqual(normalize_street("вул. Центральна"), "центральна")
        self.assertEqual(normalize_street("провулок Парковий"), "парковий")

    def test_dtek_city_selection(self):
        raw = {"streets": {"с-ще Бородянка": ["вул. Семашка", "Центральна"],
                            "с. Берестянка": ["Шкільна"]}}
        self.assertEqual(load_dtek_streets(raw, "с-ще Бородянка"),
                         ["Центральна", "вул. Семашка"])
        with self.assertRaises(ValueError):
            load_dtek_streets(raw, "Бородянка")

    def test_exact_alias_candidate_and_unmatched(self):
        roads = [road("вулиця Семашка"), road("Центральна вулиця"), road("Паркова вулиця")]
        dtek = ["Семашка вул.", "Центральна", "Стара назва", "Паркоа", "Інша"]
        r = compare_streets(dtek, roads, {"Стара назва": "Паркова вулиця"}, min_score=0.70)
        statuses = {item["dtek"]: item["status"] for item in r["streets"]}
        self.assertEqual(statuses["Семашка вул."], "exact")
        self.assertEqual(statuses["Центральна"], "exact")
        self.assertEqual(statuses["Стара назва"], "alias")
        self.assertEqual(statuses["Паркоа"], "candidates")
        self.assertEqual(statuses["Інша"], "unmatched")
        self.assertEqual(sum(r["counts"].values()), len(dtek))


if __name__ == "__main__":
    unittest.main()
