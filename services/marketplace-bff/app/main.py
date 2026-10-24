"""Same-origin backend-for-frontend for the Cirvanna marketplace.

This service keeps service credentials server-side and forwards only an explicit
allowlist of customer commerce routes. It never issues identity tokens or
fabricates decision, fit, Click It, Virtual Twin, or try-on outputs.
"""
from __future__ import annotations

import hmac
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from app.governance import govern_candidates

SERVICE = "cirvanna-marketplace-bff"
ROOT = Path(__file__).resolve().parents[3]
DEFAULT_HTML = ROOT / "apps" / "demo-web" / "marketplace.html"
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
    description="Same-origin marketplace UI, account-safe AI search, and constrained API gateway.",
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


async def _verified_user_id(request: Request) -> tuple[str, str]:
    """Resolve the actor from Commerce's verified /me endpoint, never from browser input."""
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(401, detail={"code": "USER_BEARER_REQUIRED"}, headers={"WWW-Authenticate": "Bearer"})
    base = _upstream_base("COMMERCE_API_URL")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_SECONDS), trust_env=False, follow_redirects=False) as client:
            response = await client.get(base + "/me", headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "USER_IDENTITY_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "USER_IDENTITY_UNAVAILABLE"}) from exc
    if response.status_code in {401, 403}:
        raise HTTPException(401, detail={"code": "USER_AUTHENTICATION_FAILED"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "USER_IDENTITY_UNAVAILABLE"})
    try:
        actor = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "INVALID_USER_IDENTITY_RESPONSE"}) from exc
    user_id = actor.get("user_id") if isinstance(actor, dict) else None
    if not isinstance(user_id, str) or not user_id.strip():
        raise HTTPException(502, detail={"code": "INVALID_USER_IDENTITY_RESPONSE"})
    return user_id.strip(), token


def _internal_service(url_key: str, token_key: str) -> tuple[str, str]:
    base = _upstream_base(url_key)
    token = os.getenv(token_key, "").strip()
    if len(token.encode("utf-8")) < 32:
        raise HTTPException(status_code=503, detail={"code": f"{token_key}_NOT_CONFIGURED"})
    return base, token


class InternalCALAuthorizationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject_id: str = Field(min_length=1, max_length=128)
    candidate_id: str = Field(min_length=1, max_length=128)
    catalog_product_id: str = Field(min_length=1, max_length=128)


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
async def marketplace_description_search(request: Request, payload: MarketplaceSearchIn) -> dict:
    """Run Xari retrieval, then expose only candidates authorized by canonical CAL."""
    user_id, _user_token = await _verified_user_id(request)
    base, token = _internal_service("XARI_API_URL", "XARI_API_TOKEN")
    request_body = {"query": payload.normalized_query, "limit": payload.limit}
    if payload.category and payload.category.strip():
        request_body["category"] = payload.category.strip()
    data = await _safe_json_post(base, "/v1/marketplace/search", token, request_body)
    governed = await govern_candidates(user_id, data["candidates"])
    return {
        "status": "complete",
        "query": payload.normalized_query,
        "user_id": user_id,
        **governed,
    }


@app.post("/api/vision/click-it")
async def marketplace_click_it(
    request: Request,
    consent_id: str = Form(min_length=8, max_length=160),
    consent_image_processing: bool = Form(),
    consent_click_it: bool = Form(),
    product_image: UploadFile = File(...),
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
        candidates = data.get("candidates")
        if not isinstance(candidates, list):
            raise HTTPException(502, detail={"code": "CLICK_IT_INVALID_RESPONSE"})
        # Ignore upstream display flags; evaluate every candidate against fresh,
        # subject-bound evidence and the canonical CAL response.
        governed = await govern_candidates(subject_id.strip(), candidates)
        return JSONResponse(
            content={
                "status": "complete",
                **governed,
                "image_persisted": data.get("image_persisted") is False,
            },
            headers={"Cache-Control": "no-store, private"},
        )
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


@app.post("/internal/cal/authorize")
async def internal_cal_authorize(request: Request, payload: InternalCALAuthorizationIn) -> dict:
    """Private service-to-service transaction-time revalidation endpoint."""
    expected = os.getenv("CAL_GATEWAY_SERVICE_TOKEN", "").strip()
    scheme, _, supplied = request.headers.get("authorization", "").partition(" ")
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "CAL_GATEWAY_SERVICE_TOKEN_NOT_CONFIGURED"})
    if scheme.lower() != "bearer" or not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, detail={"code": "CAL_GATEWAY_AUTH_FAILED"})
    if not UUID_RE.fullmatch(payload.catalog_product_id.strip()):
        raise HTTPException(422, detail={"code": "CANONICAL_CATALOG_PRODUCT_ID_REQUIRED"})
    governed = await govern_candidates(payload.subject_id.strip(), [{
        "candidate_id": payload.candidate_id.strip(),
        "catalog_product_id": payload.catalog_product_id.strip(),
    }])
    candidates = governed.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 1:
        return {"subject_id": payload.subject_id.strip(), "candidate_id": payload.candidate_id.strip(), "catalog_product_id": payload.catalog_product_id.strip(),
                "decision": "NO_SHOW", "may_display": False, "reason_code": governed.get("governance_status", "CAL_NO_SHOW")}
    returned_candidate = candidates[0]
    if (returned_candidate.get("candidate_id") != payload.candidate_id.strip()
            or returned_candidate.get("catalog_product_id") != payload.catalog_product_id.strip()):
        return {"subject_id": payload.subject_id.strip(), "candidate_id": payload.candidate_id.strip(),
                "catalog_product_id": payload.catalog_product_id.strip(), "decision": "NO_SHOW",
                "may_display": False, "reason_code": "CAL_CANDIDATE_BINDING_MISMATCH"}
    receipt = returned_candidate.get("cal_decision")
    if not isinstance(receipt, dict) or receipt.get("verdict") != "SHOW" or receipt.get("may_display") is not True:
        return {"subject_id": payload.subject_id.strip(), "candidate_id": payload.candidate_id.strip(), "catalog_product_id": payload.catalog_product_id.strip(),
                "decision": "NO_SHOW", "may_display": False, "reason_code": "CAL_RECEIPT_INVALID"}
    return {"subject_id": payload.subject_id.strip(), "candidate_id": payload.candidate_id.strip(), "catalog_product_id": payload.catalog_product_id.strip(),
            "decision": "SHOW", "may_display": True, "request_id": receipt.get("request_id"),
            "policy_version": receipt.get("policy_version")}


