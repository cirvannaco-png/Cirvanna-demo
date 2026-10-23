"""Persistence boundary for durable NPL event handling.

An adapter must implement these operations transactionally. In particular,
rejection_event_id uniqueness must be enforced by the durable store, not merely
by the pure in-memory policy kernel.
"""
from __future__ import annotations

from typing import Protocol

from .core import NegativePreference

class NPLLedger(Protocol):
    def list_preferences_for_user(self, user_id: str) -> tuple[NegativePreference, ...]:
        """Return only the requested user's current preferences."""
        ...

    def record_rejection_atomically(
        self,
        *,
        user_id: str,
        preference_id: str,
        rejection_event_id: str,
    ) -> NegativePreference:
        """Persist a rejection once under a unique (user_id, rejection_event_id) key."""
        ...

    def retract_preference_atomically(
        self,
        *,
        user_id: str,
        preference_id: str,
        correction_event_id: str,
    ) -> NegativePreference:
        """Persist an auditable, user-scoped correction; reject cross-user access."""
        ...
