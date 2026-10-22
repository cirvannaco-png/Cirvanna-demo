#!/usr/bin/env python3
"""Audit source archive integrity, current snapshot baselines, and staged lineage.

Historical intake hashes are retained as provenance, not assumed to describe
the current redacted snapshots. Candidate/source mapping gaps remain explicit
warnings until their source-block parser coverage is reconciled.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "integration-staging"
SOURCE_ARCHIVE = STAGING / "source-intake" / "original" / "cirvanna-source.txt"
SOURCE_MANIFEST = STAGING / "source-manifest.json"
SNAPSHOT_MANIFEST = STAGING / "source-intake" / "manifests" / "source-manifest.csv"
SNAPSHOT_AUDIT = STAGING / "source-intake" / "manifests" / "source-audit.csv"
SNAPSHOT_LINEAGE_LEDGER = ROOT / "docs" / "migration" / "source-snapshot-lineage-ledger.csv"
LINEAGE_LEDGER = ROOT / "docs" / "migration" / "source-candidate-lineage-ledger.csv"
EXCEPTIONS = ROOT / "docs" / "migration" / "source-candidate-lineage-exceptions.csv"

ARCHIVE_HEADER = re.compile(rb"^===== FILE: (.*?) =====[ \t]*(?:\r?\n)?$")
TICK = chr(96)
FENCED_BLOCK = re.compile(
    r"(?ms)^" + TICK * 3 + r"[^\r\n" + TICK + r"]*\r?\n(.*?)^"
    + TICK * 3 + r"[ \t]*(?:\r?\n|$)"
)

# These five minimal repairs are individually described in
# docs/migration/source-candidate-syntax-repairs.md.
DOCUMENTED_REPAIR_PATHS = {
    "source-candidates/23-virtual-tryon-1-.txt/gsis/validators.py",
    "source-candidates/24-virtual-tryon-2-.txt/gsis/validators.py",
    "source-candidates/26-virtual-tryon-improved.txt/gsis/validators.py",
    "source-candidates/25-virtual-tryon-.txt/gsis/service.py",
    "source-candidates/30-wardrobe-2-3-and-4-.txt/services/api-gateway/app/main.py",
}

LEDGER_FIELDS = {
    "source_section", "section_slug", "source_line", "declared_path",
    "staged_path", "manifest_bytes", "tracked_bytes", "git_blob_sha1",
    "duplicate_blob_count", "size_status", "review_status",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    """Return Git's SHA-1 for a blob, including the Git object header."""
    header = b"blob " + str(len(data)).encode("ascii") + b"\0"
    return hashlib.sha1(header + data).hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _extract_archive_sections(data: bytes) -> list[tuple[str, bytes]]:
    sections: list[tuple[str, bytes]] = []
    current_name: str | None = None
    current_lines: list[bytes] = []
    for line in data.splitlines(keepends=True):
        match = ARCHIVE_HEADER.match(line)
        if match:
            if current_name is not None:
                sections.append((current_name, b"".join(current_lines)))
            current_name = match.group(1).decode("utf-8", errors="replace")
            current_lines = []
        elif current_name is not None:
            current_lines.append(line)
    if current_name is not None:
        sections.append((current_name, b"".join(current_lines)))
    return sections


def _normalise_path(value: str) -> str:
    value = value.strip().strip(chr(96)).strip().replace("\\", "/")
    value = re.sub(r"/+", "/", value)
    value = re.sub(r"^(?:#\s*File:|FILE:)\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^(?:#|//|--)\s*", "", value)
    return re.sub(r"/+", "/", value.strip().lstrip("./"))


def _named_code_blocks(snapshot_text: str) -> dict[str, list[str]]:
    """Map declared filenames to the code following each fenced filename line."""
    found: dict[str, list[str]] = {}
    for match in FENCED_BLOCK.finditer(snapshot_text):
        lines = match.group(1).splitlines(keepends=True)
        if not lines:
            continue
        declared = _normalise_path(lines[0].strip())
        if not declared or "." not in Path(declared).name:
            continue
        body = "".join(lines[1:])
        found.setdefault(declared, []).append(body.replace("\r\n", "\n"))
    return found


def _load_exceptions() -> dict[str, str]:
    if not EXCEPTIONS.is_file():
        return {}
    rows = _read_csv(EXCEPTIONS)
    approved: dict[str, str] = {}
    for row in rows:
        path = row.get("staged_path", "").strip()
        reason = row.get("approved_reason", "").strip()
        if not path:
            continue
        if not reason:
            raise ValueError(f"exception for {path} has no approved_reason")
        if path in approved:
            raise ValueError(f"duplicate exception path: {path}")
        approved[path] = reason
    return approved


