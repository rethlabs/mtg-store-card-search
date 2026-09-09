from __future__ import annotations

import json
import os
import time
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class TCGPlayerError(RuntimeError):
    """Raised when TCGplayer returns an unsuccessful response."""


class TCGPlayerAuthError(TCGPlayerError):
    """Raised when credentials are missing or rejected."""


class TCGPlayerClient:
    def __init__(
        self,
        public_key: str,
        private_key: str,
        *,
        access_token: str | None = None,
        api_base: str = "https://api.tcgplayer.com/v1.39.0",
        token_url: str = "https://api.tcgplayer.com/token",
        timeout: float = 20.0,
        retries: int = 3,
    ) -> None:
        if not public_key or not private_key:
            raise TCGPlayerAuthError(
                "TCGPLAYER_PUBLIC_KEY and TCGPLAYER_PRIVATE_KEY are required"
            )
        self.public_key = public_key
        self.private_key = private_key
        self.access_token = access_token
        self.api_base = api_base.rstrip("/")
        self.token_url = token_url
        self.timeout = timeout
        self.retries = retries
        self._bearer_token: str | None = None

    @classmethod
    def from_environment(cls) -> "TCGPlayerClient":
        return cls(
            os.getenv("TCGPLAYER_PUBLIC_KEY", ""),
            os.getenv("TCGPLAYER_PRIVATE_KEY", ""),
            access_token=os.getenv("TCGPLAYER_ACCESS_TOKEN"),
            api_base=os.getenv(
                "TCGPLAYER_API_BASE", "https://api.tcgplayer.com/v1.39.0"
            ),
            token_url=os.getenv("TCGPLAYER_TOKEN_URL", "https://api.tcgplayer.com/token"),
        )

    def authenticate(self) -> str:
        form = urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self.public_key,
                "client_secret": self.private_key,
            }
        ).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        if self.access_token:
            headers["X-Tcg-Access-Token"] = self.access_token
        payload = self._send(Request(self.token_url, data=form, headers=headers))
        token = payload.get("access_token")
        if not token:
            raise TCGPlayerAuthError("TCGplayer did not return an access_token")
        self._bearer_token = str(token)
        return self._bearer_token

    def search_stores(self, **filters: str) -> list[str]:
        return self._paged_get("/stores", filters)

    def get_store_info(self, store_keys: Iterable[str]) -> list[dict[str, Any]]:
        keys = list(dict.fromkeys(store_keys))
        results: list[dict[str, Any]] = []
        for start in range(0, len(keys), 50):
            joined = ",".join(keys[start : start + 50])
            payload = self._get(f"/stores/{joined}")
            results.extend(payload.get("results", []))
        return results

    def get_store_inventory(
        self,
        store_key: str,
        product_name: str,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self._paged_get(
            f"/stores/{store_key}/inventory/products",
            {
                "categoryName": "Magic",
                "productName": product_name,
                "skuLimit": "50",
                "includeGeneric": "true",
                "includeCustom": "true",
            },
            page_size=min(limit, 100),
            max_items=limit,
        )

    def _paged_get(
        self,
        path: str,
        params: dict[str, str],
        *,
        page_size: int = 100,
        max_items: int | None = None,
    ) -> list[Any]:
        offset = 0
        results: list[Any] = []
        while True:
            query = dict(params)
            query.update({"offset": str(offset), "limit": str(page_size)})
            payload = self._get(path, query)
            page = payload.get("results", [])
            results.extend(page)
            total = int(payload.get("totalItems", len(results)))
            if not page or len(results) >= total:
                break
            if max_items is not None and len(results) >= max_items:
                break
            offset += len(page)
        return results[:max_items] if max_items is not None else results

    def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        if not self._bearer_token:
            self.authenticate()
        url = f"{self.api_base}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"bearer {self._bearer_token}",
                "User-Agent": "tcg-local-finder/0.1.0",
            },
        )
        payload = self._send(request)
        if not payload.get("success", True):
            raise TCGPlayerError("; ".join(payload.get("errors", ["API request failed"])))
        return payload

    def _send(self, request: Request) -> dict[str, Any]:
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code == 401:
                    raise TCGPlayerAuthError(
                        f"TCGplayer rejected the credentials (HTTP 401): {body}"
                    ) from exc
                if exc.code == 429 or 500 <= exc.code < 600:
                    if attempt < self.retries:
                        time.sleep(0.5 * (2**attempt))
                        continue
                raise TCGPlayerError(f"TCGplayer HTTP {exc.code}: {body}") from exc
            except (URLError, TimeoutError) as exc:
                if attempt < self.retries:
                    time.sleep(0.5 * (2**attempt))
                    continue
                raise TCGPlayerError(f"Unable to reach TCGplayer: {exc}") from exc
        raise TCGPlayerError("TCGplayer request failed")

