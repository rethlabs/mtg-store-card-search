from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from .public_client import TCGPlayerPublicClient


def normalize_seller_name(value: str) -> str:
    normalized = (
        value.casefold().replace("'", "").replace("’", "").replace("&", " and ")
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", normalized).split())


def resolve_seller(
    client: TCGPlayerPublicClient,
    store_name: str,
) -> dict[str, Any]:
    candidates = client.search_sellers(store_name)
    target = normalize_seller_name(store_name)
    exact = [
        candidate
        for candidate in candidates
        if normalize_seller_name(str(candidate.get("displayName") or "")) == target
    ]

    if len(exact) == 1:
        candidate = exact[0]
        key = str(candidate.get("sellerKey") or "")
        return {
            "status": "exact",
            "seller_key": key,
            "seller_name": candidate.get("displayName"),
            "seller_location": candidate.get("location"),
            "seller_url": seller_url(candidate),
            "candidate_count": len(candidates),
        }
    return {
        "status": "ambiguous" if exact else "not_found",
        "seller_key": None,
        "seller_name": None,
        "seller_location": None,
        "seller_url": None,
        "candidate_count": len(candidates),
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


def seller_url(candidate: dict[str, Any]) -> str | None:
    key = str(candidate.get("sellerKey") or "").strip()
    name = str(candidate.get("displayName") or "").strip()
    if not key or not name:
        return None
    slug = quote(name.replace(" ", "-"), safe="-")
    return f"https://www.tcgplayer.com/sellers/{slug}/{key}"
