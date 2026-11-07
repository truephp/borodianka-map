# Cumulative map edits (Borodianka pilot)

## Files and lifecycle

- `data/buildings.geojson` in Git is the **immutable imported OSM source**. Never commit manually patched building geometries into this file.
- `data/borodianka-manual-overrides.json` is the **single accumulating master** for reviewed DTEK matches (`decisions`), OSM polygons (`geometryPatches`), and OSM addresses (`addressOverrides`). Each type is keyed by a stable address tuple or OSM ID, not appended blindly.
- `data/borodianka-osm-approvals.json` records exceptional manual approvals for a **specific current OSM geometry SHA-256**.
- GitHub Pages gets the original as `data/buildings.original.geojson` and the **patched** data under the existing `data/buildings.geojson` URL. The build changes only the workflow workspace, **not** the Git-tracked original.

## Add a new exported JSON file

1. Edit buildings and/or DTEK links on the map. Export `borodianka-all-manual-overrides.json` from **8. Збереження та експорт**. The editor tries to load the current master and merge it before downloading.
2. Upload the resulting file to the repository path `pending/borodianka-manual-overrides.json` in GitHub. Alternatively run the CLI merge below with your new export.
3. The **Merge exported map edits into cumulative master** workflow merges it into `data/borodianka-manual-overrides.json`, removes the temporary uploaded file and triggers the regular data rebuild. On the VPS this file upload/merge will be an API operation.
4. Inspect the resulting master commit and any failed conflict report before trusting the new map. Do not edit `data/buildings.geojson` to bypass conflicts.

Local CLI merge (can also merge exports from separate editors, one at a time):

```bash
python scripts/build_map_patches.py merge \
  --master data/borodianka-manual-overrides.json \
  --incoming borodianka-all-manual-overrides.json \
  --output data/borodianka-manual-overrides.json
```

The merge **replaces entries with the same ID** and preserves all unrelated ones. An older baseline for an existing geometry/address edit is retained, not silently rebased. For conflicting baselines, merge stops rather than losing the history.

## Applying patches to a refreshed original OSM

```bash
python scripts/build_map_patches.py apply \
  --original data/buildings.geojson \
  --points data/address-points.geojson \
  --master data/borodianka-manual-overrides.json \
  --approvals data/borodianka-osm-approvals.json \
  --output /tmp/buildings.patched.geojson \
  --report /tmp/borodianka-patch-report.json
```

Each new geometry/address patch contains `baseGeometry`, a snapshot from the unmodified OSM feature before the edit. If the next OSM import differs from this baseline, patch application fails and produces a conflict report. **No corrected file is published.** A legacy patch without this baseline also requires review.

Example conflict:

```json
{
  "source": "geometryPatches",
  "id": "320878713",
  "reason": "geometry_changed",
  "currentGeometrySha256": "..."
}
```

After manually comparing the changed source with the existing correction, add the exact current geometry SHA-256 to the approvals file:

```json
{
  "approvedGeometry": {
    "320878713": "<exact currentGeometrySha256 from the conflict report>"
  }
}
```

This approves that particular version of the original OSM geometry, **not arbitrary future updates**. The master still retains the original baseline until an intentional rebase.

## Limits and security

- The regular frontend currently reads the patched OSM export. Private Visicom geometry is not written to this public OSM GeoJSON. The separate encrypted Visicom-first unified dataset must be rebuilt when OSM geometry changes affect deduplication or cross-source correspondence.
- A user's browser **cannot commit downloaded files to GitHub**. The automatic merge begins when the exported JSON is uploaded to the `pending/` path (or the CLI is run). In the future the VPS backend will accept it directly.
- Export/import does not modify OpenStreetMap itself.
