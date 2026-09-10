from __future__ import annotations

import unittest

from tcg_local_finder.seller_resolution import normalize_seller_name, resolve_seller


class FakeClient:
    def __init__(self, candidates, suggestions=None, sellers_by_name=None):
        self.candidates = candidates
        self.suggestions = suggestions or {}
        self.sellers_by_name = sellers_by_name or {}
        self.suggestion_queries = []

    def search_sellers(self, seller_name):
        return self.sellers_by_name.get(seller_name, self.candidates)

    def suggest_seller_names(self, query):
        self.suggestion_queries.append(query)
        return self.suggestions.get(query, [])


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

    def test_progressive_search_uses_last_nonempty_list_and_stop_words(self):
        seller = {
            "displayName": "Card Traders Austin",
            "sellerKey": "bfe5e82c",
            "location": "US",
        }
        client = FakeClient(
            [],
            suggestions={
                "Card": ["Card and Board LLC"],
                "Card Traders": ["Card Traders Austin", "Texas Card Traders"],
            },
            sellers_by_name={"Card Traders Austin": [seller]},
        )

        result = resolve_seller(client, "Card Traders of Austin")

        self.assertEqual(result["status"], "stopword")
        self.assertEqual(result["seller_key"], "bfe5e82c")
        self.assertEqual(
            client.suggestion_queries,
            ["Card", "Card Traders"],
        )

    def test_unresolved_search_records_attempts_and_candidates(self):
        client = FakeClient(
            [],
            suggestions={
                "The": ["The Secret Lair"],
                "The Secret": ["The Secret Lair"],
            },
        )

        result = resolve_seller(client, "The Secret Lantern")

        self.assertEqual(result["status"], "not_found")
        self.assertEqual(
            result["attempted_queries"],
            ["The Secret Lantern", "The", "The Secret", "The Secret Lantern"],
        )
        self.assertEqual(result["candidates"][0]["seller_name"], "The Secret Lair")

    def test_stop_word_collision_is_ambiguous(self):
        client = FakeClient(
            [
                {"displayName": "Keep of Games", "sellerKey": "one"},
                {"displayName": "The Keep Games", "sellerKey": "two"},
            ]
        )

        result = resolve_seller(client, "The Keep of Games")

        self.assertEqual(result["status"], "ambiguous")
        self.assertIsNone(result["seller_key"])


if __name__ == "__main__":
    unittest.main()
