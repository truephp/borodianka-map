# DTEK Kyiv regional networks — street matching spike

The source parser is **not copied or forked**: `truephp/search-estate/tools/dtek-houses.mjs` already accepts `--base-url` and `--city`.

From a checkout of `search-estate`:

```bash
node tools/dtek-houses.mjs --base-url https://www.dtek-krem.com.ua --city "<exact city name from DTEK streets directory>" "<exact street name>"
```

For Borodianka, use the exact city/street strings returned by the site's directory, **not** an assumed spelling. The script reads `DisconSchedule.streets` from the site and reports similar values when an input is unknown. If the site returns a different response format, inspect the live response before changing parsing behavior.

To compare a **captured DTEK list of streets** against `data/roads.geojson`, store either a JSON array of street-name strings, or a map matching `{"streets":{"<city>":["<street>", ...]}}`, and run:

```bash
python scripts/match_dtek_streets.py --dtek /path/to/dtek-streets.json --city "<exact city key>" --output /tmp/dtek-street-matches.json
```

Omit `--city` for a simple JSON array. Optional `--aliases aliases.json` accepts manually reviewed `{"DTEK name":"OSM name"}` mappings. The output distinguishes exact normalized matches, reviewed aliases, fuzzy candidates, and unmatched street names; fuzzy candidates are **not** automatically approved.

This is an offline diagnostic step. It does not scrape addresses itself, publish statuses, or alter the production map. Keep live request cadence conservative and keep authentication/proxy details outside Git.

## Automated one-time export

The isolated `DTEK KREM — Borodianka street directory pilot` GitHub Actions workflow runs on pushes to `feature/dtek-address-matching` and does not deploy the website. It opens only `https://www.dtek-krem.com.ua/ua/shutdowns` in Chromium, reads the publicly exposed `DisconSchedule.streets` browser object, selects exactly one settlement whose name contains `бородян`, exports its street list, and produces a DTEK/OSM matching JSON report. It uploads both files as a seven-day Actions artifact.

If the DTEK site blocks the browser or changes its JavaScript data structure, the job reports that failure. Do not substitute other settlements or invent street names; browser access and schema compatibility must be verified from an actual run.

The requested street aliases require human review. No addresses or outage statuses are fetched at this stage. No direct DTEK requests from the public Leaflet website are needed.
