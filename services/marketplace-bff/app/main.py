"""Same-origin backend-for-frontend for the Cirvanna marketplace.

This service keeps service credentials server-side and forwards only an explicit
allowlist of customer commerce routes. It never issues identity tokens or
fabricates decision, fit, Click It, Virtual Twin, or try-on outputs.
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from urllib.parse import urlsplit

import httpx
from fastapi import Body, FastAPI, HTTPException, Query, Request
from starlette.datastructures import UploadFile as StarletteUploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SERVICE = "cirvanna-marketplace-bff"
ROOT = Path(__file__).resolve().parents[3]
DEFAULT_HTML = ROOT / "apps" / "demo-web" / "marketplace.html"
DEFAULT_WARDROBE_HTML = ROOT / "apps" / "demo-web" / "wardrobe.html"
DEFAULT_BRAND_PORTAL_HTML = ROOT / "apps" / "demo-web" / "brand-portal.html"
DEFAULT_FOUNDER_CONSOLE_HTML = ROOT / "apps" / "demo-web" / "founder-console.html"
DEFAULT_PORTAL_ASSETS = ROOT / "apps" / "demo-web" / "assets"
HTML_PATH = Path(os.getenv("MARKETPLACE_HTML_PATH", str(DEFAULT_HTML)))
BRAND_PORTAL_HTML_PATH = Path(os.getenv("BRAND_PORTAL_HTML_PATH", str(DEFAULT_BRAND_PORTAL_HTML)))
FOUNDER_CONSOLE_HTML_PATH = Path(os.getenv("FOUNDER_CONSOLE_HTML_PATH", str(DEFAULT_FOUNDER_CONSOLE_HTML)))
# Public assets are repository-owned presentation files, never an upload or media store.
PORTAL_ASSETS_DIR = DEFAULT_PORTAL_ASSETS
TIMEOUT_SECONDS = 5.0
MAX_PAGE_SIZE = 100
MAX_VISION_IMAGE_BYTES = 10 * 1024 * 1024
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")
SERVICE_PATHS = {
    ("GET", "me"),
    ("GET", "merchants/me"),
    ("GET", "merchants/me/markets"),
    ("POST", "merchants/applications"),
    ("POST", "merchant/markets"),
    ("GET", "merchant/listings"),
    ("GET", "merchant/orders"),
    ("POST", "merchant/listings"),
    ("GET", "admin/merchants"),
    ("GET", "admin/merchant-decisions"),
    ("GET", "cart"),
    ("GET", "saved-products"),
    ("GET", "orders"),
    ("POST", "cart/items"),
    ("POST", "checkout"),
}

app = FastAPI(
    title="Cirvanna Marketplace BFF",
    version="0.1.0",
    description="Same-origin marketplace, Wardrobe and governed merchant portals with verified account identity and private service proxies.",
)

app.mount("/assets", StaticFiles(directory=str(PORTAL_ASSETS_DIR), check_dir=True), name="portal-assets")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; "
        "base-uri 'self'; frame-ancestors 'none'",
    )
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


def _upstream_base(key: str) -> str:
    raw = os.getenv(key, "").strip()
    if not raw:
        raise HTTPException(status_code=503, detail={"code": f"{key}_NOT_CONFIGURED"})
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    local = host in {"localhost", "127.0.0.1", "::1"}
    if (
        not host
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or (parts.scheme != "https" and not (parts.scheme == "http" and local))
    ):
        raise HTTPException(status_code=503, detail={"code": f"{key}_MUST_BE_TRUSTED_HTTPS"})
    return raw.rstrip("/")


def _upstream_ready(base: str) -> bool:
    try:
        response = httpx.get(base + "/ready", timeout=TIMEOUT_SECONDS, follow_redirects=False)
        if response.status_code != 200:
            return False
        payload = response.json()
        return isinstance(payload, dict) and payload.get("ready") is True
    except (httpx.HTTPError, ValueError):
        return False


def _internal_service(url_key: str, token_key: str) -> tuple[str, str]:
    base = _upstream_base(url_key)
    token = os.getenv(token_key, "").strip()
    if len(token.encode("utf-8")) < 32:
        raise HTTPException(status_code=503, detail={"code": f"{token_key}_NOT_CONFIGURED"})
    return base, token

def _pnelly_internal_service() -> tuple[str, str]:
    """Prefer PNELLY URL/token as a pair; keep Xari and Tari pairs as fallbacks."""
    pnelly_url = os.getenv("PNELLY_API_URL", "").strip()
    xari_url = os.getenv("XARI_API_URL", "").strip()
    tari_url = os.getenv("TARI_API_URL", "").strip()

    if pnelly_url:
        url_key = "PNELLY_API_URL"
        token = os.getenv("PNELLY_API_TOKEN", "").strip()
    elif xari_url:
        url_key = "XARI_API_URL"
        token = os.getenv("XARI_API_TOKEN", "").strip() or os.getenv("TARI_API_TOKEN", "").strip()
    elif tari_url:
        url_key = "TARI_API_URL"
        token = os.getenv("TARI_API_TOKEN", "").strip()
    else:
        raise HTTPException(status_code=503, detail={"code": "PNELLY_API_URL_NOT_CONFIGURED"})

    base = _upstream_base(url_key)
    if len(token.encode("utf-8")) < 32:
        raise HTTPException(status_code=503, detail={"code": "PNELLY_API_TOKEN_NOT_CONFIGURED"})
    return base, token


class MarketplaceSearchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=3, max_length=1000)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    limit: int = Field(default=10, ge=1, le=25)

    @property
    def normalized_query(self) -> str:
        return " ".join(self.query.split()).strip()


class OfferComparisonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variant_ids: list[str] = Field(min_length=2, max_length=2)
    destination_country_code: str = Field(min_length=2, max_length=2)
    destination_key: str = Field(min_length=3, max_length=180)
    fulfillment_mode: Literal["shipping", "courier_delivery", "merchant_delivery", "collection", "local_transport"]
    display_currency: str = Field(min_length=3, max_length=3)
    payment_method: str | None = Field(default=None, min_length=2, max_length=50)
    radius_km: float = Field(default=30.0, ge=1.0, le=500.0)

    @field_validator("variant_ids")
    @classmethod
    def valid_variants(cls, values: list[str]) -> list[str]:
        parsed = [str(uuid.UUID(value)) for value in values]
        if len(set(parsed)) != 2:
            raise ValueError("two distinct variant IDs are required")
        return parsed

    @field_validator("destination_country_code")
    @classmethod
    def valid_market_country(cls, value: str) -> str:
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{2}", value):
            raise ValueError("destination country must be a two-letter code")
        return value

    @field_validator("display_currency")
    @classmethod
    def valid_display_currency(cls, value: str) -> str:
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", value):
            raise ValueError("display currency must be a three-letter code")
        return value


async def _safe_json_post(
    base: str,
    path: str,
    token: str,
    payload: dict,
) -> dict:
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=2.0),
            trust_env=False,
            follow_redirects=False,
        ) as client:
            response = await client.post(
                base + path,
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "VISION_SEARCH_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "VISION_SEARCH_UNAVAILABLE"}) from exc
    if response.status_code != 200:
        if response.status_code in {400, 413, 415, 422}:
            raise HTTPException(response.status_code, detail={"code": "VISION_SEARCH_REQUEST_REJECTED"})
        if response.status_code in {502, 503, 504}:
            raise HTTPException(503, detail={"code": "VISION_SEARCH_UNAVAILABLE"})
        raise HTTPException(502, detail={"code": "VISION_SEARCH_FAILED"})
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "VISION_SEARCH_INVALID_RESPONSE"}) from exc
    if not isinstance(data, dict) or data.get("status") != "complete" or not isinstance(data.get("candidates"), list):
        raise HTTPException(502, detail={"code": "VISION_SEARCH_INVALID_RESPONSE"})
    return data


@app.post("/api/vision/marketplace-search")
async def marketplace_description_search(payload: MarketplaceSearchIn) -> dict:
    """Search marketplace candidates by description without exposing PNELLY credentials."""
    base, token = _pnelly_internal_service()
    request_body = {"query": payload.normalized_query, "limit": payload.limit}
    if payload.category and payload.category.strip():
        request_body["category"] = payload.category.strip()
    data = await _safe_json_post(base, "/v1/marketplace/search", token, request_body)
    # PNELLY retrieval is never a CAL decision. Do not return candidate records,
    # even if an upstream response incorrectly claims SHOW/display_authorized.
    raw_count = data.get("candidate_count", len(data["candidates"]))
    if isinstance(raw_count, bool) or not isinstance(raw_count, int) or raw_count < 0:
        raise HTTPException(502, detail={"code": "VISION_SEARCH_INVALID_CANDIDATE_COUNT"})
    return {
        "status": "complete",
        "query": payload.normalized_query,
        "candidate_count": raw_count,
        "display_authorized": False,
        "decision_status": "PENDING_CAL",
        "scores_are_probabilities": False,
    }



class CreateWardrobeItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=80)
    attributes: list[str] = Field(default_factory=list, max_length=100)
    catalog_product_id: str | None = Field(default=None, max_length=128)


class EditWardrobeItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    command_id: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    attributes: list[str] | None = Field(default=None, max_length=100)


class CreateWardrobeOutfitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    wardrobe_item_ids: list[str] = Field(min_length=1, max_length=20)


class AddWardrobeOutfitPieceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    command_id: str = Field(min_length=8, max_length=128)
    wardrobe_item_id: str = Field(min_length=3, max_length=128)


class RecordPNELLYLookWearIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_ids: list[str] = Field(min_length=1, max_length=20)
    event_id: str = Field(min_length=8, max_length=128)
    consent_receipt_id: str = Field(min_length=8, max_length=128)
    observed_at: str = Field(min_length=20, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    context: dict[str, str] = Field(default_factory=dict, max_length=8)


class EditWardrobeOutfitPieceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    command_id: str = Field(min_length=8, max_length=128)
    wardrobe_item_id: str | None = Field(default=None, min_length=3, max_length=128)


class ColorProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    liked_colors: list[str] = Field(default_factory=list, max_length=40)
    disliked_colors: list[str] = Field(default_factory=list, max_length=40)
    best_version_colors: list[str] = Field(default_factory=list, max_length=40)


class WardrobeFeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str = Field(min_length=3, max_length=128)
    event_id: str = Field(min_length=8, max_length=128)
    signal: Literal["like", "dislike", "avoid", "modify", "wear"]
    consent_receipt_id: str = Field(min_length=8, max_length=128)
    target_type: Literal["item", "attribute"] | None = None
    target_value: str | None = Field(default=None, min_length=1, max_length=180)


class WardrobeConsentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Literal["style_learning", "personalization", "profile_storage"]
    granted: bool = True


class DailyLooksIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    occasion: str | None = Field(default=None, max_length=120)
    climate: str | None = Field(default=None, max_length=80)
    timezone: str = Field(default="UTC", min_length=1, max_length=80)
    evaluation_consent_receipt_id: str | None = Field(default=None, min_length=8, max_length=128)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value


class WardrobePreferenceRetractionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    correction_event_id: str = Field(min_length=8, max_length=128)



class WardrobeRecommendationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=2, max_length=160)
    category: str | None = Field(default=None, max_length=80)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    limit: int = Field(default=10, ge=1, le=25)
    occasion: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=120)
    climate: str | None = Field(default=None, max_length=120)
    exclude_owned_products: bool = True


class WardrobeTryOnIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    wardrobe_item_id: str = Field(min_length=3, max_length=128)
    twin_id: str = Field(min_length=8, max_length=128)
    person_image_asset_id: str = Field(min_length=36, max_length=36)
    consent_id: str = Field(min_length=8, max_length=160)
    consent_image_processing: bool
    consent_virtual_try_on: bool
    request_id: str | None = Field(default=None, min_length=8, max_length=128)
    look_id: str | None = Field(default=None, min_length=3, max_length=128)
    look_version: int | None = Field(default=None, ge=1)
    wardrobe_snapshot_version: int | None = Field(default=None, ge=1)

    @field_validator("person_image_asset_id")
    @classmethod
    def valid_person_asset_id(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not UUID_RE.fullmatch(normalized):
            raise ValueError("person_image_asset_id must be an opaque UUID")
        return normalized

    @model_validator(mode="after")
    def validate_look_version(self):
        if self.look_id and (self.look_version is None or self.wardrobe_snapshot_version is None):
            raise ValueError("look_id requires look_version and wardrobe_snapshot_version")
        if not self.look_id and (self.look_version is not None or self.wardrobe_snapshot_version is not None):
            raise ValueError("look versions require look_id")
        return self



async def _verified_commerce_subject(client: httpx.AsyncClient, request: Request) -> tuple[str, str]:
    authorization = request.headers.get("authorization", "")
    scheme, _, user_token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not user_token.strip():
        raise HTTPException(401, detail={"code": "USER_BEARER_REQUIRED"}, headers={"WWW-Authenticate": "Bearer"})
    commerce_base = _upstream_base("COMMERCE_API_URL")
    try:
        identity = await client.get(
            commerce_base + "/me",
            headers={"Authorization": "Bearer " + user_token.strip(), "Accept": "application/json"},
        )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "USER_IDENTITY_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "USER_IDENTITY_UNAVAILABLE"}) from exc
    if identity.status_code in {401, 403}:
        raise HTTPException(401, detail={"code": "USER_AUTHENTICATION_FAILED"})
    if identity.status_code != 200:
        raise HTTPException(503, detail={"code": "USER_IDENTITY_UNAVAILABLE"})
    try:
        actor = identity.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "INVALID_USER_IDENTITY_RESPONSE"}) from exc
    subject = actor.get("user_id") if isinstance(actor, dict) else None
    if not isinstance(subject, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}", subject.strip()):
        raise HTTPException(502, detail={"code": "INVALID_USER_IDENTITY_RESPONSE"})
    return subject.strip(), user_token.strip()


def _wardrobe_service() -> tuple[str, str]:
    return _internal_service("WARDROBE_SERVICE_URL", "WARDROBE_SERVICE_TOKEN")


def _identity_learning_service() -> tuple[str, str]:
    return _internal_service("IDENTITY_SERVICE_URL", "IDENTITY_SERVICE_TOKEN")


def _decision_gateway() -> tuple[str, str]:
    return _internal_service("DECISION_GATEWAY_URL", "DECISION_GATEWAY_TOKEN")


def _parse_rotation_snapshot(data: object, *, subject: str, active_item_ids: set[str]) -> dict:
    if not isinstance(data, dict) or data.get("version") is None:
        raise HTTPException(502, detail={"code": "PNELLY_ROTATION_STATE_RESPONSE_INVALID"})
    version = data.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 0:
        raise HTTPException(502, detail={"code": "PNELLY_ROTATION_STATE_RESPONSE_INVALID"})
    state = data.get("state")
    if state is None:
        if version != 0:
            raise HTTPException(502, detail={"code": "PNELLY_ROTATION_STATE_RESPONSE_INVALID"})
        return {"version": 0, "cycle_number": 1, "cycle_started_at": None, "seen_item_ids": []}
    if not isinstance(state, dict) or state.get("owner_user_id") != subject or state.get("version") != version:
        raise HTTPException(502, detail={"code": "PNELLY_ROTATION_STATE_SCOPE_MISMATCH"})
    cycle_number = state.get("cycle_number")
    started = state.get("cycle_started_at")
    seen = state.get("surfaced_item_ids")
    if isinstance(cycle_number, bool) or not isinstance(cycle_number, int) or cycle_number < 1:
        raise HTTPException(502, detail={"code": "PNELLY_ROTATION_STATE_RESPONSE_INVALID"})
    if (
        not isinstance(started, str)
        or not isinstance(seen, list)
        or any(not isinstance(item_id, str) for item_id in seen)
        or len(seen) != len(set(seen))
    ):
        raise HTTPException(502, detail={"code": "PNELLY_ROTATION_STATE_RESPONSE_INVALID"})
    try:
        from datetime import date
        cycle_start_date = started[:10]
        date.fromisoformat(cycle_start_date)
    except (TypeError, ValueError):
        raise HTTPException(502, detail={"code": "PNELLY_ROTATION_STATE_RESPONSE_INVALID"})
    if any(not isinstance(item_id, str) or item_id not in active_item_ids for item_id in seen):
        raise HTTPException(502, detail={"code": "PNELLY_ROTATION_STATE_SCOPE_MISMATCH"})
    return {
        "version": version,
        "cycle_number": cycle_number,
        "cycle_started_at": cycle_start_date,
        "seen_item_ids": seen,
    }


def _validate_rotation_recommendation(
    recommendation: object,
    *,
    active_item_ids: set[str],
    prior_state: dict,
    local_date: str,
) -> dict:
    if not isinstance(recommendation, dict):
        raise HTTPException(502, detail={"code": "PNELLY_ROTATION_RESPONSE_INVALID"})
    rotation = recommendation.get("wardrobe_rotation")
    if not isinstance(rotation, dict) or rotation.get("policy_version") != "wardrobe-revival-v1":
        raise HTTPException(502, detail={"code": "PNELLY_ROTATION_RESPONSE_INVALID"})
    next_state = rotation.get("next_state")
    seen = next_state.get("seen_item_ids") if isinstance(next_state, dict) else None
    queue = rotation.get("revival_queue_item_ids")
    cycle_number = next_state.get("cycle_number") if isinstance(next_state, dict) else None
    cycle_started = next_state.get("cycle_started_at") if isinstance(next_state, dict) else None
    complete = rotation.get("cycle_complete")
    overdue = rotation.get("cycle_overdue")
    try:
        from datetime import date
        date.fromisoformat(cycle_started)
    except (TypeError, ValueError):
        raise HTTPException(502, detail={"code": "PNELLY_ROTATION_RESPONSE_INVALID"})
    if (
        isinstance(cycle_number, bool) or not isinstance(cycle_number, int) or cycle_number < 1
        or not isinstance(seen, list) or len(seen) != len(set(seen))
        or not isinstance(queue, list) or len(queue) != len(set(queue))
        or any(not isinstance(item_id, str) or item_id not in active_item_ids for item_id in seen + queue)
        or set(seen).intersection(queue)
        or not isinstance(complete, bool) or not isinstance(overdue, bool)
    ):
        raise HTTPException(502, detail={"code": "PNELLY_ROTATION_RESPONSE_INVALID"})
    prior_cycle = prior_state["cycle_number"]
    prior_start = prior_state["cycle_started_at"] or local_date
    if complete:
        if cycle_number != prior_cycle + 1 or seen or cycle_started != local_date or overdue:
            raise HTTPException(502, detail={"code": "PNELLY_ROTATION_CYCLE_RESET_INVALID"})
    else:
        if cycle_number != prior_cycle or cycle_started != prior_start:
            raise HTTPException(502, detail={"code": "PNELLY_ROTATION_CYCLE_RESET_INVALID"})
        days_elapsed = (date.fromisoformat(local_date) - date.fromisoformat(prior_start)).days
        if days_elapsed >= 7 and not overdue:
            raise HTTPException(502, detail={"code": "PNELLY_ROTATION_OVERDUE_STATE_INVALID"})
        if overdue and days_elapsed < 7:
            raise HTTPException(502, detail={"code": "PNELLY_ROTATION_OVERDUE_STATE_INVALID"})
    return {"cycle_number": cycle_number, "cycle_started_at": cycle_started, "seen_item_ids": seen}


def _withhold_unverified_media(value):
    """Recursively redact image URLs until the exact asset has a verified receipt."""
    if isinstance(value, list):
        return [_withhold_unverified_media(item) for item in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            normalized = str(key).casefold()
            if normalized == "image_urls":
                result[key] = []
            elif normalized in {"image_url", "photo_url", "avatar_url", "media_url", "thumbnail_url"}:
                result[key] = None
            else:
                result[key] = _withhold_unverified_media(item)
        return result
    return value


def _private_json_response(data: dict, *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        content=_withhold_unverified_media(data),
        headers={"Cache-Control": "no-store, private"},
        status_code=status_code,
    )


@app.get("/wardrobe", response_class=HTMLResponse)
def wardrobe_page() -> HTMLResponse:
    try:
        html = DEFAULT_WARDROBE_HTML.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=503, detail={"code": "WARDROBE_PAGE_UNAVAILABLE"}) from exc
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/api/style/color-profile")
async def get_style_color_profile(request: Request) -> Response:
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=2.0), trust_env=False, follow_redirects=False) as client:
        subject, _ = await _verified_commerce_subject(client, request)
        base, token = _identity_learning_service()
        try:
            response = await client.get(
                base + f"/v1/color-profiles/{subject}",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "COLOR_PROFILE_SERVICE_UNAVAILABLE"}) from exc
    if response.status_code in {401, 403, 404}:
        try:
            detail = response.json().get("detail", {})
        except ValueError:
            detail = {"code": "COLOR_PROFILE_ACCESS_DENIED"}
        raise HTTPException(response.status_code, detail=detail)
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "COLOR_PROFILE_SERVICE_UNAVAILABLE"})
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "COLOR_PROFILE_RESPONSE_INVALID"}) from exc
    if not isinstance(data, dict) or data.get("subject_id") != subject:
        raise HTTPException(502, detail={"code": "COLOR_PROFILE_SCOPE_MISMATCH"})
    return _private_json_response(data)


@app.put("/api/style/color-profile")
async def put_style_color_profile(request: Request, payload: ColorProfileIn) -> Response:
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=2.0), trust_env=False, follow_redirects=False) as client:
        subject, _ = await _verified_commerce_subject(client, request)
        base, token = _identity_learning_service()
        try:
            response = await client.put(
                base + f"/v1/color-profiles/{subject}",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json=payload.model_dump(),
            )
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "COLOR_PROFILE_SAVE_UNAVAILABLE"}) from exc
    if response.status_code in {400, 403, 404, 409, 422}:
        try:
            detail = response.json().get("detail", {})
        except ValueError:
            detail = {"code": "COLOR_PROFILE_SAVE_REJECTED"}
        raise HTTPException(response.status_code, detail=detail)
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "COLOR_PROFILE_SAVE_UNAVAILABLE"})
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "COLOR_PROFILE_RESPONSE_INVALID"}) from exc
    if not isinstance(data, dict) or data.get("subject_id") != subject:
        raise HTTPException(502, detail={"code": "COLOR_PROFILE_SCOPE_MISMATCH"})
    return _private_json_response(data)


@app.get("/api/wardrobe/items")
async def wardrobe_items(request: Request) -> Response:
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=2.0), trust_env=False, follow_redirects=False) as client:
        subject, _ = await _verified_commerce_subject(client, request)
        base, token = _wardrobe_service()
        try:
            response = await client.get(
                base + "/v1/items",
                params={"owner_user_id": subject, "include_archived": "false"},
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "WARDROBE_SERVICE_UNAVAILABLE"}) from exc
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "WARDROBE_SERVICE_UNAVAILABLE"})
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "WARDROBE_RESPONSE_INVALID"}) from exc
    if (
        not isinstance(data, dict) or data.get("owner_user_id") != subject
        or not isinstance(data.get("items"), list)
        or any(not isinstance(item, dict) or item.get("owner_user_id") != subject for item in data["items"])
    ):
        raise HTTPException(502, detail={"code": "WARDROBE_SCOPE_OR_SCHEMA_MISMATCH"})
    return _private_json_response(data)




@app.get("/api/virtual-twin/capabilities")
async def virtual_twin_capabilities(request: Request) -> Response:
    """Expose a minimal authenticated capability snapshot; never imply a Twin exists."""
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(5.0, connect=1.5), trust_env=False, follow_redirects=False
    ) as client:
        await _verified_commerce_subject(client, request)
        twin_base = _upstream_base("VIRTUAL_TWIN_API_URL")
        try:
            response = await client.get(twin_base + "/capabilities", headers={"Accept": "application/json"})
        except httpx.TimeoutException as exc:
            raise HTTPException(504, detail={"code": "VIRTUAL_TWIN_CAPABILITIES_TIMEOUT"}) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "VIRTUAL_TWIN_CAPABILITIES_UNAVAILABLE"}) from exc
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "VIRTUAL_TWIN_CAPABILITIES_UNAVAILABLE"})
    try:
        source = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "VIRTUAL_TWIN_CAPABILITIES_INVALID"}) from exc
    if not isinstance(source, dict):
        raise HTTPException(502, detail={"code": "VIRTUAL_TWIN_CAPABILITIES_INVALID"})
    boolean_fields = (
        "twin_generation", "persistent_twin_generation", "persistent_twin_preview",
        "pose_skeleton_inference", "body_reconstruction", "full_surface_mesh",
        "calibrated_body_measurements", "fit_prediction", "ar_rendering",
        "image_persistence", "click_it_twin_personalization",
    )
    if any(not isinstance(source.get(field), bool) for field in boolean_fields):
        raise HTTPException(502, detail={"code": "VIRTUAL_TWIN_CAPABILITIES_INVALID"})
    return _private_json_response({
        "service": "virtual-twin",
        "persistent_twin_generation": source["persistent_twin_generation"],
        "persistent_twin_preview": source["persistent_twin_preview"],
        "pose_skeleton_inference": source["pose_skeleton_inference"],
        "body_reconstruction": source["body_reconstruction"],
        "full_surface_mesh": source["full_surface_mesh"],
        "calibrated_body_measurements": source["calibrated_body_measurements"],
        "fit_prediction": source["fit_prediction"],
        "ar_rendering": source["ar_rendering"],
        "image_persistence": source["image_persistence"],
        "click_it_twin_personalization": source["click_it_twin_personalization"],
        "try_on_available": False,
        "reason": source.get("reason") if isinstance(source.get("reason"), str) else None,
    })


@app.post("/api/wardrobe/items/{item_id}/try-on")
async def try_on_wardrobe_item(item_id: str, request: Request, payload: WardrobeTryOnIn) -> Response:
    """Start a private Twin render for an exact, active, user-owned wardrobe image."""
    if item_id != payload.wardrobe_item_id:
        raise HTTPException(422, detail={"code": "WARDROBE_ITEM_ID_MISMATCH"})
    if not payload.consent_image_processing or not payload.consent_virtual_try_on:
        raise HTTPException(403, detail={"code": "TRY_ON_CONSENT_REQUIRED"})

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=2.0), trust_env=False, follow_redirects=False
    ) as client:
        subject, _ = await _verified_commerce_subject(client, request)
        wardrobe_base, wardrobe_token = _wardrobe_service()
        try:
            item_response = await client.get(
                wardrobe_base + f"/v1/items/{item_id}",
                params={"owner_user_id": subject},
                headers={"Authorization": "Bearer " + wardrobe_token, "Accept": "application/json"},
            )
        except httpx.TimeoutException as exc:
            raise HTTPException(504, detail={"code": "WARDROBE_ITEM_LOOKUP_TIMEOUT"}) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "WARDROBE_ITEM_LOOKUP_UNAVAILABLE"}) from exc

        if item_response.status_code in {403, 404}:
            raise HTTPException(404, detail={"code": "WARDROBE_ITEM_NOT_FOUND"})
        if item_response.status_code != 200:
            raise HTTPException(503, detail={"code": "WARDROBE_ITEM_LOOKUP_UNAVAILABLE"})
        try:
            item_payload = item_response.json()
        except ValueError as exc:
            raise HTTPException(502, detail={"code": "WARDROBE_ITEM_RESPONSE_INVALID"}) from exc
        item = item_payload.get("item") if isinstance(item_payload, dict) else None
        if not isinstance(item, dict) or item.get("owner_user_id") != subject or item.get("item_id") != item_id:
            raise HTTPException(502, detail={"code": "WARDROBE_ITEM_SCOPE_MISMATCH"})
        if item.get("status") != "active":
            raise HTTPException(409, detail={"code": "WARDROBE_ITEM_NOT_ACTIVE"})
        garment_asset_id = item.get("image_asset_id")
        if item.get("image_storage_consent") is not True or not isinstance(garment_asset_id, str) or not UUID_RE.fullmatch(garment_asset_id):
            raise HTTPException(409, detail={"code": "WARDROBE_ITEM_PRIVATE_IMAGE_NOT_READY"})

        category = str(item.get("category", "")).strip().lower().replace("-", "_").replace(" ", "_")
        category_map = {
            "upper_body": "upper_body", "top": "upper_body", "tops": "upper_body",
            "shirt": "upper_body", "shirts": "upper_body", "blouse": "upper_body",
            "blouses": "upper_body", "sweater": "upper_body", "sweaters": "upper_body",
            "lower_body": "lower_body", "bottom": "lower_body", "bottoms": "lower_body",
            "trousers": "lower_body", "pants": "lower_body", "jeans": "lower_body",
            "shorts": "lower_body", "skirt": "lower_body", "skirts": "lower_body",
            "dress": "dress", "dresses": "dress",
            "outerwear": "outerwear", "jacket": "outerwear", "jackets": "outerwear",
            "coat": "outerwear", "coats": "outerwear",
            "full_outfit": "full_outfit",
        }
        garment_category = category_map.get(category)
        if garment_category is None:
            raise HTTPException(422, detail={"code": "WARDROBE_CATEGORY_NOT_SUPPORTED_FOR_TRY_ON"})

        try:
            vton_base, vton_token = _internal_service("VIRTUAL_TRY_ON_API_URL", "VIRTUAL_TRY_ON_API_TOKEN")
        except HTTPException:
            raise
        body = {
            "request_id": payload.request_id.strip() if payload.request_id else str(uuid.uuid4()),
            "subject_id": subject,
            "twin_id": payload.twin_id.strip(),
            "product_id": "wardrobe:" + item_id,
            "person_image_asset_id": payload.person_image_asset_id,
            "garment_image_asset_id": garment_asset_id.lower(),
            "garment_asset_purpose": "wardrobe_garment_image",
            "garment_asset_parent_id": item_id,
            "garment_category": garment_category,
            "look_id": payload.look_id,
            "look_version": payload.look_version,
            "wardrobe_snapshot_version": payload.wardrobe_snapshot_version,
            "consent": {
                "consent_id": payload.consent_id.strip(),
                "image_processing": True,
                "virtual_try_on": True,
                "retention_policy": "ephemeral",
            },
        }
        try:
            response = await client.post(
                vton_base + "/v1/try-ons",
                headers={"Authorization": "Bearer " + vton_token, "Accept": "application/json"},
                json=body,
            )
        except httpx.TimeoutException as exc:
            raise HTTPException(504, detail={"code": "VIRTUAL_TRY_ON_TIMEOUT"}) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "VIRTUAL_TRY_ON_UNAVAILABLE"}) from exc

    if response.status_code in {400, 403, 404, 409, 413, 415, 422}:
        try:
            detail = response.json().get("detail", {})
            if not isinstance(detail, dict):
                detail = {"code": "VIRTUAL_TRY_ON_REJECTED"}
        except ValueError:
            detail = {"code": "VIRTUAL_TRY_ON_REJECTED"}
        raise HTTPException(response.status_code, detail=detail)
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "VIRTUAL_TRY_ON_UNAVAILABLE"})
    try:
        result = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "VIRTUAL_TRY_ON_RESPONSE_INVALID"}) from exc
    if (
        not isinstance(result, dict)
        or result.get("status") != "complete"
        or result.get("request_id") != body["request_id"]
        or not isinstance(result.get("output_asset_id"), str)
        or not UUID_RE.fullmatch(result["output_asset_id"])
    ):
        raise HTTPException(502, detail={"code": "VIRTUAL_TRY_ON_RESPONSE_INVALID"})
    return _private_json_response(result)


@app.patch("/api/wardrobe/items/{item_id}")
async def edit_wardrobe_item(request: Request, item_id: str, payload: EditWardrobeItemIn) -> Response:
    """Edit exactly one wardrobe item for the Commerce-verified user."""
    changes = payload.model_dump(exclude_unset=True)
    editable = {key: value for key, value in changes.items() if key not in {"expected_version", "command_id"}}
    if not editable or all(value is None for value in editable.values()):
        raise HTTPException(422, detail={"code": "WARDROBE_EDIT_EMPTY"})
    if "display_name" in editable and editable["display_name"] is not None:
        editable["display_name"] = editable["display_name"].strip()
        if not editable["display_name"]:
            raise HTTPException(422, detail={"code": "WARDROBE_DISPLAY_NAME_EMPTY"})
    if "category" in editable and editable["category"] is not None:
        editable["category"] = editable["category"].strip()
        if not editable["category"]:
            raise HTTPException(422, detail={"code": "WARDROBE_CATEGORY_EMPTY"})
    if "attributes" in editable and editable["attributes"] is not None:
        editable["attributes"] = [value.strip() for value in editable["attributes"]]
        if any(not value for value in editable["attributes"]) or len(set(editable["attributes"])) != len(editable["attributes"]):
            raise HTTPException(422, detail={"code": "WARDROBE_ATTRIBUTES_INVALID"})
    body = {
        "owner_user_id": None,
        "expected_version": payload.expected_version,
        "command_id": payload.command_id.strip(),
        **editable,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=2.0), trust_env=False, follow_redirects=False) as client:
        subject, _ = await _verified_commerce_subject(client, request)
        base, token = _wardrobe_service()
        body["owner_user_id"] = subject
        try:
            response = await client.patch(
                base + f"/v1/items/{item_id}",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json=body,
            )
        except httpx.TimeoutException as exc:
            raise HTTPException(504, detail={"code": "WARDROBE_ITEM_EDIT_TIMEOUT"}) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "WARDROBE_ITEM_EDIT_UNAVAILABLE"}) from exc
    if response.status_code in {400, 403, 404, 409, 422}:
        try:
            detail = response.json().get("detail", {})
            if not isinstance(detail, dict):
                detail = {"code": "WARDROBE_ITEM_EDIT_REJECTED"}
        except ValueError:
            detail = {"code": "WARDROBE_ITEM_EDIT_REJECTED"}
        raise HTTPException(response.status_code, detail=detail)
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "WARDROBE_ITEM_EDIT_UNAVAILABLE"})
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "WARDROBE_ITEM_EDIT_RESPONSE_INVALID"}) from exc
    item = data.get("item") if isinstance(data, dict) else None
    if not isinstance(item, dict) or item.get("owner_user_id") != subject or item.get("item_id") != item_id:
        raise HTTPException(502, detail={"code": "WARDROBE_ITEM_EDIT_SCOPE_MISMATCH"})
    return _private_json_response({"item": item, "status": data.get("status", "updated")})


@app.get("/api/wardrobe/categories")
async def get_wardrobe_categories(request: Request) -> Response:
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=2.0), trust_env=False, follow_redirects=False) as client:
        await _verified_commerce_subject(client, request)
        base, token = _wardrobe_service()
        try:
            response = await client.get(
                base + "/v1/categories",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "WARDROBE_CATEGORY_SERVICE_UNAVAILABLE"}) from exc
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "WARDROBE_CATEGORY_SERVICE_UNAVAILABLE"})
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "WARDROBE_CATEGORY_RESPONSE_INVALID"}) from exc
    if not isinstance(data, dict) or not isinstance(data.get("taxonomy_version"), str) or not isinstance(data.get("categories"), list):
        raise HTTPException(502, detail={"code": "WARDROBE_CATEGORY_RESPONSE_INVALID"})
    if any(not isinstance(item, dict) or not all(isinstance(item.get(key), str) for key in ("id", "label", "group")) for item in data["categories"]):
        raise HTTPException(502, detail={"code": "WARDROBE_CATEGORY_RESPONSE_INVALID"})
    return _private_json_response(data)


@app.get("/api/wardrobe/outfits")
async def list_wardrobe_outfits(request: Request) -> Response:
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=2.0), trust_env=False, follow_redirects=False) as client:
        subject, _ = await _verified_commerce_subject(client, request)
        base, token = _wardrobe_service()
        try:
            response = await client.get(
                base + "/v1/outfits", params={"owner_user_id": subject},
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "WARDROBE_OUTFIT_SERVICE_UNAVAILABLE"}) from exc
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "WARDROBE_OUTFIT_SERVICE_UNAVAILABLE"})
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "WARDROBE_OUTFIT_RESPONSE_INVALID"}) from exc
    if not isinstance(data, dict):
        raise HTTPException(502, detail={"code": "WARDROBE_OUTFIT_RESPONSE_INVALID"})
    outfits = data.get("outfits")
    if data.get("owner_user_id") != subject or not isinstance(outfits, list) or any(
        not isinstance(outfit, dict) or outfit.get("owner_user_id") != subject
        or not isinstance(outfit.get("pieces"), list)
        for outfit in outfits
    ):
        raise HTTPException(502, detail={"code": "WARDROBE_OUTFIT_SCOPE_MISMATCH"})
    return _private_json_response(data)


@app.post("/api/wardrobe/outfits", status_code=201)
async def create_wardrobe_outfit(request: Request, payload: CreateWardrobeOutfitIn) -> Response:
    item_ids = [value.strip() for value in payload.wardrobe_item_ids]
    if len(set(item_ids)) != len(item_ids):
        raise HTTPException(422, detail={"code": "OUTFIT_ITEM_DUPLICATE"})
    body = {
        "outfit_id": str(uuid.uuid4()),
        "name": payload.name.strip(),
        "pieces": [{"slot_id": str(uuid.uuid4()), "wardrobe_item_id": item_id} for item_id in item_ids],
    }
    if not body["name"]:
        raise HTTPException(422, detail={"code": "OUTFIT_NAME_EMPTY"})
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=2.0), trust_env=False, follow_redirects=False) as client:
        subject, _ = await _verified_commerce_subject(client, request)
        base, token = _wardrobe_service()
        body["owner_user_id"] = subject
        try:
            response = await client.post(base + "/v1/outfits", headers={"Authorization": "Bearer " + token}, json=body)
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "WARDROBE_OUTFIT_CREATE_UNAVAILABLE"}) from exc
    if response.status_code in {400, 403, 404, 409, 422}:
        try:
            detail = response.json().get("detail", {})
        except ValueError:
            detail = {"code": "WARDROBE_OUTFIT_CREATE_REJECTED"}
        raise HTTPException(response.status_code, detail=detail)
    if response.status_code != 201:
        raise HTTPException(503, detail={"code": "WARDROBE_OUTFIT_CREATE_UNAVAILABLE"})
    data = response.json()
    outfit = data.get("outfit") if isinstance(data, dict) else None
    if not isinstance(outfit, dict) or outfit.get("owner_user_id") != subject:
        raise HTTPException(502, detail={"code": "WARDROBE_OUTFIT_SCOPE_MISMATCH"})
    return _private_json_response(data, status_code=201)


@app.post("/api/wardrobe/looks/wear", status_code=201)
async def record_pnelly_look_worn(request: Request, payload: RecordPNELLYLookWearIn) -> Response:
    """Persist a user-confirmed look wear event; never infer wear from recommendation exposure."""
    item_ids = [value.strip() for value in payload.item_ids]
    if any(not item_id for item_id in item_ids) or len(set(item_ids)) != len(item_ids):
        raise HTTPException(422, detail={"code": "PNELLY_WEAR_ITEM_IDS_INVALID"})
    if not payload.name.strip():
        raise HTTPException(422, detail={"code": "PNELLY_WEAR_OUTFIT_NAME_REQUIRED"})
    async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=2.0), trust_env=False, follow_redirects=False) as client:
        subject, _ = await _verified_commerce_subject(client, request)
        wardrobe_base, wardrobe_token = _wardrobe_service()
        headers = {"Authorization": "Bearer " + wardrobe_token, "Accept": "application/json"}
        try:
            items_response = await client.get(
                wardrobe_base + "/v1/items",
                params={"owner_user_id": subject, "include_archived": "false"},
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "PNELLY_WEAR_WARDROBE_UNAVAILABLE"}) from exc
        if items_response.status_code != 200:
            raise HTTPException(503, detail={"code": "PNELLY_WEAR_WARDROBE_UNAVAILABLE"})
        try:
            items_data = items_response.json()
        except ValueError as exc:
            raise HTTPException(502, detail={"code": "PNELLY_WEAR_WARDROBE_INVALID"}) from exc
        if (
            not isinstance(items_data, dict)
            or items_data.get("owner_user_id") != subject
            or not isinstance(items_data.get("items"), list)
        ):
            raise HTTPException(502, detail={"code": "PNELLY_WEAR_WARDROBE_SCOPE_MISMATCH"})
        active_items = {
            item.get("item_id"): item for item in items_data["items"]
            if isinstance(item, dict)
            and item.get("owner_user_id") == subject
            and item.get("status") == "active"
            and isinstance(item.get("item_id"), str)
        }
        if any(item_id not in active_items for item_id in item_ids):
            raise HTTPException(422, detail={"code": "PNELLY_WEAR_ITEM_NOT_ACTIVE_OR_NOT_OWNED"})

        # Stable outfit and slot IDs make repeated client submissions idempotent.
        outfit_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"cirvanna:pnelly-wear:{subject}:{payload.event_id}"))
        pieces = [
            {
                "slot_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"cirvanna:pnelly-wear-slot:{subject}:{payload.event_id}:{item_id}")),
                "wardrobe_item_id": item_id,
            }
            for item_id in item_ids
        ]
        create_body = {
            "owner_user_id": subject,
            "outfit_id": outfit_id,
            "name": payload.name.strip(),
            "pieces": pieces,
        }
        try:
            create_response = await client.post(
                wardrobe_base + "/v1/outfits", headers=headers, json=create_body,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "PNELLY_WEAR_OUTFIT_CREATE_UNAVAILABLE"}) from exc

        if create_response.status_code == 201:
            try:
                outfit_data = create_response.json().get("outfit")
            except (ValueError, AttributeError) as exc:
                raise HTTPException(502, detail={"code": "PNELLY_WEAR_OUTFIT_RESPONSE_INVALID"}) from exc
        elif create_response.status_code in {409, 503}:
            # A retry may arrive after the deterministic outfit was created. The
            # Wardrobe service may surface a duplicate-key write as 503; only an
            # owner-matched persisted outfit allows this request to be replayed.
            try:
                list_response = await client.get(
                    wardrobe_base + "/v1/outfits",
                    params={"owner_user_id": subject},
                    headers=headers,
                )
                listed = list_response.json() if list_response.status_code == 200 else None
                existing = next(
                    (outfit for outfit in listed.get("outfits", [])
                     if isinstance(outfit, dict) and outfit.get("outfit_id") == outfit_id),
                    None,
                ) if isinstance(listed, dict) else None
            except (httpx.HTTPError, ValueError) as exc:
                raise HTTPException(503, detail={"code": "PNELLY_WEAR_OUTFIT_RELOAD_UNAVAILABLE"}) from exc
            if not isinstance(existing, dict):
                raise HTTPException(409, detail={"code": "PNELLY_WEAR_OUTFIT_CREATE_CONFLICT"})
            existing_ids = [
                piece.get("wardrobe_item_id") for piece in existing.get("pieces", [])
                if isinstance(piece, dict)
            ]
            if existing.get("owner_user_id") != subject or existing_ids != item_ids:
                raise HTTPException(409, detail={"code": "PNELLY_WEAR_OUTFIT_IDEMPOTENCY_CONFLICT"})
            outfit_data = existing
        else:
            raise HTTPException(503, detail={"code": "PNELLY_WEAR_OUTFIT_CREATE_UNAVAILABLE"})

        if (
            not isinstance(outfit_data, dict)
            or outfit_data.get("owner_user_id") != subject
            or outfit_data.get("outfit_id") != outfit_id
            or not isinstance(outfit_data.get("version"), int)
            or outfit_data["version"] < 1
        ):
            raise HTTPException(502, detail={"code": "PNELLY_WEAR_OUTFIT_SCOPE_MISMATCH"})
        wear_body = {
            "owner_user_id": subject,
            "event_id": payload.event_id.strip(),
            "expected_outfit_version": outfit_data["version"],
            "consent_receipt_id": payload.consent_receipt_id.strip(),
            "observed_at": payload.observed_at,
            "context": payload.context,
        }
        try:
            wear_response = await client.post(
                wardrobe_base + f"/v1/outfits/{outfit_id}/wear",
                headers=headers, json=wear_body,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "PNELLY_WEAR_EVENT_UNAVAILABLE"}) from exc
    if wear_response.status_code in {401, 403, 404, 409, 422}:
        try:
            detail = wear_response.json().get("detail", {})
        except ValueError:
            detail = {"code": "PNELLY_WEAR_EVENT_REJECTED"}
        raise HTTPException(wear_response.status_code, detail=detail)
    if wear_response.status_code != 201:
        raise HTTPException(503, detail={"code": "PNELLY_WEAR_EVENT_UNAVAILABLE"})
    try:
        wear_data = wear_response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "PNELLY_WEAR_EVENT_RESPONSE_INVALID"}) from exc
    snapshot = wear_data.get("items") if isinstance(wear_data, dict) else None
    if (
        not isinstance(wear_data, dict)
        or wear_data.get("event_id") != payload.event_id
        or not isinstance(snapshot, list)
        or [item.get("item_id") for item in snapshot if isinstance(item, dict)] != item_ids
    ):
        raise HTTPException(502, detail={"code": "PNELLY_WEAR_EVENT_SCOPE_MISMATCH"})
    return _private_json_response({
        "status": wear_data.get("status", "recorded"),
        "event_id": payload.event_id,
        "outfit_id": outfit_id,
        "outfit_version": wear_data.get("outfit_version", outfit_data["version"]),
        "items": snapshot,
        "delivery": wear_data.get("delivery", []),
    }, status_code=201)


@app.post("/api/wardrobe/outfits/{outfit_id}/pieces", status_code=201)
async def add_wardrobe_outfit_piece(request: Request, outfit_id: str, payload: AddWardrobeOutfitPieceIn) -> Response:
    body = payload.model_dump()
    body["slot_id"] = str(uuid.uuid4())
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=2.0), trust_env=False, follow_redirects=False) as client:
        subject, _ = await _verified_commerce_subject(client, request)
        base, token = _wardrobe_service()
        body["owner_user_id"] = subject
        try:
            response = await client.post(
                base + f"/v1/outfits/{outfit_id}/pieces",
                headers={"Authorization": "Bearer " + token}, json=body,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "WARDROBE_OUTFIT_EDIT_UNAVAILABLE"}) from exc
    if response.status_code in {400, 403, 404, 409, 422}:
        try:
            detail = response.json().get("detail", {})
        except ValueError:
            detail = {"code": "WARDROBE_OUTFIT_EDIT_REJECTED"}
        raise HTTPException(response.status_code, detail=detail)
    if response.status_code != 201:
        raise HTTPException(503, detail={"code": "WARDROBE_OUTFIT_EDIT_UNAVAILABLE"})
    data = response.json()
    outfit = data.get("outfit") if isinstance(data, dict) else None
    if not isinstance(outfit, dict) or outfit.get("owner_user_id") != subject:
        raise HTTPException(502, detail={"code": "WARDROBE_OUTFIT_SCOPE_MISMATCH"})
    return _private_json_response(data, status_code=201)


@app.patch("/api/wardrobe/outfits/{outfit_id}/pieces/{slot_id}")
async def edit_wardrobe_outfit_piece(request: Request, outfit_id: str, slot_id: str, payload: EditWardrobeOutfitPieceIn) -> Response:
    if "wardrobe_item_id" not in payload.model_fields_set:
        raise HTTPException(422, detail={"code": "OUTFIT_PIECE_ACTION_REQUIRED"})
    body = payload.model_dump()
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=2.0), trust_env=False, follow_redirects=False) as client:
        subject, _ = await _verified_commerce_subject(client, request)
        base, token = _wardrobe_service()
        body["owner_user_id"] = subject
        try:
            response = await client.patch(
                base + f"/v1/outfits/{outfit_id}/pieces/{slot_id}",
                headers={"Authorization": "Bearer " + token}, json=body,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "WARDROBE_OUTFIT_EDIT_UNAVAILABLE"}) from exc
    if response.status_code in {400, 403, 404, 409, 422}:
        try:
            detail = response.json().get("detail", {})
        except ValueError:
            detail = {"code": "WARDROBE_OUTFIT_EDIT_REJECTED"}
        raise HTTPException(response.status_code, detail=detail)
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "WARDROBE_OUTFIT_EDIT_UNAVAILABLE"})
    data = response.json()
    outfit = data.get("outfit") if isinstance(data, dict) else None
    if not isinstance(outfit, dict) or outfit.get("owner_user_id") != subject:
        raise HTTPException(502, detail={"code": "WARDROBE_OUTFIT_SCOPE_MISMATCH"})
    return _private_json_response(data)


@app.get("/api/wardrobe/learning/export")
async def export_wardrobe_learning_data(request: Request) -> Response:
    """Return the signed-in user's TAL, NPL and Wardrobe feedback records."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=2.0), trust_env=False, follow_redirects=False) as client:
        subject, user_token = await _verified_commerce_subject(client, request)
        gateway_base, gateway_token = _decision_gateway()
        try:
            gateway_response = await client.get(
                gateway_base + "/v1/me/learning/export",
                headers={
                    "Authorization": "Bearer " + gateway_token,
                    "X-End-User-Authorization": "Bearer " + user_token,
                    "Accept": "application/json",
                },
            )
        except httpx.TimeoutException as exc:
            raise HTTPException(504, detail={"code": "LEARNING_EXPORT_TIMEOUT"}) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "LEARNING_EXPORT_UNAVAILABLE"}) from exc
        if gateway_response.status_code != 200:
            try:
                detail = gateway_response.json().get("detail", {})
                code = detail.get("code") if isinstance(detail, dict) else None
            except ValueError:
                code = None
            raise HTTPException(
                gateway_response.status_code if gateway_response.status_code in {401, 403} else 503,
                detail={"code": code or "LEARNING_EXPORT_UNAVAILABLE"},
            )
        try:
            learning = gateway_response.json()
        except ValueError as exc:
            raise HTTPException(502, detail={"code": "LEARNING_EXPORT_RESPONSE_INVALID"}) from exc
        if (
            not isinstance(learning, dict)
            or learning.get("subject_id") != subject
            or not isinstance(learning.get("tal"), dict)
            or not isinstance(learning.get("npl"), dict)
            or learning["npl"].get("user_id") != subject
        ):
            raise HTTPException(502, detail={"code": "LEARNING_EXPORT_SCOPE_MISMATCH"})

        wardrobe_base, wardrobe_token = _wardrobe_service()
        try:
            wardrobe_response = await client.get(
                wardrobe_base + "/v1/feedback",
                params={"owner_user_id": subject},
                headers={"Authorization": "Bearer " + wardrobe_token, "Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "WARDROBE_FEEDBACK_EXPORT_UNAVAILABLE"}) from exc
        if wardrobe_response.status_code != 200:
            raise HTTPException(503, detail={"code": "WARDROBE_FEEDBACK_EXPORT_UNAVAILABLE"})
        try:
            wardrobe_data = wardrobe_response.json()
        except ValueError as exc:
            raise HTTPException(502, detail={"code": "WARDROBE_FEEDBACK_EXPORT_INVALID"}) from exc
        if (
            not isinstance(wardrobe_data, dict)
            or wardrobe_data.get("owner_user_id") != subject
            or not isinstance(wardrobe_data.get("items"), list)
        ):
            raise HTTPException(502, detail={"code": "WARDROBE_FEEDBACK_EXPORT_SCOPE_MISMATCH"})

        try:
            items_response = await client.get(
                wardrobe_base + "/v1/items",
                params={"owner_user_id": subject, "include_archived": "false"},
                headers={"Authorization": "Bearer " + wardrobe_token, "Accept": "application/json"},
            )
            rotation_response = await client.get(
                wardrobe_base + "/v1/rotation-state",
                params={"owner_user_id": subject},
                headers={"Authorization": "Bearer " + wardrobe_token, "Accept": "application/json"},
            )
            wear_history_response = await client.get(
                wardrobe_base + "/v1/wear-history",
                params={"owner_user_id": subject, "limit": 100},
                headers={"Authorization": "Bearer " + wardrobe_token, "Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "WARDROBE_DATA_EXPORT_UNAVAILABLE"}) from exc
        if any(response.status_code != 200 for response in (items_response, rotation_response, wear_history_response)):
            raise HTTPException(503, detail={"code": "WARDROBE_DATA_EXPORT_UNAVAILABLE"})
        try:
            items_data = items_response.json()
            rotation_data = rotation_response.json()
            wear_history_data = wear_history_response.json()
        except ValueError as exc:
            raise HTTPException(502, detail={"code": "WARDROBE_DATA_EXPORT_INVALID"}) from exc
        if (
            not isinstance(items_data, dict)
            or items_data.get("owner_user_id") != subject
            or not isinstance(items_data.get("items"), list)
            or any(
                not isinstance(item, dict) or item.get("owner_user_id") != subject
                or item.get("status") != "active" or not isinstance(item.get("item_id"), str)
                for item in items_data.get("items", [])
            )
        ):
            raise HTTPException(502, detail={"code": "WARDROBE_ROTATION_EXPORT_SCOPE_MISMATCH"})
        active_ids = {item["item_id"] for item in items_data["items"]}
        rotation_snapshot = _parse_rotation_snapshot(
            rotation_data, subject=subject, active_item_ids=active_ids,
        )
        if (
            not isinstance(wear_history_data, dict)
            or wear_history_data.get("owner_user_id") != subject
            or not isinstance(wear_history_data.get("items"), list)
            or any(
                not isinstance(event, dict)
                or not isinstance(event.get("event_id"), str)
                or not isinstance(event.get("outfit_id"), str)
                or not isinstance(event.get("items"), list)
                or any(
                    not isinstance(piece, dict)
                    or not isinstance(piece.get("item_id"), str)
                    or isinstance(piece.get("item_version"), bool)
                    or not isinstance(piece.get("item_version"), int)
                    or piece.get("item_version") < 1
                    for piece in event.get("items", [])
                )
                for event in wear_history_data.get("items", [])
            )
        ):
            raise HTTPException(502, detail={"code": "WARDROBE_WEAR_HISTORY_EXPORT_SCOPE_MISMATCH"})

    return _private_json_response({
        "subject_id": subject,
        "export_version": 1,
        "tal": learning["tal"],
        "npl": learning["npl"],
        "wardrobe_feedback": wardrobe_data["items"],
        "wardrobe_rotation": rotation_snapshot,
        "wardrobe_wear_history": wear_history_data["items"],
    })


@app.post("/api/wardrobe/preferences/{preference_id}/retract")
async def retract_wardrobe_preference(
    preference_id: str,
    request: Request,
    payload: WardrobePreferenceRetractionIn = Body(...),
) -> Response:
    """Apply an explicit, subject-bound correction to one NPL preference."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", preference_id):
        raise HTTPException(422, detail={"code": "INVALID_NPL_PREFERENCE_ID"})
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=2.0), trust_env=False, follow_redirects=False) as client:
        _, user_token = await _verified_commerce_subject(client, request)
        gateway_base, gateway_token = _decision_gateway()
        try:
            response = await client.post(
                gateway_base + f"/v1/me/npl/preferences/{preference_id}/retract",
                headers={
                    "Authorization": "Bearer " + gateway_token,
                    "X-End-User-Authorization": "Bearer " + user_token,
                    "Accept": "application/json",
                },
                json={"correction_event_id": payload.correction_event_id.strip()},
            )
        except httpx.TimeoutException as exc:
            raise HTTPException(504, detail={"code": "NPL_CORRECTION_TIMEOUT"}) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "NPL_CORRECTION_UNAVAILABLE"}) from exc
    if response.status_code in {400, 401, 403, 404, 409, 422}:
        try:
            detail = response.json().get("detail", {})
            code = detail.get("code") if isinstance(detail, dict) else None
        except ValueError:
            code = None
        raise HTTPException(response.status_code, detail={"code": code or "NPL_CORRECTION_REJECTED"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "NPL_CORRECTION_UNAVAILABLE"})
    try:
        result = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "NPL_CORRECTION_RESPONSE_INVALID"}) from exc
    return _private_json_response(result)


@app.delete("/api/wardrobe/learning")
async def delete_wardrobe_learning_data(request: Request) -> Response:
    """Delete canonical learning first, then the Wardrobe service's local audit mirror."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=2.0), trust_env=False, follow_redirects=False) as client:
        subject, user_token = await _verified_commerce_subject(client, request)
        gateway_base, gateway_token = _decision_gateway()
        try:
            learning_response = await client.delete(
                gateway_base + "/v1/me/learning/data",
                headers={
                    "Authorization": "Bearer " + gateway_token,
                    "X-End-User-Authorization": "Bearer " + user_token,
                    "Accept": "application/json",
                },
            )
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "LEARNING_DELETE_UNAVAILABLE"}) from exc
        if learning_response.status_code != 200:
            try:
                detail = learning_response.json().get("detail", {})
                code = detail.get("code") if isinstance(detail, dict) else None
            except ValueError:
                code = None
            raise HTTPException(
                learning_response.status_code if learning_response.status_code in {401, 403} else 503,
                detail={"code": code or "LEARNING_DELETION_INCOMPLETE"},
            )

        wardrobe_base, wardrobe_token = _wardrobe_service()
        try:
            wardrobe_response = await client.delete(
                wardrobe_base + "/v1/feedback",
                params={"owner_user_id": subject},
                headers={"Authorization": "Bearer " + wardrobe_token, "Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                503,
                detail={"code": "LEARNING_DELETION_PARTIAL", "identity_and_npl_deleted": True, "wardrobe_audit_deleted": False},
            ) from exc
        if wardrobe_response.status_code != 200:
            raise HTTPException(
                503,
                detail={"code": "LEARNING_DELETION_PARTIAL", "identity_and_npl_deleted": True, "wardrobe_audit_deleted": False},
            )
        try:
            wardrobe_result = wardrobe_response.json()
        except ValueError as exc:
            raise HTTPException(
                502,
                detail={"code": "LEARNING_DELETION_PARTIAL", "identity_and_npl_deleted": True, "wardrobe_audit_deleted": False, "wardrobe_rotation_state_deleted": False},
            ) from exc
        if not isinstance(wardrobe_result, dict) or wardrobe_result.get("status") != "deleted":
            raise HTTPException(
                502,
                detail={"code": "LEARNING_DELETION_PARTIAL", "identity_and_npl_deleted": True, "wardrobe_audit_deleted": False, "wardrobe_rotation_state_deleted": False},
            )
        try:
            rotation_delete = await client.delete(
                wardrobe_base + "/v1/rotation-state",
                params={"owner_user_id": subject},
                headers={"Authorization": "Bearer " + wardrobe_token, "Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                503,
                detail={"code": "LEARNING_DELETION_PARTIAL", "identity_and_npl_deleted": True, "wardrobe_audit_deleted": True, "wardrobe_rotation_state_deleted": False},
            ) from exc
        if rotation_delete.status_code != 200:
            raise HTTPException(
                503,
                detail={"code": "LEARNING_DELETION_PARTIAL", "identity_and_npl_deleted": True, "wardrobe_audit_deleted": True, "wardrobe_rotation_state_deleted": False},
            )
        try:
            rotation_result = rotation_delete.json()
        except ValueError as exc:
            raise HTTPException(
                502,
                detail={"code": "LEARNING_DELETION_PARTIAL", "identity_and_npl_deleted": True, "wardrobe_audit_deleted": True, "wardrobe_rotation_state_deleted": False},
            ) from exc
        if not isinstance(rotation_result, dict) or rotation_result.get("status") != "deleted" or rotation_result.get("owner_user_id") != subject:
            raise HTTPException(
                502,
                detail={"code": "LEARNING_DELETION_PARTIAL", "identity_and_npl_deleted": True, "wardrobe_audit_deleted": True, "wardrobe_rotation_state_deleted": False},
            )
        try:
            wear_history_delete = await client.delete(
                wardrobe_base + "/v1/wear-history",
                params={"owner_user_id": subject},
                headers={"Authorization": "Bearer " + wardrobe_token, "Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                503,
                detail={"code": "LEARNING_DELETION_PARTIAL", "identity_and_npl_deleted": True,
                        "wardrobe_audit_deleted": True, "wardrobe_rotation_state_deleted": True,
                        "wardrobe_wear_history_deleted": False},
            ) from exc
        if wear_history_delete.status_code != 200:
            raise HTTPException(
                503,
                detail={"code": "LEARNING_DELETION_PARTIAL", "identity_and_npl_deleted": True,
                        "wardrobe_audit_deleted": True, "wardrobe_rotation_state_deleted": True,
                        "wardrobe_wear_history_deleted": False},
            )
        try:
            wear_history_result = wear_history_delete.json()
        except ValueError as exc:
            raise HTTPException(
                502,
                detail={"code": "LEARNING_DELETION_PARTIAL", "identity_and_npl_deleted": True,
                        "wardrobe_audit_deleted": True, "wardrobe_rotation_state_deleted": True,
                        "wardrobe_wear_history_deleted": False},
            ) from exc
        if not isinstance(wear_history_result, dict) or wear_history_result.get("status") != "deleted" or wear_history_result.get("owner_user_id") != subject:
            raise HTTPException(
                502,
                detail={"code": "LEARNING_DELETION_PARTIAL", "identity_and_npl_deleted": True,
                        "wardrobe_audit_deleted": True, "wardrobe_rotation_state_deleted": True,
                        "wardrobe_wear_history_deleted": False},
            )
    return _private_json_response({
        "status": "deleted",
        "identity_and_npl_deleted": True,
        "wardrobe_audit_deleted": True,
        "wardrobe_rotation_state_deleted": True,
        "wardrobe_wear_history_deleted": True,
        "deleted_wardrobe_feedback_events": wardrobe_result.get("deleted_feedback_events", 0),
        "deleted_wear_events": wear_history_result.get("deleted_wear_events", 0),
    })


@app.post("/api/wardrobe/daily-looks", include_in_schema=False)
@app.post("/api/wardrobe/pnelly/daily-looks")
async def wardrobe_daily_looks(request: Request, payload: DailyLooksIn = Body(default=DailyLooksIn())) -> Response:
    """Build daily looks and persist the verified user's rotation with bounded CAS retries."""
    request_id = str(uuid.uuid4())
    local_date = datetime.now(ZoneInfo(payload.timezone)).date().isoformat()
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(14.0, connect=2.0),
        trust_env=False,
        follow_redirects=False,
    ) as client:
        subject, user_token = await _verified_commerce_subject(client, request)
        wardrobe_base, wardrobe_token = _wardrobe_service()
        service_headers = {"Authorization": "Bearer " + wardrobe_token, "Accept": "application/json"}
        try:
            wardrobe_response = await client.get(
                wardrobe_base + "/v1/items",
                params={"owner_user_id": subject, "include_archived": "false"},
                headers=service_headers,
            )
        except httpx.TimeoutException as exc:
            raise HTTPException(504, detail={"code": "PNELLY_WARDROBE_TIMEOUT"}) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "PNELLY_WARDROBE_UNAVAILABLE"}) from exc
        if wardrobe_response.status_code != 200:
            raise HTTPException(503, detail={"code": "PNELLY_WARDROBE_UNAVAILABLE"})
        try:
            wardrobe_data = wardrobe_response.json()
        except ValueError as exc:
            raise HTTPException(502, detail={"code": "PNELLY_WARDROBE_RESPONSE_INVALID"}) from exc
        if (
            not isinstance(wardrobe_data, dict)
            or wardrobe_data.get("owner_user_id") != subject
            or not isinstance(wardrobe_data.get("items"), list)
            or any(not isinstance(item, dict) or item.get("owner_user_id") != subject
                   for item in wardrobe_data.get("items", []))
        ):
            raise HTTPException(502, detail={"code": "PNELLY_WARDROBE_SCOPE_MISMATCH"})

        active_items = []
        for item in wardrobe_data["items"]:
            if item.get("status") != "active":
                continue
            if (
                not isinstance(item.get("item_id"), str)
                or not isinstance(item.get("display_name"), str)
                or not isinstance(item.get("category"), str)
                or not isinstance(item.get("attributes", []), list)
                or any(not isinstance(value, str) for value in item.get("attributes", []))
            ):
                raise HTTPException(502, detail={"code": "PNELLY_WARDROBE_ITEM_SCHEMA_INVALID"})
            active_items.append({
                "item_id": item["item_id"],
                "owner_user_id": subject,
                "display_name": item["display_name"],
                "category": item["category"],
                "attributes": item.get("attributes", []),
                "status": "active",
            })
        if len(active_items) > 150:
            raise HTTPException(413, detail={"code": "PNELLY_WARDROBE_TOO_LARGE"})
        active_item_ids = {item["item_id"] for item in active_items}

        async def read_rotation_state() -> dict:
            try:
                state_response = await client.get(
                    wardrobe_base + "/v1/rotation-state",
                    params={"owner_user_id": subject},
                    headers=service_headers,
                )
            except httpx.HTTPError as exc:
                raise HTTPException(503, detail={"code": "PNELLY_ROTATION_STATE_UNAVAILABLE"}) from exc
            if state_response.status_code != 200:
                raise HTTPException(503, detail={"code": "PNELLY_ROTATION_STATE_UNAVAILABLE"})
            try:
                state_data = state_response.json()
            except ValueError as exc:
                raise HTTPException(502, detail={"code": "PNELLY_ROTATION_STATE_RESPONSE_INVALID"}) from exc
            return _parse_rotation_snapshot(state_data, subject=subject, active_item_ids=active_item_ids)

        rotation_snapshot = await read_rotation_state()
        gateway_base, gateway_token = _decision_gateway()
        headers = {
            "Authorization": "Bearer " + gateway_token,
            "X-End-User-Authorization": "Bearer " + user_token,
            "Accept": "application/json",
        }
        body = {
            "request_id": request_id,
            "user_id": subject,
            "local_date": local_date,
            "occasion": payload.occasion.strip() if payload.occasion and payload.occasion.strip() else None,
            "climate": payload.climate.strip() if payload.climate and payload.climate.strip() else None,
            "evaluation_consent_receipt_id": payload.evaluation_consent_receipt_id,
            "wardrobe_items": active_items,
        }
        result = None
        recommendation = None
        next_rotation = None
        for attempt in range(2):
            body["rotation_seen_item_ids"] = list(rotation_snapshot["seen_item_ids"])
            body["rotation_cycle_started_at"] = rotation_snapshot["cycle_started_at"]
            body["rotation_cycle_number"] = rotation_snapshot["cycle_number"]
            try:
                gateway_response = await client.post(
                    gateway_base + "/v1/pnelly/daily-looks",
                    headers=headers,
                    json=body,
                )
            except httpx.TimeoutException as exc:
                raise HTTPException(504, detail={"code": "PNELLY_RECOMMENDATION_TIMEOUT"}) from exc
            except httpx.HTTPError as exc:
                raise HTTPException(503, detail={"code": "PNELLY_RECOMMENDATION_UNAVAILABLE"}) from exc

            if gateway_response.status_code in {401, 403, 422}:
                try:
                    detail = gateway_response.json().get("detail", {})
                    code = detail.get("code") if isinstance(detail, dict) else None
                except ValueError:
                    code = None
                raise HTTPException(gateway_response.status_code, detail={"code": code or "PNELLY_RECOMMENDATION_REJECTED"})
            if gateway_response.status_code != 200:
                raise HTTPException(503, detail={"code": "PNELLY_RECOMMENDATION_UNAVAILABLE"})
            try:
                result = gateway_response.json()
            except ValueError as exc:
                raise HTTPException(502, detail={"code": "PNELLY_RECOMMENDATION_RESPONSE_INVALID"}) from exc

            recommendation = result.get("recommendation") if isinstance(result, dict) else None
            roles = ["everyday", "elevated", "explore"]
            looks = recommendation.get("looks") if isinstance(recommendation, dict) else None
            if (
                not isinstance(result, dict)
                or result.get("mode") != "pnelly_wardrobe_daily_looks"
                or not isinstance(recommendation, dict)
                or recommendation.get("look_count") != 3
                or not isinstance(looks, list)
                or [look.get("role") if isinstance(look, dict) else None for look in looks] != roles
                or any(
                    not isinstance(look, dict)
                    or not isinstance(look.get("virtual_twin_preview"), dict)
                    or look["virtual_twin_preview"].get("status") != "unavailable"
                    or any(key in look["virtual_twin_preview"] for key in ("asset_id", "output_asset_id", "render_id"))
                    for look in looks
                )
            ):
                raise HTTPException(502, detail={"code": "PNELLY_RECOMMENDATION_SCHEMA_INVALID"})
            next_rotation = _validate_rotation_recommendation(
                recommendation,
                active_item_ids=active_item_ids,
                prior_state=rotation_snapshot,
                local_date=local_date,
            )
            write_body = {
                "owner_user_id": subject,
                "request_id": request_id,
                "expected_version": rotation_snapshot["version"],
                "cycle_number": next_rotation["cycle_number"],
                "cycle_started_at": next_rotation["cycle_started_at"] + "T00:00:00Z",
                "surfaced_item_ids": next_rotation["seen_item_ids"],
            }
            # Retry the exact write once on a transport failure. The rotation
            # service uses request_id+payload hash to replay a committed write.
            try:
                write_response = await client.put(
                    wardrobe_base + "/v1/rotation-state",
                    headers=service_headers,
                    json=write_body,
                )
            except httpx.HTTPError:
                try:
                    write_response = await client.put(
                        wardrobe_base + "/v1/rotation-state",
                        headers=service_headers,
                        json=write_body,
                    )
                except httpx.HTTPError as exc:
                    raise HTTPException(503, detail={"code": "PNELLY_ROTATION_STATE_WRITE_UNAVAILABLE"}) from exc

            if write_response.status_code == 409 and attempt == 0:
                # A concurrent daily-look request won the compare-and-swap.
                # Reload and recompose; never merge stale exposure sets.
                rotation_snapshot = await read_rotation_state()
                continue
            if write_response.status_code == 409:
                raise HTTPException(409, detail={"code": "PNELLY_ROTATION_STATE_CONFLICT"})
            if write_response.status_code != 200:
                raise HTTPException(503, detail={"code": "PNELLY_ROTATION_STATE_WRITE_UNAVAILABLE"})
            try:
                saved = write_response.json()
                saved_state = saved.get("state") if isinstance(saved, dict) else None
                saved_version = saved.get("version") if isinstance(saved, dict) else None
            except ValueError as exc:
                raise HTTPException(502, detail={"code": "PNELLY_ROTATION_STATE_WRITE_RESPONSE_INVALID"}) from exc
            if (
                not isinstance(saved, dict)
                or not isinstance(saved_state, dict)
                or saved_state.get("owner_user_id") != subject
                or saved_state.get("cycle_number") != next_rotation["cycle_number"]
                or saved_state.get("surfaced_item_ids") != next_rotation["seen_item_ids"]
                or not isinstance(saved_version, int)
                or saved_version < 1
                or saved_state.get("version") != saved_version
            ):
                raise HTTPException(502, detail={"code": "PNELLY_ROTATION_STATE_WRITE_RESPONSE_INVALID"})
            break
        else:
            raise HTTPException(409, detail={"code": "PNELLY_ROTATION_STATE_CONFLICT"})

    # Internal evaluation traces are available only to server-side study collection,
    # never to browser sessions.
    public_result = dict(result)
    public_recommendation = dict(recommendation)
    public_recommendation.pop("evaluation_trace", None)
    public_result["recommendation"] = public_recommendation
    return _private_json_response(public_result)


async def _record_look_it_consent(
    client: httpx.AsyncClient, *, base: str, token: str, subject: str,
    receipt_id: str, consent_id: str, resource_id: str, scope: str,
    expires_at: str, consent_version: str,
) -> None:
    response = await client.post(
        base + "/v1/tal/consents",
        params={"subject_id": subject},
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
        json={
            "receipt_id": receipt_id, "consent_id": consent_id,
            "resource_id": resource_id, "scope": scope,
            "consent_version": consent_version, "granted": True,
            "expires_at": expires_at,
        },
    )
    if response.status_code not in {200, 201}:
        raise HTTPException(503, detail={"code": "LOOK_IT_CONSENT_WRITE_FAILED"})
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "LOOK_IT_CONSENT_RESPONSE_INVALID"}) from exc
    if not (
        isinstance(data, dict) and data.get("receipt_id") == receipt_id
        and data.get("consent_id") == consent_id and data.get("resource_id") == resource_id
        and data.get("granted") is True
    ):
        raise HTTPException(502, detail={"code": "LOOK_IT_CONSENT_SCOPE_MISMATCH"})


