#!/usr/bin/env python3
"""Small offline smoke test for the static raster tile renderer."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from shapely.geometry import Polygon, LineString
from scripts.build_osm_tiles import boundary_geometry, classify


class StaticTilesTest(unittest.TestCase):
    def test_buildings_are_never_rendered(self):
        box = Polygon([(29.92, 50.64), (29.921, 50.64),
                       (29.921, 50.641), (29.92, 50.641)])
        self.assertIsNone(classify({"building": "yes"}, box))
        self.assertIsNone(classify({"building:part": "yes"}, box))

    def test_small_static_export(self):
        c = boundary_geometry("data/boundary.geojson").centroid
        x, y = c.x, c.y
        road = {"type": "Feature", "properties": {"highway": "residential", "name": "Тест"},
                "geometry": {"type": "LineString",
                             "coordinates": [[x - .005, y], [x + .005, y]]}}
        park = {"type": "Feature", "properties": {"leisure": "park"},
                "geometry": {"type": "Polygon",
                             "coordinates": [[[x - .002, y - .002], [x + .002, y - .002],
                                              [x + .002, y + .002], [x - .002, y + .002],
                                              [x - .002, y - .002]]]}}
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "test.geojsonseq"
            source.write_text("".join("\x1e" + json.dumps(f) + "\n" for f in (road, park)))
            result = subprocess.run([sys.executable, "scripts/build_osm_tiles.py", "--input",
                                     str(source), "--out", str(Path(tmp) / "tiles"),
                                     "--min-zoom", "14", "--max-zoom", "14"],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((Path(tmp) / "tiles" / "manifest.json").read_text())
            self.assertGreater(manifest["totalTiles"], 0)
            self.assertFalse(manifest["buildingsRendered"])
            self.assertEqual(len(list((Path(tmp) / "tiles").rglob("*.webp"))),
                             manifest["totalTiles"])


if __name__ == "__main__":
    unittest.main()
