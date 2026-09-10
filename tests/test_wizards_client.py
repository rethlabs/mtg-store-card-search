from __future__ import annotations

import json
import unittest

from tcg_local_finder.wizards_client import WizardsLocatorClient, decode_wizards_data


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return self.text.encode("utf-8")


class FakeOpener:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        return FakeResponse(next(self.responses))


def encoded_store_response():
    table = [
        {"_1": 2},
        "routes/($lang).search",
        {"_3": 4},
        "data",
        {"_5": 6},
        "storesPins",
        {"_7": 8},
        "storesByLocation",
        {"_9": 10},
        "stores",
        [11],
        {"_12": 13, "_14": 15, "_16": 17},
        "id",
        "19593",
        "name",
        "Black Castle Gamez",
        "distance",
        2665.18286074,
    ]
    return json.dumps(table)


class WizardsClientTests(unittest.TestCase):
    def test_decodes_flattened_store_response(self):
        decoded = decode_wizards_data(encoded_store_response())
        store = decoded["routes/($lang).search"]["data"]["storesPins"][
            "storesByLocation"
        ]["stores"][0]
        self.assertEqual(store["id"], "19593")
        self.assertEqual(store["name"], "Black Castle Gamez")

    def test_search_uses_location_and_radius_without_credentials(self):
        opener = FakeOpener(["<html></html>", encoded_store_response()])
        client = WizardsLocatorClient(
            opener=opener, retry_delays=(), min_request_interval=0
        )
        stores = client.search_stores("Houston, TX", distance_miles=25)

        self.assertEqual(stores[0]["id"], "19593")
        request = opener.requests[1]
        self.assertIn("query=Houston%2C+TX", request.full_url)
        self.assertIn("distance=25", request.full_url)
        self.assertNotIn("Authorization", request.headers)
        self.assertNotIn("Cookie", request.headers)


if __name__ == "__main__":
    unittest.main()
