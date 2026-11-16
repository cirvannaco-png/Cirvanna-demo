"""Server-side DSI Android capture verification.

Client manifests and Android fields are untrusted until the pinned Google verifier,
Play Integrity decode API, byte-level image checks and Identity Learning receipt
write have all succeeded. This module deliberately does not authorize colour
measurement or profile persistence.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import subprocess
import time
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

MAX_CAPTURE_IMAGE_BYTES = 5 * 1024 * 1024
MAX_MANIFEST_BYTES = 128 * 1024
MAX_CHAIN_CERTIFICATES = 8
MAX_CERTIFICATE_BYTES = 64 * 1024
MAX_CHAIN_BYTES = 256 * 1024
VERIFIER_POLICY_VERSION = "dsi-android-attestation-v1"
PLAY_INTEGRITY_SCOPE = "https://www.googleapis.com/auth/playintegrity"
PLAY_INTEGRITY_DECODE_URL = "https://playintegrity.googleapis.com/v1/{package_name}:decodeIntegrityToken"
HEX_SHA256 = re.compile(r"^[a-f0-9]{64}$")
BASE64URL_32 = re.compile(r"^[A-Za-z0-9_-]{43}$")


class CaptureVerificationError(Exception):
    """A cryptographic, binding or provider verification failure."""


class CaptureVerificationUnavailable(Exception):
    """A trusted verifier/provider is unavailable; callers must fail closed."""


class AndroidAttestationEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, frozen=True)

    schema_version: Literal["dsi-android-attestation-v1"] = Field(alias="schemaVersion")
    capture_ref: str = Field(alias="captureRef", pattern=r"^cap_[A-Za-z0-9_-]{12,96}$")
    challenge_id: str = Field(alias="challengeId", min_length=16, max_length=128)
    manifest_sha256: str = Field(alias="manifestSha256", pattern=r"^[a-f0-9]{64}$")
    image_sha256: str = Field(alias="imageSha256", pattern=r"^[a-f0-9]{64}$")
    device_pipeline_fingerprint_sha256: str = Field(
        alias="devicePipelineFingerprintSha256", pattern=r"^[a-f0-9]{64}$"
    )
    manifest_canonical_json: str = Field(alias="manifestCanonicalJson", min_length=2, max_length=MAX_MANIFEST_BYTES)
    signature_algorithm: Literal["SHA256withECDSA"] = Field(alias="signatureAlgorithm")
    signature_base64url: str = Field(alias="signatureBase64Url", min_length=80, max_length=256)
    attestation_certificate_chain_base64url: list[str] = Field(
        alias="attestationCertificateChainBase64Url", min_length=3, max_length=MAX_CHAIN_CERTIFICATES
    )
    play_integrity_token: str = Field(alias="playIntegrityToken", min_length=32, max_length=20_000)
    play_integrity_request_hash: str = Field(alias="playIntegrityRequestHash", min_length=43, max_length=43)
    # This is a client hint only; never copied into a receipt or used for a decision.
    android_key_security_level_hint: str | None = Field(default=None, alias="androidKeySecurityLevel", max_length=64)
    verification_state: Literal["pending_server_verification"] = Field(
        default="pending_server_verification", alias="verificationState"
    )
    absolute_colour_measurement_approved: Literal[False] = Field(
        default=False, alias="absoluteColourMeasurementApproved"
    )

    @staticmethod
    def _check_certificate_strings(value: list[str]) -> list[str]:
        total = 0
        for item in value:
            if not re.fullmatch(r"[A-Za-z0-9_-]+", item):
                raise ValueError("certificate chain item is not base64url")
            decoded = base64.urlsafe_b64decode(item + "=" * (-len(item) % 4))
            if not decoded or len(decoded) > MAX_CERTIFICATE_BYTES:
                raise ValueError("certificate chain item size is invalid")
            total += len(decoded)
            if total > MAX_CHAIN_BYTES:
                raise ValueError("certificate chain is too large")
        return value

    @classmethod
    def model_validate_checked(cls, payload: Any) -> "AndroidAttestationEnvelope":
        model = cls.model_validate(payload)
        cls._check_certificate_strings(model.attestation_certificate_chain_base64url)
        return model


class IdentityCaptureChallengeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject_id: str = Field(min_length=1, max_length=128)
    consent_id: str = Field(min_length=8, max_length=128)
    consent_version: str = Field(min_length=1, max_length=80)
    resource_id: str = Field(min_length=3, max_length=160)
    purpose: Literal[
        "cosmetic_skin_analysis",
        "facial_geometry_analysis",
        "body_tone_analysis",
        "appearance_correction",
    ]


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _canonical_json(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite JSON number")
        if value == 0:
            return "0"
        sign, raw_digits, exponent = value.as_tuple()
        digits = list(raw_digits)
        while len(digits) > 1 and digits[-1] == 0:
            digits.pop()
            exponent += 1
        if abs(exponent) > MAX_MANIFEST_BYTES:
            raise ValueError("JSON number exponent exceeds manifest limits")
        body = "".join(str(digit) for digit in digits)
        if exponent >= 0:
            rendered = body + ("0" * exponent)
        else:
            point = len(body) + exponent
            if point > 0:
                rendered = body[:point] + "." + body[point:]
            else:
                rendered = "0." + ("0" * (-point)) + body
        return ("-" if sign else "") + rendered
    if isinstance(value, list):
        return "[" + ",".join(_canonical_json(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("JSON object keys must be strings")
        return "{" + ",".join(
            json.dumps(key, ensure_ascii=False, separators=(",", ":")) + ":" + _canonical_json(value[key])
            for key in sorted(value)
        ) + "}"
    raise ValueError("unsupported canonical JSON value")


def parse_canonical_manifest(raw: str) -> tuple[dict[str, Any], bytes]:
    encoded = raw.encode("utf-8")
    if not encoded or len(encoded) > MAX_MANIFEST_BYTES:
        raise CaptureVerificationError("manifest size rejected")
    try:
        parsed = json.loads(
            raw,
            parse_float=Decimal,
            parse_int=int,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non-finite number")),
            object_pairs_hook=_reject_duplicate_pairs,
        )
        if not isinstance(parsed, dict):
            raise ValueError("manifest must be a JSON object")
        canonical = _canonical_json(parsed)
    except (ValueError, TypeError, InvalidOperation, json.JSONDecodeError) as exc:
        raise CaptureVerificationError("manifest JSON rejected") from exc
    if canonical != raw:
        raise CaptureVerificationError("manifest is not canonical JSON")
    return parsed, encoded


def decode_capture_nonce(value: str) -> bytes:
    if not BASE64URL_32.fullmatch(value):
        raise CaptureVerificationError("capture nonce encoding rejected")
    try:
        raw = base64.urlsafe_b64decode(value + "=")
    except (ValueError, base64.binascii.Error) as exc:
        raise CaptureVerificationError("capture nonce encoding rejected") from exc
    if len(raw) != 32 or base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != value:
        raise CaptureVerificationError("capture nonce must contain exactly 256 bits")
    return raw


def validate_capture_binding(
    envelope: AndroidAttestationEnvelope,
    *,
    challenge_nonce_base64url: str,
    image_bytes: bytes,
) -> tuple[dict[str, Any], bytes, str]:
    if not image_bytes or len(image_bytes) > MAX_CAPTURE_IMAGE_BYTES:
        raise CaptureVerificationError("capture image size rejected")
    nonce = decode_capture_nonce(challenge_nonce_base64url)
    manifest, manifest_bytes = parse_canonical_manifest(envelope.manifest_canonical_json)
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
    image_digest = hashlib.sha256(image_bytes).hexdigest()
    nonce_digest = hashlib.sha256(nonce).hexdigest()

    expected = {
        "schema_version": "dsi-capture-manifest-v1",
        "capture_ref": envelope.capture_ref,
        "challenge_id": envelope.challenge_id,
        "challenge_nonce_sha256": nonce_digest,
        "image_sha256": image_digest,
        "device_pipeline_fingerprint_sha256": envelope.device_pipeline_fingerprint_sha256,
        "absolute_colour_measurement_approved": False,
        "server_verification_required": True,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise CaptureVerificationError(f"capture manifest binding rejected: {key}")
    if type(manifest.get("image_byte_count")) is not int or manifest["image_byte_count"] != len(image_bytes):
        raise CaptureVerificationError("capture image byte count mismatch")
    if not HEX_SHA256.fullmatch(envelope.manifest_sha256) or manifest_digest != envelope.manifest_sha256:
        raise CaptureVerificationError("capture manifest digest mismatch")
    if envelope.image_sha256 != image_digest:
        raise CaptureVerificationError("capture image digest mismatch")
    if not HEX_SHA256.fullmatch(envelope.device_pipeline_fingerprint_sha256):
        raise CaptureVerificationError("device pipeline fingerprint digest invalid")

    request_hash = base64.urlsafe_b64encode(hashlib.sha256(manifest_bytes).digest()).rstrip(b"=").decode("ascii")
    if envelope.play_integrity_request_hash != request_hash:
        raise CaptureVerificationError("Play Integrity requestHash mismatch")
    return manifest, nonce, request_hash


def _required_config() -> dict[str, str]:
    package = os.getenv("DSI_ANDROID_CAPTURE_PACKAGE_NAME", "").strip()
    minimum_version = os.getenv("DSI_ANDROID_CAPTURE_MIN_VERSION_CODE", "").strip()
    signing_cert = os.getenv("DSI_ANDROID_CAPTURE_SIGNING_CERT_SHA256", "").strip().lower()
    sdk_version = os.getenv("DSI_ANDROID_CAPTURE_SDK_VERSION", "").strip()
    if not package or not re.fullmatch(r"[A-Za-z0-9_.]{3,200}", package):
        raise CaptureVerificationUnavailable("Android capture package policy is not configured")
    if not minimum_version.isdigit() or int(minimum_version) <= 0:
        raise CaptureVerificationUnavailable("Android capture minimum version code is not configured")
    if not HEX_SHA256.fullmatch(signing_cert):
        raise CaptureVerificationUnavailable("Android capture signing certificate policy is not configured")
    if not sdk_version:
        raise CaptureVerificationUnavailable("Android capture SDK version policy is not configured")
    return {
        "package_name": package,
        "minimum_version_code": minimum_version,
        "signing_certificate_sha256": signing_cert,
        "sdk_version": sdk_version,
    }


async def run_android_key_verifier(
    envelope: AndroidAttestationEnvelope,
    nonce: bytes,
    policy: dict[str, str],
) -> dict[str, Any]:
    executable = os.getenv(
        "DSI_ANDROID_ATTESTATION_VERIFIER_BIN",
        "/opt/dsi-attestation-verifier/bin/dsi-android-attestation-verifier",
    )
    if not os.path.isfile(executable) or not os.access(executable, os.X_OK):
        raise CaptureVerificationUnavailable("Android key-attestation verifier is not installed")
    request = {
        "challengeId": envelope.challenge_id,
        "challengeBase64Url": base64.urlsafe_b64encode(nonce).rstrip(b"=").decode("ascii"),
        "certificateChainBase64Url": envelope.attestation_certificate_chain_base64url,
        "manifestCanonicalJson": envelope.manifest_canonical_json,
        "manifestSha256": envelope.manifest_sha256,
        "signatureBase64Url": envelope.signature_base64url,
        "packageName": policy["package_name"],
        "minimumVersionCode": policy["minimum_version_code"],
        "signingCertificateSha256Hex": policy["signing_certificate_sha256"],
    }
    request_bytes = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(request_bytes) > 512 * 1024:
        raise CaptureVerificationError("Android attestation envelope exceeds size limit")
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            executable,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await asyncio.wait_for(process.communicate(request_bytes), timeout=18)
    except asyncio.TimeoutError as exc:
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()
        raise CaptureVerificationUnavailable("Android key-attestation verifier timed out") from exc
    except OSError as exc:
        raise CaptureVerificationUnavailable("Android key-attestation verifier failed to run") from exc
    if process.returncode == 2:
        raise CaptureVerificationError("Android key-attestation proof rejected")
    if process.returncode != 0 or len(stdout) > 16 * 1024:
        raise CaptureVerificationUnavailable("Android key-attestation verifier unavailable")
    try:
        result = json.loads(stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureVerificationUnavailable("Android key-attestation verifier returned invalid output") from exc
    if (
        not isinstance(result, dict)
        or result.get("status") != "verified"
        or result.get("packageName") != policy["package_name"]
        or result.get("packageCertificateSha256") != policy["signing_certificate_sha256"]
        or result.get("verifiedBootState") != "verified"
        or result.get("deviceLocked") is not True
        or result.get("certificateChainVerified") is not True
        or result.get("attestationChallengeMatched") is not True
        or result.get("manifestSignatureVerified") is not True
        or result.get("keySecurityLevel") not in {"strongbox", "trusted_environment"}
    ):
        raise CaptureVerificationError("Android key-attestation result violates server policy")
    return result


def validate_play_integrity_payload(
    payload: dict[str, Any],
    *,
    package_name: str,
    minimum_version_code: int,
    expected_request_hash: str,
    signing_certificate_sha256_hex: str,
    now_ms: int | None = None,
    maximum_age_ms: int = 120_000,
    maximum_future_skew_ms: int = 10_000,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise CaptureVerificationError("Play Integrity payload is invalid")
    request = payload.get("requestDetails")
    account = payload.get("accountDetails")
    app = payload.get("appIntegrity")
    device = payload.get("deviceIntegrity")
    if not all(isinstance(item, dict) for item in (request, account, app, device)):
        raise CaptureVerificationError("Play Integrity verdict sections are missing")

    if request.get("requestPackageName") != package_name:
        raise CaptureVerificationError("Play Integrity package name mismatch")
    if request.get("requestHash") != expected_request_hash:
        raise CaptureVerificationError("Play Integrity requestHash mismatch")
    timestamp_raw = request.get("timestampMillis")
    try:
        timestamp = int(timestamp_raw)
    except (TypeError, ValueError) as exc:
        raise CaptureVerificationError("Play Integrity timestamp missing") from exc
    current = int(time.time() * 1000) if now_ms is None else now_ms
    age = current - timestamp
    if age < -maximum_future_skew_ms or age > maximum_age_ms:
        raise CaptureVerificationError("Play Integrity token is stale or from the future")

    if app.get("packageName") != package_name:
        raise CaptureVerificationError("Play Integrity app package mismatch")
    if app.get("appRecognitionVerdict") != "PLAY_RECOGNIZED":
        raise CaptureVerificationError("Play Integrity does not recognize the installed app")
    version_code = app.get("versionCode")
    try:
        if int(version_code) < minimum_version_code:
            raise CaptureVerificationError("Play Integrity app version is below policy")
    except (TypeError, ValueError) as exc:
        raise CaptureVerificationError("Play Integrity app version is invalid") from exc

    expected_cert_b64 = base64.b64encode(bytes.fromhex(signing_certificate_sha256_hex)).decode("ascii")
    certificate_digests = app.get("certificateSha256Digest")
    if not isinstance(certificate_digests, list) or expected_cert_b64 not in certificate_digests:
        raise CaptureVerificationError("Play Integrity signing certificate mismatch")
    if account.get("appLicensingVerdict") != "LICENSED":
        raise CaptureVerificationError("Play Integrity app licensing is not active")

    device_verdicts = device.get("deviceRecognitionVerdict")
    if not isinstance(device_verdicts, list):
        raise CaptureVerificationError("Play Integrity device verdict is missing")
    accepted_device_verdicts = [
        item for item in device_verdicts
        if item in {"MEETS_DEVICE_INTEGRITY", "MEETS_STRONG_INTEGRITY"}
    ]
    if not accepted_device_verdicts:
        raise CaptureVerificationError("Play Integrity device integrity threshold not met")
    return {
        "app_recognition_verdict": "PLAY_RECOGNIZED",
        "account_licensing_verdict": "LICENSED",
        "device_integrity_verdicts": accepted_device_verdicts,
        "package_name": package_name,
        "app_version_code": int(version_code),
        "token_timestamp_ms": timestamp,
    }


def decode_play_integrity_token(*, package_name: str, token: str) -> dict[str, Any]:
    """Decode on the server with ADC/service-account credentials; never trust client claims."""
    try:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        credentials, _project = google.auth.default(scopes=[PLAY_INTEGRITY_SCOPE])
        session = AuthorizedSession(credentials)
        response = session.post(
            PLAY_INTEGRITY_DECODE_URL.format(package_name=package_name),
            json={"integrity_token": token},
            timeout=(5, 10),
        )
        if response.status_code != 200:
            raise CaptureVerificationError("Play Integrity decode rejected")
        body = response.json()
        decoded = body.get("tokenPayloadExternal") if isinstance(body, dict) else None
        if not isinstance(decoded, dict):
            raise CaptureVerificationError("Play Integrity decode response is invalid")
        return decoded
    except CaptureVerificationError:
        raise
    except Exception as exc:
        raise CaptureVerificationUnavailable("Play Integrity decode service unavailable") from exc


def _identity_url(path: str) -> str:
    base = os.getenv("IDENTITY_LEARNING_SERVICE_URL", "").strip().rstrip("/")
    if not base:
        raise CaptureVerificationUnavailable("Identity Learning service URL is not configured")
    parsed = urlsplit(base)
    host = (parsed.hostname or "").lower()
    local = host in {"localhost", "127.0.0.1", "::1"}
    if parsed.username or parsed.password or parsed.query or parsed.fragment or not host or (
        parsed.scheme != "https" and not (parsed.scheme == "http" and local)
    ):
        raise CaptureVerificationUnavailable("Identity Learning URL must use trusted HTTPS")
    return base + path


async def issue_identity_capture_challenge(payload: IdentityCaptureChallengeRequest) -> dict[str, Any]:
    token = os.getenv("IDENTITY_DSI_CAPTURE_SERVICE_TOKEN", "").strip()
    if len(token.encode("utf-8")) < 32:
        raise CaptureVerificationUnavailable("Identity DSI capture service token is not configured")
    url = _identity_url("/internal/v1/dsi/capture-challenges")
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(8.0, connect=2.0), trust_env=False, follow_redirects=False
        ) as client:
            response = await client.post(
                url,
                json=payload.model_dump(mode="json"),
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise CaptureVerificationUnavailable("Identity challenge service unavailable") from exc
    if response.status_code in {401, 403, 404, 409, 422}:
        raise CaptureVerificationError("Identity challenge could not be issued for this consent")
    if response.status_code != 200:
        raise CaptureVerificationUnavailable("Identity challenge service unavailable")
    try:
        result = response.json()
    except ValueError as exc:
        raise CaptureVerificationUnavailable("Identity challenge response is invalid") from exc
    if not isinstance(result, dict) or result.get("status") != "issued":
        raise CaptureVerificationUnavailable("Identity challenge response is invalid")
    return result


async def persist_identity_capture_receipt(
    *,
    envelope: AndroidAttestationEnvelope,
    manifest: dict[str, Any],
    nonce_base64url: str,
    key_result: dict[str, Any],
    play_result: dict[str, Any],
    policy: dict[str, str],
) -> dict[str, Any]:
    token = os.getenv("IDENTITY_DSI_CAPTURE_SERVICE_TOKEN", "").strip()
    if len(token.encode("utf-8")) < 32:
        raise CaptureVerificationUnavailable("Identity DSI capture service token is not configured")
    version = manifest.get("capture_app_version") or manifest.get("app_runtime_version")
    if not isinstance(version, str) or not version.strip():
        raise CaptureVerificationError("capture app version is missing from manifest")
    body = {
        "nonce_b64url": nonce_base64url,
        "manifest_sha256": envelope.manifest_sha256,
        "image_sha256": envelope.image_sha256,
        "device_pipeline_fingerprint_sha256": envelope.device_pipeline_fingerprint_sha256,
        "key_attestation_challenge_sha256": hashlib.sha256(decode_capture_nonce(nonce_base64url)).hexdigest(),
        # Identity schema currently stores the hexadecimal manifest digest here.
        "play_integrity_request_hash": envelope.manifest_sha256,
        "package_name": policy["package_name"],
        "package_certificate_sha256": policy["signing_certificate_sha256"],
        "app_version": version,
        "sdk_version": policy["sdk_version"],
        "verifier_policy_version": VERIFIER_POLICY_VERSION,
        "key_security_level": key_result["keySecurityLevel"],
        "verified_boot_state": key_result["verifiedBootState"],
        "app_recognition_verdict": play_result["app_recognition_verdict"],
        "account_licensing_verdict": play_result["account_licensing_verdict"],
        "device_integrity_verdicts": play_result["device_integrity_verdicts"],
    }
    url = _identity_url(
        "/internal/v1/dsi/capture-challenges/" + envelope.challenge_id + "/consume"
    )
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(8.0, connect=2.0), trust_env=False, follow_redirects=False
        ) as client:
            response = await client.post(
                url,
                json=body,
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise CaptureVerificationUnavailable("Identity receipt persistence unavailable") from exc
    if response.status_code in {403, 404, 409, 410, 422}:
        raise CaptureVerificationError("Identity rejected the capture challenge or consent")
    if response.status_code != 200:
        raise CaptureVerificationUnavailable("Identity receipt persistence unavailable")
    try:
        result = response.json()
    except ValueError as exc:
        raise CaptureVerificationUnavailable("Identity receipt response is invalid") from exc
    receipt = result.get("receipt") if isinstance(result, dict) else None
    if not isinstance(result, dict) or result.get("status") != "verified_receipt_created" or not isinstance(receipt, dict):
        raise CaptureVerificationUnavailable("Identity receipt response is invalid")
    return receipt


async def verify_and_persist_capture(
    envelope: AndroidAttestationEnvelope,
    *,
    challenge_nonce_base64url: str,
    image_bytes: bytes,
) -> dict[str, Any]:
    manifest, nonce, request_hash = validate_capture_binding(
        envelope,
        challenge_nonce_base64url=challenge_nonce_base64url,
        image_bytes=image_bytes,
    )
    policy = _required_config()
    key_result = await run_android_key_verifier(envelope, nonce, policy)
    try:
        decoded = await asyncio.to_thread(
            decode_play_integrity_token,
            package_name=policy["package_name"],
            token=envelope.play_integrity_token,
        )
    except CaptureVerificationError:
        raise
    except Exception as exc:
        raise CaptureVerificationUnavailable("Play Integrity decoding failed") from exc
    play_result = validate_play_integrity_payload(
        decoded,
        package_name=policy["package_name"],
        minimum_version_code=int(policy["minimum_version_code"]),
        expected_request_hash=request_hash,
        signing_certificate_sha256_hex=policy["signing_certificate_sha256"],
    )
    receipt = await persist_identity_capture_receipt(
        envelope=envelope,
        manifest=manifest,
        nonce_base64url=challenge_nonce_base64url,
        key_result=key_result,
        play_result=play_result,
        policy=policy,
    )
    return {
        "status": "verified",
        "receipt": receipt,
        "key_attestation": {
            "key_security_level": key_result["keySecurityLevel"],
            "verified_boot_state": key_result["verifiedBootState"],
            "device_locked": True,
            "certificate_chain_verified": True,
            "manifest_signature_verified": True,
            "verifier_policy_version": VERIFIER_POLICY_VERSION,
        },
        "play_integrity": play_result,
        "absolute_colour_measurement_approved": False,
        "measurement_uncertainty_validated": False,
        "profile_persistence_authorized": False,
    }


async def verify_identity_capture_receipt(
    *,
    receipt_id: str,
    subject_id: str,
    resource_id: str,
    purpose: Literal[
        "cosmetic_skin_analysis",
        "facial_geometry_analysis",
        "body_tone_analysis",
        "appearance_correction",
    ],
    manifest_sha256: str,
    image_sha256: str,
    device_pipeline_fingerprint_sha256: str,
) -> dict[str, Any]:
    token = os.getenv("IDENTITY_DSI_CAPTURE_SERVICE_TOKEN", "").strip()
    if len(token.encode("utf-8")) < 32:
        raise CaptureVerificationUnavailable("Identity DSI capture service token is not configured")
    body = {
        "receipt_id": receipt_id,
        "subject_id": subject_id,
        "resource_id": resource_id,
        "purpose": purpose,
        "manifest_sha256": manifest_sha256,
        "image_sha256": image_sha256,
        "device_pipeline_fingerprint_sha256": device_pipeline_fingerprint_sha256,
    }
    url = _identity_url("/internal/v1/dsi/capture-receipts/verify")
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(8.0, connect=2.0), trust_env=False, follow_redirects=False
        ) as client:
            response = await client.post(
                url,
                json=body,
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise CaptureVerificationUnavailable("Identity receipt verification unavailable") from exc
    if response.status_code in {403, 404, 410, 422}:
        raise CaptureVerificationError("capture receipt is expired, revoked or out of scope")
    if response.status_code != 200:
        raise CaptureVerificationUnavailable("Identity receipt verification unavailable")
    try:
        result = response.json()
    except ValueError as exc:
        raise CaptureVerificationUnavailable("Identity receipt verification response is invalid") from exc
    if not isinstance(result, dict) or result.get("verified") is not True or not isinstance(result.get("receipt"), dict):
        raise CaptureVerificationError("Identity receipt is not active")
    return result
