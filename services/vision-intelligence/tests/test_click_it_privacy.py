from __future__ import annotations

import hashlib
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import HTTPException
from PIL import Image, ImageDraw

from app import click_it_privacy as privacy


class FakeMediaPipeImage:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeDetector:
    def __init__(self, detections):
        self.detections = detections

    def detect(self, _image):
        return SimpleNamespace(detections=self.detections)


def fake_mediapipe(monkeypatch):
    module = SimpleNamespace(
        Image=FakeMediaPipeImage,
        ImageFormat=SimpleNamespace(SRGB="SRGB"),
    )
    monkeypatch.setitem(sys.modules, "mediapipe", module)


def detection(box, score=0.99):
    return SimpleNamespace(
        categories=[SimpleNamespace(score=score)],
        bounding_box=SimpleNamespace(
            origin_x=box[0], origin_y=box[1], width=box[2], height=box[3]
        ),
    )


def test_face_mask_blurs_two_faces_and_preserves_pixels_outside_face_regions():
    image = Image.new("RGB", (240, 140), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((25, 20, 80, 75), fill="black")
    draw.ellipse((150, 20, 205, 75), fill="black")
    draw.ellipse((42, 38, 50, 46), fill="white")
    draw.ellipse((167, 38, 175, 46), fill="white")
    masked, count = privacy.mask_face_regions(image, [(25, 20, 55, 55), (150, 20, 55, 55)])
    assert count == 2
    assert masked.crop((15, 10, 90, 85)).tobytes() != image.crop((15, 10, 90, 85)).tobytes()
    assert masked.crop((140, 10, 215, 85)).tobytes() != image.crop((140, 10, 215, 85)).tobytes()
    assert masked.getpixel((230, 125)) == image.getpixel((230, 125))


def test_zero_face_detections_preserve_product_only_image(monkeypatch):
    fake_mediapipe(monkeypatch)
    image = Image.new("RGB", (120, 120), (30, 80, 120))
    monkeypatch.setattr(privacy, "_face_detector", lambda: FakeDetector([]))
    masked, count = privacy.anonymize_click_it_image(image)
    assert count == 0
    assert masked.tobytes() == image.tobytes()


@pytest.mark.parametrize("box", [(1, 2, 0, 4), (1, 2, -1, 4), ("1", 2, 3, 4), (1, 2, 3)])
def test_malformed_face_regions_fail_closed(box):
    image = Image.new("RGB", (80, 80), "white")
    with pytest.raises(HTTPException) as error:
        privacy.mask_face_regions(image, [box])
    assert error.value.status_code == 503
    assert error.value.detail["code"] == "CLICK_IT_PRIVACY_INVALID_DETECTION"


def test_detector_is_not_ready_without_pinned_asset(monkeypatch):
    monkeypatch.delenv("CLICK_IT_FACE_DETECTOR_MODEL_PATH", raising=False)
    monkeypatch.delenv("CLICK_IT_FACE_DETECTOR_MODEL_SHA256", raising=False)
    configured, reason = privacy.detector_configuration()
    assert configured is False
    assert reason == "pinned_face_detector_asset_required"


def test_anonymizer_blocks_before_any_image_model_when_detector_is_not_configured(monkeypatch):
    monkeypatch.delenv("CLICK_IT_FACE_DETECTOR_MODEL_PATH", raising=False)
    monkeypatch.delenv("CLICK_IT_FACE_DETECTOR_MODEL_SHA256", raising=False)
    image = Image.new("RGB", (120, 120), "white")
    with pytest.raises(HTTPException) as error:
        privacy.anonymize_click_it_image(image)
    assert error.value.status_code == 503
    assert error.value.detail["code"] == "CLICK_IT_PRIVACY_DETECTOR_NOT_READY"


def test_detector_rejects_asset_with_wrong_checksum(tmp_path, monkeypatch):
    asset = tmp_path / "face_detector.task"
    asset.write_bytes(b"test-model-bytes")
    monkeypatch.setenv("CLICK_IT_FACE_DETECTOR_MODEL_PATH", str(asset))
    monkeypatch.setenv("CLICK_IT_FACE_DETECTOR_MODEL_SHA256", "0" * 64)
    configured, reason = privacy.detector_configuration()
    assert configured is False
    assert reason == "face_detector_asset_sha256_mismatch"


def test_detector_accepts_exact_pinned_asset_checksum(tmp_path, monkeypatch):
    asset = tmp_path / "face_detector.task"
    payload = b"test-model-bytes"
    asset.write_bytes(payload)
    monkeypatch.setenv("CLICK_IT_FACE_DETECTOR_MODEL_PATH", str(asset))
    monkeypatch.setenv("CLICK_IT_FACE_DETECTOR_MODEL_SHA256", hashlib.sha256(payload).hexdigest())
    assert privacy.detector_configuration() == (True, "configured")


def test_uncertain_detector_output_fails_closed(monkeypatch, tmp_path):
    fake_mediapipe(monkeypatch)
    asset = tmp_path / "face_detector.task"
    payload = b"test-model-bytes"
    asset.write_bytes(payload)
    monkeypatch.setenv("CLICK_IT_FACE_DETECTOR_MODEL_PATH", str(asset))
    monkeypatch.setenv("CLICK_IT_FACE_DETECTOR_MODEL_SHA256", hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(privacy, "_face_detector", lambda: FakeDetector(None))
    with pytest.raises(HTTPException) as error:
        privacy.anonymize_click_it_image(Image.new("RGB", (120, 120), "white"))
    assert error.value.status_code == 503
    assert error.value.detail["code"] == "CLICK_IT_PRIVACY_DETECTION_UNCERTAIN"


def test_low_confidence_face_detection_fails_closed(monkeypatch, tmp_path):
    fake_mediapipe(monkeypatch)
    asset = tmp_path / "face_detector.task"
    payload = b"test-model-bytes"
    asset.write_bytes(payload)
    monkeypatch.setenv("CLICK_IT_FACE_DETECTOR_MODEL_PATH", str(asset))
    monkeypatch.setenv("CLICK_IT_FACE_DETECTOR_MODEL_SHA256", hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(privacy, "_face_detector", lambda: FakeDetector([detection((20, 20, 30, 30), 0.2)]))
    with pytest.raises(HTTPException) as error:
        privacy.anonymize_click_it_image(Image.new("RGB", (120, 120), "white"))
    assert error.value.status_code == 503
    assert error.value.detail["code"] == "CLICK_IT_PRIVACY_DETECTION_UNCERTAIN"


def test_detector_runtime_exception_fails_closed(monkeypatch, tmp_path):
    fake_mediapipe(monkeypatch)
    asset = tmp_path / "face_detector.task"
    payload = b"test-model-bytes"
    asset.write_bytes(payload)
    monkeypatch.setenv("CLICK_IT_FACE_DETECTOR_MODEL_PATH", str(asset))
    monkeypatch.setenv("CLICK_IT_FACE_DETECTOR_MODEL_SHA256", hashlib.sha256(payload).hexdigest())

    def fail():
        raise RuntimeError("detector unavailable")

    monkeypatch.setattr(privacy, "_face_detector", fail)
    with pytest.raises(HTTPException) as error:
        privacy.anonymize_click_it_image(Image.new("RGB", (120, 120), "white"))
    assert error.value.status_code == 503
    assert error.value.detail["code"] == "CLICK_IT_PRIVACY_DETECTION_FAILED"
