from common.config import settings

SERVICE_NAME = "recommendation-service"
GRAPH_SERVICE_URL = settings.graph_service_url
ITEM_SERVICE_URL = settings.item_service_url
QDRANT_URL = settings.qdrant_url
QDRANT_COLLECTION = settings.qdrant_collection
QDRANT_VECTOR_SIZE = settings.qdrant_vector_size
SUGGESTION_CACHE_TTL = 300
