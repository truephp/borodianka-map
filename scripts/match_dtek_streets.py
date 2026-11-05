#!/usr/bin/env python3
"""Compare an exported DTEK street directory with OSM road names.

This tool has no network access and does not assume a particular DTEK API.
An input file may contain a JSON array of street names, or an object containing
a `streets` map keyed by city (as observed by search-estate/tools/dtek-houses.mjs).
"""
import argparse
from collections import defaultdict
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import sys
import unicodedata

STREET_TYPES = (
    r"вулиця", r"вул\.?", r"провулок", r"пров\.?", r"проспект",
    r"просп\.?", r"площа", r"пл\.?", r"бульвар", r"бульв\.?",
    r"узвіз", r"шосе", r"дорога", r"набережна", r"алея",
)
TYPE_PATTERN = re.compile(r"^(?:" + "|".join(STREET_TYPES) + r")\s+", re.I)
TRAILING_TYPE_PATTERN = re.compile(r"\s+(?:" + "|".join(STREET_TYPES) + r")$", re.I)


# Reviewed Borodianka DTEK / Visicom street-name equivalents.
# Avoid general word reordering: only these verified variants are canonicalized.
REVIEWED_STREET_ALIASES = {
    "костенко ліни": "ліни костенко",
    "чорновола в'ячеслава": "чорновола",
    "хмельницького богдана": "богдана хмельницького",
    "здвижовий": "здвиженський",
    "млинова": "млиновий",
}


def normalize_street(value):
    s = unicodedata.normalize("NFKC", str(value or "")).casefold()
    s = s.replace("’", "'").replace("ʼ", "'").replace("‘", "'")
    s = re.sub(r"[.,]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = TYPE_PATTERN.sub("", s)
    s = TRAILING_TYPE_PATTERN.sub("", s)
    name = re.sub(r"\s+", " ", s).strip()
    return REVIEWED_STREET_ALIASES.get(name, name)


def load_dtek_streets(raw, city=None):
    if isinstance(raw, list):
        result = raw
    elif isinstance(raw, dict):
        if isinstance(raw.get("streets"), dict):
            raw = raw["streets"]
        if city:
            if city not in raw:
                raise ValueError("City not found in DTEK export: " + city)
            result = raw[city]
        else:
            raise ValueError("DTEK object requires --city (must match an exact source key)")
    else:
        raise ValueError("DTEK export must be an array or a city->streets object")
    if not isinstance(result, list) or not all(isinstance(s, str) for s in result):
        raise ValueError("DTEK streets must be an array of strings")
    return sorted(set(s.strip() for s in result if s.strip()))


def compare_streets(dtek_names, osm_features, aliases=None, min_score=0.72):
    aliases = aliases or {}
    normalized_aliases = {normalize_street(k): normalize_street(v) for k, v in aliases.items()}
    osm = defaultdict(set)
    for feature in osm_features:
        if feature.get("geometry", {}).get("type") != "LineString":
            continue
        name = feature.get("properties", {}).get("name")
        if name and normalize_street(name):
            osm[normalize_street(name)].add(name)
    result = []
    for dtek in dtek_names:
        norm = normalize_street(dtek)
        key = normalized_aliases.get(norm, norm)
        if key in osm:
            names = sorted(osm[key])
            result.append({"dtek": dtek, "normalized": norm, "status": "alias" if key != norm else "exact", "osm": names})
            continue
        ranked = sorted(
            ((SequenceMatcher(None, key, candidate).ratio(), candidate) for candidate in osm),
            key=lambda item: (-item[0], item[1]),
        )
        candidates = [
            {"score": round(score, 3), "osm": sorted(osm[candidate])}
            for score, candidate in ranked[:5] if score >= min_score
        ]
        result.append({"dtek": dtek, "normalized": norm,
                       "status": "candidates" if candidates else "unmatched",
                       "candidates": candidates})
    counts = {status: sum(r["status"] == status for r in result)
              for status in ("exact", "alias", "candidates", "unmatched")}
    return {"schemaVersion": 1, "totalDtekStreets": len(dtek_names),
            "totalOsmStreetNames": len(osm), "counts": counts, "streets": result}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dtek", required=True, help="Path to JSON DTEK street export")
    parser.add_argument("--city", help="Exact source city key when DTEK JSON has city->streets")
    parser.add_argument("--osm", default="data/roads.geojson")
    parser.add_argument("--aliases", help="Optional reviewed JSON map: DTEK street -> OSM street")
    parser.add_argument("--output", help="Write JSON report to this file (default stdout)")
    args = parser.parse_args(argv)
    try:
        raw = json.loads(Path(args.dtek).read_text(encoding="utf-8"))
        streets = load_dtek_streets(raw, args.city)
        features = json.loads(Path(args.osm).read_text(encoding="utf-8"))["features"]
        aliases = json.loads(Path(args.aliases).read_text(encoding="utf-8")) if args.aliases else {}
        if not isinstance(aliases, dict):
            raise ValueError("Aliases must be an object")
        report = compare_streets(streets, features, aliases)
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        print("DTEK comparison failed: " + str(exc), file=sys.stderr)
        return 1
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
