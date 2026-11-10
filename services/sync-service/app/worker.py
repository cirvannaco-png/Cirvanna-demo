"""At-least-once Commerce-to-Wardrobe event delivery worker.

The worker never infers payment. It consumes only events leased by Commerce's
internal outbox API and relies on Wardrobe's order-line idempotency for replay.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Any

import httpx


class SyncContractError(ValueError):
    """An event cannot safely be translated to the Wardrobe ownership contract."""


@dataclass(frozen=True)
class Settings:
    commerce_url: str
    commerce_token: str
    wardrobe_url: str
    wardrobe_token: str
    worker_id: str
    identity_learning_url: str | None = None
    identity_learning_token: str | None = None
    batch_size: int = 20
    timeout_seconds: float = 10.0
    poll_seconds: float = 3.0

    @classmethod
    def from_env(cls) -> "Settings":
        required = {
            "COMMERCE_SERVICE_URL": os.getenv("COMMERCE_SERVICE_URL", "").strip(),
            "COMMERCE_SYNC_TOKEN": os.getenv("COMMERCE_SYNC_TOKEN", ""),
            "WARDROBE_SERVICE_URL": os.getenv("WARDROBE_SERVICE_URL", "").strip(),
            "WARDROBE_SERVICE_TOKEN": os.getenv("WARDROBE_SERVICE_TOKEN", ""),
            "SYNC_WORKER_ID": os.getenv("SYNC_WORKER_ID", "commerce-wardrobe-sync").strip(),
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise ValueError("missing required sync configuration: " + ",".join(missing))
        if len(required["COMMERCE_SYNC_TOKEN"].encode()) < 32:
            raise ValueError("COMMERCE_SYNC_TOKEN must be at least 32 bytes")
        if len(required["WARDROBE_SERVICE_TOKEN"].encode()) < 32:
            raise ValueError("WARDROBE_SERVICE_TOKEN must be at least 32 bytes")
        identity_url = os.getenv("IDENTITY_SERVICE_URL", "").strip().rstrip("/") or None
        identity_token = os.getenv("IDENTITY_SERVICE_TOKEN", "").strip() or None
        if bool(identity_url) != bool(identity_token):
            raise ValueError("IDENTITY_SERVICE_URL and IDENTITY_SERVICE_TOKEN must be configured together")
        if identity_token is not None and len(identity_token.encode()) < 32:
            raise ValueError("IDENTITY_SERVICE_TOKEN must be at least 32 bytes")
        return cls(
            commerce_url=required["COMMERCE_SERVICE_URL"].rstrip("/"),
            commerce_token=required["COMMERCE_SYNC_TOKEN"],
            wardrobe_url=required["WARDROBE_SERVICE_URL"].rstrip("/"),
            wardrobe_token=required["WARDROBE_SERVICE_TOKEN"],
            worker_id=required["SYNC_WORKER_ID"],
            identity_learning_url=identity_url,
            identity_learning_token=identity_token,
            batch_size=max(1, min(int(os.getenv("SYNC_BATCH_SIZE", "20")), 100)),
            timeout_seconds=max(1.0, min(float(os.getenv("SYNC_TIMEOUT_SECONDS", "10")), 60.0)),
            poll_seconds=max(1.0, min(float(os.getenv("SYNC_POLL_SECONDS", "3")), 60.0)),
        )


def _required_string(value: Any, field: str, max_length: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > max_length:
        raise SyncContractError(f"invalid_{field}")
    return value.strip()


def _purchase_payload(event: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        raise SyncContractError("invalid_event_payload")
    event_id = _required_string(event.get("event_id"), "event_id", 36)
    if payload.get("event_id") != event_id:
        raise SyncContractError("event_id_mismatch")
    if event.get("event_type") != "commerce.order.paid" or payload.get("event_type") != "commerce.order.paid":
        raise SyncContractError("unsupported_event_type")
    if event.get("schema_version") != 1 or payload.get("schema_version") != 1:
        raise SyncContractError("unsupported_event_schema")
    if payload.get("ownership_authority") != "verified_payment":
        raise SyncContractError("unverified_ownership_authority")
    items = payload.get("items")
    if not isinstance(items, list) or not items or item not in items:
        raise SyncContractError("invalid_paid_order_items")
    return {
        "event_id": event_id,
        "event_type": "commerce.order.paid",
        "schema_version": 1,
        "ownership_authority": "verified_payment",
        "owner_user_id": _required_string(payload.get("buyer_user_id"), "buyer_user_id", 128),
        "order_id": _required_string(payload.get("order_id"), "order_id", 36),
        "order_item_id": _required_string(item.get("order_item_id"), "order_item_id", 36),
        "catalog_product_id": _required_string(item.get("catalog_product_id"), "catalog_product_id", 128),
        "product_name": _required_string(item.get("product_name"), "product_name", 200),
        "quantity": item.get("quantity"),
        "currency": _required_string(item.get("currency") or payload.get("currency"), "currency", 3),
        "unit_price_minor": item.get("unit_price_minor"),
        "paid_at": _required_string(payload.get("paid_at"), "paid_at", 64),
    }



def _tal_checkout_payloads(event: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Map consented checkout selections or paid lines to bounded TAL observations."""
    payload = event.get("payload")
    if not isinstance(payload, dict):
        raise SyncContractError("invalid_checkout_learning_payload")
    receipt_id = payload.get("personalization_consent_receipt_id")
    if receipt_id is None:
        return []
    receipt_id = _required_string(receipt_id, "personalization_consent_receipt_id", 128)
    subject_id = _required_string(payload.get("buyer_user_id"), "buyer_user_id", 128)
    event_id = _required_string(event.get("event_id"), "event_id", 36)
    event_type = event.get("event_type")
    if (
        payload.get("event_id") != event_id
        or event_type not in {"commerce.checkout.started", "commerce.order.paid"}
        or payload.get("event_type") != event_type
        or event.get("schema_version") != 1
        or payload.get("schema_version") != 1
    ):
        raise SyncContractError("invalid_checkout_learning_authority")
    if event_type == "commerce.order.paid" and payload.get("ownership_authority") != "verified_payment":
        raise SyncContractError("unverified_purchase_learning_authority")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise SyncContractError("invalid_checkout_learning_items")
    total = payload.get("total_minor")
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        raise SyncContractError("invalid_checkout_learning_total")
    observed_at = _required_string(payload.get("paid_at") or payload.get("occurred_at"), "observed_at", 64)
    try:
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SyncContractError("invalid_checkout_learning_timestamp") from exc
    if observed.tzinfo is None:
        raise SyncContractError("checkout_learning_timestamp_requires_timezone")

    events = []
    for item in items:
        if not isinstance(item, dict):
            raise SyncContractError("invalid_checkout_learning_line")
        quantity, price = item.get("quantity"), item.get("unit_price_minor")
        if (
            not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1
            or not isinstance(price, int) or isinstance(price, bool) or price < 0
        ):
            raise SyncContractError("invalid_checkout_learning_amount")
        currency = _required_string(item.get("currency") or payload.get("currency"), "currency", 3)
        if len(currency) != 3 or not currency.isalpha() or currency != currency.upper():
            raise SyncContractError("invalid_checkout_learning_currency")
        order_item_id = _required_string(item.get("order_item_id"), "order_item_id", 36)
        value = {
            "schema_version": "1.0",
            "evidence_type": "verified_transaction" if event_type == "commerce.order.paid" else "explicit_checkout_selection",
            "signal_strength": "weak",
            "signal_semantics": (
                "purchase_choice_is_not_a_declared_or_permanent_preference"
                if event_type == "commerce.order.paid"
                else "checkout_selection_is_not_a_purchase_or_declared_preference"
            ),
            "source_event_type": event_type,
            "order_id": _required_string(payload.get("order_id"), "order_id", 36),
            "order_item_id": order_item_id,
            "catalog_product_id": _required_string(item.get("catalog_product_id"), "catalog_product_id", 128),
            "variant_id": _required_string(item.get("merchant_variant_id") or item.get("variant_id"), "variant_id", 128),
            "merchant_id": _required_string(item.get("merchant_id"), "merchant_id", 128),
            "quantity": quantity,
            "unit_price_minor": price,
            "currency": currency,
            "order_total_minor": total,
            "fulfillment_mode": payload.get("fulfillment_mode"),
            "payment_method_family": payload.get("payment_method_family"),
            "may_change_explicit_preference": False,
            "may_create_hard_npl_veto": False,
        }
        tal_event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"cirvanna:tal-checkout:{event_id}:{order_item_id}"))
        events.append((subject_id, {
            "event_id": tal_event_id,
            "idempotency_key": f"checkout-choice:{event_id}:{order_item_id}",
            "consent_receipt_id": receipt_id,
            "feature_key": "checkout.purchase_choice" if event_type == "commerce.order.paid" else "checkout.selection",
            "value": json.dumps(value, sort_keys=True, separators=(",", ":")),
            "observed_at": observed.isoformat(),
            "expires_at": (observed + timedelta(days=180)).isoformat(),
            "event_kind": "observation",
        }))
    return events


