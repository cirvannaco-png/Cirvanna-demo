"""Fail-closed pairwise offer comparison based on canonical variant identity.

Only item-price comparisons are supported here. Shipping, tax, fulfilment,
local transport and FX are deliberately excluded until independently sourced
market quotes are available.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import re
import uuid
from typing import Any


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _offer_summary(offer: dict[str, Any]) -> dict[str, Any]:
    return {
        "merchant_id": offer["merchant_id"],
        "merchant_name": offer["merchant_name"],
        "listing_id": offer["listing_id"],
        "variant_id": offer["variant_id"],
        "merchant_sku": offer["sku"],
        "canonical_variant_id": str(uuid.UUID(offer["canonical_variant_id"])),
        "price_minor": offer["price_minor"],
        "currency": offer["currency"],
        "available_stock": offer["available_stock"],
        "observed_at": _timestamp(offer["observed_at"]).isoformat().replace("+00:00", "Z"),
    }


def compare_like_for_like_offers(
    offers: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    max_age_seconds: int = 3600,
) -> dict[str, Any]:
    """Build exact-variant, same-currency groups with two or more distinct merchants."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    reasons: set[str] = set()
    groups: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    canonical_currencies: dict[str, set[str]] = defaultdict(set)

    for offer in offers:
        if not isinstance(offer, dict):
            reasons.add("INVALID_OFFER_RECORD")
            continue
        raw_variant = offer.get("canonical_variant_id")
        try:
            canonical_id = str(uuid.UUID(raw_variant)) if isinstance(raw_variant, str) else None
        except (ValueError, AttributeError, TypeError):
            canonical_id = None
        if canonical_id is None:
            reasons.add("MISSING_OR_INVALID_CANONICAL_VARIANT_ID")
            continue

        currency = offer.get("currency")
        if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
            reasons.add("INVALID_CURRENCY")
            continue
        canonical_currencies[canonical_id].add(currency)

        price = offer.get("price_minor")
        stock = offer.get("available_stock")
        if isinstance(price, bool) or not isinstance(price, int) or price < 0:
            reasons.add("INVALID_PRICE")
            continue
        if isinstance(stock, bool) or not isinstance(stock, int) or stock <= 0:
            reasons.add("OUT_OF_STOCK")
            continue

        observed = _timestamp(offer.get("observed_at"))
        if observed is None:
            reasons.add("INVALID_OBSERVED_AT")
            continue
        age = (now - observed).total_seconds()
        if age < -300:
            reasons.add("FUTURE_OBSERVED_AT")
            continue
        if age > max_age_seconds:
            reasons.add("STALE_OFFER")
            continue

        provenance = ("merchant_id", "merchant_name", "listing_id", "variant_id", "sku")
        if any(not isinstance(offer.get(key), str) or not offer[key].strip() for key in provenance):
            reasons.add("MISSING_MERCHANT_SOURCE_PROVENANCE")
            continue

        key = (canonical_id, currency)
        merchant_id = offer["merchant_id"]
        candidate = _offer_summary(offer)
        existing = groups[key].get(merchant_id)
        # One current offer per merchant/variant: freshest observation wins;
        # price and listing ID break exact timestamp ties deterministically.
        if existing is None:
            groups[key][merchant_id] = candidate
        else:
            current_time = _timestamp(existing["observed_at"])
            if (
                observed > current_time
                or (
                    observed == current_time
                    and (price, candidate["listing_id"]) < (existing["price_minor"], existing["listing_id"])
                )
            ):
                groups[key][merchant_id] = candidate

    comparable_groups = []
    for (canonical_id, currency), merchant_offers in sorted(groups.items()):
        if len(merchant_offers) < 2:
            reasons.add("INSUFFICIENT_DISTINCT_MERCHANTS")
            continue
        ordered = sorted(
            merchant_offers.values(),
            key=lambda item: (item["price_minor"], item["merchant_id"], item["listing_id"]),
        )
        comparable_groups.append({
            "canonical_variant_id": canonical_id,
            "currency": currency,
            "offers": ordered,
            "merchant_count": len(ordered),
            "basis": "item_price_only",
        })

    for currencies in canonical_currencies.values():
        if len(currencies) > 1:
            reasons.add("CURRENCY_MISMATCH")

    if comparable_groups:
        return {
            "status": "available",
            "basis": "item_price_only",
            "groups": comparable_groups,
            "unavailable_reasons": sorted(reasons),
            "exclusions": ["shipping", "tax", "fulfilment", "local_transport", "foreign_exchange"],
            "landed_cost_available": False,
        }
    if not reasons:
        reasons.add("NO_COMPARABLE_OFFERS")
    return {
        "status": "unavailable",
        "basis": None,
        "groups": [],
        "unavailable_reasons": sorted(reasons),
        "exclusions": ["shipping", "tax", "fulfilment", "local_transport", "foreign_exchange"],
        "landed_cost_available": False,
    }
