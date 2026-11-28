"""Shared anthropometry metric contract used by training and held-out evaluation."""
from __future__ import annotations

MEASUREMENTS = (
    "height_mm",
    "chest_circumference_mm",
    "waist_circumference_mm",
    "hip_circumference_mm",
    "inseam_mm",
)
MAX_HELD_OUT_MEASUREMENT_MAPE_PERCENT = 4.0


def measurement_accuracy_gate(test_report: dict) -> dict:
    """Apply the pre-registered per-measurement held-out MAPE ceiling."""
    metrics = test_report.get("measurements")
    if not isinstance(metrics, dict):
        return {
            "threshold_mape_percent": MAX_HELD_OUT_MEASUREMENT_MAPE_PERCENT,
            "passed": False,
            "reason": "held_out_measurement_metrics_missing",
            "per_measurement": {},
        }
    results = {}
    for name in MEASUREMENTS:
        item = metrics.get(name)
        mape = item.get("mape_percent") if isinstance(item, dict) else None
        count = item.get("sample_count") if isinstance(item, dict) else None
        passed = (
            isinstance(mape, (int, float))
            and not isinstance(mape, bool)
            and isinstance(count, int)
            and not isinstance(count, bool)
            and count > 0
            and float(mape) <= MAX_HELD_OUT_MEASUREMENT_MAPE_PERCENT
        )
        results[name] = {"mape_percent": mape, "sample_count": count, "passed": passed}
    return {
        "threshold_mape_percent": MAX_HELD_OUT_MEASUREMENT_MAPE_PERCENT,
        "metric": "per_measurement_held_out_mean_absolute_percentage_error",
        "passed": all(item["passed"] for item in results.values()) and len(results) == len(MEASUREMENTS),
        "per_measurement": results,
    }