def _refund_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        raise SyncContractError("invalid_refund_payload")
    event_id = _required_string(event.get("event_id"), "event_id", 36)
    if payload.get("event_id") != event_id:
        raise SyncContractError("refund_event_id_mismatch")
    if event.get("event_type") != "commerce.order.refund.updated" or payload.get("event_type") != "commerce.order.refund.updated":
        raise SyncContractError("unsupported_refund_event_type")
    if event.get("schema_version") != 1 or payload.get("schema_version") != 1:
        raise SyncContractError("unsupported_refund_event_schema")
    if payload.get("ownership_authority") != "verified_stripe_charge_refund":
        raise SyncContractError("unverified_refund_authority")
    if payload.get("physical_return_confirmed") is not False or payload.get("ownership_effect") != "financial_status_only":
        raise SyncContractError("refund_must_not_imply_physical_return")
    order_total = payload.get("order_total_minor")
    refunded = payload.get("amount_refunded_minor")
    if (
        not isinstance(order_total, int) or isinstance(order_total, bool) or order_total <= 0
        or not isinstance(refunded, int) or isinstance(refunded, bool) or refunded <= 0
        or refunded > order_total
    ):
        raise SyncContractError("invalid_refund_amount")
    expected_state = "refunded" if refunded == order_total else "partial_refund"
    if payload.get("refund_state") != expected_state:
        raise SyncContractError("refund_state_amount_mismatch")
    currency = _required_string(payload.get("currency"), "currency", 3)
    if len(currency) != 3 or not currency.isalpha() or currency != currency.upper():
        raise SyncContractError("invalid_refund_currency")
    return {
        "event_id": event_id,
        "provider_event_id": _required_string(payload.get("provider_event_id"), "provider_event_id", 180),
        "event_type": "commerce.order.refund.updated",
        "schema_version": 1,
        "ownership_authority": "verified_stripe_charge_refund",
        "owner_user_id": _required_string(payload.get("buyer_user_id"), "buyer_user_id", 128),
        "order_id": _required_string(payload.get("order_id"), "order_id", 36),
        "payment_intent_id": _required_string(payload.get("payment_intent_id"), "payment_intent_id", 180),
        "charge_id": _required_string(payload.get("charge_id"), "charge_id", 180),
        "currency": currency,
        "order_total_minor": order_total,
        "amount_refunded_minor": refunded,
        "refund_state": expected_state,
        "refunded_at": _required_string(payload.get("refunded_at"), "refunded_at", 64),
        "physical_return_confirmed": False,
        "ownership_effect": "financial_status_only",
    }


