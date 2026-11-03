#!/usr/bin/env python3
"""Fail when canonical application code imports quarantined source material."""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "docs" / "architecture" / "runtime-source-registry.json"
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
SKIPPED_PATH_SEGMENTS = {"candidates", "candidate", "experimental", "experiments"}
FORBIDDEN_SEGMENTS = {
    "integration-staging",
    "integration_staging",
    "source-intake",
    "source_intake",
    "source-candidates",
    "source_candidates",
    "candidates",
    "candidate",
    "experimental",
    "experiments",
    "archive",
    "archived",
}
JS_IMPORT_RE = re.compile(
    r"""(?:\bfrom\s*|\bimport\s*\(|\bimport\s*|\brequire\s*\()\s*["']([^"']+)["']"""
)


def is_quarantined_reference(specifier: str) -> bool:
    """Return true when an import target names a quarantined path segment."""
    normalized = specifier.replace("\\", "/").split("?", 1)[0].split("#", 1)[0]
    segments = re.split(r"[/\.]+", normalized)
    for segment in segments:
        segment = segment.strip().lower()
        if not segment:
            continue
        if segment in FORBIDDEN_SEGMENTS:
            return True
        if segment.replace("_", "-") in FORBIDDEN_SEGMENTS:
            return True
        if segment.replace("-", "_") in FORBIDDEN_SEGMENTS:
            return True
    return False


def python_imports(source: str, file_path: Path) -> list[tuple[int, str]]:
    """Extract statically identifiable Python imports, including dynamic imports."""
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as exc:
        return [(exc.lineno or 1, "unparseable Python source; boundary could not be verified")]

    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.lineno, node.module))
        elif isinstance(node, ast.Call):
            function_name = ""
            if isinstance(node.func, ast.Name):
                function_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                function_name = node.func.attr
            if function_name in {"__import__", "import_module"} and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    found.append((node.lineno, first.value))
    return found


def javascript_imports(source: str) -> list[tuple[int, str]]:
    """Extract static, re-export, dynamic-import, and CommonJS require targets."""
    found: list[tuple[int, str]] = []
    for match in JS_IMPORT_RE.finditer(source):
        line = source.count("\n", 0, match.start()) + 1
        found.append((line, match.group(1)))
    return found


def scan_source_boundaries(
    root: Path, runtime_roots: Iterable[str]
) -> list[str]:
    """Scan registered canonical roots for statically identifiable quarantine imports."""
    errors: list[str] = []
    for relative_root in runtime_roots:
        source_root = root / relative_root
        if not source_root.is_dir():
            errors.append(f"registered canonical source root is missing: {relative_root}")
            continue

        for file_path in sorted(source_root.rglob("*")):
            if not file_path.is_file() or file_path.suffix.lower() not in SOURCE_SUFFIXES:
                continue
            relative_parts = file_path.relative_to(source_root).parts
            if any(part.lower() in SKIPPED_PATH_SEGMENTS for part in relative_parts):
                continue
            try:
                source = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                errors.append(f"{file_path.relative_to(root)}: cannot read source: {exc}")
                continue

            if file_path.suffix.lower() == ".py":
                imports = python_imports(source, file_path)
            else:
                imports = javascript_imports(source)

            for line, specifier in imports:
                if is_quarantined_reference(specifier):
                    errors.append(
                        f"{file_path.relative_to(root)}:{line}: "
                        f"import from quarantined source is forbidden: {specifier}"
                    )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    args = parser.parse_args()

    try:
        registry = json.loads(args.registry.read_text(encoding="utf-8"))
        roots = [
            entry["path"]
            for entry in registry["canonical_roots"]
            if isinstance(entry, dict) and isinstance(entry.get("path"), str)
        ]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"ERROR: cannot load canonical source registry: {exc}")
        return 1

    errors = scan_source_boundaries(ROOT, roots)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"OK: {len(roots)} canonical source roots contain no detected quarantine imports.")
    print("Note: this static guard does not replace dependency, build, or runtime review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
