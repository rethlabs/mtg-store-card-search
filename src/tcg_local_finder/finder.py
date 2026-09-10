from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterable

from .models import Area, CardWanted, Listing, Store, StoreResult


def find_stores(client: Any, areas: Iterable[Area]) -> list[Store]:
    area_by_key: dict[str, set[str]] = defaultdict(set)
    for area in areas:
        for key in client.search_stores(**area.query()):
            area_by_key[str(key)].add(area.label)

    keys = sorted(area_by_key)
    info_by_key = {
        str(item.get("storeKey")): item for item in client.get_store_info(keys)
    }
    stores: list[Store] = []
    for key in keys:
        info = info_by_key.get(key, {})
        stores.append(
            Store(
                key=key,
                name=str(info.get("name") or info.get("displayName") or key),
                areas=tuple(sorted(area_by_key[key])),
                storefront_url=info.get("storefrontUrl"),
            )
        )
    return sorted(stores, key=lambda store: store.name.casefold())


def find_cards(
    client: Any,
    stores: Iterable[Store],
    wanted_cards: Iterable[CardWanted],
    *,
    workers: int = 4,
) -> list[StoreResult]:
    store_list = list(stores)
    wanted_list = list(wanted_cards)
    listings_by_store: dict[str, list[Listing]] = defaultdict(list)
    errors_by_store: dict[str, list[str]] = defaultdict(list)

    def lookup(store: Store, wanted: CardWanted) -> list[Listing]:
        products = client.get_store_inventory(store.key, wanted.name)
        return _matching_listings(store, wanted, products)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(lookup, store, wanted): (store, wanted)
            for store in store_list
            for wanted in wanted_list
        }
        for future in as_completed(futures):
            store, wanted = futures[future]
            try:
                listings_by_store[store.key].extend(future.result())
            except Exception as exc:
                errors_by_store[store.key].append(f"{wanted.name}: {exc}")

    results = [
        StoreResult(
            store=store,
            wanted_count=len(wanted_list),
            listings=listings_by_store.get(store.key, []),
            errors=errors_by_store.get(store.key, []),
        )
        for store in store_list
    ]
    return sorted(
        results,
        key=lambda result: (
            -result.found_count,
            result.total_price,
            result.store.name.casefold(),
        ),
    )


def _matching_listings(
    store: Store,
    wanted: CardWanted,
    products: Iterable[dict[str, Any]],
) -> list[Listing]:
    listings: list[Listing] = []
    for product in products:
        product_name = str(product.get("name", ""))
        if not _matches_card_name(product_name, wanted.name):
            continue
        if wanted.set_name and not _same(product.get("group"), wanted.set_name):
            continue
        if wanted.number and not _same(product.get("number"), wanted.number):
            continue
        for sku in product.get("skus") or []:
            quantity = int(sku.get("quantity") or 0)
            if quantity <= 0:
                continue
            condition = _nested_name(sku, "condition")
            language = _nested_name(sku, "language")
            foil = bool(sku.get("foil"))
            if wanted.condition and not _same(condition, wanted.condition):
                continue
            if wanted.language and not _same(language, wanted.language):
                continue
            if wanted.finish == "foil" and not foil:
                continue
            if wanted.finish == "nonfoil" and foil:
                continue
            listings.append(
                Listing(
                    store=store,
                    wanted=wanted,
                    product_id=_optional_int(product.get("productId")),
                    product_name=product_name,
                    set_name=_optional_str(product.get("group")),
                    number=_optional_str(product.get("number")),
                    sku_id=_optional_int(sku.get("skuId")),
                    condition=condition,
                    language=language,
                    foil=foil,
                    price=float(sku.get("price") or 0),
                    quantity=quantity,
                )
            )
    return sorted(listings, key=lambda listing: listing.price)


def _matches_card_name(product_name: str, wanted_name: str) -> bool:
    product = " ".join(product_name.casefold().split())
    wanted = " ".join(wanted_name.casefold().split())
    return product == wanted or product.startswith(f"{wanted} //")


def _same(left: Any, right: Any) -> bool:
    return str(left or "").strip().casefold() == str(right or "").strip().casefold()


def _nested_name(value: dict[str, Any], key: str) -> str | None:
    nested = value.get(key) or {}
    return _optional_str(nested.get("name"))


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)