async def _verify_look_it_bundle(
    client: httpx.AsyncClient, *, base: str, token: str, subject: str,
    consent_id: str, resource_id: str, consent_version: str,
) -> None:
    response = await client.post(
        base + "/internal/v1/consents/verify",
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
        json={
            "subject_id": subject, "consent_id": consent_id,
            "resource_id": resource_id, "consent_version": consent_version,
            "required_scopes": ["image_processing", "look_it"],
        },
    )
    if response.status_code != 200:
        raise HTTPException(403, detail={"code": "LOOK_IT_CONSENT_NOT_VERIFIED"})
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "LOOK_IT_CONSENT_VERIFY_RESPONSE_INVALID"}) from exc
    scopes = data.get("granted_scopes") if isinstance(data, dict) else None
    expires_at = data.get("expires_at") if isinstance(data, dict) else None
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00")) if isinstance(expires_at, str) else None
    except ValueError:
        expiry = None
    if expiry is not None and (expiry.tzinfo is None or expiry.utcoffset() is None):
        expiry = None
    if not (
        isinstance(data, dict) and data.get("verified") is True and data.get("active") is True
        and data.get("subject_id") == subject and data.get("consent_id") == consent_id
        and data.get("resource_id") == resource_id and data.get("consent_version") == consent_version
        and isinstance(scopes, list) and {"image_processing", "look_it"}.issubset(set(scopes))
        and expiry is not None and expiry.astimezone(timezone.utc) > datetime.now(timezone.utc)
    ):
        raise HTTPException(403, detail={"code": "LOOK_IT_CONSENT_NOT_VERIFIED"})


