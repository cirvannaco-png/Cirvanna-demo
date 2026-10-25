"""Internal application service wiring the catalog adapter, NPL ledger, and CAL kernel.

This module deliberately exposes Python methods, not public HTTP routes. Callers
must supply a server-authenticated AppearanceContext and server-trusted evidence.
"""
from __future__ import annotations

from datetime import datetime
from typing import Mapping, Protocol, Sequence

from catacaci import DecisionSignal
from npl import NegativePreference

from appearance_intelligence import (
    AppearanceContext,
    CatalogSnapshot,
    EvaluationStatus,
    LookCompositionResult,
    SpecialistId,
    SpecialistResult,
    build_look as compose_catalog_look,
    run_specialist as evaluate_catalog_specialist,
)
from appearance_intelligence.registry import describe_specialist
from catalog_client import CatalogClient, CatalogUnavailable
from npl_client import NPLClient, NPLUnavailable


class CatalogReader(Protocol):
    def fetch_active_catalog(self, *, now: datetime | None = None) -> CatalogSnapshot: ...


class PreferenceReader(Protocol):
    def fetch_preferences(self, user_id: str) -> tuple[NegativePreference, ...]: ...


class AppearanceOrchestrator:
    """Coordinate canonical read services without owning product or preference data."""

    def __init__(
        self,
        catalog: CatalogReader | None = None,
        preferences: PreferenceReader | None = None,
    ) -> None:
        self._catalog = CatalogClient.from_env() if catalog is None else catalog
        self._preferences = NPLClient.from_env() if preferences is None else preferences

    @staticmethod
    def _review_specialist(specialist: SpecialistId, notice: str) -> SpecialistResult:
        return SpecialistResult(specialist, EvaluationStatus.NEEDS_REVIEW, (), (notice,))

    @staticmethod
    def _review_look(notice: str) -> LookCompositionResult:
        return LookCompositionResult(EvaluationStatus.NEEDS_REVIEW, {}, (), (), (notice,))

    def run_specialist(
        self,
        context: AppearanceContext,
        specialist: SpecialistId | str,
        trusted_signals_by_product: Mapping[str, Sequence[DecisionSignal]] | None = None,
        *,
        now: datetime | None = None,
    ) -> SpecialistResult:
        descriptor = describe_specialist(specialist)
        if descriptor.specialist is SpecialistId.SKIN:
            # Skin analysis has no validated inference provider. It does not need
            # catalog or NPL calls and must not be disguised as catalog matching.
            return SpecialistResult(
                SpecialistId.SKIN,
                EvaluationStatus.PROVIDER_UNAVAILABLE,
                (),
                ("DermalSight has no approved model artifact and signed validation report; no skin analysis was fabricated.",),
            )
        try:
            snapshot = self._catalog.fetch_active_catalog(now=now)
        except CatalogUnavailable:
            return self._review_specialist(
                descriptor.specialist,
                "Canonical catalog data is unavailable or invalid; no candidates are displayable.",
            )
        try:
            preferences = self._preferences.fetch_preferences(context.user_id)
        except NPLUnavailable:
            return self._review_specialist(
                descriptor.specialist,
                "Canonical NPL state is unavailable; no candidates are displayable.",
            )
        return evaluate_catalog_specialist(
            context,
            descriptor.specialist,
            snapshot,
            preferences,
            trusted_signals_by_product,
            now=now,
        )

    def compose_look(
        self,
        context: AppearanceContext,
        trusted_signals_by_product: Mapping[str, Sequence[DecisionSignal]] | None = None,
        *,
        bundle_signals: Sequence[DecisionSignal] = (),
        now: datetime | None = None,
        max_candidates_per_component: int = 3,
        max_options: int = 12,
    ) -> LookCompositionResult:
        """Compose Look + Makeup after successful canonical catalog and NPL reads."""
        try:
            snapshot = self._catalog.fetch_active_catalog(now=now)
        except CatalogUnavailable:
            return self._review_look(
                "Canonical catalog data is unavailable or invalid; no look options are displayable."
            )
        try:
            preferences = self._preferences.fetch_preferences(context.user_id)
        except NPLUnavailable:
            return self._review_look(
                "Canonical NPL state is unavailable; no look options are displayable."
            )
        return compose_catalog_look(
            context,
            snapshot,
            preferences,
            trusted_signals_by_product,
            bundle_signals=bundle_signals,
            now=now,
            max_candidates_per_component=max_candidates_per_component,
            max_options=max_options,
        )
