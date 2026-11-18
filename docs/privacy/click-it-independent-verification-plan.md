# Click It end-to-end privacy and rights verification plan

**Release blocked — Click It must remain disabled.**

## Purpose and threat model

Click It accepts user-supplied photographs that may contain people other than the uploader. The system must prevent identity recognition/search, unauthorized processing, public exposure of unmasked faces, rights violations and retention beyond the approved purpose.

The existing `click_it_privacy.py` component detects and blurs face regions and fails closed on detector configuration or uncertain output. It is not a complete lifecycle. A detector can miss a face; a unit test with synthetic detections cannot prove that every real face is masked. No public route may rely on a single detector result as proof of privacy.

## Hard product boundaries

- No face recognition, identity matching, face embeddings, demographic inference or person search.
- No child face or behavior-based identity analysis. Apply stricter defaults to content involving minors; public unmasked child imagery is prohibited.
- No original-photo retention unless a separately documented, necessary purpose and explicit valid consent authorize it.
- No downstream model, merchant, marketplace, CDN, analytics, moderation or publishing service receives original bytes before privacy processing and rights checks.
- Uncertain detection, missing detector asset, checksum mismatch, failed masking, consent ambiguity, rights complaint, failed deletion or unavailable authorization means deny.
- Click It and Look It remain distinct products and endpoints. Click It must not be enabled by Look It consent or feature configuration.

## Required lifecycle

1. **Intake:** authenticate uploader; validate purpose and jurisdiction; capture explicit, granular consent; assign an opaque asset/request ID; enforce file size/type/dimension limits and malware/content checks.
2. **Transient processing:** process in memory or approved encrypted ephemeral storage with strict TTL. Do not write raw images to logs, traces, crash reports, analytics, temporary public buckets or model caches.
3. **Face masking:** use a commercially/licence-approved, pinned detector. Treat low-confidence, malformed, partial, occluded, multi-person or uncertain results as failure. The pipeline must not return an image or derived result if masking cannot be established.
4. **Human/automated quality checks:** validate output digest, mask coverage and privacy scan. Independently test false negatives across representative lighting, skin tones, ages, poses, occlusion, image quality and group-photo conditions. Any unresolved subgroup failure blocks release.
5. **Rights screening:** provide a photographed-person reporting path; record claim, evidence, case owner and review decision; quarantine disputed content and derivatives immediately; prevent republication while under review.
6. **Downstream use:** only the approved masked derivative may proceed, with purpose-bound authorization and digest-bound provenance. No face/identity features may be invoked.
7. **Publication:** each public/private share, restore, export, syndication, thumbnail, cache, CDN and media-serving route must re-check publication authorization and asset digest. Fail closed if the authorization service is unavailable.
8. **Revocation/deletion:** revoke consent; quarantine immediately; delete originals, derivatives, thumbnails, embeddings/features if any, cached copies, replicas and provider-held copies according to contractual deletion; invalidate CDN caches; collect provider deletion receipts.
9. **Audit:** store minimal, tamper-evident lifecycle metadata (request ID, policy version, asset digest, decisions, provider/model version, timestamps and actor). Never store raw face crops or original image bytes in audit logs.

## Child and guardian controls

- Apply the jurisdiction's age and guardian-consent requirements before processing.
- Where age or guardian authority is uncertain, deny processing and publication.
- Do not publicly expose unmasked faces of minors under any circumstance.
- Do not use a child's image for identity, behavior, biometric, profiling or model-training purposes.
- Ensure guardian revocation triggers the same quarantine, deletion and CDN invalidation lifecycle.

## Route inventory — mandatory before activation

Create a route inventory from the deployed application and infrastructure, not just source grep. Include:

- upload and retry;
- preprocessing and model inference;
- outfit/attribute result APIs;
- object-storage read/write and signed URL issuance;
- gallery/profile/wardrobe display;
- public share and embed;
- publish, unpublish, restore and reprocess;
- moderation/report and appeal;
- export and account deletion;
- thumbnails, image transforms and responsive image endpoints;
- CDN origin, cache, purge and stale-if-error behavior;
- backup/replica retention and restore;
- analytics, observability, support tooling and third-party provider egress.

For every route, record owner, authorization decision, input/output asset digests, consent/rights check, cache behavior, deletion propagation and negative-test evidence. Any unaccounted route blocks release.

## Independent verification protocol

The verifier must be independent of the implementation team and must receive the exact deployed candidate commit, image digests, route inventory and test corpus manifest.

Required evidence:

1. Threat model and data-flow review, including provider subprocessors and cross-border transfers.
2. Consent tests: absent, wrong purpose, wrong subject, expired, revoked, changed version, guardian revoked.
3. Detector tests: missing/unpinned asset, checksum mismatch, no detections, multiple faces, low confidence, partial/occluded faces, corrupt image, runtime exception and adversarial conditions.
4. Binary egress tests: instrument every outbound HTTP, object-store, queue, log, analytics and CDN path; prove original bytes cannot escape before approved masking.
5. Publication tests: attempt every publish/restore/share/thumbnail/CDN route with missing, expired, revoked, mismatched and tampered authorization; verify no bytes are served.
6. Rights tests: report, quarantine, appeal, resolution and repeat-publication attempts.
7. Deletion tests: verify originals and all derivatives are removed or cryptographically inaccessible across application stores, caches, CDN, backups according to documented retention, and provider systems; retain deletion receipts.
8. Child-safety tests across age/guardian uncertainty and revocation.
9. Operational tests: provider outage, timeout, failed cache purge, failed deletion, replay and restore.
10. Signed report with test corpus provenance, model and code digests, coverage, false-negative analysis, unresolved findings, reviewer identity/independence statement and remediation status.

## Activation gate

Click It remains disabled until REL-09, REL-14, REL-16 and the relevant staging evidence in REL-11 pass on the exact release candidate, with independent sign-off. A successful unit suite, face-blur screenshot, mock provider, or documentation checklist is not activation evidence.

**Stop condition:** if any raw/unmasked image can reach an unapproved downstream system or any publication/deletion path cannot be enumerated and tested, Click It stays disabled.
