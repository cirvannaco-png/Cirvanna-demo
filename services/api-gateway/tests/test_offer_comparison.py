from datetime import datetime, timedelta, timezone
import uuid

from app.comparison import compare_like_for_like_offers


CANONICAL = "d5f2f2e0-1e43-4fb6-a2f4-7c8b8d0f3e11"
OTHER_CANONICAL = "e5f2f2e0-1e43-4fb6-a2f4-7c8b8d0f3e11"
NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)


def offer(
    merchant_id="merchant-a",
    *,
    canonical_variant_id=CANONICAL,
    variant_id="local-variant-1",
    currency="KES",
    price_minor=120000,
    stock=4,
    observed_at=None,
    listing_id=None,
):
    return {
        "merchant_id": merchant_id,
        "merchant_name": merchant_id.title(),
        "listing_id": listing_id or f"listing-{merchant_id}",
        "variant_id": variant_id,
        "sku": f"SKU-{merchant_id}",
        "canonical_variant_id": canonical_variant_id,
        "currency": currency,
        "price_minor": price_minor,
        "available_stock": stock,
        "observed_at": (observed_at or NOW).isoformat().replace("+00:00", "Z"),
    }


def test_only_same_canonical_variant_and_currency_from_distinct_merchants_compare():
    result = compare_like_for_like_offers(
        [offer("merchant-a", price_minor=120000), offer("merchant-b", price_minor=115000)],
        now=NOW,
    )
    assert result["status"] == "available"
    assert result["basis"] == "item_price_only"
    group = result["groups"][0]
    assert group["canonical_variant_id"] == CANONICAL
    assert group["currency"] == "KES"
    assert [item["merchant_id"] for item in group["offers"]] == ["merchant-b", "merchant-a"]
    assert result["landed_cost_available"] is False
    assert "shipping" in result["exclusions"] and "tax" in result["exclusions"]


def test_matching_merchant_local_variant_ids_do_not_prove_same_variant():
    result = compare_like_for_like_offers(
        [
            offer("merchant-a", canonical_variant_id=CANONICAL, variant_id="same-local-id"),
            offer("merchant-b", canonical_variant_id=OTHER_CANONICAL, variant_id="same-local-id"),
        ],
        now=NOW,
    )
    assert result["status"] == "unavailable"
    assert "INSUFFICIENT_DISTINCT_MERCHANTS" in result["unavailable_reasons"]


def test_missing_canonical_identity_fails_closed_even_when_local_ids_match():
    first = offer("merchant-a", variant_id="local-123")
    second = offer("merchant-b", variant_id="local-123")
    first.pop("canonical_variant_id")
    second.pop("canonical_variant_id")
    result = compare_like_for_like_offers([first, second], now=NOW)
    assert result["status"] == "unavailable"
    assert "MISSING_OR_INVALID_CANONICAL_VARIANT_ID" in result["unavailable_reasons"]


def test_currency_mismatch_is_not_silently_converted():
    result = compare_like_for_like_offers(
        [offer("merchant-a", currency="KES"), offer("merchant-b", currency="USD")],
        now=NOW,
    )
    assert result["status"] == "unavailable"
    assert "CURRENCY_MISMATCH" in result["unavailable_reasons"]
    assert result["groups"] == []


def test_stale_or_future_offer_cannot_enter_comparison():
    stale = offer("merchant-a", observed_at=NOW - timedelta(hours=2))
    fresh = offer("merchant-b")
    result = compare_like_for_like_offers([stale, fresh], now=NOW, max_age_seconds=3600)
    assert result["status"] == "unavailable"
    assert "STALE_OFFER" in result["unavailable_reasons"]

    future = offer("merchant-c", observed_at=NOW + timedelta(minutes=10))
    result = compare_like_for_like_offers([fresh, future], now=NOW)
    assert result["status"] == "unavailable"
    assert "FUTURE_OBSERVED_AT" in result["unavailable_reasons"]


def test_stock_and_provenance_are_mandatory():
    result = compare_like_for_like_offers(
        [offer("merchant-a", stock=0), offer("merchant-b")],
        now=NOW,
    )
    assert result["status"] == "unavailable"
    assert "OUT_OF_STOCK" in result["unavailable_reasons"]

    missing_source = offer("merchant-c")
    missing_source["merchant_name"] = ""
    result = compare_like_for_like_offers([offer("merchant-a"), missing_source], now=NOW)
    assert result["status"] == "unavailable"
    assert "MISSING_MERCHANT_SOURCE_PROVENANCE" in result["unavailable_reasons"]


def test_one_offer_per_merchant_uses_freshest_observation():
    older = offer("merchant-a", price_minor=100000, observed_at=NOW - timedelta(minutes=10), listing_id="old")
    newer = offer("merchant-a", price_minor=110000, observed_at=NOW - timedelta(minutes=1), listing_id="new")
    peer = offer("merchant-b", price_minor=115000)
    result = compare_like_for_like_offers([older, newer, peer], now=NOW)
    assert result["status"] == "available"
    merchant_a = next(x for x in result["groups"][0]["offers"] if x["merchant_id"] == "merchant-a")
    assert merchant_a["listing_id"] == "new"
    assert merchant_a["price_minor"] == 110000
