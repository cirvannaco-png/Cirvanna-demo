# Click It privacy, child-safety and image-rights controls

Status: implementation contract and guarded adapter work. The policy registry, rights service, guardian-verification integration and licensed detector asset are external release dependencies; this document does not claim they are deployed.

## 1. Processing boundary

The Click It route remains separate from PNELLY Look It.

1. The BFF validates the signed Commerce user session and active, purpose-specific consent record.
2. Virtual Twin checks the declared photographed-person context, verifies consent, and obtains a current jurisdiction-policy PASS receipt.
3. The Vision Intelligence Click It endpoint validates the image bytes and decodes the image in memory.
4. A licensed, SHA-256-pinned face detector locates faces only. It must not produce identity templates, embeddings, names, matches, age estimates or identity-search results.
5. Every detected face is strongly blurred before image-quality analysis, image embedding, catalog retrieval or other product processing.
6. Any missing, unpinned, unavailable, low-confidence, malformed or uncertain detector output blocks the request. The unmasked decoded image is closed before product embedding.
7. The Click It response contains marketplace candidates only; it does not return the submitted photograph. Candidate display remains subject to CAL, NPL and required cultural-identity checks.

The original and masked uploads are not persisted by the Click It pipeline. Responses are marked `Cache-Control: no-store, private`. Logs and telemetry may contain request IDs, decision codes and aggregate operational metrics only; never image bytes, face crops, face embeddings or biometric/identity signals.

## 2. Prohibited processing

Click It may detect a face solely to locate a region for masking. It must not perform:
- facial recognition, identity verification, identity matching or person search;
- face embeddings, identity templates, naming or reverse-image person search;
- age estimation or sensitive-trait inference from facial features;
- behavioural profiling or preference learning about photographed minors;
- child-specific Twin/wardrobe personalization for images declared to contain a minor;
- any face-reveal override or public exposure of an unmasked child's face.

The current child route blocks Twin personalization whenever a minor is declared. Product discovery is not permission to identify or profile the person photographed.

## 3. Photographed-person declaration and consent

The client must choose one of:
- `no_people`: no person is visible; the consent record must include `photographed_no_people_attestation`;
- `adults_only`: every visible person is declared to be an adult; the consent record must include `photographed_people_adult_attestation`;
- `contains_minor`: at least one minor is visible; the consent record must include `photographed_people_minor_attestation`.

Missing or unknown status blocks processing. This declaration is not facial age estimation and must not be presented as an independently verified fact.

When people are declared visible, the uploader must explicitly attest that they have permission to submit the photograph and, where required, parent/guardian authority. For either `adults_only` or `contains_minor`, the consent service refuses to grant the photographed-person attestation scope unless `photographed_people_consent_confirmed=true`. This is an uploader attestation, not independent proof that every photographed adult consented; it must never be described as verified consent from those people.

For a declared minor, the jurisdiction policy registry decides whether guardian consent is legally required. When required, the consent service must return an active receipt containing the `guardian_authorized` scope and `guardian_authority_verified=true`. A checkbox alone is not guardian verification. The policy registry may apply a stricter platform rule than the legal minimum.

For minor-containing images:
- no Twin, wardrobe or preference-learning personalization is allowed;
- no face reveal or public sharing is allowed;
- the image is processed only for the authorized, narrow product-discovery purpose;
- any safety uncertainty or missing required guardian evidence blocks processing.

## 4. Jurisdiction policy registry contract

Virtual Twin calls:

`POST /internal/v1/privacy/click-it/evaluate`

The registry must resolve the complete set of applicable jurisdictions using trusted subject/account records, the controller and processor establishments, capture context, deployment/processing locations, storage locations and transfer destinations. A user-entered capture jurisdiction is an unverified hint only and must never determine legal applicability by itself.

A PASS receipt must include:
- `decision=PASS`, `current=true`, a policy version and SHA-256 digest;
- a non-empty complete `applicable_jurisdictions` list;
- `jurisdiction_resolution_complete=true` and `policy_conflicts_resolved=true`;
- `lawful_basis_authorized=true` and `cross_border_transfers_authorized=true`;
- a dynamic `guardian_consent_required` decision for declared minors;
- explicit prohibitions for facial recognition, face identity analysis, child facial identity analysis, child behavioural profiling, public unmasked-face exposure, image retention and public sharing.

No country, age threshold, legal basis, retention period, transfer rule or guardian-consent threshold is hardcoded in Click It. The registry owns the current jurisdiction-specific rule set and its versioning. Unsupported or ambiguous jurisdiction, stale policy, missing fields, conflicting policies, denied transfer, missing lawful basis, or unavailable registry => BLOCK/REVIEW.

