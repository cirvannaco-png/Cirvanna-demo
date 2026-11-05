"""Same-origin backend-for-frontend for the Cirvanna marketplace.

This service keeps service credentials server-side and forwards only an explicit
allowlist of customer commerce routes. It never issues identity tokens or
fabricates decision, fit, Click It, Virtual Twin, or try-on outputs.
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx
from fastapi import Body, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

SERVICE = "cirvanna-marketplace-bff"
ROOT = Path(__file__).resolve().parents[3]
DEFAULT_HTML = ROOT / "apps" / "demo-web" / "marketplace.html"
DEFAULT_WARDROBE_HTML = ROOT / "apps" / "demo-web" / "wardrobe.html"
HTML_PATH = Path(os.getenv("MARKETPLACE_HTML_PATH", str(DEFAULT_HTML)))
TIMEOUT_SECONDS = 5.0
MAX_PAGE_SIZE = 100
MAX_VISION_IMAGE_BYTES = 10 * 1024 * 1024
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")
SERVICE_PATHS = {
    ("GET", "cart"),
    ("GET", "saved-products"),
    ("GET", "orders"),
    ("POST", "cart/items"),
    ("POST", "checkout"),
}

app = FastAPI(
    title="Cirvanna Marketplace BFF",
    version="0.1.0",
    description="Same-origin marketplace and Wardrobe UI with verified account identity and private service proxies.",
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; "
        "base-uri 'self'; frame-ancestors 'none'",
    )
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    if request.url.path in {"/api/vision/click-it", "/api/privacy/image-requests"}:
        response.headers["Cache-Control"] = "no-store, private"
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

def _xari_internal_service() -> tuple[str, str]:
    """Prefer Xari environment names while retaining Tari aliases during migration."""
    xari_url = os.getenv("XARI_API_URL", "").strip()
    tari_url = os.getenv("TARI_API_URL", "").strip()
    url_key = "XARI_API_URL" if xari_url else "TARI_API_URL"
    token = os.getenv("XARI_API_TOKEN", "").strip() or os.getenv("TARI_API_TOKEN", "").strip()
    if not xari_url and not tari_url:
        raise HTTPException(status_code=503, detail={"code": "XARI_API_URL_NOT_CONFIGURED"})
    base = _upstream_base(url_key)
    if len(token.encode("utf-8")) < 32:
        raise HTTPException(status_code=503, detail={"code": "XARI_API_TOKEN_NOT_CONFIGURED"})
    return base, token


class ImageRightsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_reference: str = Field(min_length=8, max_length=160, pattern=r"^[A-Za-z0-9_-]+$")
    request_type: Literal["report", "removal"]
    reason_code: Literal["unmasked_face", "possible_minor", "nonconsensual", "privacy_concern", "other"]
    requester_relationship: Literal["photographed_person", "parent_guardian", "authorized_representative", "other"]
    jurisdiction_hint: str | None = Field(default=None, max_length=100)


class MarketplaceSearchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=3, max_length=1000)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    limit: int = Field(default=10, ge=1, le=25)

    @property
    def normalized_query(self) -> str:
        return " ".join(self.query.split()).strip()


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
    """Search marketplace candidates by description without exposing Xari credentials."""
    base, token = _xari_internal_service()
    request_body = {"query": payload.normalized_query, "limit": payload.limit}
    if payload.category and payload.category.strip():
        request_body["category"] = payload.category.strip()
    data = await _safe_json_post(base, "/v1/marketplace/search", token, request_body)
    # This endpoint intentionally forwards candidates separately from display authorization.
    return {
        "status": "complete",
        "query": payload.normalized_query,
        "candidate_count": data.get("candidate_count", len(data["candidates"])),
        "candidates": data["candidates"],
        "display_authorized": data.get("display_authorized") is True,
        "decision_status": data.get("decision_status", "PENDING_CAL"),
        "scores_are_probabilities": False,
    }



class CreateWardrobeItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=80)
    attributes: list[str] = Field(default_factory=list, max_length=100)
    catalog_product_id: str | None = Field(default=None, max_length=128)


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


def _private_json_response(data: dict) -> JSONResponse:
    return JSONResponse(content=data, headers={"Cache-Control": "no-store, private"})


@app.get("/wardrobe", response_class=HTMLResponse)
def wardrobe_page() -> HTMLResponse:
    try:
        html = DEFAULT_WARDROBE_HTML.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=503, detail={"code": "WARDROBE_PAGE_UNAVAILABLE"}) from exc
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


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
    # The decision gateway returns product/offer details only for CAL SHOW.
    if not isinstance(data, dict) or not isinstance(data.get("displayable_products"), list):
        raise HTTPException(502, detail={"code": "WARDROBE_RECOMMENDATIONS_RESPONSE_INVALID"})
    return _private_json_response(data)



@app.post("/api/vision/click-it")
async def marketplace_click_it(
    request: Request,
    consent_id: str = Form(min_length=8, max_length=160),
    consent_image_processing: bool = Form(),
    consent_click_it: bool = Form(),
    product_image: UploadFile = File(...),
    photographed_people_status: str = Form(default="unknown"),
    capture_jurisdiction_hint: str | None = Form(default=None, max_length=100),
    twin_id: str | None = Form(default=None, min_length=3, max_length=128),
    category: str | None = Form(default=None, max_length=80),
    limit: int = Form(default=10, ge=1, le=25),
) -> Response:
    """Bind Click It to a verified Commerce identity and keep all service tokens private.

    The browser may supply consent flags and an opaque consent reference, but the
    Virtual Twin service verifies the durable, active record with the consent
    provider. This endpoint cannot treat a checkbox alone as durable consent.
    """
    authorization = request.headers.get("authorization", "")
    scheme, _, user_token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not user_token.strip():
        raise HTTPException(401, detail={"code": "USER_BEARER_REQUIRED"}, headers={"WWW-Authenticate": "Bearer"})
    if not consent_image_processing or not consent_click_it:
        raise HTTPException(400, detail={"code": "EXPLICIT_CLICK_IT_CONSENT_REQUIRED"})
    content_type = product_image.content_type or ""
    if content_type not in {"image/jpeg", "image/png", "image/webp"}:
        await product_image.close()
        raise HTTPException(415, detail={"code": "UNSUPPORTED_PRODUCT_IMAGE_TYPE"})
    if product_image.size is not None and product_image.size > MAX_VISION_IMAGE_BYTES:
        await product_image.close()
        raise HTTPException(413, detail={"code": "PRODUCT_IMAGE_SIZE_LIMIT_EXCEEDED"})
    content = b""
    try:
        content = await product_image.read(MAX_VISION_IMAGE_BYTES + 1)
    finally:
        await product_image.close()
    if not content:
        raise HTTPException(400, detail={"code": "EMPTY_PRODUCT_IMAGE"})
    if len(content) > MAX_VISION_IMAGE_BYTES:
        raise HTTPException(413, detail={"code": "PRODUCT_IMAGE_SIZE_LIMIT_EXCEEDED", "maximum_bytes": MAX_VISION_IMAGE_BYTES})

    commerce_base = _upstream_base("COMMERCE_API_URL")
    twin_base, twin_token = _internal_service("VIRTUAL_TWIN_API_URL", "VIRTUAL_TWIN_API_TOKEN")
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(8.0, connect=2.0),
            trust_env=False,
            follow_redirects=False,
        ) as client:
            # /me derives subject_id from a signed/verified Commerce token. Never
            # trust a subject_id submitted by browser JavaScript.
            identity = await client.get(
                commerce_base + "/me",
                headers={"Authorization": "Bearer " + user_token, "Accept": "application/json"},
            )
            if identity.status_code in {401, 403}:
                raise HTTPException(401, detail={"code": "USER_AUTHENTICATION_FAILED"})
            if identity.status_code != 200:
                raise HTTPException(503, detail={"code": "USER_IDENTITY_UNAVAILABLE"})
            actor = identity.json()
            subject_id = actor.get("user_id") if isinstance(actor, dict) else None
            if not isinstance(subject_id, str) or not subject_id.strip():
                raise HTTPException(502, detail={"code": "INVALID_USER_IDENTITY_RESPONSE"})
            fields = {
                "subject_id": subject_id,
                "consent_id": consent_id.strip(),
                "consent_image_processing": "true",
                "consent_click_it": "true",
                "photographed_people_status": photographed_people_status,
                "capture_jurisdiction_hint": capture_jurisdiction_hint or "",
                "limit": str(limit),
            }
            if twin_id and twin_id.strip():
                fields["twin_id"] = twin_id.strip()
            if category and category.strip():
                fields["category"] = category.strip()
            response = await client.post(
                twin_base + "/click-it",
                headers={"Authorization": "Bearer " + twin_token, "Accept": "application/json"},
                data=fields,
                files={"product_image": (product_image.filename or "click-it-image", content, content_type)},
            )
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "CLICK_IT_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "CLICK_IT_UNAVAILABLE"}) from exc
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "CLICK_IT_INVALID_RESPONSE"}) from exc
    if response.status_code == 200 and isinstance(data, dict):
        return JSONResponse(content=data, headers={"Cache-Control": "no-store, private"})
    detail = data.get("detail", {}) if isinstance(data, dict) else {}
    code = detail.get("code") if isinstance(detail, dict) else None
    safe = {"code": code if isinstance(code, str) else "CLICK_IT_REQUEST_FAILED"}
    if isinstance(detail, dict):
        for key in ("quality", "message", "maximum_bytes", "visibility"):
            if key in detail:
                safe[key] = detail[key]
    if response.status_code in {400, 403, 413, 415, 422}:
        raise HTTPException(response.status_code, detail=safe)
    if response.status_code == 504:
        raise HTTPException(504, detail={"code": "CLICK_IT_TIMEOUT"})
    if response.status_code in {502, 503}:
        raise HTTPException(503 if response.status_code == 503 else 502, detail=safe)
    raise HTTPException(502, detail={"code": "CLICK_IT_FAILED"})


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
def public_offers(
    q: str | None = Query(default=None, max_length=160),
    category: str | None = Query(default=None, max_length=80),
    currency: str | None = Query(default=None, min_length=3, max_length=3),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
) -> dict:
    """Expose only Commerce's active, approved, in-stock merchant offers."""
    base = _upstream_base("COMMERCE_API_URL")
    params: dict[str, str | int] = {"offset": offset, "limit": limit}
    if q and q.strip():
        params["q"] = q.strip()
    if category and category.strip():
        params["category"] = category.strip()
    if currency and currency.strip():
        params["currency"] = currency.strip().upper()
    try:
        response = httpx.get(
            base + "/marketplace/offers",
            params=params,
            headers={"Accept": "application/json"},
            timeout=TIMEOUT_SECONDS,
            follow_redirects=False,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail={"code": "COMMERCE_OFFERS_UNAVAILABLE"}) from exc
    if response.status_code != 200:
        raise HTTPException(
            status_code=503,
            detail={"code": "COMMERCE_OFFERS_UNAVAILABLE", "upstream_status": response.status_code},
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail={"code": "INVALID_COMMERCE_RESPONSE"}) from exc
    if not (
        isinstance(payload, dict)
        and isinstance(payload.get("items"), list)
        and isinstance(payload.get("total"), int)
    ):
        raise HTTPException(status_code=502, detail={"code": "INVALID_COMMERCE_RESPONSE"})
    return payload


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
    return False


