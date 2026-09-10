from __future__ import annotations

import unittest

from tcg_local_finder.seller_resolution import normalize_seller_name, resolve_seller


class FakeClient:
    def __init__(self, candidates):
        self.candidates = candidates

    def search_sellers(self, seller_name):
        return self.candidates


class SellerResolutionTests(unittest.TestCase):
    def test_normalizes_punctuation_without_fuzzy_guessing(self):
        self.assertEqual(
            normalize_seller_name("Wonko's Toys & Games"),
            normalize_seller_name("Wonkos Toys and Games"),
        )

    def test_resolves_one_exact_normalized_name(self):
        client = FakeClient(
            [
                {
                    "displayName": "Black Castle Gamez",
                    "sellerKey": "b31b0b79",
                    "location": "Texas, US",
                }
            ]
        )
        result = resolve_seller(client, "Black Castle Gamez")
        self.assertEqual(result["status"], "exact")
        self.assertEqual(result["seller_key"], "b31b0b79")
        self.assertEqual(
            result["seller_url"],
            "https://www.tcgplayer.com/sellers/Black-Castle-Gamez/b31b0b79",
        )

    def test_does_not_guess_when_only_partial_matches_exist(self):
        client = FakeClient(
            [
                {
                    "displayName": "Black Castle Cards",
                    "sellerKey": "wrong",
                    "location": "Texas, US",
                }
            ]
        )
        result = resolve_seller(client, "Black Castle Gamez")
        self.assertEqual(result["status"], "not_found")
        self.assertIsNone(result["seller_key"])
        self.assertEqual(result["candidate_count"], 1)


if __name__ == "__main__":
    unittest.main()
