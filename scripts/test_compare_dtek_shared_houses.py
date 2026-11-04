import unittest
from scripts.compare_dtek_shared_houses import compare, extract_houses, house_key, shared_streets, CITIES

DIRECTORY = {"streets": {
    CITIES[0]: ["вул. Лісна", "вул. Центральна", "вул. Заводська"],
    CITIES[1]: ["вул. Лісна", "вул. Заводська", "вул. Макарівська"],
}}


def response(city, street, numbers=None, error=None):
    result = {"city": city, "street": street}
    if error:
        result["error"] = error
    else:
        result["response"] = {"result": True, "data": {n: {"status": "hidden"} for n in numbers}}
    return result


class CompareHousesTest(unittest.TestCase):
    def test_shared_streets(self):
        self.assertEqual(shared_streets(DIRECTORY), ["вул. Заводська", "вул. Лісна"])

    def test_no_false_joins(self):
        self.assertNotEqual(house_key("15"), house_key("15А"))
        self.assertNotEqual(house_key("15/1"), house_key("15"))
        self.assertEqual(house_key("15 А"), house_key("15а"))

    def test_response_keys_are_house_numbers(self):
        self.assertEqual(set(extract_houses({"result": True, "data": {"1": {}, "2а": {}}})),
                         {"1", "2а"})
        with self.assertRaises(ValueError):
            extract_houses({"result": False, "data": {}})

    def test_compare_and_report_failures(self):
        data = [
            response(CITIES[0], "вул. Лісна", ["1", "2", "3"]),
            response(CITIES[1], "вул. Лісна", ["2", "3", "4"]),
            response(CITIES[0], "вул. Заводська", ["7"]),
            response(CITIES[1], "вул. Заводська", error="HTTP 403"),
        ]
        report = compare(DIRECTORY, data)
        self.assertEqual(report["compared"], 1)
        self.assertEqual(report["failed"], 1)
        row = next(r for r in report["streets"] if r["street"] == "вул. Лісна")
        self.assertEqual(row["counts"], {"first": 3, "second": 3, "shared": 2,
                                         "onlyFirst": 1, "onlySecond": 1})
        self.assertEqual(row["houseNumbers"]["onlyFirst"], ["1"])
        self.assertEqual(row["houseNumbers"]["onlySecond"], ["4"])
        bad = next(r for r in report["streets"] if r["street"] == "вул. Заводська")
        self.assertEqual(bad["status"], "error")
        self.assertNotIn("houseNumbers", bad)

    def test_missing_city_is_not_empty_set(self):
        report = compare(DIRECTORY, [response(CITIES[0], "вул. Лісна", ["1"])])
        self.assertEqual(report["failed"], 2)


if __name__ == "__main__":
    unittest.main()
