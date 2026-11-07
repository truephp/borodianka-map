import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parent))
from build_map_patches import apply, geometry_digest, merge


def polygon(x=0):
    return {"type": "Polygon", "coordinates": [[[x, 0], [x+2, 0],
            [x+2, 2], [x, 2], [x, 0]]]}


def feature(identifier, x=0):
    return {"type": "Feature", "properties": {"id": identifier, "street": "Семашка",
            "housenumber": "3"}, "geometry": polygon(x)}


def doc(geometry=None, address=None, decisions=None):
    return {"schemaVersion": 1, "source": "manual-dtek-borodianka-review",
            "decisions": decisions or [], "geometryPatches": geometry or [],
            "addressOverrides": address or []}


class CumulativeMapPatchTests(unittest.TestCase):
    def setUp(self):
        self.original = {"type": "FeatureCollection", "features": [feature(7), feature(8, 5)]}
        self.points = {"type": "FeatureCollection", "features": []}
        self.patch = {"source": "osm", "id": "7", "baseGeometry": polygon(),
                      "geometry": polygon(1)}

    def test_merge_preserves_unrelated_edits(self):
        decision = {"city": "Бородянка", "street": "Семашка", "house": "3",
                    "action": "confirm", "links": [{"source": "osm", "id": "7"}]}
        before = doc([self.patch], decisions=[decision])
        after = doc(address=[{"osmId": "8", "baseGeometry": polygon(5),
                              "includeOriginal": False, "addresses": []}])
        combined = merge(before, after)
        self.assertEqual(len(combined["geometryPatches"]), 1)
        self.assertEqual(len(combined["addressOverrides"]), 1)
        self.assertEqual(len(combined["decisions"]), 1)

    def test_merge_latest_wins_same_id_but_keeps_first_baseline(self):
        first = doc([self.patch])
        updated = doc([dict(self.patch, geometry=polygon(2))])
        merged = merge(first, updated)
        self.assertEqual(merged["geometryPatches"][0]["geometry"], polygon(2))
        self.assertEqual(merged["geometryPatches"][0]["baseGeometry"], polygon())

    def test_changed_baseline_rejected_on_merge(self):
        first = doc([self.patch])
        newer = doc([dict(self.patch, baseGeometry=polygon(9))])
        with self.assertRaisesRegex(ValueError, "Conflicting original geometry baseline"):
            merge(first, newer)

    def test_source_not_mutated(self):
        src = copy.deepcopy(self.original)
        output, report = apply(src, self.points, doc([self.patch]))
        self.assertFalse(report["conflicts"])
        self.assertEqual(output["features"][0]["geometry"], polygon(1))
        self.assertEqual(src, self.original)

    def test_changed_osm_requires_manual_approval_hash(self):
        changed = copy.deepcopy(self.original)
        changed["features"][0]["geometry"] = polygon(3)
        output, report = apply(changed, self.points, doc([self.patch]))
        self.assertIsNone(output)
        self.assertEqual(report["conflicts"][0]["reason"], "geometry_changed")
        approved = {"7": geometry_digest(polygon(3))}
        result, report = apply(changed, self.points, doc([self.patch]), approved)
        self.assertFalse(report["conflicts"])
        self.assertEqual(result["features"][0]["geometry"], polygon(1))

    def test_missing_baseline_blocks_legacy_geometry(self):
        patch = {k: v for k, v in self.patch.items() if k != "baseGeometry"}
        result, report = apply(self.original, self.points, doc([patch]))
        self.assertIsNone(result)
        self.assertEqual(report["conflicts"][0]["reason"], "missing_baseline")

    def test_address_decisions_consider_changed_geometry(self):
        address = {"osmId": "7", "includeOriginal": False, "baseGeometry": polygon(),
                   "addresses": []}
        result, report = apply(self.original, self.points, doc(address=[address]))
        self.assertFalse(report["conflicts"])
        self.assertEqual(result["features"][0]["properties"]["addresses"], [])
        changed = copy.deepcopy(self.original)
        changed["features"][0]["geometry"] = polygon(9)
        result, report = apply(changed, self.points, doc(address=[address]))
        self.assertIsNone(result)

    def test_invalid_geometry_blocks_export(self):
        patch = dict(self.patch, geometry={"type": "Polygon", "coordinates":
                      [[[0, 0], [2, 2], [0, 2], [2, 0], [0, 0]]]})
        with self.assertRaisesRegex(ValueError, "Zero-area|Self-intersecting"):
            apply(self.original, self.points, doc([patch]))

    def test_unclosed_ring_blocks_export(self):
        patch = dict(self.patch, geometry={"type": "Polygon", "coordinates":
                      [[[0, 0], [2, 0], [2, 2], [0, 2]]]})
        with self.assertRaisesRegex(ValueError, "Unclosed"):
            apply(self.original, self.points, doc([patch]))

    def test_missing_building_blocks(self):
        patch = dict(self.patch, id="999")
        result, report = apply(self.original, self.points, doc([patch]))
        self.assertIsNone(result)
        self.assertEqual(report["conflicts"][0]["reason"], "missing_building")

    def test_merge_idempotent(self):
        master = doc([self.patch])
        result = merge(master, master)
        self.assertEqual(result["geometryPatches"], master["geometryPatches"])
        self.assertEqual(result["masterRevision"], 1)

    def test_stale_export_cannot_overwrite_newer_master(self):
        current = dict(doc([self.patch]), masterRevision=4)
        previous = dict(doc([dict(self.patch, geometry=polygon(3))]), baseRevision=3)
        with self.assertRaisesRegex(ValueError, "Stale patch export"):
            merge(current, previous)
        previous["baseRevision"] = 4
        self.assertEqual(merge(current, previous)["masterRevision"], 5)


if __name__ == "__main__":
    unittest.main()
