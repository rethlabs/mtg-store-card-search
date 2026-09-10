from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Sequence

from .wizards_client import WizardsLocatorClient, WizardsLocatorError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wizards-stores",
        description="Find nearby Magic stores using Wizards Store Locator.",
    )
    parser.add_argument("--city", action="append", required=True, help="City; repeatable")
    parser.add_argument("--state", default="TX", help="State code (default: TX)")
    parser.add_argument(
        "--radius-miles", type=int, default=10, help="Search radius (default: 10)"
    )
    parser.add_argument("--workers", type=int, default=4, help="Concurrent searches")
    parser.add_argument("--format", choices=("table", "json"), default="table")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        client = WizardsLocatorClient()
        locations = [f"{city}, {args.state}" for city in args.city]
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            searches = executor.map(
                lambda location: (
                    location,
                    client.search_stores(location, distance_miles=args.radius_miles),
                ),
                locations,
            )
            results = list(searches)
        stores = _combine_stores(results)
        if args.format == "json":
            print(json.dumps(stores, indent=2))
        else:
            print(_render(stores))
        return 0
    except (WizardsLocatorError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _combine_stores(
    searches: list[tuple[str, list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    areas_by_id: dict[str, set[str]] = defaultdict(set)
    for area, stores in searches:
        for store in stores:
            store_id = str(store.get("id") or "")
            if not store_id:
                continue
            areas_by_id[store_id].add(area)
            distance_miles = float(store.get("distance") or 0) / 1609.344
            normalized = {
                "wizards_store_id": store_id,
                "name": str(store.get("name") or store_id),
                "address": store.get("postalAddress"),
                "latitude": store.get("latitude"),
                "longitude": store.get("longitude"),
                "distance_miles": distance_miles,
                "phone": store.get("phoneNumber"),
                "website": store.get("website"),
                "is_premium": bool(store.get("isPremium")),
            }
            existing = by_id.get(store_id)
            if existing is None or distance_miles < existing["distance_miles"]:
                by_id[store_id] = normalized
    for store_id, store in by_id.items():
        store["distance_miles"] = round(store["distance_miles"], 2)
        store["matched_areas"] = sorted(areas_by_id[store_id])
    return sorted(by_id.values(), key=lambda store: (store["distance_miles"], store["name"]))


def _render(stores: list[dict[str, Any]]) -> str:
    if not stores:
        return "No Wizards stores found."
    headers = ["Store", "Address", "Distance", "Wizards ID", "Matched area"]
    rows = [
        [
            str(store["name"]),
            str(store["address"] or ""),
            f"{store['distance_miles']:.2f} mi",
            str(store["wizards_store_id"]),
            ", ".join(store["matched_areas"]),
        ]
        for store in stores
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
