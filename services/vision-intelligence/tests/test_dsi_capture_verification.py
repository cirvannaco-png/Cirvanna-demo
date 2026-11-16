from __future__ import annotations

import base64
import hashlib
import json

import httpx
import pytest

from app import dsi_capture_verification as verify


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def make_manifest(challenge_id="challenge-1234", nonce=None, image=b"image-bytes"):
    nonce = nonce or (b"n" * 32)
    fingerprint = {"platform": "android", "camera_id": "0", "os_release": "Android 15"}
    fingerprint_sha = hashlib.sha256(verify._canonical_json(fingerprint).encode()).hexdigest()
    manifest = {
        "schema_version": "dsi-capture-manifest-v1",
        "capture_ref": "cap_abcdefghijkl",
        "challenge_id": challenge_id,
        "challenge_nonce_sha256": hashlib.sha256(nonce).hexdigest(),
        "image_sha256": hashlib.sha256(image).hexdigest(),
        "image_byte_count": len(image),
        "device_pipeline_fingerprint_sha256": fingerprint_sha,
        "device_baseline_report": {"fingerprint": fingerprint},
        "app_runtime_version": "0.1.0",
        "absolute_colour_measurement_approved": False,
    }
    return verify._canonical_json(manifest), manifest, nonce, image


def valid_play_payload(monkeypatch, manifest_sha, **overrides):
    monkeypatch.setenv("DSI_ANDROID_PACKAGE_NAME", "co.cirvanna.app")
    monkeypatch.setenv("DSI_ANDROID_SIGNING_CERT_SHA256", "a" * 64)
    monkeypatch.setenv("DSI_ANDROID_MIN_PACKAGE_VERSION_CODE", "42")
    cert = b64url(bytes.fromhex("a" * 64))
    value = {
        "requestDetails": {
            "requestPackageName": "co.cirvanna.app",
            "requestHash": b64url(bytes.fromhex(manifest_sha)),
            "timestampMillis": "1000000",
        },
        "appIntegrity": {
            "appRecognitionVerdict": "PLAY_RECOGNIZED",
            "packageName": "co.cirvanna.app",
            "certificateSha256Digest": [cert],
            "versionCode": "42",
        },
        "accountDetails": {"appLicensingVerdict": "LICENSED"},
        "deviceIntegrity": {"deviceRecognitionVerdict": ["MEETS_DEVICE_INTEGRITY"]},
    }
    value.update(overrides)
    return value


def test_canonical_manifest_accepts_exact_canonical_json():
    raw = '{"a":1,"b":2}'
    canonical, parsed = verify.canonical_manifest(raw)
    assert canonical == raw.encode()
    assert parsed == {"a": 1, "b": 2}


@pytest.mark.parametrize("raw", [
    '{"b":2,"a":1}', '{"a":1, "b":2}', '{"a":1,"a":2}', '{"a":NaN}',
])
def test_canonical_manifest_rejects_ambiguous_or_noncanonical_json(raw):
    with pytest.raises(verify.CaptureVerificationError):
        verify.canonical_manifest(raw)


def test_manifest_image_and_challenge_are_bound_exactly():
    manifest_text, manifest, nonce, image = make_manifest()
    canonical, parsed, manifest_sha, image_sha, device_sha = verify.validate_capture_binding(
        challenge_id="challenge-1234",
        nonce_b64url=b64url(nonce),
        manifest_text=manifest_text,
        image_bytes=image,
    )
    assert parsed == manifest
    assert manifest_sha == hashlib.sha256(canonical).hexdigest()
    assert image_sha == hashlib.sha256(image).hexdigest()
    assert device_sha == manifest["device_pipeline_fingerprint_sha256"]


def test_manipulated_image_bytes_are_rejected_before_verifiers_run():
    manifest_text, _manifest, nonce, _image = make_manifest()
    with pytest.raises(verify.CaptureVerificationError, match="MANIFEST_BINDING_MISMATCH"):
        verify.validate_capture_binding(
            challenge_id="challenge-1234",
            nonce_b64url=b64url(nonce),
            manifest_text=manifest_text,
            image_bytes=b"attacker-replaced-image",
        )


@pytest.mark.parametrize("change", [
    {"challenge_id": "different-challenge"},
    {"nonce": b"x" * 32},
])
def test_forged_challenge_or_nonce_is_rejected(change):
    manifest_text, _manifest, nonce, image = make_manifest()
    with pytest.raises(verify.CaptureVerificationError):
        verify.validate_capture_binding(
            challenge_id=change.get("challenge_id", "challenge-1234"),
            nonce_b64url=b64url(change.get("nonce", nonce)),
            manifest_text=manifest_text,
            image_bytes=image,
        )


