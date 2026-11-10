#!/usr/bin/env python3
"""Normalize published Kyiv region DTEK group schedules into a safe public snapshot.

Source is a public secondary mirror of DTEK's schedule. Fail closed: missing,
incomplete or outdated days must never be interpreted as power ON.
"""
import argparse
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import json
from pathlib import Path
from urllib.request import Request, urlopen

MIRROR = "https://raw.githubusercontent.com/Baskerville42/outage-data-ua/main/data/kyiv-region.json"
VALID = {"yes", "no", "first", "second", "maybe", "mfirst", "msecond"}
KYIV = ZoneInfo("Europe/Kyiv")


def normalize(source, now=None):
    now = now or datetime.now(timezone.utc)
    if source.get("regionId") != "kyiv-region":
        raise ValueError("Wrong regional schedule")
    stamp = datetime.fromisoformat(str(source["lastUpdated"]).replace("Z", "+00:00"))
    if not stamp.tzinfo or stamp > now + timedelta(minutes=15):
        raise ValueError("Invalid schedule timestamp")
    if now - stamp > timedelta(hours=12):
        raise ValueError("Schedule source is stale (over 12 hours)")
    if source.get("lastUpdateStatus", {}).get("ok") is not True:
        raise ValueError("Schedule source marked as unsuccessful")
    fact = source.get("fact", {})
    if not isinstance(fact.get("data"), dict):
        raise ValueError("Missing schedule data")
    days = {}
    for key, groups in fact["data"].items():
        try:
            date = datetime.fromtimestamp(int(key), timezone.utc).astimezone(KYIV).date().isoformat()
        except (ValueError, OverflowError):
            continue
        if not isinstance(groups, dict):
            continue
        normalized = {}
        for group, hours in groups.items():
            if not (isinstance(group, str) and group.startswith("GPV") and isinstance(hours, dict)):
                continue
            values = [hours.get(str(index)) for index in range(1, 25)]
            if len(values) != 24 or any(v not in VALID for v in values):
                continue
            normalized[group] = values
        if normalized:
            days[date] = normalized
    today = now.astimezone(KYIV).date()
    if not any(abs((datetime.fromisoformat(day).date() - today).days) <= 1 for day in days):
        raise ValueError("No schedule for today/tomorrow")
    if not days:
        raise ValueError("No complete group schedules")
    return {
        "schemaVersion": 1, "region": "kyiv-region",
        "source": MIRROR,
        "sourceUpdatedAt": source["lastUpdated"],
        "dtekPublishedAt": fact.get("update"),
        "fetchedAt": now.isoformat(),
        "timezone": "Europe/Kyiv", "days": days,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument("--input", help="Optional fixture for tests")
    args = ap.parse_args()
    if args.input:
        source = json.loads(Path(args.input).read_text(encoding="utf-8"))
    else:
        req = Request(MIRROR, headers={"User-Agent": "borodianka-map/1.0",
                                       "Accept": "application/json"})
        with urlopen(req, timeout=40) as response:
            source = json.load(response)
    normalized = normalize(source)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(normalized, ensure_ascii=False, separators=(",", ":")) + "\n",
                      encoding="utf-8")
    print(f"Published schedule dates: {list(normalized['days'])}, groups: " +
          ", ".join(f"{day}={len(groups)}" for day, groups in normalized["days"].items()), flush=True)


if __name__ == "__main__":
    main()
