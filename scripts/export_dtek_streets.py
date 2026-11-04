#!/usr/bin/env python3
"""Capture the published DTEK KREM street directory through a normal browser session.

One navigation only; no bypass of access controls or repeated probing.
Requires playwright + Chromium. The result contains street names, not outages.
"""
import argparse
import asyncio
import json
from pathlib import Path
import re
import sys

from playwright.async_api import async_playwright

URL = "https://www.dtek-krem.com.ua/ua/shutdowns"


async def capture(url, city_pattern):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page(locale="uk-UA", timezone_id="Europe/Kyiv")
            response = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            print(f"DTEK page HTTP: {response.status if response else 'no response'}", file=sys.stderr)
            # The first-party application may populate DisconSchedule after DOM ready.
            found = None
            for attempt in range(6):
                for frame in page.frames:
                    try:
                        value = await frame.evaluate("""() => {
                            const schedule = window.DisconSchedule;
                            if (!schedule || typeof schedule.streets !== 'object') return null;
                            return schedule.streets;
                        }""")
                        if isinstance(value, dict):
                            found = value
                            break
                    except Exception:
                        continue
                if found is not None:
                    break
                await page.wait_for_timeout(1500)
            if found is None:
                title = await page.title()
                print(f"Diagnostic title: {title!r}", file=sys.stderr)
                for frame in page.frames[:12]:
                    # Only record public URL origins/path and structural indicators;
                    # do not copy cookies, response bodies, or signed query strings.
                    try:
                        diag = await frame.evaluate("""() => ({
                            hasScheduleName: document.documentElement.outerHTML.includes('DisconSchedule'),
                            iframes: [...document.querySelectorAll('iframe')].slice(0, 8).map(e => {
                                try { let u = new URL(e.src, location.href); return u.origin + u.pathname; }
                                catch { return 'invalid iframe URL'; }
                            }),
                            scripts: [...document.scripts].slice(-20).map(e => {
                                if (!e.src) return '(inline)';
                                let u = new URL(e.src); return u.origin + u.pathname;
                            }),
                            hasCityFields: !!document.querySelector('[name*=city], [id*=city], [name*=street], [id*=street]'),
                        })""")
                        from urllib.parse import urlsplit
                        u = urlsplit(frame.url)
                        print("Frame: " + json.dumps({"url": f"{u.scheme}://{u.netloc}{u.path}", **diag}, ensure_ascii=False), file=sys.stderr)
                    except Exception as exc:
                        print(f"Frame diagnostics unavailable: {type(exc).__name__}", file=sys.stderr)
                raise RuntimeError(
                    "DTEK did not expose DisconSchedule.streets to the browser. "
                    f"Page title: {title!r}. Access may be blocked or the site's schema changed."
                )
            matches = [
                key for key in found
                if re.search(city_pattern, key, flags=re.IGNORECASE)
            ]
            print(f"DTEK settlements in directory: {len(found)}", file=sys.stderr)
            print(f"Settlement keys matching {city_pattern!r}: {matches!r}", file=sys.stderr)
            if len(matches) != 1:
                raise RuntimeError(
                    f"Expected one matching settlement, got {len(matches)}. "
                    "Review exact DTEK city names and use a narrower --city-pattern."
                )
            city = matches[0]
            streets = found[city]
            if not isinstance(streets, list) or not all(isinstance(x, str) for x in streets):
                raise RuntimeError("DTEK street directory has an unexpected type")
            return {"source": url, "city": city, "streets": {city: streets}}
        finally:
            await browser.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=URL)
    ap.add_argument("--city-pattern", default="бородян")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    if args.url != URL:
        raise SystemExit("This pilot is restricted to the known DTEK KREM URL")
    result = asyncio.run(capture(args.url, args.city_pattern))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Exported {len(result['streets'][result['city']])} streets for {result['city']!r}", file=sys.stderr)


if __name__ == "__main__":
    main()
