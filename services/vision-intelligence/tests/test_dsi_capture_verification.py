from __future__ import annotations

import base64
import hashlib

import pytest
from pydantic import ValidationError

from app.dsi_capture_verification import (
    AndroidAttestationEnvelope,
    CaptureVerificationError,
    _canonical_json,
    validate_capture_binding,
    validate_play_integrity_payload,
)


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def nonce_b64() -> str:
    return base64.urlsafe_b64encode(b"n" * 32).rstrip(b"=").decode("ascii")


def envelope_and_image(**overrides):
    image = b"trusted-image-bytes-for-test"
    nonce = nonce_b64()
    manifest = {
        "schema_version": "dsi-capture-manifest-v1",
        "capture_ref": "cap_abcdefghijkl",
        "challenge_id": "dsi_challenge_0123456789abcdef",
        "challenge_nonce_sha256": sha(b"n" * 32),
        "image_sha256": sha(image),
        "image_byte_count": len(image),
        "device_pipeline_fingerprint_sha256": "a" * 64,
        "absolute_colour_measurement_approved": False,
        "server_verification_required": True,
    }
    raw_manifest = _canonical_json(manifest)
    manifest_digest = sha(raw_manifest.encode())
    request_hash = base64.urlsafe_b64encode(hashlib.sha256(raw_manifest.encode()).digest()).rstrip(b"=").decode()
    values = {
        "schemaVersion": "dsi-android-attestation-v1",
        "captureRef": "cap_abcdefghijkl",
        "challengeId": manifest["challenge_id"],
        "manifestSha256": manifest_digest,
        "imageSha256": manifest["image_sha256"],
        "devicePipelineFingerprintSha256": manifest["device_pipeline_fingerprint_sha256"],
        "manifestCanonicalJson": raw_manifest,
        "signatureAlgorithm": "SHA256withECDSA",
        "signatureBase64Url": "A" * 86,
        "attestationCertificateChainBase64Url": ["QUJD", "REVG", "R0hJ"],
        "playIntegrityToken": "x" * 80,
        "playIntegrityRequestHash": request_hash,
        "androidKeySecurityLevel": "software",
        "verificationState": "pending_server_verification",
        "absoluteColourMeasurementApproved": False,
    }
    values.update(overrides)
    return AndroidAttestationEnvelope.model_validate_checked(values), image, nonce, manifest, request_hash


def test_client_security_level_hint_is_not_used_for_server_result():
    envelope, _image, _nonce, _manifest, _request_hash = envelope_and_image()
    assert envelope.android_key_security_level_hint == "software"
    assert envelope.verification_state == "pending_server_verification"


def test_exact_image_and_manifest_are_bound_to_nonce_and_challenge():
    envelope, image, nonce, _manifest, request_hash = envelope_and_image()
    manifest, decoded_nonce, actual_hash = validate_capture_binding(
        envelope,
        challenge_nonce_base64url=nonce,
        image_bytes=image,
    )
    assert manifest["capture_ref"] == envelope.capture_ref
    assert decoded_nonce == b"n" * 32
    assert actual_hash == request_hash


@pytest.mark.parametrize(
    "mutator",
    [
        lambda image: image + b"tampered",
        lambda image: image[:-1],
    ],
)
def test_manipulated_image_bytes_are_rejected(mutator):
    envelope, image, nonce, _manifest, _request_hash = envelope_and_image()
    with pytest.raises(CaptureVerificationError):
        validate_capture_binding(
            envelope,
            challenge_nonce_base64url=nonce,
            image_bytes=mutator(image),
        )


def test_wrong_nonce_is_rejected():
    envelope, image, _nonce, _manifest, _request_hash = envelope_and_image()
    another_nonce = base64.urlsafe_b64encode(b"x" * 32).rstrip(b"=").decode()
    with pytest.raises(CaptureVerificationError):
        validate_capture_binding(
            envelope,
            challenge_nonce_base64url=another_nonce,
            image_bytes=image,
        )


