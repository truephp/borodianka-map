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

## First captured Borodianka directory (4 November 2026)

The user supplied the exact DTEK KREM key `с-ще Бородянка` and 81 DTEK street entries, committed in `data/dtek-borodianka-streets.json`. These are source names, not inferred OSM aliases. The offline GitHub Actions comparison run [41905496067](https://github.com/truephp/borodianka-map/actions/runs/41905496067) completed successfully.

Direct normalization comparison against `data/roads.geojson` (304 road segments, 74 distinct normalized names): **57 exact matches, 24 names without an exact match** (70.4% direct coverage). The latter are listed below for alias review; "Без вулиці" is a special source category and must not be treated as a road.

| DTEK street without exact match | Review note |
|---|---|
| Без вулиці | Special category; not a road name |
| вул. Абрикосова | No normalized exact match |
| вул. Базарна | No normalized exact match |
| вул. Яблунева | No normalized exact match |
| вул. Зоряна | No normalized exact match |
| вул. Затишна | No normalized exact match |
| пров. Привокзальний | No normalized exact match |
| вул. Франка | No normalized exact match |
| вул. Довженка | No normalized exact match |
| вул. Ковпака | No normalized exact match |
| вул. Набережна | No normalized exact match |
| вул. Лугова | No normalized exact match |
| вул. Костенко Ліни | Check OSM `вулиця Ліни Костенко`; not automatically approved |
| вул. Київська | No normalized exact match |
| вул. Робітнича | No normalized exact match |
| вул. Лісна | No normalized exact match |
| вул. Хмельницького Богдана | Review name order or historical alias |
| вул. Селекційна | No normalized exact match |
| вул. Чорновола В’ячеслава | Review personal name order |
| вул. Житня | No normalized exact match |
| пров. Здвижовий | No normalized exact match |
| пров. Банний | No normalized exact match |
| пров. Пляжний | No normalized exact match |
| пров. Травневий | No normalized exact match |

Do not assume missing names are wrong: some streets may be outside the OSM road clipping boundary, missing in OSM, renamed, or otherwise represented. Investigate each before approving aliases or matching house numbers.

The headless-browser export of `DisconSchedule.streets` from KREM did not succeed: the site responded HTTP 200 but did not expose that object. The offline matching pipeline now uses the user-supplied verified list and does not depend on scraping the web page. The exploratory `scripts/export_dtek_streets.py` remains available for diagnostics but is not run by the offline workflow.
