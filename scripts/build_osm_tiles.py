#!/usr/bin/env python3
"""Render a small, static, building-free OSM raster basemap to 256px WebP XYZ tiles.

Source input must be generated from OSM PBF, not downloaded raster tiles.
Dependencies: Pillow, Shapely >= 2, mercantile. No tile server/PostGIS required.
"""
import argparse
import json
import math
from collections import Counter
from pathlib import Path

import mercantile
from PIL import Image, ImageDraw
from shapely.geometry import shape, box, Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection
from shapely.strtree import STRtree

TILE_SIZE = 256
MAX_MERC_LAT = 85.05112878
COLORS = {
    "background": "#162231", "park": "#243b36", "forest": "#203932",
    "grass": "#2b393b", "residential": "#202e3d", "industrial": "#263039",
    "water": "#183f56", "waterline": "#32647b",
    "rail": "#556579", "path": "#4d6571", "minor": "#627384",
    "road": "#8796a3", "major": "#a7afb9", "text": "#d4dce3",
}


def boundary_geometry(path):
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if obj.get("type") == "FeatureCollection":
        geom = shape(obj["features"][0]["geometry"])
    elif obj.get("type") == "Feature":
        geom = shape(obj["geometry"])
    else:
        geom = shape(obj)
    if geom.is_empty:
        raise ValueError("Empty administrative boundary")
    return geom


def padded_bbox(geom, pad=0.18):
    west, south, east, north = geom.bounds
    dx, dy = (east - west) * pad, (north - south) * pad
    return west - dx, south - dy, east + dx, north + dy


def mercator_pixel(lon, lat, zoom):
    lat = max(-MAX_MERC_LAT, min(MAX_MERC_LAT, lat))
    sinlat = math.sin(math.radians(lat))
    scale = TILE_SIZE * (2 ** zoom)
    x = (lon + 180) / 360 * scale
    y = (0.5 - math.log((1 + sinlat) / (1 - sinlat)) / (4 * math.pi)) * scale
    return x, y


def classify(tags, geom):
    if tags.get("building") or tags.get("building:part"):
        return None
    if isinstance(geom, (Polygon, MultiPolygon)):
        if tags.get("natural") == "water" or tags.get("water") or tags.get("waterway") == "riverbank":
            return "water"
        if tags.get("landuse") in ("forest",) or tags.get("natural") == "wood":
            return "forest"
        if tags.get("leisure") in ("park", "garden", "nature_reserve"):
            return "park"
        if tags.get("landuse") in ("grass", "meadow") or tags.get("natural") in ("grassland", "scrub"):
            return "grass"
        if tags.get("landuse") == "residential":
            return "residential"
        if tags.get("landuse") in ("industrial", "commercial", "retail"):
            return "industrial"
    if isinstance(geom, (LineString, MultiLineString)):
        if tags.get("waterway") in ("river", "stream", "canal", "ditch"):
            return "waterline"
        if tags.get("railway") in ("rail", "light_rail"):
            return "rail"
        road = tags.get("highway")
        if road in ("motorway", "trunk", "primary", "secondary"):
            return "major"
        if road in ("tertiary", "residential", "unclassified", "living_street"):
            return "road"
        if road in ("service",):
            return "minor"
        if road in ("footway", "path", "cycleway", "pedestrian", "steps", "track"):
            return "path"
    return None


def load_features(path, area_bbox):
    wanted = box(*area_bbox)
    items, categories = [], Counter()
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            line = line.lstrip("\x1e").strip()
            if not line:
                continue
            obj = json.loads(line)
            tags = obj.get("properties") or {}
            geo = obj.get("geometry")
            if not geo:
                continue
            geom = shape(geo)
            if geom.is_empty or not geom.is_valid and geom.geom_type not in ("Polygon", "MultiPolygon"):
                continue
            category = classify(tags, geom)
            if category is None or not geom.intersects(wanted):
                continue
            items.append((geom, category, str(tags.get("name", ""))[:80]))
            categories[category] += 1
    return items, categories


def parts(geom, types):
    if geom.is_empty:
        return
    if isinstance(geom, types):
        yield geom
    elif hasattr(geom, "geoms"):
        for g in geom.geoms:
            yield from parts(g, types)


