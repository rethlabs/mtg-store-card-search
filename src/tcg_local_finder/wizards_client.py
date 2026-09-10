from __future__ import annotations

import json
import threading
import time
from http.cookiejar import CookieJar
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


class WizardsLocatorError(RuntimeError):
    """Raised when Wizards Store Locator cannot complete a search."""


class WizardsLocatorClient:
    def __init__(
        self,
        *,
        base_url: str = "https://locator.wizards.com",
        timeout: float = 20.0,
        retry_delays: tuple[float, ...] = (60.0, 180.0),
        min_request_interval: float = 0.5,
        opener: Any | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retry_delays = retry_delays
        self.min_request_interval = min_request_interval
        self._opener = opener or build_opener(HTTPCookieProcessor(CookieJar()))
        self._request_lock = threading.Lock()
        self._session_lock = threading.Lock()
        self._next_request_time = 0.0
        self._session_started = False

    def search_stores(
        self,
        location: str,
        *,
        distance_miles: int = 10,
    ) -> list[dict[str, Any]]:
        if not location.strip():
            raise ValueError("location cannot be empty")
        if distance_miles <= 0:
            raise ValueError("distance_miles must be positive")

        self._start_anonymous_session()
        query = urlencode(
            {
                "query": location.strip(),
                "searchType": "magic-events",
                "sortBy": "date",
                "sortDirection": "Asc",
                "distance": distance_miles,
                "page": 1,
                "pageSize": 10,
            }
        )
        body = self._get_text(f"{self.base_url}/search.data?{query}")
        route_data = _search_route_data(decode_wizards_data(body))
        store_result = (route_data.get("storesPins") or route_data.get("stores") or {}).get(
            "storesByLocation", {}
        )
        stores = store_result.get("stores") or []
        return sorted(stores, key=lambda store: float(store.get("distance") or 0))

    def _start_anonymous_session(self) -> None:
        if self._session_started:
            return
        with self._session_lock:
            if self._session_started:
                return
            self._get_text(f"{self.base_url}/")
            self._session_started = True

    def _get_text(self, url: str) -> str:
        request = Request(
            url,
            headers={
                "Accept": "*/*",
                "Referer": f"{self.base_url}/",
                "User-Agent": "mtg-store-card-search/0.1.0",
            },
        )
        for attempt in range(len(self.retry_delays) + 1):
            try:
                self._wait_for_request_slot()
                with self._opener.open(request, timeout=self.timeout) as response:
                    return response.read().decode("utf-8")
            except HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code == 429 or 500 <= exc.code < 600:
                    if attempt < len(self.retry_delays):
                        time.sleep(self.retry_delays[attempt])
                        continue
                raise WizardsLocatorError(
                    f"Wizards Locator HTTP {exc.code}: {body}"
                ) from exc
            except (URLError, TimeoutError) as exc:
                if attempt < len(self.retry_delays):
                    time.sleep(self.retry_delays[attempt])
                    continue
                raise WizardsLocatorError(
                    f"Unable to reach Wizards Locator: {exc}"
                ) from exc
        raise WizardsLocatorError("Wizards Locator request failed")

    def _wait_for_request_slot(self) -> None:
        with self._request_lock:
            now = time.monotonic()
            wait = self._next_request_time - now
            if wait > 0:
                time.sleep(wait)
            self._next_request_time = (
                max(now, self._next_request_time) + self.min_request_interval
            )


def decode_wizards_data(text: str) -> dict[str, Any]:
    """Decode the flattened JSON reference format returned by search.data."""
    try:
        table = json.loads(text)
    except json.JSONDecodeError as exc:
        raise WizardsLocatorError("Wizards Locator returned invalid JSON") from exc
    if not isinstance(table, list) or not table:
        raise WizardsLocatorError("Wizards Locator returned an unexpected response")

    cache: dict[int, Any] = {}

    def resolve_reference(value: Any) -> Any:
        if isinstance(value, bool):
            return value
        if not isinstance(value, int):
            return value
        if value < 0:
            return None
        if value >= len(table):
            raise WizardsLocatorError("Wizards Locator returned an invalid reference")
        return hydrate(value)

    def hydrate(index: int) -> Any:
        if index in cache:
            return cache[index]
        value = table[index]
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            cache[index] = result
            for raw_key, raw_value in value.items():
                if raw_key.startswith("_") and raw_key[1:].isdigit():
                    key = str(hydrate(int(raw_key[1:])))
                else:
                    key = raw_key
                result[key] = resolve_reference(raw_value)
            return result
        if isinstance(value, list):
            result_list: list[Any] = []
            cache[index] = result_list
            result_list.extend(resolve_reference(item) for item in value)
            return result_list
        cache[index] = value
        return value

    decoded = hydrate(0)
    if not isinstance(decoded, dict):
        raise WizardsLocatorError("Wizards Locator returned an unexpected root value")
    return decoded


def _search_route_data(decoded: dict[str, Any]) -> dict[str, Any]:
    for key, value in decoded.items():
        if key.endswith(".search") and isinstance(value, dict):
            data = value.get("data")
            if isinstance(data, dict):
                return data
    raise WizardsLocatorError("Wizards Locator response did not contain search data")
