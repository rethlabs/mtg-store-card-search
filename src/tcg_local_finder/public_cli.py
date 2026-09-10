from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse

from .public_client import TCGPlayerPublicClient, TCGPlayerPublicError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tcg-seller",
        description="Search a public TCGplayer seller storefront without logging in.",
    )
    parser.add_argument(
        "--seller-url",
        required=True,
        help="Public seller URL, such as https://www.tcgplayer.com/sellers/Name/key",
    )
    parser.add_argument("--card", action="append", default=[], help="Card name; repeatable")
    parser.add_argument("--cards-file", type=Path, help="One card name per line")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent searches")
    parser.add_argument("--format", choices=("table", "json"), default="table")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        seller_name, seller_key = parse_seller_url(args.seller_url)
        cards = list(args.card)
        if args.cards_file:
            cards.extend(
                line.strip()
                for line in args.cards_file.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            )
        if not cards:
            raise ValueError("Provide --card or --cards-file")

        client = TCGPlayerPublicClient()
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            searches = executor.map(
                lambda card: listings_for_card(client, seller_name, seller_key, card),
                cards,
            )
            results = [listing for search in searches for listing in search]
        if args.format == "json":
            print(json.dumps(results, indent=2))
        else:
            print(_render(results))
        return 0
    except (TCGPlayerPublicError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def parse_seller_url(value: str) -> tuple[str, str]:
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in {
        "tcgplayer.com",
        "www.tcgplayer.com",
    }:
        raise ValueError("seller URL must be an HTTPS tcgplayer.com URL")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 3 or parts[0].casefold() != "sellers":
        raise ValueError("seller URL must have the form /sellers/<name>/<seller-key>")
    return parts[1].replace("-", " "), parts[2]


def listings_for_card(
    client: TCGPlayerPublicClient,
    seller_name: str,
    seller_key: str,
    wanted: str,
) -> list[dict[str, Any]]:
    listings: list[dict[str, Any]] = []
    for product in client.search_store_inventory(seller_key, wanted):
        if not _same_card(product.get("productName"), wanted):
            continue
        attributes = product.get("customAttributes") or {}
        for listing in product.get("listings") or []:
            if str(listing.get("sellerKey")) != seller_key:
                continue
            listings.append(
                {
                    "seller": str(listing.get("sellerName") or seller_name),
                    "seller_key": seller_key,
                    "wanted": wanted,
                    "product_name": str(product.get("productName") or ""),
                    "set": product.get("setName"),
                    "number": attributes.get("number"),
                    "condition": listing.get("condition"),
                    "language": listing.get("language"),
                    "finish": str(listing.get("printing") or "").lower(),
                    "card_price": float(listing.get("sellerPrice") or 0),
                    "shipping_price": float(listing.get("shippingPrice") or 0),
                    "quantity": int(listing.get("quantity") or 0),
                    "product_id": _optional_int(product.get("productId")),
                    "listing_id": _optional_int(listing.get("listingId")),
                }
            )
    return sorted(listings, key=lambda item: item["card_price"])


def _same_card(product_name: Any, wanted: str) -> bool:
    product = " ".join(str(product_name or "").casefold().split())
    target = " ".join(wanted.casefold().split())
    return product == target or product.startswith(f"{target} //")


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _render(results: list[dict[str, Any]]) -> str:
    if not results:
        return "No matching in-stock cards found."
    headers = ["Card", "Set", "Condition", "Finish", "Qty", "Price", "Shipping"]
    rows = [
        [
            str(item["product_name"]),
            str(item["set"] or ""),
            str(item["condition"] or ""),
            str(item["finish"] or ""),
            str(item["quantity"]),
            f"${item['card_price']:.2f}",
            f"${item['shipping_price']:.2f}",
        ]
        for item in results
    ]
    widths = [len(header) for header in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))
    rule = "-+-".join("-" * width for width in widths)
    lines = [
        " | ".join(header.ljust(widths[index]) for index, header in enumerate(headers)),
        rule,
    ]
    lines.extend(
        " | ".join(value.ljust(widths[index]) for index, value in enumerate(row))
        for row in rows
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