@app.post("/api/vision/look-it")
async def marketplace_look_it(request: Request) -> Response:
    """Authenticate before multipart parsing; process a short-lived, consented Look It request."""
    authorization = request.headers.get("authorization", "")
    scheme, _, supplied_token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not supplied_token.strip():
        raise HTTPException(401, detail={"code": "USER_BEARER_REQUIRED"}, headers={"WWW-Authenticate": "Bearer"})

    form = None
    reference_image: StarletteUploadFile | None = None
    consent_receipt_ids: list[str] = []
    operation_error: HTTPException | None = None
    revoke_failed = False
    upstream_payload: dict | None = None
    subject: str | None = None
    identity_base: str | None = None
    identity_token: str | None = None

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(35.0, connect=3.0),
            trust_env=False,
            follow_redirects=False,
        ) as client:
            try:
                # Commerce /me is checked before request.form() parses or spools the upload.
                subject, _user_token = await _verified_commerce_subject(client, request)
                try:
                    form = await request.form(max_files=1, max_fields=8)
                except Exception as exc:
                    raise HTTPException(400, detail={"code": "LOOK_IT_MULTIPART_INVALID"}) from exc
                image_consent = str(form.get("consent_image_processing", "")).strip().lower() == "true"
                look_it_consent = str(form.get("consent_look_it", "")).strip().lower() == "true"
                if not image_consent or not look_it_consent:
                    raise HTTPException(403, detail={"code": "EXPLICIT_LOOK_IT_CONSENT_REQUIRED"})
                uploaded = form.get("reference_image")
                if not isinstance(uploaded, StarletteUploadFile):
                    raise HTTPException(422, detail={"code": "LOOK_IT_IMAGE_REQUIRED"})
                reference_image = uploaded
                content_type = (reference_image.content_type or "").lower()
                if content_type not in {"image/jpeg", "image/png", "image/webp"}:
                    raise HTTPException(415, detail={"code": "UNSUPPORTED_LOOK_IT_IMAGE_TYPE"})
                if reference_image.size is not None and reference_image.size > MAX_VISION_IMAGE_BYTES:
                    raise HTTPException(413, detail={"code": "LOOK_IT_IMAGE_SIZE_LIMIT_EXCEEDED"})

                identity_base, identity_token = _identity_learning_service()
                pnelly_base, pnelly_token = _pnelly_internal_service()
                consent_id = str(uuid.uuid4())
                resource_id = "look-it-" + str(uuid.uuid4())
                consent_version = "pnelly-look-it-2026-11-v1"
                expires_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()

                for scope in ("image_processing", "look_it"):
                    receipt_id = str(uuid.uuid4())
                    # Track before write: a network failure may follow a committed receipt.
                    consent_receipt_ids.append(receipt_id)
                    await _record_look_it_consent(
                        client,
                        base=identity_base,
                        token=identity_token,
                        subject=subject,
                        receipt_id=receipt_id,
                        consent_id=consent_id,
                        resource_id=resource_id,
                        scope=scope,
                        expires_at=expires_at,
                        consent_version=consent_version,
                    )
                await _verify_look_it_bundle(
                    client,
                    base=identity_base,
                    token=identity_token,
                    subject=subject,
                    consent_id=consent_id,
                    resource_id=resource_id,
                    consent_version=consent_version,
                )

                content = await reference_image.read(MAX_VISION_IMAGE_BYTES + 1)
                if not content:
                    raise HTTPException(400, detail={"code": "EMPTY_LOOK_IT_IMAGE"})
                if len(content) > MAX_VISION_IMAGE_BYTES:
                    raise HTTPException(413, detail={"code": "LOOK_IT_IMAGE_SIZE_LIMIT_EXCEEDED"})

                fields = {
                    "subject_id": subject,
                    "consent_id": consent_id,
                    "resource_id": resource_id,
                    "consent_image_processing": "true",
                    "consent_look_it": "true",
                    "limit": "10",
                }
                # The category is an optional hint; only accept a bounded string.
                category = form.get("category")
                if isinstance(category, str) and category.strip():
                    fields["category"] = category.strip()[:80]
                upstream = await client.post(
                    pnelly_base + "/v1/marketplace/search/image",
                    headers={"Authorization": "Bearer " + pnelly_token, "Accept": "application/json"},
                    data=fields,
                    files={"image": (reference_image.filename or "look-it-reference", content, content_type)},
                )
                if upstream.status_code != 200:
                    code = "LOOK_IT_SEARCH_FAILED"
                    try:
                        detail = upstream.json().get("detail", {})
                        if isinstance(detail, dict) and isinstance(detail.get("code"), str):
                            code = detail["code"]
                    except (ValueError, AttributeError):
                        pass
                    if upstream.status_code in {400, 403, 413, 415, 422}:
                        raise HTTPException(upstream.status_code, detail={"code": code})
                    raise HTTPException(503 if upstream.status_code in {502, 503, 504} else 502, detail={"code": code})
                try:
                    data = upstream.json()
                except ValueError as exc:
                    raise HTTPException(502, detail={"code": "LOOK_IT_RESPONSE_INVALID"}) from exc
                if not (
                    isinstance(data, dict)
                    and data.get("status") == "complete"
                    and data.get("display_authorized") is False
                    and data.get("decision_status") == "PENDING_CAL"
                    and data.get("image_persisted") is False
                    and isinstance(data.get("candidate_count"), int)
                    and isinstance(data.get("outfit_decomposition"), dict)
                ):
                    raise HTTPException(502, detail={"code": "LOOK_IT_RESPONSE_INVALID"})
                upstream_payload = data
            except HTTPException as exc:
                operation_error = exc
            except httpx.TimeoutException:
                operation_error = HTTPException(504, detail={"code": "LOOK_IT_OPERATION_TIMEOUT"})
            except httpx.HTTPError:
                operation_error = HTTPException(503, detail={"code": "LOOK_IT_OPERATION_UNAVAILABLE"})
            finally:
                if consent_receipt_ids and subject and identity_base and identity_token:
                    try:
                        revoked = await client.post(
                            identity_base + f"/v1/tal/consents/{consent_receipt_ids[0]}/revoke",
                            params={"subject_id": subject},
                            headers={"Authorization": "Bearer " + identity_token, "Accept": "application/json"},
                        )
                        revoke_failed = revoked.status_code != 200
                    except (httpx.TimeoutException, httpx.HTTPError):
                        revoke_failed = True
    finally:
        if form is not None:
            await form.close()
        elif reference_image is not None:
            await reference_image.close()

    if revoke_failed:
        raise HTTPException(503, detail={"code": "LOOK_IT_CONSENT_REVOCATION_FAILED"})
    if operation_error is not None:
        raise operation_error
    if not isinstance(upstream_payload, dict):
        raise HTTPException(502, detail={"code": "LOOK_IT_RESPONSE_INVALID"})

    decomposition = upstream_payload["outfit_decomposition"]
    components = decomposition.get("components")
    if not isinstance(components, list):
        raise HTTPException(502, detail={"code": "LOOK_IT_DECOMPOSITION_RESPONSE_INVALID"})
    safe_components = []
    for component in components:
        if not isinstance(component, dict):
            raise HTTPException(502, detail={"code": "LOOK_IT_DECOMPOSITION_RESPONSE_INVALID"})
        description = component.get("description")
        category_value = component.get("category")
        count = component.get("candidate_count", 0)
        if (
            not isinstance(description, str) or not 3 <= len(description) <= 500
            or not isinstance(category_value, str) or not category_value
            or isinstance(count, bool) or not isinstance(count, int) or count < 0
        ):
            raise HTTPException(502, detail={"code": "LOOK_IT_DECOMPOSITION_RESPONSE_INVALID"})
        safe_components.append({"category": category_value, "description": description, "candidate_count": count})

    candidate_count = upstream_payload["candidate_count"]
    if isinstance(candidate_count, bool) or not isinstance(candidate_count, int) or candidate_count < 0:
        raise HTTPException(502, detail={"code": "LOOK_IT_RESPONSE_INVALID"})
    return _private_json_response({
        "status": "complete",
        "search_mode": "pnelly_look_it_image_to_catalog_text_similarity",
        "candidate_count": candidate_count,
        "scores_are_probabilities": False,
        "image_persisted": False,
        "display_authorized": False,
        "decision_status": "PENDING_CAL",
        "outfit_decomposition": {
            "status": decomposition.get("status"),
            "reason": decomposition.get("reason"),
            "components": safe_components,
        },
        "merchant_comparison": {
            "status": "pending_cal",
            "reason": "CAL_AUTHORIZATION_REQUIRED_BEFORE_PRODUCT_OR_OFFER_DETAILS",
            "landed_cost_included": False,
        },
        "notice": "No product or offer details are returned by Look It. CAL, NPL and explicit cultural-identity checks must authorize display before Commerce comparison.",
    })


