# Click It independent privacy evaluation tools

## Detector/masking score

Run:

    python tools/click_it_privacy_eval/score.py --csv /secure/evaluator/annotations.csv --policy /secure/evaluator/preregistered-policy.json --report /secure/evaluator/report.json

The annotation CSV contains only evaluator measurements, never image bytes or identifiers. Required fields include per-stratum ground-truth/missed/residual face counts, masking-before-embedding, uncertainty state and whether uncertain output was actually rejected, identity/age-feature call counts, and child-processing/publication outcomes. The scorer reports false-negative rates and 95% Wilson upper bounds by stratum. The policy must be preregistered and requires zero residual unmasked faces, zero identity-feature calls, zero age-estimation calls, fail-closed rejection of uncertain outputs and child-media processing/publication. An uncertain result is safe only when it was rejected and not publicly published. The evaluator must choose sample floors and FNR confidence thresholds before seeing the data. This tool is not a detector and cannot independently certify the model.

## Photographed-person report/removal intake

Run against a deployed staging BFF with a pre-provisioned synthetic asset reference:

    python tools/click_it_privacy_eval/rights_smoke.py --config /secure/path/rights-staging.json --report /secure/evidence/rights-report.json

The config must specify environment=staging, an HTTPS bff_base_url, a synthetic asset_reference, and at least one urgent report plus one removal request. The runner calls the public BFF intake, requires urgent quarantine confirmation, then retrieves each private status exactly once using the one-time status token. It never prints or stores that token.

A successful run proves intake and quarantine/status behavior only. It does not prove requester authority, reviewer decision, deletion completion, or propagation across source, derivatives, replicas, backups, CDN, merchant surfaces and shared links. Those require separate provider receipts and independent probes.

## Current operational status

- Click It public BFF upload remains blocked before multipart parsing.
- The Vision Docker build pins BlazeFace full-range SHA-256 3698b18f063835bc609069ef052228fbe86d9c9a6dc8dcb7c7c2d69aed2b181b; this is an integrity pin and smoke test, not independent recall evidence.
- No independent annotated evaluation dataset/report is present.
- Privacy Governance requires live jurisdiction, Content Lifecycle, guardian-verification and requester-authority providers; code mocks are not production evidence.
- No Cirvanna Render service is currently deployed in the connected workspaces, so no deployed staging rights run is claimed.
