#!/usr/bin/env python3
"""Merge reviewed map edits and apply them to an immutable OSM source.

Usage:
  python scripts/build_map_patches.py merge --master data/borodianka-manual-overrides.json --incoming exported.json --output data/borodianka-manual-overrides.json
  python scripts/build_map_patches.py apply --original data/buildings.geojson --points data/address-points.geojson --master data/borodianka-manual-overrides.json --output /tmp/buildings.patched.geojson --report /tmp/patch-report.json

Never modify the original OSM file. Missing/changed base geometry fails closed,
except when an explicit approval pins the SHA-256 of the CURRENT OSM geometry.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

from apply_osm_address_overrides import apply_overrides

SOURCE = "manual-dtek-borodianka-review"


def geometry_digest(geometry):
    return hashlib.sha256(json.dumps(geometry, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def verify(patch):
    if patch.get("schemaVersion") != 1 or patch.get("source") != SOURCE:
        raise ValueError("Unsupported combined patch document")
    for field in ("decisions", "geometryPatches", "addressOverrides"):
        if not isinstance(patch.get(field, []), list):
            raise ValueError("Expected array: " + field)
    return patch


def normalized(patch):
    verify(patch)
    return {"schemaVersion": 1, "source": SOURCE,
            "decisions": deepcopy(patch.get("decisions", [])),
            "geometryPatches": deepcopy(patch.get("geometryPatches", [])),
            "addressOverrides": deepcopy(patch.get("addressOverrides", []))}


def identifiers(section, item):
    if section == "decisions":
        key = (item.get("city"), item.get("street"), str(item.get("house")))
        if not all(key):
            raise ValueError("Missing DTEK address key")
        return key
    if section == "geometryPatches":
        if item.get("source") != "osm":
            raise ValueError("Only OSM geometry patches are supported")
        key = item.get("id")
    else:
        key = item.get("osmId")
    if key is None or not str(key):
        raise ValueError("Missing OSM polygon ID in " + section)
    return str(key)


def index_unique(section, items):
    indexed = {}
    for entry in items:
        key = identifiers(section, entry)
        if key in indexed:
            raise ValueError(f"Duplicate {section} key: {key}")
        indexed[key] = entry
    return indexed


def merge(master, incoming):
    """Merge by stable ID, preserving untouched entries; new decisions win.

    For geometry/address changes to the same OSM way, retain the *original*
    baseline snapshot from the first patch, so repeated editor exports cannot
    silently rebase historical overrides to a newer OSM version.
    """
    base, change = normalized(master), normalized(incoming)
    merged = {"schemaVersion": 1, "source": SOURCE}
    for section in ("decisions", "geometryPatches", "addressOverrides"):
        old = index_unique(section, base[section])
        new = index_unique(section, change[section])
        for key, item in new.items():
            result = deepcopy(item)
            if section != "decisions" and key in old:
                original_baseline = old[key].get("baseGeometry")
                if original_baseline is not None:
                    if result.get("baseGeometry") is not None and result["baseGeometry"] != original_baseline:
                        raise ValueError(f"Conflicting original geometry baseline for {section}: {key}")
                    result["baseGeometry"] = deepcopy(original_baseline)
            old[key] = result
        merged[section] = list(old.values())
    return merged


def apply(original, points, master, approvals=None):
    """Return patched copy and report. On conflict, return no output.

    A missing baseline from a legacy patch also requires human approval.
    Approvals pin the exact hash of the current OSM geometry, not merely an ID.
    """
    doc = normalized(master)
    approvals = approvals or {}
    if original.get("type") != "FeatureCollection":
        raise ValueError("Expected FeatureCollection for OSM")
    output = deepcopy(original)
    features = {}
    for feature in output["features"]:
        ident = str((feature.get("properties") or {}).get("id", ""))
        if not ident or ident in features:
            raise ValueError("Missing or duplicate OSM building ID: " + ident)
        features[ident] = feature

    conflicts = []
    modified_ids = set()
    for section in ("geometryPatches", "addressOverrides"):
        for entry in doc[section]:
            ident = identifiers(section, entry)
            modified_ids.add(ident)
            feature = features.get(ident)
            if feature is None:
                conflicts.append({"source": section, "id": ident, "reason": "missing_building"})
                continue
            base = entry.get("baseGeometry")
            actual = feature["geometry"]
            # A former edit already incorporated into OSM is not a conflict.
            already = section == "geometryPatches" and entry.get("geometry") == actual
            if not already and base != actual:
                fingerprint = geometry_digest(actual)
                if approvals.get(ident) != fingerprint:
                    conflicts.append({"source": section, "id": ident,
                                      "reason": "missing_baseline" if base is None else "geometry_changed",
                                      "currentGeometrySha256": fingerprint})
    report = {"patchCounts": {k: len(doc[k]) for k in ("decisions", "geometryPatches", "addressOverrides")},
              "conflicts": conflicts, "modifiedBuildings": len(modified_ids)}
    if conflicts:
        return None, report

    for entry in doc["geometryPatches"]:
        ident = str(entry["id"])
        geometry = entry.get("geometry")
        if not isinstance(geometry, dict) or geometry.get("type") not in ("Polygon", "MultiPolygon"):
            raise ValueError("Invalid polygon geometry in patch: " + ident)
        # Source geometries remain unmodified (output is a deep copy).
        features[ident]["geometry"] = deepcopy(geometry)
    if doc["addressOverrides"]:
        # Use the shared address validator after applying new contours.
        decisions = {"schemaVersion": 1, "source": "borodianka-osm-building-address-overrides",
                     "overrides": doc["addressOverrides"]}
        apply_overrides(output, points, decisions)
    return output, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    merging = commands.add_parser("merge")
    merging.add_argument("--master", type=Path, required=True)
    merging.add_argument("--incoming", type=Path, required=True)
    merging.add_argument("--output", type=Path, required=True)
    applying = commands.add_parser("apply")
    applying.add_argument("--original", type=Path, required=True)
    applying.add_argument("--points", type=Path, required=True)
    applying.add_argument("--master", type=Path, required=True)
    applying.add_argument("--output", type=Path, required=True)
    applying.add_argument("--report", type=Path, required=True)
    applying.add_argument("--approvals", type=Path)
    args = parser.parse_args(argv)
    result = None
    if args.action == "merge":
        master = json.loads(args.master.read_text(encoding="utf-8"))
        incoming = json.loads(args.incoming.read_text(encoding="utf-8"))
        result = merge(master, incoming)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        print("Merged patch counts:", {k: len(result[k]) for k in ("decisions", "geometryPatches", "addressOverrides")})
    else:
        source = json.loads(args.original.read_text(encoding="utf-8"))
        points = json.loads(args.points.read_text(encoding="utf-8"))
        master = json.loads(args.master.read_text(encoding="utf-8"))
        approvals = json.loads(args.approvals.read_text(encoding="utf-8")).get("approvedGeometry", {}) if args.approvals else {}
        result, report = apply(source, points, master, approvals)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        if result is None:
            print(f"Blocked publication: {len(report['conflicts'])} OSM conflicts. Review {args.report}", file=sys.stderr)
            return 2
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":"))+"\n", encoding="utf-8")
        print("Published patched OSM buildings:", len(result["features"]))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print("Map patch error:", exc, file=sys.stderr)
        raise SystemExit(1)
