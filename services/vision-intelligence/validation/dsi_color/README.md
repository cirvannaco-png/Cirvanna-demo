# DSI colour validation harness

This is an offline evaluation tool, not a live inference service. It evaluates candidate DSI skin-colour preview outputs against independent spectrophotometer measurements. It does not accept or store raw images, videos, face templates, names, account identifiers or direct subject identifiers.

## Dataset protocol

Keep the evaluation dataset in access-controlled storage outside Git and the application container. Each JSONL row represents one capture/region comparison and contains:
- a stable HMAC-SHA256 subject pseudonym for repeatability and subject-clustered confidence intervals;
- device/camera, operating-system and lighting slice metadata;
- exact skin-model, segmentation-model and chart-profile hashes;
- independent CIE Lab D50 reference values, instrument model, calibration-certificate reference, measurement geometry and uncertainty;
- DSI estimates or sanitized inference failure codes;
- chart-fit diagnostics for completed predictions.

The signed manifest binds the exact sample JSONL file through `samples_sha256`. The manifest also cites dataset rights, per-purpose consent, training-overlap audit and independent ground-truth protocol. The evaluator rejects mismatched manifest/sample hashes, records from another dataset version, mixed model/segmenter/chart/instrument versions, duplicate capture-region records and malformed provenance digests.

The evaluator accepts only pseudonymous subject references matching `hmac-sha256:<64 lowercase hex characters>`. Never use names, emails, account IDs or unhashed identifiers. Raw media fields are forbidden by the schema.

## Cryptographic evidence

Both manifest and release policy require detached Ed25519 signatures. The verifier checks the signature over the exact file bytes and verifies the public key's DER SubjectPublicKeyInfo SHA-256 against an out-of-band environment pin:
- `DSI_EVALUATION_TRUSTED_MANIFEST_PUBLIC_KEY_SHA256`
- `DSI_EVALUATION_TRUSTED_POLICY_PUBLIC_KEY_SHA256`

Keep the private signing keys offline or in a separately controlled approval service. The public PEM files and detached 64-byte signatures are supplied to the CLI. A caller-supplied public key is not trusted unless its fingerprint matches the environment pin. Missing pins, invalid keys, changed input bytes or invalid signatures abort the run.

Example key-generation workflow (run in a controlled offline approval environment):
```bash
openssl genpkey -algorithm ED25519 -out manifest-signing-private.pem
openssl pkey -in manifest-signing-private.pem -pubout -out manifest-signing-public.pem
openssl pkey -pubin -in manifest-signing-public.pem -outform DER | sha256sum

openssl genpkey -algorithm ED25519 -out policy-signing-private.pem
openssl pkey -in policy-signing-private.pem -pubout -out policy-signing-public.pem
openssl pkey -pubin -in policy-signing-public.pem -outform DER | sha256sum

openssl pkeyutl -sign -rawin -inkey manifest-signing-private.pem -in dataset-manifest.json -out dataset-manifest.sig
openssl pkeyutl -sign -rawin -inkey policy-signing-private.pem -in release-policy.json -out release-policy.sig
```

Provision the resulting public-key fingerprints through the evaluation environment's secret/configuration manager, separately from files supplied by the evaluator operator. Never commit private keys, real signatures, sample data or trust pins.

## Run

From `services/vision-intelligence`, install `requirements-test.txt` and set both out-of-band SHA-256 trust pins. Then run:

```bash
python -m validation.dsi_color.cli \
  --manifest /secure/evaluation/dataset-manifest.json \
  --manifest-signature /secure/evaluation/dataset-manifest.sig \
  --manifest-public-key /secure/evaluation/manifest-signing-public.pem \
  --samples /secure/evaluation/samples.jsonl \
  --policy /secure/evaluation/release-policy.json \
  --policy-signature /secure/evaluation/release-policy.sig \
  --policy-public-key /secure/evaluation/policy-signing-public.pem \
  --output /secure/evaluation/reports/dsi-colour-report.json
```

Use the example manifest, sample row and policy as schema templates only. Replace all placeholders with independently approved evidence. The manifest's `samples_sha256` must equal the SHA-256 of the exact JSONL bytes before the manifest is signed.

Exit codes: 0 = PASS, 1 = FAIL, 2 = invalid or untrusted evidence, 3 = REVIEW_REQUIRED.

## Metrics and slices

The report includes:
- CIEDE2000 median, mean, p95 and maximum against independent Lab D50 references;
- signed and absolute mean L*, a* and b* bias;
- inference failure rate and chart-fit p95;
- reference-instrument uncertainty distribution;
- repeat-capture pairwise colour variation grouped by pseudonymous subject, region, camera and lighting;
- metrics sliced by face/body region, camera model, lighting profile, reference L* bin, operating-system family, chart condition and measurement geometry;
- subject-clustered bootstrap 95% confidence intervals for median and p95 colour error.

Repeat-capture variation is descriptive repeatability, not instrument uncertainty. The independent instrument uncertainty is reported separately. Subject pseudonyms are used internally for clustering and never exported in the report.

## Release decision

The example policy intentionally contains null thresholds and no approval references. It must produce `REVIEW_REQUIRED`, never `PASS`.

A release PASS requires:
1. Valid detached Ed25519 signatures for the exact manifest and release-policy bytes, validated against out-of-band pinned public-key fingerprints.
2. A signed held-out dataset manifest whose sample digest matches the exact JSONL bytes.
3. Rights/consent provenance, training-overlap audit and independent ground-truth protocol references.
4. One exact skin model, segmentation model, chart profile, reference instrument and measurement geometry per evaluation.
5. Complete, signed acceptance thresholds for subject/sample counts, failure rate, ΔE2000, axis bias, repeatability and chart-fit error.
6. Both face/body regions and required lighting slices with sufficient sample counts.
7. No sufficiently powered camera, lighting, region, lightness, OS, chart-condition or measurement-geometry slice may breach the accepted aggregate error/bias limits.
8. Approval timestamp no later than the signed evaluation manifest creation timestamp, plus independent review reference.

Cirvanna's independent measurement/validation reviewers must determine the thresholds; this repository does not invent universal ΔE limits or sample counts. Missing or underpowered evidence yields `REVIEW_REQUIRED`; configured threshold violations yield `FAIL`.

A PASS applies only to the exact hashed model, segmentation model, chart profile, dataset, policy and protocol. This tool does not train, recalibrate or deploy models, ingest raw media, change Vision/DermalSight readiness or authorize shade ranking. Synthetic tests validate computation only; real release evidence requires consented captures and independently calibrated spectrophotometer ground truth across cameras, lighting, regions and measured skin-colour ranges.
