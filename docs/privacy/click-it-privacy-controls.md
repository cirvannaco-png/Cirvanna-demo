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

Click It scans are ephemeral and do not retain an original image object. A removal request therefore applies to a retained/shared Cirvanna asset, not a transient scan that no longer exists. The UI asks for a Cirvanna asset/share reference to distinguish those cases.

## 6. Release blockers

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
