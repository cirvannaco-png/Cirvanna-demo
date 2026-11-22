#!/usr/bin/env python3
"""Export the Vision service's exact live retrieval candidate set to a private snapshot.

Run inside the Vision Intelligence service environment. This module deliberately
imports _live_offers() lazily so its validation and file-writing helpers are
unit-testable without importing the web service or requiring credentials.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_MARKETPLACE_CANDIDATES = 1000


def _load_rights_validator():
    """Load the canonical benchmark rights validator from a full source checkout."""
    repository_root = Path(__file__).resolve().parents[3]
    validator_path = (repository_root / "tools" / "model_evaluation" / "fashion_retrieval"
                      / "data_rights.py")
    if not validator_path.is_file():
        raise RuntimeError("run the snapshot exporter from a complete Cirvanna repository checkout")
    spec = importlib.util.spec_from_file_location("cirvanna_benchmark_data_rights", validator_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load the canonical data-rights validator")
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    return validator


def load_rights_manifest(path: str | Path) -> dict[str, Any]:
    return _load_rights_validator().load_and_validate_data_rights_manifest(path)


def rights_manifest_summary(rights: dict[str, Any]) -> dict[str, str]:
    return _load_rights_validator().rights_manifest_summary(rights)


def snapshot_records(offers: Any) -> list[dict[str, str]]:
    """Project live offers onto the exact fields consumed by the retrieval runner."""
    if not isinstance(offers, list):
        raise ValueError("live offer result must be a list")
    if len(offers) > MAX_MARKETPLACE_CANDIDATES:
        raise ValueError("live offer list exceeds the Vision service candidate bound")
    records: list[dict[str, str]] = []
    seen_variant_ids: set[str] = set()
    for index, offer in enumerate(offers, start=1):
        if not isinstance(offer, dict):
            raise ValueError(f"live offer row {index} is not an object")
        variant_id = offer.get("variant_id")
        search_text = offer.get("search_text")
        # Do not trim or reconstruct the identifiers/text: exact service output
        # must survive this export. Whitespace-only IDs are rejected.
        if (not isinstance(variant_id, str) or not variant_id or not variant_id.strip()
                or variant_id != variant_id.strip()):
            raise ValueError(f"live offer row {index} has an invalid variant_id")
        if variant_id in seen_variant_ids:
            raise ValueError(f"duplicate variant_id in live offer set: {variant_id!r}")
        if (not isinstance(search_text, str) or not search_text.strip()
                or len(search_text) > 2000):
            raise ValueError(f"live offer row {index} has invalid search_text")
        seen_variant_ids.add(variant_id)
        records.append({"variant_id": variant_id, "search_text": search_text})
    if not records:
        raise ValueError("Vision returned no eligible active catalogue offers")
    return records


def jsonl_bytes(records: list[dict[str, str]]) -> bytes:
    return "".join(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n"
                   for row in records).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _atomic_private_write(path: Path, payload: bytes, *, overwrite: bool) -> None:
    """Write a 0600 file atomically; never follow an output symlink."""
    if path.is_symlink():
        raise ValueError(f"refusing to write through a symbolic link: {path.name}")
    if path.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite existing snapshot file: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary_name = tempfile.mkstemp(prefix=".cirvanna-snapshot-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if overwrite:
            os.replace(temporary, path)
        else:
            # A hard-link publish provides exclusive creation if another process
            # races this exporter after the preflight check.
            os.link(temporary, path)
            temporary.unlink()
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_snapshot(
    output_path: str | Path,
    records: list[dict[str, str]],
    manifest: dict[str, Any],
    *,
    overwrite: bool = False,
) -> tuple[Path, Path, str]:
    output = Path(output_path).expanduser().absolute()
    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    if output == manifest_path:
        raise ValueError("snapshot and manifest paths must be different")
    if not overwrite and (output.exists() or manifest_path.exists()):
        raise FileExistsError("snapshot or manifest already exists; pass --overwrite to replace both")
    payload = jsonl_bytes(records)
    digest = sha256_bytes(payload)
    final_manifest = {
        **manifest,
        "snapshot_file_sha256": digest,
        "snapshot_record_count": len(records),
        "exported_fields": ["variant_id", "search_text"],
        "commerce_offer_order_preserved": True,
        "product_image_urls_exported": False,
        "raw_offer_payloads_exported": False,
        "credentials_or_service_urls_exported": False,
        "point_in_time_consistency": "sequential Commerce/Catalog service read; not a cross-service transaction",
        "privacy_note": "Keep the snapshot and manifest in an access-controlled evaluation workspace; do not commit either file to Git.",
    }
    manifest_payload = (json.dumps(final_manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _atomic_private_write(output, payload, overwrite=overwrite)
    try:
        _atomic_private_write(manifest_path, manifest_payload, overwrite=overwrite)
    except Exception:
        # Avoid leaving a data snapshot without its provenance sidecar.
        try:
            output.unlink()
        except OSError:
            pass
        raise
    return output, manifest_path, digest


async def export_current_snapshot(
    output_path: str | Path,
    *,
    rights_summary: dict[str, str],
    overwrite: bool = False,
) -> dict[str, Any]:
    # Import only inside the trusted Vision service environment. _live_offers()
    # applies Commerce eligibility and active Catalog product checks, preserving
    # the same order and _offer_description() text used by _rank_offers().
    from app.main import (
        MAX_MARKETPLACE_CANDIDATES as SERVICE_CANDIDATE_LIMIT,
        MODEL_ID,
        PINNED_MODEL_REVISION,
        SERVICE,
        _live_offers,
    )

    offers, truncated = await _live_offers()
    records = snapshot_records(offers)
    if len(records) > SERVICE_CANDIDATE_LIMIT:
        raise ValueError("export exceeds the configured Vision service candidate bound")
    manifest = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "Vision Intelligence _live_offers() using live Commerce offers and active Catalog products",
        "source_service": SERVICE,
        "baseline_model_id": MODEL_ID,
        "baseline_model_revision": PINNED_MODEL_REVISION,
        "candidate_limit": SERVICE_CANDIDATE_LIMIT,
        "commerce_offer_list_was_truncated_at_service_limit": bool(truncated),
        "candidate_order": "original Commerce offer order after active Catalog product filtering",
        "search_text_source": "exact _offer_description() output produced by Vision Intelligence _live_offers()",
        "search_text_max_chars_in_source": 2000,
        "data_rights": rights_summary,
    }
    output, manifest_path, digest = write_snapshot(
        output_path, records, manifest, overwrite=overwrite
    )
    return {
        "status": "exported",
        "candidate_count": len(records),
        "truncated": bool(truncated),
        "snapshot_sha256": digest,
        "output_file": str(output),
        "manifest_file": str(manifest_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True,
                        help="Destination on a restricted local volume or mounted evaluation workspace")
    parser.add_argument("--rights-manifest", required=True,
                        help="Private approved data-rights manifest; validation occurs before service access")
    parser.add_argument("--overwrite", action="store_true",
                        help="Atomically replace an existing snapshot and manifest")
    args = parser.parse_args()
    try:
        # The exporter is an isolated-checkout operator tool, not a production
        # endpoint. Load the same canonical validator used by the benchmark
        # runner; fail closed if the checkout does not contain that validator.
        rights = load_rights_manifest(args.rights_manifest)
        rights_summary = rights_manifest_summary(rights)
        result = asyncio.run(export_current_snapshot(
            args.output, rights_summary=rights_summary, overwrite=args.overwrite
        ))
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        # Avoid emitting upstream URLs, response bodies, or credential-adjacent details.
        print(f"catalog snapshot export failed: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
