"""Temporal Learning Layer (TAL) event contract.

TAL stores only explicit, consented observations. This module provides a
deterministic in-memory event ledger for testing; it is not durable storage.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


def _parse_time(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must not be empty")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class TemporalEvent:
    event_id: str
    user_id: str
    feature_key: str
    value: str
    observed_at: str
    source_version: str
    consent_granted: bool
    expires_at: str | None = None

    def __post_init__(self) -> None:
        for name in ("event_id", "user_id", "feature_key", "value", "source_version"):
            field_value = getattr(self, name)
            if not isinstance(field_value, str) or not field_value.strip():
                raise ValueError(f"{name} must not be empty")
        _parse_time(self.observed_at)
        if self.expires_at is not None:
            if _parse_time(self.expires_at) <= _parse_time(self.observed_at):
                raise ValueError("expires_at must be later than observed_at")


@dataclass(frozen=True)
class TemporalState:
    version: int = 0
    events: tuple[TemporalEvent, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.version, int) or self.version < 0:
            raise ValueError("version must be a non-negative integer")
        if not isinstance(self.events, tuple):
            raise ValueError("events must be a tuple")
        ids = [event.event_id for event in self.events]
        if len(ids) != len(set(ids)):
            raise ValueError("event IDs must be unique")


def append_event(state: TemporalState, event: TemporalEvent) -> TemporalState:
    """Append idempotently; duplicate IDs with changed payload are rejected."""
    if not event.consent_granted:
        raise PermissionError("TAL cannot record an observation without explicit consent")
    existing = next((item for item in state.events if item.event_id == event.event_id), None)
    if existing is not None:
        if existing == event:
            return state
        raise ValueError("event_id already exists with different payload")
    events = tuple(sorted(state.events + (event,), key=lambda item: (_parse_time(item.observed_at), item.event_id)))
    return TemporalState(version=state.version + 1, events=events)


def latest_values(state: TemporalState, user_id: str, as_of: str) -> dict[str, str]:
    """Return latest non-expired values as of a timestamp; never mutates state."""
    cutoff = _parse_time(as_of)
    latest: dict[str, TemporalEvent] = {}
    for event in state.events:
        if event.user_id != user_id or _parse_time(event.observed_at) > cutoff:
            continue
        current = latest.get(event.feature_key)
        if current is None or (_parse_time(event.observed_at), event.event_id) > (
            _parse_time(current.observed_at), current.event_id
        ):
            latest[event.feature_key] = event
    # Do not resurrect an older preference when the latest value has expired.
    return {
        key: event.value
        for key, event in sorted(latest.items())
        if event.expires_at is None or cutoff < _parse_time(event.expires_at)
    }
