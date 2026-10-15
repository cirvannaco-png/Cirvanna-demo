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