def test_forged_device_pipeline_digest_is_rejected():
    manifest_text, _manifest, nonce, image = make_manifest()
    parsed = json.loads(manifest_text)
    parsed["device_pipeline_fingerprint_sha256"] = "f" * 64
    tampered_text = verify._canonical_json(parsed)
    with pytest.raises(verify.CaptureVerificationError, match="FINGERPRINT_MISMATCH"):
        verify.validate_capture_binding(
            challenge_id="challenge-1234",
            nonce_b64url=b64url(nonce),
            manifest_text=tampered_text,
            image_bytes=image,
        )


@pytest.mark.parametrize("status", ["REVOKED", "SUSPENDED"])
def test_google_attestation_status_rejects_revoked_and_suspended(status):
    assert verify._validate_status_document(
        {"entries": {"a12b34": {"status": status}}}
    ) == frozenset({"a12b34"})


@pytest.mark.parametrize("document", [
    [], {}, {"entries": {"not-hex": {"status": "REVOKED"}}},
    {"entries": {"abc123": {"status": "GOOD"}}},
    {"entries": {"abc123": {"status": "REVOKED", "unexpected": "x"}}},
])
def test_malformed_google_status_list_fails_closed(document):
    with pytest.raises(verify.CaptureVerificationError):
        verify._validate_status_document(document)


@pytest.mark.asyncio
async def test_revocation_list_caches_only_for_google_cache_control_max_age():
    verify._REVOCATION_CACHE.clear()
    calls = []

    async def response_handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            headers={"Cache-Control": "public, max-age=60", "ETag": '"status-v1"'},
            json={"entries": {"aabbcc": {"status": "SUSPENDED"}}},
        )

    transport = httpx.MockTransport(response_handler)
    first = await verify.fetch_google_revoked_serials(now=100, transport=transport)
    second = await verify.fetch_google_revoked_serials(now=120, transport=transport)
    assert first == frozenset({"aabbcc"})
    assert second == first
    assert len(calls) == 1
    verify._REVOCATION_CACHE.clear()


@pytest.mark.asyncio
async def test_expired_revocation_cache_is_not_used_if_google_refresh_fails():
    verify._REVOCATION_CACHE.clear()
    verify._REVOCATION_CACHE.update(serials=frozenset(), expires_at=50, etag=None)

    def fail(_request):
        raise httpx.ConnectError("offline")

    with pytest.raises(verify.CaptureVerificationError, match="STATUS_UNAVAILABLE"):
        await verify.fetch_google_revoked_serials(
            now=100,
            transport=httpx.MockTransport(fail),
        )
    verify._REVOCATION_CACHE.clear()


def test_play_integrity_requires_package_hash_certificate_license_and_device(monkeypatch):
    payload = valid_play_payload(monkeypatch, "c" * 64)
    verdict = verify.validate_play_integrity_payload(
        payload, expected_manifest_sha256="c" * 64, now_ms=1_000_000
    )
    assert verdict == (
        "PLAY_RECOGNIZED", "LICENSED", ("MEETS_DEVICE_INTEGRITY",), "42"
    )


@pytest.mark.parametrize(("field", "replacement", "error"), [
    ("requestDetails", {
        "requestPackageName": "co.attacker.app",
        "requestHash": b64url(bytes.fromhex("c" * 32)),
        "timestampMillis": "1000000",
    }, "REQUEST_BINDING_MISMATCH"),
    ("appIntegrity", {
        "appRecognitionVerdict": "UNRECOGNIZED_VERSION",
        "packageName": "co.cirvanna.app",
        "certificateSha256Digest": [b64url(bytes.fromhex("a" * 32))],
        "versionCode": "42",
    }, "APP_NOT_RECOGNIZED"),
    ("appIntegrity", {
        "appRecognitionVerdict": "PLAY_RECOGNIZED",
        "packageName": "co.cirvanna.app",
        "certificateSha256Digest": [b64url(bytes.fromhex("b" * 32))],
        "versionCode": "42",
    }, "CERTIFICATE_MISMATCH"),
    ("accountDetails", {"appLicensingVerdict": "UNLICENSED"}, "APP_NOT_LICENSED"),
    ("deviceIntegrity", {
        "deviceRecognitionVerdict": ["MEETS_BASIC_INTEGRITY"]
    }, "DEVICE_NOT_TRUSTED"),
])
def test_play_integrity_rejects_forged_or_insufficient_claims(
    monkeypatch, field, replacement, error
):
    payload = valid_play_payload(monkeypatch, "c" * 64, **{field: replacement})
    with pytest.raises(verify.CaptureVerificationError, match=error):
        verify.validate_play_integrity_payload(
            payload, expected_manifest_sha256="c" * 64, now_ms=1_000_000
        )