@app.post("/api/vision/click-it")
async def marketplace_click_it(request: Request) -> Response:
    """Reject Click It before FastAPI parses any multipart photo upload.

    This endpoint intentionally has no Form/File parameters and never calls
    request.form(), request.body(), or request.stream(). Until the masking,
    consent, and asset-bound attestation providers are released, even parsing
    the uploaded photo into a spooled file is unnecessary.
    """
    authorization = request.headers.get("authorization", "")
    scheme, _, user_token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not user_token.strip():
        raise HTTPException(
            401,
            detail={"code": "USER_BEARER_REQUIRED"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    raise HTTPException(
        503,
        detail={
            "code": "CLICK_IT_PRIVACY_PIPELINE_NOT_RELEASED",
            "message": "Click It is unavailable until verified face masking, resource-bound consent and publication attestation are released.",
        },
        headers={"Cache-Control": "no-store"},
    )


def _page_html() -> str:
    try:
        html = HTML_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=503, detail={"code": "MARKETPLACE_PAGE_UNAVAILABLE"}) from exc
    marker = "<script>\n(() => {"
    bootstrap = (
        '<script>window.CIRVANNA_MARKETPLACE_CONFIG = Object.freeze({publicOffersBase:"/api/commerce"});</script>\n'
        + "<script>\n(() => {"
    )
    if 'window.CIRVANNA_MARKETPLACE_CONFIG = Object.freeze({' not in html:
        if html.count(marker) != 1:
            raise HTTPException(status_code=503, detail={"code": "MARKETPLACE_BOOTSTRAP_MARKER_MISSING"})
        html = html.replace(marker, bootstrap, 1)
    return html


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "alive", "service": SERVICE}


