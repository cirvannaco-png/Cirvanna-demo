from __future__ import annotations

import hashlib

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from validation.dsi_color.attestation import AttestationError, verify_ed25519_attestation


def _write_keypair(tmp_path):
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_path = tmp_path / "trusted-public.pem"
    public_path.write_bytes(public_pem)
    signature_path = tmp_path / "manifest.sig"
    return private_key, public_path, signature_path, hashlib.sha256(public_der).hexdigest()


def test_ed25519_attestation_requires_signature_and_out_of_band_key_pin(tmp_path, monkeypatch):
    payload = b'{"dataset_version":"held-out-1"}'
    private, public_path, signature_path, fingerprint = _write_keypair(tmp_path)
    signature_path.write_bytes(private.sign(payload))
    monkeypatch.setenv("DSI_EVALUATION_TRUSTED_MANIFEST_PUBLIC_KEY_SHA256", fingerprint)

    result = verify_ed25519_attestation(
        signed_bytes=payload,
        signature_path=signature_path,
        public_key_path=public_path,
        trusted_fingerprint_environment="DSI_EVALUATION_TRUSTED_MANIFEST_PUBLIC_KEY_SHA256",
    )
    assert result["algorithm"] == "Ed25519"
    assert result["public_key_sha256"] == fingerprint


def test_ed25519_rejects_changed_payload(tmp_path, monkeypatch):
    private, public_path, signature_path, fingerprint = _write_keypair(tmp_path)
    signature_path.write_bytes(private.sign(b"approved"))
    monkeypatch.setenv("DSI_EVALUATION_TRUSTED_MANIFEST_PUBLIC_KEY_SHA256", fingerprint)
    with pytest.raises(AttestationError, match="signature verification failed"):
        verify_ed25519_attestation(
            signed_bytes=b"tampered",
            signature_path=signature_path,
            public_key_path=public_path,
            trusted_fingerprint_environment="DSI_EVALUATION_TRUSTED_MANIFEST_PUBLIC_KEY_SHA256",
        )


def test_ed25519_rejects_unpinned_public_key(tmp_path, monkeypatch):
    private, public_path, signature_path, _fingerprint = _write_keypair(tmp_path)
    signature_path.write_bytes(private.sign(b"approved"))
    monkeypatch.setenv("DSI_EVALUATION_TRUSTED_MANIFEST_PUBLIC_KEY_SHA256", "0" * 64)
    with pytest.raises(AttestationError, match="does not match"):
        verify_ed25519_attestation(
            signed_bytes=b"approved",
            signature_path=signature_path,
            public_key_path=public_path,
            trusted_fingerprint_environment="DSI_EVALUATION_TRUSTED_MANIFEST_PUBLIC_KEY_SHA256",
        )


def test_ed25519_rejects_non_ed25519_public_key(tmp_path, monkeypatch):
    from cryptography.hazmat.primitives.asymmetric.ed448 import Ed448PrivateKey

    private = Ed448PrivateKey.generate()
    public_pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_path = tmp_path / "ed448-public.pem"
    public_path.write_bytes(public_pem)
    signature_path = tmp_path / "invalid.sig"
    signature_path.write_bytes(b"x" * 64)
    monkeypatch.setenv("DSI_EVALUATION_TRUSTED_POLICY_PUBLIC_KEY_SHA256", "1" * 64)
    with pytest.raises(AttestationError, match="must be Ed25519"):
        verify_ed25519_attestation(
            signed_bytes=b"approved",
            signature_path=signature_path,
            public_key_path=public_path,
            trusted_fingerprint_environment="DSI_EVALUATION_TRUSTED_POLICY_PUBLIC_KEY_SHA256",
        )


def test_ed25519_rejects_invalid_signature_length(tmp_path, monkeypatch):
    private, public_path, signature_path, fingerprint = _write_keypair(tmp_path)
    signature_path.write_bytes(b"short")
    monkeypatch.setenv("DSI_EVALUATION_TRUSTED_MANIFEST_PUBLIC_KEY_SHA256", fingerprint)
    with pytest.raises(AttestationError, match="exactly 64 bytes"):
        verify_ed25519_attestation(
            signed_bytes=b"approved",
            signature_path=signature_path,
            public_key_path=public_path,
            trusted_fingerprint_environment="DSI_EVALUATION_TRUSTED_MANIFEST_PUBLIC_KEY_SHA256",
        )



