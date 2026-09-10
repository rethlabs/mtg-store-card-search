from __future__ import annotations

import unittest

from tcg_local_finder.finder import _matching_listings, find_cards, find_stores
from tcg_local_finder.models import Area, CardWanted, Store


class FakeClient:
    def search_stores(self, **filters):
        if filters.get("city") == "Houston":
            return ["alpha", "shared"]
        return ["shared", "beta"]

    def get_store_info(self, keys):
        names = {"alpha": "Alpha Games", "shared": "Shared Games", "beta": "Beta Games"}
        return [
            {"storeKey": key, "name": names[key], "storefrontUrl": f"https://{key}.example"}
            for key in keys
        ]

    def get_store_inventory(self, store_key, product_name):
        if store_key == "beta":
            return []
        return [
            {
                "productId": 123,
                "name": "Tergrid, God of Fright // Tergrid's Lantern",
                "category": "Magic",
                "group": "Kaldheim",
                "number": "307",
                "skus": [
                    {
                        "skuId": 456,
                        "condition": {"name": "Near Mint"},
                        "language": {"name": "English"},
                        "foil": False,
                        "price": 19.25,
                        "quantity": 1,
                    }
                ],
            }
        ]


class PartlyFailingClient(FakeClient):
    def get_store_inventory(self, store_key, product_name):
        if store_key == "beta":
            raise RuntimeError("store authorization required")
        return super().get_store_inventory(store_key, product_name)


class FinderTests(unittest.TestCase):
    def test_store_discovery_deduplicates_and_keeps_area_labels(self):
        stores = find_stores(
            FakeClient(),
            [Area(city="Houston", state="TX"), Area(city="Dallas", state="TX")],
        )
        shared = next(store for store in stores if store.key == "shared")
        self.assertEqual(shared.areas, ("Dallas, TX", "Houston, TX"))

    def test_double_faced_card_matches_front_name(self):
        wanted = CardWanted(
            name="Tergrid, God of Fright",
            set_name="Kaldheim",
            number="307",
            condition="Near Mint",
            finish="nonfoil",
        )
        store = Store(key="alpha", name="Alpha Games")
        products = FakeClient().get_store_inventory("alpha", wanted.name)
        listings = _matching_listings(store, wanted, products)
        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].price, 19.25)

    def test_store_results_rank_by_coverage(self):
        stores = [Store(key="beta", name="Beta"), Store(key="alpha", name="Alpha")]
        results = find_cards(
            FakeClient(), stores, [CardWanted(name="Tergrid, God of Fright")], workers=1
        )
        self.assertEqual(results[0].store.key, "alpha")
        self.assertEqual(results[0].found_count, 1)
        self.assertEqual(results[1].found_count, 0)

    def test_one_store_failure_does_not_abort_other_results(self):
        stores = [Store(key="beta", name="Beta"), Store(key="alpha", name="Alpha")]
        results = find_cards(
            PartlyFailingClient(),
            stores,
            [CardWanted(name="Tergrid, God of Fright")],
            workers=1,
        )
        beta = next(result for result in results if result.store.key == "beta")
        alpha = next(result for result in results if result.store.key == "alpha")
        self.assertEqual(alpha.found_count, 1)
        self.assertEqual(len(beta.errors), 1)


if __name__ == "__main__":
    unittest.main()
