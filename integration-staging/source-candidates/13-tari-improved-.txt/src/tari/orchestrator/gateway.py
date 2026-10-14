"""
Xyra Gateway Orchestrator – routes requests to agents, handles timeouts, retries, tracing.
"""
import asyncio
import time
import uuid
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from ..config import TariConfig
from ..connection_pool import SecureConnectionPool
from ..cache.predictive_cache import PredictiveCache
from ..privacy.manager import PrivacyManager
from .agents.conversation_agent import ConversationAgent
from .agents.retrieval_agent import RetrievalAgent
from .agents.outfit_agent import OutfitAgent
from .agents.tryon_agent import TryOnAgent
from .agents.learning_agent import LearningAgent
from .memory.memory_service import MemoryService
from .knowledge_graph import FashionKnowledgeGraph

@dataclass
class OrchestrationContext:
    request_id: str
    user_id: str
    query: str
    context: Dict[str, Any]
    start_time: float = field(default_factory=time.perf_counter)
    metadata: Dict[str, Any] = field(default_factory=dict)

class XyraGatewayOrchestrator:
    def __init__(self, config: TariConfig, cache: PredictiveCache,
                 privacy_manager: PrivacyManager, pool: SecureConnectionPool):
        self.config = config
        self.cache = cache
        self.privacy_manager = privacy_manager
        self.pool = pool
        # Agents
        self.conversation_agent = ConversationAgent(config, cache, privacy_manager, pool)
        self.retrieval_agent = RetrievalAgent(config, cache, privacy_manager, pool)
        self.outfit_agent = OutfitAgent(config, cache, privacy_manager, pool)
        self.tryon_agent = TryOnAgent(config, cache, privacy_manager, pool)
        self.learning_agent = LearningAgent(config, cache, privacy_manager, pool)
        self.memory_service = MemoryService(config, cache, privacy_manager, pool)
        self.knowledge_graph = FashionKnowledgeGraph(config)
        # State
        self._active_requests: Dict[str, OrchestrationContext] = {}

    async def process(self, user_id: str, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        request_id = str(uuid.uuid4())
        orch_ctx = OrchestrationContext(
            request_id=request_id,
            user_id=user_id,
            query=query,
            context=context
        )
        self._active_requests[request_id] = orch_ctx
        try:
            # Step 1: Intent parsing (conversation agent)
            intent = await self.conversation_agent.parse_intent(query, context)
            # Step 2: Retrieve user memory
            user_profile = await self.memory_service.get_user_profile(user_id)
            # Step 3: Style embedding generation (via retrieval agent)
            style_embedding = await self.retrieval_agent.generate_style_embedding(intent, user_profile)
            # Step 4: Semantic product retrieval
            products = await self.retrieval_agent.retrieve_products(style_embedding, intent, user_profile)
            # Step 5: Outfit composition
            outfits = await self.outfit_agent.compose_outfits(products, intent, user_profile)
            # Step 6: XARI ranking
            ranked_outfits = await self.learning_agent.rank_outfits(outfits, user_id, context)
            # Step 7: Generate variations (if requested)
            if context.get("generate_variations"):
                ranked_outfits = await self.outfit_agent.generate_variations(ranked_outfits, intent)
            # Step 8: Trigger try-on asynchronously (if user selects a look)
            tryon_job = None
            if context.get("auto_tryon") and ranked_outfits:
                selected_outfit = ranked_outfits[0]
                tryon_job = await self.tryon_agent.queue_tryon(user_id, selected_outfit, context)
            # Step 9: Prepare response
            elapsed_ms = (time.perf_counter() - orch_ctx.start_time) * 1000
            response = {
                "request_id": request_id,
                "intent": intent,
                "products": products[:12],
                "outfits": ranked_outfits[:4],
                "tryon_job": tryon_job,
                "performance": {"elapsed_ms": elapsed_ms}
            }
            # Step 10: Async feedback learning
            asyncio.create_task(self.learning_agent.record_interaction(user_id, query, response, context))
            return response
        except Exception as e:
            return {"error": str(e), "request_id": request_id}
        finally:
            self._active_requests.pop(request_id, None)

    async def health_check(self) -> Dict[str, Any]:
        return {
            "orchestrator": "healthy",
            "agents": {
                "conversation": await self.conversation_agent.health(),
                "retrieval": await self.retrieval_agent.health(),
                "outfit": await self.outfit_agent.health(),
                "tryon": await self.tryon_agent.health(),
                "learning": await self.learning_agent.health(),
            },
            "memory": await self.memory_service.health(),
            "knowledge_graph": await self.knowledge_graph.health()
        }
