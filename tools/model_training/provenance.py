"""Strict source provenance helpers for reproducible model training."""
from __future__ import annotations
import re, subprocess
from pathlib import Path

_COMMIT=re.compile(r"^[0-9a-f]{40}$")

def require_clean_source_revision(repository_root:Path)->str:
    root=repository_root.resolve()
    try:
        revision=subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True,stderr=subprocess.DEVNULL).strip()
        dirty=subprocess.check_output(["git","status","--porcelain","--untracked-files=normal"],cwd=root,text=True,stderr=subprocess.DEVNULL)
    except Exception as exc:
        raise RuntimeError("model training requires a Git checkout with a committed source revision") from exc
    if not _COMMIT.fullmatch(revision):
        raise RuntimeError("Git HEAD is not a full commit SHA")
    if dirty.strip():
        raise RuntimeError("model training requires a clean source tree; commit all code and configuration first")
    return revision
