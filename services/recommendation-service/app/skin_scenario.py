"""Opt-in cosmetic skin-scenario contract; forecasting stays disabled without validation."""
from __future__ import annotations

from typing import Any


def build_skin_scenario_preview(payload: dict[str, Any]) -> dict[str, Any]:
    """Describe a user-selected scenario without inventing a skin forecast.

    A production forecast requires an independently validated longitudinal
    provider and signed evaluation evidence. Neither is present in this service.
    """
    if payload.get("consent") is not True:
        raise ValueError("explicit consent is required")
    cycle_context = payload.get("cycle_context")
    cycle_consent = payload.get("cycle_context_consent") is True
    if cycle_context is not None and not cycle_consent:
        raise ValueError("cycle context requires separate explicit consent")

    scenario = {
        "humidity": payload["humidity_scenario"],
        "sleep": payload["sleep_scenario"],
        "cycle_context": cycle_context if cycle_consent else None,
        "cycle_context_included": bool(cycle_context and cycle_consent),
    }
    return {
        "schema_version": "1.0",
        "contract_version": "1.0.0",
        "request_id": payload["request_id"],
        "product_id": payload["product_id"],
        "forecast_horizon_weeks": payload["forecast_horizon_weeks"],
        "status": "not_validated",
        "reason_code": "SKIN_FORECAST_PROVIDER_NOT_VALIDATED",
        "forecast": None,
        "scenario_inputs": scenario,
        "scenario_definition_only": True,
        "required_before_forecast": [
            "Product-specific ingredient, concentration, formulation and use-instruction provenance.",
            "Longitudinal product-response observations with defined outcome measures and follow-up intervals.",
            "Evaluation across skin attributes, climate, lighting/capture conditions and relevant user subgroups.",
            "Calibration, uncertainty intervals, missing-data handling and independent model review.",
            "Explicit consent, data minimisation, correction/export/deletion controls and privacy review.",
        ],
        "explanation": (
            "The selected conditions are recorded only in this response as a scenario definition. "
            "No future skin behaviour has been predicted because a validated longitudinal forecast "
            "provider is not configured."
        ),
        "limits": [
            "Cosmetic information only; not a diagnosis or clinical recommendation.",
            "Cycle context is optional, user-reported and separately consented. It is not inferred from a face, image, name, location or shopping history.",
            "This contract does not diagnose hormonal imbalance or predict endocrine status.",
            "No medication or treatment changes are recommended.",
            "Scenario parameters are not stored by this service.",
        ],
    }
