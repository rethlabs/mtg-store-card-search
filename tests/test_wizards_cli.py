from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tcg_local_finder.public_client import TCGPlayerPublicError
from tcg_local_finder.wizards_cli import (
    _combine_stores,
    _render,
    _safe_resolve_seller,
    _write_triage_file,
    build_parser,
)


class WizardsCliTests(unittest.TestCase):
    def test_seller_failure_is_kept_as_store_error(self):
        class FailingClient:
            def search_sellers(self, seller_name):
                raise TCGPlayerPublicError("temporary failure")

        result = _safe_resolve_seller(FailingClient(), "Example Store")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "temporary failure")

    def test_defaults_to_four_workers(self):
        args = build_parser().parse_args(["--city", "Houston"])
        self.assertEqual(args.workers, 4)

    def test_combines_duplicate_stores_across_areas(self):
        store = {
            "id": "19593",
            "name": "Black Castle Gamez",
            "postalAddress": "1335 E Whitestone Blvd, Cedar Park, TX",
            "distance": 1609.344,
        }
        stores = _combine_stores(
            [("Houston, TX", [store]), ("Dallas, TX", [dict(store)])]
        )
        self.assertEqual(len(stores), 1)
        self.assertEqual(stores[0]["distance_miles"], 1.0)
        self.assertEqual(stores[0]["matched_areas"], ["Dallas, TX", "Houston, TX"])

    def test_renders_resolved_seller_key(self):
        stores = [
            {
                "wizards_store_id": "19593",
                "name": "Black Castle Gamez",
                "address": "Cedar Park, TX",
                "distance_miles": 1.66,
                "matched_areas": ["Cedar Park, TX"],
                "tcgplayer": {"status": "exact", "seller_key": "b31b0b79"},
            }
        ]
        rendered = _render(stores)
        self.assertIn("TCG match", rendered)
        self.assertIn("b31b0b79", rendered)

    def test_unresolved_seller_is_warned_and_written_for_triage(self):
        stores = [
            {
                "wizards_store_id": "21783",
                "name": "The Secret Lantern Books & Games",
                "address": "Cedar Park, TX",
                "tcgplayer": {
                    "status": "not_found",
                    "attempted_queries": ["The", "The Secret"],
                    "candidates": [],
                },
            }
        ]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "triage.jsonl"
            with self.assertLogs(
                "tcg_local_finder.wizards_cli", level="WARNING"
            ) as captured:
                _write_triage_file(stores, str(path))

            self.assertIn("The Secret Lantern", captured.output[0])
            self.assertIn('"status": "not_found"', path.read_text())


if __name__ == "__main__":
    unittest.main()
