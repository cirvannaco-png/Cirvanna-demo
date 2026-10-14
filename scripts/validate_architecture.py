#!/usr/bin/env python3
"""Validate Cirvanna's architecture inventory and scaffold ownership."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "migration" / "module-inventory.json"


def validate_inventory(manifest: dict[str, Any], root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    modules = manifest.get("modules")
    snapshots = manifest.get("sourceSnapshots")

    if not isinstance(modules, list) or not modules:
        return ["modules must be a non-empty array"]
    if not isinstance(snapshots, list) or not snapshots:
        return ["sourceSnapshots must be a non-empty array"]

    module_ids: list[str] = []
    targets: list[str] = []
    for module in modules:
        if not isinstance(module, dict):
            errors.append("each module must be an object")
            continue
        module_id = module.get("id")
        target = module.get("target")
        if not isinstance(module_id, str) or not module_id.strip():
            errors.append("each module must have a non-empty id")
        else:
            module_ids.append(module_id)
        if not isinstance(target, str) or not target.strip():
            errors.append(f"module {module_id!r} must have a target")
            continue
        if target.startswith("/") or ".." in Path(target).parts:
            errors.append(f"unsafe target path: {target}")
            continue
        targets.append(target)
        if not (root / target / "README.md").is_file():
            errors.append(f"module target is missing README scaffold: {target}")

    if len(module_ids) != len(set(module_ids)):
        errors.append("module ids must be unique")
    if len(targets) != len(set(targets)):
        errors.append("each module must own a distinct target path")

    seen_artifacts: set[str] = set()
    previous_range_end = 0
    for snapshot in sorted(snapshots, key=lambda item: item.get("lineStart", 0)):
        if not isinstance(snapshot, dict):
            errors.append("each source snapshot must be an object")
            continue
        artifact = snapshot.get("artifact")
        start, end = snapshot.get("lineStart"), snapshot.get("lineEnd")
        if not isinstance(artifact, str) or not artifact:
            errors.append("each source snapshot must have an artifact name")
        elif artifact in seen_artifacts:
            errors.append(f"duplicate source artifact: {artifact}")
        else:
            seen_artifacts.add(artifact)
        if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
            errors.append(f"invalid line range for source artifact: {artifact}")
        elif start <= previous_range_end:
            errors.append(f"overlapping or unsorted source range: {artifact}")
        else:
            previous_range_end = end
        candidate_targets = snapshot.get("targets")
        if not isinstance(candidate_targets, list) or not candidate_targets:
            errors.append(f"source artifact {artifact!r} must have candidate targets")
        else:
            for target in candidate_targets:
                if not isinstance(target, str) or target.startswith("/") or ".." in Path(target).parts:
                    errors.append(f"unsafe candidate target for {artifact!r}: {target}")
                elif not (root / target / "README.md").is_file():
                    errors.append(f"source artifact {artifact!r} points to a target without README scaffold: {target}")

    intake = manifest.get("intakeArtifact", {})
    if intake.get("sourceSnapshotCount") != len(snapshots):
        errors.append("sourceSnapshotCount does not match sourceSnapshots")
    if intake.get("runtimeSourcePromoted") is not False:
        errors.append("runtimeSourcePromoted must remain false until migration gates pass")
    if manifest.get("repository") != "cirvannaco-png/Cirvanna-demo":
        errors.append("repository identity mismatch")
    return errors


def main() -> int:
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot load module inventory: {exc}")
        return 1
    errors = validate_inventory(manifest)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(
        f"OK: {len(manifest['modules'])} modules, "
        f"{len(manifest['sourceSnapshots'])} source snapshots, "
        "all target paths scaffolded. Runtime source remains unpromoted."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
