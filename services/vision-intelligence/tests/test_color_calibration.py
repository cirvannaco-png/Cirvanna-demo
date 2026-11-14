from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from app.color_calibration import (
    ColorCalibrationError,
    PROFILE_ID,
    PROFILE_SHA256,
    build_skin_colour_preview,
    delta_e_2000,
    lab_d50_to_xyz,
    xyz_d50_to_lab,
)
from app.colorchecker_profile import PATCHES


def test_ciede2000_matches_published_reference_pair():
    # Sharma, Wu and Dalal (2005), supplementary test data, pair 1.
    actual = delta_e_2000((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485))
    assert actual == pytest.approx(2.0425, abs=1e-4)


def test_lab_xyz_d50_round_trip():
    expected = np.asarray([
        [37.54, 14.37, 14.92],
        [62.73, 35.83, 56.50],
        [20.64, 0.07, -0.46],
    ])
    actual = xyz_d50_to_lab(lab_d50_to_xyz(expected))
    assert actual == pytest.approx(expected, abs=1e-8)


def _lab_to_srgb(lab: tuple[float, float, float]) -> tuple[int, int, int]:
    xyz = lab_d50_to_xyz(np.asarray(lab, dtype=np.float64))
    srgb_to_xyz_d50 = np.asarray([
        [0.4360747, 0.3850649, 0.1430804],
        [0.2225045, 0.7168786, 0.0606169],
        [0.0139322, 0.0971045, 0.7141733],
    ])
    linear = xyz @ np.linalg.inv(srgb_to_xyz_d50).T
    linear = np.clip(linear, 0.0, 1.0)
    encoded = np.where(
        linear <= 0.0031308,
        12.92 * linear,
        1.055 * np.power(linear, 1.0 / 2.4) - 0.055,
    )
    return tuple(int(round(float(value) * 255.0)) for value in encoded)


def _synthetic_capture():
    width, height = 1000, 700
    rgb = np.full((height, width, 3), 118, dtype=np.uint8)
    categories = np.zeros((height, width), dtype=np.uint8)

    # Place the 6x4 chart on a flat, fronto-parallel plane.
    for col, letter in enumerate("ABCDEF"):
        for row in range(4):
            label = f"{letter}{row + 1}"
            patch = next(item for item in PATCHES if item[0] == label)
            colour = _lab_to_srgb((patch[1], patch[2], patch[3]))
            x0, x1 = 100 + col * 100, 100 + (col + 1) * 100
            y0, y1 = 50 + row * 100, 50 + (row + 1) * 100
            rgb[y0:y1, x0:x1] = colour

    # Synthetic face-skin and body-skin regions let the test exercise the
    # full colour transform without any real-person media.
    rgb[100:260, 750:920] = (145, 94, 72)
    categories[100:260, 750:920] = 3
    rgb[320:640, 730:960] = (160, 118, 95)
    categories[320:640, 730:960] = 2

    return Image.fromarray(rgb, mode="RGB"), categories


def test_colorchecker_fit_returns_unvalidated_face_and_body_colour_previews():
    image, categories = _synthetic_capture()
    try:
        result = build_skin_colour_preview(
            image,
            categories,
            patch_grid_corners=[[100, 50], [700, 50], [700, 450], [100, 450]],
            chart_age_months_declared=12,
        )
    finally:
        image.close()

    assert result["status"] == "colorchecker_fit_candidate_unvalidated"
    assert result["calibration_state"] == "experimental_unvalidated"
    assert result["profile"]["profile_id"] == PROFILE_ID
    assert result["profile"]["profile_sha256"] == PROFILE_SHA256
    assert result["chart_patch_count"] == 24
    assert len(result["patch_leave_one_out_delta_e_2000"]) == 24
    assert result["requested_region"] == "both"
    assert set(result["chart_fit_leave_one_out_delta_e_2000"]) == {
        "mean", "median", "p95", "maximum"
    }
    assert result["skin_regions"]["face_skin"]["lab_estimate_d50"] is not None
    assert result["skin_regions"]["body_skin"]["lab_estimate_d50"] is not None
    assert result["absolute_colour_measurement_approved"] is False
    assert result["independent_model_validation_passed"] is False
    assert result["image_persisted"] is False
    assert result["profile_persisted"] is False
    assert result["global_training_performed"] is False
    assert result["discovery_restricted"] is False


