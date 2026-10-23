from __future__ import annotations

from app import main


def test_pose_asset_digest_must_match_reviewed_pin(monkeypatch, tmp_path):
    asset = tmp_path / "pose_landmarker_full.task"
    asset.write_bytes(b"untrusted model bytes")
    monkeypatch.setenv("POSE_LANDMARKER_MODEL_PATH", str(asset))
    monkeypatch.setenv("POSE_LANDMARKER_MODEL_SHA256", "0" * 64)

    configured, reason = main._pose_model_configured()

    assert configured is False
    assert reason == "pose_model_sha256_does_not_match_reviewed_pin"


def test_pose_asset_bytes_must_match_pinned_digest(monkeypatch, tmp_path):
    asset = tmp_path / "pose_landmarker_full.task"
    asset.write_bytes(b"untrusted model bytes")
    monkeypatch.setenv("POSE_LANDMARKER_MODEL_PATH", str(asset))
    monkeypatch.setenv("POSE_LANDMARKER_MODEL_SHA256", main.PINNED_POSE_MODEL_SHA256)

    configured, reason = main._pose_model_configured()

    assert configured is False
    assert reason == "pose_model_sha256_mismatch"
