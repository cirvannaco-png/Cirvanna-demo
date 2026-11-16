"""Trusted server-side verification for Android DSI capture envelopes.

This module verifies request bytes, Google Play Integrity verdicts and an
independent Android Key Attestation chain before Vision is allowed to ask
Identity Learning to persist a verification receipt. Client-supplied verdicts
are never accepted.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import io
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from PIL import Image, UnidentifiedImageError

MAX_MANIFEST_BYTES = 128 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_CHAIN_CERTIFICATES = 8
MAX_CERTIFICATE_BYTES = 24 * 1024
MAX_PLAY_TOKEN_LENGTH = 16 * 1024
ATTESTATION_STATUS_URL = "https://android.googleapis.com/attestation/status"
PLAY_INTEGRITY_SCOPE = "https://www.googleapis.com/auth/playintegrity"
PLAY_INTEGRITY_DECODE_BASE = "https://playintegrity.googleapis.com/v1"
HEX_256 = re.compile(r"^[a-f0-9]{64}$")
B64URL = re.compile(r"^[A-Za-z0-9_-]+$")


class CaptureVerificationError(RuntimeError):
    """Sanitized, fail-closed DSI capture verification failure."""

    def __init__(self, code: str, status_code: int = 403):
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class VerifiedAndroidCapture:
    package_name: str
    package_certificate_sha256: str
    app_version: str
    key_security_level: str
    verified_boot_state: str
    device_locked: bool
    app_recognition_verdict: str
    account_licensing_verdict: str
    device_integrity_verdicts: tuple[str, ...]
    manifest_sha256: str
    image_sha256: str
    device_pipeline_fingerprint_sha256: str
    play_integrity_request_hash: str


_REVOCATION_CACHE: dict[str, Any] = {}


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decode_b64url(value: str, *, field: str, maximum: int) -> bytes:
    if not isinstance(value, str) or not value or not B64URL.fullmatch(value):
        raise CaptureVerificationError("DSI_CAPTURE_ENVELOPE_INVALID")
    try:
        decoded = base64.urlsafe_b64decode(value + ("=" * ((4 - len(value) % 4) % 4)))
    except (ValueError, binascii.Error) as exc:
        raise CaptureVerificationError("DSI_CAPTURE_ENVELOPE_INVALID") from exc
    if not decoded or len(decoded) > maximum:
        raise CaptureVerificationError("DSI_CAPTURE_ENVELOPE_INVALID")
    return decoded


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CaptureVerificationError("DSI_CAPTURE_MANIFEST_DUPLICATE_KEY")
        result[key] = value
    return result


def _json_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _decimal_canonical(value: Decimal) -> str:
    if not value.is_finite():
        raise CaptureVerificationError("DSI_CAPTURE_MANIFEST_NUMBER_INVALID")
    if value == 0:
        return "0"
    normalized = value.normalize()
    if normalized == normalized.to_integral_value():
        return str(normalized.quantize(Decimal(1)))
    rendered = format(normalized, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _canonical_json(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _json_quote(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        return _decimal_canonical(value)
    if isinstance(value, float):
        if not value.is_integer():
            return _decimal_canonical(Decimal(str(value)))
        return str(int(value))
    if isinstance(value, list):
        return "[" + ",".join(_canonical_json(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise CaptureVerificationError("DSI_CAPTURE_MANIFEST_INVALID")
        return "{" + ",".join(
            _json_quote(key) + ":" + _canonical_json(value[key])
            for key in sorted(value)
        ) + "}"
    raise CaptureVerificationError("DSI_CAPTURE_MANIFEST_INVALID")


def canonical_manifest(manifest_text: str) -> tuple[bytes, dict[str, Any]]:
    if not isinstance(manifest_text, str):
        raise CaptureVerificationError("DSI_CAPTURE_MANIFEST_INVALID")
    raw = manifest_text.encode("utf-8")
    if not raw or len(raw) > MAX_MANIFEST_BYTES:
        raise CaptureVerificationError("DSI_CAPTURE_MANIFEST_SIZE_INVALID")
    try:
        payload = json.loads(
            manifest_text,
            parse_float=Decimal,
            parse_int=int,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                CaptureVerificationError("DSI_CAPTURE_MANIFEST_NUMBER_INVALID")
            ),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except CaptureVerificationError:
        raise
    except (UnicodeError, ValueError, InvalidOperation) as exc:
        raise CaptureVerificationError("DSI_CAPTURE_MANIFEST_INVALID") from exc
    if not isinstance(payload, dict):
        raise CaptureVerificationError("DSI_CAPTURE_MANIFEST_INVALID")
    canonical = _canonical_json(payload).encode("utf-8")
    if canonical != raw:
        raise CaptureVerificationError("DSI_CAPTURE_MANIFEST_NOT_CANONICAL")
    return canonical, payload


def validate_capture_binding(
    *,
    challenge_id: str,
    nonce_b64url: str,
    manifest_text: str,
    image_bytes: bytes,
) -> tuple[bytes, dict[str, Any], str, str, str]:
    if not isinstance(image_bytes, bytes) or not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        raise CaptureVerificationError("DSI_CAPTURE_IMAGE_SIZE_INVALID", 413)
    nonce = _decode_b64url(nonce_b64url, field="nonce", maximum=64)
    if len(nonce) != 32:
        raise CaptureVerificationError("DSI_CAPTURE_NONCE_INVALID")

    canonical, manifest = canonical_manifest(manifest_text)
    manifest_sha = _sha256_hex(canonical)
    image_sha = _sha256_hex(image_bytes)

    # The current native Camera2 upload contract is encoded JPEG only. DNG/RAW
    # and YUV are not silently interpreted as JPEG or given colour authority.
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            encoded_format = image.format
            actual_width, actual_height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise CaptureVerificationError("DSI_CAPTURE_IMAGE_DECODE_INVALID", 422) from exc
    if encoded_format != "JPEG":
        raise CaptureVerificationError("DSI_CAPTURE_IMAGE_FORMAT_UNSUPPORTED", 422)
    if (
        not isinstance(manifest.get("output_width"), int)
        or not isinstance(manifest.get("output_height"), int)
        or manifest["output_width"] != actual_width
        or manifest["output_height"] != actual_height
    ):
        raise CaptureVerificationError("DSI_CAPTURE_IMAGE_DIMENSIONS_MISMATCH")
    if manifest.get("output_format") != "jpeg":
        raise CaptureVerificationError("DSI_CAPTURE_IMAGE_FORMAT_MISMATCH")

    required = {
        "schema_version": "dsi-capture-manifest-v1",
        "challenge_id": challenge_id,
        "challenge_nonce_sha256": _sha256_hex(nonce),
        "image_sha256": image_sha,
        "image_byte_count": len(image_bytes),
    }
    for key, expected in required.items():
        if manifest.get(key) != expected:
            raise CaptureVerificationError("DSI_CAPTURE_MANIFEST_BINDING_MISMATCH")
    capture_ref = manifest.get("capture_ref")
    if not isinstance(capture_ref, str) or not re.fullmatch(r"^cap_[A-Za-z0-9_-]{12,96}$", capture_ref):
        raise CaptureVerificationError("DSI_CAPTURE_MANIFEST_BINDING_MISMATCH")

    device_hash = manifest.get("device_pipeline_fingerprint_sha256")
    report = manifest.get("device_baseline_report")
    fingerprint = report.get("fingerprint") if isinstance(report, dict) else None
    if (
        not isinstance(device_hash, str)
        or not HEX_256.fullmatch(device_hash)
        or not isinstance(fingerprint, dict)
        or _sha256_hex(_canonical_json(fingerprint).encode("utf-8")) != device_hash
    ):
        raise CaptureVerificationError("DSI_CAPTURE_DEVICE_FINGERPRINT_MISMATCH")

    return canonical, manifest, manifest_sha, image_sha, device_hash


def _parse_max_age(cache_control: str, age_header: str | None) -> int:
    match = re.search(r"(?:^|,)\s*max-age\s*=\s*['\"]?(\d+)", cache_control, re.IGNORECASE)
    if not match:
        raise CaptureVerificationError("DSI_ATTESTATION_STATUS_CACHE_POLICY_INVALID", 503)
    age = int(match.group(1))
    if age <= 0:
        raise CaptureVerificationError("DSI_ATTESTATION_STATUS_CACHE_EXPIRED", 503)
    try:
        current_age = max(0, int(age_header or "0"))
    except ValueError:
        raise CaptureVerificationError("DSI_ATTESTATION_STATUS_CACHE_POLICY_INVALID", 503)
    return max(0, age - current_age)


def _validate_status_document(document: Any) -> frozenset[str]:
    if not isinstance(document, dict) or set(document) != {"entries"}:
        raise CaptureVerificationError("DSI_ATTESTATION_STATUS_DOCUMENT_INVALID", 503)
    entries = document.get("entries")
    if not isinstance(entries, dict) or len(entries) > 100_000:
        raise CaptureVerificationError("DSI_ATTESTATION_STATUS_DOCUMENT_INVALID", 503)
    serials: set[str] = set()
    for serial, item in entries.items():
        if not isinstance(serial, str) or not re.fullmatch(r"^[a-f1-9][a-f0-9]*$", serial):
            raise CaptureVerificationError("DSI_ATTESTATION_STATUS_DOCUMENT_INVALID", 503)
        if not isinstance(item, dict) or item.get("status") not in {"REVOKED", "SUSPENDED"}:
            raise CaptureVerificationError("DSI_ATTESTATION_STATUS_DOCUMENT_INVALID", 503)
        allowed = {"status", "expires", "reason", "comment"}
        if set(item) - allowed:
            raise CaptureVerificationError("DSI_ATTESTATION_STATUS_DOCUMENT_INVALID", 503)
        # Both statuses deny use. Entries remain deny-listed even if they carry an
        # optional expiry; an expired/removed key must be removed by Google's feed.
        serials.add(serial)
    return frozenset(serials)


async def fetch_google_revoked_serials(
    *,
    now: float | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> frozenset[str]:
    current = time.time() if now is None else now
    cached_expires = float(_REVOCATION_CACHE.get("expires_at", 0.0))
    if current < cached_expires:
        cached = _REVOCATION_CACHE.get("serials")
        if isinstance(cached, frozenset):
            return cached

    headers: dict[str, str] = {"Accept": "application/json"}
    etag = _REVOCATION_CACHE.get("etag")
    if isinstance(etag, str) and etag:
        headers["If-None-Match"] = etag

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(5.0, connect=2.0),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        ) as client:
            response = await client.get(ATTESTATION_STATUS_URL, headers=headers)
    except httpx.HTTPError as exc:
        # Expired cache is never used after a failed refresh.
        raise CaptureVerificationError("DSI_ATTESTATION_STATUS_UNAVAILABLE", 503) from exc

    if response.status_code == 304:
        serials = _REVOCATION_CACHE.get("serials")
        if not isinstance(serials, frozenset):
            raise CaptureVerificationError("DSI_ATTESTATION_STATUS_CACHE_INVALID", 503)
        max_age = _parse_max_age(
            response.headers.get("cache-control", ""),
            response.headers.get("age"),
        )
        if max_age <= 0:
            raise CaptureVerificationError("DSI_ATTESTATION_STATUS_CACHE_EXPIRED", 503)
        _REVOCATION_CACHE.update(
            expires_at=current + max_age,
            etag=response.headers.get("etag") or etag,
        )
        return serials

    if response.status_code != 200:
        raise CaptureVerificationError("DSI_ATTESTATION_STATUS_UNAVAILABLE", 503)
    max_age = _parse_max_age(
        response.headers.get("cache-control", ""),
        response.headers.get("age"),
    )
    if max_age <= 0:
        raise CaptureVerificationError("DSI_ATTESTATION_STATUS_CACHE_EXPIRED", 503)
    if len(response.content) > 2 * 1024 * 1024:
        raise CaptureVerificationError("DSI_ATTESTATION_STATUS_DOCUMENT_INVALID", 503)
    try:
        document = response.json()
    except ValueError as exc:
        raise CaptureVerificationError("DSI_ATTESTATION_STATUS_DOCUMENT_INVALID", 503) from exc
    serials = _validate_status_document(document)
    _REVOCATION_CACHE.clear()
    _REVOCATION_CACHE.update(
        serials=serials,
        expires_at=current + max_age,
        etag=response.headers.get("etag"),
    )
    return serials


def _run_java_verifier(
    *,
    challenge_b64url: str,
    manifest_bytes: bytes,
    manifest_sha256: str,
    manifest_signature_b64url: str,
    certificate_chain_b64url: list[str],
    revoked_serials: frozenset[str],
) -> dict[str, Any]:
    jar_path = os.getenv("DSI_ANDROID_ATTESTATION_VERIFIER_JAR_PATH", "").strip()
    package_name = os.getenv("DSI_ANDROID_PACKAGE_NAME", "").strip()
    cert_sha = os.getenv("DSI_ANDROID_SIGNING_CERT_SHA256", "").strip().lower()
    version_code = os.getenv("DSI_ANDROID_MIN_PACKAGE_VERSION_CODE", "").strip()
    if not jar_path or not os.path.isabs(jar_path):
        raise CaptureVerificationError("DSI_ANDROID_ATTESTATION_VERIFIER_NOT_CONFIGURED", 503)
    if not package_name or not cert_sha or not HEX_256.fullmatch(cert_sha):
        raise CaptureVerificationError("DSI_ANDROID_APP_IDENTITY_NOT_CONFIGURED", 503)
    if not version_code.isdigit() or int(version_code) <= 0:
        raise CaptureVerificationError("DSI_ANDROID_APP_VERSION_POLICY_NOT_CONFIGURED", 503)
    if not (2 <= len(certificate_chain_b64url) <= MAX_CHAIN_CERTIFICATES):
        raise CaptureVerificationError("DSI_ANDROID_ATTESTATION_CHAIN_INVALID")
    for encoded in certificate_chain_b64url:
        _decode_b64url(encoded, field="certificate", maximum=MAX_CERTIFICATE_BYTES)

    request = {
        "challenge_b64url": challenge_b64url,
        "package_name": package_name,
        "minimum_package_version_code": version_code,
        "signing_certificate_sha256": cert_sha,
        "manifest_base64url": base64.urlsafe_b64encode(manifest_bytes).rstrip(b"=").decode("ascii"),
        "manifest_sha256": manifest_sha256,
        "manifest_signature_base64url": manifest_signature_b64url,
        "attestation_certificate_chain_base64url": certificate_chain_b64url,
        "revoked_serials": sorted(revoked_serials),
    }
    payload = json.dumps(request, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    if len(payload) > 3 * 1024 * 1024:
        raise CaptureVerificationError("DSI_ANDROID_ATTESTATION_ENVELOPE_TOO_LARGE", 413)
    try:
        result = subprocess.run(
            ["java", "-jar", jar_path],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=12,
            check=False,
            close_fds=True,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CaptureVerificationError("DSI_ANDROID_ATTESTATION_VERIFIER_UNAVAILABLE", 503) from exc
    try:
        output = json.loads(result.stdout.decode("utf-8")) if result.stdout else {}
    except (UnicodeError, ValueError) as exc:
        raise CaptureVerificationError("DSI_ANDROID_ATTESTATION_VERIFIER_INVALID_RESPONSE", 503) from exc
    if result.returncode != 0 or not isinstance(output, dict) or output.get("verified") is not True:
        raise CaptureVerificationError("DSI_ANDROID_KEY_ATTESTATION_REJECTED")
    if (
        output.get("code") != "ANDROID_KEY_ATTESTATION_VERIFIED"
        or output.get("manifest_sha256") != manifest_sha256
        or output.get("verified_boot_state") != "verified"
        or output.get("device_locked") is not True
        or output.get("security_level") not in {"trusted_environment", "strongbox"}
    ):
        raise CaptureVerificationError("DSI_ANDROID_KEY_ATTESTATION_REJECTED")
    return output


def _decode_play_integrity_token(token: str) -> dict[str, Any]:
    if not isinstance(token, str) or not token or len(token) > MAX_PLAY_TOKEN_LENGTH:
        raise CaptureVerificationError("DSI_PLAY_INTEGRITY_TOKEN_INVALID")
    package_name = os.getenv("DSI_ANDROID_PACKAGE_NAME", "").strip()
    if not package_name:
        raise CaptureVerificationError("DSI_ANDROID_APP_IDENTITY_NOT_CONFIGURED", 503)
    try:
        import google.auth
        from google.auth.transport.requests import Request
        import requests

        session = requests.Session()
        # Ignore ambient HTTP(S)_PROXY / .netrc settings for this security-critical
        # provider call. Use the same bounded, explicit session for ADC refresh.
        session.trust_env = False
        credentials, _project = google.auth.default(scopes=[PLAY_INTEGRITY_SCOPE])
        credentials.refresh(Request(session=session))
        response = session.post(
            f"{PLAY_INTEGRITY_DECODE_BASE}/{package_name}:decodeIntegrityToken",
            headers={
                "Authorization": f"Bearer {credentials.token}",
                "Accept": "application/json",
            },
            json={"integrity_token": token},
            timeout=(3.0, 8.0),
            allow_redirects=False,
        )
    except Exception as exc:
        raise CaptureVerificationError("DSI_PLAY_INTEGRITY_PROVIDER_UNAVAILABLE", 503) from exc
    if response.status_code != 200:
        raise CaptureVerificationError("DSI_PLAY_INTEGRITY_PROVIDER_REJECTED", 503)
    try:
        document = response.json()
        payload = document.get("tokenPayloadExternal") if isinstance(document, dict) else None
    except (ValueError, AttributeError) as exc:
        raise CaptureVerificationError("DSI_PLAY_INTEGRITY_RESPONSE_INVALID", 503) from exc
    if not isinstance(payload, dict):
        raise CaptureVerificationError("DSI_PLAY_INTEGRITY_RESPONSE_INVALID", 503)
    return payload


def validate_play_integrity_payload(
    payload: dict[str, Any],
    *,
    expected_manifest_sha256: str,
    now_ms: int | None = None,
) -> tuple[str, str, tuple[str, ...], str]:
    package_name = os.getenv("DSI_ANDROID_PACKAGE_NAME", "").strip()
    expected_cert = os.getenv("DSI_ANDROID_SIGNING_CERT_SHA256", "").strip().lower()
    min_version = os.getenv("DSI_ANDROID_MIN_PACKAGE_VERSION_CODE", "").strip()
    if not package_name or not HEX_256.fullmatch(expected_cert) or not min_version.isdigit():
        raise CaptureVerificationError("DSI_ANDROID_APP_IDENTITY_NOT_CONFIGURED", 503)

    request_details = payload.get("requestDetails")
    app_integrity = payload.get("appIntegrity")
    account_details = payload.get("accountDetails")
    device_integrity = payload.get("deviceIntegrity")
    if not all(isinstance(value, dict) for value in (
        request_details, app_integrity, account_details, device_integrity
    )):
        raise CaptureVerificationError("DSI_PLAY_INTEGRITY_VERDICT_INCOMPLETE")

    expected_request_hash = base64.urlsafe_b64encode(
        bytes.fromhex(expected_manifest_sha256)
    ).rstrip(b"=").decode("ascii")
    if (
        request_details.get("requestPackageName") != package_name
        or request_details.get("requestHash") != expected_request_hash
    ):
        raise CaptureVerificationError("DSI_PLAY_INTEGRITY_REQUEST_BINDING_MISMATCH")

    try:
        timestamp_ms = int(request_details.get("timestampMillis"))
    except (TypeError, ValueError) as exc:
        raise CaptureVerificationError("DSI_PLAY_INTEGRITY_TIMESTAMP_INVALID") from exc
    current_ms = int(time.time() * 1000) if now_ms is None else now_ms
    age_ms = current_ms - timestamp_ms
    if age_ms < -30_000 or age_ms > 120_000:
        raise CaptureVerificationError("DSI_PLAY_INTEGRITY_TOKEN_STALE")

    if (
        app_integrity.get("appRecognitionVerdict") != "PLAY_RECOGNIZED"
        or app_integrity.get("packageName") != package_name
    ):
        raise CaptureVerificationError("DSI_PLAY_INTEGRITY_APP_NOT_RECOGNIZED")

    cert_digests = app_integrity.get("certificateSha256Digest")
    if not isinstance(cert_digests, list) or not cert_digests:
        raise CaptureVerificationError("DSI_PLAY_INTEGRITY_CERTIFICATE_MISMATCH")
    expected_cert_b64 = base64.urlsafe_b64encode(bytes.fromhex(expected_cert)).rstrip(b"=").decode("ascii")
    if expected_cert_b64 not in cert_digests:
        raise CaptureVerificationError("DSI_PLAY_INTEGRITY_CERTIFICATE_MISMATCH")

    try:
        app_version = str(app_integrity.get("versionCode"))
        app_version_int = int(app_version)
    except (TypeError, ValueError) as exc:
        raise CaptureVerificationError("DSI_PLAY_INTEGRITY_APP_VERSION_INVALID") from exc
    if app_version_int < int(min_version):
        raise CaptureVerificationError("DSI_PLAY_INTEGRITY_APP_VERSION_TOO_OLD")

    licensing = account_details.get("appLicensingVerdict")
    if licensing != "LICENSED":
        raise CaptureVerificationError("DSI_PLAY_INTEGRITY_APP_NOT_LICENSED")

    device_verdicts = device_integrity.get("deviceRecognitionVerdict")
    if not isinstance(device_verdicts, list):
        raise CaptureVerificationError("DSI_PLAY_INTEGRITY_DEVICE_NOT_TRUSTED")
    accepted = {"MEETS_DEVICE_INTEGRITY", "MEETS_STRONG_INTEGRITY"}
    normalized = tuple(sorted({str(value) for value in device_verdicts}))
    if not (accepted & set(normalized)):
        raise CaptureVerificationError("DSI_PLAY_INTEGRITY_DEVICE_NOT_TRUSTED")

    return "PLAY_RECOGNIZED", licensing, normalized, app_version


async def verify_android_capture_envelope(
    *,
    challenge_id: str,
    nonce_b64url: str,
    manifest_text: str,
    manifest_signature_b64url: str,
    attestation_certificate_chain_base64url: list[str],
    play_integrity_token: str,
    image_bytes: bytes,
    revocation_transport: httpx.AsyncBaseTransport | None = None,
    play_decoder=None,
    key_verifier=None,
) -> VerifiedAndroidCapture:
    canonical, manifest, manifest_sha, image_sha, device_sha = validate_capture_binding(
        challenge_id=challenge_id,
        nonce_b64url=nonce_b64url,
        manifest_text=manifest_text,
        image_bytes=image_bytes,
    )
    signature = _decode_b64url(
        manifest_signature_b64url,
        field="signature",
        maximum=256,
    )
    if not signature:
        raise CaptureVerificationError("DSI_CAPTURE_SIGNATURE_INVALID")

    nonce = _decode_b64url(nonce_b64url, field="nonce", maximum=64)
    if len(nonce) != 32:
        raise CaptureVerificationError("DSI_CAPTURE_NONCE_INVALID")

    revoked = await fetch_google_revoked_serials(transport=revocation_transport)
    verifier = key_verifier or _run_java_verifier
    attestation = await asyncio.to_thread(
        verifier,
        challenge_b64url=nonce_b64url,
        manifest_bytes=canonical,
        manifest_sha256=manifest_sha,
        manifest_signature_b64url=manifest_signature_b64url,
        certificate_chain_b64url=attestation_certificate_chain_base64url,
        revoked_serials=revoked,
    )

    decoder = play_decoder or _decode_play_integrity_token
    play_payload = await asyncio.to_thread(decoder, play_integrity_token)
    app_verdict, licensing, device_verdicts, app_version = validate_play_integrity_payload(
        play_payload,
        expected_manifest_sha256=manifest_sha,
    )

    configured_package = os.getenv("DSI_ANDROID_PACKAGE_NAME", "").strip()
    configured_cert = os.getenv("DSI_ANDROID_SIGNING_CERT_SHA256", "").strip().lower()
    if manifest.get("app_runtime_version") is None:
        raise CaptureVerificationError("DSI_CAPTURE_MANIFEST_APP_VERSION_MISSING")
    return VerifiedAndroidCapture(
        package_name=configured_package,
        package_certificate_sha256=configured_cert,
        app_version=app_version,
        key_security_level=str(attestation["security_level"]),
        verified_boot_state="verified",
        device_locked=True,
        app_recognition_verdict=app_verdict,
        account_licensing_verdict=licensing,
        device_integrity_verdicts=device_verdicts,
        manifest_sha256=manifest_sha,
        image_sha256=image_sha,
        device_pipeline_fingerprint_sha256=device_sha,
        play_integrity_request_hash=manifest_sha,
    )