The policy registry must be maintained through legal review. A new jurisdiction cannot be enabled solely because its country code is recognized.

## 4A. Public media publication safety gate

The Privacy Governance Service exposes `POST /internal/v1/privacy/assets/publication/evaluate`. Public profiles, community feeds, Marketplace media, merchant surfaces and shared links must call this gate before every publish, restore, syndication or share activation. The gate accepts only opaque asset and masking-attestation references; it never accepts an image.

It requires a trusted Vision attestation tied to the exact asset and target surface. The attestation must confirm that all detected faces were masked before publication, zero unmasked faces remain, every detected face region was processed, and no face recognition, face embeddings or age estimation occurred. Missing, stale, mismatched or incomplete evidence blocks publication.

This deliberately masks all detected faces on public assets rather than trying to distinguish children from adults by appearance. It does not identify people or estimate age. This policy is more conservative than a child-only gate and must be disclosed in the product's media-publication terms. The repository contains the gate contract; every actual public publishing path still needs to integrate it and pass end-to-end tests before the platform can claim global protection.

### Current repository route audit

The current service source contains no public profile-photo, community-feed media, shared-link activation, restore, syndication or general user-asset-serving route. The BFF does expose one explicit static mount, `GET /assets/*`, for repository-owned presentation files under `apps/demo-web/assets`. Its directory is fixed in code (not deployment-configurable), must contain no symlinks, and is not an upload or private-media store. The BFF image CSP permits only same-origin and data images; arbitrary remote image origins are blocked. The route guard now inventories both FastAPI media routes and `StaticFiles` mounts, and fails CI if another public static root, configurable media directory or symlinked asset is introduced. Known media-adjacent exceptions are narrowly allowlisted and independently checked: BFF/PNELLY/Vision Look It routes are private, consent-bound input-processing endpoints that close uploads and return only bounded text/count metadata with no-store behavior; Click It remains a pre-read 503; skincare routine sharing serializes text-only routine fields and no media references. These are not permission to publish assets. Any new share, upload, restore, image, render or media route remains blocked by the route inventory until its intended data flow and gate are explicitly reviewed. The privacy publication gate itself remains internal-only.

Until a real asset publication owner and content-lifecycle provider are deployed, Cirvanna deliberately withholds media from customer-facing APIs:
- Commerce `GET /marketplace/offers` returns no image URLs; merchant listing creation does not echo the stored source URLs.
- Marketplace BFF recursively removes image/photo/avatar/thumbnail/render/asset URLs, IDs and references from customer-facing marketplace, wardrobe-recommendation, Click It and allowlisted Commerce JSON responses.
- API Gateway discovery and Vision search/Click It responses apply the same recursive media suppression.
- Catalog stores canonical merchant image URLs behind distinct service-read/service-write bearer scopes; those URLs are not exposed through the customer BFF. Commerce may snapshot them server-side, but the public offer contract remains image-free.
- Virtual Twin's current outputs are pose/metadata responses; image persistence and public rendering remain disabled. Virtual Try-On remains unavailable until its consent, asset-authorisation and renderer adapters are real.
- The separate Virtual Try-On GPU worker's `POST /v1/render` returns a generated PNG only to a caller with its worker bearer credential; it has no input/output persistence, does not accept remote URLs, and sets `Cache-Control: no-store, private`. A static regression guard covers this explicit private-inference exception. The orchestrator remains disabled until live consent verification, asset authorization and renderer registration exist; this worker response is not a public asset publication.

This means the current application APIs do not provide a public path for a photograph or its image reference to be published. It does **not** prove that an externally hosted URL is inaccessible outside Cirvanna, nor does it replace storage-origin, CDN, signed-URL, cache, backup and deletion verification. Those controls belong to the yet-to-be-provisioned Content Lifecycle owner and remain release blockers.

### Face-detector candidate assessment (6 November 2026)

The official MediaPipe Face Detector documentation distinguishes BlazeFace short-range (front-facing/selfie use) from full-range (back-facing phone-camera use). The full-range model card states an Apache-2.0 licence and reports 99.3% global recall, 99.2% average recall across five skin-tone categories, and 96.7–100% recall across its 17 geography groupings. Those figures are not a guarantee for Cirvanna: the card's test sets are limited (1,060 samples in Dataset I, 500 in the skin-tone slice), not disjoint, and sampled from the same source as training. The card also documents out-of-scope back-of-head and strongly turned faces, sensitivity to position/scale/orientation and degraded lighting/occlusion, a detection cap (about 10), and a requirement that at least 70% of a face box remain inside the frame. It is therefore a candidate for Click It evaluation, not a sufficient single control for public image release.