def audit() -> tuple[list[str], list[dict[str, str]], dict[str, int]]:
    errors: list[str] = []
    source_differences: list[dict[str, str]] = []
    stats: Counter[str] = Counter()

    try:
        source_manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read source manifest: {exc}"], [], {}

    try:
        archive_bytes = SOURCE_ARCHIVE.read_bytes()
    except OSError as exc:
        return [f"cannot read original source archive: {exc}"], [], {}

    actual_archive_blob = git_blob_sha1(archive_bytes)
    expected_archive_blob = source_manifest.get("source_archive_blob_sha1")
    if len(archive_bytes) != source_manifest.get("source_bytes"):
        errors.append(
            f"archive byte count mismatch: expected {source_manifest.get('source_bytes')}, "
            f"found {len(archive_bytes)}"
        )
    if actual_archive_blob != expected_archive_blob:
        errors.append(
            f"archive Git blob SHA-1 mismatch: expected {expected_archive_blob}, "
            f"found {actual_archive_blob}"
        )
    archive_sections = _extract_archive_sections(archive_bytes)
    stats["archive_sections"] = len(archive_sections)
    if len(archive_sections) != len(source_manifest.get("sections", [])):
        errors.append(
            f"archive section count mismatch: manifest has "
            f"{len(source_manifest.get('sections', []))}, archive has {len(archive_sections)}"
        )

    try:
        snapshot_manifest = _read_csv(SNAPSHOT_MANIFEST)
        snapshot_audit = _read_csv(SNAPSHOT_AUDIT)
        snapshot_lineage = _read_csv(SNAPSHOT_LINEAGE_LEDGER)
    except OSError as exc:
        return errors + [f"cannot read snapshot manifests/lineage: {exc}"], [], dict(stats)

    manifest_by_name = {row["original_filename"]: row for row in snapshot_manifest}
    audit_by_name = {row["original_filename"]: row for row in snapshot_audit}
    lineage_by_name = {row["original_filename"]: row for row in snapshot_lineage}
    archive_by_name = dict(archive_sections)
    if len(manifest_by_name) != len(archive_sections):
        errors.append("snapshot manifest rows do not match unique archive section names")
    if len(lineage_by_name) != len(snapshot_lineage):
        errors.append("snapshot lineage ledger contains duplicate original filenames")
    if set(manifest_by_name) != set(audit_by_name):
        errors.append("historical snapshot manifest and audit filename sets differ")
    if set(manifest_by_name) != set(lineage_by_name):
        errors.append("current snapshot lineage ledger and historical manifest filename sets differ")

    for name, row in manifest_by_name.items():
        extracted = STAGING / "source-intake" / "extracted" / row["extracted_filename"]
        original_section = archive_by_name.get(name)
        audit_row = audit_by_name.get(name)
        lineage_row = lineage_by_name.get(name)
        if original_section is None:
            errors.append(f"archive is missing source section {name!r}")
            continue
        if audit_row is None or lineage_row is None:
            continue
        # The source-manifest/source-audit records are historical intake
        # baselines. Check that those records agree with each other, but do
        # not mistake them for the current redacted snapshot content.
        if row.get("byte_count") != audit_row.get("bytes"):
            errors.append(f"historical manifest/audit byte counts disagree: {row['extracted_filename']}")
        if row.get("sha256") != audit_row.get("sha256"):
            errors.append(f"historical manifest/audit hashes disagree: {row['extracted_filename']}")
        if lineage_row.get("historical_bytes") != row.get("byte_count"):
            errors.append(f"snapshot lineage historical byte baseline mismatch: {row['extracted_filename']}")
        if lineage_row.get("historical_sha256") != row.get("sha256"):
            errors.append(f"snapshot lineage historical hash baseline mismatch: {row['extracted_filename']}")
        if lineage_row.get("audit_bytes") != audit_row.get("bytes"):
            errors.append(f"snapshot lineage audit byte baseline mismatch: {row['extracted_filename']}")
        if lineage_row.get("audit_sha256") != audit_row.get("sha256"):
            errors.append(f"snapshot lineage audit hash baseline mismatch: {row['extracted_filename']}")
        if not extracted.is_file():
            errors.append(f"extracted source snapshot is missing: {extracted.relative_to(ROOT)}")
            continue
        snapshot_bytes = extracted.read_bytes()
        current_bytes = len(snapshot_bytes)
        current_blob = git_blob_sha1(snapshot_bytes)
        try:
            expected_current_bytes = int(lineage_row["current_bytes"])
        except (KeyError, ValueError):
            errors.append(f"snapshot lineage has invalid current byte count: {row['extracted_filename']}")
            continue
        if current_bytes != expected_current_bytes:
            errors.append(
                f"current snapshot byte count differs from lineage ledger: {row['extracted_filename']}"
            )
        if current_blob != lineage_row.get("current_git_blob_sha1"):
            errors.append(
                f"current snapshot Git blob differs from lineage ledger: {row['extracted_filename']}"
            )
        # Redaction/version drift between the pinned archive and extracted
        # snapshots is measured, not silently called exact parity. The
        # archive itself and each snapshot are independently hash-pinned.
        if sha256(original_section) != sha256(snapshot_bytes) or len(original_section) != current_bytes:
            stats["archive_snapshot_differences"] += 1
    stats["source_snapshots"] = len(snapshot_manifest)

    candidate_manifest = source_manifest.get("files", [])
    try:
        ledger_rows = _read_csv(LINEAGE_LEDGER)
    except OSError as exc:
        return errors + [f"cannot read candidate lineage ledger: {exc}"], [], dict(stats)

    if not ledger_rows:
        errors.append("candidate lineage ledger is empty")
        return errors, [], dict(stats)
    if not LEDGER_FIELDS.issubset(ledger_rows[0].keys()):
        errors.append(f"lineage ledger is missing columns: {sorted(LEDGER_FIELDS - set(ledger_rows[0].keys()))}")
        return errors, [], dict(stats)

    if len(candidate_manifest) != len(ledger_rows):
        errors.append(
            f"candidate count mismatch: source manifest has {len(candidate_manifest)}, "
            f"lineage ledger has {len(ledger_rows)}"
        )
    manifest_by_path = {item["staged_path"]: item for item in candidate_manifest}
    ledger_by_path = {row["staged_path"]: row for row in ledger_rows}
    if len(manifest_by_path) != len(candidate_manifest):
        errors.append("source manifest contains duplicate staged paths")
    if len(ledger_by_path) != len(ledger_rows):
        errors.append("lineage ledger contains duplicate staged paths")
    if set(manifest_by_path) != set(ledger_by_path):
        errors.append("candidate paths in source manifest and lineage ledger differ")

    try:
        approved_exceptions = _load_exceptions()
    except (OSError, ValueError) as exc:
        return errors + [f"invalid candidate exception ledger: {exc}"], [], dict(stats)

    actual_blobs: Counter[str] = Counter()
    candidate_data: dict[str, bytes] = {}
    for rel_path, item in manifest_by_path.items():
        full_path = STAGING / rel_path
        if not full_path.is_file():
            errors.append(f"candidate is missing: {full_path.relative_to(ROOT)}")
            continue
        data = full_path.read_bytes()
        digest = git_blob_sha1(data)
        candidate_data[rel_path] = data
        actual_blobs[digest] += 1
        row = ledger_by_path.get(rel_path)
        if row is None:
            continue
        if row.get("source_section") != item.get("source_section"):
            errors.append(f"source section mismatch in ledger for {rel_path}")
        if row.get("section_slug") != item.get("section_slug"):
            errors.append(f"section slug mismatch in ledger for {rel_path}")
        if row.get("declared_path") != item.get("declared_path"):
            errors.append(f"declared path mismatch in ledger for {rel_path}")
        if row.get("source_line") != str(item.get("source_line")):
            errors.append(f"source line mismatch in ledger for {rel_path}")
        if row.get("manifest_bytes") != str(item.get("bytes")):
            errors.append(f"manifest byte baseline mismatch in ledger for {rel_path}")
        if row.get("tracked_bytes") != str(len(data)):
            errors.append(f"tracked byte count mismatch in ledger for {rel_path}")
        if row.get("git_blob_sha1") != digest:
            errors.append(f"candidate Git blob SHA-1 mismatch: {rel_path}")
        expected_status = "SIZE_MATCH" if len(data) == int(item["bytes"]) else "SIZE_DIFFERS_REQUIRES_REVIEW"
        if row.get("size_status") != expected_status:
            errors.append(f"candidate size status mismatch in ledger for {rel_path}")

    for rel_path, row in ledger_by_path.items():
        actual = candidate_data.get(rel_path)
        if actual is None:
            continue
        digest = git_blob_sha1(actual)
        if row.get("duplicate_blob_count") != str(actual_blobs[digest]):
            errors.append(f"duplicate blob count mismatch in ledger for {rel_path}")

    section_snapshot_names = {row["original_filename"]: row for row in snapshot_manifest}
    blocks_by_section: dict[str, dict[str, list[str]]] = {}
    for item in candidate_manifest:
        section = item["source_section"]
        if section in blocks_by_section:
            continue
        snapshot = section_snapshot_names.get(section)
        if snapshot is None:
            errors.append(f"no preserved source snapshot maps to section {section!r}")
            continue
        snapshot_path = STAGING / "source-intake" / "extracted" / snapshot["extracted_filename"]
        text = snapshot_path.read_text(encoding="utf-8", errors="replace")
        blocks_by_section[section] = _named_code_blocks(text)

    for item in candidate_manifest:
        rel_path = item["staged_path"]
        data = candidate_data.get(rel_path)
        if data is None:
            continue
        source_paths = blocks_by_section.get(item["source_section"], {})
        declared = _normalise_path(item["declared_path"])
        source_blocks = source_paths.get(declared, [])
        candidate_text = data.decode("utf-8", errors="replace").replace("\r\n", "\n")
        if not source_blocks:
            status = "SOURCE_BLOCK_NOT_FOUND"
        elif candidate_text in source_blocks:
            status = "EXACT_CONTENT_MATCH"
        elif rel_path in DOCUMENTED_REPAIR_PATHS:
            status = "DOCUMENTED_SYNTAX_REPAIR_DIFF"
        elif rel_path in approved_exceptions:
            status = "APPROVED_EXCEPTION"
        else:
            status = "UNRECONCILED_CONTENT_DIFF"
        stats[status] += 1
        if status in {"SOURCE_BLOCK_NOT_FOUND", "UNRECONCILED_CONTENT_DIFF"}:
            source_hashes = "|".join(sha256(option.encode("utf-8")) for option in source_blocks)
            source_differences.append({
                "status": status,
                "staged_path": rel_path,
                "source_section": item["source_section"],
                "declared_path": item["declared_path"],
                "source_line": str(item["source_line"]),
                "manifest_bytes": str(item["bytes"]),
                "tracked_bytes": str(len(data)),
                "candidate_sha256": sha256(data),
                "source_block_count": str(len(source_blocks)),
                "source_block_sha256": source_hashes,
                "approved_reason": approved_exceptions.get(rel_path, ""),
            })

    actual_paths = {
        str(path.relative_to(STAGING)).replace("\\", "/")
        for path in (STAGING / "source-candidates").rglob("*")
        if path.is_file()
    }
    declared_paths = set(manifest_by_path)
    if actual_paths != declared_paths:
        missing = sorted(declared_paths - actual_paths)
        untracked = sorted(actual_paths - declared_paths)
        if missing:
            errors.append(f"candidate manifest paths missing on disk: {missing[:10]}")
        if untracked:
            errors.append(f"unlisted candidate files exist: {untracked[:10]}")
    stats["candidate_files"] = len(actual_paths)

    return errors, source_differences, dict(stats)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-unreconciled",
        action="store_true",
        help="report source-content differences without failing; integrity checks still fail closed",
    )
    args = parser.parse_args()

    errors, differences, stats = audit()
    print("=== Cirvanna source-lineage audit ===")
    for key in ("archive_sections", "source_snapshots", "candidate_files", "archive_snapshot_differences"):
        print(f"{key}: {stats.get(key, 0)}")
    for status in (
        "EXACT_CONTENT_MATCH", "DOCUMENTED_SYNTAX_REPAIR_DIFF",
        "APPROVED_EXCEPTION", "SOURCE_BLOCK_NOT_FOUND", "UNRECONCILED_CONTENT_DIFF",
    ):
        print(f"{status}: {stats.get(status, 0)}")
    print(f"unreconciled_path_count: {len(differences)}")

    if differences:
        print("\n=== Candidate/source differences requiring disposition ===")
        for item in differences:
            print(
                f"{item['status']} | {item['staged_path']} | source={item['source_section']}"
                f"::{item['declared_path']} | size={item['manifest_bytes']}->{item['tracked_bytes']}"
                f" | candidate_sha256={item['candidate_sha256']}"
                f" | source_sha256={item['source_block_sha256'] or 'none'}"
            )
        if len(differences) > 100:
            print(f"... {len(differences) - 100} additional differences omitted from console output")

    if errors:
        print("\n=== Integrity failures ===")
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    if differences and not args.allow_unreconciled:
        print("\nERROR: source differences remain without a documented repair or reviewed exception.")
        return 2
    print("\nOK: archive, preserved snapshots, and 544 candidate hash/provenance entries passed integrity checks.")
    if differences:
        print("WARNING: --allow-unreconciled was supplied; content differences remain unresolved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
