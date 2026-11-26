#!/usr/bin/env python3
"""Run the unified Cirvanna CAL adversarial matrix against deployed staging services.

This runner deliberately requires an explicit environment-specific manifest. It
never fabricates service URLs, credentials, fixtures, or a successful provider
state. A staging fixture-control API must create/revoke real test records before
the shopper routes are exercised.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

REQUIRED_SURFACES = {
    "marketplace", "pnelly", "wardrobe", "look_it", "click_it",
    "saved_products", "comparison", "cart", "checkout", "daily_looks",
}
REQUIRED_SCENARIOS = {
    "mapped_approved", "unmapped_candidate", "merchant_suspended",
    "stale_offer", "merchant_disconnected", "consent_session_revoked",
    "cache_after_revocation", "payment_revoked_race",
}
SECRET_KEY_PATTERN = re.compile(r"(token|secret|password|authorization|api[_-]?key)", re.I)
ENV_PATTERN = re.compile(r"^\$\{([A-Z][A-Z0-9_]*)\}$")
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class MatrixError(RuntimeError):
    pass


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: Any
    elapsed_ms: int


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        match = ENV_PATTERN.match(value)
        if match:
            env_name = match.group(1)
            result = os.getenv(env_name, "")
            if not result:
                raise MatrixError(f"required environment variable {env_name} is not configured")
            return result
        return value
    if isinstance(value, list):
        return [_expand(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand(item) for key, item in value.items()}
    return value


def _redact(value: Any, key: str = "") -> Any:
    if SECRET_KEY_PATTERN.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {k: _redact(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _json_path(document: Any, path: str) -> Any:
    """Resolve $.a.b[0].c and wildcard collection paths such as $.items[*].image_url."""
    if not path.startswith("$."):
        raise MatrixError(f"JSON assertion path must start with '$.': {path}")
    parsed_parts = []
    for part in path[2:].split("."):
        match = re.fullmatch(r"([A-Za-z0-9_-]+)(?:\[(\d+|\*)\])?", part)
        if not match:
            raise MatrixError(f"unsupported JSON assertion path: {path}")
        parsed_parts.append(match.groups())
    current: Any = document
    for key, index in parsed_parts:
        if isinstance(current, list):
            values = [item[key] for item in current if isinstance(item, dict) and key in item]
            if not values:
                return []
            current = values
        else:
            if not isinstance(current, dict) or key not in current:
                return _MISSING
            current = current[key]
        if index == "*":
            if not isinstance(current, list):
                return _MISSING
            continue
        if index is not None:
            if not isinstance(current, list) or int(index) >= len(current):
                return _MISSING
            current = current[int(index)]
    return current


_MISSING = object()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward bearer credentials or fixture data to a redirect target.
        return None


def _http(request_spec: dict[str, Any], timeout: int) -> Response:
    method = str(request_spec.get("method", "GET")).upper()
    url = str(request_spec["url"])
    headers = {str(k): str(v) for k, v in request_spec.get("headers", {}).items()}
    token_env = request_spec.get("token_env")
    if token_env:
        token = os.getenv(token_env, "")
        if len(token.encode("utf-8")) < 32:
            raise MatrixError(f"{token_env} must be configured with at least 32 bytes")
        headers["Authorization"] = f"Bearer {token}"
    body = request_spec.get("body")
    data = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
    if data is not None:
        headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    started = time.monotonic()
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            status = response.status
            response_headers = {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        raw = exc.read(MAX_RESPONSE_BYTES + 1)
        status = exc.code
        response_headers = {k.lower(): v for k, v in exc.headers.items()}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise MatrixError(f"{method} {url} transport failure: {type(exc).__name__}") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise MatrixError(f"{method} {url} response exceeded the {MAX_RESPONSE_BYTES}-byte safety limit")
    elapsed = int((time.monotonic() - started) * 1000)
    try:
        parsed = json.loads(raw.decode("utf-8")) if raw else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        parsed = None
    return Response(status, response_headers, parsed, elapsed)



def _safe_http(request_spec: dict[str, Any], timeout: int, label: str, failures: list[str]) -> Response | None:
    try:
        return _http(request_spec, timeout)
    except MatrixError:
        failures.append(f"{label}: staging transport failed")
        return None


def _render(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        for name, replacement in variables.items():
            value = value.replace("{{" + name + "}}", str(replacement))
        return value
    if isinstance(value, list):
        return [_render(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: _render(item, variables) for key, item in value.items()}
    return value


def _assert_response(response: Response, assertion: dict[str, Any], label: str) -> list[str]:
    failures: list[str] = []
    expected = assertion.get("status", [200])
    if isinstance(expected, int):
        expected = [expected]
    if response.status not in expected:
        failures.append(f"{label}: HTTP {response.status}, expected one of {expected}")
    if assertion.get("require_no_store"):
        cache_control = response.headers.get("cache-control", "").lower()
        if "no-store" not in cache_control:
            failures.append(f"{label}: response lacks Cache-Control no-store")
    if assertion.get("require_json") and response.body is None:
        failures.append(f"{label}: expected a JSON response")
    for path, expected_value in assertion.get("json_equals", {}).items():
        actual = _json_path(response.body, path)
        if actual != expected_value:
            failures.append(f"{label}: {path} was {_redact(actual)!r}, expected {_redact(expected_value)!r}")
    for path in assertion.get("json_present", []):
        if _json_path(response.body, path) is _MISSING:
            failures.append(f"{label}: required field {path} is absent")
    for path in assertion.get("json_absent", []):
        actual = _json_path(response.body, path)
        if actual is not _MISSING and actual not in ([], None):
            failures.append(f"{label}: forbidden field {path} is present")
    for path in assertion.get("json_one_of", []):
        actual = _json_path(response.body, path["path"])
        if actual not in path["values"]:
            failures.append(f"{label}: {path['path']} value {_redact(actual)!r} not in allowed set")
    return failures


def _validate_assertion(assertion: Any, label: str) -> None:
    if not isinstance(assertion, dict):
        raise MatrixError(f"{label}: assertion must be an object")
    allowed = {"status", "require_no_store", "require_json", "json_equals", "json_present", "json_absent", "json_one_of"}
    unknown = set(assertion) - allowed
    if unknown:
        raise MatrixError(f"{label}: unsupported assertion keys: {sorted(unknown)}")
    status = assertion.get("status", [200])
    if isinstance(status, int):
        status = [status]
    if not isinstance(status, list) or not status or any(
        not isinstance(code, int) or isinstance(code, bool) or not 100 <= code <= 599 for code in status
    ):
        raise MatrixError(f"{label}: status must be an HTTP status or a non-empty list of HTTP statuses")
    for flag in ("require_no_store", "require_json"):
        if flag in assertion and not isinstance(assertion[flag], bool):
            raise MatrixError(f"{label}: {flag} must be boolean")
    equals = assertion.get("json_equals", {})
    if not isinstance(equals, dict):
        raise MatrixError(f"{label}: json_equals must be an object")
    for path in equals:
        _json_path({}, path)
    for key in ("json_present", "json_absent"):
        paths = assertion.get(key, [])
        if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
            raise MatrixError(f"{label}: {key} must be a list of JSONPath strings")
        for path in paths:
            _json_path({}, path)
    choices = assertion.get("json_one_of", [])
    if not isinstance(choices, list):
        raise MatrixError(f"{label}: json_one_of must be a list")
    for choice in choices:
        if not isinstance(choice, dict) or set(choice) != {"path", "values"}:
            raise MatrixError(f"{label}: each json_one_of item requires exactly path and values")
        if not isinstance(choice["path"], str) or not isinstance(choice["values"], list) or not choice["values"]:
            raise MatrixError(f"{label}: json_one_of path and values are invalid")
        _json_path({}, choice["path"])


def validate_manifest(config: dict[str, Any]) -> None:
    if config.get("environment") != "staging":
        raise MatrixError("refusing to run: manifest environment must be exactly 'staging'")
    control = config.get("fixture_control")
    if not isinstance(control, dict) or not control.get("url") or not control.get("token_env"):
        raise MatrixError("fixture_control.url and fixture_control.token_env are required")
    control_url = urlsplit(str(control["url"]))
    if control_url.scheme != "https" or control_url.username or control_url.password:
        raise MatrixError("fixture_control.url must be trusted HTTPS without embedded credentials")
    scenarios = config.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise MatrixError("scenarios must be a non-empty list")
    if any(not isinstance(item, dict) for item in scenarios):
        raise MatrixError("every scenario must be an object")
    if any(not isinstance(item.get("id"), str) for item in scenarios):
        raise MatrixError("every scenario must have a string ID")
    scenario_ids = {item.get("id") for item in scenarios}
    if len(scenario_ids) != len(scenarios):
        raise MatrixError("scenario IDs must be unique")
    missing_scenarios = REQUIRED_SCENARIOS - scenario_ids
    if missing_scenarios:
        raise MatrixError("missing required adversarial scenarios: " + ", ".join(sorted(missing_scenarios)))
    surfaces = config.get("surfaces")
    if not isinstance(surfaces, dict):
        raise MatrixError("surfaces must be an object")
    missing_surfaces = REQUIRED_SURFACES - set(surfaces)
    extra_surfaces = set(surfaces) - REQUIRED_SURFACES
    if missing_surfaces or extra_surfaces:
        raise MatrixError(
            "shopper surfaces must be exactly the required ten; "
            f"missing={sorted(missing_surfaces)}, extra={sorted(extra_surfaces)}"
        )
    for surface, spec in surfaces.items():
        if not isinstance(spec, dict) or not spec.get("url") or not spec.get("method"):
            raise MatrixError(f"surface {surface} requires url and method")
        parsed_url = urlsplit(str(spec["url"]))
        if parsed_url.scheme != "https" or parsed_url.username or parsed_url.password:
            raise MatrixError(f"surface {surface} URL must be trusted HTTPS without embedded credentials")
    for scenario in scenarios:
        if not isinstance(scenario.get("id"), str) or scenario["id"] not in REQUIRED_SCENARIOS:
            raise MatrixError("scenario has an unknown or missing adversarial ID")
        if not isinstance(scenario.get("fixture", {}), dict):
            raise MatrixError(f"scenario {scenario['id']} fixture must be an object")
        exercise_surfaces = scenario.get("exercise_surfaces")
        if not isinstance(exercise_surfaces, list) or any(not isinstance(name, str) for name in exercise_surfaces):
            raise MatrixError(f"scenario {scenario['id']} exercise_surfaces must be a list of surface names")
        required = set(exercise_surfaces)
        if required != REQUIRED_SURFACES:
            raise MatrixError(
                f"scenario {scenario.get('id')} must exercise every surface; "
                f"missing={sorted(REQUIRED_SURFACES-required)}, extra={sorted(required-REQUIRED_SURFACES)}"
            )
        assertions = scenario.get("assertions", {})
        if set(assertions) != REQUIRED_SURFACES:
            raise MatrixError(f"scenario {scenario.get('id')} must define assertions for every shopper surface")
        for surface, assertion in assertions.items():
            _validate_assertion(assertion, f"scenario {scenario.get('id')} / {surface}")
            if not any(assertion.get(key) for key in ("json_equals", "json_one_of", "json_absent", "json_present")):
                raise MatrixError(
                    f"scenario {scenario.get('id')} assertion for {surface} "
                    "must verify response semantics, not status alone"
                )
        if scenario.get("id") in {"consent_session_revoked", "cache_after_revocation", "payment_revoked_race"}:
            if scenario.get("recheck_after_revoke") is not True:
                raise MatrixError(f"scenario {scenario.get('id')} must recheck all surfaces after revocation")
            post_assertions = scenario.get("post_revoke_assertions")
            if not isinstance(post_assertions, dict) or set(post_assertions) != REQUIRED_SURFACES:
                raise MatrixError(
                    f"scenario {scenario.get('id')} must define explicit post-revocation assertions for every surface"
                )
            for surface, assertion in post_assertions.items():
                _validate_assertion(assertion, f"scenario {scenario.get('id')} post-revoke / {surface}")
                if not any(assertion.get(key) for key in ("json_equals", "json_one_of", "json_absent")):
                    raise MatrixError(
                        f"scenario {scenario.get('id')} post-revocation assertion for {surface} "
                        "must verify response semantics, not status alone"
                    )
        if scenario.get("id") == "cache_after_revocation" and not scenario.get("revoke"):
            raise MatrixError("cache_after_revocation requires a sequential revoke step")
        if scenario.get("revoke"):
            if not isinstance(scenario["revoke"], dict):
                raise MatrixError(f"scenario {scenario.get('id')} revoke must be an object")
            revoke_url = urlsplit(str(scenario["revoke"].get("url", "")))
            if revoke_url.scheme != "https" or revoke_url.username or revoke_url.password or not scenario["revoke"].get("token_env"):
                raise MatrixError(f"scenario {scenario.get('id')} revoke must use HTTPS and a dedicated token_env")
        if scenario.get("recheck_after_revoke") is True:
            post_assertions = scenario.get("post_revoke_assertions")
            if not isinstance(post_assertions, dict) or set(post_assertions) != REQUIRED_SURFACES:
                raise MatrixError(
                    f"scenario {scenario.get('id')} must define post_revoke_assertions for every shopper surface"
                )
            for surface, assertion in post_assertions.items():
                if not isinstance(assertion, dict) or assertion.get("require_no_store") is not True:
                    raise MatrixError(
                        f"scenario {scenario.get('id')} post-revoke {surface} must require Cache-Control no-store"
                    )
                forbidden_paths = set(assertion.get("json_absent", []))
                allowed_denial_statuses = assertion.get("status", [200])
                if isinstance(allowed_denial_statuses, int):
                    allowed_denial_statuses = [allowed_denial_statuses]
                if not forbidden_paths.intersection({
                    "$.products[*].id", "$.items[*].product_id", "$.offers[*].id", "$.recommendations[*].id"
                }) and not set(allowed_denial_statuses) <= {401, 403, 410}:
                    raise MatrixError(
                        f"scenario {scenario.get('id')} post-revoke {surface} must deny access or assert product payload absence"
                    )
        if scenario.get("id") in {"consent_session_revoked", "payment_revoked_race"}:
            race = scenario.get("race")
            if not isinstance(race, dict) or not isinstance(race.get("revoke"), dict):
                raise MatrixError(f"scenario {scenario.get('id')} requires a race object with revocation")
            if not isinstance(race.get("surfaces"), list) or not race["surfaces"] or any(
                not isinstance(name, str) for name in race["surfaces"]
            ):
                raise MatrixError(f"scenario {scenario.get('id')} race surfaces must be a non-empty list")
            if not set(race["surfaces"]).issubset(REQUIRED_SURFACES):
                raise MatrixError(f"scenario {scenario.get('id')} race references an unknown shopper surface")
            race_assertions = scenario.get("race_assertions")
            if not isinstance(race_assertions, dict) or set(race_assertions) != set(race["surfaces"]):
                raise MatrixError(
                    f"scenario {scenario.get('id')} must define explicit race assertions for every raced surface"
                )
            for surface, assertion in race_assertions.items():
                _validate_assertion(assertion, f"scenario {scenario.get('id')} race / {surface}")
                if not any(assertion.get(key) for key in ("json_equals", "json_one_of", "json_absent")):
                    raise MatrixError(
                        f"scenario {scenario.get('id')} race assertion for {surface} "
                        "must verify authorization outcome, not status alone"
                    )
            if scenario.get("revoke") and scenario["revoke"] != race["revoke"]:
                raise MatrixError(
                    f"scenario {scenario.get('id')} sequential and concurrent revocation definitions must match"
                )
            race_url = urlsplit(str(race["revoke"].get("url", "")))
            if race_url.scheme != "https" or race_url.username or race_url.password or not race["revoke"].get("token_env"):
                raise MatrixError(f"scenario {scenario.get('id')} race revocation must use HTTPS and a dedicated token_env")


def run(config: dict[str, Any], timeout: int = 20) -> int:
    validate_manifest(config)
    control = config["fixture_control"]
    control_token = os.getenv(control["token_env"], "")
    if len(control_token.encode("utf-8")) < 32:
        raise MatrixError(f"{control['token_env']} must be configured with at least 32 bytes")
    failures: list[str] = []
    results: list[dict[str, Any]] = []
    for scenario in config["scenarios"]:
        scenario_id = scenario["id"]
        fixture_url = control["url"].rstrip("/") + "/v1/scenarios/" + scenario_id + "/activate"
        fixture_request = {
            "url": fixture_url,
            "method": "POST",
            "headers": {"Authorization": "Bearer " + control_token},
            "body": scenario.get("fixture", {}),
        }
        activated = _safe_http(fixture_request, timeout, f"{scenario_id}/fixture-activate", failures)
        if activated is None:
            continue
        if activated.status not in (200, 201):
            failures.append(f"{scenario_id}: fixture activation failed with HTTP {activated.status}")
            continue
        fixture_id = (activated.body or {}).get("fixture_id") if isinstance(activated.body, dict) else None
        request_id = (activated.body or {}).get("request_id") if isinstance(activated.body, dict) else None
        if not isinstance(fixture_id, str) or not fixture_id or not isinstance(request_id, str) or not request_id:
            failures.append(f"{scenario_id}: fixture controller omitted fixture_id or request_id; teardown cannot be safely addressed")
            continue
        variables = {
            "scenario_id": scenario_id,
            "fixture_id": fixture_id,
            "request_id": request_id,
        }
        for surface in sorted(REQUIRED_SURFACES):
            spec = _render(config["surfaces"][surface], variables)
            request_spec = {
                "url": spec["url"],
                "method": spec["method"],
                "headers": spec.get("headers", {}),
                "token_env": spec.get("token_env"),
                "body": spec.get("body"),
            }
            label = f"{scenario_id}/{surface}"
            response = _safe_http(request_spec, timeout, label, failures)
            if response is None:
                continue
            assertion = scenario.get("assertions", {}).get(surface, spec.get("assertions", {}))
            surface_failures = _assert_response(response, assertion, label)
            failures.extend(surface_failures)
            results.append({
                "scenario": scenario_id,
                "surface": surface,
                "status": response.status,
                "elapsed_ms": response.elapsed_ms,
                "cache_control": response.headers.get("cache-control"),
                "failures": len(surface_failures),
            })
        # Race active shopper requests against a real revocation, then replay every surface.
        race = scenario.get("race")
        revoke_result = None
        revoke_spec = None
        revoke_attempted = False
        if race:
            revoke_spec = _render(race["revoke"], variables)
            race_jobs = {}
            with ThreadPoolExecutor(max_workers=len(race["surfaces"]) + 1) as executor:
                revoke_attempted = True
                revoke_future = executor.submit(_http, {
                    "url": revoke_spec["url"], "method": revoke_spec.get("method", "POST"),
                    "headers": revoke_spec.get("headers", {}), "token_env": revoke_spec.get("token_env"),
                    "body": revoke_spec.get("body"),
                }, timeout)
                for surface in race["surfaces"]:
                    spec = _render(config["surfaces"][surface], variables)
                    race_jobs[surface] = executor.submit(_http, {
                        "url": spec["url"], "method": spec["method"],
                        "headers": spec.get("headers", {}), "token_env": spec.get("token_env"),
                        "body": spec.get("body"),
                    }, timeout)
                try:
                    revoke_result = revoke_future.result()
                except MatrixError:
                    failures.append(f"{scenario_id}/race-revoke: staging transport failed")
                for surface, future in race_jobs.items():
                    try:
                        response = future.result()
                    except MatrixError:
                        failures.append(f"{scenario_id}/race/{surface}: staging transport failed")
                        continue
                    assertion = scenario["race_assertions"][surface]
                    label = f"{scenario_id}/race/{surface}"
                    surface_failures = _assert_response(response, assertion, label)
                    failures.extend(surface_failures)
                    results.append({
                        "scenario": scenario_id + "/race",
                        "surface": surface,
                        "status": response.status,
                        "elapsed_ms": response.elapsed_ms,
                        "cache_control": response.headers.get("cache-control"),
                        "failures": len(surface_failures),
                    })
        # Revoke while the fixture is live, then repeat the shopper requests to
        # detect stale browser/API/CDN state after the authoritative mutation.
        revoke = scenario.get("revoke") or (race.get("revoke") if race else None)
        if revoke:
            revoke_spec = revoke_spec or _render(revoke, variables)
            if revoke_result is None and not revoke_attempted:
                revoke_attempted = True
                revoke_result = _safe_http({
                    "url": revoke_spec["url"], "method": revoke_spec.get("method", "POST"),
                    "headers": revoke_spec.get("headers", {}), "token_env": revoke_spec.get("token_env"),
                    "body": revoke_spec.get("body"),
                }, timeout, f"{scenario_id}/revoke", failures)
            if revoke_result is None:
                pass
            elif revoke_result.status not in revoke_spec.get("accepted_status", [200, 204]):
                failures.append(f"{scenario_id}: revocation step returned HTTP {revoke_result.status}")
            elif scenario.get("recheck_after_revoke", False):
                for surface in sorted(REQUIRED_SURFACES):
                    spec = _render(config["surfaces"][surface], variables)
                    label = f"{scenario_id}/post-revoke/{surface}"
                    response = _safe_http({
                        "url": spec["url"], "method": spec["method"],
                        "headers": spec.get("headers", {}), "token_env": spec.get("token_env"),
                        "body": spec.get("body"),
                    }, timeout, label, failures)
                    if response is None:
                        continue
                    assertion = scenario["post_revoke_assertions"][surface]
                    surface_failures = _assert_response(response, assertion, label)
                    failures.extend(surface_failures)
                    results.append({
                        "scenario": scenario_id + "/post-revoke",
                        "surface": surface,
                        "status": response.status,
                        "elapsed_ms": response.elapsed_ms,
                        "cache_control": response.headers.get("cache-control"),
                        "failures": len(surface_failures),
                    })
        # Teardown must be explicit and provider-confirmed by the fixture control plane.
        deactivated = _safe_http({
            "url": control["url"].rstrip("/") + "/v1/scenarios/" + scenario_id + "/deactivate",
            "method": "POST",
            "headers": {"Authorization": "Bearer " + control_token},
            "body": {"fixture_id": variables["fixture_id"]},
        }, timeout, f"{scenario_id}/fixture-deactivate", failures)
        if deactivated is None:
            failures.append(f"{scenario_id}: fixture teardown not confirmed")
        elif deactivated.status not in (200, 204):
            failures.append(f"{scenario_id}: fixture teardown not confirmed (HTTP {deactivated.status})")
    report = {
        "schema_version": 1,
        "environment": "staging",
        "scenario_count": len(config["scenarios"]),
        "surface_count": len(REQUIRED_SURFACES),
        "request_count": len(results),
        "passed": not failures,
        "results": results,
        "failures": failures,
    }
    output = Path(config.get("report_path", "cal-staging-matrix-report.json"))
    output.write_text(json.dumps(_redact(report), indent=2) + "\n", encoding="utf-8")
    print(json.dumps(_redact(report), indent=2))
    return 0 if not failures else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="environment-specific staging manifest JSON")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()
    try:
        raw = json.loads(Path(args.config).read_text(encoding="utf-8"))
        config = _expand(raw)
        return run(config, timeout=max(1, min(args.timeout, 120)))
    except (OSError, json.JSONDecodeError, MatrixError, KeyError, TypeError) as exc:
        print(f"CAL staging matrix blocked: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
