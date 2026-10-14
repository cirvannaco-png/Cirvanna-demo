#!/usr/bin/env python3
"""Conservative, value-redacting source secret scan for the Cirvanna repository.

This is a lightweight guard for common credential formats and high-entropy values
assigned to credential-like keys. It is not a substitute for provider-side secret
scanning or credential rotation. Findings intentionally exclude the matched value.
"""
from __future__ import annotations

import math
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build"}
MAX_FILE_BYTES = 4 * 1024 * 1024

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key-block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("aws-access-key-id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{20,}\b")),
    ("stripe-live-secret", re.compile(r"\b(?:sk|rk)_live_[0-9A-Za-z]{20,}\b")),
    ("embedded-url-credentials", re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s/:@]+:[^\s/@]+@[^\s]+")),
)

ASSIGNMENT = re.compile(
    r"""(?ix)
    \b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|
       secret[_-]?key|password|passwd|private[_-]?key|auth[_-]?token|bearer[_-]?token)
    \b\s*[:=]\s*
    (?P<quote>['"]?)
    (?P<value>[A-Za-z0-9_./+=:-]{20,})
    (?P=quote)
    """
)
PLACEHOLDER_PARTS = (
    "placeholder", "your_", "your-", "change_me", "changeme", "replace_me",
    "example", "sample", "dummy", "redacted", "not_a_secret", "insert_", "todo",
    "test_token", "token_here", "secret_here", "api_key_here",
)


def looks_like_placeholder(value: str) -> bool:
    normalized = value.lower()
    if any(part in normalized for part in PLACEHOLDER_PARTS):
        return True
    compact = re.sub(r"[^a-z0-9]", "", normalized)
    if len(compact) >= 8 and len(set(compact)) <= 2:
        return True
    return False


def entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def iter_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_DIRS for part in relative.parts):
            continue
        if path.name == Path(__file__).name:
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield path


def scan_file(path: Path):
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return []
    findings: list[tuple[int, str]] = []
    occupied: set[tuple[int, str]] = set()

    for category, pattern in PATTERNS:
        for match in pattern.finditer(content):
            token = match.group(0)
            if category == "embedded-url-credentials":
                # The category itself is high confidence; never include the URL in output.
                pass
            elif looks_like_placeholder(token):
                continue
            item = (line_number(content, match.start()), category)
            if item not in occupied:
                occupied.add(item)
                findings.append(item)

    for match in ASSIGNMENT.finditer(content):
        value = match.group("value")
        if looks_like_placeholder(value) or entropy(value) < 3.7:
            continue
        item = (line_number(content, match.start("value")), "high-entropy-credential-assignment")
        if item not in occupied:
            occupied.add(item)
            findings.append(item)
    return findings


def main() -> int:
    findings: list[tuple[str, int, str]] = []
    for path in iter_files():
        for line, category in scan_file(path):
            findings.append((str(path.relative_to(ROOT)), line, category))
    if findings:
        print("Potential secrets detected (values redacted):")
        for path, line, category in sorted(findings):
            print(f"{path}:{line}: {category}")
        print(f"Found {len(findings)} potential secret(s); inspect privately and rotate any exposed credential.")
        return 1
    print("Secret-pattern scan passed: no configured high-confidence credential patterns found.")
    print("Note: this lightweight scan is not a substitute for provider-side secret scanning.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
