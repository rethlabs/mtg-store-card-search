from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tcg_local_finder.cli import _load_request, build_parser


class CliTests(unittest.TestCase):
    def test_repeatable_city_and_card_arguments(self):
        args = build_parser().parse_args(
            ["find", "--city", "Austin", "--city", "Temple", "--card", "Sol Ring"]
        )
        self.assertEqual(args.city, ["Austin", "Temple"])
        self.assertEqual(args.card, ["Sol Ring"])

    def test_request_file_loads_printing_filters(self):
        payload = {
            "areas": [{"city": "Austin", "state": "TX"}],
            "cards": [{"name": "Sol Ring", "set": "Commander Masters", "finish": "foil"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            areas, cards = _load_request(path)
        self.assertEqual(areas[0].label, "Austin, TX")
        self.assertEqual(cards[0].set_name, "Commander Masters")
        self.assertEqual(cards[0].finish, "foil")

    def test_request_defaults_language_to_english(self):
        payload = {
            "areas": [{"city": "Austin", "state": "TX"}],
            "cards": [{"name": "Sol Ring"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            _areas, cards = _load_request(path)
        self.assertEqual(cards[0].language, "English")


if __name__ == "__main__":
    unittest.main()
