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
- Source rights are append-only events. Registering a source creates the initial rights event; `POST /sources/{source_id}/revoke` appends a prohibition event that immediately blocks subsequent commercial serving assessments.
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
- `POST /sources/{source_id}/revoke`: append an auditable rights-revocation event.
- `POST /evidence`: admin registers immutable evidence against a source.
- `POST /serving/assessment`: internal claim-level rights/evidence assessment.
- `POST /outcomes`: internal consent- and CAL-receipt-verified event ingestion.
- `GET /outcomes/aggregate`: minimum-cohort aggregate and review signal.
- `GET /cal/review-queue`: pending review signals for CAL.
- `POST /cal/review-queue/{id}/decision`: persist a signed-in CAL service decision reference.
- `GET /ready`, `GET /capabilities`.

The Catalog serving gate is implemented and calls `/serving/assessment` before exposing product intelligence. Pending/rejected claims remain withheld; only individually eligible ingredient/claim records can pass, with attribution attached when required. Deployment must configure the CIL gateway and verify the end-to-end path before any CIL metadata is exposed.
