# Cirvanna Intelligence Service

This service is the first durable runtime for platform-wide CIL source rights,
evidence references, product-serving assessments and consented recommendation
outcomes. It uses PostgreSQL in production through `CIL_DATABASE_URL`; SQLite
is for local tests only. The initial schema is versioned with Alembic under
`migrations/versions`.

## Security and operation

- Set `CIL_DATABASE_URL`, `CIL_ADMIN_TOKEN`, `CIL_SERVICE_TOKEN`, and a
  random `CIL_RECEIPT_SIGNING_KEY` of at least 32 bytes.
- Set `CIL_AUTO_CREATE_SCHEMA=false` in production and run `alembic upgrade head`
  as a release step. Verify PostgreSQL backup/restore before production traffic.
- Source rights are immutable records. Revocation is implemented by inserting
  a new source version in a future migration; do not edit historical evidence.
- Unknown, expired, research-only or purpose-mismatched sources fail closed
  for commercial serving.
- The provider adapter requires HTTPS, an API token, licence ID and terms URL.
  It follows no redirects and does not scrape. No vendor is enabled by default.
- Consent and CAL receipts are HMAC-signed, product-bound, purpose-bound and
  expiry checked. The upstream consent/CAL issuers must share the configured
  verification key and exact receipt schema before outcome ingestion is enabled.
- Cohort metrics are suppressed below 30 distinct contributors. Feedback
  creates a CAL REVIEW signal only; it never suppresses a product automatically.

## Endpoints

- `POST /sources`: admin registers rights and permitted purposes.
- `POST /evidence`: admin registers immutable evidence against a source.
- `POST /serving/assessment`: internal claim-level rights/evidence assessment.
- `POST /outcomes`: internal consent- and CAL-receipt-verified event ingestion.
- `GET /outcomes/aggregate`: minimum-cohort aggregate and review signal.
- `GET /cal/review-queue`: pending review signals for CAL.
- `POST /cal/review-queue/{id}/decision`: persist a signed-in CAL service decision reference.
- `GET /ready`, `GET /capabilities`.

This is not yet a completed provider integration or a substitute for the Catalog
serving path. Catalog must call `/serving/assessment` before exposing product
intelligence claims and must remove ineligible claims fail-closed. Until that
gateway is deployed and verified, CIL-backed claims must not be treated as
approved for customer display.
