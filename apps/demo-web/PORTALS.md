# Cirvanna operational portals

This change extracts the useful merchant and founder-facing parts of the supplied UI source while excluding PAMASMMA and all PAMASMMA-dependent behavior.

## Brand Partner Portal

Open `merchant-portal.html` from the demo web application. It connects to the existing Commerce API and supports:

- Verifying the current actor through `GET /me`.
- Reading the authenticated user's merchant record through `GET /merchants/me`.
- Submitting a merchant application through `POST /merchants/applications`.
- Creating an offer listing from an existing canonical Catalog product UUID.
- Creating variants and recording inventory adjustments.
- Reading merchant-scoped order activity.

The portal does not create a separate brand identity table, accept a client-supplied merchant ID as authority, upload catalog products/images, or fabricate analytics. Catalog product creation and asset ingestion remain in their owning services. The token is held in page memory only and is never written to browser storage. Remote bearer-token requests require HTTPS.

Merchant onboarding and merchant-role issuance are deliberately separate: an application may be pending even if the trusted identity provider has not yet issued the merchant role. The Commerce API remains the authorization authority.

## Founder Console

Open `founder-console.html` from the demo web application. It supports only existing, enforceable Commerce administration:

- Verify the signed actor is an administrator using `GET /me`.
- Read Commerce readiness through `GET /ready`.
- Review paginated merchant applications.
- Approve only when an external verification reference is supplied.
- Reject or suspend merchants through the existing admin decision endpoint.

The new `GET /admin/merchants` endpoint is administrator-only, filtered and paginated. Its response intentionally excludes owner user IDs and internal verification references. Every decision continues to be enforced by the Commerce API.

The console intentionally omits simulated AI metrics, autonomy controls, circuit breakers, action logs, and system health panels for which the supplied code had no authoritative backend implementation.

## Validation

Run from the repository root:

```bash
python -m unittest discover -s apps/demo-web -p 'test_portal_contract.py'
cd services/commerce-service
python -m pip install -r requirements.txt
python -m pytest tests -q
```

The Commerce service workflow also runs its existing migration and test checks. Static portal checks verify route contracts, token handling, TLS restrictions, and the absence of simulated control claims.

## Operational prerequisites

- Deploy Commerce with its existing production OIDC/JWKS configuration, database migration and Catalog integration.
- Configure exact frontend origins in Commerce CORS settings if the portals are hosted on a separate origin.
- Issue tokens through the trusted identity provider; do not paste production tokens into shared devices.
- Give a merchant role only after the business verification process; the UI cannot grant it.
- Keep founder/admin tokens short-lived and restricted to authorized administrators.
- These HTML files are browser clients, not authentication providers or a substitute for production access controls.