def test_noncanonical_manifest_is_rejected():
    envelope, image, nonce, _manifest, _request_hash = envelope_and_image()
    whitespace = envelope.manifest_canonical_json.replace(",", ", ", 1)
    altered = envelope.model_copy(update={"manifest_canonical_json": whitespace})
    with pytest.raises(CaptureVerificationError):
        validate_capture_binding(
            altered,
            challenge_nonce_base64url=nonce,
            image_bytes=image,
        )


def test_false_or_missing_measurement_boundary_is_not_accepted():
    envelope, _image, _nonce, _manifest, _request_hash = envelope_and_image()
    payload = envelope.model_dump(by_alias=True)
    payload["absoluteColourMeasurementApproved"] = True
    with pytest.raises(ValidationError):
        AndroidAttestationEnvelope.model_validate_checked(payload)


def play_payload(*, now_ms: int, request_hash: str, cert_hex: str = "ab" * 32):
    cert_b64 = base64.b64encode(bytes.fromhex(cert_hex)).decode("ascii")
    return {
        "requestDetails": {
            "requestPackageName": "co.cirvanna.app",
            "requestHash": request_hash,
            "timestampMillis": str(now_ms),
        },
        "appIntegrity": {
            "packageName": "co.cirvanna.app",
            "appRecognitionVerdict": "PLAY_RECOGNIZED",
            "versionCode": "42",
            "certificateSha256Digest": [cert_b64],
        },
        "accountDetails": {"appLicensingVerdict": "LICENSED"},
        "deviceIntegrity": {
            "deviceRecognitionVerdict": ["MEETS_DEVICE_INTEGRITY", "MEETS_BASIC_INTEGRITY"]
        },
    }


def test_play_integrity_requires_recognized_app_license_and_device_integrity():
    now = 1_800_000_000_000
    result = validate_play_integrity_payload(
        play_payload(now_ms=now, request_hash="valid-hash"),
        package_name="co.cirvanna.app",
        minimum_version_code=40,
        expected_request_hash="valid-hash",
        signing_certificate_sha256_hex="ab" * 32,
        now_ms=now,
    )
    assert result["app_recognition_verdict"] == "PLAY_RECOGNIZED"
    assert result["account_licensing_verdict"] == "LICENSED"
    assert result["device_integrity_verdicts"] == ["MEETS_DEVICE_INTEGRITY"]


@pytest.mark.parametrize(
    "mutator",
    [
        lambda p: p["requestDetails"].update(requestHash="forged"),
        lambda p: p["requestDetails"].update(requestPackageName="co.attacker.app"),
        lambda p: p["requestDetails"].update(timestampMillis="1"),
        lambda p: p["appIntegrity"].update(appRecognitionVerdict="UNRECOGNIZED_VERSION"),
        lambda p: p["accountDetails"].update(appLicensingVerdict="UNLICENSED"),
        lambda p: p["deviceIntegrity"].update(deviceRecognitionVerdict=["MEETS_BASIC_INTEGRITY"]),
        lambda p: p["appIntegrity"].update(certificateSha256Digest=["Zm9yZ2Vk"]),
        lambda p: p["appIntegrity"].update(versionCode="1"),
    ],
)
def test_forged_or_weak_play_integrity_claims_fail_closed(mutator):
    now = 1_800_000_000_000
    payload = play_payload(now_ms=now, request_hash="valid-hash")
    mutator(payload)
    with pytest.raises(CaptureVerificationError):
        validate_play_integrity_payload(
            payload,
            package_name="co.cirvanna.app",
            minimum_version_code=40,
            expected_request_hash="valid-hash",
            signing_certificate_sha256_hex="ab" * 32,
            now_ms=now,
        )


def test_future_dated_play_integrity_payload_is_rejected():
    now = 1_800_000_000_000
    with pytest.raises(CaptureVerificationError):
        validate_play_integrity_payload(
            play_payload(now_ms=now + 60_000, request_hash="valid-hash"),
            package_name="co.cirvanna.app",
            minimum_version_code=40,
            expected_request_hash="valid-hash",
            signing_certificate_sha256_hex="ab" * 32,
            now_ms=now,
        )