def render_tile(tile, tree, features):
    image = Image.new("RGB", (TILE_SIZE, TILE_SIZE), COLORS["background"])
    draw = ImageDraw.Draw(image)
    west, south, east, north = mercantile.bounds(tile)
    # Clip to a slightly larger envelope to preserve thick strokes at tile edges.
    bounds = box(west - (east - west) * .03, south - (north - south) * .03,
                 east + (east - west) * .03, north + (north - south) * .03)
    origin_x, origin_y = tile.x * TILE_SIZE, tile.y * TILE_SIZE

    def xy(point):
        px, py = mercator_pixel(point[0], point[1], tile.z)
        return (round(px - origin_x, 2), round(py - origin_y, 2))

    candidates = []
    for index in tree.query(bounds):
        geom, kind, name = features[int(index)]
        try:
            clipped = geom.intersection(bounds)
            if not clipped.is_empty:
                candidates.append((clipped, kind, name))
        except Exception:
            continue
    order = {"residential": 0, "industrial": 1, "forest": 2, "park": 3,
             "grass": 4, "water": 5, "rail": 6, "path": 7,
             "minor": 8, "road": 9, "major": 10, "waterline": 11}
    candidates.sort(key=lambda row: order[row[1]])
    for geom, kind, name in candidates:
        if kind in ("residential", "industrial", "forest", "park", "grass", "water"):
            for poly in parts(geom, (Polygon,)):
                coords = [xy(p) for p in poly.exterior.coords]
                if len(coords) >= 3:
                    draw.polygon(coords, fill=COLORS[kind])
                    for ring in poly.interiors:
                        draw.polygon([xy(p) for p in ring.coords], fill=COLORS["background"])
        else:
            for line in parts(geom, (LineString,)):
                coords = [xy(p) for p in line.coords]
                if len(coords) < 2:
                    continue
                width = {"major": 4, "road": 3, "minor": 2,
                         "waterline": 3, "rail": 2, "path": 1}[kind]
                if tile.z < 15 and kind in ("minor", "path"):
                    continue
                draw.line(coords, fill=COLORS[kind], width=width, joint="curve")
    return image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--boundary", default="data/boundary.geojson")
    parser.add_argument("--city", default="borodianka")
    parser.add_argument("--input", help="OSM GeoJSON sequence exported by osmium")
    parser.add_argument("--out", default="dist/tiles")
    parser.add_argument("--min-zoom", type=int, default=13)
    parser.add_argument("--max-zoom", type=int, default=19)
    parser.add_argument("--padding", type=float, default=.18)
    parser.add_argument("--quality", type=int, default=78)
    parser.add_argument("--print-bbox", action="store_true")
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    args = parser.parse_args()
    boundary = boundary_geometry(args.boundary)
    bbox = padded_bbox(boundary, args.padding)
    if args.print_bbox:
        print(",".join(f"{v:.7f}" for v in bbox))
        return
    if not args.input:
        parser.error("--input is required unless --print-bbox")
    if not 0 <= args.min_zoom <= args.max_zoom <= 19:
        parser.error("zoom range must be within 0..19")
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        parser.error("--shard-index must be within [0, --shard-count)")
    features, categories = load_features(args.input, bbox)
    if not features:
        raise RuntimeError("No usable OSM features; refusing to publish blank tiles")
    print("OSM features:", len(features), dict(categories), flush=True)
    tree = STRtree([row[0] for row in features])
    output = Path(args.out)
    count, per_zoom = 0, {}
    total_bytes, bytes_by_zoom = 0, {}
    buffered_boundary = boundary.buffer(max(boundary.bounds[2] - boundary.bounds[0],
                                            boundary.bounds[3] - boundary.bounds[1]) * args.padding)
    for z in range(args.min_zoom, args.max_zoom + 1):
        current = 0
        zoom_bytes = 0
        for tile in mercantile.tiles(*bbox, zooms=z):
            if (tile.x * 1000003 + tile.y) % args.shard_count != args.shard_index:
                continue
            if not buffered_boundary.intersects(box(*mercantile.bounds(tile))):
                continue
            file = output / str(z) / str(tile.x) / f"{tile.y}.webp"
            file.parent.mkdir(parents=True, exist_ok=True)
            image = render_tile(tile, tree, features)
            image.save(file, format="WEBP", quality=args.quality, method=4)
            zoom_bytes += file.stat().st_size
            current += 1
        per_zoom[str(z)] = current
        bytes_by_zoom[str(z)] = zoom_bytes
        count += current
        total_bytes += zoom_bytes
        print(f"zoom {z}: {current} tiles, {zoom_bytes/1024/1024:.2f} MiB; total {count} tiles, {total_bytes/1024/1024:.2f} MiB", flush=True)
    manifest = {"type": "StaticOSMTiles", "city": args.city, "scheme": "xyz", "format": "webp",
                "minZoom": args.min_zoom, "maxZoom": args.max_zoom,
                "bounds": [round(v, 7) for v in bbox], "tileSize": TILE_SIZE,
                "counts": per_zoom, "totalTiles": count,
                "bytesByZoom": bytes_by_zoom, "totalBytes": total_bytes,
                "averageTileBytes": round(total_bytes/count, 1) if count else 0,
                "shardIndex": args.shard_index, "shardCount": args.shard_count,
                "attribution": "© OpenStreetMap contributors (ODbL)",
                "buildingsRendered": False}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Generated", count, "tiles", flush=True)


if __name__ == "__main__":
    main()
