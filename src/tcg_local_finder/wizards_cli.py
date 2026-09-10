from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Sequence

from .public_client import TCGPlayerPublicClient, TCGPlayerPublicError
from .seller_resolution import resolve_seller
from .wizards_client import WizardsLocatorClient, WizardsLocatorError

LOGGER = logging.getLogger(__name__)


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
    parser.add_argument(
        "--triage-file",
        default="tcgplayer-resolution-triage.jsonl",
        help="Write unresolved TCGplayer matches here (default: %(default)s)",
    )
    parser.add_argument("--workers", type=int, default=4, help="Concurrent searches")
    parser.add_argument(
        "--resolve-tcgplayer",
        action="store_true",
        help="Find an exact TCGplayer seller match for each Wizards store",
    )
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
        if args.resolve_tcgplayer:
            _resolve_tcgplayer_sellers(stores, workers=args.workers)
            _write_triage_file(stores, args.triage_file)
        if args.format == "json":
            print(json.dumps(stores, indent=2))
        else:
            print(_render(stores))
        return 0
    except (TCGPlayerPublicError, WizardsLocatorError, ValueError) as exc:
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


def _resolve_tcgplayer_sellers(
    stores: list[dict[str, Any]],
    *,
    workers: int,
) -> None:
    client = TCGPlayerPublicClient()
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        matches = executor.map(
            lambda store: _safe_resolve_seller(client, str(store["name"])), stores
        )
        for store, match in zip(stores, matches):
            store["tcgplayer"] = match


def _safe_resolve_seller(
    client: TCGPlayerPublicClient,
    store_name: str,
) -> dict[str, Any]:
    try:
        return resolve_seller(client, store_name)
    except TCGPlayerPublicError as exc:
        return {
            "status": "error",
            "seller_key": None,
            "seller_name": None,
            "seller_location": None,
            "seller_url": None,
            "candidate_count": 0,
            "error": str(exc),
        }


def _write_triage_file(stores: list[dict[str, Any]], path: str) -> None:
    unresolved = [
        store
        for store in stores
        if store.get("tcgplayer", {}).get("status")
        not in {"exact", "normalized", "stopword"}
    ]
    records = []
    for store in unresolved:
        match = store["tcgplayer"]
        LOGGER.warning(
            "TCGplayer seller unresolved for %s (%s)",
            store["name"],
            match["status"],
        )
        records.append(
            {
                "wizards_store_id": store["wizards_store_id"],
                "store_name": store["name"],
                "address": store.get("address"),
                "status": match["status"],
                "attempted_queries": match.get("attempted_queries", []),
                "candidates": match.get("candidates", []),
                "error": match.get("error"),
            }
        )
    with open(path, "w", encoding="utf-8") as triage_file:
        for record in records:
            triage_file.write(json.dumps(record, sort_keys=True) + "\n")


def _render(stores: list[dict[str, Any]]) -> str:
    if not stores:
        return "No Wizards stores found."
    show_tcgplayer = any("tcgplayer" in store for store in stores)
    headers = ["Store", "Address", "Distance", "Wizards ID", "Matched area"]
    if show_tcgplayer:
        headers.extend(["TCG match", "Seller key"])
    rows = [
        [
            str(store["name"]),
            str(store["address"] or ""),
            f"{store['distance_miles']:.2f} mi",
            str(store["wizards_store_id"]),
            ", ".join(store["matched_areas"]),
        ]
        + (
            [
                str(store["tcgplayer"]["status"]),
                str(store["tcgplayer"]["seller_key"] or ""),
            ]
            if show_tcgplayer
            else []
        )
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
