"""Background consumer for Wardrobe's durable asset-deletion outbox.

Only calls the configured internal asset service at a fixed path. Deletion is
idempotent; 404 is accepted as already deleted. The worker never fetches URLs
stored in wardrobe data or logs asset/user identifiers.
"""
from __future__ import annotations
import logging
import os
import re
import time
from urllib.parse import urlsplit
import httpx
from app.store import WardrobeDeletionQueue, engine_for_url

logger = logging.getLogger("wardrobe.deletion_worker")
ASSET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
WORKER_ID = os.getenv("WARDROBE_DELETION_WORKER_ID", "wardrobe-deletion-worker")[:128]

def trusted_base_url(value: str) -> bool:
    try:
        parts = urlsplit(value.strip())
        host = (parts.hostname or "").lower()
        local = host in {"localhost", "127.0.0.1", "::1"}
        return bool(
            host and parts.username is None and parts.password is None
            and not parts.query and not parts.fragment
            and (parts.scheme == "https" or (parts.scheme == "http" and local))
        )
    except ValueError:
        return False

def worker_config() -> tuple[str, str, str]:
    database_url = os.getenv("WARDROBE_DATABASE_URL", "").strip()
    asset_base = os.getenv("WARDROBE_ASSET_SERVICE_URL", "").strip().rstrip("/")
    token = os.getenv("WARDROBE_ASSET_SERVICE_TOKEN", "")
    if not database_url.startswith("postgresql+psycopg://"):
        raise RuntimeError("WARDROBE_DATABASE_URL must target PostgreSQL")
    if not trusted_base_url(asset_base):
        raise RuntimeError("WARDROBE_ASSET_SERVICE_URL must be a trusted HTTPS base URL")
    if len(token.encode("utf-8")) < 32:
        raise RuntimeError("WARDROBE_ASSET_SERVICE_TOKEN is not configured")
    return database_url, asset_base, token

def process_once(*, http_client_factory=httpx.Client) -> str:
    database_url, asset_base, token = worker_config()
    queue = WardrobeDeletionQueue(engine_for_url(database_url))
    queue.heartbeat(WORKER_ID)
    job = queue.claim(worker_id=WORKER_ID)
    if job is None:
        return "idle"
    if not ASSET_ID.fullmatch(job.asset_id):
        queue.retry(job, error_code="ASSET_ID_INVALID")
        return "retry_scheduled"
    try:
        with http_client_factory(timeout=httpx.Timeout(5.0, connect=1.5), follow_redirects=False) as client:
            response = client.delete(
                f"{asset_base}/v1/assets/{job.asset_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": job.command_id,
                    "X-Asset-Owner-ID": job.owner_user_id,
                },
            )
        if 200 <= response.status_code < 300 or response.status_code == 404:
            if queue.complete(job):
                return "completed"
            return "lease_lost"
        code = f"ASSET_SERVICE_HTTP_{response.status_code}"
    except httpx.TimeoutException:
        code = "ASSET_SERVICE_TIMEOUT"
    except httpx.HTTPError:
        code = "ASSET_SERVICE_CONNECTION_ERROR"
    except Exception:
        code = "ASSET_SERVICE_UNEXPECTED_ERROR"
    outcome = queue.retry(job, error_code=code)
    logger.warning("Wardrobe asset deletion attempt ended with state=%s code=%s", outcome, code)
    return outcome

def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    poll_seconds = max(1.0, min(float(os.getenv("WARDROBE_DELETION_POLL_SECONDS", "3")), 60.0))
    while True:
        try:
            outcome = process_once()
            if outcome == "idle":
                time.sleep(poll_seconds)
        except Exception as exc:
            # Do not print credentials, connection URLs or provider response bodies.
            logger.error("Wardrobe deletion worker is not configured/available: %s", type(exc).__name__)
            time.sleep(poll_seconds)

if __name__ == "__main__":
    main()
