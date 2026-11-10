"""Perfect Corp YouCam AI Skin Analysis V2.1 provider client.

The client implements the documented file-upload -> task-create -> poll -> delete
workflow. It never persists the source image, provider file ID, output masks or
provider URLs. It is disabled unless a DPA/retention review and API credentials
are explicitly configured by an operator.
"""
from __future__ import annotations

import os
from urllib.parse import quote, urlparse

import httpx


class PerfectCorpNotConfigured(RuntimeError):
    pass


class PerfectCorpRequestError(RuntimeError):
    pass


API_BASE_DEFAULT = "https://yce-api-01.makeupar.com"
ALLOWED_API_HOSTS = {"yce-api-01.makeupar.com"}
ALLOWED_UPLOAD_SUFFIX = ".s3-accelerate.amazonaws.com"
MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}
ALLOWED_ACTIONS = {
    "sd": ["wrinkle","droopy_upper_eyelid","droopy_lower_eyelid","firmness","acne","moisture","eye_bag","dark_circle_v2","age_spot","radiance","redness","oiliness","pore","texture","tear_trough","skin_type"],
    "hd": ["hd_redness","hd_oiliness","hd_age_spot","hd_radiance","hd_moisture","hd_dark_circle","hd_eye_bag","hd_droopy_upper_eyelid","hd_droopy_lower_eyelid","hd_firmness","hd_texture","hd_acne","hd_pore","hd_wrinkle","hd_tear_trough","hd_skin_type"],
}


def _settings(*, for_delete: bool = False) -> tuple[str, str]:
    if not for_delete:
        if os.getenv("CIL_PERFECTCORP_ENABLED", "false").lower() != "true":
            raise PerfectCorpNotConfigured("Perfect Corp integration is disabled by default")
        if os.getenv("CIL_PERFECTCORP_DPA_APPROVED", "false").lower() != "true":
            raise PerfectCorpNotConfigured("Perfect Corp DPA/retention review is not approved")
        if not os.getenv("CIL_PERFECTCORP_RETENTION_POLICY_REF", "").strip():
            raise PerfectCorpNotConfigured("Perfect Corp retention policy reference is required")
        if not os.getenv("CIL_PERFECTCORP_LICENCE_ID", "").strip() or not os.getenv("CIL_PERFECTCORP_TERMS_URL", "").strip():
            raise PerfectCorpNotConfigured("Perfect Corp licence ID and terms URL are required")
    token = os.getenv("CIL_PERFECTCORP_API_TOKEN", "").strip()
    base = os.getenv("CIL_PERFECTCORP_API_BASE_URL", API_BASE_DEFAULT).strip().rstrip("/")
    parsed = urlparse(base)
    if not token:
        raise PerfectCorpNotConfigured("Perfect Corp API token is not configured")
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_API_HOSTS or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise PerfectCorpNotConfigured("Perfect Corp API base URL is not an approved HTTPS endpoint")
    return base, token


