# Catalog service

**Owner:** canonical product/garment identity and item metadata.  
**Status:** implemented API foundation; not yet a complete marketplace or production release.

## Implemented in this service

- Create, read, search/list, update, and soft-archive catalog products.
- Read up to 100 canonical active product records with one authenticated `GET /products/batch?ids=<uuid>&ids=<uuid>` call for trusted internal marketplace retrieval.
- Search product descriptions and categories in addition to name, SKU, and brand for keyword lookup. Semantic ranking is performed by the separate Vision Intelligence service, not in Catalog.
- Validate normalized SKU, currency code, price minor units, metadata JSON, and HTTP(S) image URLs.
- Persist product records through SQLAlchemy (SQLite for local development; PostgreSQL through `CATALOG_DATABASE_URL`).
- Record a version snapshot for creation, updates, and archival.
- Support an optional `expected_version` query parameter for optimistic conflict detection.
- Enforce read-only versus write-scoped bearer credentials for product routes in production; legacy single-token mode is limited to local development. Expose liveness, readiness, and factual capability endpoints separately.

## Local run

From this directory:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export CATALOG_API_TOKEN='replace-with-a-long-random-secret'  # local development only
uvicorn app.main:app --host 127.0.0.1 --port 8080
```

The default database is `sqlite:///./catalog.db`. Use a managed PostgreSQL database and set `CATALOG_DATABASE_URL` for shared environments. Local development supports `Authorization: Bearer $CATALOG_API_TOKEN`. In production, set `CATALOG_ENVIRONMENT=production` and use distinct `CATALOG_READ_TOKEN` and `CATALOG_WRITE_TOKEN` values; GET endpoints accept only the read token and POST/PATCH/DELETE endpoints accept only the write token. Commerce should receive only the Catalog read token in its own server-side `CATALOG_API_TOKEN` setting. The production readiness probe fails if either scoped token is missing or they are equal.

## Product contract

Prices use integer minor units and a three-letter currency code, e.g. `price_minor: 1299, currency: "KES"`. The SKU is normalized to uppercase and must be unique. Product deletion is a soft archive, preserving history. List results are active-only by default; pass `status=archived` or `status=all` when needed.

The API does **not** handle payment credentials, checkout, inventory reservation, merchant bulk import, personalized recommendations, user wardrobes, fit predictions, Click It reconstruction, or Virtual Try-On. The bounded `/products/batch` endpoint is internal data access for trusted services, not a public search or authorization decision. Those remain separate domains and must not be inferred from catalog CRUD working.

## Release constraints

- A versioned Alembic schema migration is provided. For deployments, set `CATALOG_DATABASE_URL`, run `alembic upgrade head` from this directory, and set `CATALOG_AUTO_CREATE_SCHEMA=false`. Local/demo runs may use SQLAlchemy `create_all` for convenience. The migration and rollback process still needs an environment-specific rehearsal before production.
- Production deployment still requires secret management, PostgreSQL provisioning/backup/restore drills, identity and authorization policy, rate limiting, observability, dependency/security scans, and deployment-level smoke tests. Rotate both Catalog scoped credentials independently and restrict write-token distribution to the catalog operator or trusted ingestion service.
- Image URLs are metadata only; the API does not fetch or proxy remote URLs.

## Marketplace browser integration

The standalone marketplace page calls `GET /products` with a bearer token. For a separately hosted frontend, configure `CATALOG_CORS_ORIGINS` as a comma-separated allowlist of exact trusted origins, for example `https://shop.example.com`. Do not use `*`; authenticated cross-origin browser requests are intentionally disabled unless this allowlist is configured. The middleware permits only `GET`/preflight and the `Authorization` and `Accept` headers. Restart the service after changing the setting. Keep the catalog token in a server-side integration for production; the demo page holds it only in page memory and is not an appropriate production credential-distribution design.


## Product intelligence metadata

The optional `attributes.product_intelligence` namespace is validated by
`app/product_intelligence.py` before create or update. It supports:

- **Climate compatibility:** supported climate-condition tags with an evidence reference.
- **Context usage:** intended occasions and use contexts with source provenance.
- **Cultural usage:** explicit product-context tags only when editorially reviewed. The catalogue describes the product context; it does not infer a buyer's culture.
- **Skin response metadata:** ingredient-label and non-clinical cosmetic-intent tags with manufacturer, merchant, or cosmetic-test provenance. These are not diagnoses or guarantees of compatibility.
- **Appearance complement:** shade families, declared undertone matches, finish, pairing colours, and feature-complement tags sourced from merchant cataloguing.
- **Observed outcomes:** consented aggregate feedback only, with a minimum cohort of 30, a time window, a source reference, and limitations. This is an observed descriptive metric—not a calibrated probability, causal efficacy result, or guarantee of future success.

