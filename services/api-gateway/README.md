# API gateway

**Owner:** Request boundary and API composition. **Status:** scaffold only.

Own authentication/authorization, request validation at the edge, rate limits, correlation IDs and service routing. It must not duplicate domain policy or query other services' databases. Production deployment is blocked until API contracts, threat model, secret handling and integration tests exist.