class CommerceWardrobeWorker:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self.client = client or httpx.Client(timeout=settings.timeout_seconds)

    def _commerce_headers(self) -> dict[str, str]:
        return {"X-Commerce-Sync-Token": self.settings.commerce_token}

    def _wardrobe_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.wardrobe_token}"}

    def _tal_headers(self) -> dict[str, str]:
        if not self.settings.identity_learning_token:
            raise SyncContractError("TAL_SINK_NOT_CONFIGURED")
        return {"Authorization": f"Bearer {self.settings.identity_learning_token}"}

    def process_batch(self) -> dict[str, int]:
        claim = self.client.post(
            f"{self.settings.commerce_url}/internal/outbox/claim",
            headers=self._commerce_headers(),
            json={"worker_id": self.settings.worker_id, "limit": self.settings.batch_size},
        )
        claim.raise_for_status()
        events = claim.json().get("events", [])
        if not isinstance(events, list):
            raise SyncContractError("invalid_claim_response")
        processed = retried = dead_lettered = 0
        for event in events:
            event_id = _required_string(event.get("event_id"), "event_id", 36)
            try:
                event_type = event.get("event_type")
                if event_type == "commerce.checkout.started":
                    tal_events = _tal_checkout_payloads(event)
                    if tal_events and not self.settings.identity_learning_url:
                        raise SyncContractError("TAL_SINK_NOT_CONFIGURED")
                    for subject_id, tal_request in tal_events:
                        tal_response = self.client.post(
                            f"{self.settings.identity_learning_url}/v1/tal/events",
                            params={"subject_id": subject_id},
                            headers=self._tal_headers(),
                            json=tal_request,
                        )
                        if tal_response.status_code == 403:
                            break
                        tal_response.raise_for_status()
                elif event_type == "commerce.order.paid":
                    payload = event.get("payload")
                    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
                        raise SyncContractError("invalid_paid_order_payload")
                    for item in payload["items"]:
                        if not isinstance(item, dict):
                            raise SyncContractError("invalid_paid_order_line")
                        purchase = _purchase_payload(event, item)
                        response = self.client.post(
                            f"{self.settings.wardrobe_url}/v1/purchases/verified",
                            headers=self._wardrobe_headers(),
                            json=purchase,
                        )
                        response.raise_for_status()
                    tal_events = _tal_checkout_payloads(event)
                    if tal_events and not self.settings.identity_learning_url:
                        raise SyncContractError("TAL_SINK_NOT_CONFIGURED")
                    for subject_id, tal_request in tal_events:
                        tal_response = self.client.post(
                            f"{self.settings.identity_learning_url}/v1/tal/events",
                            params={"subject_id": subject_id},
                            headers=self._tal_headers(),
                            json=tal_request,
                        )
                        if tal_response.status_code == 403:
                            break
                        tal_response.raise_for_status()
                elif event_type == "commerce.order.refund.updated":
                    refund = _refund_payload(event)
                    response = self.client.post(
                        f"{self.settings.wardrobe_url}/v1/purchases/refund-status",
                        headers=self._wardrobe_headers(),
                        json=refund,
                    )
                    response.raise_for_status()
                else:
                    raise SyncContractError("unsupported_commerce_event_type")
                ack = self.client.post(
                    f"{self.settings.commerce_url}/internal/outbox/{event_id}/ack",
                    headers=self._commerce_headers(),
                    json={"worker_id": self.settings.worker_id},
                )
                ack.raise_for_status()
                processed += 1
            except Exception as exc:
                # Do not forward exception text: HTTP clients may include URLs,
                # request bodies or other sensitive material in their messages.
                code = exc.args[0] if isinstance(exc, SyncContractError) and exc.args else "DOWNSTREAM_DELIVERY_FAILED"
                failure = self.client.post(
                    f"{self.settings.commerce_url}/internal/outbox/{event_id}/fail",
                    headers=self._commerce_headers(),
                    json={"worker_id": self.settings.worker_id, "error_code": re.sub(r"[^A-Z0-9_]", "_", str(code).upper())[:120]},
                )
                if failure.is_success:
                    status = failure.json().get("status")
                    if status == "dead_lettered":
                        dead_lettered += 1
                    else:
                        retried += 1
                else:
                    # Lease will expire and Commerce can safely redeliver.
                    retried += 1
        return {"claimed": len(events), "processed": processed, "retried": retried, "dead_lettered": dead_lettered}

    def run_forever(self) -> None:
        while True:
            try:
                self.process_batch()
            except Exception:
                # Keep the worker alive; no user data or credentials are logged.
                pass
            time.sleep(self.settings.poll_seconds)

    def close(self) -> None:
        self.client.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="process one outbox batch and exit")
    args = parser.parse_args()
    worker = CommerceWardrobeWorker(Settings.from_env())
    try:
        if args.once:
            print(worker.process_batch())
        else:
            worker.run_forever()
    finally:
        worker.close()


if __name__ == "__main__":
    main()
