#!/usr/bin/env python3
"""Download a gated SAM 3D Body model revision and create its immutable artifact manifest.

Run only after the model card/license terms have been reviewed and accepted.
The HF token is read from HF_TOKEN and is never written to the manifest or logs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

from huggingface_hub import snapshot_download

SOURCE_COMMIT = "b5c765a0d89d789985e186d396315e7590887b94"
DEFAULT_MODEL_ID = "facebook/sam-3d-body-dinov3"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def release_digest(model_id: str, revision: str, files: dict[str, str]) -> str:
    canonical = json.dumps(
        {
            "model_id": model_id,
            "model_revision": revision,
            "source_commit": SOURCE_COMMIT,
            "files": dict(sorted(files.items())),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", default=os.getenv("SAM3D_BODY_MODEL_ID", DEFAULT_MODEL_ID))
    parser.add_argument("--revision", default=os.getenv("SAM3D_BODY_MODEL_REVISION", ""))
    parser.add_argument("--output", default=os.getenv("SAM3D_BODY_ARTIFACT_DIR", "./sam3d-body-artifacts"))
    parser.add_argument("--checkpoint-file", default=os.getenv("SAM3D_BODY_CHECKPOINT_FILE", "model.ckpt"))
    parser.add_argument("--config-file", default=os.getenv("SAM3D_BODY_CONFIG_FILE", "model_config.yaml"))
    parser.add_argument("--mhr-file", default=os.getenv("SAM3D_BODY_MHR_FILE", "assets/mhr_model.pt"))
    args = parser.parse_args()

    token = os.getenv("HF_TOKEN", "")
    if not token:
        raise SystemExit("HF_TOKEN is required; provide it through a secret environment variable.")
    if args.model_id != DEFAULT_MODEL_ID:
        raise SystemExit(f"Unsupported model id: {args.model_id}")
    if not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        raise SystemExit("A full 40-character Hugging Face model revision is required.")
    if os.getenv("SAM3D_BODY_LICENSE_ACCEPTED", "").lower() != "true":
        raise SystemExit("Set SAM3D_BODY_LICENSE_ACCEPTED=true only after license review and acceptance.")
    if not os.getenv("SAM3D_BODY_LICENSE_EVIDENCE_ID", "").strip():
        raise SystemExit("SAM3D_BODY_LICENSE_EVIDENCE_ID must reference the approved license evidence.")

    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=args.model_id,
        revision=args.revision,
        token=token,
        local_dir=str(output),
        local_dir_use_symlinks=False,
    )

    required = [args.checkpoint_file, args.config_file, args.mhr_file]
    for relative in required:
        path = (output / relative).resolve()
        if output not in path.parents or not path.is_file():
            raise SystemExit(f"Required model file is missing: {relative}")
    if (output / args.checkpoint_file).parent != (output / args.config_file).parent:
        raise SystemExit("model_config.yaml must be beside the checkpoint file.")

    files: dict[str, str] = {}
    for path in sorted(output.rglob("*")):
        if not path.is_file() or path.name == "manifest.json":
            continue
        if ".cache" in path.parts or path.name.endswith(".lock"):
            continue
        relative = path.relative_to(output).as_posix()
        files[relative] = sha256_file(path)

    release = release_digest(args.model_id, args.revision, files)
    manifest = {
        "schema_version": 1,
        "model_id": args.model_id,
        "model_revision": args.revision,
        "source_commit": SOURCE_COMMIT,
        "files": files,
        "model_release_sha256": release,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "model_id": args.model_id,
        "model_revision": args.revision,
        "source_commit": SOURCE_COMMIT,
        "model_release_sha256": release,
        "file_count": len(files),
        "manifest_path": str(manifest_path),
    }, indent=2))


if __name__ == "__main__":
    main()
