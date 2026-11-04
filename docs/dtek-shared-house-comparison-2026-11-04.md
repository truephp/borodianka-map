# DTEK KREM — seven shared Borodianka streets: house-number comparison

Date of collection: **2026-11-04**.
Source: public DTEK KREM `getHomeNum` response for the exact user-supplied
keys `с-ще Бородянка` and `смт Бородянка`.
Successful GitHub Actions run: [41906649117](https://github.com/truephp/borodianka-map/actions/runs/41906649117).
The run artifact `dtek-borodianka-seven-streets` has the original house-number
keys and the generated comparison JSON (7-day retention).

**Result:** 14 requests succeeded; each city/street pair returned a valid
`result=true` with a `data` object. Across these seven shared street names,
46 house-number entries occurred under `с-ще`, and 14 under `смт`.
There were **zero identical numbers after conservative case/whitespace
normalization**, but this does not prove there are no overlapping physical
buildings. DTEK may use different spellings and/or duplicate address records.

| Street | с-ще | смт | Exact intersection | Only с-ще | Only смт |
|---|---:|---:|---:|---:|---:|
| вул. Ветеранів | 7 | 1 | 0 | 7 | 1 |
| вул. Дорожна | 10 | 1 | 0 | 10 | 1 |
| вул. Заводська | 15 | 1 | 0 | 15 | 1 |
| вул. Лісна | 4 | 1 | 0 | 4 | 1 |
| вул. Черкаська | 1 | 3 | 0 | 1 | 3 |
| вул. Чернігівська | 2 | 3 | 0 | 2 | 3 |
| пров. Будівельників | 7 | 4 | 0 | 7 | 4 |
| **Total** | **46** | **14** | **0** | **46** | **14** |

## Important review candidates

- `вул. Ветеранів`: `с-ще` has `1/А`, `смт` has `1A`
  (different slash / alphabet; potential same building).
- `вул. Заводська`: `с-ще` has `1А`, `смт` has `1/А`
  (potential same building).
- `вул. Чернігівська`: `смт` has unusual value `:0003`;
  do not silently normalize to house 3.
- `вул. Заводська`: `с-ще` includes unusual `0095`;
  preserve source string.

Comparisons use the exact street name and city key in each request,
without assuming that historical and current settlement names are aliases.
The report contains only public house-number keys, not outage status details.
Do not auto-merge `1/А` and `1А` until their addresses are confirmed
against physical buildings or source data.

### Follow-up

1. Check both spelling candidates against Visicom/OSM addresses.
2. Extend the analysis to streets unique to either settlement key, and
   normalize street aliases only after confirmation.
3. Keep the city key in the source address ID even after unifying aliases.
4. Do not treat the two city directories as interchangeable or discard the
   legacy `смт` list.