def test_identity_receipt_is_not_persisted_until_both_proofs_pass(monkeypatch):
    import asyncio
    from app import dsi_capture_verification as verification

    envelope, image, nonce, _manifest, request_hash = envelope_and_image()
    monkeypatch.setenv("DSI_ANDROID_CAPTURE_PACKAGE_NAME", "co.cirvanna.app")
    monkeypatch.setenv("DSI_ANDROID_CAPTURE_MIN_VERSION_CODE", "40")
    monkeypatch.setenv("DSI_ANDROID_CAPTURE_SIGNING_CERT_SHA256", "ab" * 32)
    monkeypatch.setenv("DSI_ANDROID_CAPTURE_SDK_VERSION", "1.0.0")

    async def key_verified(_envelope, _nonce, _policy):
        return {
            "status": "verified",
            "keySecurityLevel": "trusted_environment",
            "verifiedBootState": "verified",
            "deviceLocked": True,
            "certificateChainVerified": True,
            "attestationChallengeMatched": True,
            "manifestSignatureVerified": True,
            "packageName": "co.cirvanna.app",
            "packageCertificateSha256": "ab" * 32,
        }

    monkeypatch.setattr(verification, "run_android_key_verifier", key_verified)
    payload = play_payload(now_ms=1_800_000_000_000, request_hash=request_hash)
    monkeypatch.setattr(verification, "decode_play_integrity_token", lambda **_kwargs: payload)
    persisted = []

    async def persist(**_kwargs):
        persisted.append(True)
        return {"receipt_id": "dsi_receipt_1234567890"}

    monkeypatch.setattr(verification, "persist_identity_capture_receipt", persist)
    monkeypatch.setattr(verification.time, "time", lambda: 1_800_000_000)
    result = asyncio.run(
        verification.verify_and_persist_capture(
            envelope,
            challenge_nonce_base64url=nonce,
            image_bytes=image,
        )
    )
    assert result["status"] == "verified"
    assert result["absolute_colour_measurement_approved"] is False
    assert persisted == [True]


def test_invalid_play_integrity_claim_never_consumes_identity_challenge(monkeypatch):
    import asyncio
    from app import dsi_capture_verification as verification

    envelope, image, nonce, _manifest, request_hash = envelope_and_image()
    monkeypatch.setenv("DSI_ANDROID_CAPTURE_PACKAGE_NAME", "co.cirvanna.app")
    monkeypatch.setenv("DSI_ANDROID_CAPTURE_MIN_VERSION_CODE", "40")
    monkeypatch.setenv("DSI_ANDROID_CAPTURE_SIGNING_CERT_SHA256", "ab" * 32)
    monkeypatch.setenv("DSI_ANDROID_CAPTURE_SDK_VERSION", "1.0.0")

    async def key_verified(_envelope, _nonce, _policy):
        return {
            "status": "verified",
            "keySecurityLevel": "trusted_environment",
            "verifiedBootState": "verified",
            "deviceLocked": True,
            "certificateChainVerified": True,
            "attestationChallengeMatched": True,
            "manifestSignatureVerified": True,
            "packageName": "co.cirvanna.app",
            "packageCertificateSha256": "ab" * 32,
        }

    monkeypatch.setattr(verification, "run_android_key_verifier", key_verified)
    invalid_payload = play_payload(now_ms=1_800_000_000_000, request_hash="attacker-hash")
    monkeypatch.setattr(verification, "decode_play_integrity_token", lambda **_kwargs: invalid_payload)
    persisted = []

    async def persist(**_kwargs):
        persisted.append(True)
        return {"receipt_id": "should-not-exist"}

    monkeypatch.setattr(verification, "persist_identity_capture_receipt", persist)
    monkeypatch.setattr(verification.time, "time", lambda: 1_800_000_000)
    with pytest.raises(CaptureVerificationError):
        asyncio.run(
            verification.verify_and_persist_capture(
                envelope,
                challenge_nonce_base64url=nonce,
                image_bytes=image,
            )
        )
    assert persisted == []
