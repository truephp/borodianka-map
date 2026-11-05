import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
from enrich_visicom_street_types import metadata_by_id, enrich_collections


class EnrichVisicomTests(unittest.TestCase):
    def test_batch_feature_collection_metadata(self):
        result = metadata_by_id({
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "id": "ADR1",
                 "properties": {"street_type": "вулиця", "street_id": "STR1"}},
                {"type": "Feature", "id": "ADR2",
                 "properties": {"street_type": "провулок", "street_id": "STR2"}},
            ],
        })
        self.assertEqual(result["ADR1"]["street_type"], "вулиця")
        self.assertEqual(result["ADR2"]["street_id"], "STR2")

    def test_enriches_both_encrypted_collection_payloads(self):
        source = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []},
             "properties": {"visicomId": "ADR1", "street": "Грушевського", "name": "7"}}
        ]}
        unified = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []},
             "properties": {"source": "visicom", "visicomId": "ADR1",
                            "street": "Грушевського", "housenumber": "7"}},
            {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []},
             "properties": {"source": "osm", "sourceId": "42", "street": "Київська"}},
        ]}
        with patch("enrich_visicom_street_types.fetch_batch", return_value={
            "ADR1": {"street_type": "вулиця", "street_id": "STR1"}
        }) as fetch:
            count = enrich_collections(source, unified, "private-key", 100, 0)
        self.assertEqual(count, 1)
        fetch.assert_called_once_with(["ADR1"], "private-key")
        self.assertEqual(source["features"][0]["properties"]["street_type"], "вулиця")
        self.assertEqual(unified["features"][0]["properties"]["street_id"], "STR1")
        self.assertNotIn("street_type", unified["features"][1]["properties"])

    def test_rejects_partial_batch_without_modifying_original_data(self):
        source = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"visicomId": "ADR1"}}
        ]}
        unified = {"type": "FeatureCollection", "features": []}
        with patch("enrich_visicom_street_types.fetch_batch", return_value={}):
            with self.assertRaises(ValueError):
                enrich_collections(source, unified, "private-key", 100, 0)
        self.assertNotIn("street_type", source["features"][0]["properties"])


if __name__ == "__main__":
    unittest.main()
