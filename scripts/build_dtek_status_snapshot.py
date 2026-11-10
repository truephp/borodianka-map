#!/usr/bin/env python3
"""Create a timestamped, encrypted DTEK house-status snapshot.

Preserves the seven raw fields without claiming that an empty type means power
is available. Failed street queries remain explicit; a partial capture cannot
replace the last successful public-facing snapshot.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path

FIELDS = ("cek", "start_date", "end_date", "sub_type",
          "sub_type_reason", "type", "voluntarily")


def assemble(capture):
    responses = capture.get("responses")
    if not isinstance(responses, list) or not responses:
        raise ValueError("Missing DTEK street responses")
    items, errors = [], []
    categories = Counter()
    for record in responses:
        city, street = record.get("city"), record.get("street")
        if not isinstance(city, str) or not isinstance(street, str):
            raise ValueError("DTEK record missing city/street")
        if "error" in record or "response" not in record:
            errors.append({"city": city, "street": street, "reason": str(record.get("error", "missing response"))[:160]})
            continue
        payload = record["response"]
        if payload.get("result") is not True or not isinstance(payload.get("data"), dict):
            errors.append({"city": city, "street": street, "reason": "invalid getHomeNum response"})
            continue
        for house, entry in payload["data"].items():
            if not isinstance(entry, dict):
                errors.append({"city": city, "street": street, "reason": "invalid house details"})
                continue
            raw = {field: entry.get(field) for field in FIELDS}
            has_signal = any(raw.get(field) not in (None, "", []) for field in ("type", "sub_type", "sub_type_reason", "start_date", "end_date"))
            categories["has_dtek_signal" if has_signal else "no_reported_outage_signal"] += 1
            items.append({"city": city, "street": street, "house": str(house), "raw": raw,
                          "signal": "reported" if has_signal else "unknown"})
    return {"schemaVersion": 1, "source": capture.get("source"),
            "fetchedAt": capture.get("fetchedAt"),
            "processedAt": datetime.now(timezone.utc).isoformat(),
            "complete": len(errors) == 0,
            "streetPairs": len(responses), "successfulPairs": len(responses) - len(errors),
            "errors": errors, "counts": dict(categories),
            "addresses": items}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()
    payload = assemble(json.loads(Path(args.input).read_text(encoding="utf-8")))
    summary = {k: payload[k] for k in ("schemaVersion", "source", "fetchedAt", "processedAt",
               "complete", "streetPairs", "successfulPairs", "counts")}
    summary["errorCount"] = len(payload["errors"])
    summary["addressCount"] = len(payload["addresses"])
    Path(args.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if not payload["complete"]:
        raise RuntimeError(f"Refusing to publish incomplete DTEK status capture: {len(payload['errors'])} source errors")
    from merge_buildings import encrypt
    password = os.environ.get("VISICOM_EXPORT_PASSWORD")
    if not password:
        raise RuntimeError("Missing VISICOM_EXPORT_PASSWORD")
    Path(args.output).write_text(json.dumps(encrypt(payload, password), ensure_ascii=False), encoding="utf-8")
    print(f"Encrypted {len(payload['addresses'])} DTEK house records; statuses are raw/unclassified", flush=True)


if __name__ == "__main__":
    main()
