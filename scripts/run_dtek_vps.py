#!/usr/bin/env python3
"""Run the existing first-party DTEK collector and atomically publish public JSON.

No Visicom geometry, private matching decisions, R2 credentials or database.
Schedule and house data publish independently; an unsuccessful capture does not
overwrite the last valid JSON. systemd handles locking and periodic execution.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory, NamedTemporaryFile

from fetch_dtek_gpv_schedule import normalize
from build_dtek_status_snapshot import assemble

SCHEMA_VERSION = 1
MAX_STREET_ERRORS = 2
MIN_COVERAGE = 0.95


def atomic_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                            prefix=".dtek-", suffix=".tmp", delete=False) as fp:
        temp_path = Path(fp.name)
        try:
            json.dump(obj, fp, ensure_ascii=False, separators=(",", ":"))
            fp.write("\n")
            fp.flush()
            os.fsync(fp.fileno())
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise
    try:
        os.chmod(temp_path, 0o644)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def publish_capture(capture, output_dir, *, now=None):
    """Publish each valid dataset independently and return per-dataset results."""
    output_dir = Path(output_dir)
    results = {}
    try:
        schedule = normalize(capture, now=now)
        atomic_json(output_dir / "schedule.json", schedule)
        results["schedule"] = {"ok": True, "fetchedAt": schedule["sourceUpdatedAt"],
                               "publishedAt": schedule["dtekPublishedAt"],
                               "days": list(schedule["days"])}
    except (ValueError, KeyError, TypeError, OverflowError) as error:
        results["schedule"] = {"ok": False, "error": str(error)[:200]}

    try:
        houses = assemble(capture)
        total, successful = houses["streetPairs"], houses["successfulPairs"]
        if not total or (total - successful) > MAX_STREET_ERRORS or successful / total < MIN_COVERAGE:
            raise ValueError(f"Street coverage insufficient: {successful}/{total}")
        atomic_json(output_dir / "houses.json", houses)
        results["houses"] = {"ok": True, "fetchedAt": houses["fetchedAt"],
                             "complete": houses["complete"],
                             "streetPairs": total, "successfulPairs": successful,
                             "addressCount": len(houses["addresses"]),
                             "errors": houses["errors"]}
    except (ValueError, KeyError, TypeError, ZeroDivisionError) as error:
        results["houses"] = {"ok": False, "error": str(error)[:200]}
    return results


def run(output_dir, *, collector=None, directory=None, workers=2, delay=1.5, timeout=600):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    collector = collector or Path(__file__).with_name("fetch_dtek_shared_houses.py")
    directory = directory or Path(__file__).resolve().parents[1] / "data/dtek-borodianka-streets.json"
    attempted = datetime.now(timezone.utc).isoformat()
    report = {"schemaVersion": SCHEMA_VERSION,
              "region": "kyiv-region", "lastAttemptAt": attempted}
    with TemporaryDirectory(prefix="dtek-capture-") as work:
        capture_path = Path(work) / "capture.json"
        cmd = [sys.executable, str(collector), "--directory", str(directory),
               "--all-streets", "--workers", str(workers), "--delay-seconds", str(delay),
               "--output", str(capture_path)]
        try:
            proc = subprocess.run(cmd, timeout=timeout, check=False)
            report["collectorExitCode"] = proc.returncode
        except subprocess.TimeoutExpired:
            report["collectorExitCode"] = -1
            report["collectorError"] = "Collector timed out"
        if capture_path.is_file():
            try:
                capture = json.loads(capture_path.read_text(encoding="utf-8"))
                report.update(publish_capture(capture, output_dir))
            except (ValueError, KeyError, TypeError) as error:
                report["collectorError"] = f"Invalid capture: {error}"[:200]
        else:
            report.setdefault("collectorError", "No DTEK capture file produced")

    # Status is never a claim that the previous data is fresh; consumers
    # inspect schedule.json/houses.json fetchedAt separately.
    report["ok"] = bool(report.get("schedule", {}).get("ok") and
                        report.get("houses", {}).get("ok"))
    atomic_json(output_dir / "status.json", report)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report["ok"] else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--delay-seconds", type=float, default=1.5)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4 or args.delay_seconds < 1 or args.timeout < 60:
        parser.error("workers must be 1..4, delay >=1, timeout >=60")
    raise SystemExit(run(args.output_dir, workers=args.workers,
                         delay=args.delay_seconds, timeout=args.timeout))


if __name__ == "__main__":
    main()
