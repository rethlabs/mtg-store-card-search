from __future__ import annotations

import unittest

from tcg_local_finder.public_cli import _listings, parse_seller_url


class FakeClient:
    def search_store_inventory(self, seller_key, card_name):
        return [
            {
                "productName": "Wind Strider",
                "setName": "Ixalan",
                "productId": 145771.0,
                "customAttributes": {"number": "88"},
                "listings": [
                    {
                        "sellerName": "Black Castle Gamez",
                        "sellerKey": seller_key,
                        "listingId": 758052085.0,
                        "printing": "Normal",
                        "condition": "Near Mint",
                        "language": "English",
                        "sellerPrice": 0.20,
                        "shippingPrice": 1.49,
                        "quantity": 4.0,
                    }
                ],
            }
        ]


class PublicCliTests(unittest.TestCase):
    def test_parse_seller_url(self):
        name, key = parse_seller_url(
            "https://www.tcgplayer.com/sellers/Black-Castle-Gamez/b31b0b79?q=x"
        )
        self.assertEqual(name, "Black Castle Gamez")
        self.assertEqual(key, "b31b0b79")

    def test_response_maps_seller_price_and_shipping(self):
        listings = _listings(FakeClient(), "Black Castle Gamez", "b31b0b79", "Wind Strider")
        self.assertEqual(listings[0]["card_price"], 0.20)
        self.assertEqual(listings[0]["shipping_price"], 1.49)
        self.assertEqual(listings[0]["quantity"], 4)


if __name__ == "__main__":
    unittest.main()
