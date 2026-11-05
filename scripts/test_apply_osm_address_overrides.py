import copy
import unittest

from scripts.apply_osm_address_overrides import apply_overrides

POLYGON = {
    "type": "FeatureCollection",
    "features": [{
        "type": "Feature",
        "properties": {"id": 939469763, "building": "yes",
                       "street": "вулиця Семашка", "housenumber": "1"},
        "geometry": {"type": "Polygon", "coordinates": [[
            [0, 0], [2, 0], [2, 2], [0, 2], [0, 0]
        ]]},
    }],
}
NODES = {
    "type": "FeatureCollection",
    "features": [{
        "type": "Feature",
        "properties": {"id": 100, "street": "вулиця Семашка", "housenumber": "3е"},
        "geometry": {"type": "Point", "coordinates": [1, 1]},
    }, {
        "type": "Feature",
        "properties": {"id": 101, "street": "вулиця Семашка", "housenumber": "3є"},
        "geometry": {"type": "Point", "coordinates": [1.5, 1]},
    }],
}


def decisions(addresses, include_original=False):
    return {"schemaVersion": 1, "source": "borodianka-osm-building-address-overrides",
            "overrides": [{"osmId": "939469763", "includeOriginal": include_original,
                           "addresses": addresses}]}


def node_address(node, suffix):
    return {"street": "вулиця Семашка", "housenumber": suffix,
            "pointIds": [str(node)], "fromPolygon": False}


class ApplyOsmAddressOverrideTests(unittest.TestCase):
    def setUp(self):
        self.buildings = copy.deepcopy(POLYGON)
        self.points = copy.deepcopy(NODES)
        self.properties = self.buildings["features"][0]["properties"]

    def test_replace_wrong_polygon_address_with_point_address(self):
        count = apply_overrides(self.buildings, self.points,
                                decisions([node_address(100, "3е")]))
        self.assertEqual(count, 1)
        self.assertEqual(self.properties["street"], "вулиця Семашка")
        self.assertEqual(self.properties["housenumber"], "3е")
        self.assertEqual(len(self.properties["addresses"]), 1)
        self.assertFalse(self.properties["addresses"][0]["fromPolygon"])

    def test_original_and_two_internal_points(self):
        original = {"street": "вулиця Семашка", "housenumber": "1",
                    "pointIds": [], "fromPolygon": True}
        apply_overrides(self.buildings, self.points, decisions(
            [original, node_address(100, "3е"), node_address(101, "3є")], True))
        self.assertEqual([x["housenumber"] for x in self.properties["addresses"]],
                         ["1", "3е", "3є"])

    def test_no_addresses_removes_old_primary_address(self):
        apply_overrides(self.buildings, self.points, decisions([]))
        self.assertNotIn("street", self.properties)
        self.assertNotIn("housenumber", self.properties)
        self.assertEqual(self.properties["addresses"], [])

    def test_node_outside_polygon_rejected(self):
        self.points["features"][0]["geometry"]["coordinates"] = [10, 10]
        with self.assertRaisesRegex(ValueError, "outside polygon"):
            apply_overrides(self.buildings, self.points,
                            decisions([node_address(100, "3е")]))

    def test_refuses_unverified_address(self):
        fake = {"street": "вулиця Семашка", "housenumber": "99", "pointIds": []}
        with self.assertRaises(ValueError):
            apply_overrides(self.buildings, self.points, decisions([fake]))


if __name__ == "__main__":
    unittest.main()
