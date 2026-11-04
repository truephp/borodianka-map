#!/usr/bin/env python3
"""One-session, 14-request DTEK KREM house-directory diagnostic.

Reads the two user-supplied city keys and seven exact shared street strings.
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


async def main_async(directory, output, update_fact, delay_seconds):
    streets = shared_streets(directory)
    result = {"source": BASE_URL, "fetchedAt": datetime.now(timezone.utc).isoformat(),
              "cities": list(CITIES), "streetNames": streets, "responses": []}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page(locale="uk-UA", timezone_id="Europe/Kyiv")
            navigation = await page.goto(PAGE_URL, wait_until="domcontentloaded", timeout=60000)
            print(f"Source page HTTP: {navigation.status if navigation else 'none'}", file=sys.stderr)
            metadata = await page.evaluate("""() => {
                const meta = document.querySelector('meta[name="csrf-token"]');
                const csrfName = document.querySelector('meta[name="csrf-param"]');
                const fact = window.DisconSchedule?.fact?.update || null;
                const html = document.documentElement.outerHTML;
                const fallbackFact = html.match(/"updateFact"\\s*:\\s*"([^"]+)"/);
                return {
                    csrfToken: meta?.content || null,
                    csrfName: csrfName?.content || '_csrf',
                    updateFact: fact || fallbackFact?.[1] || null,
                };
            }""")
            fact = metadata["updateFact"] or update_fact
            if not fact:
                raise RuntimeError("Missing updateFact: provide current DTEK value using --update-fact")
            if not metadata["csrfToken"]:
                raise RuntimeError("DTEK did not provide a csrf-token meta tag; cannot POST safely")
            print("DTEK page provided CSRF token; using page session for 14 queries", file=sys.stderr)
            for street in streets:
                for city in CITIES:
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
                        # Do not publish outage status details in diagnostic artifacts.
                        clean = {"result": True, "data": {key: None for key in keys}}
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
    args = parser.parse_args()
    if args.delay_seconds < 1:
        parser.error("--delay-seconds must be at least 1")
    directory = json.loads(Path(args.directory).read_text(encoding="utf-8"))
    code = asyncio.run(main_async(directory, args.output, args.update_fact, args.delay_seconds))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