@app.get("/ready")
def readiness() -> dict:
    catalog_configured = bool(os.getenv("CATALOG_API_URL"))
    commerce_configured = bool(os.getenv("COMMERCE_API_URL"))
    catalog_ready = False
    commerce_ready = False
    try:
        catalog_base = _upstream_base("CATALOG_API_URL")
        if catalog_configured:
            catalog_ready = _upstream_ready(catalog_base)
    except HTTPException:
        catalog_ready = False
    try:
        commerce_base = _upstream_base("COMMERCE_API_URL")
        commerce_ready = _upstream_ready(commerce_base)
    except HTTPException:
        commerce_ready = False
    ready = catalog_configured and commerce_configured and catalog_ready and commerce_ready
    result = {
        "status": "ready" if ready else "not_ready",
        "service": SERVICE,
        "catalog_url_configured": catalog_configured,
        "catalog_ready": catalog_ready,
        "commerce_url_configured": commerce_configured,
        "commerce_ready": commerce_ready,
        "ready": ready,
    }
    if not ready:
        raise HTTPException(status_code=503, detail=result)
    return result


@app.get("/", response_class=HTMLResponse)
@app.get("/marketplace.html", response_class=HTMLResponse)
def marketplace_page() -> HTMLResponse:
    return HTMLResponse(_page_html(), headers={"Cache-Control": "no-store"})