def test_cli_verifies_signed_manifest_and_policy_and_writes_review_report(tmp_path, monkeypatch):
    import json
    from validation.dsi_color.cli import main

    def prepare_keypair(name, pin_env, signed_bytes):
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        public_der = public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        public_path = tmp_path / f"{name}-public.pem"
        signature_path = tmp_path / f"{name}.sig"
        public_path.write_bytes(public_pem)
        signature_path.write_bytes(private_key.sign(signed_bytes))
        monkeypatch.setenv(pin_env, hashlib.sha256(public_der).hexdigest())
        return public_path, signature_path

    sample = {
        "record_id": "eval_000000000001",
        "dataset_version": "dsi-cli-heldout-v1",
        "evaluation_split": "held_out_test",
        "subject_ref": "hmac-sha256:" + "a" * 64,
        "capture_ref": "cap_000000000001",
        "capture_session_ref": "ses_000000000001",
        "region": "face_skin",
        "camera_vendor": "ExampleVendor",
        "camera_model": "ExamplePhone",
        "operating_system_family": "Android",
        "lighting_profile": "controlled",
        "skin_model_name": "dsi-colour-preview",
        "skin_model_version": "candidate-1",
        "skin_model_sha256": "b" * 64,
        "segmentation_model_version": "segmenter-1",
        "segmentation_model_sha256": "c" * 64,
        "chart_profile_id": "xrite-colorchecker24-after-2014",
        "chart_profile_sha256": "d" * 64,
        "chart_patch_count_used": 23,
        "chart_fit_p95_delta_e_2000": 1.2,
        "chart_age_months_declared": 12,
        "chart_condition_declared": "good",
        "reference_instrument_model": "Spectro-Reference-1",
        "reference_instrument_calibration_ref": "instrument-calibration:cert-001",
        "reference_measurement_geometry": "45_0",
        "reference_uncertainty_delta_e_2000": 0.5,
        "reference_lab_d50": {"l_star": 50.0, "a_star": 12.0, "b_star": 16.0},
        "prediction_status": "completed",
        "predicted_lab_d50": {"l_star": 50.2, "a_star": 11.9, "b_star": 16.1},
        "failure_code": None,
    }
    samples_raw = (json.dumps(sample, separators=(",", ":")) + "\n").encode()
    manifest_obj = {
        "dataset_version": "dsi-cli-heldout-v1",
        "samples_sha256": hashlib.sha256(samples_raw).hexdigest(),
        "created_at": "2026-11-14T00:00:00Z",
        "held_out_test_data": True,
        "rights_provenance_ref": "rights-registry:cli-test",
        "consent_registry_ref": "consent-registry:cli-test",
        "training_overlap_audit_ref": "training-audit:cli-test",
        "independent_ground_truth_protocol_ref": "spectro-protocol:cli-test",
        "reference_instrument_model": "Spectro-Reference-1",
        "reference_instrument_calibration_ref": "instrument-calibration:cert-001",
        "reference_measurement_standard": "CIE_LAB_D50_2DEG",
        "source_images_included": False,
        "source_videos_included": False,
        "face_templates_included": False,
        "direct_identifiers_included": False,
    }
    manifest_raw = (json.dumps(manifest_obj, separators=(",", ":")) + "\n").encode()
    policy_raw = b'{"policy_id":"pending-cli-test","policy_version":"1"}\n'

    manifest_path = tmp_path / "manifest.json"
    samples_path = tmp_path / "samples.jsonl"
    policy_path = tmp_path / "policy.json"
    manifest_path.write_bytes(manifest_raw)
    samples_path.write_bytes(samples_raw)
    policy_path.write_bytes(policy_raw)

    manifest_public, manifest_sig = prepare_keypair(
        "manifest", "DSI_EVALUATION_TRUSTED_MANIFEST_PUBLIC_KEY_SHA256", manifest_raw
    )
    policy_public, policy_sig = prepare_keypair(
        "policy", "DSI_EVALUATION_TRUSTED_POLICY_PUBLIC_KEY_SHA256", policy_raw
    )
    output_path = tmp_path / "reports" / "report.json"
    result = main([
        "--manifest", str(manifest_path),
        "--manifest-signature", str(manifest_sig),
        "--manifest-public-key", str(manifest_public),
        "--samples", str(samples_path),
        "--policy", str(policy_path),
        "--policy-signature", str(policy_sig),
        "--policy-public-key", str(policy_public),
        "--output", str(output_path),
    ])

    assert result == 3
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["decision"] == "REVIEW_REQUIRED"
    assert report["dataset"]["manifest_signature_verified"] is True
    assert report["dataset"]["policy_signature_verified"] is True
    assert report["attestations"]["manifest"]["algorithm"] == "Ed25519"
    assert report["attestations"]["release_policy"]["algorithm"] == "Ed25519"


