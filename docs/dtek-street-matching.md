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
