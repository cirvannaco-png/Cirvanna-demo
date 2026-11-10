# Cirvanna Intelligence Service

This service is the first durable runtime for platform-wide CIL source rights,
evidence references, product-serving assessments and consented recommendation
outcomes. It uses PostgreSQL in production through `CIL_DATABASE_URL`; SQLite
is for local tests only. The initial schema is versioned with Alembic under
`migrations/versions`.

## Security and operation

- Set `CIL_DATABASE_URL`, `CIL_ADMIN_TOKEN`, `CIL_SERVICE_TOKEN`,
  `CIL_CATALOG_SERVICE_TOKEN`, `CIL_CAL_SERVICE_TOKEN`, and a random
  `CIL_RECEIPT_SIGNING_KEY` of at least 32 bytes. Keep Catalog, internal service,
  and CAL credentials separate.
- Set `CIL_AUTO_CREATE_SCHEMA=false` in production and run `alembic upgrade head`
  as a release step. Verify PostgreSQL backup/restore before production traffic.
- Source rights are append-only events. Registering a source creates the initial rights event; `POST /sources/{source_id}/revoke` appends a prohibition event that immediately blocks subsequent commercial serving assessments.
- Unknown, expired, research-only or purpose-mismatched sources fail closed
  for commercial serving.
- The generic research adapter requires HTTPS, an API token, licence ID and terms URL. It follows no redirects and does not scrape.
- Perfect Corp's YouCam Skin Analysis V2.1 client is disabled by default. Enable it only after signed commercial terms, DPA and retention approval, an API token, licence ID, terms URL and retention-policy reference are configured.
- Perfect Corp photo tasks are adult-only and require a signed consent receipt bound to the exact image digest, provider, purpose and pseudonymous contributor. Images are normalized in memory and EXIF is stripped; only opaque task handles, pseudonymous ownership, digest and expiry metadata are persisted.
- Terminal task results are not released until provider-side task/file deletion succeeds. Schedule the admin-only POST /providers/perfectcorp/reap-tasks route at least every 5 minutes with the CIL admin token; the default abandoned-task TTL is 30 minutes. Keep the provider API token available for deletions after disabling new processing.
- Revieve is not connected. Public SDK material alone does not establish current production API, DPA, retention or deletion terms; see docs/integrations/beauty-provider-research.md.
- Consent and CAL receipts are HMAC-signed, product-bound, purpose-bound and
  expiry checked. The upstream consent/CAL issuers must share the configured
  verification key and exact receipt schema before outcome ingestion is enabled.
- Cohort metrics are suppressed below 30 distinct contributors. Feedback
  creates a durable CAL review request; the Decision Service proxies the queue and
  final decision callback. It never suppresses a product automatically.

## Endpoints

- `POST /sources`: admin registers rights and permitted purposes.
- `POST /sources/{source_id}/revoke`: append an auditable rights-revocation event.
- `POST /evidence`: admin registers immutable evidence against a source.
- `POST /serving/assessment`: internal claim-level rights/evidence assessment.
- `POST /outcomes`: internal consent- and CAL-receipt-verified event ingestion.
- `GET /outcomes/aggregate`: minimum-cohort aggregate and review signal.
- `POST /learning/signals`: batch product/context suitability signals for the recommendation ranker; cohorts below 30 distinct contributors are suppressed.
- `POST /providers/perfectcorp/skin-analysis`, `GET /providers/perfectcorp/skin-analysis/{task_id}`, `DELETE /providers/perfectcorp/skin-analysis/{task_id}`: opt-in, adult-only YouCam skin analysis, contributor-bound polling and provider-file deletion.
- `POST /providers/perfectcorp/reap-tasks`: admin-only cron cleanup for abandoned provider tasks.
- `GET /cal/review-queue`: pending review signals for CAL; the Decision Service exposes the authenticated `/v1/cal/feedback-reviews` proxy.
- `POST /cal/review-queue/{id}/decision`: persist a final CAL service decision reference; the Decision Service forwards decisions from `/v1/cal/feedback-reviews/{id}/decision`.
- `GET /ready`, `GET /capabilities`.

The Catalog serving gate is implemented and calls `/serving/assessment` before exposing product intelligence. The API Gateway can query `/learning/signals` and apply a configurable ranking penalty to products with a high unsuitable share; this is a bounded feedback-informed rerank, not model training or efficacy evidence. The initial `CIL_FEEDBACK_RANKING_WEIGHT` is experimental and requires cohort A/B validation before it is treated as a production ranking policy. Pending/rejected claims remain withheld; only individually eligible ingredient/claim records can pass, with attribution attached when required. Deployment must configure the CIL gateway and verify the end-to-end path before any CIL metadata is exposed.
