from __future__ import annotations

from tools.pnelly_evaluation import evaluate_pnelly_cases as runner


def test_role_report_keeps_everyday_elevated_and_explore_separate(monkeypatch):
    calls = []
    def fake_evaluate(records, k=3):
        calls.append((records[0]["context"]["role"] if records else "empty", k, len(records)))
        return {"status": "descriptive_only", "case_count": len(records)}
    monkeypatch.setattr(runner, "evaluate", fake_evaluate)
    records = [
        {"case_id": "1", "context": {"role": "everyday"}},
        {"case_id": "2", "context": {"role": "elevated"}},
        {"case_id": "3", "context": {"role": "explore"}},
    ]
    result = runner.evaluate_by_role(records, k=2)
    assert set(result["by_role"]) == {"everyday", "elevated", "explore"}
    assert result["overall"]["case_count"] == 3
    assert all(row[1] == 2 for row in calls)
