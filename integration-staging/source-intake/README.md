# Cirvanna Source Intake Archive

## Purpose

This directory preserves the source material supplied for Cirvanna
architecture reconstruction and repository integration.

## Directory layout

- original/: Original merged source archive.
- extracted/: Individual source sections extracted from the archive.
- manifests/: Source inventory, checksums, audit report and index.
- scripts/: Source extraction, auditing and comparison utilities.

## Important status

These files are preserved source candidates, not a declaration that
every included component is implemented, runnable, tested or production-ready.

Some sections may be duplicates, incomplete, malformed, outdated or
inconsistent with other versions. Review the manifest and audit report
before promoting any candidate into canonical application directories.

The archive's SHA-256 checksum must be compared with the original
before declaring the preservation copy verified.

## Security

Review this archive and all extracted files for credentials, private
keys, database connection strings, broker credentials and other secrets
before committing. The repository's secret scanner has documented
coverage limitations and cannot establish that all files are safe.

Do not use production credentials in source files. Externalize secrets
into appropriate environment variables or secret-management systems.

## Integration policy

Preserve source provenance. Do not overwrite existing application code
merely because a candidate has a similar filename or module name.

Promote candidates only after reviewing their dependencies, interfaces,
security, tests and compatibility with the canonical architecture.


## Redaction status — 15 October 2026

A credential-pattern review found credential-bearing database/cache URI shapes, quoted password assignments, and API/key-like assignments in historical examples. The tracked archive and affected extracted/source-candidate examples have been redacted in the security review branch: credential values are replaced with explicit `REDACTED` placeholders. These files are preserved for provenance and review, not as byte-identical originals or runnable deployments.

**Checksum semantics:** the SHA-256 values in the intake manifests describe the pre-redaction snapshots and therefore must not be treated as checksums for the sanitized files. The owner-reported SHA-256 of the original local archive is `0313937af5be95d0fac8798ed96a38f0d25b3a405441be3f64569f8a6bb9a45b`; keep that exact original in owner-controlled storage, not in the repository. If any detected value was a real or reused credential, rotate it. A pattern scan is not proof that every secret has been found.

The updated CI scan covers credential-bearing PostgreSQL, MySQL, MongoDB and Redis URIs plus quoted password assignments. Keep this security PR gated on the scan and source-candidate syntax workflow passing.
