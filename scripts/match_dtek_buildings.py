#!/usr/bin/env python3
"""Audit DTEK house addresses against OSM and the encrypted unified building layer.

A missing Visicom street type is accepted when the street name and house
number uniquely match and neither the OSM roads nor DTEK directories nor
building records contain a conflicting street/lane type. Spelling variants
remain review candidates. Visicom derived records must remain encrypted.
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


def known_street_types(roads=None, directory=None, buildings=()):
    """Return explicit street/lane types by normalized name across all sources.

    Missing Visicom type never introduces a type, and a conflicting explicit
    type anywhere is enough to require manual review.
    """
    names = defaultdict(set)
    for item in buildings:
        if item["kind"]:
            names[item["streetKey"]].add(item["kind"])
    for feature in (roads or {}).get("features", []):
        street = (feature.get("properties") or {}).get("name")
        if street:
            kind, name = street_key(street)
            if kind and name:
                names[name].add(kind)
    for streets in (directory or {}).get("streets", {}).values():
        for street in streets:
            kind, name = street_key(street)
            if kind and name:
                names[name].add(kind)
    return names


def match_houses(responses, building_records, aliases=None, roads=None, directory=None):
    # Alias overrides are human-reviewed, not guessed from string similarity.
    aliases = aliases or {}
    kinds = known_street_types(roads, directory, building_records)
    typed_idx = defaultdict(list)
    name_idx = defaultdict(list)
    name_loose_idx = defaultdict(list)
    for building in building_records:
        key = (building["kind"], building["streetKey"])
        typed_idx[(key, building["houseKey"])].append(building)
        name_idx[(building["streetKey"], building["houseKey"])].append(building)
        name_loose_idx[(building["streetKey"], house_candidate_key(building["house"]))].append(building)

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

        available_kinds = kinds.get(street_name, set())
        ambiguous_kind = len(available_kinds) > 1
        # A different explicit building type is a conflict, never a match.
        for house in houses.values():
            hkey = house_key(house)
            same_name = name_idx.get((street_name, hkey), [])
            compatible = [b for b in same_name if b["kind"] is None or b["kind"] == street_type]
            conflicting = [b for b in same_name if b["kind"] and b["kind"] != street_type]
            if same_name:
                if conflicting or ambiguous_kind or not street_type:
                    # An untyped Visicom address cannot choose between a street and lane.
                    status, matches = "candidate_street_type", same_name
                elif len(compatible) == 1:
                    status, matches = "exact", compatible
                elif len(compatible) > 1:
                    status, matches = "multiple", compatible
                else:
                    status, matches = "candidate_street_type", same_name
            else:
                loose = name_loose_idx.get((street_name, house_candidate_key(house)), [])
                if loose:
                    status = ("candidate_house_format"
                              if street_type and not ambiguous_kind
                              and all(b["kind"] in (None, street_type) for b in loose)
                              else "candidate_street_and_house_format")
                    matches = loose
                else:
                    status, matches = "unmatched", []
            counts[status] += 1
            source_data = entry["response"].get("data")
            # The data dictionary keys are original house numbers; normalized
            # keys are only for matching, not for retrieving status payloads.
            house_fields = {}
            if isinstance(source_data, dict):
                for original_number, payload in source_data.items():
                    if house_key(original_number) == house_key(house) and isinstance(payload, dict):
                        house_fields = {k: payload[k] for k in (
                            "cek", "start_date", "end_date", "sub_type",
                            "sub_type_reason", "type", "voluntarily"
                        ) if k in payload}
                        break
            out.append({"city": city, "street": street, "house": house, "status": status,
                        "dtek": house_fields,
                        "links": [{"source": b["source"], "id": b["id"],
                                   "street": b["street"], "house": b["house"]} for b in matches]})
    return {"schemaVersion": 2, "counts": dict(counts), "records": out}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dtek", required=True, help="Captured DTEK house-number JSON")
    ap.add_argument("--osm", default="data/buildings.geojson")
    ap.add_argument("--roads", default="data/roads.geojson")
    ap.add_argument("--directory", default="data/dtek-borodianka-streets.json")
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
    roads = json.loads(Path(args.roads).read_text(encoding="utf-8"))
    directory = json.loads(Path(args.directory).read_text(encoding="utf-8"))
    result = match_houses(raw["responses"], buildings, aliases, roads=roads, directory=directory)
    result["sourceFetchedAt"] = raw.get("fetchedAt")
    result["buildingSources"] = dict(Counter(b["source"] for b in buildings))
    # Aggregate-only diagnostics: never expose decrypted Visicom addresses.
    source_names = {b["streetKey"] for b in buildings}
    source_typed_names = {(b["kind"], b["streetKey"]) for b in buildings}
    source_houses = {b["houseKey"] for b in buildings}
    source_candidate_houses = {house_candidate_key(b["house"]) for b in buildings}
    source_pairs = {(b["streetKey"], b["houseKey"]) for b in buildings}
    source_candidate_pairs = {(b["streetKey"], house_candidate_key(b["house"])) for b in buildings}
    measurements = Counter()
    for r in result["records"]:
        if "house" not in r:
            continue
        street_type, street_name = street_key(r["street"])
        name_alias = aliases.get(f'{r["city"]}|{r["street"]}')
        if name_alias:
            street_type, street_name = street_key(name_alias)
        house = house_key(r["house"])
        measurements["dtekTotal"] += 1
        measurements["streetNameFound"] += street_name in source_names
        measurements["streetNameAndTypeFound"] += (street_type, street_name) in source_typed_names
        measurements["houseNumberAnywhereFound"] += house in source_houses
        measurements["houseNumberVariantAnywhereFound"] += house_candidate_key(r["house"]) in source_candidate_houses
        measurements["nameAndHouseIgnoringTypeFound"] += (street_name, house) in source_pairs
        measurements["nameAndHouseVariantIgnoringTypeFound"] += (street_name, house_candidate_key(r["house"])) in source_candidate_pairs
    result["diagnosticCounts"] = dict(measurements)
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
               "diagnosticCounts": result["diagnosticCounts"],
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
