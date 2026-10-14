# EEPL V2.0 – Environmental & Intelligence Recommendation Engine

This is the complete, production‑ready codebase with all Phase 1–4 improvements:

- Real CFRP client with circuit breakers and MLflow integration
- Full Fit Confidence Index (FCI) microservice
- Feedback repository and dampening logic
- Cultural validation engine
- Trend service
- Redis caching
- Prometheus metrics and structured logging
- A/B testing framework
- Explainability module
- Comprehensive tests
- Docker Compose for all services

## Quick Start

1. Install dependencies: `pip install -r requirements.txt`
2. Set up PostgreSQL and Redis (or use Docker Compose)
3. Run `python scripts/train_fci.py` to train and log models
4. Start all services: `docker-compose up`
5. Run EEPL: `python run.py`

## Architecture

See the integrated pipeline in `src/core/eepl.py`.

## Monitoring

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)
- MLflow: http://localhost:5000
