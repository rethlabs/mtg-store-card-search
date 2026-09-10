from __future__ import annotations

import unittest

from tcg_local_finder.local_cli import _load_cards, _render, build_parser, search_local_inventory
from tcg_local_finder.public_client import TCGPlayerPublicError


class FakeClient:
    def search_store_inventory(self, seller_key, card_name):
        if card_name == "Missing Card":
            return []
        if card_name == "Broken Card":
            raise TCGPlayerPublicError("temporary failure")
        price = 1.0 if seller_key == "near" else 0.5
        return [
            {
                "productName": card_name,
                "setName": "Example Set",
                "customAttributes": {"number": "1"},
                "listings": [
                    {
                        "sellerName": seller_key,
                        "sellerKey": seller_key,
                        "printing": "Normal",
                        "condition": "Near Mint",
                        "language": "English",
                        "sellerPrice": price,
                        "shippingPrice": 1.49,
                        "quantity": 1,
                    }
                ],
            }
        ]


def store(name, key, distance):
    return {
        "wizards_store_id": key,
        "name": name,
        "address": "Texas",
        "distance_miles": distance,
        "tcgplayer": {
            "status": "exact",
            "seller_name": name,
            "seller_key": key,
        },
    }


class LocalCliTests(unittest.TestCase):
    def test_defaults_to_four_workers(self):
        args = build_parser().parse_args(["--city", "Houston", "--card", "Sol Ring"])
        self.assertEqual(args.workers, 4)

    def test_card_arguments_are_deduplicated(self):
        cards = _load_cards(["Sol Ring", "Sol Ring", "Arcane Signet"], None)
        self.assertEqual(cards, ["Sol Ring", "Arcane Signet"])

    def test_results_rank_by_coverage_then_subtotal(self):
        stores = [store("Near Store", "near", 1.0), store("Cheap Store", "cheap", 5.0)]
        results = search_local_inventory(
            stores,
            ["Found Card", "Missing Card"],
            workers=2,
            client=FakeClient(),
        )
        self.assertEqual(results[0]["store_name"], "Cheap Store")
        self.assertEqual(results[0]["found_count"], 1)
        self.assertEqual(results[0]["card_subtotal"], 0.5)

    def test_unresolved_stores_are_not_searched(self):
        unresolved = store("Unknown", "unknown", 1.0)
        unresolved["tcgplayer"]["status"] = "not_found"
        self.assertEqual(
            search_local_inventory([unresolved], ["Sol Ring"], client=FakeClient()),
            [],
        )

    def test_physical_only_store_remains_visible_but_is_not_searched(self):
        physical = store("Physical Store", "physical", 2.0)
        physical["tcgplayer"] = {
            "status": "physical_only",
            "seller_name": None,
            "seller_key": None,
        }
        physical["registry"] = {
            "singles_status": "sells",
            "tcgplayer_status": "physical_only",
        }

        results = search_local_inventory(
            [physical], ["Sol Ring"], client=FakeClient()
        )

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["searched"])
        self.assertIn("not searched", _render(results))
        self.assertIn("physical_only", _render(results))

    def test_one_inventory_failure_does_not_abort_other_cards(self):
        results = search_local_inventory(
            [store("Example", "near", 1.0)],
            ["Found Card", "Broken Card"],
            client=FakeClient(),
        )
        self.assertEqual(results[0]["found_count"], 1)
        self.assertIn("Broken Card: temporary failure", results[0]["inventory_errors"])
        self.assertIn("Found Card", _render(results))


if __name__ == "__main__":
    unittest.main()