@app.get("/api/commerce/marketplace/offers")
async def public_offers(
    request: Request,
    q: str | None = Query(default=None, max_length=160),
    category: str | None = Query(default=None, max_length=80),
    currency: str | None = Query(default=None, min_length=3, max_length=3),
    market_country_code: str | None = Query(default=None, min_length=2, max_length=2),
    display_currency: str | None = Query(default=None, min_length=3, max_length=3),
    destination_key: str | None = Query(default=None, min_length=3, max_length=180),
    fulfillment_mode: Literal["shipping", "courier_delivery", "merchant_delivery", "collection", "local_transport"] | None = Query(default=None),
    radius_km: float = Query(default=30.0, ge=1.0, le=500.0),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
) -> Response:
    """Authenticated marketplace browse through the canonical CAL discovery route."""
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=3.0),
        trust_env=False,
        follow_redirects=False,
    ) as client:
        subject, user_token = await _verified_commerce_subject(client, request)
        gateway_base, gateway_token = _decision_gateway()
        body = {
            "user_id": subject,
            "query": " ".join((q or "").split()).strip(),
            "category": category.strip() if category and category.strip() else None,
            "currency": currency.upper() if currency else None,
            "market_country_code": market_country_code.upper() if market_country_code else None,
            "display_currency": display_currency.upper() if display_currency else None,
            "destination_key": destination_key.strip() if destination_key and destination_key.strip() else None,
            "fulfillment_mode": fulfillment_mode,
            "radius_km": radius_km,
            "offset": offset,
            "limit": min(limit, 25),
            "use_wardrobe_context": False,
            "exclude_owned_products": True,
        }
        try:
            response = await client.post(
                gateway_base + "/v1/discover",
                headers={
                    "Authorization": "Bearer " + gateway_token,
                    "X-End-User-Authorization": "Bearer " + user_token,
                    "Accept": "application/json",
                },
                json=body,
            )
        except httpx.TimeoutException as exc:
            raise HTTPException(504, detail={"code": "CAL_MARKETPLACE_DISCOVERY_TIMEOUT"}) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "CAL_MARKETPLACE_DISCOVERY_UNAVAILABLE"}) from exc

    if response.status_code in {400, 401, 403, 404, 409, 422}:
        try:
            detail = response.json().get("detail", {})
            code = detail.get("code") if isinstance(detail, dict) else None
        except ValueError:
            code = None
        raise HTTPException(response.status_code, detail={"code": code or "CAL_MARKETPLACE_DISCOVERY_REJECTED"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "CAL_MARKETPLACE_DISCOVERY_UNAVAILABLE"})
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "CAL_MARKETPLACE_DISCOVERY_RESPONSE_INVALID"}) from exc
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("displayable_products"), list)
        or not isinstance(data.get("withheld_candidate_ids", []), list)
        or isinstance(data.get("ranked_candidate_count"), bool)
        or not isinstance(data.get("ranked_candidate_count", 0), int)
        or data.get("ranked_candidate_count", 0) < 0
    ):
        raise HTTPException(502, detail={"code": "CAL_MARKETPLACE_DISCOVERY_RESPONSE_INVALID"})

    items = []
    for candidate in data["displayable_products"]:
        if not isinstance(candidate, dict):
            raise HTTPException(502, detail={"code": "CAL_MARKETPLACE_DISCOVERY_RESPONSE_INVALID"})
        decision = candidate.get("decision")
        product = candidate.get("product")
        offer = candidate.get("offer")
        if (
            not isinstance(decision, dict)
            or decision.get("verdict") != "show"
            or decision.get("may_display") is not True
            or not isinstance(product, dict)
            or not isinstance(offer, dict)
            or not isinstance(product.get("product_id"), str)
            or offer.get("catalog_product_id") != product.get("product_id")
            or not isinstance(offer.get("variant_id"), str)
        ):
            raise HTTPException(502, detail={"code": "CAL_MARKETPLACE_CANDIDATE_AUTHORIZATION_INVALID"})
        safe_offer = _withhold_unverified_media(offer)
        safe_offer["product_name"] = offer.get("product_name") or product.get("name")
        safe_offer["brand"] = product.get("brand")
        safe_offer["category"] = offer.get("category") or product.get("category")
        safe_offer["description"] = product.get("description") or ""
        safe_offer["attributes"] = product.get("attributes") if isinstance(product.get("attributes"), dict) else {}
        safe_offer["image_urls"] = []
        safe_offer["product"] = _withhold_unverified_media(product)
        items.append(safe_offer)

    withheld = data.get("withheld_candidate_ids", [])
    ranked_count = data.get("ranked_candidate_count", len(items) + len(withheld))
    has_more = ranked_count >= min(limit, 25)
    total = offset + ranked_count + (1 if has_more else 0)
    return JSONResponse(
        content={
            "items": items,
            "total": total,
            "offset": offset,
            "limit": min(limit, 25),
            "has_more": has_more,
            "withheld_candidate_count": len(withheld),
            "display_authority": "CaTaCaCi/CAL",
            "display_rule": "Only authenticated, candidate-bound CAL SHOW decisions with may_display=true are returned with product and offer details.",
        },
        headers={"Cache-Control": "no-store, private"},
    )