@app.get("/ready")
def readiness() -> dict:
    catalog_configured = bool(os.getenv("CATALOG_API_URL"))
    commerce_configured = bool(os.getenv("COMMERCE_API_URL"))
    evidence_url_configured = bool(os.getenv("GOVERNANCE_EVIDENCE_API_URL"))
    evidence_token_configured = len(os.getenv("GOVERNANCE_EVIDENCE_API_TOKEN", "").encode("utf-8")) >= 32
    decision_url_configured = bool(os.getenv("DECISION_SERVICE_API_URL"))
    decision_token_configured = len(os.getenv("DECISION_SERVICE_TOKEN", "").encode("utf-8")) >= 32
    cal_gateway_token_configured = len(os.getenv("CAL_GATEWAY_SERVICE_TOKEN", "").encode("utf-8")) >= 32
    catalog_ready = False
    commerce_ready = False
    evidence_ready = False
    decision_ready = False
    for env_key, configured, assign in (
        ("CATALOG_API_URL", catalog_configured, "catalog"),
        ("COMMERCE_API_URL", commerce_configured, "commerce"),
        ("GOVERNANCE_EVIDENCE_API_URL", evidence_url_configured and evidence_token_configured, "evidence"),
        ("DECISION_SERVICE_API_URL", decision_url_configured and decision_token_configured, "decision"),
    ):
        try:
            upstream_ready = _upstream_ready(_upstream_base(env_key)) if configured else False
        except HTTPException:
            upstream_ready = False
        if assign == "catalog":
            catalog_ready = upstream_ready
        elif assign == "commerce":
            commerce_ready = upstream_ready
        elif assign == "evidence":
            evidence_ready = upstream_ready
        else:
            decision_ready = upstream_ready
    ready = (
        catalog_configured and commerce_configured and catalog_ready and commerce_ready
        and evidence_url_configured and evidence_token_configured and evidence_ready
        and decision_url_configured and decision_token_configured and decision_ready
        and cal_gateway_token_configured
    )
    result = {
        "status": "ready" if ready else "not_ready",
        "service": SERVICE,
        "catalog_url_configured": catalog_configured,
        "catalog_ready": catalog_ready,
        "commerce_url_configured": commerce_configured,
        "commerce_ready": commerce_ready,
        "governance_evidence_url_configured": evidence_url_configured,
        "governance_evidence_auth_configured": evidence_token_configured,
        "governance_evidence_ready": evidence_ready,
        "decision_service_url_configured": decision_url_configured,
        "decision_service_auth_configured": decision_token_configured,
        "decision_service_ready": decision_ready,
        "cal_gateway_service_auth_configured": cal_gateway_token_configured,
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
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
) -> dict:
    """Return only offers that received an exact, candidate-bound CAL SHOW decision."""
    user_id, _user_token = await _verified_user_id(request)
    base = _upstream_base("COMMERCE_API_URL")
    params: dict[str, str | int] = {"offset": offset, "limit": limit}
    for key, value in (("q", q), ("category", category), ("currency", currency)):
        if value and value.strip():
            params[key] = value.strip()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(TIMEOUT_SECONDS), trust_env=False, follow_redirects=False
        ) as client:
            upstream = await client.get(
                base + "/marketplace/offers",
                params=params,
                headers={"Accept": "application/json"},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "COMMERCE_OFFERS_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "COMMERCE_OFFERS_UNAVAILABLE"}) from exc
    if upstream.status_code != 200:
        raise HTTPException(503, detail={"code": "COMMERCE_OFFERS_UNAVAILABLE"})
    try:
        payload = upstream.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "COMMERCE_OFFERS_INVALID_RESPONSE"}) from exc
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("items"), list)
        or not isinstance(payload.get("total"), int)
    ):
        raise HTTPException(502, detail={"code": "COMMERCE_OFFERS_INVALID_RESPONSE"})
    governed = await govern_candidates(user_id, payload["items"])
    if governed["governance_status"] == "CAL_GATE_NOT_CONNECTED":
        raise HTTPException(
            503,
            detail={"code": "CAL_GOVERNANCE_NOT_ENFORCED", "retryable": True},
        )
    return {
        **governed,
        "items": governed["candidates"],
        "candidates": governed["candidates"],
        "total": payload["total"],
        "offset": offset,
        "limit": limit,
    }


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
