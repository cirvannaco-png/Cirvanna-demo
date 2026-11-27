"""Low-cardinality, privacy-safe HTTP telemetry for internal scraping.

This module intentionally records only route templates, HTTP methods, status codes
and elapsed time. It never records request bodies, query strings, tokens, user IDs,
asset IDs, image data, or exception messages.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
import threading
import time
import uuid
from collections import defaultdict
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

if TYPE_CHECKING:
    from fastapi import Response

_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
_LOG = logging.getLogger("cirvanna.http")


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


class RequestMetrics:
    """Thread-safe, bounded-cardinality request counter and latency histogram."""

    def __init__(self, service: str) -> None:
        self.service = service
        self._lock = threading.Lock()
        self._counts: dict[tuple[str, str, int], int] = defaultdict(int)
        self._sums: dict[tuple[str, str, int], float] = defaultdict(float)
        self._buckets: dict[tuple[str, str, int], list[int]] = defaultdict(
            lambda: [0 for _ in _BUCKETS]
        )

    def record(self, method: str, route: str, status_code: int, elapsed: float) -> None:
        key = (method, route, status_code)
        with self._lock:
            self._counts[key] += 1
            self._sums[key] += elapsed
            values = self._buckets[key]
            for index, boundary in enumerate(_BUCKETS):
                if elapsed <= boundary:
                    values[index] += 1

    def render(self) -> str:
        with self._lock:
            counts = dict(self._counts)
            sums = dict(self._sums)
            buckets = {key: list(value) for key, value in self._buckets.items()}

        lines = [
            "# HELP http_server_requests_total Total HTTP requests by bounded route template.",
            "# TYPE http_server_requests_total counter",
        ]
        for (method, route, status_code), count in sorted(counts.items()):
            labels = (
                f'service="{_escape_label(self.service)}",'
                f'method="{_escape_label(method)}",'
                f'route="{_escape_label(route)}",'
                f'status_code="{status_code}"'
            )
            lines.append(f"http_server_requests_total{{{labels}}} {count}")

        lines.extend([
            "# HELP http_server_request_duration_seconds HTTP request duration in seconds.",
            "# TYPE http_server_request_duration_seconds histogram",
        ])
        for key in sorted(counts):
            method, route, status_code = key
            base = (
                f'service="{_escape_label(self.service)}",'
                f'method="{_escape_label(method)}",'
                f'route="{_escape_label(route)}",'
                f'status_code="{status_code}"'
            )
            values = buckets.get(key, [0 for _ in _BUCKETS])
            for index, boundary in enumerate(_BUCKETS):
                lines.append(
                    f'http_server_request_duration_seconds_bucket{{{base},le="{boundary:g}"}} {values[index]}'
                )
            lines.append(
                f'http_server_request_duration_seconds_bucket{{{base},le="+Inf"}} {counts[key]}'
            )
            lines.append(
                f"http_server_request_duration_seconds_sum{{{base}}} {sums.get(key, 0.0):.9f}"
            )
            lines.append(
                f"http_server_request_duration_seconds_count{{{base}}} {counts[key]}"
            )
        return "\n".join(lines) + "\n"


def install_observability(app: FastAPI, service: str) -> RequestMetrics:
    """Install structured request logs and a separately authenticated metrics route."""

    metrics = RequestMetrics(service)
    app.state.request_metrics = metrics

    @app.middleware("http")
    async def request_telemetry(request: Request, call_next):
        # Metrics scraping is deliberately excluded to avoid a self-referential series.
        if request.scope.get("path") == "/internal/metrics":
            return await call_next(request)

        request_id = str(uuid.UUID(bytes=secrets.token_bytes(16), version=4))
        started = time.perf_counter()
        status_code = 500
        response = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers.setdefault("X-Request-ID", request_id)
            return response
        finally:
            elapsed = max(0.0, time.perf_counter() - started)
            route_object = request.scope.get("route")
            route = getattr(route_object, "path", None) or "unmatched"
            method = request.method.upper()
            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}:
                method = "OTHER"
            metrics.record(method, route, status_code, elapsed)
            # Do not log full URLs, headers, payloads, exception text or principal data.
            _LOG.info(json.dumps({
                "event": "http_request",
                "service": service,
                "request_id": request_id,
                "method": method,
                "route": route,
                "status_code": status_code,
                "duration_ms": round(elapsed * 1000, 3),
            }, separators=(",", ":"), sort_keys=True))

    @app.get("/internal/metrics", include_in_schema=False)
    def internal_metrics(request: Request) -> PlainTextResponse:
        if os.getenv("METRICS_ENABLED", "false").strip().lower() != "true":
            raise HTTPException(status_code=404, detail={"code": "METRICS_NOT_ENABLED"}, headers={"Cache-Control": "no-store"})
        expected = os.getenv("OBSERVABILITY_METRICS_TOKEN", "").strip()
        if len(expected.encode("utf-8")) < 32:
            raise HTTPException(status_code=404, detail={"code": "METRICS_NOT_CONFIGURED"}, headers={"Cache-Control": "no-store"})
        supplied = request.headers.get("x-observability-token", "")
        if not hmac.compare_digest(supplied, expected):
            raise HTTPException(status_code=401, detail={"code": "METRICS_AUTH_REQUIRED"}, headers={"Cache-Control": "no-store"})
        return PlainTextResponse(
            metrics.render(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
            headers={"Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff"},
        )

    return metrics
