# Click It independent privacy verification plan

**Status: Click It remains disabled.** The current BFF rejects Click It before multipart parsing. Vision Intelligence has a separately authenticated internal scan contract with face masking, but the real detector pin/runtime and external privacy providers are not proven in a deployed environment. This document sets the independent evidence required before any enablement proposal.

## 1. System boundary and current controls

Click It is a separate product surface from PNELLY Look It. It must not perform face recognition, identity search, face embeddings, naming, age estimation, identity matching or behavioral profiling. The only permitted face operation is locating regions for conservative masking.

Look It remains a separate consent and retrieval workflow. Its BFF creates short-lived image_processing + look_it consent receipts plus a declaration-specific receipt; the PNELLY boundary re-verifies all three scopes. Only no_people and adults_only declarations are accepted; missing declarations and minor-containing images are rejected. For adults_only, a zero-face detector result fails closed. Its Vision route reuses the face-detection-only masking primitive before quality analysis, image embedding and optional outfit decomposition. This shared privacy primitive does not merge the products, scopes or enablement decisions. The real detector artifact, deployed runtime, false-negative evaluation and independent privacy assessment remain release blockers for both image workflows.

The current code establishes useful fail-closed boundaries:

- Marketplace BFF returns `503 CLICK_IT_PRIVACY_PIPELINE_NOT_RELEASED` without reading or parsing the uploaded body.
- Vision's internal `/v1/click-it/scan` checks explicit processing/purpose consent and photographed-person declaration, requires detector readiness, masks before quality scoring/embedding, closes the unmasked decoded image, and closes the masked working image on success and failure.
- Privacy Governance owns purpose-bound consent receipts, signed jurisdiction policy bundles, photographed-person rights cases, urgent quarantine requests, requester-authority checks and required deletion-surface assertions.
- The privacy route-guard test scans service media routes and static mounts in both service and app source roots; the media-delivery inventory also records the known private binary read paths, the one repository-owned public static root, and currently unverified external origins. These are code-level inventory guards, not proof that external object storage, CDN, caches, backups or provider systems behave correctly.

The following privacy providers are still declared unconfigured/unverified in the canonical deployment inventory: jurisdiction resolver, content-lifecycle provider, guardian verification, requester-authority verification, vision privacy attestation and private object storage. The Privacy Governance `/ready` endpoint must remain 503 while a required provider or its database/signing dependency is unavailable.

## 2. Complete processing lifecycle

| Stage | Required control | Failure result |
|---|---|---|
| Capture | Authenticated uploader; bounded JPEG/PNG/WebP; no background upload; clear separate Click It purpose consent | Reject before parsing/forwarding |
| Photographed-person declaration | `no_people`, `adults_only` or `contains_minor`; declaration is user attestation, not model inference | Unknown/missing declaration blocks |
| Consent | Short-lived consent bound to verified subject, one request/resource, purpose, version and exact scope; revocation checked before processing | No scan and no candidate response |
| Jurisdiction | Signed current policy with complete applicability and cross-border transfer resolution | BLOCK/REVIEW; no processing |
| Child safeguards | Independent, purpose-bound guardian authority for minor-containing images; no child Twin/wardrobe/behavioral personalization | BLOCK |
| Masking | Immutable licensed detector asset and runtime pin; all detected faces masked; uncertainty or detector error fails closed | No embedding or catalog retrieval |
| Product search | Only masked in-memory image reaches image embedding/retrieval; no identity features; product data remains candidate-only until CAL | No candidates returned |
| Response | Aggregate counts and approved non-identifying metadata only; `Cache-Control: no-store`; no image bytes, source URLs or unmasked face output | Suppress response |
| Cleanup | Close original and masked image buffers on every path; no upload spool, temp file, cache, body logging or telemetry payload | Incident and disable pipeline |
| Reporting/removal | Public report and removal intake; urgent quarantine confirmed before acknowledgement; independent requester authority; propagate source/derivative/replica/cache/CDN/shared-link deletion | Keep quarantined; escalate |
| Verification | Independent end-to-end inspection of every ingress, processing, storage, publication, restore and deletion route | Click It remains disabled |

A Click It scan is intended to be ephemeral. It does not create a retained Cirvanna image asset. The image-rights request workflow applies to a retained/shared Cirvanna asset reference, not to a transient scan that no longer exists. These two lifecycles must not be conflated in the product UI or incident response.

## 3. Independent detector and masking evaluation

The evaluator must be independent of the implementation team and must receive the exact candidate release build, detector artifact and test protocol. A third-party model card or internally generated unit-test fixture is not sufficient.

The evidence pack must include:

