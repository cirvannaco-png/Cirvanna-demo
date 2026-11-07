#!/usr/bin/env python3
"""Create a source-bound SHA-256 manifest after controlled model downloads."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

REQUIRED = (
    "model.safetensors",
    "dwpose/yolox_l.onnx",
    "dwpose/dw-ll_ucoco_384.onnx",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights-dir", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_commit):
        parser.error("--source-commit must be an exact 40-character lowercase Git SHA")
    root = args.weights_dir.resolve()
    if not root.is_dir():
        parser.error("--weights-dir must already exist")
    artifacts: dict[str, str] = {}
    for relative in REQUIRED:
        path = (root / relative).resolve()
        if root not in path.parents or not path.is_file():
            parser.error(f"required model artifact missing or outside weights directory: {relative}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        artifacts[relative] = digest
    manifest = {"schema_version": 1, "source_commit": args.source_commit, "artifacts": artifacts}
    destination = root / "manifest.json"
    temporary = root / ".manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
    temporary.replace(destination)
    print(f"Wrote verified artifact manifest: {destination}")


if __name__ == "__main__":
    main()
