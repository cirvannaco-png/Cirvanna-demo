# Source archive credential-pattern review

**Reviewed:** 2026-10-15  
**Scope:** All 31 extracted source snapshots under `integration-staging/source-intake/extracted/`. The original merged archive remains preserved byte-for-byte; it was not independently scanned through the connector because the large-file content response was empty, so this report describes the extracted-snapshot scan rather than claiming a direct raw-archive scan.

## Findings

An expanded, read-only pattern check found **46 URI occurrences containing user-info** across 11 extracted snapshots. The parsed hosts were limited to `localhost`, `postgres`, and `rabbitmq`—loopback or typical internal container-service names. This is consistent with local development or container examples, but it does **not** prove the credentials are harmless, unused, or safe to reuse. No credential values are reproduced here.

| Snapshot | Lines containing credentialed connection URIs |
|---|---|
| `0006__EEPL_V2.0.txt` | 1836 |
| `0012__NPL_V2.txt` | 60 |
| `0013__Tari_improved_.txt` | 1436 |
| `0014__We_have_now.txt` | 1226, 1258, 1270, 1311 |
| `0015__Xyra.txt` | 178 |
| `0017__txt` | 1436 |
| `0023__virtual_Tryon_1_.txt` | 14, 99, 129, 144, 177, 225, 244, 3155 |
| `0024__virtual_Tryon_2_.txt` | 14, 99, 129, 144, 177, 225, 244, 3155 |
| `0025__virtual_Tryon_.txt` | 6, 93, 124, 137, 178, 3195 |
| `0026__virtual_Tryon_improved.txt` | 14, 99, 129, 144, 177, 225, 244, 3155 |
| `0031__wardrobe_part_1.txt` | 152, 170, 234, 236, 328, 556, 572 |

A separate heuristic flagged hard-coded credential-like assignments (including API-key, password, and token labels). Some matches are code parameters or type annotations rather than assigned secret values, so these require contextual review and must not be treated as confirmed active credentials solely from the pattern match.

## Repository-level source-candidate spot-check

A separate code-search spot-check of the assembled `integration-staging/source-candidates/` mirrors found repeated development-style defaults in database and message-broker connection configuration, including user-info in local/container service URIs and password-valued environment examples. The observed examples referenced local or internal container hostnames; this is not evidence that every value is harmless or unused. The spot-check was not an exhaustive secret scan of all candidate files. Treat these values as unsafe for shared, staging, or production environments, and replace defaults with required environment configuration before promoting any candidate. The scanner now checks common PostgreSQL, MySQL, MongoDB and Redis URI user-info patterns, but regex matching and placeholder heuristics can miss or misclassify values; a green run is not equivalent to a full secret clearance.

## Required handling

1. Keep the archive and extracted snapshots as provenance-only source material; do not promote their embedded connection strings or credential-like values into runtime code.
2. Runtime services must receive credentials from environment configuration or a secret manager. Examples should use empty values or clearly nonfunctional placeholders.
3. Before promoting any specific candidate, inspect its listed lines and nearby configuration. If any credential may have been used against a non-local or shared service, rotate it and review provider logs.
4. The repository's existing high-confidence scanner and green workflow are useful checks, not proof that the archive contains no secrets. Extend automated coverage to credentialed database/cache/message-broker URIs before treating source intake as security-cleared.

## Limitations

This is a regex-based triage report, not a complete secret-scanning or penetration-test result. URI user-info can be an intentional local fixture; regex hits can also be false positives. The report deliberately omits the matched credential values.
