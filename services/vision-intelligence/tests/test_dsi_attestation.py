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
