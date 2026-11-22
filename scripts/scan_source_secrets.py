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
    ("embedded-url-credentials", re.compile(r"\bhttps?://[^\s/:@]+:[^\s/@]+@[^\s]+")),
    ("database-uri-credentials", re.compile(r"\b(?P<scheme>postgres(?:ql)?(?:\+[A-Za-z0-9._-]+)?|mysql(?:\+[A-Za-z0-9._-]+)?|mongodb(?:\+srv)?|rediss?|amqps?|nats(?:\+tls)?|mqtts?|kafka)://(?P<user>[^/\s:@]+):(?P<password>[^@\s/]+)@(?P<host>[^/\s]+)", re.IGNORECASE)),
)

# These exact guest:guest AMQP values are preserved in the immutable, non-runtime
# Wardrobe intake snapshot and its extracted/candidate copies. They are local
# development defaults, not production credentials. Keep this allowlist path-,
# line-, scheme- and host-bound: any other use of a default broker credential
# must remain a failing finding. Never copy these fixtures into a runtime service.
HISTORICAL_LOCAL_DEFAULT_URI_FIXTURES = {
    ("integration-staging/source-candidates/31-wardrobe-part-1.txt/docker-compose.yml", 6):
        ("amqp", "guest", "guest", "rabbitmq:5672"),
    ("integration-staging/source-candidates/31-wardrobe-part-1.txt/services/common/config.py", 66):
        ("amqp", "guest", "guest", "localhost"),
    ("integration-staging/source-intake/extracted/0031__wardrobe_part_1.txt", 170):
        ("amqp", "guest", "guest", "rabbitmq:5672"),
    ("integration-staging/source-intake/extracted/0031__wardrobe_part_1.txt", 236):
        ("amqp", "guest", "guest", "rabbitmq:5672"),
    ("integration-staging/source-intake/extracted/0031__wardrobe_part_1.txt", 572):
        ("amqp", "guest", "guest", "localhost"),
    ("integration-staging/source-intake/original/cirvanna-source.txt", 50498):
        ("amqp", "guest", "guest", "rabbitmq:5672"),
    ("integration-staging/source-intake/original/cirvanna-source.txt", 50564):
        ("amqp", "guest", "guest", "rabbitmq:5672"),
    ("integration-staging/source-intake/original/cirvanna-source.txt", 50900):
        ("amqp", "guest", "guest", "localhost"),
    # Exact local-only PostgreSQL defaults in the same immutable, non-runtime source intake.
    ("integration-staging/source-candidates/31-wardrobe-part-1.txt/docker-compose.yml", 4):
        ("postgresql+asyncpg", "cirvanna", "cirvanna", "postgres:5432"),
    ("integration-staging/source-candidates/31-wardrobe-part-1.txt/services/common/config.py", 50):
        ("postgresql+asyncpg", "cirvanna", "cirvanna", "localhost:5432"),
    ("integration-staging/source-intake/extracted/0031__wardrobe_part_1.txt", 152):
        ("postgresql+asyncpg", "cirvanna", "cirvanna", "postgres:5432"),
    ("integration-staging/source-intake/extracted/0031__wardrobe_part_1.txt", 234):
        ("postgresql+asyncpg", "cirvanna", "cirvanna", "postgres:5432"),
    ("integration-staging/source-intake/extracted/0031__wardrobe_part_1.txt", 556):
        ("postgresql+asyncpg", "cirvanna", "cirvanna", "localhost:5432"),
    ("integration-staging/source-intake/original/cirvanna-source.txt", 50480):
        ("postgresql+asyncpg", "cirvanna", "cirvanna", "postgres:5432"),
    ("integration-staging/source-intake/original/cirvanna-source.txt", 50562):
        ("postgresql+asyncpg", "cirvanna", "cirvanna", "postgres:5432"),
    ("integration-staging/source-intake/original/cirvanna-source.txt", 50884):
        ("postgresql+asyncpg", "cirvanna", "cirvanna", "localhost:5432"),
}


