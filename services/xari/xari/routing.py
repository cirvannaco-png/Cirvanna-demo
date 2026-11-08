"""Canonical, consent-aware PNELLY capability routing. The `xari` import path is retained for compatibility.

Tari and Xyra are legacy source names. This module routes only to fixed,
server-configured capabilities; it never accepts a client-provided URL or
claims that a capability executed. Execution adapters remain a separate gate.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlsplit

CONTRACT_VERSION = "1.0.0"

@dataclass(frozen=True)
class CapabilityRoute:
    intent: str
    capability: str
    upstream_env: str
    required_consents: tuple[str, ...]

ROUTES: dict[str, CapabilityRoute] = {
    "assistant_chat": CapabilityRoute("assistant_chat", "chat", "XARI_CHAT_API_URL", ()),
    "skin_analysis": CapabilityRoute("skin_analysis", "skin_analysis", "DERMALSIGHT_API_URL", ("image_processing",)),
    "marketplace_search": CapabilityRoute("marketplace_search", "marketplace_search", "MARKETPLACE_BFF_URL", ()),
    "virtual_try_on": CapabilityRoute("virtual_try_on", "virtual_try_on", "VIRTUAL_TRY_ON_API_URL", ("image_processing", "virtual_try_on")),
    "virtual_twin": CapabilityRoute("virtual_twin", "virtual_twin", "VIRTUAL_TWIN_API_URL", ("image_processing", "body_measurements")),
    "wardrobe": CapabilityRoute("wardrobe", "wardrobe", "WARDROBE_API_URL", ("wardrobe_access",)),
    "click_it": CapabilityRoute("click_it", "click_it", "VIRTUAL_TWIN_API_URL", ("image_processing", "click_it")),
}
CONSENT_KEYS = frozenset({
    "image_processing", "virtual_try_on", "body_measurements",
    "wardrobe_access", "click_it",
})
OPAQUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")

@dataclass(frozen=True)
class RoutePlan:
    contract_version: str
    intent: str
    capability: str
    upstream_env: str
    status: str
    code: str
    missing_consents: tuple[str, ...]
    configured: bool
    execution_supported: bool = False

def _trusted_base_url(value: str) -> bool:
    try:
        parts = urlsplit(value.strip())
        host = (parts.hostname or "").lower()
        local = host in {"localhost", "127.0.0.1", "::1"}
        return bool(
            host
            and parts.username is None
            and parts.password is None
            and not parts.query
            and not parts.fragment
            and (
                parts.scheme == "https"
                or (parts.scheme == "http" and local)
            )
        )
    except ValueError:
        return False

def plan_route(
    intent: str,
    consents: Mapping[str, bool],
    *,
    environment: Mapping[str, str] | None = None,
) -> RoutePlan:
    """Create a route plan without returning secrets or executing an upstream."""
    if intent not in ROUTES:
        raise ValueError("unsupported Xari intent")
    if not isinstance(consents, Mapping):
        raise ValueError("consents must be a mapping")
    if any(key not in CONSENT_KEYS for key in consents):
        raise ValueError("unknown consent field")
    if any(not isinstance(value, bool) for value in consents.values()):
        raise ValueError("consent values must be booleans")

    route = ROUTES[intent]
    missing = tuple(
        key for key in route.required_consents if consents.get(key) is not True
    )
    if missing:
        return RoutePlan(
            CONTRACT_VERSION, intent, route.capability, route.upstream_env,
            "blocked", "XARI_REQUIRED_CONSENT_MISSING", missing, False,
        )

    env = os.environ if environment is None else environment
    upstream = str(env.get(route.upstream_env, "")).strip()
    if not upstream:
        return RoutePlan(
            CONTRACT_VERSION, intent, route.capability, route.upstream_env,
            "unavailable", "XARI_UPSTREAM_NOT_CONFIGURED", (), False,
        )
    if not _trusted_base_url(upstream):
        return RoutePlan(
            CONTRACT_VERSION, intent, route.capability, route.upstream_env,
            "unavailable", "XARI_UPSTREAM_URL_INVALID", (), False,
        )
    return RoutePlan(
        CONTRACT_VERSION, intent, route.capability, route.upstream_env,
        "route_configured", "XARI_ROUTE_CONFIGURED_NOT_EXECUTED", (), True,
    )
