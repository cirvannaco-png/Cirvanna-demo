from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICES = (
    "marketplace-bff",
    "commerce-service",
    "privacy-governance-service",
    "api-gateway",
)


def test_critical_services_install_the_shared_observability_contract():
    for service in SERVICES:
        source = ROOT / "services" / service / "app" / "main.py"
        module = ROOT / "services" / service / "app" / "observability.py"
        text = source.read_text(encoding="utf-8")
        module_text = module.read_text(encoding="utf-8")
        ast.parse(text, filename=str(source))
        ast.parse(module_text, filename=str(module))
        assert "from app.observability import install_observability" in text
        expected_call = "install_observability(app, SERVICE_NAME)" if service == "api-gateway" else "install_observability(app, SERVICE)"
        assert expected_call in text
        assert '"/internal/metrics"' in module_text


def test_http_telemetry_excludes_high_risk_request_content():
    module = (ROOT / "services" / "marketplace-bff" / "app" / "observability.py").read_text(encoding="utf-8")
    assert "request.body" not in module
    assert "request.url" not in module
    assert "request.query_params" not in module
    assert '"user_id"' not in module
    assert '"asset_id"' not in module
    assert "OBSERVABILITY_METRICS_TOKEN" in module
    assert "http_server_request_duration_seconds_bucket" in module