def test_play_integrity_rejects_stale_tokens(monkeypatch):
    payload = valid_play_payload(monkeypatch, "c" * 64)
    with pytest.raises(verify.CaptureVerificationError, match="TOKEN_STALE"):
        verify.validate_play_integrity_payload(
            payload, expected_manifest_sha256="c" * 64, now_ms=1_200_001
        )


@pytest.mark.asyncio
async def test_receipt_inputs_are_returned_only_after_both_verifiers_pass(monkeypatch):
    verify._REVOCATION_CACHE.clear()
    verify._REVOCATION_CACHE.update(serials=frozenset(), expires_at=1e20)
    manifest_text, _manifest, nonce, image = make_manifest()
    canonical, _parsed = verify.canonical_manifest(manifest_text)
    manifest_sha = hashlib.sha256(canonical).hexdigest()
    key_calls, play_calls = [], []

    def fake_key_verifier(**kwargs):
        key_calls.append(kwargs)
        return {
            "verified": True,
            "code": "ANDROID_KEY_ATTESTATION_VERIFIED",
            "security_level": "trusted_environment",
            "verified_boot_state": "verified",
            "device_locked": True,
            "manifest_sha256": kwargs["manifest_sha256"],
        }

    def fake_play_decoder(_token):
        play_calls.append(True)
        return valid_play_payload(monkeypatch, manifest_sha)

    result = await verify.verify_android_capture_envelope(
        challenge_id="challenge-1234",
        nonce_b64url=b64url(nonce),
        manifest_text=manifest_text,
        manifest_signature_b64url=b64url(b"test-signature"),
        attestation_certificate_chain_base64url=[b64url(b"leaf"), b64url(b"intermediate")],
        play_integrity_token="opaque-token",
        image_bytes=image,
        key_verifier=fake_key_verifier,
        play_decoder=fake_play_decoder,
    )
    assert len(key_calls) == 1 and len(play_calls) == 1
    assert result.manifest_sha256 == manifest_sha
    assert result.image_sha256 == hashlib.sha256(image).hexdigest()
    assert result.verified_boot_state == "verified"
    assert result.key_security_level == "trusted_environment"
    verify._REVOCATION_CACHE.clear()


@pytest.mark.asyncio
async def test_play_integrity_failure_means_no_verified_capture_result(monkeypatch):
    verify._REVOCATION_CACHE.clear()
    verify._REVOCATION_CACHE.update(serials=frozenset(), expires_at=1e20)
    manifest_text, _manifest, nonce, image = make_manifest()
    canonical, _parsed = verify.canonical_manifest(manifest_text)
    manifest_sha = hashlib.sha256(canonical).hexdigest()

    def fake_key_verifier(**kwargs):
        return {
            "verified": True,
            "code": "ANDROID_KEY_ATTESTATION_VERIFIED",
            "security_level": "trusted_environment",
            "verified_boot_state": "verified",
            "device_locked": True,
            "manifest_sha256": kwargs["manifest_sha256"],
        }

    def bad_play_decoder(_token):
        payload = valid_play_payload(monkeypatch, manifest_sha)
        payload["accountDetails"]["appLicensingVerdict"] = "UNLICENSED"
        return payload

    with pytest.raises(verify.CaptureVerificationError, match="APP_NOT_LICENSED"):
        await verify.verify_android_capture_envelope(
            challenge_id="challenge-1234",
            nonce_b64url=b64url(nonce),
            manifest_text=manifest_text,
            manifest_signature_b64url=b64url(b"test-signature"),
            attestation_certificate_chain_base64url=[b64url(b"leaf"), b64url(b"intermediate")],
            play_integrity_token="opaque-token",
            image_bytes=image,
            key_verifier=fake_key_verifier,
            play_decoder=bad_play_decoder,
        )
    verify._REVOCATION_CACHE.clear()
