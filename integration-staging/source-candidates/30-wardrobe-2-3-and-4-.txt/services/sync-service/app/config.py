from common.config import settings

SERVICE_NAME = "sync-service"
BATCH_SIZE = settings.sync_batch_size
MAX_RETRIES = settings.sync_max_retries
RETRY_BACKOFF_SECONDS = settings.sync_retry_backoff_seconds
ITEM_SERVICE_URL = settings.item_service_url
