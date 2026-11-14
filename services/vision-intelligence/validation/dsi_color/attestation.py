"""Pinned Ed25519 attestation verification for DSI evaluation evidence."""
from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class AttestationError(ValueError):
    """An evaluation evidence signature is absent, invalid or untrusted."""


def _trusted_pin(environment_name: str) -> str:
    value = os.getenv(environment_name, "").strip().lower()
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise AttestationError(f"{environment_name} must contain a pinned 64-character SHA-256 digest")
    return value


def verify_ed25519_attestation(
    *,
    signed_bytes: bytes,
    signature_path: Path,
    public_key_path: Path,
    trusted_fingerprint_environment: str,
) -> dict[str, str]:
    """Verify detached Ed25519 signature and a separately pinned public-key fingerprint.

    The public key is not trusted merely because a caller supplies it. Its DER
    SubjectPublicKeyInfo SHA-256 must match a fingerprint configured out-of-band
    in the evaluation environment.
    """
    try:
        signature = signature_path.read_bytes()
        pem = public_key_path.read_bytes()
        key = serialization.load_pem_public_key(pem)
    except OSError as exc:
        raise AttestationError("attestation signature or public-key file cannot be read") from exc
    except ValueError as exc:
        raise AttestationError("attestation public key is not valid PEM") from exc

    if not isinstance(key, Ed25519PublicKey):
        raise AttestationError("attestation public key must be Ed25519")
    if len(signature) != 64:
        raise AttestationError("Ed25519 detached signature must be exactly 64 bytes")

    public_der = key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    fingerprint = hashlib.sha256(public_der).hexdigest()
    expected = _trusted_pin(trusted_fingerprint_environment)
    if not hmac.compare_digest(fingerprint, expected):
        raise AttestationError("public-key fingerprint does not match the out-of-band trust pin")

    try:
        key.verify(signature, signed_bytes)
    except InvalidSignature as exc:
        raise AttestationError("Ed25519 signature verification failed") from exc

    return {
        "algorithm": "Ed25519",
        "public_key_sha256": fingerprint,
        "signature_sha256": hashlib.sha256(signature).hexdigest(),
    }
