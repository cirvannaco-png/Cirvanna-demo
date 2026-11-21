"""Authenticated, read-only adapter for the canonical Catalog Service."""
from __future__ import annotations
from datetime import datetime, timezone
from math import isfinite
from typing import Any
import httpx
from client_security import validate_internal_service_credentials
from appearance_intelligence.contracts import CatalogProduct, CatalogSnapshot

class CatalogUnavailable(RuntimeError):
    """Canonical catalog could not provide a complete valid read."""

class CatalogClient:
    """Fetch every active product page or fail closed; never return partial data."""
    PAGE_SIZE = 100

    def __init__(self, base_url: str, read_token: str, *, timeout_seconds: float = 5.0, max_products: int = 5000, client: httpx.Client | None = None) -> None:
        normalized_url = validate_internal_service_credentials(
            base_url, read_token, service_name="catalog", token_name="CATALOG_READ_TOKEN"
        )
        if (
            not isinstance(timeout_seconds, (int, float))
            or isinstance(timeout_seconds, bool)
            or not isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be a finite positive number")
        if isinstance(max_products, bool) or not isinstance(max_products, int) or max_products < 1:
            raise ValueError("max_products must be positive")
        self.base_url, self._token = normalized_url, read_token
        self._timeout, self._max_products, self._client = float(timeout_seconds), max_products, client

    @classmethod
    def from_env(cls) -> "CatalogClient":
        import os
        return cls(os.getenv("CATALOG_BASE_URL", ""), os.getenv("CATALOG_READ_TOKEN", ""))

    def fetch_active_catalog(self, *, now: datetime | None = None) -> CatalogSnapshot:
        # Timestamp the beginning of pagination so a slow multi-page read cannot
        # make old records appear fresh merely because the final page was slow.
        snapshot_started_at = now or datetime.now(timezone.utc)
        owned = self._client is None
        client = self._client or httpx.Client(timeout=httpx.Timeout(self._timeout, connect=min(2.0, self._timeout)), trust_env=False, follow_redirects=False)
        products: list[CatalogProduct] = []
        ids: set[str] = set()
        offset, expected_total = 0, None
        try:
            while True:
                try:
                    response = client.get(self.base_url + "/products", params={"status": "active", "offset": offset, "limit": self.PAGE_SIZE}, headers={"Authorization": "Bearer " + self._token, "Accept": "application/json"})
                except httpx.HTTPError as exc:
                    raise CatalogUnavailable("canonical catalog request failed") from exc
                if response.status_code != 200:
                    raise CatalogUnavailable(f"canonical catalog returned HTTP {response.status_code}")
                try:
                    payload: Any = response.json()
                except ValueError as exc:
                    raise CatalogUnavailable("canonical catalog returned invalid JSON") from exc
                if not isinstance(payload, dict):
                    raise CatalogUnavailable("canonical catalog response must be an object")
                items, total = payload.get("items"), payload.get("total")
                if not isinstance(items, list) or isinstance(total, bool) or not isinstance(total, int) or total < 0 or payload.get("offset") != offset or payload.get("limit") != self.PAGE_SIZE:
                    raise CatalogUnavailable("canonical catalog page contract is invalid")
                if expected_total is None:
                    expected_total = total
                    if total > self._max_products:
                        raise CatalogUnavailable("catalog exceeds the complete-snapshot limit")
                elif total != expected_total:
                    raise CatalogUnavailable("catalog total changed during pagination; retry the request")
                if len(items) > self.PAGE_SIZE:
                    raise CatalogUnavailable("catalog returned more products than the requested page size")
                if len(items) > max(0, total - offset):
                    raise CatalogUnavailable("catalog page contains more products than its declared total")
                if not items and offset < total:
                    raise CatalogUnavailable("catalog pagination ended before all products were read")
                for raw in items:
                    try:
                        item = CatalogProduct.from_mapping(raw)
                    except (TypeError, ValueError, KeyError) as exc:
                        raise CatalogUnavailable("canonical catalog returned an invalid product record") from exc
                    if item.product_id in ids:
                        raise CatalogUnavailable("catalog pagination returned a duplicate product ID")
                    ids.add(item.product_id)
                    products.append(item)
                offset += len(items)
                if offset >= total:
                    break
                if len(items) != self.PAGE_SIZE:
                    raise CatalogUnavailable("catalog returned a short page before the declared end")
        finally:
            if owned:
                client.close()
        try:
            return CatalogSnapshot(tuple(products), snapshot_started_at, complete=True)
        except (TypeError, ValueError) as exc:
            raise CatalogUnavailable("catalog snapshot failed validation") from exc
