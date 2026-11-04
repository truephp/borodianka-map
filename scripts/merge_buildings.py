#!/usr/bin/env python3
"""Build a *private, encrypted* Visicom-first unified building FeatureCollection.

Source: encrypted Visicom polygons + public OSM buildings. The original features
are not mutated, and distinct source IDs remain available for DTEK matching.
"""
import argparse
import base64
import json
import os
from collections import Counter
from pathlib import Path
from secrets import token_bytes

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from shapely.geometry import shape, mapping
from shapely.strtree import STRtree

ITERATIONS = 210000


def key_for(password, salt, iterations):
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                      iterations=iterations).derive(password.encode("utf-8"))


def decrypt(envelope, password):
    if envelope.get("version") != 1 or envelope.get("kdf") != "PBKDF2-SHA256":
        raise ValueError("Unsupported encrypted Visicom export")
    salt = base64.b64decode(envelope["salt"], validate=True)
    iv = base64.b64decode(envelope["iv"], validate=True)
    ciphertext = base64.b64decode(envelope["data"], validate=True)
    clear = AESGCM(key_for(password, salt, envelope["iterations"])).decrypt(iv, ciphertext, None)
    return json.loads(clear)


def encrypt(payload, password):
    salt, iv = token_bytes(16), token_bytes(12)
    clear = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ct = AESGCM(key_for(password, salt, ITERATIONS)).encrypt(iv, clear, None)
    return {"version": 1, "kdf": "PBKDF2-SHA256", "iterations": ITERATIONS,
            "salt": base64.b64encode(salt).decode(), "iv": base64.b64encode(iv).decode(),
            "data": base64.b64encode(ct).decode()}


def usable_feature(f):
    return isinstance(f, dict) and f.get("type") == "Feature" and isinstance(f.get("geometry"), dict) and f["geometry"].get("type") in ("Polygon", "MultiPolygon")


def create_merged(visicom_collection, osm_collection, boundary_collection,
                  iou_threshold=0.35, overlap_threshold=0.80):
    """Exclude OSM where ANY Visicom contour crosses configured overlap thresholds."""
    if not 0 < iou_threshold <= 1 or not 0 < overlap_threshold <= 1:
        raise ValueError("Overlap thresholds must be in (0,1]")
    if visicom_collection.get("type") != "FeatureCollection" or osm_collection.get("type") != "FeatureCollection":
        raise ValueError("Expected FeatureCollections")
    if visicom_collection.get("metadata", {}).get("complete") is False:
        raise ValueError("Refusing incomplete Visicom export")
    boundary = shape(boundary_collection["features"][0]["geometry"])
    if not boundary.is_valid:
        boundary = boundary.buffer(0)
    visicom, polygons, seen = [], [], set()
    for f in visicom_collection["features"]:
        if not usable_feature(f):
            continue
        vid = str(f.get("properties", {}).get("visicomId") or "")
        if not vid or vid in seen:
            continue
        g = shape(f["geometry"])
        if not g.is_valid:
            g = g.buffer(0)
        if g.is_empty or g.area <= 0 or not g.intersects(boundary):
            continue
        seen.add(vid)
        props = f.get("properties", {})
        visicom.append({"type": "Feature", "geometry": f["geometry"],
                         "properties": {"source": "visicom", "sourceId": vid,
                                        "visicomId": vid, "street": props.get("street") or None,
                                        "housenumber": props.get("name") or None,
                                        "name": props.get("name") or None,
                                        "matchStatus": "primary"}})
        polygons.append(g)

    tree = STRtree(polygons) if polygons else None
    supplemental = []
    skipped = Counter()
    for f in osm_collection["features"]:
        if not usable_feature(f):
            continue
        p = f.get("properties", {})
        oid = str(p.get("id") or "")
        if not oid:
            continue
        g = shape(f["geometry"])
        if not g.is_valid:
            g = g.buffer(0)
        if g.is_empty or g.area <= 0 or not g.intersects(boundary):
            skipped["outside"] += 1
            continue
        best_iou, best_overlap, best_visicom = 0.0, 0.0, None
        matched = False
        if tree:
            for idx in tree.query(g):
                other = polygons[int(idx)]
                if not g.intersects(other):
                    continue
                try:
                    intersection = g.intersection(other).area
                except Exception:
                    skipped["geometry_errors"] += 1
                    continue
                if intersection <= 0:
                    continue
                iou = intersection / (g.area + other.area - intersection)
                overlap = intersection / min(g.area, other.area)
                if iou > best_iou or overlap > best_overlap:
                    best_iou = max(best_iou, iou)
                    best_overlap = max(best_overlap, overlap)
                    best_visicom = visicom[int(idx)]["properties"]["visicomId"]
                if iou >= iou_threshold or overlap >= overlap_threshold:
                    skipped["overlap"] += 1
                    matched = True
                    break
            if matched:
                continue
        supplemental.append({"type": "Feature", "geometry": f["geometry"],
                             "properties": {"source": "osm", "sourceId": oid, "osmId": oid,
                                            "street": p.get("street") or None,
                                            "housenumber": p.get("housenumber") or None,
                                            "building": p.get("building") or None,
                                            "matchStatus": "partial_overlap" if best_overlap else "no_overlap",
                                            "bestIoU": round(best_iou, 5),
                                            "bestOverlap": round(best_overlap, 5),
                                            "candidateVisicomId": best_visicom}})
    features = visicom + supplemental
    return {"type": "FeatureCollection", "features": features,
            "metadata": {"mergedBuildings": True, "scope": "Borodianka, Bucha district, Kyiv oblast",
                         "visicom": len(visicom), "osmSupplemental": len(supplemental),
                         "osmSkippedOverlap": skipped["overlap"],
                         "osmOutside": skipped["outside"],
                         "geometryErrors": skipped["geometry_errors"],
                         "iouThreshold": iou_threshold,
                         "overlapThreshold": overlap_threshold,
                         "publicDistributionApproved": False}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--visicom", required=True)
    ap.add_argument("--osm", default="data/buildings.geojson")
    ap.add_argument("--boundary", default="data/boundary.geojson")
    ap.add_argument("--output", required=True)
    ap.add_argument("--iou", type=float, default=0.35)
    ap.add_argument("--overlap", type=float, default=0.8)
    args = ap.parse_args()
    password = os.environ.get("VISICOM_EXPORT_PASSWORD")
    if not password:
        raise SystemExit("Missing VISICOM_EXPORT_PASSWORD")
    vc = decrypt(json.loads(Path(args.visicom).read_text()), password)
    osm = json.loads(Path(args.osm).read_text())
    boundary = json.loads(Path(args.boundary).read_text())
    merged = create_merged(vc, osm, boundary, args.iou, args.overlap)
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(encrypt(merged, password), separators=(",", ":")) + "\n")
    print("MERGED_BUILDINGS " + json.dumps({**merged["metadata"], "total": len(merged["features"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
