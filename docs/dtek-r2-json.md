# Live DTEK JSON in Cloudflare R2

The static map is deployed to GitHub Pages **only for changes in code/geodata**.
DTEK data is published to R2 directly from the 15-minute collector; it no
longer dispatches a Pages deployment after each capture.

## R2 keys

Current GitHub Actions publishing uses the configured `R2_BUCKET` and
`R2_ACCOUNT_ID` with these objects:

- `borodianka/data/dtek-gpv-schedule.json` — **public**, no Visicom data
- `borodianka/data/dtek-house-statuses.enc.json` — encrypted raw DTEK status capture
- `borodianka/data/dtek-all-unified-matches.enc.json` — **encrypted** DTEK ↔ Visicom/OSM address mapping, with fresh DTEK status fields

**Never publish decrypted Visicom records or credentials**. The map decrypts
the unified matching report locally with the existing Visicom password.

## Public host and map configuration

The R2 API upload endpoint `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`
requires signed requests; it is **not** a public web URL.

1. In Cloudflare R2, assign a public custom domain (or a suitable public
   R2 development URL) to the existing bucket `boromap`.
2. Confirm the following public URL actually serves the current schedule:
   `https://<YOUR-PUBLIC-R2-HOST>/borodianka/data/dtek-gpv-schedule.json`.
3. Set repository **Actions variable** `DTEK_R2_BASE_URL` to:
   `https://<YOUR-PUBLIC-R2-HOST>/borodianka/data`
   (the directory path, not a filename).
4. Run `Deploy site` **once**. It generates `data/dtek-r2-config.json`
   for all visitors. Subsequent DTEK data updates use R2 without a Pages build.
5. Alternatively, paste the same URL into **Публічний URL R2 для ДТЕК**
   in the map settings. This per-browser override is saved in localStorage.
   The map also derives the host from a configured Borodianka R2 tile URL.

Use a Cloudflare R2 CORS rule allowing the map origin
`https://truephp.lampass.top` with methods `GET` and `HEAD`, and suitable
request/response headers. If the public map itself is on another origin, allow
that origin too. Check the browser's Network tab for a successful cross-origin
fetch of both schedule and encrypted matching report.

The map polls the dynamic JSON every five minutes while the tab remains open.
When manual address decisions are being edited, it does not overwrite them.

## Safety and fallback

- If there is no configured public R2 URL, the frontend uses the legacy Pages
  JSON files as a **fallback**, with their original timestamps.
- If an R2 URL is configured but its fetch fails (including CORS), the map
  displays a loading error rather than silently claiming that the stale Pages
  JSON is live.
- Schedule and matching report are separate objects; an error in one part of
  the DTEK pipeline cannot overwrite the other part with invalid data.
- The two known failing streets remain explicit `source_error` records.
- The last successful encrypted report remains at its stable R2 key.

Do not retire the old Pages JSON until R2 public URLs and browser decryption
are verified for the actual map deployment.
