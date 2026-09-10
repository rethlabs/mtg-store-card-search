from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Area:
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None

    def __post_init__(self) -> None:
        if not self.city and not self.zip_code:
            raise ValueError("An area requires a city or ZIP code")

    @property
    def label(self) -> str:
        place = self.city or self.zip_code or "Unknown"
        return f"{place}, {self.state}" if self.state else place

    def query(self) -> dict[str, str]:
        result: dict[str, str] = {}
        if self.city:
            result["city"] = self.city
        if self.state:
            result["state"] = self.state
        if self.zip_code:
            result["zipCode"] = self.zip_code
        return result


@dataclass(frozen=True)
class CardWanted:
    name: str
    set_name: str | None = None
    number: str | None = None
    condition: str | None = None
    language: str | None = "English"
    finish: str = "any"

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Card name cannot be empty")
        if self.finish not in {"any", "foil", "nonfoil"}:
            raise ValueError("finish must be any, foil, or nonfoil")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CardWanted":
        return cls(
            name=str(value["name"]).strip(),
            set_name=_optional_text(value.get("set")),
            number=_optional_text(value.get("number")),
            condition=_optional_text(value.get("condition")),
            language=_optional_text(value.get("language", "English")),
            finish=str(value.get("finish", "any")).lower(),
        )


@dataclass(frozen=True)
class Store:
    key: str
    name: str
    areas: tuple[str, ...] = ()
    storefront_url: str | None = None


@dataclass(frozen=True)
class Listing:
    store: Store
    wanted: CardWanted
    product_id: int | None
    product_name: str
    set_name: str | None
    number: str | None
    sku_id: int | None
    condition: str | None
    language: str | None
    foil: bool
    price: float
    quantity: int


@dataclass
class StoreResult:
    store: Store
    wanted_count: int
    listings: list[Listing] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def cheapest_by_card(self) -> dict[str, Listing]:
        cheapest: dict[str, Listing] = {}
        for listing in self.listings:
            key = listing.wanted.name.casefold()
            if key not in cheapest or listing.price < cheapest[key].price:
                cheapest[key] = listing
        return cheapest

    @property
    def found_count(self) -> int:
        return len(self.cheapest_by_card)

    @property
    def total_price(self) -> float:
        return sum(item.price for item in self.cheapest_by_card.values())


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
