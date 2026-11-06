# PNELLY orchestration service

**Canonical runtime:** PNELLY. Xari and Tari are compatibility names only; they do not represent independently deployed agents.

PNELLY preserves the v1 orchestration API and request/response contracts previously served by Xari. Historic `XARI_*` error codes remain stable for existing clients until a separately versioned API migration.

## API contracts

- `GET /health`, `/ready`, `/capabilities`
- `POST /v1/route` — existing consent-aware route-planning contract.
- `POST /v1/marketplace/search` — existing authenticated natural-language candidate-search contract.

Schemas, paths, consent checks, candidate-only semantics and the CAL boundary are unchanged. Search results are not product-display authorization, fit evidence or a purchase instruction.

## Configuration

- `PNELLY_API_TOKEN`: canonical internal bearer token, at least 32 UTF-8 bytes.
- `XARI_API_TOKEN`: temporary compatibility alias, used only when PNELLY is absent.
- `TARI_API_TOKEN`: older compatibility alias, used only when PNELLY and Xari are absent.
- `PNELLY_CHAT_API_URL`: canonical assistant-chat upstream; `XARI_CHAT_API_URL` and `TARI_CHAT_API_URL` are temporary fallbacks.
- `VISION_INTELLIGENCE_API_URL` and `VISION_INTELLIGENCE_API_TOKEN`: private marketplace text-search adapter.

PNELLY-first precedence is deterministic. All aliases resolve to the same implementation. Do not expose internal credentials to browser clients.

## Local verification

    python -m pip install -r requirements.txt
    python -m compileall -q app pnelly tests
    python -m pytest -q

PNELLY coordinates existing bounded capabilities; it does not own Wardrobe, USI, TAL, NPL, EEPL, Catalog, Commerce, CAL, Virtual Twin or Virtual Try-On data. FASHN model execution is owned by Virtual Try-On, never by PNELLY.