def test_colorchecker_fit_rejects_wrong_patch_grid_aspect_ratio():
    image, categories = _synthetic_capture()
    try:
        with pytest.raises(ColorCalibrationError, match="aspect ratio"):
            build_skin_colour_preview(
                image,
                categories,
                patch_grid_corners=[[100, 50], [500, 50], [500, 450], [100, 450]],
                chart_age_months_declared=12,
            )
    finally:
        image.close()



def test_colorchecker_fit_reports_old_chart_without_hard_rejection():
    image, categories = _synthetic_capture()
    try:
        result = build_skin_colour_preview(
            image,
            categories,
            patch_grid_corners=[[100, 50], [700, 50], [700, 450], [100, 450]],
            chart_age_months_declared=60,
        )
    finally:
        image.close()
    assert result["chart_age_months_declared_by_user"] == 60
    assert result["chart_integrity_status"] == "not_independently_inspected"


def test_colorchecker_fit_keeps_worn_chart_preview_advisory_not_denied():
    image, categories = _synthetic_capture()
    try:
        result = build_skin_colour_preview(
            image,
            categories,
            patch_grid_corners=[[100, 50], [700, 50], [700, 450], [100, 450]],
            chart_age_months_declared=None,
            chart_condition_declared="worn",
        )
    finally:
        image.close()
    assert result["status"] == "colorchecker_fit_candidate_unvalidated"
    assert result["chart_age_months_declared_by_user"] is None
    assert result["chart_integrity_status"] == "user_declared_worn_review_recommended"
    assert result["discovery_restricted"] is False


def test_colorchecker_profile_has_exact_24_post_2014_patches():
    labels = [item[0] for item in PATCHES]
    assert len(PATCHES) == 24
    assert labels == [
        f"{letter}{row}"
        for letter in "ABCDEF"
        for row in range(1, 5)
    ]



def test_colorchecker_fit_rejects_clipped_chart_patch():
    image, categories = _synthetic_capture()
    pixels = np.asarray(image).copy()
    pixels[50:150, 100:200] = 255
    clipped = Image.fromarray(pixels, mode="RGB")
    try:
        with pytest.raises(ColorCalibrationError, match="excessive clipped pixels"):
            build_skin_colour_preview(
                clipped,
                categories,
                patch_grid_corners=[[100, 50], [700, 50], [700, 450], [100, 450]],
            )
    finally:
        clipped.close()
        image.close()


def test_patch_grid_corner_order_is_strict():
    image, categories = _synthetic_capture()
    try:
        with pytest.raises(ColorCalibrationError, match="ordered TL,TR,BR,BL"):
            build_skin_colour_preview(
                image,
                categories,
                patch_grid_corners=[[100, 50], [100, 450], [700, 450], [700, 50]],
            )
    finally:
        image.close()



@pytest.mark.parametrize(
    ("requested_region", "expected_face", "expected_body"),
    [
        ("face_skin", True, False),
        ("body_skin", False, True),
    ],
)
def test_colorchecker_preview_only_summarizes_the_user_selected_region(
    requested_region, expected_face, expected_body
):
    image, categories = _synthetic_capture()
    try:
        result = build_skin_colour_preview(
            image,
            categories,
            patch_grid_corners=[[100, 50], [700, 50], [700, 450], [100, 450]],
            requested_region=requested_region,
        )
    finally:
        image.close()
    assert (result["skin_regions"]["face_skin"] is not None) is expected_face
    assert (result["skin_regions"]["body_skin"] is not None) is expected_body
    assert result["requested_region"] == requested_region
