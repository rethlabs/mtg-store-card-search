from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from tcg_local_finder.public_client import TCGPlayerPublicClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class PublicClientTests(unittest.TestCase):
    def test_search_uses_anonymous_seller_filter(self):
        response = {
            "errors": [],
            "results": [{"results": [{"productName": "Wind Strider"}], "totalResults": 1}],
        }
        client = TCGPlayerPublicClient(retry_delays=(), min_request_interval=0)

        with patch(
            "tcg_local_finder.public_client.urlopen",
            return_value=FakeResponse(response),
        ) as open_url:
            products = client.search_store_inventory("b31b0b79", "Wind Strider")

        self.assertEqual(products[0]["productName"], "Wind Strider")
        request = open_url.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(
            body["listingSearch"]["filters"]["term"]["sellerKey"], ["b31b0b79"]
        )
        self.assertNotIn("Authorization", request.headers)
        self.assertNotIn("Cookie", request.headers)


if __name__ == "__main__":
    unittest.main()
