# DTEK house addresses vs OSM / private Visicom buildings

This experiment runs **only** in `feature/dtek-address-matching`. It does not
change the production Leaflet map or publish Visicom plaintext.

## Data, code and privacy

- The DTEK street directory has two independently keyed settlements:
  `с-ще Бородянка` (81 street labels, including `Без вулиці`) and
  `смт Бородянка` (27 labels). The key and original house numbers are
  always retained in the DTEK address ID.
- `scripts/fetch_dtek_shared_houses.py` supports `--all-streets`, querying
  all 107 ordinary city/street pairs. This keeps shared streets separate by
  settlement key. It excludes the special label `Без вулиці`.
- `scripts/match_dtek_buildings.py` reads DTEK house-number responses and
  public OSM GeoJSON. Optionally it decrypts R2's unified
  `borodianka/data/borodianka-buildings.enc.json` in the CI runner using the
  existing `VISICOM_EXPORT_PASSWORD` secret. Detailed Visicom matching results
  are encrypted with the same existing AES-GCM envelope before artifact upload.
  No Visicom geometry or plaintext derived links are committed to git.
- House numbers are **not** merged across Cyrillic/Latin or slash variants.
  Uncertain spellings such as `1/А` ↔ `1A` are review-only.
- Exact status requires a matching street **type**, name and conservative
  house number, with a unique building. A Visicom address without road type
  cannot receive automatic exact status. Instead it appears as
  `candidate_street_type`. Similar numbers yield
  `candidate_street_and_house_format`.
- The count of candidate matches is **not** a count of confirmed outage
  addresses. Some streets and lanes share a bare name. Any candidate needs
  review against the building geometry and original address.

## Seven common street labels: first comparison

Actions run [41908393070](https://github.com/truephp/borodianka-map/actions/runs/41908393070)
successfully matched 60 DTEK house-number entries against two layers:

| Match class | Public OSM | Encrypted unified Visicom+OSM |
|---|---:|---:|
| Exact | 1 | 0 |
| Candidate: type omitted or different | 0 | 33 |
| Candidate: type and house spelling | 0 | 3 |
| Unmatched | 59 | 24 |

The unified layer contains 2477 Visicom and 53 supplemental OSM
features with nonempty address fields (2530 total). Its lack of
confirmed matches is explained by missing street **types** in the
Visicom source. Diagnostic counts show that among the 60 DTEK
addresses, 55 have a normalized bare street name in the unified
building index, 33 match street name + conservatively normalized house
number, and 36 match under the looser house-number review normalizer.
None match both the street type and name, so 33 + 3 are **candidates**,
not verified ties.

### Whole-settlement run

[All-address workflow](../.github/workflows/dtek-all-addresses.yml)
fetches the 107 city/street pairs once with a delay of 1.5 seconds per
pair, then builds public OSM and encrypted private unified reports.
Its original DTEK keys, JSON reports, and aggregate summaries are
kept in temporary GitHub Actions artifacts (7 days). A failed request is
recorded as `source_error`, never as an absent street or empty house.

Do not turn on real outage colors based on these diagnostic results:
current data collection only returns house number keys. Live outage
interpretation and address validation remain separate tasks.
