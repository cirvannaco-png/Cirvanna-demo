#!/usr/bin/env python3
"""Build or verify a file-level inventory of preserved Cirvanna source snippets."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "integration-staging" / "source-manifest.json"
OUTPUT = ROOT / "docs" / "migration" / "code-snippet-inventory.json"

CANONICAL_DESTINATIONS = {
    '01-cdic-.txt': "packages/identity-intelligence/cdic/candidates/typescript-v7/",
    '03-cdic-v5.txt': "packages/identity-intelligence/cdic/ (legacy candidate; not canonical)",
    '04-cdic.txt': "packages/identity-intelligence/cdic/ (legacy candidate; not canonical)",
    '05-cfrp-v6.txt': "tests/cfrp_candidate/ (candidate only)",
    '06-eepl-v2.0.txt': "packages/identity-intelligence/eepl/",
    '07-eepl.txt': "packages/identity-intelligence/eepl/",
    '09-fci-.txt': "packages/fit-intelligence/fci/",
    '10-fci-v2.0.txt': "packages/fit-intelligence/fci/",
    '11-fit-confidence-index-repository-.txt': "packages/fit-intelligence/fci/",
    '12-npl-v2.txt': "packages/preferences/npl/",
    '13-tari-improved-.txt': "Xari assistant capability; no canonical runtime promotion",
    '14-we-have-now.txt': "Xari assistant capability; no canonical runtime promotion",
    '15-xyra.txt': "Xari assistant capability; no canonical runtime promotion",
    '17-txt': "Xari assistant capability; no canonical runtime promotion",
    '18-cirvanna-skeleton-.txt': "source reference only",
    '19-cultural-identity-module-.txt': "packages/identity-intelligence/cultural_identity/",
    '20-identity-decision-engine-.txt': "packages/identity-intelligence/catacaci/ (CAL remains sole display authority)",
    '22-skin-analysis-repo-.txt': "services/dermalsight/ (inference disabled until validated)",
    '23-virtual-tryon-1-.txt': "services/virtual-try-on/ and services/virtual-twin/ (renderer not validated)",
    '24-virtual-tryon-2-.txt': "services/virtual-try-on/ and services/virtual-twin/ (renderer not validated)",
    '25-virtual-tryon-.txt': "services/virtual-try-on/ and services/virtual-twin/ (renderer not validated)",
    '26-virtual-tryon-improved.txt': "services/virtual-try-on/ and services/virtual-twin/ (renderer not validated)",
    '30-wardrobe-2-3-and-4-.txt': "wardrobe capability; canonical schema/persistence not established",
    '31-wardrobe-part-1.txt': "wardrobe capability; canonical schema/persistence not established"
}


def git_blob_sha1(data: bytes) -> str:
    header = b"blob " + str(len(data)).encode("ascii") + bytes([0])
    return hashlib.sha1(header + data).hexdigest()


def build_inventory(root: Path = ROOT) -> dict[str, Any]:
    manifest = json.loads((root / "integration-staging" / "source-manifest.json").read_text(encoding="utf-8"))
    sections = []
    for section in manifest["sections"]:
        count = section["extracted_files"]
        sections.append({
            "source_section": section["source_section"],
            "section_slug": section["section_slug"],
            "extracted_files": count,
            "canonical_destination": CANONICAL_DESTINATIONS.get(section["section_slug"], "no canonical owner assigned; preserve pending review"),
            "status": "preserved_candidate" if count else "source_section_without_extracted_code",
        })

    snippets = []
    hash_counts: dict[str, int] = {}
    size_mismatches = 0
    for entry in manifest["files"]:
        relative_path = Path("integration-staging") / entry["staged_path"]
        file_path = root / relative_path
        if not file_path.is_file():
            raise ValueError(f"missing staged source snippet: {relative_path.as_posix()}")
        data = file_path.read_bytes()
        actual_size = len(data)
        matches = actual_size == entry["bytes"]
        size_mismatches += int(not matches)
        blob_sha = git_blob_sha1(data)
        hash_counts[blob_sha] = hash_counts.get(blob_sha, 0) + 1
        disposition = (
            "reference_for_hardened_offline_metrics_reimplementation"
            if entry["section_slug"] == "09-fci-.txt" and entry["declared_path"] == "src/fci/metrics.py"
            else "pending_file_level_review"
        )
        snippets.append({
            "section_slug": entry["section_slug"],
            "source_line": entry["source_line"],
            "declared_path": entry["declared_path"],
            "staged_path": relative_path.as_posix(),
            "manifest_bytes": entry["bytes"],
            "tracked_bytes": actual_size,
            "size_matches_manifest": matches,
            "git_blob_sha1": blob_sha,
            "duplicate_in_section": bool(entry.get("duplicate_in_section", False)),
            "status": "preserved_candidate_not_runtime",
            "disposition": disposition,
        })
    duplicate_groups = [
        {"git_blob_sha1": sha, "count": count}
        for sha, count in sorted(hash_counts.items()) if count > 1
    ]
    duplicate_hashes = {group["git_blob_sha1"] for group in duplicate_groups}
    for snippet in snippets:
        snippet["duplicate_group"] = snippet["git_blob_sha1"] if snippet["git_blob_sha1"] in duplicate_hashes else None
    if len(snippets) != sum(s["extracted_files"] for s in manifest["sections"]):
        raise ValueError("section counts do not reconcile with snippet entries")

    return {
        "schema_version": 1,
        "generated_from": "integration-staging/source-manifest.json",
        "source_archive_blob_sha1": manifest["source_archive_blob_sha1"],
        "source_bytes": manifest["source_bytes"],
        "summary": {
            "source_sections": len(manifest["sections"]),
            "extracted_snippets": len(manifest["files"]),
            "present_in_main": len(snippets),
            "missing": 0,
            "runtime_promoted_from_archive": 0,
            "unique_git_blob_count": len(hash_counts),
            "duplicate_group_count": len(duplicate_groups),
            "cross_path_duplicate_snippet_count": sum(1 for s in snippets if s["duplicate_group"] is not None),
            "tracked_size_differs_from_manifest_count": size_mismatches,
        },
        "sections": sections,
        "duplicate_groups": duplicate_groups,
        "snippets": snippets,
    }


def render_inventory(inventory: dict[str, Any]) -> str:
    return json.dumps(inventory, sort_keys=True, separators=(",", ":")) + chr(10)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the committed inventory is stale")
    args = parser.parse_args()
    try:
        rendered = render_inventory(build_inventory())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.check:
        try:
            committed = OUTPUT.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"ERROR: cannot read inventory: {exc}", file=sys.stderr)
            return 1
        if committed != rendered:
            print("ERROR: code-snippet inventory is stale; regenerate it with python scripts/build_code_snippet_inventory.py", file=sys.stderr)
            return 1
        print("OK: code-snippet inventory matches all staged files and content hashes.")
        return 0
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
