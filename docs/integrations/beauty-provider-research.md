# External Beauty Provider Research and Integration Readiness

Research reviewed: 10 November 2026. This records public vendor materials and the implementation boundary; it is not evidence that either vendor has granted Cirvanna a licence or activated production credentials.

## Decision summary

| Provider | Publicly documented integration | Cirvanna implementation state | Activation gate |
|---|---|---|---|
| Perfect Corp YouCam AI Skin Analysis V2.1 | REST File API, presigned PUT upload, asynchronous task create/poll, task/file deletion | Dedicated connector and internal routes implemented; disabled by default | Signed commercial licence, DPA/retention approval, API token, provider privacy review, staging validation |
| Revieve AR SDK / BeautyCatalyst | Public browser SDK page (AR SDK v0.9); partner ID; image passed to client SDK and sent to Revieve on initialize. Beauty LLM Suite announcement describes six intelligence domains | Research and integration boundary documented; no connector or SDK enabled | Current partner SDK/API specification, partner ID, licence, DPA, retention/deletion guarantees, region/subprocessor list and staging evidence |

## Perfect Corp YouCam

Official references:

- [Quick Start Guide](https://docs.perfectcorp.com/develop/quick_start_guide)
- [AI Skin Analysis V2.1 standard analysis](https://docs.perfectcorp.com/reference/ai_skin_analysis/standard-analysis)
- [AI Skin Analysis integration guide](https://docs.perfectcorp.com/reference/ai_skin_analysis/section/overview/integration-guide)
- [File Management API](https://docs.perfectcorp.com/reference/file)
- [Task Management API](https://docs.perfectcorp.com/reference/task_management)
- [Delete task and its files](https://docs.perfectcorp.com/reference/task_management/paths/~1s2s~1v2.0~1task~1delete/post)
- [YCO API Terms of Service (last updated September 2026)](https://www.perfectcorp.com/perfectbeauty/youcam/terms-of-service-api)
- [YouCam Privacy Policy (effective June 2026)](https://www.perfectcorp.com/perfectbeauty/youcam/privacy-policy)

The documented workflow is:

1. POST /s2s/v2.0/file to request a file ID and presigned upload URL.
2. PUT the image bytes to that URL with the returned content headers. The metadata call alone does not upload the file.
3. POST /s2s/v2.1/task/skin-analysis with src_file_id, dst_actions and format.
4. GET /s2s/v2.1/task/skin-analysis/{task_id} to poll the asynchronous result.
5. POST /s2s/v2.0/task/delete with the task ID to delete the finished task, associated input file and generated output files.

The official V2.1 skin-analysis reference describes a selfie-based assessment with 16 metrics and optional advanced report/product recommendation add-ons. Perfect Corp also describes the `ui_score` as a presentation-oriented score adjusted to be more favorable for consumer psychology; treat `raw_score` as the underlying provider metric and never treat either score as clinical evidence or as a substitute for independent validation. Cirvanna does not enable the vendor product-recommendation add-on: provider suggestions must not bypass Cirvanna Catalog ranking, evidence/rights checks or CAL. Published input constraints include JPEG/PNG, less than 10 MB, a minimum short side of 480 px for SD and 1080 px for HD, and automatic resizing to 2560 px maximum long side. The current V2.1 action schema uses `hd_age_spot` (not `hd_spot`) and `hd_skin_type`; SD and HD actions cannot be mixed. The documented V2.1 task endpoint and task-status endpoint are both `/s2s/v2.1/task/skin-analysis` (POST and GET respectively). V2.1 analysis results are image-based indicators, not clinical measurements, medical diagnosis or medical assessment. Pricing is unit-based and depends on the number of concerns and SD/HD mode; the API Console must be checked before cost-bearing use.

### Contractual privacy caveat — activation blocker

Perfect Corp's current YCO API Terms are a material constraint, not a footnote:

- Section 3.4 says some services identify facial geometry and places responsibility on the API client to obtain consent from **any person in the photo**. The connector therefore requires an adult, single-subject consent receipt and now performs a conservative face-count screen. The screen rejects zero or multiple detectable faces; it is not a proof that every face in an image is detectable, so independent false-negative testing remains mandatory before live use.
- Section 4.1 says the API service is adults-only. Cirvanna therefore disables this provider route for children even though other Cirvanna photo experiences can apply separate child-safe face masking.
- Section 8.6(t) prohibits using the service to create datasets to train neural networks or third-party photo-editing templates. Cirvanna must not turn provider inputs, outputs or scores into training corpora or reverse-engineer provider functionality.
- Section 11.2.1 says Perfect will use User Submissions only as necessary to provide the service, comply with law or prevent abuse, and will not use them to develop or improve services unless the customer explicitly agrees.
- Section 12.4 says Perfect generally retains Client Data and AI-generated Content for 30 days after a session. The task deletion endpoint separately says it deletes the finished task and associated input/output files. Public material does not establish whether that API deletion overrides the general 30-day retention schedule for backups, logs, abuse-prevention copies or all derived outputs.
- The API Terms also say that Perfect disclaims responsibility for deletion failures (section 1.2) and that uploaded data is to be lawfully collected with required consent (sections 12.2–12.3).

**Result:** the connector now requires an executed retention/erasure schedule reference, DPA approval, an explicit verified-erasure-SLA flag and a contractual maximum provider-retention setting of no more than one hour before new tasks can start. The publicly stated 30-day default does not meet this gate. Deletion calls are still made before result release and by the cleanup reaper, but that is technical best-effort deletion—not independent evidence that every provider-side copy is erased. Do not set the erasure gate until Perfect Corp confirms in writing that the account's contractual/API-specific terms provide the required deletion/retention guarantee, including backups, temporary upload files, masks, derived content and logs.

### Cirvanna connector controls

The implementation in services/intelligence-service/app/perfectcorp.py follows the documented File API/task/poll/delete flow and only accepts the documented Perfect Corp API hostname plus presigned upload URLs on the expected S3 acceleration host suffix.

The internal routes are:

- POST /providers/perfectcorp/skin-analysis
- GET /providers/perfectcorp/skin-analysis/{task_id}
- DELETE /providers/perfectcorp/skin-analysis/{task_id}
- POST /providers/perfectcorp/reap-tasks (admin/cron cleanup)

Controls implemented:

- Disabled by default. A valid API token, licence ID, terms URL, retention policy reference, explicit DPA approval, verified erasure-SLA flag and contractual maximum provider retention of no more than one hour are required before task creation.
- Adult-only: the signed consent receipt must assert age 18+, one consenting subject, the Perfect Corp provider, the exact image SHA-256 digest and the perfectcorp_skin_analysis purpose. OpenCV frontal/profile screening rejects uploads where it cannot detect exactly one face. This is a conservative screening layer, not an identity system or a guarantee against missed faces.
- User-owned raw bytes are accepted in memory only. The service verifies the actual JPEG/PNG content, corrects EXIF orientation, removes EXIF metadata by re-encoding, and normalizes the image to JPEG before upload.
- No face identity search, matching or recognition endpoint is used. This is a separately consented skin-analysis task, not Click It or Look It. The face-count screen only estimates how many faces are visibly present; it must be evaluated for false negatives against diverse real-world images before activation.
- No raw image or mask URL is persisted. The durable task ledger stores only provider/task reference, pseudonymous contributor token, image digest, consent expiry and task timestamps/status.
- Polling is contributor-bound. On terminal success/error, the service calls the provider task-deletion API before releasing the result. If deletion cannot be confirmed, it fails closed and does not release the result.
- Consent expiry or withdrawn DPA approval triggers deletion on the next poll. Abandoned tasks require the admin cleanup route to be invoked by a scheduled job; the default TTL is 30 minutes. Keep provider API credentials available for deletion even after disabling new processing.
- Results expose allowlisted numeric metric scores only; detection-mask URLs and other provider URLs are removed.
- Product recommendations from the provider are not treated as CAL approval. Any product display still requires Cirvanna Catalog evidence/rights and CaTaCaCi/CAL.

### Required production evidence

Before turning on CIL_PERFECTCORP_ENABLED=true, record:

- Executed commercial licence and DPA/processing terms covering face-photo handling, purposes, sub-processors, international transfer, data residency, security, incident notification, user deletion requests and model-training/reuse restrictions.
- A signed written amendment or applicable order that resolves the current API Terms' general 30-day Client Data retention against the task-delete endpoint, and specifies deletion of uploaded images, temporary files, task inputs, generated masks, derived results, logs and backups within the one-hour activation threshold.
- A verified API key, contractual unit pricing, usage ceilings and budget alerts.
- End-to-end staging evidence for upload, task failure, poll, immediate delete, abandoned-task reaping, consent expiry and revoked approval.
- Security review of the presigned upload host behavior and all returned URL handling.
- Independent evaluation of the single-visible-face screening false-negative rate across lighting, skin tones, pose, occlusion, image quality, glasses, head coverings and background bystanders. Until this passes, keep live provider upload disabled.

The connector is code-complete as a gated client/route foundation, not vendor-activated or production-certified.

## Revieve

Official public references:

- [Revieve AR SDK documentation](https://ar-sdk.revieve.com/)
- [Revieve Makeup Artist product page](https://www.revieve.com/solutions/makeup-artist)
- [Revieve Beauty LLM Suite announcement, 13 October 2026](https://www.revieve.com/insider/news/revieve-beauty-llm-suite-specialized-ai-intelligence)
- [Revieve current public news feed with October 2026 deployments](https://www.revieve.com/insider/news)

The publicly accessible AR SDK page identifies version 0.9, requires a partner ID, and shows both React and base-JavaScript usage. Revieve's current public site also reports a 28 October 2026 launch of [SKIN]ALYZE PRO across seven European markets and a 7 October 2026 PT Rohto Laboratories Indonesia deployment; these prove market activity, not API access, performance validation or permission to ingest their data. The SDK accepts a Base64 image or HTML file object; its documented initialize method sends the image to Revieve for analysis before filter methods become available. The public page does not provide a complete current enterprise API contract, a documented server-side upload/task lifecycle, a deletion endpoint or a verifiable data-retention SLA.

Revieve's October 2026 Beauty LLM Suite announcement describes six domains: Skin, Ingredient, Product, Routine, Beauty Lifestyle and Brand Intelligence. This is a useful market/architecture signal for Cirvanna's domain separation, not evidence of an API endpoint, model licence, dataset right or deployable partner integration.

### Privacy and DPA findings from Revieve's published documents

Revieve's [Solutions: Data & Technology Overview (effective 3 April 2026)](https://www.revieve.com/solutions-data-technology-overview) provides more concrete privacy information than the SDK page alone:

- In the **standard Advisor** experience, Revieve says selfie images are processed transiently for skin analysis, deleted immediately after analysis, and not stored. The service retains derived numeric scores/attributes and anonymized product/preferences/context events. It also says standard Advisor uses a session-specific anonymous identifier and does not receive directly identifying information.
- Revieve says it does not train models on consumer personal data collected through its solutions or use it to develop generalized/shared models. It may use aggregate anonymized data for analytics, benchmarking and service improvement only where the client agreement permits it.
- The optional **Pro** experience is materially different: it may include email, authentication data, account-associated selfies and historical results, under client-controlled settings and privacy notices. Do not assume standard Advisor terms apply to Pro or to the old public AR SDK.
- Revieve's public DPA (effective 1 January 2025, updated 1 February 2026) describes controller/processor roles, client instructions and consent responsibilities, subprocessor notification, international transfer mechanisms and security controls. It lists cloud and analytics subprocessors in multiple regions (including AWS, Google Cloud, Google Analytics, MongoDB, Vaisala, MaxMind and Functional Software). The current list and actual regions must be reconfirmed in the partner contract.
- The public DPA contains a deletion timing ambiguity: section 10.2 refers to a mutually agreed timeframe and gives an illustrative upper limit of 60 days, while Appendix A.4 allows stored personal data to be deleted within 90 days after termination. The standard Advisor selfie itself is stated to be deleted immediately after analysis in Appendix A.5. Get the executed DPA/order to distinguish the transient selfie lifecycle from stored derived/account data and termination deletion.
- Revieve's website privacy policy explicitly says its website policy does not replace the specific client agreement governing an embedded partner experience. The published DPA and overview are not proof that Cirvanna has executed those terms or that they cover the version 0.9 AR SDK.

This makes Revieve a promising partner candidate, not an automatically approved data source. Before choosing its Advisor vs Pro vs AR SDK, obtain a partner-specific integration pack and written confirmation that the published standard-Advisor transient-photo/no-personal-data-training commitments apply to the exact SKU and deployment regions Cirvanna would use.

### Decision: do not activate a Revieve SDK yet

Do not bundle the public SDK script or send Cirvanna photos to it until Revieve supplies:

- Current supported SDK/API versions and a partner-specific technical integration pack.
- Partner ID and signed licence, including redistribution/browser SDK terms.
- Executed DPA/order confirming which exact service (standard Advisor, Pro, or AR SDK) is covered, controller/processor roles, sub-processors, data-region options, retention, deletion and backup handling. Resolve the public DPA's section 10.2 vs Appendix A.4 60/90-day wording.
- Written terms on training, model improvement, reuse, user content rights and whether the provider can retain derived embeddings/face maps.
- Security requirements, CSP domains, SDK integrity/versioning, accessibility and mobile browser support.
- Image processing and child-age restrictions, and whether Revieve's face-tracking stack can run without collecting any identity-linked information.

When authorized, build Revieve as a dedicated client-side adapter with consent before the SDK's initialize/upload call; keep partner credentials and any server secrets out of the browser. Only explicit user-approved skin-tone settings should be passed; the Fitzpatrick input exposed by the old SDK page is not a substitute for an objective or universally valid skin-tone measurement.

## CIL learning and research rules for both providers

- Public marketing pages and announcements are discovery sources, not scientific efficacy evidence.
- A provider's proprietary knowledge, model weights, images, user data or derived signals are not copied into Cirvanna without explicit licence rights.
- Ingredient evidence is not allowed to substantiate finished-product efficacy. A vendor score is scoped to its validated task and population; it is not a medical diagnosis or universal skin truth.
- Provider output must retain source, model/API version, task/configuration, limitations, consent scope, provider licence, expiry and attribution metadata.
- Customer acceptance/rejection and outcome data remain Cirvanna consent-governed data; provider outputs cannot bypass CAL or cause automatic product suppression.
