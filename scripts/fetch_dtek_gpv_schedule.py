#!/usr/bin/env python3
"""Normalize the public DisconSchedule.fact from the same DTEK KREM capture.

No secondary feeds. Reject missing, malformed, stale or incomplete schedules;
unknown dates cannot be treated as evidence of power availability.
"""
import argparse
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import json
from pathlib import Path

VALID = {"yes", "no", "first", "second", "maybe", "mfirst", "msecond"}
KYIV = ZoneInfo("Europe/Kyiv")


def normalize(capture, now=None):
    now = now or datetime.now(timezone.utc)
    if capture.get("source", "").rstrip("/") != "https://www.dtek-krem.com.ua":
        raise ValueError("Unexpected schedule source")
    stamp = datetime.fromisoformat(str(capture["fetchedAt"]).replace("Z", "+00:00"))
    if stamp.tzinfo is None or stamp > now + timedelta(minutes=15) or now - stamp > timedelta(hours=12):
        raise ValueError("DTEK captured schedule is stale or has an invalid timestamp")
    fact = capture.get("scheduleFact")
    if not isinstance(fact, dict) or not isinstance(fact.get("data"), dict):
        raise ValueError("Missing DisconSchedule.fact.data in first-party DTEK capture")
    days = {}
    for key, groups in fact["data"].items():
        try:
            date = datetime.fromtimestamp(int(key), timezone.utc).astimezone(KYIV).date().isoformat()
        except (ValueError, OverflowError, TypeError):
            continue
        if not isinstance(groups, dict):
            continue
        normalized = {}
        for group, hours in groups.items():
            if not (isinstance(group, str) and group.startswith("GPV")
                    and isinstance(hours, dict)):
                continue
            values = [hours.get(str(index)) for index in range(1, 25)]
            if all(value in VALID for value in values):
                normalized[group] = values
        if normalized:
            days[date] = normalized
    today = now.astimezone(KYIV).date()
    if not any(abs((datetime.fromisoformat(day).date() - today).days) <= 1 for day in days):
        raise ValueError("No valid schedule for the current Kyiv date")
    return {
        "schemaVersion": 1,
        "region": "kyiv-region",
        "source": "https://www.dtek-krem.com.ua/ua/shutdowns",
        "sourceUpdatedAt": capture["fetchedAt"],
        "dtekPublishedAt": fact.get("update"),
        "fetchedAt": now.isoformat(),
        "timezone": "Europe/Kyiv",
        "days": days,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="DTEK address capture containing scheduleFact")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    source = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = normalize(source)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print("Normalized first-party DTEK groups: " +
          ", ".join(f"{day}={len(groups)}" for day, groups in result["days"].items()), flush=True)


if __name__ == "__main__":
    main()
