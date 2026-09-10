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
    def test_seller_name_suggestions_are_anonymous_and_flattened(self):
        response = {
            "errors": [],
            "results": [["Card Traders Austin", "Texas Card Traders"]],
        }
        client = TCGPlayerPublicClient(retry_delays=(), min_request_interval=0)

        with patch(
            "tcg_local_finder.public_client.urlopen",
            return_value=FakeResponse(response),
        ) as open_url:
            names = client.suggest_seller_names("Card Traders")

        self.assertEqual(names, ["Card Traders Austin", "Texas Card Traders"])
        request = open_url.call_args.args[0]
        self.assertIn("query=Card+Traders", request.full_url)
        self.assertNotIn("Authorization", request.headers)
        self.assertNotIn("Cookie", request.headers)

    def test_seller_search_treats_api_404_as_no_match(self):
        response = {
            "errors": [{"code": "404", "message": "Seller results not found"}],
            "results": [],
        }
        client = TCGPlayerPublicClient(retry_delays=(), min_request_interval=0)

        with patch(
            "tcg_local_finder.public_client.urlopen",
            return_value=FakeResponse(response),
        ):
            sellers = client.search_sellers("Missing Store")

        self.assertEqual(sellers, [])

    def test_seller_search_uses_magic_category_without_credentials(self):
        response = {
            "errors": [],
            "results": [
                {
                    "searchResults": [
                        {
                            "displayName": "Black Castle Gamez",
                            "sellerKey": "b31b0b79",
                        }
                    ]
                }
            ],
        }
        client = TCGPlayerPublicClient(retry_delays=(), min_request_interval=0)

        with patch(
            "tcg_local_finder.public_client.urlopen",
            return_value=FakeResponse(response),
        ) as open_url:
            sellers = client.search_sellers("Black Castle Gamez")

        self.assertEqual(sellers[0]["sellerKey"], "b31b0b79")
        request = open_url.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(body["categoryId"], 1)
        self.assertNotIn("Authorization", request.headers)
        self.assertNotIn("Cookie", request.headers)

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