def test_cli_rejects_samples_changed_after_manifest_attestation(tmp_path, monkeypatch):
    import json
    from validation.dsi_color.cli import main

    def prepare_keypair(name, pin_env, signed_bytes):
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        public_der = public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        public_path = tmp_path / f"{name}-public.pem"
        signature_path = tmp_path / f"{name}.sig"
        public_path.write_bytes(public_pem)
        signature_path.write_bytes(private_key.sign(signed_bytes))
        monkeypatch.setenv(pin_env, hashlib.sha256(public_der).hexdigest())
        return public_path, signature_path

    sample = {
        "record_id": "eval_000000000002",
        "dataset_version": "dsi-cli-heldout-v1",
        "evaluation_split": "held_out_test",
        "subject_ref": "hmac-sha256:" + "e" * 64,
        "capture_ref": "cap_000000000002",
        "capture_session_ref": "ses_000000000002",
        "region": "face_skin",
        "camera_vendor": "ExampleVendor",
        "camera_model": "ExamplePhone",
        "operating_system_family": "Android",
        "lighting_profile": "controlled",
        "skin_model_name": "dsi-colour-preview",
        "skin_model_version": "candidate-1",
        "skin_model_sha256": "b" * 64,
        "segmentation_model_version": "segmenter-1",
        "segmentation_model_sha256": "c" * 64,
        "chart_profile_id": "xrite-colorchecker24-after-2014",
        "chart_profile_sha256": "d" * 64,
        "chart_patch_count_used": 23,
        "chart_fit_p95_delta_e_2000": 1.2,
        "reference_instrument_model": "Spectro-Reference-1",
        "reference_instrument_calibration_ref": "instrument-calibration:cert-001",
        "reference_measurement_geometry": "45_0",
        "reference_uncertainty_delta_e_2000": 0.5,
        "reference_lab_d50": {"l_star": 50.0, "a_star": 12.0, "b_star": 16.0},
        "prediction_status": "completed",
        "predicted_lab_d50": {"l_star": 50.2, "a_star": 11.9, "b_star": 16.1},
        "failure_code": None,
    }
    signed_samples = (json.dumps(sample, separators=(",", ":")) + "\n").encode()
    manifest_obj = {
        "dataset_version": "dsi-cli-heldout-v1",
        "samples_sha256": hashlib.sha256(signed_samples).hexdigest(),
        "created_at": "2026-11-14T00:00:00Z",
        "held_out_test_data": True,
        "rights_provenance_ref": "rights-registry:cli-test",
        "consent_registry_ref": "consent-registry:cli-test",
        "training_overlap_audit_ref": "training-audit:cli-test",
        "independent_ground_truth_protocol_ref": "spectro-protocol:cli-test",
        "reference_instrument_model": "Spectro-Reference-1",
        "reference_instrument_calibration_ref": "instrument-calibration:cert-001",
        "reference_measurement_standard": "CIE_LAB_D50_2DEG",
        "source_images_included": False,
        "source_videos_included": False,
        "face_templates_included": False,
        "direct_identifiers_included": False,
    }
    manifest_raw = (json.dumps(manifest_obj, separators=(",", ":")) + "\n").encode()
    policy_raw = b'{"policy_id":"pending-cli-test","policy_version":"1"}\n'
    manifest_path = tmp_path / "manifest.json"
    samples_path = tmp_path / "samples.jsonl"
    policy_path = tmp_path / "policy.json"
    manifest_path.write_bytes(manifest_raw)
    samples_path.write_bytes(signed_samples + b" ")
    policy_path.write_bytes(policy_raw)

    manifest_public, manifest_sig = prepare_keypair(
        "manifest", "DSI_EVALUATION_TRUSTED_MANIFEST_PUBLIC_KEY_SHA256", manifest_raw
    )
    policy_public, policy_sig = prepare_keypair(
        "policy", "DSI_EVALUATION_TRUSTED_POLICY_PUBLIC_KEY_SHA256", policy_raw
    )
    result = main([
        "--manifest", str(manifest_path),
        "--manifest-signature", str(manifest_sig),
        "--manifest-public-key", str(manifest_public),
        "--samples", str(samples_path),
        "--policy", str(policy_path),
        "--policy-signature", str(policy_sig),
        "--policy-public-key", str(policy_public),
        "--output", str(tmp_path / "report.json"),
    ])
    assert result == 2
