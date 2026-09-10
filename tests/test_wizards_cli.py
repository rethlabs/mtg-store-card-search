from __future__ import annotations

import unittest

from tcg_local_finder.wizards_cli import _combine_stores, build_parser


class WizardsCliTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
