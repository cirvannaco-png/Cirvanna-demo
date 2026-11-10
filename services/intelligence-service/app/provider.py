"""Rights-gated generic provider adapter. No vendor is enabled by default."""
from __future__ import annotations

import os
from urllib.parse import urlparse

import httpx


class ProviderNotConfigured(RuntimeError):
    pass


def fetch_licensed_research(*, path: str, params: dict[str, str] | None = None) -> dict:
    """Fetch only from an explicitly configured, licence-bound provider endpoint.

    This adapter intentionally does not scrape public pages or infer permission
    from reachability. The caller must separately register the licence/source.
    """
    base = os.getenv("CIL_PROVIDER_BASE_URL", "").strip()
    token = os.getenv("CIL_PROVIDER_API_TOKEN", "").strip()
    licence = os.getenv("CIL_PROVIDER_LICENCE_ID", "").strip()
    terms = os.getenv("CIL_PROVIDER_TERMS_URL", "").strip()
    if not all((base, token, licence, terms)):
        raise ProviderNotConfigured("provider URL, API token, licence ID and terms URL are required")
    parsed = urlparse(base)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ProviderNotConfigured("provider base URL must be credential-free HTTPS")
    if path.startswith("/") or ".." in path.split("/"):
        raise ValueError("provider path must be relative and traversal-free")
    with httpx.Client(timeout=httpx.Timeout(8.0, connect=3.0), follow_redirects=False) as client:
        response = client.get(
            f"{base.rstrip('/')}/{path}",
            params=params or {},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json",
                     "X-Cirvanna-Licence-Id": licence},
        )
        response.raise_for_status()
        if "application/json" not in response.headers.get("content-type", "").lower():
            raise ValueError("licensed provider response must be JSON")
        payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("licensed provider response must be a JSON object")
    return {"licence_id": licence, "terms_url": terms, "payload": payload}
