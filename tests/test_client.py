from __future__ import annotations

import io
import unittest
from unittest.mock import call, patch
from urllib.error import HTTPError
from urllib.request import Request

from tcg_local_finder.client import TCGPlayerClient


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return b'{"success": true}'


class ClientTests(unittest.TestCase):
    def test_retry_schedule_is_one_minute_then_three_minutes(self):
        failures = [
            HTTPError("https://example.test", 500, "error", {}, io.BytesIO(b"{}")),
            HTTPError("https://example.test", 500, "error", {}, io.BytesIO(b"{}")),
        ]
        client = TCGPlayerClient(
            "public",
            "private",
            retry_delays=(60.0, 180.0),
            min_request_interval=0,
        )

        with (
            patch(
                "tcg_local_finder.client.urlopen",
                side_effect=[*failures, FakeResponse()],
            ),
            patch("tcg_local_finder.client.time.sleep") as sleep,
        ):
            result = client._send(Request("https://example.test"))

        self.assertTrue(result["success"])
        self.assertEqual(sleep.call_args_list, [call(60.0), call(180.0)])

    def test_request_starts_are_spaced_half_a_second_apart(self):
        client = TCGPlayerClient(
            "public",
            "private",
            retry_delays=(),
            min_request_interval=0.5,
        )

        with (
            patch("tcg_local_finder.client.time.monotonic", side_effect=[10.0, 10.1]),
            patch("tcg_local_finder.client.time.sleep") as sleep,
        ):
            client._wait_for_request_slot()
            client._wait_for_request_slot()

        sleep.assert_called_once()
        self.assertAlmostEqual(sleep.call_args.args[0], 0.4)


if __name__ == "__main__":
    unittest.main()