Sources:
- [MediaPipe Face Detector model selection and supported camera ranges](https://developers.google.com/edge/mediapipe/solutions/vision/face_detector)
- [BlazeFace Full Range model card (licence, intended use, limitations and evaluation)](https://storage.googleapis.com/mediapipe-assets/MediaPipe%20BlazeFace%20Model%20Card%20%28Full%20Range%29.pdf)

No model binary is included or pinned by this repository change. A mutable `latest` download URL is not a production pin. Before enabling Click It or any publication path, the selected binary must be obtained from the official source, its exact immutable version and SHA-256 recorded, licence and supply chain reviewed, and an independently curated evaluation run on Cirvanna's actual capture distribution (including small/background faces, faces at distance, profile/back-facing/partially occluded faces, low light, motion blur, multiple people, children, skin-tone and regional slices). Report false-negative rate and confidence intervals by slice; any missed or uncertain face blocks publication. Until these results and the asset-bound verifier are deployed, all public image references remain withheld.

## 5. Photographed-person report and removal workflow

The public BFF intake is:

`POST /api/privacy/image-requests`

It accepts an opaque Cirvanna asset/share reference, request type, reason, requester relationship and an optional unverified jurisdiction hint. It does not accept an arbitrary remote URL, an uploaded identity document, or an image upload. The photographed person, parent/guardian or authorized representative does not need the uploader's account.

The BFF forwards to:

`POST /internal/v1/image-rights/requests`

The rights service must:
- verify requester relationship/authority using a proportionate, privacy-preserving process;
- issue a request ID and status token without requiring an account owned by the uploader;
- immediately quarantine/unpublish urgent reports involving a possible minor, unmasked face, non-consensual exposure or credible safety risk;
- return `quarantined=true` before the BFF acknowledges an urgent report;
- track jurisdiction-specific response deadlines and provide status/appeal/escalation handling;
- propagate approved removals to source objects, derivatives, replicas, caches, CDN surfaces, feeds and shared links;
- preserve only the minimum audit record needed to evidence the request and outcome, with a defined retention schedule.

The BFF deliberately returns an error rather than claiming success when the rights service is unavailable or does not confirm quarantine. The service must have edge rate limits, abuse controls and monitoring before public enablement.
The rights service records a platform triage target separately from any legal response deadline. A statutory deadline is returned only when all applicable jurisdictions have been resolved and every jurisdiction has a current signed policy bundle. When jurisdiction resolution or policy coverage is incomplete, the status reports that the legal deadline is unresolved and exposes only the internal platform triage target; it never substitutes a platform target for a legal obligation.

After submission, the requester receives an opaque request ID and private status token. The public status endpoint is `GET /api/privacy/image-requests/{request_id}`, with the token supplied in the `X-Privacy-Request-Token` header. The BFF forwards the token to the rights service for validation and returns only a minimal status receipt. The token is a bearer secret and must not be placed in a URL, analytics event or application log.

Click It scans are ephemeral and do not retain an original image object. A removal request therefore applies to a retained/shared Cirvanna asset, not a transient scan that no longer exists. The UI asks for a Cirvanna asset/share reference to distinguish those cases.

## 7. Consent-provider and verification dependency

The repository currently contains adapter contracts, not a deployed consent-verification provider or image-rights backend. The consent provider must issue and verify the purpose-bound photographed-person attestation scopes and prove guardian authority when requested by the policy receipt. A consent checkbox alone is not sufficient. The privacy-rights provider must independently verify requester authority, quarantine urgent reports, issue the opaque status token, implement abuse controls and propagate approved deletion across stored copies and derivatives. Until both services exist and pass live integration tests, Click It child-context processing and public rights requests remain unavailable.

## 8. Release blockers

Do not merge or deploy this feature until:
- the exact face-detector asset, licence, provenance, SHA-256 pin and runtime are reviewed;
- independent masking evaluations cover varied lighting, skin tones, face sizes, multiple faces and background bystanders;
- the privacy policy registry is deployed and returns signed/current jurisdiction receipts;
- the consent system verifies adult/no-person/minor attestations and guardian authority where required;
- the image-rights service is deployed with verification, quarantine, deadline tracking and deletion propagation;
- public intake rate limiting and abuse controls are enabled;
- end-to-end tests prove that no unmasked image reaches product embedding, catalog retrieval, logs, telemetry, public display or persistent storage;
- Vision Intelligence, Virtual Twin, Marketplace BFF, architecture and integration workflows pass.

No production deployment or automatic release is authorized by this code alone.
