# ADR-0006: PNELLY brand clearance and commercial launch gate

**Status:** PNELLY identity selected by product owner and runtime migration authorized by [ADR-0010](ADR-0010-pnelly-canonical-assistant-identity.md); commercial trademark clearance remains pending.
**Date:** 4 November 2026
**Supersedes:** The legal-clearance hold remains active. ADR-0010 supersedes this ADR's former Xari runtime-identity hold but does not supersede the commercial clearance requirement.

## Context

The product owner selected **PNELLY** as the canonical public-facing identity for Cirvanna's conversational beauty and marketplace-discovery assistant. The owner specifies the pronunciation as **“Pinelly”**. The spelling is intentional and must remain PNELLY; do not silently normalize it to Pinelly, Nelly or Pnelly.

The implementation historically used Xari identity and configuration: source path `services/xari`, `XARI_API_URL`, `XARI_API_TOKEN`, and Xari-labelled capability metadata. ADR-0010 authorizes PNELLY as the canonical runtime/product identity while preserving that source path, the existing HTTP contract and XARI/TARI credential aliases during a staged migration. Commercial use of the PNELLY mark remains blocked pending counsel-led clearance.

Initial public-web reconnaissance found a US PINELLY trademark application (serial 98164366) for handbags, purses and wallets, reported abandoned on 10 March 2025. This is not evidence that PNELLY is available for software, AI, beauty, marketplace or other services, and it does not establish availability in Kenya or any other target market. Similarity can be assessed by sight, sound and commercial context; the requested pronunciation makes PINELLY a relevant search variant.

## Decision

1. **Product identity:** PNELLY is the selected canonical assistant identity; commercial launch remains subject to trademark clearance.
2. **Owner-confirmed pronunciation:** “Pinelly”.
3. **Runtime identity:** PNELLY is canonical under ADR-0010. Xari, Tari and Xyra are compatibility aliases/source lineage only; no second assistant may be deployed.
4. **No duplicate assistant:** PNELLY is the canonical identity of the existing assistant capability, not a second agent, service or orchestrator.
5. **Compatibility during migration:** Keep `services/xari` and the existing `/v1/*` route contract temporarily. Prefer the paired `PNELLY_API_URL` / `PNELLY_API_TOKEN` configuration; XARI_* and TARI_* remain fallback aliases as defined by ADR-0010. The source-path relocation is a later reviewed change.
6. **Complementer remains separate and optional:** Complementer is an advisory styling collaborator, not a second assistant identity and not an authority over Catalog, Commerce, NPL, FCI or CAL.

## Clearance work required before accepting the name for commercial use

Commission a professional clearance search for the exact word mark **PNELLY**, the phonetic equivalent **PINELLY**, and confusingly similar spellings/pronunciations. Search at minimum:

- Kenya (KIPI), including pending applications and registered marks;
- WIPO Global Brand Database and Madrid System designations;
- intended launch markets, including the United States, United Kingdom and European Union;
- relevant Nice classes based on the actual business model, including software/AI and SaaS (Class 9 and/or 42), marketplace and retail services (Class 35), cosmetics/beauty products (Class 3), and beauty/personal-care services (Class 44), as advised by trademark counsel.

The search must review owners, goods/services specifications, filing/priority dates, status, territorial coverage, opposition history and potential confusion—not merely exact-word matches. Separately verify company/business-name availability, domains and major social handles. Domain or company-name availability does not establish trademark rights.

KIPI's published guidance describes a formal search using Form TM27 and an application using Form TM2; its FAQ lists indicative staged fees. Confirm current forms, fees and eCitizen workflow directly with KIPI before filing. Do not represent a preliminary web search as an official KIPI search or legal opinion.

## Migration gate

Only after written legal clearance and explicit product-owner approval may a separate implementation ADR authorize the migration. That ADR must include:

- an inventory of every Xari service, API, environment variable, route, capability field, UI label, test, deployment manifest, secret and operational reference;
- a compatibility strategy for existing `XARI_*` settings and clients, with a defined deprecation window and no secret leakage;
- a staged rollout, observability, rollback plan and cross-service contract tests;
- confirmation that the migration changes branding only, not assistant permissions, consent requirements, data ownership, orchestration boundaries or safety policy;
- regression coverage proving there is one assistant service and no duplicate Xari/PNELLY orchestrators.

## Acceptance criteria

- [x] Product owner selected the exact spelling PNELLY.
- [x] Product owner confirmed pronunciation “Pinelly”.
- [x] Existing Xari HTTP routes and source path are preserved as compatibility contracts while PNELLY becomes the canonical runtime identity.
- [ ] Professional exact, phonetic and confusing-similarity trademark search completed for Kenya and intended launch territories.
- [ ] Trademark counsel provides written risk assessment and filing recommendation.
- [ ] Domain, company-name and social-handle checks completed.
- [ ] Product owner explicitly approves the legal-risk assessment and migration plan.
- [ ] Separate implementation ADR and tested migration PR approved before any runtime/UI rename.

## Release truth

PNELLY is the product-owner-selected identity, but it is not represented as a cleared or registered trademark. This ADR preserves the legal clearance requirement. It does not authorize commercial launch under PNELLY or claim legal availability. The runtime identity/credential migration is governed by ADR-0010; production deployment and service activation remain separate gates.
