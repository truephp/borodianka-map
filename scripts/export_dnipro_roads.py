#!/usr/bin/env python3
"""Export named OSM road centerlines for the separate Dnipro SVG label overlay."""
import argparse
import json
from pathlib import Path

ROAD_TYPES = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "residential",
    "unclassified", "living_street", "service", "pedestrian"
}


def convert(src: Path, dst: Path):
    features = []
    with src.open(encoding="utf-8") as stream:
        for line in stream:
            line = line.lstrip("\x1e").strip()
            if not line:
                continue
            feature = json.loads(line)
            props = feature.get("properties") or {}
            geom = feature.get("geometry") or {}
            if props.get("highway") not in ROAD_TYPES:
                continue
            name = str(props.get("name:uk") or props.get("name") or "").strip()
            if not name or geom.get("type") not in ("LineString", "MultiLineString"):
                continue
            pieces = [geom["coordinates"]] if geom["type"] == "LineString" else geom["coordinates"]
            for idx, coords in enumerate(pieces):
                if len(coords) < 2:
                    continue
                features.append({"type": "Feature",
                                 "properties": {"name": name, "id": str(props.get("@id") or props.get("id") or "") + ":" + str(idx)},
                                 "geometry": {"type": "LineString", "coordinates": coords}})
    result = {"type": "FeatureCollection", "features": features}
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Exported {len(features)} named road segments to {dst} ({dst.stat().st_size} bytes)", flush=True)
    if not features:
        raise RuntimeError("No named road segments; refusing to publish empty overlay")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    convert(options.input, options.output)
