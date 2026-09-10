from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from .seller_resolution import normalize_seller_name

DEFAULT_REGISTRY_PATH = Path("store-registry.json")
DEFAULT_EXCLUSIONS_PATH = Path("store-exclusions.json")

RECHECK_DAYS = {
    "unknown": 30,
    "candidate": 30,
    "physical_only": 90,
    "does_not_sell_singles": 90,
}
TRUSTED_STATUSES = {"automatic", "manual_verified"}


def load_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def load_registry(path: Path = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
    registry = load_json_object(path)
    if registry.get("schema_version") != 1:
        raise ValueError(f"Unsupported registry schema in {path}")
    if not isinstance(registry.get("stores"), list):
        raise ValueError(f"{path} must contain a stores list")
    return registry


def load_exclusions(path: Path = DEFAULT_EXCLUSIONS_PATH) -> dict[str, Any]:
    exclusions = load_json_object(path)
    if exclusions.get("schema_version") != 1:
        raise ValueError(f"Unsupported exclusions schema in {path}")
    return exclusions


def registry_by_name(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        normalize_seller_name(str(entry["store_name"])): entry
        for entry in registry["stores"]
    }


def exclusion_reason(store_name: str, exclusions: dict[str, Any]) -> str | None:
    target = normalize_seller_name(store_name)
    for rule in exclusions.get("exact_names") or []:
        if normalize_seller_name(str(rule.get("name") or "")) == target:
            return str(rule.get("reason") or "configured exclusion")
    for rule in exclusions.get("name_prefixes") or []:
        prefix = normalize_seller_name(str(rule.get("prefix") or ""))
        if prefix and target.startswith(prefix):
            return str(rule.get("reason") or "configured exclusion")
    return None


def entry_is_due(
    entry: dict[str, Any],
    *,
    today: date | None = None,
    stale_days: int | None = None,
    recheck_all: bool = False,
) -> bool:
    status = str(entry.get("tcgplayer_status") or "unknown")
    if status == "manual_verified" and not entry.get("last_error"):
        return False
    if recheck_all:
        return True
    if status in TRUSTED_STATUSES and not entry.get("last_error"):
        return False
    threshold = stale_days if stale_days is not None else RECHECK_DAYS.get(status, 30)
    checked = entry.get("last_checked")
    if not checked:
        return True
    checked_date = date.fromisoformat(str(checked))
    return ((today or date.today()) - checked_date).days >= threshold


def apply_store_registry(
    stores: list[dict[str, Any]],
    registry: dict[str, Any],
    exclusions: dict[str, Any],
    *,
    recheck_all: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    entries = registry_by_name(registry)
    included = []
    excluded = []
    for store in stores:
        reason = exclusion_reason(str(store["name"]), exclusions)
        if reason and not recheck_all:
            excluded.append({**store, "exclusion_reason": reason})
            continue
        entry = entries.get(normalize_seller_name(str(store["name"])))
        store["registry"] = entry
        if entry and entry.get("tcgplayer_status") == "manual_verified":
            store["tcgplayer"] = {
                "status": "manual_verified",
                "seller_key": entry.get("seller_key"),
                "seller_name": entry.get("seller_name"),
                "seller_location": entry.get("seller_location"),
                "seller_url": entry.get("seller_url"),
                "candidate_count": 1,
            }
        included.append(store)
    return included, excluded


def stores_requiring_resolution(
    stores: list[dict[str, Any]],
    *,
    recheck_all: bool = False,
) -> list[dict[str, Any]]:
    required = []
    for store in stores:
        tcgplayer = store.get("tcgplayer", {})
        if tcgplayer.get("seller_key") and (
            not recheck_all or tcgplayer.get("status") == "manual_verified"
        ):
            continue
        entry = store.get("registry")
        if entry and not entry_is_due(entry, recheck_all=recheck_all):
            store["tcgplayer"] = {
                "status": entry.get("tcgplayer_status"),
                "seller_key": None,
                "seller_name": entry.get("seller_name"),
                "seller_location": entry.get("seller_location"),
                "seller_url": entry.get("seller_url"),
                "candidate_count": 0,
            }
            continue
        required.append(store)
    return required
