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
