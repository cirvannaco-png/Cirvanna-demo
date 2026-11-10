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

The documented workflow is:

1. POST /s2s/v2.0/file to request a file ID and presigned upload URL.
2. PUT the image bytes to that URL with the returned content headers. The metadata call alone does not upload the file.
3. POST /s2s/v2.1/task/skin-analysis with src_file_id, dst_actions and format.
4. GET /s2s/v2.1/task/skin-analysis/{task_id} to poll the asynchronous result.
5. POST /s2s/v2.0/task/delete with the task ID to delete the finished task, associated input file and generated output files.

The official V2.1 skin-analysis reference describes a selfie-based assessment with 16 metrics and optional advanced report/product recommendation add-ons. Perfect Corp also describes the `ui_score` as a presentation-oriented score adjusted to be more favorable for consumer psychology; treat `raw_score` as the underlying provider metric and never treat either score as clinical evidence or as a substitute for independent validation. Cirvanna does not enable the vendor product-recommendation add-on: provider suggestions must not bypass Cirvanna Catalog ranking, evidence/rights checks or CAL. Published input constraints include JPEG/PNG, less than 10 MB, a minimum short side of 480 px for SD and 1080 px for HD, and automatic resizing to 2560 px maximum long side. The current V2.1 action schema uses `hd_age_spot` (not `hd_spot`) and `hd_skin_type`; SD and HD actions cannot be mixed. The documented V2.1 task endpoint and task-status endpoint are both `/s2s/v2.1/task/skin-analysis` (POST and GET respectively). V2.1 analysis results are image-based indicators, not clinical measurements, medical diagnosis or medical assessment. Pricing is unit-based and depends on the number of concerns and SD/HD mode; the API Console must be checked before cost-bearing use.

### Cirvanna connector controls

The implementation in services/intelligence-service/app/perfectcorp.py follows the documented File API/task/poll/delete flow and only accepts the documented Perfect Corp API hostname plus presigned upload URLs on the expected S3 acceleration host suffix.

The internal routes are:

- POST /providers/perfectcorp/skin-analysis
- GET /providers/perfectcorp/skin-analysis/{task_id}
- DELETE /providers/perfectcorp/skin-analysis/{task_id}
- POST /providers/perfectcorp/reap-tasks (admin/cron cleanup)

Controls implemented:

- Disabled by default. A valid API token, licence ID, terms URL, retention policy reference and explicit DPA approval flag are required before task creation.
- Adult-only: the signed consent receipt must assert age 18+, a single-subject image, the Perfect Corp provider, the exact image SHA-256 digest and the perfectcorp_skin_analysis purpose.
- User-owned raw bytes are accepted in memory only. The service verifies the actual JPEG/PNG content, corrects EXIF orientation, removes EXIF metadata by re-encoding, and normalizes the image to JPEG before upload.
- No face identity search, matching or recognition endpoint is used. This is a separately consented skin-analysis task, not Click It or Look It.
- No raw image or mask URL is persisted. The durable task ledger stores only provider/task reference, pseudonymous contributor token, image digest, consent expiry and task timestamps/status.
- Polling is contributor-bound. On terminal success/error, the service calls the provider task-deletion API before releasing the result. If deletion cannot be confirmed, it fails closed and does not release the result.
- Consent expiry or withdrawn DPA approval triggers deletion on the next poll. Abandoned tasks require the admin cleanup route to be invoked by a scheduled job; the default TTL is 30 minutes. Keep provider API credentials available for deletion even after disabling new processing.
- Results expose allowlisted numeric metric scores only; detection-mask URLs and other provider URLs are removed.
- Product recommendations from the provider are not treated as CAL approval. Any product display still requires Cirvanna Catalog evidence/rights and CaTaCaCi/CAL.

### Required production evidence

Before turning on CIL_PERFECTCORP_ENABLED=true, record:

- Executed commercial licence and DPA/processing terms covering face-photo handling, purposes, sub-processors, international transfer, data residency, security, incident notification, user deletion requests and model-training/reuse restrictions.
- Confirmed provider retention/deletion behavior for uploaded images, temporary files, task inputs, generated masks and result URLs, including any backup expiry window.
- A verified API key, contractual unit pricing, usage ceilings and budget alerts.
- End-to-end staging evidence for upload, task failure, poll, immediate delete, abandoned-task reaping, consent expiry and revoked approval.
- Security review of the presigned upload host behavior and all returned URL handling.

The connector is code-complete as a gated client/route foundation, not vendor-activated or production-certified.

## Revieve

Official public references:

- [Revieve AR SDK documentation](https://ar-sdk.revieve.com/)
- [Revieve Makeup Artist product page](https://www.revieve.com/solutions/makeup-artist)
- [Revieve Beauty LLM Suite announcement, 13 October 2026](https://www.revieve.com/insider/news/revieve-beauty-llm-suite-specialized-ai-intelligence)
- [Revieve current public news feed with October 2026 deployments](https://www.revieve.com/insider/news)

The publicly accessible AR SDK page identifies version 0.9, requires a partner ID, and shows both React and base-JavaScript usage. Revieve's current public site also reports a 28 October 2026 launch of [SKIN]ALYZE PRO across seven European markets and a 7 October 2026 PT Rohto Laboratories Indonesia deployment; these prove market activity, not API access, performance validation or permission to ingest their data. The SDK accepts a Base64 image or HTML file object; its documented initialize method sends the image to Revieve for analysis before filter methods become available. The public page does not provide a complete current enterprise API contract, a documented server-side upload/task lifecycle, a deletion endpoint or a verifiable data-retention SLA.

Revieve's October 2026 Beauty LLM Suite announcement describes six domains: Skin, Ingredient, Product, Routine, Beauty Lifestyle and Brand Intelligence. This is a useful market/architecture signal for Cirvanna's domain separation, not evidence of an API endpoint, model licence, dataset right or deployable partner integration.

### Decision: do not activate a Revieve SDK yet

Do not bundle the public SDK script or send Cirvanna photos to it until Revieve supplies:

- Current supported SDK/API versions and a partner-specific technical integration pack.
- Partner ID and signed licence, including redistribution/browser SDK terms.
- DPA, controller/processor roles, sub-processors, data-region options, retention and verified deletion API/SLA.
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