- detector/model name, immutable version, SHA-256, license, source, transitive dependencies, container/image digest and runtime configuration;
- test-set provenance, consent/rights basis, dataset SHA-256, inclusion/exclusion criteria, capture-device mix, annotation protocol and adjudication process;
- representative and adversarial slices: small/background faces, multiple people, faces at distance, profile/back-facing/partially occluded faces, low light, motion blur, image edges, reflections/posters/screens, varied skin tones and regional/device capture patterns;
- per-slice face detection recall and false-negative rate with confidence intervals, mask coverage, residual unmasked-face rate, uncertainty/rejection rate and sample count;
- tests for overlapping faces, detector timeouts, malformed coordinates, NaN/infinite coordinates, low confidence, no face returned when people are declared, and resource exhaustion;
- proof that the exact masked bytes—not the source bytes—are passed to quality, embedding and catalog search;
- memory/temp-file/log/telemetry inspection demonstrating no original image or face crop escapes the processing boundary.

A high average recall does not compensate for a dangerous false-negative subgroup. Any missed or uncertain face, incomplete mask, unpinned asset, provider mismatch or missing evidence blocks publication and Click It activation. The release decision must define a risk-based minimum recall and confidence interval before evaluation begins; do not choose thresholds after seeing the results.

## 4. Independent end-to-end privacy verification

A separate assessor must test the deployed release, not only source code. The assessment must bind to:

- exact Git commit and PR merge commit;
- service image digests, build provenance, dependency lock/SBOM and detector SHA-256;
- deployment region, service IDs, environment policy and provider versions;
- current consent schema/purpose/version, policy bundle digests and key IDs;
- object-store bucket/versioning/retention configuration, CDN origins, cache rules, backup policies and access logs;
- route inventory including API endpoints, static mounts, signed URLs, background workers, queues, exports, support/admin tools, mobile/deep links and rollback paths.

Required tests include:

1. attempt to access Click It from every public ingress, including the BFF, old compatibility routes, direct Vision worker routes, browser network paths and stale frontend bundles;
2. prove absent, expired, revoked, wrong-subject, wrong-resource, wrong-purpose and replayed consent prevents processing;
3. attempt malformed, missing, low-confidence, out-of-frame, occluded and detector-unavailable masking scenarios; no source image may reach embedding or retrieval;
4. inspect application logs, reverse-proxy logs, tracing, metrics, error reporting, crash dumps and temp directories for image bytes, crops, embeddings, user-supplied filenames, tokens or unnecessary identifiers;
5. enumerate every route and object path that can publish, restore, share, syndicate or serve media; verify the publication gate is enforced before every action;
6. submit urgent possible-minor/unmasked-face/non-consensual reports and prove quarantine/unpublish is confirmed before acknowledgment;
7. approve removal and verify source, derivatives, replicas, object versions, backups where legally required, caches, CDN, merchant surfaces and shared links; record propagation timestamps and exceptions;
8. revoke consent mid-flight and during provider failure; prove the request is cancelled or withheld and cleanup still occurs;
9. test key rotation, provider timeout, queue backlog, retries, duplicate events, stale receipts, provider account mismatch and disaster restore;
10. repeat the audit after any route, storage, CDN, model, consent, provider, deployment or frontend change that can alter the media lifecycle.

The assessor must state tested limitations, residual risk, false-negative confidence bounds, exact evidence references, reviewer identity/independence and report digest. The assessor must reconcile the deployed origin, CDN, legacy public URLs, cache/replica/backup surfaces against `infrastructure/deployment/media-delivery-inventory.json`; repository entries alone do not count as provider-backed evidence. A self-attestation by the team that built the route is not independent verification.

## 5. Required operational response

- **Any suspected unmasked media exposure:** disable Click It and all media publication/restore paths; quarantine implicated assets; preserve security/audit evidence without copying image bytes into tickets; notify the privacy incident owner; start legal/jurisdiction assessment; verify deletion propagation before restoring service.
- **Detector/provider/attestation outage:** fail closed. Do not fall back to an unmasked scan, a different unreviewed model, a face-free assumption, Look It or a direct Vision route.
- **Deletion propagation incomplete:** maintain quarantine and unpublish state, keep the request open, retry through an idempotent workflow, escalate any storage/CDN/backup exception and do not report completion.
- **Minor/guardian uncertainty:** do not process or personalize; escalate under the child-safety runbook.

## 6. Evidence record template

The assessor's signed report should include: `assessment_id`, `release_commit`, `service_image_digests`, `detector_sha256`, `dataset_sha256`, `protocol_version`, `assessor_organization`, `independence_declaration`, `slice_metrics`, `route_inventory_digest`, `storage_cdn_configuration_digest`, `deletion_propagation_results`, `residual_risks`, `report_sha256`, `issued_at`, `expires_at`, and `approval_decision`.

Do not populate the template with synthetic hashes, mock results, or an internal test run. Evidence must be generated by the real assessor against the exact candidate release and reviewed by the privacy owner.

## 7. Enablement rule

Click It stays disabled until detector, consent, jurisdiction, guardian, rights-authority, content-lifecycle, private-storage and masking-attestation providers are actually deployed; the full independent evaluation and route/storage audit passes; operational on-call and incident processes are live; and REL-14 is passed with evidence tied to the exact commit. This proposal does not authorize activation.
