#!/usr/bin/env python3
"""One-session DTEK KREM house-directory diagnostic (shared or complete directory).

Reads the two user-supplied city keys and optionally all listed street strings.
Uses same-origin POST /ua/ajax with DTEK's standard getHomeNum method and the
current page's cookies/CSRF. No credential bypass, retries, or proxy rotation.
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

BASE_URL = "https://www.dtek-krem.com.ua"
PAGE_URL = BASE_URL + "/ua/shutdowns"


async def main_async(directory, output, update_fact, delay_seconds, all_streets=False):
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
                    "() => !!(window.DisconSchedule?.fact?.data && Object.keys(window.DisconSchedule.fact.data).length)",
                    timeout=15000,
                )
            except Exception:
                print("DTEK fact.data was not initialized in 15 seconds", file=sys.stderr)
            metadata = await page.evaluate("""() => {
                const meta = document.querySelector('meta[name="csrf-token"]');
                const csrfName = document.querySelector('meta[name="csrf-param"]');
                const fact = window.DisconSchedule?.fact?.update || null;
                const html = document.documentElement.outerHTML;
                const fallbackFact = html.match(/"updateFact"\\s*:\\s*"([^"]+)"/);
                const schedule = window.DisconSchedule?.fact || null;
                return {
                    csrfToken: meta?.content || null,
                    csrfName: csrfName?.content || '_csrf',
                    updateFact: fact || fallbackFact?.[1] || null,
                    // Read the public schedule from the SAME DTEK page/session
                    // used to fetch addresses. No external mirror.
                    schedule: schedule && typeof schedule === 'object'
                        ? {data: schedule.data || null, today: schedule.today || null,
                           update: schedule.update || null}
                        : null,
                };
            }""")
            result["scheduleFact"] = metadata.get("schedule")
            fact = metadata["updateFact"] or update_fact
            if not fact:
                raise RuntimeError("Missing updateFact: provide current DTEK value using --update-fact")
            if not metadata["csrfToken"]:
                raise RuntimeError("DTEK did not provide a csrf-token meta tag; cannot POST safely")
            print(f"DTEK CSRF present; requesting {len(pairs)} city/street pairs", file=sys.stderr)
            for city, street in pairs:
                    try:
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
                            raise RuntimeError("getHomeNum returned result != true")
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
                        result["responses"].append({"city": city, "street": street, "response": clean})
                        print(f"{city} / {street}: {len(keys)} house numbers", file=sys.stderr)
                    except Exception as exc:
                        result["responses"].append({"city": city, "street": street,
                                                    "error": str(exc)[:160]})
                        print(f"FAILED {city} / {street}: {type(exc).__name__}: {exc}", file=sys.stderr)
                    await page.wait_for_timeout(round(delay_seconds * 1000))
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
    args = parser.parse_args()
    if args.delay_seconds < 1:
        parser.error("--delay-seconds must be at least 1")
    directory = json.loads(Path(args.directory).read_text(encoding="utf-8"))
    code = asyncio.run(main_async(directory, args.output, args.update_fact, args.delay_seconds, args.all_streets))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
