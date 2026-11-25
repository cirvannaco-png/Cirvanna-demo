"""Yoti AVS orchestration over the durable identity-owned lifecycle store."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from .core import build_threshold_attestation, sign_threshold_attestation
from .store import AgeEvidenceConflict, AgeEvidenceStore
from .yoti import YotiAVSClient


class AgeEvidenceService:
    def __init__(
        self, *, store: AgeEvidenceStore, yoti: YotiAVSClient,
        signing_secret: str, redirect_url: str, cancel_url: str,
        privacy_policy_url: str, terms_url: str,
    ):
        if len(signing_secret.encode("utf-8")) < 32:
            raise ValueError("age evidence signing secret must be at least 32 bytes")
        self.store, self.yoti, self.signing_secret = store, yoti, signing_secret
        self.redirect_url, self.cancel_url = redirect_url, cancel_url
        self.privacy_policy_url, self.terms_url = privacy_policy_url, terms_url

    def start(
        self, *, subject_id: str, request_id: str, purpose: str,
        policy_id: str, policy_version: str, threshold: int,
    ) -> dict:
        reference = secrets.token_urlsafe(36)
        session_id = self.store.create_session(
            subject_id=subject_id, request_id=request_id, purpose=purpose,
            policy_id=policy_id, policy_version=policy_version,
            threshold=threshold, provider_reference=reference,
        )
        try:
            provider = self.yoti.create_over_session(
                threshold=threshold, reference_id=reference,
                redirect_url=self.redirect_url, cancel_url=self.cancel_url,
                privacy_policy_url=self.privacy_policy_url,
                terms_url=self.terms_url, ttl_seconds=900,
            )
            expires_at = datetime.fromisoformat(provider.expires_at.replace("Z", "+00:00"))
            self.store.attach_provider_session(
                session_id, provider.session_id, expires_at,
            )
        except Exception:
            self.store.fail_session(session_id)
            raise
        return {
            "session_id": session_id,
            "provider": "yoti",
            "state": "pending",
            "verification_url": provider.user_view_url,
            "expires_at": provider.expires_at,
        }

    def poll(self, session_id: str) -> dict:
        row = self.store.get_session(session_id)
        if row is None:
            raise ValueError("age verification session not found")
        if row["state"] in {"revoked", "expired", "failed"}:
            return {"session_id": session_id, "state": row["state"]}
        if row["state"] in {"verified", "denied"}:
            persisted = self.store.get_attestation(session_id)
            if persisted is None:
                raise ValueError("terminal age attestation is missing or revoked")
            return {"session_id": session_id, "state": row["state"], "attestation": persisted["attestation"], "signature": persisted["signature"], "attestation_issued": True}
        provider_session_id = str(uuid.UUID(str(row["provider_session_id"])))
        result = self.yoti.get_threshold_result(
            session_id=provider_session_id,
            expected_reference_id=row["provider_reference"],
            threshold=row["threshold"],
        )
        now = datetime.now(timezone.utc)
        if result.state in {"PENDING", "IN_PROGRESS", "PROCESSING"}:
            return {"session_id": session_id, "state": "pending"}
        if result.state in {"EXPIRED", "CANCELLED", "ERROR"}:
            terminal = "expired" if result.state == "EXPIRED" else "failed"
            self.store.mark_provider_terminal(
                session_id, provider_session_id, terminal, now=datetime.now(timezone.utc),
            )
            return {"session_id": session_id, "state": terminal}
        self.store.record_provider_result(
            session_id, state=result.state, threshold_met=result.threshold_met,
            evidence_id=result.evidence_id, provider_session_id=provider_session_id,
            now=now,
        )
        row = self.store.get_session(session_id)
        if result.state not in {"COMPLETE", "FAIL"} or not result.evidence_id:
            raise ValueError("provider result is not terminal verified evidence")
        issued = now
        provider_expiry = row["expires_at"]
        if provider_expiry.tzinfo is None:
            provider_expiry = provider_expiry.replace(tzinfo=timezone.utc)
        expires = min(issued + timedelta(minutes=5), provider_expiry)
        payload = build_threshold_attestation(
            subject_id=row["subject_id"], request_id=row["request_id"],
            purpose=row["purpose"], policy_id=row["policy_id"],
            policy_version=row["policy_version"], threshold=row["threshold"],
            threshold_met=(result.state == "COMPLETE"), provider_session_id=provider_session_id,
            provider_evidence_id=result.evidence_id, issued_at=issued,
            expires_at=expires,
        )
        signature = sign_threshold_attestation(payload, self.signing_secret)
        try:
            self.store.issue_attestation(
                session_id=session_id, jti=payload["jti"], signature=signature,
                attestation_payload=payload, issued_at=issued, expires_at=expires, now=issued,
            )
        except AgeEvidenceConflict:
            # A concurrent poll may have committed the single allowed attestation first.
            persisted = self.store.get_attestation(session_id)
            if persisted is None:
                raise
            payload, signature = persisted["attestation"], persisted["signature"]
        return {
            "session_id": session_id, "state": ("verified" if result.state == "COMPLETE" else "denied"),
            "attestation": payload, "signature": signature,
        }

    def close(self) -> None:
        self.yoti.close()
        self.store.engine.dispose()

    def revoke(self, session_id: str) -> bool:
        return self.store.revoke_session(session_id)