@app.post("/api/commerce/marketplace/compare")
async def compare_public_offers(request: Request) -> Response:
    """Fail closed until each candidate is bound to an authenticated CAL SHOW receipt."""
    raise HTTPException(
        status_code=503,
        detail={
            "code": "CAL_AUTHORIZATION_REQUIRED",
            "message": "Merchant comparison is unavailable until candidate-bound CAL authorization is enforced.",
        },
        headers={"Cache-Control": "no-store"},
    )

def _authorized_commerce_path(method: str, path: str) -> bool:
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return False
    if (method, path) in SERVICE_PATHS:
        return True
    if len(parts) == 2 and parts[0] == "saved-products" and UUID_RE.fullmatch(parts[1]):
        return method in {"PUT", "DELETE"}
    if len(parts) == 3 and parts[:2] == ["cart", "items"] and UUID_RE.fullmatch(parts[2]):
        return method in {"PATCH", "DELETE"}
    if len(parts) == 2 and parts[0] == "orders" and UUID_RE.fullmatch(parts[1]):
        return method == "GET"
    if len(parts) == 4 and parts[:2] == ["merchant", "listings"] and UUID_RE.fullmatch(parts[2]) and parts[3] == "variants":
        return method == "POST"
    if len(parts) == 4 and parts[:2] == ["merchant", "variants"] and UUID_RE.fullmatch(parts[2]) and parts[3] == "inventory-adjustments":
        return method == "POST"
    if len(parts) == 4 and parts[:2] == ["admin", "merchants"] and UUID_RE.fullmatch(parts[2]) and parts[3] == "decision":
        return method == "POST"
    if len(parts) == 4 and parts[:2] == ["admin", "merchants"] and UUID_RE.fullmatch(parts[2]) and parts[3] == "markets":
        return method == "GET"
    if len(parts) == 5 and parts[:2] == ["admin", "merchants"] and UUID_RE.fullmatch(parts[2]) and parts[3] == "markets" and re.fullmatch(r"[A-Za-z]{2}", parts[4]):
        return method == "PUT"
    return False


