"""Conflict resolution between local and remote WardrobeObject snapshots."""
from __future__ import annotations

from common.domain import WardrobeObject


def resolve(local: WardrobeObject, remote: WardrobeObject) -> WardrobeObject:
    """Last-write-wins with confidence/regret merging.

    - The newer snapshot wins for scalar fields.
    - Wear counters take the maximum to avoid losing data.
    - Per-dimension confidence takes the maximum.
    - Regret signals union with max strength.
    """
    winner = remote if remote.last_updated > local.last_updated else local
    loser = local if winner is remote else remote

    if winner.total_wears < loser.total_wears:
        winner.total_wears = loser.total_wears
        winner.successful_wears = loser.successful_wears
        winner.usage_history = loser.usage_history

    for field in (
        "geometry_confidence",
        "surface_confidence",
        "category_confidence",
        "context_confidence",
    ):
        setattr(
            winner.confidence_envelope,
            field,
            max(
                getattr(local.confidence_envelope, field),
                getattr(remote.confidence_envelope, field),
            ),
        )

    for k, tv in remote.regret_signals.implicit.items():
        if k in winner.regret_signals.implicit:
            winner.regret_signals.implicit[k].current = max(
                winner.regret_signals.implicit[k].current, tv.current
            )
        else:
            winner.regret_signals.implicit[k] = tv

    return winner
