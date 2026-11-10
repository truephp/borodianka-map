#!/usr/bin/env python3
"""Export tiled, clipped OSM building footprints for the Dnipro Leaflet map.

Reads the same GeoJSON sequence used to render the static OSM base map.
Outputs independent GeoJSON tiles at zoom 15, with a manifest written last.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

import mercantile
from shapely.geometry import Polygon, MultiPolygon, box, mapping, shape


def polygon_parts(geom):
    if isinstance(geom, Polygon):
        if not geom.is_empty and geom.area:
            yield geom
    elif isinstance(geom, MultiPolygon):
        for poly in geom.geoms:
            yield from polygon_parts(poly)
    elif hasattr(geom, "geoms"):
        for part in geom.geoms:
            yield from polygon_parts(part)


def export_buildings(source: Path, boundary_path: Path, dest: Path, zoom: int = 15):
    boundary_doc = json.loads(boundary_path.read_text(encoding="utf-8"))
    boundary_geo = (boundary_doc["features"][0]["geometry"]
                    if boundary_doc.get("type") == "FeatureCollection"
                    else boundary_doc.get("geometry", boundary_doc))
    boundary = shape(boundary_geo)
    tiles = defaultdict(list)
    accepted = 0
    dropped = 0
    for number, line in enumerate(source.open(encoding="utf-8"), 1):
        line = line.lstrip("\x1e").strip()
        if not line:
            continue
        feature = json.loads(line)
        props = feature.get("properties") or {}
        if not props.get("building") and not props.get("building:part"):
            continue
        geo = feature.get("geometry")
        if not geo or geo.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        geom = shape(geo)
        if not geom.is_valid:
            geom = geom.buffer(0)
        if geom.is_empty or not geom.intersects(boundary):
            dropped += 1
            continue
        # Restrict the layer to the OSM city outline, not the padded raster bbox.
        geom = geom.intersection(boundary)
        if geom.is_empty:
            continue
        osm_id = str(props.get("@id") or feature.get("id") or props.get("id") or f"line:{number}")
        address = {k: str(props[k]) for k in (
            "addr:street", "addr:housenumber", "addr:unit", "addr:city",
        ) if props.get(k)}
        attributes = {"osmId": osm_id, "building": str(props.get("building") or props.get("building:part") or "yes"),
                      **address}
        west, south, east, north = geom.bounds
        for tile in mercantile.tiles(west, south, east, north, zooms=zoom):
            tile_bounds = box(*mercantile.bounds(tile))
            if not geom.intersects(tile_bounds):
                continue
            clipped = geom.intersection(tile_bounds)
            for part in polygon_parts(clipped):
                tiles[(tile.x, tile.y)].append({
                    "type": "Feature", "properties": attributes,
                    "geometry": mapping(part),
                })
        accepted += 1
        if accepted % 25000 == 0:
            print(f"Processed {accepted:,} OSM buildings", flush=True)
    dest.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    for (x, y), features in sorted(tiles.items()):
        target = dest / str(zoom) / str(x) / f"{y}.geojson"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"type": "FeatureCollection", "features": features},
                                     ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        total_bytes += target.stat().st_size
    manifest = {
        "type": "OSMBuildingTiles", "city": "dnipro", "zoom": zoom,
        "source": "OpenStreetMap", "buildingCount": accepted,
        "tileCount": len(tiles), "totalBytes": total_bytes,
        "droppedOutsideBoundary": dropped, "bounds": list(boundary.bounds),
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False), flush=True)
    if accepted == 0:
        raise RuntimeError("No OSM buildings were exported")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--boundary", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--zoom", type=int, default=15)
    args = parser.parse_args()
    if not 10 <= args.zoom <= 17:
        parser.error("--zoom must be between 10 and 17")
    export_buildings(args.input, args.boundary, args.out, args.zoom)


if __name__ == "__main__":
    main()
