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

from compare_dtek_shared_houses import extract_houses, house_key
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


def reversed_two_word_street(name):
    """Try a word-order variant only for a two-word normalized street name."""
    words = name.split()
    return " ".join(reversed(words)) if len(words) == 2 and words[0] != words[1] else None


def house_candidate_key(value):
    # Do not erase numeric subdivisions: 23 and 2/3 must never be candidates.
    # Canonical letter suffixes are already handled by house_key.
    return house_key(value)


def address_records(collection, source_override=None):
    for feature in collection.get("features", []):
        p = feature.get("properties") or {}
        source = source_override or p.get("source") or "osm"
        identifier = p.get("sourceId") or p.get("visicomId") or p.get("id")
        if identifier is None:
            continue
        # A reviewed polygon can have zero, one or several valid addresses.
        # An explicit empty list means none: do not fall back to stale tags.
        addresses = p.get("addresses")
        if not isinstance(addresses, list):
            addresses = [{"street": p.get("street"), "housenumber": p.get("housenumber")}]
        seen = set()
        for address in addresses:
            if not isinstance(address, dict):
                continue
            street, house = address.get("street"), address.get("housenumber")
            if not street or not house:
                continue
            kind, key = street_key(street)
            if not key:
                continue
            if source == "visicom" and p.get("street_type"):
                explicit_kind, _ = street_key(str(p["street_type"]).strip() + " " + str(street))
                if explicit_kind:
                    kind = explicit_kind
            dedupe = (kind, key, house_key(house))
            if dedupe in seen:
                continue
            seen.add(dedupe)
            yield {"source": source, "id": str(identifier), "street": street,
                   "house": str(house), "kind": kind, "streetKey": key,
                   "houseKey": house_key(house)}


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


def resolved_address_status(matches):
    """Multiple polygons are ambiguous only when sources differ.

    Several Visicom polygons (or several OSM polygons) may legitimately share
    one address. A Visicom/OSM combination needs manual source reconciliation.
    """
    return "multiple" if len({b["source"] for b in matches}) > 1 else "exact"


def match_houses(responses, building_records, aliases=None, roads=None, directory=None):
    # Alias overrides are human-reviewed, not guessed from string similarity.
    aliases = aliases or {}
    kinds = known_street_types(roads, directory, building_records)
    typed_idx = defaultdict(list)
    name_idx = defaultdict(list)
    name_loose_idx = defaultdict(list)
    building_names = {b["streetKey"] for b in building_records}
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
        # DTEK may return several spellings of the same address in one API
        # response (e.g. 230А and 230/А). Process the canonical address once.
        variants = defaultdict(list)
        for original in (entry["response"].get("data") or {}):
            variants[house_key(original)].append(original)
        # A different explicit building type is a conflict, never a match.
        for hkey, house in houses.items():
            same_name = name_idx.get((street_name, hkey), [])
            compatible = [b for b in same_name if b["kind"] is None or b["kind"] == street_type]
            if compatible:
                # Explicitly incompatible lanes/streets must never appear in
                # the candidate links, even if the number is identical.
                untyped = any(b["kind"] is None for b in compatible)
                if not street_type or (ambiguous_kind and untyped):
                    status, matches = "candidate_street_type", compatible
                else:
                    # Many polygons from one source may share an address.
                    # A cross-source Visicom/OSM combination remains ambiguous.
                    status, matches = resolved_address_status(compatible), compatible
            else:
                loose_all = name_loose_idx.get((street_name, house_candidate_key(house)), [])
                loose = [b for b in loose_all if b["kind"] is None or b["kind"] == street_type]
                if loose:
                    uncertain_type = not street_type or (
                        ambiguous_kind and any(b["kind"] is None for b in loose))
                    status = ("candidate_street_and_house_format" if uncertain_type
                              else "candidate_house_format")
                    matches = loose
                else:
                    # A same-name, same-number building of the opposite known
                    # street type is not a match or a review candidate.
                    status, matches = "unmatched", []
            # Fallback for two-word street names only. Never override an existing
            # original-name street, or downgrade a normal candidate to a guess.
            # The usual number, street/lane type, and ambiguity checks still apply.
            match_method = "normal"
            if status == "unmatched" and street_name not in building_names:
                swapped = reversed_two_word_street(street_name)
                if swapped:
                    swapped_same = name_idx.get((swapped, hkey), [])
                    swapped_kinds = kinds.get(swapped, set()) | available_kinds
                    swapped_ambiguous = len(swapped_kinds) > 1
                    swapped_compatible = [b for b in swapped_same
                                          if b["kind"] is None or b["kind"] == street_type]
                    if swapped_compatible:
                        untyped = any(b["kind"] is None for b in swapped_compatible)
                        if not street_type or (swapped_ambiguous and untyped):
                            status, matches = "candidate_street_type", swapped_compatible
                        else:
                            status, matches = resolved_address_status(swapped_compatible), swapped_compatible
                    else:
                        swapped_loose_all = name_loose_idx.get(
                            (swapped, house_candidate_key(house)), [])
                        swapped_loose = [b for b in swapped_loose_all
                                         if b["kind"] is None or b["kind"] == street_type]
                        if swapped_loose:
                            uncertain_type = not street_type or (
                                swapped_ambiguous and any(b["kind"] is None for b in swapped_loose))
                            status = ("candidate_street_and_house_format" if uncertain_type
                                      else "candidate_house_format")
                            matches = swapped_loose
                    if status != "unmatched":
                        match_method = "reversed_two_words"
            counts[status] += 1
            source_data = entry["response"].get("data")
            # The data dictionary keys are original house numbers; normalized
            # keys are only for matching, not for retrieving status payloads.
            house_fields = {}
            source_variants = variants.get(hkey, [house])
            dtek_fields = ("cek", "start_date", "end_date", "sub_type",
                           "sub_type_reason", "type", "voluntarily")
            if isinstance(source_data, dict):
                for original_number in source_variants:
                    payload = source_data.get(original_number)
                    if isinstance(payload, dict):
                        for field in dtek_fields:
                            if field in payload and (field not in house_fields or
                                                     house_fields[field] in (None, "", [])):
                                house_fields[field] = payload[field]
            out.append({"city": city, "street": street, "house": house, "status": status,
                        "dtek": house_fields, "houseVariants": source_variants,
                        "matchMethod": match_method,
                        "links": [{"source": b["source"], "id": b["id"],
                                   "street": b["street"], "house": b["house"]} for b in matches]})
    return {"schemaVersion": 2, "counts": dict(counts), "records": out}



