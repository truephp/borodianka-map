#!/usr/bin/env python3
"""Enrich encrypted Visicom GeoJSON with address metadata, without requesting geometry.

Both the archived Visicom export and the unified building layer are updated
from the same verified API responses. Never write plaintext to disk.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from merge_buildings import decrypt, encrypt

API = "https://api.visicom.ua/data-api/5.0/uk/feature/"
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
FIELDS = ("street_type", "street_id")


def extract_features(response):
    if isinstance(response, list):
        items = response
    elif isinstance(response, dict) and response.get("type") == "FeatureCollection":
        items = response.get("features", [])
    elif isinstance(response, dict) and response.get("type") == "Feature":
        items = [response]
    elif isinstance(response, dict) and isinstance(response.get("features"), list):
        items = response["features"]
    else:
        raise ValueError("Unexpected Visicom feature response structure")
    if not isinstance(items, list):
        raise ValueError("Visicom response has invalid features list")
    return items


def metadata_by_id(response):
    result = {}
    for feature in extract_features(response):
        if not isinstance(feature, dict) or not isinstance(feature.get("properties"), dict):
            raise ValueError("Feature without properties")
        ident = str(feature.get("id") or feature["properties"].get("visicomId") or "")
        if not ident:
            raise ValueError("Feature response has no ID")
        props = feature["properties"]
        result[ident] = {field: props[field] for field in FIELDS if props.get(field) is not None}
    return result


def fetch_batch(ids, api_key, retries=3):
    url = API + ",".join(quote(ident, safe="") for ident in ids) + ".json?" + urlencode({
        "key": api_key, "geometry": "no"
    })
    for attempt in range(retries):
        try:
            request = Request(url, headers={"Accept": "application/json", "User-Agent": "BorodiankaMap/1.0"})
            with urlopen(request, timeout=45) as response:
                body = response.read()
            return metadata_by_id(json.loads(body))
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            # Never print request URL: it contains the API key.
            print(f"Visicom batch failed ({len(ids)} IDs), attempt {attempt+1}/{retries}: {type(exc).__name__}", file=sys.stderr)
            if attempt == retries-1:
                raise RuntimeError("Visicom metadata batch failed") from None
            time.sleep(2 ** attempt)


def visicom_id(feature):
    props = feature.get("properties") or {}
    if props.get("source") not in (None, "visicom"):
        return None
    value = props.get("visicomId") or (feature.get("id") if props.get("source") is None else None)
    return str(value) if value else None


def enrich_collections(source, unified, api_key, batch_size, delay):
    collections = (source, unified)
    for collection in collections:
        if collection.get("type") != "FeatureCollection" or not isinstance(collection.get("features"), list):
            raise ValueError("Expected encrypted FeatureCollections")
    ids = sorted({ident for collection in collections for feature in collection["features"]
                  if (ident := visicom_id(feature))})
    if not ids or any(not ID_PATTERN.fullmatch(ident) for ident in ids):
        raise ValueError("Invalid or empty Visicom IDs")
    print(f"Visicom IDs to enrich: {len(ids)}; estimated API requests: {(len(ids)+batch_size-1)//batch_size}")
    metadata = {}
    for offset in range(0, len(ids), batch_size):
        chunk = ids[offset:offset+batch_size]
        response = fetch_batch(chunk, api_key)
        missing = set(chunk)-set(response)
        if missing:
            raise ValueError(f"Visicom returned only {len(response)} of {len(chunk)} requested IDs; refusing partial update")
        if any("street_type" not in response[ident] or "street_id" not in response[ident] for ident in chunk):
            raise ValueError("API response missing required street_type/street_id; refusing partial update")
        metadata.update({ident: response[ident] for ident in chunk})
        print(f"Retrieved {len(metadata)}/{len(ids)} IDs")
        if offset+batch_size < len(ids):
            time.sleep(delay)
    for collection in collections:
        for feature in collection["features"]:
            ident = visicom_id(feature)
            if ident:
                feature["properties"].update(metadata[ident])
    return len(ids)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--unified", required=True)
    parser.add_argument("--out-source", required=True)
    parser.add_argument("--out-unified", required=True)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 250 or args.delay < 0:
        parser.error("batch-size must be 1..250, delay must be nonnegative")
    password, api_key = os.environ.get("VISICOM_EXPORT_PASSWORD"), os.environ.get("VISICOM_API_KEY")
    if not password or not api_key:
        raise ValueError("Missing required Visicom secrets")
    source = decrypt(json.loads(Path(args.source).read_text()), password)
    unified = decrypt(json.loads(Path(args.unified).read_text()), password)
    count = enrich_collections(source, unified, api_key, args.batch_size, args.delay)
    # Write only after all API requests succeeded and metadata is complete.
    for path, data in ((args.out_source, source), (args.out_unified, unified)):
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(encrypt(data, password), ensure_ascii=False)+"\n")
    print(f"Encrypted Visicom metadata enrichment finished: {count} IDs; no plaintext artifacts")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Enrichment failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
