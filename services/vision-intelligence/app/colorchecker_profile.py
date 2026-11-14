"""Reference patch values for an X-Rite ColorChecker Classic 24, post-November-2014 edition.

Values are copied from the published X-Rite CGATS reference file mirrored by
BabelColor. Reference values are generic averages, not a custom measurement of
the user's individual physical chart. Use a current, non-faded chart and retain
its production-age declaration with every capture.
"""
from __future__ import annotations

import hashlib
import json

PROFILE_ID = "xrite-colorchecker24-after-2014"
PROFILE_VERSION = "1.0.0"
REFERENCE_ILLUMINANT = "ICC D50"
REFERENCE_OBSERVER = "CIE 1931 2 degree"
REFERENCE_CONDITION = "M0"
REFERENCE_SOURCE_URL = (
    "https://babelcolor.com/index_htm_files/ColorChecker24_After_Nov2014.txt"
)
MANUFACTURER_SPECIFICATION_URL = (
    "https://www.xrite.com/en/service-support/new_color_specifications_for_colorchecker_sg_and_classic_charts"
)
SOURCE_ARCHIVE_MD5 = "bc09e5e6a0a5812a26fe693a710522f1"

# CGATS data order is column-major: A1..A4, B1..B4, ... F1..F4.
# Each tuple is (patch label, L*, a*, b*) under the reference condition.
PATCHES = (
    ("A1", 37.54, 14.37, 14.92),
    ("A2", 62.73, 35.83, 56.50),
    ("A3", 28.37, 15.42, -49.80),
    ("A4", 95.19, -1.03, 2.93),
    ("B1", 64.66, 19.27, 17.50),
    ("B2", 39.43, 10.75, -45.17),
    ("B3", 54.38, -39.72, 32.27),
    ("B4", 81.29, -0.57, 0.44),
    ("C1", 49.32, -3.82, -22.54),
    ("C2", 50.57, 48.64, 16.67),
    ("C3", 42.43, 51.05, 28.62),
    ("C4", 66.89, -0.75, -0.06),
    ("D1", 43.46, -12.74, 22.72),
    ("D2", 30.10, 22.54, -20.87),
    ("D3", 81.80, 2.67, 80.41),
    ("D4", 50.76, -0.13, 0.14),
    ("E1", 54.94, 9.61, -24.79),
    ("E2", 71.77, -24.13, 58.19),
    ("E3", 50.63, 51.28, -14.12),
    ("E4", 35.63, -0.46, -0.48),
    ("F1", 70.48, -32.26, -0.37),
    ("F2", 71.51, 18.24, 67.37),
    ("F3", 49.57, -29.71, -28.32),
    ("F4", 20.64, 0.07, -0.46),
)

PROFILE_CANONICAL = {
    "profile_id": PROFILE_ID,
    "profile_version": PROFILE_VERSION,
    "reference_illuminant": REFERENCE_ILLUMINANT,
    "reference_observer": REFERENCE_OBSERVER,
    "reference_condition": REFERENCE_CONDITION,
    "source_url": REFERENCE_SOURCE_URL,
    "source_archive_md5": SOURCE_ARCHIVE_MD5,
    "patches": [list(patch) for patch in PATCHES],
}
PROFILE_SHA256 = hashlib.sha256(
    json.dumps(PROFILE_CANONICAL, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()
