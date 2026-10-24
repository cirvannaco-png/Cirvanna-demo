# Cognitive orchestration (PAMASMMA-derived)

This service boundary adapts the ten PAMASMMA cognitive domains for Cirvanna. It is an orchestration boundary, not a second decision core. CaTaCaCi/CAL remains authoritative for user-facing product suitability and policy arbitration.

## Domains
- S1 executive operations — implemented as severity-based incident triage only
- S2 marketing intelligence — unavailable until a real handler is implemented
- S3 relationship management — implemented as declared-category support routing only
- S4 narrative governance — implemented as explicit required-term preflight only
- S5 creator economy — unavailable until a real handler is implemented
- S6 audience psychology — unavailable until privacy/fairness evaluation and a real handler exist
- S7 behavioral consistency — unavailable until consent-aware implementation exists
- S8 persuasion governance — implemented as a limited deterministic lexical preflight, never a policy certification
- S9 voice presence — unavailable until a real handler is implemented
- S10 strategic narrative — unavailable until a real handler is implemented

## Safety contract
Unconfigured domains fail closed. No fixed example decisions or fabricated quality/confidence scores are emitted. These handlers do not make purchase-suitability decisions; those remain with CaTaCaCi/CAL. The S8 preflight is not a legal review or proof of ethical compliance; all campaign content requires human review and is never published by this service.

Handlers only produce bounded recommendations/findings. They do not send messages, publish campaigns, remediate incidents, infer sensitive identity traits, or override consent, hard user constraints, NPL, cultural requirements, or CAL.

## Integration status
Four narrow deterministic handlers and an explicit startup registry bootstrap exist. They are not exposed as HTTP endpoints or deployed as a service yet. Production integration requires API authentication, bounded execution, audit events, monitoring, real domain implementations, privacy/fairness tests and a reviewed autonomy policy.