@app.post("/api/privacy/image-requests")
async def submit_image_rights_request(payload: ImageRightsRequest) -> Response:
    """Public privacy-rights intake; the rights service verifies authority and manages quarantine."""
    base, token = _internal_service("PRIVACY_RIGHTS_API_URL", "PRIVACY_RIGHTS_API_TOKEN")
    request_body = payload.model_dump(exclude_none=True)
    request_body["jurisdiction_hint_is_unverified"] = True
    request_body["requester_authentication"] = "verified_by_privacy_rights_workflow"
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(12.0, connect=2.0),
            trust_env=False,
            follow_redirects=False,
        ) as client:
            upstream = await client.post(
                base + "/internal/v1/image-rights/requests",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json=request_body,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "IMAGE_RIGHTS_INTAKE_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "IMAGE_RIGHTS_SERVICE_UNAVAILABLE"}) from exc
    if upstream.status_code not in {200, 202}:
        raise HTTPException(503, detail={"code": "IMAGE_RIGHTS_INTAKE_REJECTED"})
    try:
        receipt = upstream.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "IMAGE_RIGHTS_RESPONSE_INVALID"}) from exc
    urgent = payload.reason_code in {"unmasked_face", "possible_minor", "nonconsensual"}
    valid = (
        isinstance(receipt, dict)
        and isinstance(receipt.get("request_id"), str)
        and bool(receipt.get("request_id").strip())
        and receipt.get("status") in {"accepted", "under_review", "quarantined"}
        and (not urgent or receipt.get("quarantined") is True)
    )
    if not valid:
        code = "IMAGE_RIGHTS_QUARANTINE_NOT_CONFIRMED" if urgent else "IMAGE_RIGHTS_RESPONSE_INVALID"
        raise HTTPException(503, detail={"code": code})
    safe_receipt = {
        "request_id": receipt["request_id"],
        "status": receipt["status"],
        "quarantined": receipt.get("quarantined") is True,
        "status_token": receipt.get("status_token") if isinstance(receipt.get("status_token"), str) else None,
    }
    return JSONResponse(status_code=202, content=safe_receipt, headers={"Cache-Control": "no-store, private"})


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