@app.api_route("/api/commerce/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def commerce_proxy(path: str, request: Request) -> Response:
    """Forward customer operations only; admin/internal/webhook routes are not exposed."""
    method = request.method.upper()
    if not _authorized_commerce_path(method, path):
        raise HTTPException(status_code=404, detail={"code": "COMMERCE_ROUTE_NOT_AVAILABLE"})
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=401,
            detail={"code": "USER_BEARER_REQUIRED"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    base = _upstream_base("COMMERCE_API_URL")
    headers = {"Authorization": authorization, "Accept": request.headers.get("accept", "application/json")}
    for key in ("content-type", "idempotency-key"):
        if request.headers.get(key):
            headers[key] = request.headers[key]
    body = await request.body()
    try:
        upstream = httpx.request(
            method,
            base + "/" + path,
            params=list(request.query_params.multi_items()),
            content=body if body else None,
            headers=headers,
            timeout=TIMEOUT_SECONDS,
            follow_redirects=False,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail={"code": "COMMERCE_API_UNAVAILABLE"}) from exc
    response_headers = {}
    if upstream.headers.get("content-type"):
        response_headers["Content-Type"] = upstream.headers["content-type"]
    if upstream.headers.get("retry-after"):
        response_headers["Retry-After"] = upstream.headers["retry-after"]
    return Response(content=upstream.content, status_code=upstream.status_code, headers=response_headers)


@app.post("/api/wardrobe/items", status_code=201)
async def create_wardrobe_item(request: Request, payload: CreateWardrobeItemIn = Body(...)) -> Response:
    """Create and activate a text-described garment for the verified Commerce subject."""
    owner = None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=2.0), trust_env=False, follow_redirects=False) as client:
            owner, _ = await _verified_commerce_subject(client, request)
            base, token = _wardrobe_service()
            item_id = str(uuid.uuid4())
            created = await client.post(
                base + "/v1/items",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json={
                    "owner_user_id": owner,
                    "item_id": item_id,
                    "display_name": payload.display_name.strip(),
                    "category": payload.category.strip(),
                    "attributes": [value.strip() for value in payload.attributes if value.strip()],
                    "catalog_product_id": payload.catalog_product_id.strip() if payload.catalog_product_id else None,
                    "image_asset_id": None,
                    "image_storage_consent": False,
                },
            )
            if created.status_code != 201:
                raise HTTPException(503, detail={"code": "WARDROBE_ITEM_CREATE_UNAVAILABLE"})
            try:
                item = created.json().get("item")
            except ValueError as exc:
                raise HTTPException(502, detail={"code": "WARDROBE_ITEM_CREATE_RESPONSE_INVALID"}) from exc
            if not isinstance(item, dict) or item.get("owner_user_id") != owner or item.get("item_id") != item_id:
                raise HTTPException(502, detail={"code": "WARDROBE_ITEM_CREATE_SCOPE_MISMATCH"})
            activated = await client.post(
                base + f"/v1/items/{item_id}/transition",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json={
                    "owner_user_id": owner,
                    "expected_version": item.get("version", 1),
                    "target_status": "active",
                    "command_id": "activate-" + str(uuid.uuid4()),
                },
            )
            if activated.status_code != 200:
                raise HTTPException(503, detail={"code": "WARDROBE_ITEM_ACTIVATION_UNAVAILABLE"})
            try:
                result = activated.json().get("item")
            except ValueError as exc:
                raise HTTPException(502, detail={"code": "WARDROBE_ITEM_ACTIVATION_RESPONSE_INVALID"}) from exc
            if not isinstance(result, dict) or result.get("owner_user_id") != owner or result.get("status") != "active":
                raise HTTPException(502, detail={"code": "WARDROBE_ITEM_ACTIVATION_SCOPE_MISMATCH"})
            return JSONResponse(content={"item": result}, status_code=201, headers={"Cache-Control": "no-store, private"})
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "WARDROBE_ITEM_CREATE_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "WARDROBE_ITEM_CREATE_UNAVAILABLE"}) from exc



@app.get("/api/wardrobe/consents")
async def wardrobe_list_consents(request: Request) -> Response:
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=2.0), trust_env=False, follow_redirects=False) as client:
        subject, _ = await _verified_commerce_subject(client, request)
        identity_url = os.getenv("IDENTITY_SERVICE_URL", "").strip()
        identity_token = os.getenv("IDENTITY_SERVICE_TOKEN", "").strip()
        if not identity_url and not identity_token:
            # A missing learning provider must not prevent a user browsing their closet.
            return _private_json_response({"subject_id": subject, "items": [], "learning_configured": False})
        if not identity_url or len(identity_token.encode("utf-8")) < 32:
            raise HTTPException(503, detail={"code": "IDENTITY_CONSENT_CONFIGURATION_INVALID"})
        base, token = _identity_learning_service()
        try:
            response = await client.get(
                base + f"/v1/tal/consents/{subject}",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "IDENTITY_CONSENT_UNAVAILABLE"}) from exc
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "IDENTITY_CONSENT_UNAVAILABLE"})
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "IDENTITY_CONSENT_RESPONSE_INVALID"}) from exc
    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        raise HTTPException(502, detail={"code": "IDENTITY_CONSENT_RESPONSE_INVALID"})
    return _private_json_response({"subject_id": subject, "items": data, "learning_configured": True})

@app.post("/api/wardrobe/consents")
async def wardrobe_create_consent(request: Request, payload: WardrobeConsentIn = Body(...)) -> Response:
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=2.0), trust_env=False, follow_redirects=False) as client:
        subject, _ = await _verified_commerce_subject(client, request)
        base, token = _identity_learning_service()
        receipt_id = str(uuid.uuid4())
        try:
            response = await client.post(
                base + "/v1/tal/consents",
                params={"subject_id": subject},
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json={
                    "receipt_id": receipt_id,
                    "scope": payload.scope,
                    "consent_version": "wardrobe-pnelly-learning-v1",
                    "granted": payload.granted,
                },
            )
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "IDENTITY_CONSENT_UNAVAILABLE"}) from exc
    if response.status_code not in {200, 201}:
        raise HTTPException(503, detail={"code": "IDENTITY_CONSENT_WRITE_FAILED"})
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "IDENTITY_CONSENT_RESPONSE_INVALID"}) from exc
    return _private_json_response({"subject_id": subject, "receipt_id": receipt_id, "scope": payload.scope, "granted": payload.granted, "result": data})


@app.post("/api/wardrobe/consents/{receipt_id}/revoke")
async def wardrobe_revoke_consent(receipt_id: str, request: Request) -> Response:
    if len(receipt_id) < 8 or len(receipt_id) > 128:
        raise HTTPException(422, detail={"code": "INVALID_CONSENT_RECEIPT_ID"})
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=2.0), trust_env=False, follow_redirects=False) as client:
        subject, _ = await _verified_commerce_subject(client, request)
        base, token = _identity_learning_service()
        try:
            response = await client.post(
                base + f"/v1/tal/consents/{receipt_id}/revoke",
                params={"subject_id": subject},
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "IDENTITY_CONSENT_UNAVAILABLE"}) from exc
    if response.status_code == 404:
        raise HTTPException(404, detail={"code": "CONSENT_RECEIPT_NOT_FOUND"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "IDENTITY_CONSENT_REVOKE_FAILED"})
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "IDENTITY_CONSENT_RESPONSE_INVALID"}) from exc
    return _private_json_response(data)


@app.post("/api/wardrobe/feedback")
async def wardrobe_feedback(request: Request, payload: WardrobeFeedbackIn = Body(...)) -> Response:
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=2.0), trust_env=False, follow_redirects=False) as client:
        subject, _ = await _verified_commerce_subject(client, request)
        base, token = _wardrobe_service()
        body = payload.model_dump(mode="json")
        body["owner_user_id"] = subject
        body["observed_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        try:
            response = await client.post(
                base + "/v1/feedback",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json=body,
            )
        except httpx.TimeoutException as exc:
            raise HTTPException(504, detail={"code": "WARDROBE_FEEDBACK_TIMEOUT"}) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "WARDROBE_FEEDBACK_UNAVAILABLE"}) from exc
    if response.status_code in {400, 403, 404, 409, 422}:
        try:
            detail = response.json().get("detail", {})
            code = detail.get("code") if isinstance(detail, dict) else None
        except ValueError:
            code = None
        raise HTTPException(response.status_code, detail={"code": code or "WARDROBE_FEEDBACK_REJECTED"})
    if response.status_code != 201:
        raise HTTPException(503, detail={"code": "WARDROBE_FEEDBACK_UNAVAILABLE"})
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "WARDROBE_FEEDBACK_RESPONSE_INVALID"}) from exc
    return _private_json_response(data)


@app.post("/api/wardrobe/recommendations")
async def wardrobe_recommendations(request: Request, payload: WardrobeRecommendationIn = Body(...)) -> Response:
    subject, user_token = (None, None)
    async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=2.0), trust_env=False, follow_redirects=False) as client:
        subject, user_token = await _verified_commerce_subject(client, request)
        base, token = _decision_gateway()
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        context: dict[str, str] = {}
        if payload.location and payload.location.strip():
            context.update({"location": payload.location.strip(), "location_source": "user_declared", "location_observed_at": now})
        if payload.occasion and payload.occasion.strip():
            context.update({"occasion": payload.occasion.strip(), "occasion_source": "user_declared", "occasion_observed_at": now})
        if payload.climate and payload.climate.strip():
            context.update({"climate": payload.climate.strip(), "climate_source": "user_declared", "climate_observed_at": now})
        body = {
            "user_id": subject,
            "query": " ".join(payload.query.split()).strip(),
            "category": payload.category,
            "currency": payload.currency.upper() if payload.currency else None,
            "limit": payload.limit,
            "context": context,
            "use_wardrobe_context": True,
            "exclude_owned_products": payload.exclude_owned_products,
        }
        try:
            response = await client.post(
                base + "/v1/discover",
                headers={
                    "Authorization": "Bearer " + token,
                    "X-End-User-Authorization": "Bearer " + user_token,
                    "Accept": "application/json",
                },
                json=body,
            )
        except httpx.TimeoutException as exc:
            raise HTTPException(504, detail={"code": "WARDROBE_RECOMMENDATIONS_TIMEOUT"}) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "WARDROBE_RECOMMENDATIONS_UNAVAILABLE"}) from exc
    if response.status_code in {400, 401, 403, 404, 409, 422}:
        try:
            detail = response.json().get("detail", {})
            code = detail.get("code") if isinstance(detail, dict) else None
        except ValueError:
            code = None
        raise HTTPException(response.status_code, detail={"code": code or "WARDROBE_RECOMMENDATIONS_REJECTED"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "WARDROBE_RECOMMENDATIONS_UNAVAILABLE"})
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "WARDROBE_RECOMMENDATIONS_RESPONSE_INVALID"}) from exc
    # Treat the gateway decision as a candidate-bound authorization contract.
    # Never pass withheld IDs or raw policy evidence to the browser.
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("displayable_products"), list)
        or not isinstance(data.get("withheld_candidate_ids", []), list)
    ):
        raise HTTPException(502, detail={"code": "WARDROBE_RECOMMENDATIONS_RESPONSE_INVALID"})

    authorized_products = []
    for candidate in data["displayable_products"]:
        if not isinstance(candidate, dict):
            raise HTTPException(502, detail={"code": "WARDROBE_RECOMMENDATIONS_RESPONSE_INVALID"})
        decision = candidate.get("decision")
        if (
            not isinstance(decision, dict)
            or decision.get("verdict") != "show"
            or decision.get("may_display") is not True
            or not isinstance(candidate.get("product"), dict)
            or not isinstance(candidate.get("offer"), dict)
        ):
            raise HTTPException(502, detail={"code": "WARDROBE_CANDIDATE_CAL_AUTHORIZATION_INVALID"})
        authorized_products.append(_withhold_unverified_media(candidate))

    withheld = data.get("withheld_candidate_ids", [])
    safe_payload = {
        "request_id": data.get("request_id"),
        "ranked_candidate_count": data.get("ranked_candidate_count", len(authorized_products) + len(withheld)),
        "displayable_products": authorized_products,
        "withheld_candidate_count": len(withheld),
        "display_authority": "CaTaCaCi/CAL",
        "display_rule": "Only candidate-bound CAL SHOW decisions with may_display=true are returned with product and offer details.",
        "wardrobe_context": data.get("wardrobe_context") if isinstance(data.get("wardrobe_context"), dict) else {"used": True},
    }
    return _private_json_response(safe_payload)

def _read_portal_page(path: Path, code: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=503, detail={"code": code}) from exc


@app.get("/brand-portal", response_class=HTMLResponse)
@app.get("/brand-portal.html", response_class=HTMLResponse)
def brand_portal_page() -> HTMLResponse:
    return HTMLResponse(_read_portal_page(BRAND_PORTAL_HTML_PATH, "BRAND_PORTAL_UNAVAILABLE"),
        headers={"Cache-Control": "no-store"})


@app.get("/founder-console", response_class=HTMLResponse)
@app.get("/founder-console.html", response_class=HTMLResponse)
def founder_console_page() -> HTMLResponse:
    return HTMLResponse(_read_portal_page(FOUNDER_CONSOLE_HTML_PATH, "FOUNDER_CONSOLE_UNAVAILABLE"),
        headers={"Cache-Control": "no-store"})

