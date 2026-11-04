import unittest
from scripts.merge_buildings import create_merged, encrypt, decrypt


def feature(source_id, coords, source="osm"):
    p = {"id": source_id, "street": "Тестова", "housenumber": str(source_id)} if source == "osm" else {"visicomId": source_id, "street": "Тестова", "name": str(source_id)}
    return {"type": "Feature", "properties": p, "geometry": {"type": "Polygon", "coordinates": [coords]}}


class MergeBuildingsTests(unittest.TestCase):
    def test_merge_keeps_only_uncovered_osm(self):
        boundary = {"type": "FeatureCollection", "features": [feature("boundary", [[0,0],[10,0],[10,10],[0,10],[0,0]])]}
        vc = {"type": "FeatureCollection", "metadata": {"complete": True},
              "features": [feature("vis1", [[1,1],[3,1],[3,3],[1,3],[1,1]], "visicom")]}
        osm = {"type": "FeatureCollection", "features": [
            feature("1", [[1.1,1.1],[3.1,1.1],[3.1,3.1],[1.1,3.1],[1.1,1.1]]),
            feature("2", [[7,7],[8,7],[8,8],[7,8],[7,7]]),
            feature("3", [[2.9,2.9],[3.5,2.9],[3.5,3.5],[2.9,3.5],[2.9,2.9]])]}
        r = create_merged(vc, osm, boundary, 0.35, 0.8)
        self.assertEqual(r["metadata"]["visicom"], 1)
        self.assertEqual(r["metadata"]["osmSupplemental"], 2)
        self.assertEqual(r["metadata"]["osmSkippedOverlap"], 1)
        self.assertEqual([f["properties"]["source"] for f in r["features"]], ["visicom", "osm", "osm"])
        self.assertIn("no_overlap", [f["properties"]["matchStatus"] for f in r["features"]])
        self.assertIn("partial_overlap", [f["properties"]["matchStatus"] for f in r["features"]])

    def test_encrypted_roundtrip(self):
        obj = {"type": "FeatureCollection", "features": []}
        self.assertEqual(decrypt(encrypt(obj, "a test secret password"), "a test secret password"), obj)

    def test_reject_incomplete_input(self):
        with self.assertRaises(ValueError):
            create_merged({"type": "FeatureCollection", "features": [], "metadata": {"complete": False}},
                          {"type": "FeatureCollection", "features": []},
                          {"type": "FeatureCollection", "features": [feature("b", [[0,0],[1,0],[1,1],[0,1],[0,0]])]})


if __name__ == "__main__":
    unittest.main()
