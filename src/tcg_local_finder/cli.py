from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .client import TCGPlayerClient, TCGPlayerError
from .finder import find_cards, find_stores
from .models import Area, CardWanted, StoreResult


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tcg-local",
        description="Find wanted MTG cards in TCGplayer store inventories.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Verify API credentials")
    doctor.set_defaults(handler=_doctor)

    stores = subparsers.add_parser("stores", help="List stores in desired areas")
    _add_area_arguments(stores)
    stores.add_argument("--format", choices=("table", "json"), default="table")
    stores.set_defaults(handler=_stores)

    find = subparsers.add_parser("find", help="Search local store inventories")
    _add_area_arguments(find)
    find.add_argument("--card", action="append", default=[], help="Card name; repeatable")
    find.add_argument("--cards-file", type=Path, help="One card name per line")
    find.add_argument(
        "--request",
        type=Path,
        help="JSON request with areas and cards, including optional printing filters",
    )
    find.add_argument("--workers", type=int, default=4, help="Concurrent API requests")
    find.add_argument("--format", choices=("table", "json", "csv"), default="table")
    find.add_argument("--include-empty", action="store_true")
    find.set_defaults(handler=_find)
    return parser


def _add_area_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--city", action="append", default=[], help="City; repeatable")
    parser.add_argument("--zip", dest="zip_codes", action="append", default=[], help="ZIP code; repeatable")
    parser.add_argument("--state", default="TX", help="Two-letter state code (default: TX)")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (TCGPlayerError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _doctor(_args: argparse.Namespace) -> int:
    client = TCGPlayerClient.from_environment()
    client.authenticate()
    print("TCGplayer authentication succeeded.")
    return 0


def _stores(args: argparse.Namespace) -> int:
    areas = _areas_from_args(args)
    client = TCGPlayerClient.from_environment()
    stores = find_stores(client, areas)
    if args.format == "json":
        print(json.dumps([_store_dict(store) for store in stores], indent=2))
    else:
        rows = [
            [store.name, ", ".join(store.areas), store.key, store.storefront_url or ""]
            for store in stores
        ]
        print(_table(["Store", "Matched area", "Store key", "Storefront"], rows))
    return 0


def _find(args: argparse.Namespace) -> int:
    if args.request:
        areas, cards = _load_request(args.request)
    else:
        areas = _areas_from_args(args)
        cards = [CardWanted(name=name) for name in args.card]
        if args.cards_file:
            cards.extend(
                CardWanted(name=line.strip())
                for line in args.cards_file.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            )
    if not cards:
        raise ValueError("Provide --card, --cards-file, or --request")

    client = TCGPlayerClient.from_environment()
    stores = find_stores(client, areas)
    results = find_cards(client, stores, cards, workers=args.workers)
    if not args.include_empty:
        results = [result for result in results if result.found_count or result.errors]

    if args.format == "json":
        print(json.dumps(_results_dict(results), indent=2))
    elif args.format == "csv":
        _write_csv(results)
    else:
        print(_render_results(results))
    return 0


def _areas_from_args(args: argparse.Namespace) -> list[Area]:
    areas = [Area(city=city, state=args.state) for city in args.city]
    areas.extend(Area(zip_code=code, state=args.state) for code in args.zip_codes)
    if not areas:
        raise ValueError("Provide at least one --city, --zip, or --request")
    return areas


def _load_request(path: Path) -> tuple[list[Area], list[CardWanted]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    areas = [
        Area(
            city=item.get("city"),
            state=item.get("state"),
            zip_code=item.get("zip_code") or item.get("zipCode"),
        )
        for item in payload.get("areas", [])
    ]
    cards = [CardWanted.from_dict(item) for item in payload.get("cards", [])]
    if not areas or not cards:
        raise ValueError("Request JSON requires non-empty areas and cards arrays")
    return areas, cards


def _render_results(results: list[StoreResult]) -> str:
    if not results:
        return "No matching in-stock cards found."
    rows: list[list[str]] = []
    for result in results:
        cheapest = result.cheapest_by_card
        card_text = "; ".join(
            f"{listing.wanted.name} ${listing.price:.2f}"
            for listing in cheapest.values()
        )
        rows.append(
            [
                result.store.name,
                ", ".join(result.store.areas),
                f"{result.found_count}/{result.wanted_count}",
                f"${result.total_price:.2f}",
                card_text,
                str(len(result.errors)) if result.errors else "",
            ]
        )
    rendered = _table(
        ["Store", "Area", "Found", "Total", "Cheapest matches", "Errors"], rows
    )
    failures = [
        f"{result.store.name}: {message}"
        for result in results
        for message in result.errors
    ]
    if failures:
        rendered += "\n\nInventory request errors:\n- " + "\n- ".join(failures)
    return rendered


def _results_dict(results: list[StoreResult]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for result in results:
        listings = []
        for listing in result.listings:
            listings.append(
                {
                    "wanted": listing.wanted.name,
                    "product_name": listing.product_name,
                    "set": listing.set_name,
                    "number": listing.number,
                    "condition": listing.condition,
                    "language": listing.language,
                    "finish": "foil" if listing.foil else "nonfoil",
                    "price": listing.price,
                    "quantity": listing.quantity,
                    "product_id": listing.product_id,
                    "sku_id": listing.sku_id,
                }
            )
        output.append(
            {
                "store": _store_dict(result.store),
                "found_count": result.found_count,
                "wanted_count": result.wanted_count,
                "cheapest_total": result.total_price,
                "listings": listings,
                "errors": result.errors,
            }
        )
    return output


def _write_csv(results: list[StoreResult]) -> None:
    writer = csv.writer(sys.stdout)
    writer.writerow(
        [
            "store",
            "areas",
            "wanted",
            "product_name",
            "set",
            "number",
            "condition",
            "language",
            "finish",
            "price",
            "quantity",
            "storefront_url",
        ]
    )
    for result in results:
        for listing in result.listings:
            writer.writerow(
                [
                    result.store.name,
                    " | ".join(result.store.areas),
                    listing.wanted.name,
                    listing.product_name,
                    listing.set_name or "",
                    listing.number or "",
                    listing.condition or "",
                    listing.language or "",
                    "foil" if listing.foil else "nonfoil",
                    f"{listing.price:.2f}",
                    listing.quantity,
                    result.store.storefront_url or "",
                ]
            )


def _store_dict(store: Any) -> dict[str, Any]:
    return {
        "key": store.key,
        "name": store.name,
        "areas": list(store.areas),
        "storefront_url": store.storefront_url,
    }


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "No results."
    widths = [len(header) for header in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(str(value)))
    line = "-+-".join("-" * width for width in widths)
    output = [
        " | ".join(header.ljust(widths[index]) for index, header in enumerate(headers)),
        line,
    ]
    output.extend(
        " | ".join(str(value).ljust(widths[index]) for index, value in enumerate(row))
        for row in rows
    )
    return "\n".join(output)


if __name__ == "__main__":
    raise SystemExit(main())
