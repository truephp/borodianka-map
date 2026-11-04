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

    def test_overlap_statistics_and_ambiguous_candidates(self):
        boundary = {"type": "FeatureCollection", "features": [
            feature("boundary", [[0,0],[20,0],[20,20],[0,20],[0,0]])]}
        vc = {"type": "FeatureCollection", "metadata": {"complete": True}, "features": [
            feature("vis1", [[1,1],[3,1],[3,3],[1,3],[1,1]], "visicom"),
            feature("vis2", [[3,1],[5,1],[5,3],[3,3],[3,1]], "visicom")]}
        osm = {"type": "FeatureCollection", "features": [
            feature("a", [[2,1],[4,1],[4,3],[2,3],[2,1]]),
            feature("b", [[1,1],[3,1],[3,3],[1,3],[1,1]]),
            feature("c", [[10,10],[11,10],[11,11],[10,11],[10,10]])]}
        r = create_merged(vc, osm, boundary, iou_threshold=0.35, overlap_threshold=0.5)
        m = r["metadata"]
        stats = m["overlapStatistics"]
        self.assertEqual(m["osmSkippedOverlap"], 2)
        self.assertEqual(m["osmSupplemental"], 1)
        self.assertEqual(stats["histogram"], {"0-25%": 1, "25-50%": 0, "50-75%": 1, "75-100%": 1})
        self.assertEqual(stats["excluded"], {"0-25%": 0, "25-50%": 0, "50-75%": 1, "75-100%": 1})
        self.assertEqual(stats["noOverlap"], 1)
        self.assertEqual(stats["ambiguousOSM"], 1)
        self.assertEqual(stats["ambiguousOSMQualifying"], 1)
        self.assertEqual(stats["ambiguousVisicom"], 2)
        self.assertEqual(stats["ambiguousVisicomQualifying"], 2)
        self.assertEqual(sum(stats["histogram"].values()),
                         m["osmSkippedOverlap"] + m["osmSupplemental"])

    def test_exact_overlap_bin_boundaries(self):
        from scripts.merge_buildings import overlap_bin
        self.assertEqual([overlap_bin(x) for x in [0, 0.249, 0.25, 0.499, 0.5, 0.749, 0.75, 1]],
                         ["0-25%", "0-25%", "25-50%", "25-50%", "50-75%", "50-75%", "75-100%", "75-100%"])

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
