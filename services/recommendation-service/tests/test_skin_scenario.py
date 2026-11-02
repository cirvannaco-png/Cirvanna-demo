import pytest

from app.skin_scenario import build_skin_scenario_preview


def payload():
    return {
        "request_id": "skin-1",
        "product_id": "product-1",
        "consent": True,
        "forecast_horizon_weeks": 6,
        "humidity_scenario": "high",
        "sleep_scenario": "disrupted",
        "cycle_context": None,
        "cycle_context_consent": False,
    }


def test_scenario_is_not_misrepresented_as_a_forecast():
    result = build_skin_scenario_preview(payload())
    assert result["status"] == "not_validated"
    assert result["forecast"] is None
    assert result["scenario_definition_only"] is True
    assert result["scenario_inputs"]["humidity"] == "high"
    assert result["scenario_inputs"]["sleep"] == "disrupted"


def test_cycle_context_requires_separate_consent():
    request = payload()
    request["cycle_context"] = "luteal"
    with pytest.raises(ValueError, match="separate explicit consent"):
        build_skin_scenario_preview(request)


def test_cycle_context_can_be_included_only_when_user_reports_and_consents():
    request = payload()
    request["cycle_context"] = "luteal"
    request["cycle_context_consent"] = True
    result = build_skin_scenario_preview(request)
    assert result["scenario_inputs"]["cycle_context"] == "luteal"
    assert result["scenario_inputs"]["cycle_context_included"] is True
    assert result["forecast"] is None


def test_no_hormonal_status_is_inferred():
    result = build_skin_scenario_preview(payload())
    assert "cycle_context" not in result["scenario_inputs"] or result["scenario_inputs"]["cycle_context"] is None
    assert "hormonal imbalance" not in str(result).casefold()
