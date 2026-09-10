from __future__ import annotations

import unittest
from datetime import date

from tcg_local_finder.registry_cli import build_parser, render_audit


class RegistryCliTests(unittest.TestCase):
    def test_requested_audit_command_parses(self):
        args = build_parser().parse_args(["audit", "--stale-days", "30"])
        self.assertEqual(args.command, "audit")
        self.assertEqual(args.stale_days, 30)

    def test_audit_lists_due_entries_first(self):
        registry = {
            "stores": [
                {
                    "store_name": "Old Unknown",
                    "singles_status": "unknown",
                    "tcgplayer_status": "unknown",
                    "last_checked": "2026-01-01",
                },
                {
                    "store_name": "Verified",
                    "singles_status": "sells",
                    "tcgplayer_status": "manual_verified",
                    "last_checked": "2020-01-01",
                },
            ]
        }
        rendered = render_audit(
            registry,
            {"exact_names": [], "name_prefixes": []},
            today=date(2026, 9, 10),
        )
        rows = rendered.splitlines()
        self.assertIn("Old Unknown", rows[2])
        self.assertIn("yes", rows[2])
        self.assertIn("Verified", rows[3])
        self.assertIn("no", rows[3])


if __name__ == "__main__":
    unittest.main()
