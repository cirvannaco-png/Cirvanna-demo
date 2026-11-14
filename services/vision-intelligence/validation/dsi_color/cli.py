"""Command-line entry point for offline DSI colour validation."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from .attestation import AttestationError, verify_ed25519_attestation
from .evaluator import EvaluationInputError, evaluate_dataset
from .schema import ColorValidationSample, EvaluationManifest, ReleasePolicy


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise EvaluationInputError(f"{label} file cannot be read") from exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_json(raw: bytes, model_type, label: str):
    try:
        return model_type.model_validate_json(raw)
    except ValidationError as exc:
        raise EvaluationInputError(f"{label} file does not match its validation schema") from exc


def _load_samples(raw: bytes) -> list[ColorValidationSample]:
    records: list[ColorValidationSample] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(ColorValidationSample.model_validate_json(line))
        except ValidationError as exc:
            raise EvaluationInputError(
                f"sample record on line {line_number} does not match the validation schema"
            ) from exc
    if not records:
        raise EvaluationInputError("sample file contains no JSONL records")
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate DSI colour previews against independent D50 spectrophotometer references."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--manifest-signature", required=True, type=Path)
    parser.add_argument("--manifest-public-key", required=True, type=Path)
    parser.add_argument("--samples", required=True, type=Path, help="JSONL of pseudonymous validation records")
    parser.add_argument("--policy", required=True, type=Path, help="independently approved release policy JSON")
    parser.add_argument("--policy-signature", required=True, type=Path)
    parser.add_argument("--policy-public-key", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        manifest_raw = _read_bytes(args.manifest, "manifest")
        manifest_signature = verify_ed25519_attestation(
            signed_bytes=manifest_raw,
            signature_path=args.manifest_signature,
            public_key_path=args.manifest_public_key,
            trusted_fingerprint_environment="DSI_EVALUATION_TRUSTED_MANIFEST_PUBLIC_KEY_SHA256",
        )
        samples_raw = _read_bytes(args.samples, "sample")
        policy_raw = _read_bytes(args.policy, "release policy")
        policy_signature = verify_ed25519_attestation(
            signed_bytes=policy_raw,
            signature_path=args.policy_signature,
            public_key_path=args.policy_public_key,
            trusted_fingerprint_environment="DSI_EVALUATION_TRUSTED_POLICY_PUBLIC_KEY_SHA256",
        )

        input_paths = {
            args.manifest.resolve(),
            args.manifest_signature.resolve(),
            args.manifest_public_key.resolve(),
            args.samples.resolve(),
            args.policy.resolve(),
            args.policy_signature.resolve(),
            args.policy_public_key.resolve(),
        }
        if args.output.resolve() in input_paths:
            raise EvaluationInputError("report output must not overwrite an input evidence file")

        manifest = _load_json(manifest_raw, EvaluationManifest, "manifest")
        policy = _load_json(policy_raw, ReleasePolicy, "release policy")
        samples = _load_samples(samples_raw)
        report = evaluate_dataset(
            manifest,
            samples,
            policy,
            manifest_sha256=_sha256(manifest_raw),
            samples_sha256=_sha256(samples_raw),
            manifest_signature_verified=True,
            policy_signature_verified=True,
        )
        report["attestations"] = {
            "manifest": manifest_signature,
            "release_policy": policy_signature,
        }
        serialized = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_name(args.output.name + ".tmp")
        temporary.write_text(serialized, encoding="utf-8")
        temporary.replace(args.output)
    except (EvaluationInputError, AttestationError, OSError, ValueError) as exc:
        print(f"DSI evaluation input error: {exc}", file=sys.stderr)
        return 2

    print(f"Decision: {report['decision']}")
    print(f"Report: {args.output}")
    if report["decision"] == "FAIL":
        return 1
    if report["decision"] == "REVIEW_REQUIRED":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
