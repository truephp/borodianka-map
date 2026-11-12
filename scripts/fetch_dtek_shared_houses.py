#!/usr/bin/env python3
"""One-session DTEK KREM house-directory diagnostic (shared or complete directory).

Reads the two user-supplied city keys and optionally all listed street strings.
Uses same-origin POST /ua/ajax with DTEK's standard getHomeNum method and the
current page's cookies/CSRF. No credential bypass or proxy rotation. Failed streets get limited retries.
Failures are explicit records, not silently empty house-number lists.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

from playwright.async_api import async_playwright
from compare_dtek_shared_houses import CITIES, shared_streets

def parse_schedule_fact(html):
    """Parse an inline JSON `fact = {...}` declaration from the first-party page.

    JSONDecoder.raw_decode stops at the complete object and avoids greedy regex
    matches across unrelated script tags. Do not execute any inline JavaScript.
    """
    decoder = json.JSONDecoder()
    for found in re.finditer(r"(?:\b|\.)fact\s*=\s*(?=\{)", html):
        try:
            data, _ = decoder.raw_decode(html[found.end():])
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            return {"data": data["data"], "today": data.get("today"), "update": data.get("update")}
    return None


async def collect_pairs(pairs, fetch_pair, delay_seconds=1.5, workers=2):
    """Bounded per-worker pacing, preserving original street ordering."""
    if not 1 <= workers <= 4:
        raise ValueError("workers must be 1..4")
    if delay_seconds < 1:
        raise ValueError("delay_seconds must be at least 1")
    queue = asyncio.Queue()
    for index, pair in enumerate(pairs):
        queue.put_nowait((index, pair))
    results = [None] * len(pairs)

    async def worker():
        while True:
            try:
                index, (city, street) = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                for attempt in range(3):
                    try:
                        results[index] = await fetch_pair(city, street)
                        break
                    except Exception as exc:
                        if attempt < 2:
                            print(f"RETRY {attempt + 1}/2 {city} / {street}: "
                                  f"{type(exc).__name__}: {exc}", file=sys.stderr)
                            await asyncio.sleep(1.8 * (attempt + 1))
                        else:
                            results[index] = {"city": city, "street": street,
                                              "error": str(exc)[:160]}
                            print(f"FAILED {city} / {street}: "
                                  f"{type(exc).__name__}: {exc}", file=sys.stderr)
            finally:
                queue.task_done()
                await asyncio.sleep(delay_seconds)

    await asyncio.gather(*(worker() for _ in range(min(workers, len(pairs)))))
    if any(item is None for item in results):
        raise RuntimeError("Incomplete concurrent DTEK results")
    return results


BASE_URL = "https://www.dtek-krem.com.ua"
PAGE_URL = BASE_URL + "/ua/shutdowns"


async def main_async(directory, output, update_fact, delay_seconds, all_streets=False, workers=2):
    streets = shared_streets(directory)
    pairs = ([(city, street) for city in CITIES for street in directory['streets'][city] if street != 'Без вулиці']
             if all_streets else [(city, street) for street in streets for city in CITIES])
    result = {"source": BASE_URL, "fetchedAt": datetime.now(timezone.utc).isoformat(),
              "cities": list(CITIES), "streetNames": streets, "scope": "all" if all_streets else "shared", "responses": []}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page(locale="uk-UA", timezone_id="Europe/Kyiv")
            navigation = await page.goto(PAGE_URL, wait_until="domcontentloaded", timeout=60000)
            print(f"Source page HTTP: {navigation.status if navigation else 'none'}", file=sys.stderr)
            # Some DTEK responses initialize metadata after DOMContentLoaded.
            # Retry only the ordinary public page load; do not issue AJAX without CSRF.
            for attempt in range(3):
                try:
                    await page.locator('meta[name="csrf-token"]').wait_for(
                        state="attached", timeout=10000
                    )
                    break
                except Exception:
                    diagnostic = await page.evaluate("""() => ({
                        title: document.title,
                        url: location.href,
                        csrfMetaNames: [...document.querySelectorAll('meta[name*="csrf"]')].map(x => x.name),
                        hasAddressInput: !!document.querySelector('input'),
                        bodyLength: document.body?.innerText?.length || 0
                    })""")
                    print(f"DTEK page metadata attempt {attempt + 1}/3: {diagnostic}", file=sys.stderr)
                    if attempt < 2:
                        await page.wait_for_timeout(2000)
                        navigation = await page.reload(wait_until="domcontentloaded", timeout=60000)
                        print(f"DTEK reload HTTP: {navigation.status if navigation else 'none'}", file=sys.stderr)
            # The site may set the schedule after DOMContentLoaded/CSRF injection.
            # Keep address collection functional even if the schedule is absent,
            # but let the schedule validator fail closed.
            try:
                await page.wait_for_function(
                    "() => { const app = typeof DisconSchedule !== 'undefined' ? DisconSchedule : window.DisconSchedule; const schedule = app?.fact || (typeof fact !== 'undefined' ? fact : window.fact); return !!(schedule?.data && Object.keys(schedule.data).length); }",
                    timeout=15000,
                )
            except Exception:
                print("DTEK fact.data was not initialized in 15 seconds", file=sys.stderr)
            metadata = await page.evaluate("""() => {
                const meta = document.querySelector('meta[name="csrf-token"]');
                const csrfName = document.querySelector('meta[name="csrf-param"]');
                // DisconSchedule is a top-level lexical variable on DTEK's site,
                // not necessarily a property of window.
                const app = typeof DisconSchedule !== 'undefined'
                    ? DisconSchedule : window.DisconSchedule;
                const schedule = app?.fact ||
                    (typeof fact !== 'undefined' ? fact : window.fact) || null;
                const publishedUpdate = app?.preset?.updateFact ||
                    schedule?.update || null;
                const html = document.documentElement.outerHTML;
                const fallbackFact = html.match(/"updateFact"\\s*:\\s*"([^"]+)"/);
                return {
                    csrfToken: meta?.content || null,
                    csrfName: csrfName?.content || '_csrf',
                    updateFact: publishedUpdate || fallbackFact?.[1] || null,
                    // Read the public schedule from the SAME DTEK page/session
                    // used to fetch addresses. No external mirror.
                    schedule: schedule && typeof schedule === 'object'
                        ? {data: schedule.data || null, today: schedule.today || null,
                           update: schedule.update || null}
                        : null,
                };
            }""")
            schedule_fact = metadata.get("schedule")
            if not isinstance(schedule_fact, dict) or not isinstance(schedule_fact.get("data"), dict):
                schedule_fact = parse_schedule_fact(await page.content())
                if schedule_fact:
                    print("DTEK first-party schedule extracted from inline fact JSON", file=sys.stderr)
            if isinstance(schedule_fact, dict) and isinstance(schedule_fact.get("data"), dict):
                print(f"DTEK fact captured: {len(schedule_fact['data'])} days, updated {schedule_fact.get('update')}", file=sys.stderr)
            result["scheduleFact"] = schedule_fact
            fact = metadata["updateFact"] or update_fact
            if not fact:
                raise RuntimeError("Missing updateFact: provide current DTEK value using --update-fact")
            if not metadata["csrfToken"]:
                raise RuntimeError("DTEK did not provide a csrf-token meta tag; cannot POST safely")
            print(f"DTEK CSRF present; requesting {len(pairs)} city/street pairs", file=sys.stderr)
            async def request_pair(city, street):
                response = await page.evaluate("""async ({city, street, fact, csrfToken, csrfName}) => {
                    const body = new URLSearchParams();
                    body.set('method', 'getHomeNum');
                    body.set('data[0][name]', 'city');
                    body.set('data[0][value]', city);
                    body.set('data[1][name]', 'street');
                    body.set('data[1][value]', street);
                    body.set('data[2][name]', 'updateFact');
                    body.set('data[2][value]', fact);
                    body.set(csrfName, csrfToken);
                    const r = await fetch('/ua/ajax', {
                        method: 'POST',
                        headers: {
                            'X-CSRF-Token': csrfToken,
                            'X-Requested-With': 'XMLHttpRequest',
                            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                            'Accept': 'application/json'
                        },
                        credentials: 'same-origin',
                        body
                    });
                    const text = await r.text();
                    if (!r.ok) throw Error('HTTP ' + r.status);
                    try { return JSON.parse(text); }
                    catch { throw Error('Non-JSON AJAX response'); }
                }""", {"city": city, "street": street, "fact": fact,
                       "csrfToken": metadata["csrfToken"], "csrfName": metadata["csrfName"]})
                if response.get("result") is not True:
                    raise RuntimeError("getHomeNum returned result != true; " +
                                   str(response.get("message") or response.get("error") or "no explanation")[:100])
                data = response.get("data")
                if not isinstance(data, (dict, list)):
                    raise RuntimeError("getHomeNum returned unexpected data shape")
                keys = list(data.keys()) if isinstance(data, dict) else data
                if not all(isinstance(k, str) for k in keys):
                    raise RuntimeError("House number list has non-string entries")
                # Retain the original seven DTEK per-house outage fields.
                # The complete source and matching reports stay in Actions;
                # only the final AES-GCM encrypted report is served by Pages.
                fields = ("cek", "start_date", "end_date", "sub_type",
                          "sub_type_reason", "type", "voluntarily")
                if isinstance(data, dict):
                    clean_data = {
                        house: {field: value[field] for field in fields if field in value}
                        if isinstance(value, dict) else {}
                        for house, value in data.items()
                    }
                else:
                    clean_data = {house: {} for house in keys}
                clean = {"result": True, "data": clean_data}
                print(f"{city} / {street}: {len(keys)} house numbers", file=sys.stderr)
                return {"city": city, "street": street, "response": clean}
            result["responses"] = await collect_pairs(
                pairs, request_pair, delay_seconds=delay_seconds, workers=workers
            )
            errors = sum("error" in item for item in result["responses"])
            print(f"DTEK street capture: {len(pairs)-errors}/{len(pairs)} successful, "
                  f"{errors} errors, {workers} workers", file=sys.stderr)
        finally:
            await browser.close()
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if all("response" in item for item in result["responses"]) else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default="data/dtek-borodianka-streets.json")
    parser.add_argument("--output", required=True)
    parser.add_argument("--update-fact", default="", help="Actual DTEK updateFact from page, when not embedded")
    parser.add_argument("--delay-seconds", type=float, default=1.3)
    parser.add_argument("--all-streets", action="store_true", help="Query both complete street directories (except Без вулиці)")
    parser.add_argument("--workers", type=int, default=2, help="Concurrent paced requests (1..4)")
    args = parser.parse_args()
    if args.delay_seconds < 1:
        parser.error("--delay-seconds must be at least 1")
    if not 1 <= args.workers <= 4:
        parser.error("--workers must be 1..4")
    directory = json.loads(Path(args.directory).read_text(encoding="utf-8"))
    code = asyncio.run(main_async(directory, args.output, args.update_fact, args.delay_seconds, args.all_streets, args.workers))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
