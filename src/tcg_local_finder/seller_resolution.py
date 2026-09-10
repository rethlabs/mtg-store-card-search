from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from .public_client import TCGPlayerPublicClient

STOP_WORDS = frozenset({"a", "an", "as", "of", "the"})


def normalize_seller_name(value: str, *, remove_stop_words: bool = False) -> str:
    normalized = (
        value.casefold().replace("'", "").replace("’", "").replace("&", " and ")
    )
    words = re.sub(r"[^a-z0-9]+", " ", normalized).split()
    if remove_stop_words:
        words = [word for word in words if word not in STOP_WORDS]
    return " ".join(words)


def resolve_seller(
    client: TCGPlayerPublicClient,
    store_name: str,
) -> dict[str, Any]:
    candidates = client.search_sellers(store_name)
    attempted_queries = [store_name]
    match = _match_candidate_names(
        store_name,
        [str(candidate.get("displayName") or "") for candidate in candidates],
    )

    if match is None and not candidates:
        suggested_names, prefix_queries = _progressive_suggestions(client, store_name)
        attempted_queries.extend(prefix_queries)
        match = _match_candidate_names(store_name, suggested_names)
        if match is not None and match[1] is not None:
            match_status, matched_name = match
            assert matched_name is not None
            candidates = client.search_sellers(matched_name)
            attempted_queries.append(matched_name)
            matching_sellers = [
                candidate
                for candidate in candidates
                if str(candidate.get("displayName") or "") == matched_name
            ]
            if len(matching_sellers) == 1:
                return _resolved_result(
                    matching_sellers[0],
                    match_status,
                    len(suggested_names),
                    attempted_queries,
                )
            match = None
        if not candidates:
            candidates = [{"displayName": name} for name in suggested_names]

    if match is not None and match[1] is not None:
        match_status, matched_name = match
        assert matched_name is not None
        matching_sellers = [
            candidate
            for candidate in candidates
            if str(candidate.get("displayName") or "") == matched_name
        ]
        if len(matching_sellers) == 1:
            return _resolved_result(
                matching_sellers[0], match_status, len(candidates), attempted_queries
            )
    return {
        "status": (
            "ambiguous" if match is not None and match[0] == "ambiguous" else "not_found"
        ),
        "seller_key": None,
        "seller_name": None,
        "seller_location": None,
        "seller_url": None,
        "candidate_count": len(candidates),
        "attempted_queries": attempted_queries,
        "candidates": [
            {
                "seller_key": candidate.get("sellerKey"),
                "seller_name": candidate.get("displayName"),
                "seller_location": candidate.get("location"),
                "seller_url": seller_url(candidate),
            }
            for candidate in candidates
        ],
    }


def _progressive_suggestions(
    client: TCGPlayerPublicClient,
    store_name: str,
) -> tuple[list[str], list[str]]:
    words = store_name.split()
    last_nonempty: list[str] = []
    attempted: list[str] = []
    for length in range(1, len(words) + 1):
        query = " ".join(words[:length])
        suggestions = client.suggest_seller_names(query)
        attempted.append(query)
        if not suggestions:
            break
        last_nonempty = suggestions
        match = _match_candidate_names(store_name, suggestions)
        if match is not None and match[1] is not None:
            break
    return last_nonempty, attempted


def _match_candidate_names(
    store_name: str,
    candidate_names: list[str],
) -> tuple[str, str | None] | None:
    comparison_passes = (
        ("exact", lambda value: value),
        ("normalized", normalize_seller_name),
        (
            "stopword",
            lambda value: normalize_seller_name(value, remove_stop_words=True),
        ),
    )
    for status, transform in comparison_passes:
        target = transform(store_name)
        matches = [name for name in candidate_names if name and transform(name) == target]
        if len(matches) == 1:
            return status, matches[0]
        if len(matches) > 1:
            return "ambiguous", None
    return None


def _resolved_result(
    candidate: dict[str, Any],
    status: str,
    candidate_count: int,
    attempted_queries: list[str],
) -> dict[str, Any]:
    return {
        "status": status,
        "seller_key": str(candidate.get("sellerKey") or ""),
        "seller_name": candidate.get("displayName"),
        "seller_location": candidate.get("location"),
        "seller_url": seller_url(candidate),
        "candidate_count": candidate_count,
        "attempted_queries": attempted_queries,
    }


def seller_url(candidate: dict[str, Any]) -> str | None:
    key = str(candidate.get("sellerKey") or "").strip()
    name = str(candidate.get("displayName") or "").strip()
    if not key or not name:
        return None
    slug = quote(name.replace(" ", "-"), safe="-")
    return f"https://www.tcgplayer.com/sellers/{slug}/{key}"
