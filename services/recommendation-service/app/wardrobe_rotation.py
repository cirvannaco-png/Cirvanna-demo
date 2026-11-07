"""Deterministic wardrobe revival and rotation policy.

A recommendation is not a permanent exclusion. Items are ranked for revival
using exposure coverage and wear recency; only explicit user exclusions remain
hard exclusions. The trusted caller persists the returned seen-item state.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except (TypeError, ValueError) as exc:
        raise ValueError("rotation dates must be ISO-8601 calendar dates") from exc


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("wear timestamps must be ISO-8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_rotation_state(
    *,
    items: list[dict[str, Any]],
    local_date: str,
    seen_item_ids: list[str] | tuple[str, ...] = (),
    cycle_started_at: str | None = None,
    cycle_number: int = 1,
    wear_history: list[dict[str, Any]] | None = None,
    surfaced_item_ids: list[str] | tuple[str, ...] = (),
    cycle_days: int = 7,
) -> dict[str, Any]:
    """Return a deterministic revival queue and next cycle state."""
    today = _parse_date(local_date)
    started = _parse_date(cycle_started_at) if cycle_started_at else today
    if today is None or started is None or cycle_days < 1 or cycle_number < 1:
        raise ValueError("invalid wardrobe rotation cycle configuration")
    if started > today:
        raise ValueError("rotation cycle cannot start in the future")

    active_ids = {str(item["item_id"]) for item in items if item.get("status", "active") == "active"}
    seen = {value for value in seen_item_ids if isinstance(value, str) and value in active_ids}
    surfaced = {value for value in surfaced_item_ids if isinstance(value, str) and value in active_ids}
    history: dict[str, tuple[datetime | None, int]] = {}
    for event in wear_history or []:
        if not isinstance(event, dict):
            raise ValueError("wear history entries must be objects")
        item_id = event.get("item_id")
        if not isinstance(item_id, str) or item_id not in active_ids:
            continue
        last_worn = _parse_timestamp(event.get("last_worn_at"))
        count = event.get("wear_count", 0)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("wear_count must be a non-negative integer")
        previous = history.get(item_id)
        floor = datetime.min.replace(tzinfo=timezone.utc)
        if previous is None or (last_worn or floor) > (previous[0] or floor):
            history[item_id] = (last_worn, count)

    def priority(item_id: str) -> tuple[int, float, int, str]:
        last_worn, count = history.get(item_id, (None, 0))
        timestamp = last_worn.timestamp() if last_worn else float("-inf")
        return (0 if item_id not in seen else 1, timestamp, count, item_id)

    queue = sorted(active_ids - seen, key=priority)
    days_elapsed = (today - started).days
    completed = bool(active_ids) and active_ids.issubset(seen | surfaced)
    next_seen = sorted(seen | surfaced)
    next_cycle_number = cycle_number
    next_cycle_started = started.isoformat()
    if completed:
        next_cycle_number += 1
        next_cycle_started = today.isoformat()
        next_seen = []

    return {
        "policy_version": "wardrobe-revival-v1",
        "cycle_number": cycle_number,
        "cycle_started_at": started.isoformat(),
        "cycle_age_days": days_elapsed,
        "cycle_window_days": cycle_days,
        "cycle_overdue": days_elapsed >= cycle_days and not completed,
        "cycle_complete": completed,
        "eligible_item_count": len(active_ids),
        "seen_item_count": len(seen),
        "surfaced_this_request_count": len(surfaced),
        "revival_queue_item_ids": queue,
        "next_state": {
            "cycle_number": next_cycle_number,
            "cycle_started_at": next_cycle_started,
            "seen_item_ids": next_seen,
        },
        "rules": {
            "recent_wear_is_not_exclusion": True,
            "explicit_user_exclusions_only": True,
            "restart_when_all_eligible_items_surfaced": True,
            "overdue_cycle_keeps_unseen_items_prioritized": True,
            "combinations_are_recomposed_each_request": True,
        },
    }
