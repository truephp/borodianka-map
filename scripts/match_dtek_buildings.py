#!/usr/bin/env python3
"""Audit DTEK house addresses against OSM and the encrypted unified building layer.

Street type and house suffix are preserved for exact matching. Variations of
slash, Latin/Cyrillic characters, street aliases and reversed names are only
review candidates. Visicom derived records must remain encrypted.
"""
import argparse
from collections import defaultdict, Counter
import json
import os
from pathlib import Path
import re
import sys
import unicodedata

from compare_dtek_shared_houses import extract_houses
from match_dtek_streets import normalize_street

STREET_PREFIX = re.compile(r"^(вулиця|вул\.?|провулок|пров\.?)\s+", re.I)
STREET_SUFFIX = re.compile(r"\s+(вулиця|вул\.?|провулок|пров\.?)$", re.I)
STREET_KIND = {"вулиця": "street", "вул": "street", "провулок": "lane", "пров": "lane"}


def street_key(value):
    value = unicodedata.normalize("NFKC", str(value or "")).casefold().replace("’", "'")
    value = re.sub(r"\s+", " ", value).strip()
    m = STREET_PREFIX.search(value)
    if m:
        kind = STREET_KIND[m.group(1).rstrip(".")]
    else:
        m = STREET_SUFFIX.search(value)
        kind = STREET_KIND[m.group(1).rstrip(".")] if m else None
    return kind, normalize_street(value)


def house_key(value):
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"\s+", "", value.replace("’", "'").replace("ʼ", "'"))


def house_candidate_key(value):
    # Candidate-only: never use this aggressive normalizer for confirmed links.
    s = house_key(value).translate(str.maketrans({"а": "a", "в": "b", "с": "c", "е": "e",
                                                   "н": "h", "к": "k", "м": "m", "о": "o",
                                                   "р": "p", "т": "t", "х": "x"}))
    return re.sub(r"[/\\\-.]", "", s)


def address_records(collection, source_override=None):
    for feature in collection.get("features", []):
        p = feature.get("properties") or {}
        street, house = p.get("street"), p.get("housenumber")
        if not street or not house:
            continue
        kind, key = street_key(street)
        if not key:
            continue
        source = source_override or p.get("source") or "osm"
        identifier = p.get("sourceId") or p.get("visicomId") or p.get("id")
        if identifier is None:
            continue
        yield {"source": source, "id": str(identifier), "street": street, "house": str(house),
               "kind": kind, "streetKey": key, "houseKey": house_key(house)}


def match_houses(responses, building_records, aliases=None):
    # Alias overrides are human-reviewed, not guessed from string similarity.
    aliases = aliases or {}
    idx = defaultdict(list)
    loose_idx = defaultdict(list)
    for building in building_records:
        key = (building["kind"], building["streetKey"])
        idx[(key, building["houseKey"])].append(building)
        loose_idx[(key, house_candidate_key(building["house"]))].append(building)

    out, counts = [], Counter()
    for entry in responses:
        city, street = entry["city"], entry["street"]
        if entry.get("error") or "response" not in entry:
            counts["source_error"] += 1
            out.append({"city": city, "street": street, "status": "source_error",
                        "error": entry.get("error") or "missing getHomeNum response"})
            continue
        try:
            houses = extract_houses(entry["response"])
        except ValueError as exc:
            counts["source_error"] += 1
            out.append({"city": city, "street": street, "status": "source_error", "error": str(exc)})
            continue
        street_type, street_name = street_key(street)
        alias = aliases.get(f"{city}|{street}")
        if alias:
            street_type, street_name = street_key(alias)
        for house in houses.values():
            key = ((street_type, street_name), house_key(house))
            exact = idx.get(key, [])
            # Never automatically promote near matches (incl. Cyrillic vs Latin letters)
            candidate = loose_idx.get(((street_type, street_name), house_candidate_key(house)), [])
            if exact:
                # Multiple physical outlines with the same address are ambiguous.
                status = "exact" if len(exact) == 1 else "multiple"
                matches = exact
            elif candidate:
                status, matches = "candidate", candidate
            else:
                status, matches = "unmatched", []
            counts[status] += 1
            out.append({"city": city, "street": street, "house": house, "status": status,
                        "links": [{"source": b["source"], "id": b["id"],
                                   "street": b["street"], "house": b["house"]} for b in matches]})
    return {"schemaVersion": 1, "counts": dict(counts), "records": out}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dtek", required=True, help="Captured DTEK house-number JSON")
    ap.add_argument("--osm", default="data/buildings.geojson")
    ap.add_argument("--visicom-encrypted", help="Encrypted merged Visicom-first building GeoJSON")
    ap.add_argument("--aliases", help="Reviewed DTEK city|street to canonical street map")
    ap.add_argument("--output", required=True)
    ap.add_argument("--summary", help="Save public aggregate counts only")
    args = ap.parse_args(argv)
    raw = json.loads(Path(args.dtek).read_text(encoding="utf-8"))
    if not isinstance(raw.get("responses"), list):
        raise ValueError("Expected DTEK responses array")
    buildings = list(address_records(json.loads(Path(args.osm).read_text(encoding="utf-8"))))
    private = bool(args.visicom_encrypted)
    if private:
        from merge_buildings import decrypt, encrypt
        password = os.environ.get("VISICOM_EXPORT_PASSWORD")
        if not password:
            raise ValueError("Missing VISICOM_EXPORT_PASSWORD")
        merged = decrypt(json.loads(Path(args.visicom_encrypted).read_text(encoding="utf-8")), password)
        if merged.get("type") != "FeatureCollection":
            raise ValueError("Unexpected unified buildings shape")
        # Unified layer is authoritative, avoid counting OSM buildings twice.
        buildings = list(address_records(merged))
    aliases = json.loads(Path(args.aliases).read_text(encoding="utf-8")) if args.aliases else {}
    if not isinstance(aliases, dict):
        raise ValueError("Aliases must be a JSON object")
    result = match_houses(raw["responses"], buildings, aliases)
    result["buildingSources"] = dict(Counter(b["source"] for b in buildings))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if private:
        output.write_text(json.dumps(encrypt(result, password), ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {"dtekAddressCount": sum(v for k, v in result["counts"].items() if k != "source_error"),
               "sourceErrors": result["counts"].get("source_error", 0),
               "counts": result["counts"], "buildingsWithAddress": len(buildings),
               "buildingSources": result["buildingSources"],
               "encryptedDetailedReport": private}
    if args.summary:
        Path(args.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if not summary["sourceErrors"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(f"Address matching error: {exc}", file=sys.stderr)
        raise SystemExit(1)
