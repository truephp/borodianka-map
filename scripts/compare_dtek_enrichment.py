#!/usr/bin/env python3
"""Compare encrypted DTEK matching artifacts before and after Visicom metadata enrichment.

Print only aggregate counts; decrypted address-level data never leave memory.
"""
from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import zipfile

from merge_buildings import decrypt

REPO = "truephp/borodianka-map"
WORKFLOW = "dtek-all-addresses.yml"
PIVOT = datetime.fromisoformat("2026-11-05T08:38:16+00:00")
ARTIFACT = "dtek-borodianka-full-address-audit"
REPORT = "dtek-all-unified-matches.enc.json"


def api(path):
    token = os.environ["GITHUB_TOKEN"]
    request = Request("https://api.github.com" + path, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "borodianka-dtek-audit",
    })
    with urlopen(request, timeout=40) as response:
        return json.load(response)


def runs():
    result = []
    for page in range(1, 6):
        response = api(f"/repos/{REPO}/actions/workflows/{WORKFLOW}/runs?" +
                       urlencode({"status": "success", "branch": "main", "per_page": 100, "page": page}))
        batch = response.get("workflow_runs", [])
        result.extend(batch)
        if len(batch) < 100:
            break
    return result


def downloadable_run(run):
    response = api(f"/repos/{REPO}/actions/runs/{run['id']}/artifacts?per_page=100")
    for artifact in response.get("artifacts", []):
        if artifact["name"] == ARTIFACT and not artifact.get("expired"):
            return artifact["id"]
    return None


def read_report(artifact_id):
    token = os.environ["GITHUB_TOKEN"]
    request = Request(
        f"https://api.github.com/repos/{REPO}/actions/artifacts/{artifact_id}/zip",
        headers={"Authorization": "Bearer " + token, "User-Agent": "borodianka-dtek-audit"},
    )
    with urlopen(request, timeout=90) as response:
        raw = response.read()
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        matching = [name for name in archive.namelist() if name.endswith(REPORT)]
        if len(matching) != 1:
            raise ValueError("Artifact does not contain exactly one encrypted unified report")
        envelope = json.loads(archive.read(matching[0]))
    return decrypt(envelope, os.environ["VISICOM_EXPORT_PASSWORD"])


def select_pair():
    all_runs = runs()
    before = sorted((r for r in all_runs
                     if datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) < PIVOT),
                    key=lambda r: r["created_at"], reverse=True)
    after = sorted((r for r in all_runs
                    if datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) > PIVOT),
                   key=lambda r: r["created_at"], reverse=True)
    for candidates, label in ((before, "before"), (after, "after")):
        print(f"{label}: {len(candidates)} successful runs in search window")
    def pick(candidates):
        for run in candidates:
            artifact = downloadable_run(run)
            if artifact:
                try:
                    report = read_report(artifact)
                except (ValueError, zipfile.BadZipFile):
                    continue
                return run, report
        raise ValueError("No downloadable encrypted unified DTEK report in selected period")
    return pick(before), pick(after)


def index(report):
    return {(r["city"], r["street"], str(r["house"])): r
            for r in report.get("records", []) if "house" in r}


def main():
    (old_run, old), (new_run, new) = select_pair()
    old_records, new_records = index(old), index(new)
    matched_keys = set(old_records) & set(new_records)
    old_counts = Counter(x["status"] for x in old_records.values())
    new_counts = Counter(x["status"] for x in new_records.values())
    transition = Counter((old_records[k]["status"], new_records[k]["status"]) for k in matched_keys)
    columns = ("exact", "multiple", "candidate_street_type",
               "candidate_house_format", "candidate_street_and_house_format", "unmatched")
    lines = [
        "## ДТЕК: порівняння до / після збагачення Visicom",
        f"До: [run {old_run['id']}](https://github.com/{REPO}/actions/runs/{old_run['id']}) "
        f"({old.get('sourceFetchedAt') or 'невідомо'})",
        f"Після: [run {new_run['id']}](https://github.com/{REPO}/actions/runs/{new_run['id']}) "
        f"({new.get('sourceFetchedAt') or 'невідомо'})",
        f"Спільних адрес: {len(matched_keys)}; лише до: {len(set(old_records)-set(new_records))}; "
        f"лише після: {len(set(new_records)-set(old_records))}",
        "",
        "| Статус | До | Після | Різниця |",
        "|---|---:|---:|---:|",
    ]
    for key in columns:
        lines.append(f"| {key} | {old_counts[key]} | {new_counts[key]} | {new_counts[key]-old_counts[key]:+d} |")
    lines.extend(["", "### Зміни статусів на спільних адресах",
                  "| Перехід | Кількість |", "|---|---:|"])
    for (status_from, status_to), count in sorted(transition.items(), key=lambda item: -item[1]):
        if status_from != status_to:
            lines.append(f"| {status_from} → {status_to} | {count} |")
    for street_word in ("грушевського", "українки", "здив", "здвиж", "млинова"):
        relevant = [k for k in matched_keys if street_word in k[1].casefold()]
        if relevant:
            old_local = Counter(old_records[k]["status"] for k in relevant)
            new_local = Counter(new_records[k]["status"] for k in relevant)
            lines.append(f"**{street_word}**: {len(relevant)} спільних адрес, "
                         f"exact {old_local['exact']} → {new_local['exact']}; "
                         f"candidate_street_type {old_local['candidate_street_type']} → {new_local['candidate_street_type']}")
    result = "\n".join(lines) + "\n"
    print(result)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(result)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Do not print secrets, decrypted records or tokenized request URLs.
        print(f"Comparison unavailable: {type(exc).__name__}: {str(exc)[:180]}", file=sys.stderr)
        raise SystemExit(1)
