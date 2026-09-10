from __future__ import annotations

import unittest
from datetime import date

from tcg_local_finder.store_registry import (
    apply_store_registry,
    entry_is_due,
    exclusion_reason,
    stores_requiring_resolution,
)


class StoreRegistryTests(unittest.TestCase):
    def test_unknown_is_due_after_thirty_days(self):
        entry = {
            "tcgplayer_status": "unknown",
            "last_checked": "2026-08-01",
        }
        self.assertTrue(entry_is_due(entry, today=date(2026, 9, 10)))

    def test_physical_only_is_not_due_before_ninety_days(self):
        entry = {
            "tcgplayer_status": "physical_only",
            "last_checked": "2026-08-01",
        }
        self.assertFalse(entry_is_due(entry, today=date(2026, 9, 10)))

    def test_manual_match_is_only_due_on_error(self):
        entry = {
            "tcgplayer_status": "manual_verified",
            "last_checked": "2020-01-01",
        }
        self.assertFalse(entry_is_due(entry, today=date(2026, 9, 10)))
        entry["last_error"] = "seller unavailable"
        self.assertTrue(entry_is_due(entry, today=date(2026, 9, 10)))
        entry.pop("last_error")
        self.assertFalse(
            entry_is_due(entry, today=date(2026, 9, 10), recheck_all=True)
        )

    def test_gamestop_prefix_is_excluded(self):
        exclusions = {
            "name_prefixes": [
                {"prefix": "GameStop -", "reason": "no singles storefront"}
            ]
        }
        self.assertEqual(
            exclusion_reason("GameStop - 123", exclusions), "no singles storefront"
        )
        self.assertIsNone(exclusion_reason("JaysGameStop", exclusions))

    def test_manual_seller_key_is_applied_without_resolution(self):
        stores = [{"name": "Pat's Games", "wizards_store_id": "1"}]
        registry = {
            "stores": [
                {
                    "store_name": "Pat's Games",
                    "tcgplayer_status": "manual_verified",
                    "seller_name": "PatsGamesATX",
                    "seller_key": "1ee68612",
                }
            ]
        }
        included, excluded = apply_store_registry(
            stores, registry, {"exact_names": [], "name_prefixes": []}
        )
        self.assertEqual(excluded, [])
        self.assertEqual(included[0]["tcgplayer"]["seller_key"], "1ee68612")
        self.assertEqual(stores_requiring_resolution(included), [])

    def test_recheck_all_bypasses_exclusion(self):
        stores = [{"name": "GameStop - 123", "wizards_store_id": "1"}]
        exclusions = {
            "exact_names": [],
            "name_prefixes": [{"prefix": "GameStop -", "reason": "excluded"}],
        }
        included, excluded = apply_store_registry(
            stores, {"stores": []}, exclusions, recheck_all=True
        )
        self.assertEqual(len(included), 1)
        self.assertEqual(excluded, [])


if __name__ == "__main__":
    unittest.main()