All metadata is versioned with the existing product record and appears in the product-version snapshot. Legacy product attributes remain valid. No new table or migration is introduced because the canonical product attribute document is already versioned JSON.

The minimum cohort threshold is a disclosure safeguard, not a claim of differential privacy or statistical representativeness. Merchant-supplied evidence and editorial tags still require moderation, provenance checks, and audit before being trusted for user-facing claims. CaTaCaCi/CAL remains the final display authority.


## CIL structured product fields

The `attributes.product_intelligence` schema now accepts structured `ingredient_declarations` and typed `claims`. Each structured ingredient declaration requires product-label or product-test evidence with a CIL `source_id`, finished-product scope, and E1/E2/E4 evidence grade. This preserves provenance but does not validate that the source ID exists in a live registry; durable registry verification remains a runtime integration requirement.

Claims are limited to `pending_review` or `rejected`. Catalog deliberately does not accept an `approved` status in this phase. The CIL claim assessor is a contract-only package and is not yet connected to the Catalog serving path. Existing Catalog product-version snapshots continue to preserve the metadata; no new Catalog table or migration is introduced.

## Evidence-backed garment size specifications

The optional `attributes.product_intelligence.garment_fit.size_specs` contract selectively adapts the archive's garment construction fields to Catalog's existing versioned product metadata. It supports tops, bottoms and outerwear in this phase. It records finished-garment dimensions in **millimetres**, plus declared stretch ratio, fit class, fabric weight, structure and ease allowance. It does not store body measurements, infer a person's body shape, or predict fit. The source archive's pattern-dimension model does not declare a unit; its example values must not be copied directly. Every integration must explicitly normalize source values to millimetres before writing Catalog metadata.

Every size specification must:
- reference an existing active canonical Catalog variant UUID belonging to the same product;
- use a `size_label` that exactly matches that variant's canonical `size` attribute after normalization;
- provide the required category-specific finished-garment dimensions; and
- include a CIL source ID and product-specific E1/E2/E4 manufacturer, merchant, independent-product, or licensed-provider evidence. The `evidence.reference` must be the exact registered CIL evidence ID (not merely a source URL or general citation).

Create the product first, create its canonical size variants, then PATCH the product's `attributes.product_intelligence.garment_fit` metadata. Catalog rejects unknown/inactive/cross-product variants and size-label mismatches. A variant cannot be archived while a garment-fit specification references it; remove the specification in a versioned product update first. The data is preserved by existing Catalog product-version snapshots and requires no new table or migration.

The archive's CAD payload, color/L*a*b* values, subjective style vectors and numeric fit score were not imported: they lack the required evidence/ownership boundary or overlap existing product appearance metadata. This contract is descriptive garment evidence only. It does **not** enable FCI, sizing advice, Try-On, or fit guarantees; downstream consumers must apply their own validation and decision gates.

## Canonical product variants

Catalog is the canonical owner of purchasable variant identity. Create a variant with the write-scoped credential:

`POST /products/{product_id}/variants`

```json
{"attributes":{"size":"medium","colour":"blue"}}
```

Catalog normalizes option keys and values, derives a deterministic identity key within the product, and issues an immutable UUID. Repeated equivalent option sets conflict rather than creating duplicate identities. Read-only internal services use `GET /variants/{variant_id}` to verify that an ID exists, is active, and belongs to an active canonical product. Catalog operators can deactivate an identity with write-scoped `DELETE /variants/{variant_id}`; an archived identity is never reissued. Merchant-local SKUs and Commerce variant IDs remain separate provenance fields; Commerce must validate the canonical ID with this endpoint rather than accepting merchant assertions.

Variant-defining attributes are immutable. A materially different option set is a different canonical variant; corrections require a governed deactivation/replacement process rather than mutating the identity in place. This endpoint does not establish offer price, stock, or freshness—Commerce remains authoritative for those facts.


## CIL serving gate

Catalog GET representations for products, variants and version snapshots pass through the CIL serving gate. Set `CIL_GATEWAY_URL` and `CIL_CATALOG_SERVICE_TOKEN` to the internal Intelligence Service. If either is missing, the gateway is unavailable, the product/version does not match, or any CIL assessment response is malformed, Catalog strips `attributes.product_intelligence`. Claims, ingredient declarations, and garment size specifications are filtered item-by-item; only registered source/evidence records with current commercial rights, correct scope/grade, and required attribution are returned. Catalog never trusts client-supplied evidence as a display authorization. The Intelligence Service must contain the referenced CIL evidence ID (Catalog's `evidence.reference` is used as that ID) and source-rights record. The gate is fail-closed and does not change canonical Catalog persistence.
