#!/usr/bin/env python3
"""Apply reviewed OSM polygon-address decisions to public buildings GeoJSON.

This does not edit OpenStreetMap or the encrypted Visicom dataset.
Usage:
  python scripts/apply_osm_address_overrides.py \
    --overrides borodianka-osm-address-overrides.json \
    --buildings data/buildings.geojson \
    --points data/address-points.geojson \
    --output data/buildings.geojson
"""
import argparse
import json
from pathlib import Path


SOURCE = "borodianka-osm-building-address-overrides"


def contains_point(point, geometry):
    def inside_ring(ring):
        x, y = point
        inside = False
        for i, (ax, ay) in enumerate(ring):
            bx, by = ring[i - 1]
            if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
                inside = not inside
        return inside

    if not isinstance(geometry, dict):
        return False
    kind = geometry.get("type")
    polygons = ([geometry["coordinates"]] if kind == "Polygon" else
                geometry["coordinates"] if kind == "MultiPolygon" else [])
    return any(rings and inside_ring(rings[0])
               and not any(inside_ring(hole) for hole in rings[1:])
               for rings in polygons)


def apply_overrides(buildings, points, decisions):
    if buildings.get("type") != "FeatureCollection" or points.get("type") != "FeatureCollection":
        raise ValueError("Expected FeatureCollections for buildings and points")
    if decisions.get("schemaVersion") != 1 or decisions.get("source") != SOURCE:
        raise ValueError("Unsupported OSM address decisions format")
    if not isinstance(decisions.get("overrides"), list):
        raise ValueError("Missing overrides array")

    buildings_by_id = {}
    for feature in buildings.get("features", []):
        ident = str((feature.get("properties") or {}).get("id", ""))
        if ident in buildings_by_id:
            raise ValueError("Duplicate OSM building ID: " + ident)
        buildings_by_id[ident] = feature
    points_by_id = {}
    for point in points.get("features", []):
        ident = str((point.get("properties") or {}).get("id", ""))
        if ident in points_by_id:
            raise ValueError("Duplicate OSM address node ID: " + ident)
        points_by_id[ident] = point

    seen = set()
    updated = 0
    for entry in decisions["overrides"]:
        ident = str(entry.get("osmId", ""))
        if ident in seen:
            raise ValueError("Duplicate polygon decision: " + ident)
        seen.add(ident)
        feature = buildings_by_id.get(ident)
        if feature is None:
            raise ValueError("Polygon ID is absent from buildings GeoJSON: " + ident)
        addresses = entry.get("addresses")
        if not isinstance(addresses, list):
            raise ValueError("Invalid addresses for polygon " + ident)
        include_original = entry.get("includeOriginal") is True
        properties = feature["properties"]
        original = (properties.get("street"), properties.get("housenumber"))
        normalized = []
        by_address = {}

        for address in addresses:
            if not isinstance(address, dict):
                raise ValueError("Invalid address entry")
            street, number = address.get("street"), address.get("housenumber")
            if not isinstance(street, str) or not street.strip() or not isinstance(number, str) or not number.strip():
                raise ValueError("Invalid street or house number")
            node_ids = address.get("pointIds")
            if not isinstance(node_ids, list):
                raise ValueError("Invalid node IDs for polygon " + ident)
            original_address = include_original and (street, number) == original and address.get("fromPolygon") is True
            if not node_ids and not original_address:
                raise ValueError("Address must come from the polygon or a contained OSM node")
            for node_id in node_ids:
                point = points_by_id.get(str(node_id))
                p = (point or {}).get("properties") or {}
                if (point is None or p.get("street") != street or p.get("housenumber") != number
                        or not contains_point(point["geometry"]["coordinates"], feature["geometry"])):
                    raise ValueError("Address node mismatch or outside polygon: " + str(node_id))
            key = (street, number)
            if key not in by_address:
                value = {"street": street, "housenumber": number, "pointIds": [], "fromPolygon": False}
                by_address[key] = value
                normalized.append(value)
            value = by_address[key]
            value["fromPolygon"] |= original_address
            value["pointIds"] = list(dict.fromkeys(value["pointIds"] + [str(x) for x in node_ids]))

        if include_original and not any(a["fromPolygon"] for a in normalized):
            raise ValueError("Original polygon address was selected but is missing")
        if normalized:
            properties["street"] = normalized[0]["street"]
            properties["housenumber"] = normalized[0]["housenumber"]
        else:
            properties.pop("street", None)
            properties.pop("housenumber", None)
        properties["addresses"] = normalized
        updated += 1
    return updated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overrides", type=Path, required=True)
    parser.add_argument("--buildings", type=Path, default=Path("data/buildings.geojson"))
    parser.add_argument("--points", type=Path, default=Path("data/address-points.geojson"))
    parser.add_argument("--output", type=Path, default=Path("data/buildings.geojson"))
    args = parser.parse_args()
    buildings = json.loads(args.buildings.read_text(encoding="utf-8"))
    points = json.loads(args.points.read_text(encoding="utf-8"))
    decisions = json.loads(args.overrides.read_text(encoding="utf-8"))
    count = apply_overrides(buildings, points, decisions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(buildings, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Applied {count} reviewed polygon address decisions to {args.output}")


if __name__ == "__main__":
    main()
