from common.config import settings

SERVICE_NAME = "api-gateway"

ROUTES = {
    "item": settings.item_service_url,
    "graph": settings.graph_service_url,
    "recommendation": settings.recommendation_service_url,
    "perception": settings.perception_service_url,
    "sync": settings.sync_service_url,
}

# Per-endpoint + per-IP rate limits (requests, window_seconds)
ENDPOINT_LIMITS: dict[str, tuple[int, int]] = {
    "/item/items/": (60, 60),
    "/item/items": (60, 60),
    "/recommendation/suggestions/": (200, 60),
    "/perception/analyze": (10, 60),
    "/sync/offline/": (500, 60),
    "/sync/replay/": (10, 60),
}

DEFAULT_LIMIT = (300, 60)

CB_FAILURE_THRESHOLD = settings.cb_failure_threshold
CB_RECOVERY_TIMEOUT = settings.cb_recovery_timeout_seconds
CB_INITIAL_RATIO = settings.cb_initial_traffic_ratio