def _api_json(client: httpx.Client, method: str, base: str, token: str, path: str, payload: dict | None = None) -> dict:
    response = client.request(
        method,
        f"{base}{path}",
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    response.raise_for_status()
    if "application/json" not in response.headers.get("content-type", "").lower():
        raise PerfectCorpRequestError("Perfect Corp response was not JSON")
    body = response.json()
    if not isinstance(body, dict):
        raise PerfectCorpRequestError("Perfect Corp response payload was not an object")
    if body.get("status", 200) not in (200, 201):
        raise PerfectCorpRequestError("Perfect Corp API reported a non-success status")
    return body


def start_skin_analysis(*, image: bytes, file_name: str, content_type: str, actions: list[str], mode: str) -> dict:
    """Upload one consented adult user's image and start a non-diagnostic skin task."""
    base, token = _settings()
    if not image or len(image) >= MAX_IMAGE_BYTES:
        raise ValueError("skin-analysis image must be non-empty and smaller than 10 MB")
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError("only JPEG and PNG images are supported")
    if mode not in ALLOWED_ACTIONS or not actions or len(actions) > 8:
        raise ValueError("skin-analysis mode or action count is invalid")
    if len(actions) != len(set(actions)) or any(action not in ALLOWED_ACTIONS[mode] for action in actions):
        raise ValueError("actions must be unique and belong to the selected SD/HD mode")
    suffix = ".jpg" if content_type == "image/jpeg" else ".png"
    clean_name = os.path.basename(file_name)[:100]
    if not clean_name.lower().endswith(suffix):
        clean_name = f"cirvanna-skin-analysis{suffix}"

    timeout = httpx.Timeout(30.0, connect=5.0)
    with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
        file_response = _api_json(client, "POST", base, token, "/s2s/v2.0/file", {
            "files": [{"content_type": content_type, "file_name": clean_name, "file_size": len(image)}],
        })
        data = file_response.get("data") or {}
        files = data.get("files") or file_response.get("files") or []
        if not isinstance(files, list) or not files or not isinstance(files[0], dict):
            raise PerfectCorpRequestError("Perfect Corp File API omitted file metadata")
        uploaded = files[0]
        file_id = uploaded.get("file_id")
        requests = uploaded.get("requests") or []
        if not isinstance(file_id, str) or not file_id or not requests or not isinstance(requests[0], dict):
            raise PerfectCorpRequestError("Perfect Corp File API omitted file_id or upload request")
        upload = requests[0]
        upload_url = upload.get("url")
        upload_method = str(upload.get("method", "PUT")).upper()
        upload_headers = upload.get("headers") or {}
        parsed_upload = urlparse(str(upload_url or ""))
        if (
            upload_method != "PUT"
            or parsed_upload.scheme != "https"
            or not parsed_upload.hostname
            or not parsed_upload.hostname.endswith(ALLOWED_UPLOAD_SUFFIX)
            or parsed_upload.username or parsed_upload.password
        ):
            raise PerfectCorpRequestError("Perfect Corp returned an unapproved presigned upload target")
        safe_headers = {
            key: value for key, value in upload_headers.items()
            if key.lower() in {"content-type", "content-length"}
        }
        if safe_headers.get("Content-Type") not in {content_type, None}:
            raise PerfectCorpRequestError("Perfect Corp upload content type does not match image")
        content_length = safe_headers.get("Content-Length")
        if content_length is not None and (not str(content_length).isdigit() or int(content_length) != len(image)):
            raise PerfectCorpRequestError("Perfect Corp upload length does not match normalized image")
        put_response = client.put(
            str(upload_url), content=image, headers=safe_headers,
        )
        put_response.raise_for_status()

        task = _api_json(client, "POST", base, token, "/s2s/v2.1/task/skin-analysis", {
            "src_file_id": file_id,
            "dst_actions": actions,
            "format": "json",
        })
    task_data = task.get("data") or {}
    task_id = task_data.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise PerfectCorpRequestError("Perfect Corp task response omitted task_id")
    return {
        "task_id": task_id,
        "status": "running",
        "provider": "perfectcorp_youcam_skin_analysis_v2_1",
        "mode": mode,
        "actions": actions,
        "disclaimer": "Image-based skincare indicators only; not clinical measurements, diagnosis or medical assessment.",
    }


def get_skin_analysis_status(*, task_id: str) -> dict:
    base, token = _settings()
    if not task_id or len(task_id) > 256:
        raise ValueError("invalid task_id")
    with httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0), follow_redirects=False, trust_env=False) as client:
        body = _api_json(client, "GET", base, token, f"/s2s/v2.1/task/skin-analysis/{quote(task_id, safe='')}")
    data = body.get("data") or {}
    status = data.get("task_status") or data.get("status") or "unknown"
    result = {"task_id": task_id, "status": status, "provider": "perfectcorp_youcam_skin_analysis_v2_1"}
    if status == "success":
        results = data.get("results") or {}
        output = results.get("output") if isinstance(results, dict) else None
        metrics = []
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                metric = {"type": item.get("type")}
                for key in ("ui_score", "raw_score"):
                    value = item.get(key)
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        metric[key] = value
                if metric.get("type") and len(metric) > 1:
                    metrics.append(metric)
        elif isinstance(output, dict):
            for metric_name, item in output.items():
                if not isinstance(item, dict):
                    continue
                metric = {"type": str(metric_name)}
                for key in ("ui_score", "raw_score"):
                    value = item.get(key)
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        metric[key] = value
                if len(metric) > 1:
                    metrics.append(metric)
        result["metrics"] = metrics
        result["disclaimer"] = "Image-based skincare indicators only; not clinical measurements, diagnosis or medical assessment."
    elif status == "error":
        result["error_code"] = str(data.get("error_code") or "PROVIDER_TASK_FAILED")[:120]
    return result


def delete_task(*, task_id: str) -> bool:
    # Deletion remains available even after provider processing is disabled or DPA approval is withdrawn.
    base, token = _settings(for_delete=True)
    if not task_id or len(task_id) > 256:
        raise ValueError("invalid task_id")
    with httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0), follow_redirects=False, trust_env=False) as client:
        _api_json(client, "POST", base, token, "/s2s/v2.0/task/delete", {"task_id": task_id})
    return True
