#!/usr/bin/env python3
"""Compare house-number lists of DTEK streets shared by two settlement keys.

Input: a JSON file with a top-level `responses` array; each item has `city`,
`street`, and `response` (the original getHomeNum response) or `error`.
No missing/failed response is ever interpreted as an empty list.
"""
import argparse
import json
from pathlib import Path
import re
import sys

CITIES = ("с-ще Бородянка", "смт Бородянка")


def shared_streets(directory):
    streets = directory["streets"]
    return sorted(set(streets[CITIES[0]]) & set(streets[CITIES[1]]))


def house_key(value):
    # Keep suffixes and building subdivisions distinct; whitespace/case are safe.
    return re.sub(r"\s+", "", str(value)).casefold().replace("’", "'").replace("ʼ", "'")


def extract_houses(response):
    if not isinstance(response, dict) or response.get("result") is not True:
        raise ValueError("getHomeNum response is not successful")
    data = response.get("data")
    if isinstance(data, dict):
        values = list(data.keys())
    elif isinstance(data, list):
        values = data
    else:
        raise ValueError("getHomeNum 'data' must be an object or array")
    if not all(isinstance(value, str) for value in values):
        raise ValueError("House numbers are not all strings")
    return {house_key(house): house.strip() for house in values if house.strip()}


def compare(directory, records):
    shared = shared_streets(directory)
    found = {}
    for item in records:
        city, street = item.get("city"), item.get("street")
        if city not in CITIES or street not in shared:
            raise ValueError(f"Unexpected city/street: {city!r} / {street!r}")
        key = (city, street)
        if key in found:
            raise ValueError(f"Duplicate city/street: {key!r}")
        found[key] = item
    out = []
    for street in shared:
        a, b = [found.get((city, street)) for city in CITIES]
        row = {"street": street, "cities": list(CITIES)}
        errors = []
        results = []
        for city, entry in zip(CITIES, (a, b)):
            try:
                if entry is None:
                    raise ValueError("No response received")
                if entry.get("error"):
                    raise ValueError(str(entry["error"]))
                results.append(extract_houses(entry["response"]))
            except (ValueError, KeyError, TypeError) as exc:
                errors.append({"city": city, "error": str(exc)})
        if errors:
            row.update(status="error", errors=errors)
        else:
            left, right = results
            both = left.keys() & right.keys()
            only_left, only_right = left.keys() - right.keys(), right.keys() - left.keys()
            row.update(
                status="compared",
                counts={"first": len(left), "second": len(right),
                        "shared": len(both), "onlyFirst": len(only_left),
                        "onlySecond": len(only_right)},
                houseNumbers={
                    "shared": sorted(left[x] for x in both),
                    "onlyFirst": sorted(left[x] for x in only_left),
                    "onlySecond": sorted(right[x] for x in only_right),
                },
            )
        out.append(row)
    return {"schemaVersion": 1, "cityKeys": list(CITIES),
            "totalSharedStreets": len(shared),
            "compared": sum(r["status"] == "compared" for r in out),
            "failed": sum(r["status"] == "error" for r in out),
            "streets": out}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default="data/dtek-borodianka-streets.json")
    parser.add_argument("--responses", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        directory = json.loads(Path(args.directory).read_text(encoding="utf-8"))
        responses = json.loads(Path(args.responses).read_text(encoding="utf-8"))
        report = compare(directory, responses["responses"])
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        print(f"Comparison failed: {exc}", file=sys.stderr)
        return 1
    for row in report["streets"]:
        if row["status"] == "compared":
            n = row["counts"]
            print(f"{row['street']}: {n['first']} / {n['second']}; "
                  f"common={n['shared']}, only-first={n['onlyFirst']}, only-second={n['onlySecond']}")
        else:
            print(f"{row['street']}: ERROR {row['errors']}")
    return 0 if not report["failed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
