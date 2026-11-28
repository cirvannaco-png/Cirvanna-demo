from __future__ import annotations

from tools.model_training.twin_geometry.train_shape_model import (
    MEASUREMENTS,
    measurement_accuracy_gate,
)


def valid_report(mape: float = 3.5):
    return {
        "measurements": {
            name: {"mape_percent": mape, "sample_count": 40}
            for name in MEASUREMENTS
        }
    }


def test_held_out_measurement_gate_passes_only_when_every_measure_is_within_four_percent():
    result = measurement_accuracy_gate(valid_report(3.99))
    assert result["threshold_mape_percent"] == 4.0
    assert result["passed"] is True
    assert set(result["per_measurement"]) == set(MEASUREMENTS)


def test_held_out_measurement_gate_fails_when_one_measure_exceeds_four_percent():
    report = valid_report(2.0)
    report["measurements"]["waist_circumference_mm"]["mape_percent"] = 4.01
    result = measurement_accuracy_gate(report)
    assert result["passed"] is False
    assert result["per_measurement"]["waist_circumference_mm"]["passed"] is False


def test_held_out_measurement_gate_fails_for_missing_or_empty_measurement_evidence():
    report = valid_report(2.0)
    report["measurements"].pop("inseam_mm")
    assert measurement_accuracy_gate(report)["passed"] is False

    report = valid_report(2.0)
    report["measurements"]["height_mm"]["sample_count"] = 0
    assert measurement_accuracy_gate(report)["passed"] is False
