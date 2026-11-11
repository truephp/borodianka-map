#!/usr/bin/env python3
"""Fetch the public regional GPV schedule directly from the DTEK KREM page.

Does not collect house addresses and does not encrypt the public schedule.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from playwright.async_api import async_playwright

from fetch_dtek_shared_houses import PAGE_URL, BASE_URL, parse_schedule_fact


async def capture(output):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page(locale="uk-UA", timezone_id="Europe/Kyiv")
            response = await page.goto(PAGE_URL, wait_until="domcontentloaded", timeout=60000)
            if not response or response.status != 200:
                raise RuntimeError(f"DTEK schedule page HTTP {response.status if response else 'no response'}")
            schedule = None
            for _ in range(12):
                schedule = await page.evaluate("""() => {
                    try {
                        const app = typeof DisconSchedule !== 'undefined' ? DisconSchedule : window.DisconSchedule;
                        const fact = app?.fact || window.fact || null;
                        if(fact && typeof fact.data === 'object')
                            return {data:fact.data,today:fact.today || null,update:fact.update || null};
                    }catch(e){}
                    return null;
                }""")
                if isinstance(schedule, dict) and isinstance(schedule.get("data"), dict) and schedule["data"]:
                    break
                schedule = parse_schedule_fact(await page.content())
                if schedule:
                    break
                await page.wait_for_timeout(1000)
            if not schedule:
                raise RuntimeError("DTEK page returned HTTP 200 but no valid fact.data was found in JavaScript or HTML")
            captured = {"source":BASE_URL,"fetchedAt":datetime.now(timezone.utc).isoformat(),
                        "scheduleFact":schedule}
            Path(output).write_text(json.dumps(captured, ensure_ascii=False), encoding="utf-8")
            print(f"Captured DTEK fact: {len(schedule['data'])} dates, published {schedule.get('update')}", flush=True)
        finally:
            await browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    asyncio.run(capture(args.output))


if __name__ == "__main__":
    main()
