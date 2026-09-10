from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Sequence

from .public_cli import listings_for_card
from .public_client import TCGPlayerPublicClient, TCGPlayerPublicError
from .store_registry import (
    DEFAULT_EXCLUSIONS_PATH,
    DEFAULT_REGISTRY_PATH,
    apply_store_registry,
    load_exclusions,
    load_registry,
    stores_requiring_resolution,
)
from .wizards_cli import (
    _combine_stores,
    _resolve_tcgplayer_sellers,
    _write_triage_file,
)
from .wizards_client import WizardsLocatorClient, WizardsLocatorError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mtg-local-search",
        description="Find wanted Magic cards at nearby TCGplayer sellers.",
    )
    parser.add_argument("--city", action="append", required=True, help="City; repeatable")
    parser.add_argument("--state", default="TX", help="State code (default: TX)")
    parser.add_argument(
        "--radius-miles", type=int, default=10, help="Search radius (default: 10)"
    )
    parser.add_argument("--card", action="append", default=[], help="Card; repeatable")
    parser.add_argument("--cards-file", type=Path, help="One card name per line")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent searches")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--exclusions", type=Path, default=DEFAULT_EXCLUSIONS_PATH)
    parser.add_argument(
        "--recheck-all-stores",
        action="store_true",
        help="Bypass registry ages and configured exclusions",
    )
    parser.add_argument(
        "--triage-file",
        default="tcgplayer-resolution-triage.jsonl",
        help="Write unresolved seller matches here (default: %(default)s)",
    )
    parser.add_argument("--format", choices=("table", "json"), default="table")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cards = _load_cards(args.card, args.cards_file)
        locations = [f"{city}, {args.state}" for city in args.city]
        locator = WizardsLocatorClient()
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            searches = executor.map(
                lambda location: (
                    location,
                    locator.search_stores(location, distance_miles=args.radius_miles),
                ),
                locations,
            )
            stores = _combine_stores(list(searches))

        registry = load_registry(args.registry)
        exclusions = load_exclusions(args.exclusions)
        stores, _excluded = apply_store_registry(
            stores,
            registry,
            exclusions,
            recheck_all=args.recheck_all_stores,
        )
        stores_to_resolve = stores_requiring_resolution(
            stores, recheck_all=args.recheck_all_stores
        )
        _resolve_tcgplayer_sellers(stores_to_resolve, workers=args.workers)
        _write_triage_file(stores, args.triage_file)
        results = search_local_inventory(stores, cards, workers=args.workers)
        if args.format == "json":
            print(json.dumps({"stores": stores, "inventory": results}, indent=2))
        else:
            print(_render(results))
        return 0
    except (OSError, TCGPlayerPublicError, WizardsLocatorError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _load_cards(card_args: list[str], cards_file: Path | None) -> list[str]:
    cards = [card.strip() for card in card_args if card.strip()]
    if cards_file:
        cards.extend(
            line.strip()
            for line in cards_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    cards = list(dict.fromkeys(cards))
    if not cards:
        raise ValueError("Provide --card or --cards-file")
    return cards


def search_local_inventory(
    stores: list[dict[str, Any]],
    cards: list[str],
    *,
    workers: int = 4,
    client: TCGPlayerPublicClient | None = None,
) -> list[dict[str, Any]]:
    public_client = client or TCGPlayerPublicClient()
    resolved = [
        store
        for store in stores
        if store.get("tcgplayer", {}).get("seller_key")
        and store.get("tcgplayer", {}).get("status")
        in {"exact", "manual_verified", "normalized", "stopword"}
    ]
    listings: dict[tuple[str, str], list[dict[str, Any]]] = {}
    errors: dict[tuple[str, str], str] = {}

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {}
        for store in resolved:
            seller = store["tcgplayer"]
            for card in cards:
                future = executor.submit(
                    listings_for_card,
                    public_client,
                    str(seller["seller_name"] or store["name"]),
                    str(seller["seller_key"]),
                    card,
                )
                futures[future] = (str(store["wizards_store_id"]), card)
        for future in as_completed(futures):
            key = futures[future]
            try:
                listings[key] = future.result()
            except TCGPlayerPublicError as exc:
                errors[key] = str(exc)

    results = []
    for store in resolved:
        store_id = str(store["wizards_store_id"])
        cheapest = []
        store_errors = []
        for card in cards:
            matches = listings.get((store_id, card), [])
            if matches:
                cheapest.append(
                    min(
                        matches,
                        key=lambda item: (
                            item["card_price"],
                            item["shipping_price"],
                        ),
                    )
                )
            if (store_id, card) in errors:
                store_errors.append(f"{card}: {errors[(store_id, card)]}")
        results.append(
            {
                "wizards_store_id": store_id,
                "store_name": store["name"],
                "address": store.get("address"),
                "distance_miles": store["distance_miles"],
                "seller_name": store["tcgplayer"]["seller_name"],
                "seller_key": store["tcgplayer"]["seller_key"],
                "seller_match": store["tcgplayer"]["status"],
                "wanted_count": len(cards),
                "found_count": len(cheapest),
                "card_subtotal": round(
                    sum(item["card_price"] for item in cheapest), 2
                ),
                "cheapest_listings": cheapest,
                "inventory_errors": store_errors,
            }
        )
    return sorted(
        results,
        key=lambda result: (
            -result["found_count"],
            result["card_subtotal"],
            result["distance_miles"],
            result["store_name"].casefold(),
        ),
    )


def _render(results: list[dict[str, Any]]) -> str:
    if not results:
        return "No resolved TCGplayer sellers found."
    headers = [
        "Store",
        "Distance",
        "Coverage",
        "Subtotal",
        "Wanted card",
        "Set",
        "Condition",
        "Finish",
        "Qty",
        "Price",
        "Shipping",
    ]
    rows = []
    for result in results:
        matches = result["cheapest_listings"] or [None]
        for match in matches:
            rows.append(
                [
                    str(result["store_name"]),
                    f"{result['distance_miles']:.2f} mi",
                    f"{result['found_count']}/{result['wanted_count']}",
                    f"${result['card_subtotal']:.2f}",
                    str(match["wanted"] if match else ""),
                    str((match or {}).get("set") or ""),
                    str((match or {}).get("condition") or ""),
                    str((match or {}).get("finish") or ""),
                    str((match or {}).get("quantity") or ""),
                    f"${match['card_price']:.2f}" if match else "",
                    f"${match['shipping_price']:.2f}" if match else "",
                ]
            )
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
    inventory_errors = [
        f"{result['store_name']}: {error}"
        for result in results
        for error in result["inventory_errors"]
    ]
    if inventory_errors:
        lines.extend(["", "Inventory request errors:", *inventory_errors])
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