def apply_manual_decisions(result, payload):
    """Apply reviewed DTEK links to the canonical report before encryption.

    Refuse stale/unknown polygon IDs instead of silently publishing an
    incorrect confirmation. Do not alter the source building GeoJSON.
    """
    if (payload.get("schemaVersion") != 1 or
            payload.get("source") != "manual-dtek-borodianka-review" or
            not isinstance(payload.get("decisions"), list)):
        raise ValueError("Unsupported manual DTEK decisions file")

    by_address = {}
    for record in result["records"]:
        key = (record.get("city"), record.get("street"), record.get("house"))
        if key in by_address:
            raise ValueError(f"Duplicate DTEK address in report: {key}")
        by_address[key] = record

    applied = 0
    seen = set()
    for decision in payload["decisions"]:
        key = (decision.get("city"), decision.get("street"), decision.get("house"))
        if key in seen:
            raise ValueError(f"Duplicate manual DTEK decision: {key}")
        seen.add(key)
        record = by_address.get(key)
        if record is None:
            raise ValueError(f"Manual DTEK address not found in report: {key}")
        if decision.get("action") != "confirm":
            raise ValueError(f"Unsupported manual DTEK action for {key}: {decision.get('action')}")
        selection = decision.get("links")
        if not isinstance(selection, list) or not selection:
            raise ValueError(f"Manual DTEK confirmation has no links: {key}")
        allowed = {(l["source"], str(l["id"])): l for l in record.get("links", [])}
        selected = set()
        links = []
        for item in selection:
            identifier = (item.get("source"), str(item.get("id")))
            if identifier in selected:
                raise ValueError(f"Duplicate confirmed polygon for {key}: {identifier}")
            selected.add(identifier)
            if identifier not in allowed:
                raise ValueError(f"Confirmed polygon is absent from DTEK candidates for {key}: {identifier}")
            links.append(allowed[identifier])
        previous_status = record["status"]
        record["status"] = "confirmed"
        record["links"] = links
        record["manualReview"] = {
            "action": "confirm",
            "initialStatus": decision.get("initialStatus"),
            "previousStatus": previous_status,
        }
        counts = result["counts"]
        counts[previous_status] -= 1
        if counts[previous_status] == 0:
            del counts[previous_status]
        counts["confirmed"] = counts.get("confirmed", 0) + 1
        applied += 1
    result["manualDecisionsApplied"] = applied
    return applied


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dtek", required=True, help="Captured DTEK house-number JSON")
    ap.add_argument("--osm", default="data/buildings.geojson")
    ap.add_argument("--roads", default="data/roads.geojson")
    ap.add_argument("--directory", default="data/dtek-borodianka-streets.json")
    ap.add_argument("--visicom-encrypted", help="Encrypted merged Visicom-first building GeoJSON")
    ap.add_argument("--aliases", help="Reviewed DTEK city|street to canonical street map")
    ap.add_argument("--manual-decisions", help="Reviewed manual DTEK links applied before report encryption")
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
    if args.manual_decisions:
        if not private:
            raise ValueError("Manual cross-source decisions require the encrypted unified report")
        decisions = json.loads(Path(args.manual_decisions).read_text(encoding="utf-8"))
        apply_manual_decisions(result, decisions)
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
               "encryptedDetailedReport": private,
               "manualDecisionsApplied": result.get("manualDecisionsApplied", 0)}
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
