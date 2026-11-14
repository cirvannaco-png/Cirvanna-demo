"""Experimental, stateless ColorChecker calibration and skin-colour preview.

A successful chart fit is not proof of camera accuracy. The result remains
unvalidated until independently evaluated across devices, lighting, chart age,
skin-tone groups and held-out captures.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np
from PIL import Image

from app.colorchecker_profile import (
    PATCHES,
    PROFILE_ID,
    PROFILE_SHA256,
    PROFILE_VERSION,
    REFERENCE_CONDITION,
    REFERENCE_ILLUMINANT,
    REFERENCE_OBSERVER,
    REFERENCE_SOURCE_URL,
)

WARP_WIDTH = 600
WARP_HEIGHT = 400
MAX_REGION_SAMPLES = 100_000
D50_WHITE = np.asarray([0.96422, 1.0, 0.82521], dtype=np.float64)
LAB_DELTA = 6.0 / 29.0


class ColorCalibrationError(ValueError):
    """The chart capture cannot support a valid calibration candidate."""


def srgb_to_linear(values: np.ndarray) -> np.ndarray:
    """Convert normalized IEC 61966-2-1 sRGB values to linear-light RGB."""
    values = np.asarray(values, dtype=np.float64)
    return np.where(
        values <= 0.04045,
        values / 12.92,
        ((values + 0.055) / 1.055) ** 2.4,
    )


def lab_d50_to_xyz(lab: np.ndarray) -> np.ndarray:
    """Convert CIELAB D50 values to XYZ D50."""
    values = np.asarray(lab, dtype=np.float64)
    if values.shape[-1] != 3 or not np.isfinite(values).all():
        raise ValueError("CIELAB input must be finite with final dimension 3")
    lightness, a_star, b_star = np.moveaxis(values, -1, 0)
    fy = (lightness + 16.0) / 116.0
    fx = fy + a_star / 500.0
    fz = fy - b_star / 200.0

    def inverse_f(component: np.ndarray) -> np.ndarray:
        return np.where(
            component > LAB_DELTA,
            component**3,
            3.0 * LAB_DELTA**2 * (component - 4.0 / 29.0),
        )

    x = D50_WHITE[0] * inverse_f(fx)
    y = D50_WHITE[1] * inverse_f(fy)
    z = D50_WHITE[2] * inverse_f(fz)
    return np.stack([x, y, z], axis=-1)


def xyz_d50_to_lab(xyz: np.ndarray) -> np.ndarray:
    """Convert XYZ D50 to CIELAB D50."""
    values = np.asarray(xyz, dtype=np.float64)
    if values.shape[-1] != 3 or not np.isfinite(values).all():
        raise ValueError("XYZ input must be finite with final dimension 3")
    normalized = values / D50_WHITE
    f = np.where(
        normalized > LAB_DELTA**3,
        np.cbrt(normalized),
        normalized / (3.0 * LAB_DELTA**2) + 4.0 / 29.0,
    )
    fx, fy, fz = np.moveaxis(f, -1, 0)
    lightness = 116.0 * fy - 16.0
    a_star = 500.0 * (fx - fy)
    b_star = 200.0 * (fy - fz)
    return np.stack([lightness, a_star, b_star], axis=-1)


def delta_e_2000(lab1: Sequence[float], lab2: Sequence[float]) -> float:
    """CIEDE2000 colour difference for two CIELAB D50 samples."""
    l1, a1, b1 = (float(value) for value in lab1)
    l2, a2, b2 = (float(value) for value in lab2)

    c1 = math.hypot(a1, b1)
    c2 = math.hypot(a2, b2)
    c_bar = (c1 + c2) / 2.0
    c_bar7 = c_bar**7
    g = 0.5 * (1.0 - math.sqrt(c_bar7 / (c_bar7 + 25.0**7)))

    a1p = (1.0 + g) * a1
    a2p = (1.0 + g) * a2
    c1p = math.hypot(a1p, b1)
    c2p = math.hypot(a2p, b2)

    def hue_degrees(a_value: float, b_value: float) -> float:
        if a_value == 0.0 and b_value == 0.0:
            return 0.0
        return math.degrees(math.atan2(b_value, a_value)) % 360.0

    h1p = hue_degrees(a1p, b1)
    h2p = hue_degrees(a2p, b2)
    delta_l = l2 - l1
    delta_c = c2p - c1p

    if c1p * c2p == 0.0:
        delta_h_angle = 0.0
    else:
        raw = h2p - h1p
        if abs(raw) <= 180.0:
            delta_h_angle = raw
        elif raw > 180.0:
            delta_h_angle = raw - 360.0
        else:
            delta_h_angle = raw + 360.0

    delta_h = 2.0 * math.sqrt(c1p * c2p) * math.sin(math.radians(delta_h_angle / 2.0))
    l_bar_p = (l1 + l2) / 2.0
    c_bar_p = (c1p + c2p) / 2.0

    if c1p * c2p == 0.0:
        h_bar_p = h1p + h2p
    else:
        raw_h = abs(h1p - h2p)
        if raw_h <= 180.0:
            h_bar_p = (h1p + h2p) / 2.0
        elif (h1p + h2p) < 360.0:
            h_bar_p = (h1p + h2p + 360.0) / 2.0
        else:
            h_bar_p = (h1p + h2p - 360.0) / 2.0

    t = (
        1.0
        - 0.17 * math.cos(math.radians(h_bar_p - 30.0))
        + 0.24 * math.cos(math.radians(2.0 * h_bar_p))
        + 0.32 * math.cos(math.radians(3.0 * h_bar_p + 6.0))
        - 0.20 * math.cos(math.radians(4.0 * h_bar_p - 63.0))
    )
    l_shift = l_bar_p - 50.0
    s_l = 1.0 + (0.015 * l_shift**2) / math.sqrt(20.0 + l_shift**2)
    s_c = 1.0 + 0.045 * c_bar_p
    s_h = 1.0 + 0.015 * c_bar_p * t

    delta_theta = 30.0 * math.exp(-(((h_bar_p - 275.0) / 25.0) ** 2))
    c_bar_p7 = c_bar_p**7
    r_c = 2.0 * math.sqrt(c_bar_p7 / (c_bar_p7 + 25.0**7))
    r_t = -r_c * math.sin(math.radians(2.0 * delta_theta))

    term_l = delta_l / s_l
    term_c = delta_c / s_c
    term_h = delta_h / s_h
    result = term_l**2 + term_c**2 + term_h**2 + r_t * term_c * term_h
    return math.sqrt(max(result, 0.0))


def _polygon_area(points: np.ndarray) -> float:
    x = points[:, 0]
    y = points[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def _validate_corners(
    points: Sequence[Sequence[float]],
    image_size: tuple[int, int],
) -> np.ndarray:
    width, height = image_size
    corners = np.asarray(points, dtype=np.float64)
    if corners.shape != (4, 2) or not np.isfinite(corners).all():
        raise ColorCalibrationError("patch-grid corners must be four finite [x,y] points")
    if (
        (corners[:, 0] < 0).any()
        or (corners[:, 0] >= width).any()
        or (corners[:, 1] < 0).any()
        or (corners[:, 1] >= height).any()
    ):
        raise ColorCalibrationError("patch-grid corner lies outside the image")

    edges = np.roll(corners, -1, axis=0) - corners
    next_edges = np.roll(edges, -1, axis=0)
    crosses = edges[:, 0] * next_edges[:, 1] - edges[:, 1] * next_edges[:, 0]
    if not (crosses > 1e-6).all():
        raise ColorCalibrationError("patch-grid corners must be ordered TL,TR,BR,BL and form a convex quadrilateral")
    if _polygon_area(corners) < 8_000.0:
        raise ColorCalibrationError("patch grid is too small for reliable patch sampling")

    top = np.linalg.norm(corners[1] - corners[0])
    bottom = np.linalg.norm(corners[2] - corners[3])
    left = np.linalg.norm(corners[3] - corners[0])
    right = np.linalg.norm(corners[2] - corners[1])
    average_width = (top + bottom) / 2.0
    average_height = (left + right) / 2.0
    if average_width < 120.0 or average_height < 80.0:
        raise ColorCalibrationError("patch grid must be at least 120 by 80 pixels")
    aspect = average_width / average_height
    if not 1.275 <= aspect <= 1.725:
        raise ColorCalibrationError("patch-grid aspect ratio is inconsistent with a 6-by-4 chart")
    return corners


def _homography(source: np.ndarray, destination: np.ndarray) -> np.ndarray:
    rows: list[list[float]] = []
    values: list[float] = []
    for (x, y), (u, v) in zip(source, destination, strict=True):
        rows.append([x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y])
        values.append(float(u))
        rows.append([0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y])
        values.append(float(v))
    try:
        solution = np.linalg.solve(np.asarray(rows), np.asarray(values))
    except np.linalg.LinAlgError as exc:
        raise ColorCalibrationError("patch-grid perspective is geometrically degenerate") from exc
    return np.asarray([
        [solution[0], solution[1], solution[2]],
        [solution[3], solution[4], solution[5]],
        [solution[6], solution[7], 1.0],
    ])


def _warp_patch_grid(image: Image.Image, corners: np.ndarray) -> Image.Image:
    destination = np.asarray([
        [0.0, 0.0],
        [WARP_WIDTH - 1.0, 0.0],
        [WARP_WIDTH - 1.0, WARP_HEIGHT - 1.0],
        [0.0, WARP_HEIGHT - 1.0],
    ])
    forward = _homography(corners, destination)
    inverse = np.linalg.inv(forward)
    inverse /= inverse[2, 2]
    coefficients = (
        float(inverse[0, 0]), float(inverse[0, 1]), float(inverse[0, 2]),
        float(inverse[1, 0]), float(inverse[1, 1]), float(inverse[1, 2]),
        float(inverse[2, 0]), float(inverse[2, 1]),
    )
    return image.transform(
        (WARP_WIDTH, WARP_HEIGHT),
        Image.Transform.PERSPECTIVE,
        coefficients,
        resample=Image.Resampling.BICUBIC,
    )


def _sample_chart_patches(warped: Image.Image) -> tuple[np.ndarray, list[dict[str, object]]]:
    pixels = np.asarray(warped, dtype=np.uint8)
    cell_width = WARP_WIDTH // 6
    cell_height = WARP_HEIGHT // 4
    samples: list[list[float]] = []
    diagnostics: list[dict[str, object]] = []

    patch_index = 0
    for col, letter in enumerate("ABCDEF"):
        for row in range(4):
            x0 = col * cell_width + int(cell_width * 0.20)
            x1 = (col + 1) * cell_width - int(cell_width * 0.20)
            y0 = row * cell_height + int(cell_height * 0.20)
            y1 = (row + 1) * cell_height - int(cell_height * 0.20)
            region = pixels[y0:y1, x0:x1].reshape(-1, 3)
            if region.shape[0] < 100:
                raise ColorCalibrationError("insufficient pixels sampled from a chart patch")
            median = np.median(region.astype(np.float64), axis=0)
            clipped = float(np.mean(np.any((region <= 2) | (region >= 253), axis=1)))
            label = f"{letter}{row + 1}"
            if clipped > 0.05:
                raise ColorCalibrationError(
                    f"patch {label} has excessive clipped pixels; reduce glare or exposure clipping"
                )
            samples.append(median.tolist())
            diagnostics.append({
                "patch": label,
                "sample_pixels": int(region.shape[0]),
                "median_srgb": [round(float(v), 3) for v in median],
                "clipped_pixel_fraction": round(clipped, 5),
                "within_patch_rgb_std": [
                    round(float(value), 3) for value in np.std(region.astype(np.float64), axis=0)
                ],
            })
            patch_index += 1

    return np.asarray(samples, dtype=np.float64), diagnostics


def _fit_affine_rgb_to_xyz(
    observed_rgb: np.ndarray,
    reference_xyz: np.ndarray,
) -> np.ndarray:
    linear = srgb_to_linear(observed_rgb / 255.0)
    design = np.column_stack([linear, np.ones(len(linear), dtype=np.float64)])
    coefficients, _residuals, rank, _singular = np.linalg.lstsq(design, reference_xyz, rcond=None)
    if rank != 4 or not np.isfinite(coefficients).all():
        raise ColorCalibrationError("chart colours do not support a stable 3-by-3 camera transform")
    condition = float(np.linalg.cond(design))
    if not math.isfinite(condition) or condition > 1e5:
        raise ColorCalibrationError("chart colour fit is numerically ill-conditioned")
    return coefficients


def _leave_one_out_errors(
    observed_rgb: np.ndarray,
    reference_lab: np.ndarray,
    reference_xyz: np.ndarray,
) -> np.ndarray:
    errors: list[float] = []
    all_indices = np.arange(len(observed_rgb))
    for excluded in all_indices:
        keep = all_indices != excluded
        coefficients = _fit_affine_rgb_to_xyz(observed_rgb[keep], reference_xyz[keep])
        linear = srgb_to_linear(observed_rgb[excluded] / 255.0)
        predicted_xyz = np.append(linear, 1.0) @ coefficients
        predicted_lab = xyz_d50_to_lab(predicted_xyz)
        errors.append(delta_e_2000(reference_lab[excluded], predicted_lab))
    return np.asarray(errors, dtype=np.float64)


def _erode_mask(mask: np.ndarray) -> np.ndarray:
    source = np.asarray(mask, dtype=bool)
    if source.ndim != 2 or min(source.shape) < 3:
        raise ColorCalibrationError("skin mask has invalid dimensions")
    eroded = np.zeros_like(source)
    eroded[1:-1, 1:-1] = (
        source[1:-1, 1:-1]
        & source[:-2, :-2] & source[:-2, 1:-1] & source[:-2, 2:]
        & source[1:-1, :-2] & source[1:-1, 2:]
        & source[2:, :-2] & source[2:, 1:-1] & source[2:, 2:]
    )
    return eroded


def _summarize_skin_region(
    rgb_image: np.ndarray,
    category_mask: np.ndarray,
    category_index: int,
    coefficients: np.ndarray,
) -> dict[str, object]:
    mask = _erode_mask(category_mask == category_index)
    coordinates = np.flatnonzero(mask)
    if len(coordinates) < 500:
        return {
            "status": "region_not_detected_or_insufficient_pixels",
            "pixel_count": int(len(coordinates)),
            "lab_estimate": None,
        }

    if len(coordinates) > MAX_REGION_SAMPLES:
        selection = np.linspace(0, len(coordinates) - 1, MAX_REGION_SAMPLES, dtype=np.int64)
        coordinates = coordinates[selection]
    rgb = rgb_image.reshape(-1, 3)[coordinates].astype(np.float64)
    linear = srgb_to_linear(rgb / 255.0)
    design = np.column_stack([linear, np.ones(len(linear), dtype=np.float64)])
    xyz = design @ coefficients
    valid = np.isfinite(xyz).all(axis=1) & (xyz > 0.0).all(axis=1)
    valid_fraction = float(valid.mean())
    if valid_fraction < 0.90:
        return {
            "status": "invalid_colour_transform_for_region",
            "pixel_count": int(len(mask.nonzero()[0])),
            "sampled_pixel_count": int(len(coordinates)),
            "valid_colour_fraction": round(valid_fraction, 5),
            "lab_estimate": None,
        }

    lab = xyz_d50_to_lab(xyz[valid])
    median = np.median(lab, axis=0)
    lower = np.percentile(lab, 10, axis=0)
    upper = np.percentile(lab, 90, axis=0)
    mad = np.median(np.abs(lab - median), axis=0)
    return {
        "status": "experimental_region_estimate",
        "pixel_count": int(len(mask.nonzero()[0])),
        "sampled_pixel_count": int(len(coordinates)),
        "valid_colour_fraction": round(valid_fraction, 5),
        "lab_estimate_d50": {
            "L_star": round(float(median[0]), 3),
            "a_star": round(float(median[1]), 3),
            "b_star": round(float(median[2]), 3),
        },
        "within_region_p10_p90": {
            "L_star": [round(float(lower[0]), 3), round(float(upper[0]), 3)],
            "a_star": [round(float(lower[1]), 3), round(float(upper[1]), 3)],
            "b_star": [round(float(lower[2]), 3), round(float(upper[2]), 3)],
        },
        "within_region_median_absolute_deviation": {
            "L_star": round(float(mad[0]), 3),
            "a_star": round(float(mad[1]), 3),
            "b_star": round(float(mad[2]), 3),
        },
        "note": "within-region colour dispersion is not instrument uncertainty",
    }


def build_skin_colour_preview(
    image: Image.Image,
    category_mask: np.ndarray,
    *,
    patch_grid_corners: Sequence[Sequence[float]],
    chart_age_months_declared: int | None = None,
    chart_condition_declared: str = "unknown",
    requested_region: str = "both",
) -> dict[str, object]:
    """Fit a ColorChecker transform and emit provisional face/body skin Lab summaries."""
    if chart_age_months_declared is not None and chart_age_months_declared < 0:
        raise ColorCalibrationError("chart age cannot be negative")
    if chart_condition_declared not in {"good", "worn", "unknown"}:
        raise ColorCalibrationError("chart condition must be good, worn or unknown")
    if requested_region not in {"face_skin", "body_skin", "both"}:
        raise ColorCalibrationError("requested region must be face_skin, body_skin or both")
    if image.mode != "RGB":
        image = image.convert("RGB")
    corners = _validate_corners(patch_grid_corners, image.size)
    warped = _warp_patch_grid(image, corners)
    try:
        observed_rgb, patch_diagnostics = _sample_chart_patches(warped)
    finally:
        warped.close()

    reference_lab = np.asarray([[patch[1], patch[2], patch[3]] for patch in PATCHES], dtype=np.float64)
    reference_xyz = lab_d50_to_xyz(reference_lab)
    coefficients = _fit_affine_rgb_to_xyz(observed_rgb, reference_xyz)
    loo = _leave_one_out_errors(observed_rgb, reference_lab, reference_xyz)

    rgb_image = np.asarray(image, dtype=np.uint8)
    categories = np.asarray(category_mask)
    if categories.shape != (image.height, image.width) or categories.ndim != 2:
        raise ColorCalibrationError("skin segmentation mask dimensions do not match capture")
    if not np.issubdtype(categories.dtype, np.integer):
        raise ColorCalibrationError("skin segmentation mask must be an integer label map")

    face = (
        _summarize_skin_region(rgb_image, categories, 3, coefficients)
        if requested_region in {"face_skin", "both"} else None
    )
    body = (
        _summarize_skin_region(rgb_image, categories, 2, coefficients)
        if requested_region in {"body_skin", "both"} else None
    )
    return {
        "status": "colorchecker_fit_candidate_unvalidated",
        "calibration_state": "experimental_unvalidated",
        "profile": {
            "profile_id": PROFILE_ID,
            "profile_version": PROFILE_VERSION,
            "profile_sha256": PROFILE_SHA256,
            "reference_illuminant": REFERENCE_ILLUMINANT,
            "reference_observer": REFERENCE_OBSERVER,
            "measurement_condition": REFERENCE_CONDITION,
            "reference_source": REFERENCE_SOURCE_URL,
        },
        "chart_age_months_declared_by_user": chart_age_months_declared,
        "chart_condition_declared_by_user": chart_condition_declared,
        "chart_integrity_status": (
            "user_declared_worn_review_recommended"
            if chart_condition_declared == "worn"
            else "not_independently_inspected"
        ),
        "chart_patch_count": int(len(PATCHES)),
        "chart_fit_leave_one_out_delta_e_2000": {
            "mean": round(float(np.mean(loo)), 4),
            "median": round(float(np.median(loo)), 4),
            "p95": round(float(np.percentile(loo, 95)), 4),
            "maximum": round(float(np.max(loo)), 4),
        },
        "patch_leave_one_out_delta_e_2000": [
            {"patch": PATCHES[index][0], "delta_e_2000": round(float(error), 4)}
            for index, error in enumerate(loo)
        ],
        "patch_diagnostics": patch_diagnostics,
        "requested_region": requested_region,
        "skin_regions": {
            "face_skin": face,
            "body_skin": body,
        },
        "absolute_colour_measurement_approved": False,
        "independent_model_validation_passed": False,
        "clinical_diagnosis_performed": False,
        "image_persisted": False,
        "profile_persisted": False,
        "global_training_performed": False,
        "discovery_restricted": False,
        "limitations": [
            "generic average chart references are not a custom spectrophotometer measurement of the user's individual target",
            "the generic reference describes an average chart; custom spectrophotometer measurements of the user's individual target are preferable for highest accuracy",
            "the camera RGB transform and chart fit have not been independently validated across devices, lighting, exposure, skin-tone groups or capture pipelines",
            "chart age and condition are user-declared and cannot prove patch integrity; storage, fading, scratches and contamination can change patch reflectance",
            "JPEG/sRGB processing may include computational photography, local tone mapping or undocumented colour transformations",
            "face-skin/body-skin segmentation is coarse and does not identify individual neck, chest, arm, hand or leg regions",
            "reported within-region colour dispersion is not a calibrated measurement uncertainty interval",
            "do not use this preview for product shade selection, clinical advice or persistent personalization until release validation passes",
        ],
    }
