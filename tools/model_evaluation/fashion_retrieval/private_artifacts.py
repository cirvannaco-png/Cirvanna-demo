"""Atomic, owner-only writers for private model-evaluation artifacts.

On POSIX, files are created with mode 0600 before any content is written and
new parent directories with mode 0700. On non-POSIX platforms Python's chmod
may not provide an equivalent ACL guarantee; callers must use a restricted
workspace with platform ACLs and this module emits a warning.
"""
from __future__ import annotations

import os
import tempfile
import warnings
from pathlib import Path


def ensure_private_targets_available(paths: list[str | Path], *, overwrite: bool = False) -> None:
    """Fail before expensive work if any output target already exists."""
    if overwrite:
        return
    for path in paths:
        destination = Path(path).expanduser()
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"refusing to overwrite existing private artifact: {destination}")


def write_private_text(path: str | Path, content: str, *, overwrite: bool = False) -> Path:
    """Atomically write UTF-8 text with private permissions and no clobber by default."""
    destination = Path(path).expanduser()
    parent = destination.parent
    missing_directories = []
    cursor = parent
    while not cursor.exists():
        missing_directories.append(cursor)
        cursor = cursor.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    if os.name == "posix":
        if not missing_directories and cursor.stat().st_mode & 0o077:
            raise PermissionError(
                f"private artifact directory has group/other permissions; restrict it to 0700: {cursor}"
            )
        for directory in missing_directories:
            os.chmod(directory, 0o700)
    else:
        warnings.warn(
            "Private artifact permissions are not guaranteed by chmod on this platform; "
            "use a workspace with restrictive OS ACLs.",
            RuntimeWarning,
            stacklevel=2,
        )

    if destination.exists() or destination.is_symlink():
        if not overwrite:
            raise FileExistsError(f"refusing to overwrite existing private artifact: {destination}")
        if destination.is_dir() and not destination.is_symlink():
            raise IsADirectoryError(destination)

    fd, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=parent)
    temporary = Path(temporary_name)
    try:
        if os.name == "posix":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if overwrite:
            os.replace(temporary, destination)
        else:
            # Hard-link creation is atomic and fails if destination appeared
            # after the initial check, preserving the no-clobber guarantee.
            os.link(temporary, destination)
            temporary.unlink()
        if os.name == "posix":
            os.chmod(destination, 0o600)
        return destination
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        finally:
            raise
