from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Any, Sequence

from .store_registry import (
    DEFAULT_EXCLUSIONS_PATH,
    DEFAULT_REGISTRY_PATH,
    entry_is_due,
    load_exclusions,
    load_registry,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mtg-store-registry",
        description="Inspect the local-store classification registry.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit = subparsers.add_parser("audit", help="Report registry entries due for review")
    audit.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    audit.add_argument("--exclusions", type=Path, default=DEFAULT_EXCLUSIONS_PATH)
    audit.add_argument(
        "--stale-days",
        type=int,
        help="Override status-specific review intervals",
    )
    audit.add_argument(
        "--recheck-all-stores",
        action="store_true",
        help="Mark every registry and exclusion entry due",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.stale_days is not None and args.stale_days < 0:
            raise ValueError("--stale-days cannot be negative")
        registry = load_registry(args.registry)
        exclusions = load_exclusions(args.exclusions)
        print(
            render_audit(
                registry,
                exclusions,
                stale_days=args.stale_days,
                recheck_all=args.recheck_all_stores,
            )
        )
        return 0
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def render_audit(
    registry: dict[str, Any],
    exclusions: dict[str, Any],
    *,
    stale_days: int | None = None,
    recheck_all: bool = False,
    today: date | None = None,
) -> str:
    rows = []
    for entry in registry["stores"]:
        due = entry_is_due(
            entry,
            today=today,
            stale_days=stale_days,
            recheck_all=recheck_all,
        )
        rows.append(
            [
                str(entry["store_name"]),
                str(entry.get("singles_status") or "unknown"),
                str(entry.get("tcgplayer_status") or "unknown"),
                str(entry.get("last_checked") or "never"),
                "yes" if due else "no",
            ]
        )
    if recheck_all:
        for rule in exclusions.get("exact_names") or []:
            rows.append([str(rule["name"]), "excluded", "excluded", "never", "yes"])
        for rule in exclusions.get("name_prefixes") or []:
            rows.append(
                [f"{rule['prefix']}*", "excluded", "excluded", "never", "yes"]
            )
    rows.sort(key=lambda row: (row[4] != "yes", row[0].casefold()))
    headers = ["Store", "Singles", "TCGplayer", "Last checked", "Due"]
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