def is_historical_local_default_uri_fixture(
    relative_path: str, line: int, scheme: str, user: str, password: str, host: str
) -> bool:
    expected = HISTORICAL_LOCAL_DEFAULT_URI_FIXTURES.get((relative_path, line))
    return expected == (scheme.lower(), user, password, host)


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
SHORT_PASSWORD_ASSIGNMENT = re.compile(
    r"""(?ix)\b(?:password|passwd|pwd)\b\s*[:=]\s*(?P<quote>[\'"])(?P<value>[^\'"\r\n]{4,})(?P=quote)"""
)
BARE_PASSWORD_ASSIGNMENT = re.compile(
    r"""(?im)^\s*(?:export\s+)?[\'"]?(?:password|passwd|pwd)[\'"]?\s*[:=]\s*(?P<value>[A-Za-z0-9_./+=:-]{4,})(?=\s*(?:[,;#}]|$))"""
)
NON_SECRET_PASSWORD_VALUES = {
    "string", "str", "none", "null", "undefined", "true", "false",
}

PLACEHOLDER_PARTS = (
    "placeholder", "your_", "your-", "change_me", "changeme", "replace_me",
    "example", "sample", "dummy", "redacted", "not_a_secret", "insert_", "todo",
    "test_token", "test-secret", "token_here", "secret_here", "api_key_here",
)


def looks_like_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in PLACEHOLDER_PARTS:
        return True
    if normalized.startswith(("your_", "your-", "insert_")):
        return True
    # Match placeholder markers as tokens, not arbitrary substrings inside a real secret.
    marker = re.compile(
        r"(?:^|[^a-z0-9])(?:placeholder|change[_-]?me|replace[_-]?me|example|sample|dummy|"
        r"redacted|not_a_secret|todo|test_token|test-secret|token_here|secret_here|api_key_here)"
        r"(?:$|[^a-z0-9])"
    )
    if marker.search(normalized):
        return True
    compact = re.sub(r"[^a-z0-9]", "", normalized)
    if len(compact) >= 8 and len(set(compact)) <= 2:
        return True
    return False


def looks_like_reference(value: str) -> bool:
    """Recognize common variable/environment references, not literal credentials."""
    normalized = value.strip()
    lowered = normalized.lower()
    if normalized.startswith(("$", "${")):
        return True
    if any(token in lowered for token in ("process.env", "os.getenv", "getenv(")):
        return True
    # Dotted identifier paths such as object.password are references, not literal values.
    return bool(re.fullmatch(
        r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+",
        normalized,
    ))


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
            if category == "database-uri-credentials":
                if looks_like_placeholder(match.group("password")):
                    continue
                try:
                    relative_path = path.relative_to(ROOT).as_posix()
                except ValueError:
                    relative_path = ""
                if is_historical_local_default_uri_fixture(
                    relative_path,
                    line_number(content, match.start()),
                    match.group("scheme"),
                    match.group("user"),
                    match.group("password"),
                    match.group("host"),
                ):
                    continue
            if category in {"embedded-url-credentials", "database-uri-credentials"}:
                # Never include the matched URL or credential value in output.
                pass
            elif looks_like_placeholder(token):
                continue
            item = (line_number(content, match.start()), category)
            if item not in occupied:
                occupied.add(item)
                findings.append(item)

    for match in SHORT_PASSWORD_ASSIGNMENT.finditer(content):
        value = match.group("value").strip()
        if looks_like_placeholder(value):
            continue
        item = (line_number(content, match.start("value")), "hardcoded-password-assignment")
        if item not in occupied:
            occupied.add(item)
            findings.append(item)

    for match in BARE_PASSWORD_ASSIGNMENT.finditer(content):
        value = match.group("value").strip()
        lowered = value.lower()
        if (
            looks_like_placeholder(value)
            or lowered in NON_SECRET_PASSWORD_VALUES
            or looks_like_reference(value)
        ):
            continue
        item = (line_number(content, match.start("value")), "bare-password-assignment")
        if item not in occupied:
            occupied.add(item)
            findings.append(item)

    for match in ASSIGNMENT.finditer(content):
        value = match.group("value")
        if looks_like_placeholder(value) or looks_like_reference(value) or entropy(value) < 3.7:
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
    print("LIMITATION: URI schemes outside the explicit database/cache/broker allowlist are not scanned for embedded userinfo credentials.")
    print("Review and externalize any unsupported connection URI before promoting a source candidate; this scan is not a substitute for provider-side secret scanning.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
