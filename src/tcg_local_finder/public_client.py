from __future__ import annotations

import json
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class TCGPlayerPublicError(RuntimeError):
    """Raised when TCGplayer's public storefront search fails."""


class TCGPlayerPublicClient:
    """Read public seller inventory without account credentials."""

    def __init__(
        self,
        *,
        search_url: str = "https://mp-search-api.tcgplayer.com/v1/search/request",
        timeout: float = 20.0,
        retry_delays: tuple[float, ...] = (60.0, 180.0),
        min_request_interval: float = 0.5,
    ) -> None:
        self.search_url = search_url
        self.timeout = timeout
        self.retry_delays = retry_delays
        self.min_request_interval = min_request_interval
        self._request_lock = threading.Lock()
        self._next_request_time = 0.0

    def search_store_inventory(
        self,
        seller_key: str,
        card_name: str,
        *,
        page_size: int = 24,
    ) -> list[dict[str, Any]]:
        if not seller_key.strip():
            raise ValueError("seller_key cannot be empty")
        if not card_name.strip():
            raise ValueError("card_name cannot be empty")

        products: list[dict[str, Any]] = []
        offset = 0
        while True:
            payload = self._search_page(
                seller_key.strip(), card_name.strip(), offset=offset, size=page_size
            )
            errors = payload.get("errors") or []
            if errors:
                raise TCGPlayerPublicError("; ".join(str(error) for error in errors))

            result_sets = payload.get("results") or []
            if not result_sets:
                break
            result_set = result_sets[0]
            page = result_set.get("results") or []
            products.extend(page)
            total = int(result_set.get("totalResults") or len(products))
            if not page or len(products) >= total:
                break
            offset += len(page)
        return products

    def _search_page(
        self,
        seller_key: str,
        card_name: str,
        *,
        offset: int,
        size: int,
    ) -> dict[str, Any]:
        query = urlencode({"q": card_name, "isList": "false"})
        body = {
            "algorithm": "sales_exp_fields_experiment",
            "from": offset,
            "size": size,
            "filters": {"term": {}, "range": {}, "match": {}},
            "listingSearch": {
                "context": {"cart": {}},
                "filters": {
                    "term": {
                        "sellerStatus": "Live",
                        "channelId": 0,
                        "sellerKey": [seller_key],
                    },
                    "range": {"quantity": {"gte": 1}},
                    "exclude": {"channelExclusion": 0},
                },
            },
            "context": {"shippingCountry": "US", "cart": {}, "userProfile": {}},
            "settings": {"useFuzzySearch": True},
            "sort": {"field": "market-price", "order": "asc"},
        }
        request = Request(
            f"{self.search_url}?{query}",
            data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": "https://www.tcgplayer.com",
                "Referer": "https://www.tcgplayer.com/",
                "User-Agent": "mtg-store-card-search/0.1.0",
            },
            method="POST",
        )
        return self._send(request)

    def _send(self, request: Request) -> dict[str, Any]:
        for attempt in range(len(self.retry_delays) + 1):
            try:
                self._wait_for_request_slot()
                with urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code == 429 or 500 <= exc.code < 600:
                    if attempt < len(self.retry_delays):
                        time.sleep(self.retry_delays[attempt])
                        continue
                raise TCGPlayerPublicError(
                    f"TCGplayer storefront HTTP {exc.code}: {body}"
                ) from exc
            except (URLError, TimeoutError) as exc:
                if attempt < len(self.retry_delays):
                    time.sleep(self.retry_delays[attempt])
                    continue
                raise TCGPlayerPublicError(
                    f"Unable to reach the TCGplayer storefront: {exc}"
                ) from exc
            except json.JSONDecodeError as exc:
                raise TCGPlayerPublicError(
                    "TCGplayer storefront returned invalid JSON"
                ) from exc
        raise TCGPlayerPublicError("TCGplayer storefront request failed")

    def _wait_for_request_slot(self) -> None:
        with self._request_lock:
            now = time.monotonic()
            wait = self._next_request_time - now
            if wait > 0:
                time.sleep(wait)
            self._next_request_time = (
                max(now, self._next_request_time) + self.min_request_interval
            )
