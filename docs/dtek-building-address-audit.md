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
- **Current matcher (schemaVersion 2):** a Visicom address without a street
  type is eligible for an **exact** match when normalized street name and
  conservative house number are equal, exactly one physical contour matches,
  and no explicit conflicting street/lane type is present in OSM road names,
  either DTEK street directory, or typed building addresses. A missing street
  type alone is **not** a conflict.
- Explicitly different street types (street versus lane), competing names,
  multiple matching contours, and spelling-only matches remain subject to
  review. Ambiguous matches are not promoted automatically. Uncertain
  Cyrillic/Latin letter or slash variations remain review-only.

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

## Full two-directory pilot (4 November 2026)

GitHub Actions [run 41908662069](https://github.com/truephp/borodianka-map/actions/runs/41908662069)
completed **successfully**. All **107** queried settlement/street pairs returned
valid responses; the special entry `Без вулиці` was not queried.
There were **2,956 DTEK house-number entries** (records, not necessarily
unique physical buildings). No response failed.

| Match class | Public OSM buildings | Private unified Visicom+OSM buildings |
|---|---:|---:|
| Exactly one strict building match | 61 | 24 |
| Several strict matches (ambiguous) | 13 | 4 |
| Review candidate: house number spelling only | 13 | 5 |
| Review candidate: street type missing or different | 1 | 1,942 |
| Review candidate: both street type and number | 0 | 46 |
| No matching building address | 2,868 | 935 |
| **Total DTEK entries** | **2,956** | **2,956** |

Full private match candidates are stored **only as encrypted JSON** in the
seven-day `dtek-borodianka-full-address-audit` artifact.
Public Actions summaries contain aggregates, not decrypted Visicom addresses.

The unified layer had **2,530 features with address fields**, including
2,477 Visicom and 53 supplemental OSM. This is a **different dataset**
from the public `data/buildings.geojson`, which had 128 OSM features
with both street and house address fields in this diagnostic.

Important: `candidate_street_type` is deliberately **not** a confirmed
link. Visicom often stores a bare street name, without whether it is a
street or lane; `candidate_street_and_house_format` further relaxes
spelling of house suffix/slash. Manual validation must follow before
rendering per-building DTEK statuses. Ambiguous multi-feature matches also
need resolution. The two DTEK city keys remain independent in all records.

## Revised matching after accepting untyped Visicom names — 4 November 2026

Run [41910246449](https://github.com/truephp/borodianka-map/actions/runs/41910246449)
completed successfully against the **same** original complete DTEK artifact
from run 41908662069, without fetching DTEK again. All 11 unit tests passed.

| Match class | Public OSM | Unified Visicom + OSM |
|---|---:|---:|
| One unambiguous exact address match | 62 | **1,837** |
| Several matching outlines (ambiguous) | 13 | 73 |
| House spelling variant, review only | 13 | 50 |
| Street type ambiguous, review only | 0 | 60 |
| Both street type and house spelling uncertain | 0 | 1 |
| Not matched | 2,868 | 935 |
| **Total DTEK records** | **2,956** | **2,956** |

**1,837 / 2,956 = 62.1%** of DTEK *records* have unique strict address
matches in the unified layer. This is not 62.1% of distinct physical
buildings, nor evidence of electricity supply status. There are 184
review-required records (73+50+60+1) and 935 unmatched records.

The algorithm checks all explicit street/lane types for the normalized
name in OSM road features, both independently keyed DTEK settlement
directories, and typed buildings. Example: `Центральна` (Visicom)
can exactly match `вул. Центральна` (DTEK), assuming a unique
house number and no street/lane conflict. `Жиліна` without
a type cannot automatically match `вул. Жиліна` when a
`пров. Жиліна` also exists. When two building outlines share one
address, status remains `multiple` rather than `exact`.

All detailed Visicom-linked results remain encrypted. Counts above are
safe aggregate diagnostics. The main branch and published map have not
been changed.
