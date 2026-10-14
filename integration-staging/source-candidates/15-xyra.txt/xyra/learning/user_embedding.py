"""
User embedding management and online learning.
"""
import numpy as np
import torch
import torch.nn as nn
from ..connection_pool import SecureConnectionPool

class UserEmbeddingUpdater:
    def __init__(self, config):
        self.config = config
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        # Simple GRU-based updater (placeholder)
        self.gru = nn.GRUCell(config.USER_EMBEDDING_DIM, config.USER_EMBEDDING_DIM).to(self.device)
        # In production, load pre-trained weights.

    async def update_from_interaction(self, user_id: str, query_embedding: np.ndarray,
                                      response_embedding: np.ndarray, feedback: int):
        """
        Update user embedding based on interaction and explicit feedback.
        This would be called asynchronously after a response.
        """
        pool = await SecureConnectionPool.get_instance()
        async with pool.get_redis() as redis_pool:
            cached = await redis_pool.get(f"user_embedding:{user_id}")
            if cached:
                user_emb = np.frombuffer(cached, dtype=np.float32)
            else:
                # Fetch from DB or create new
                user_emb = np.random.randn(self.config.USER_EMBEDDING_DIM).astype(np.float32)
                user_emb = user_emb / np.linalg.norm(user_emb)

        # Convert to torch tensors
        user_t = torch.from_numpy(user_emb).float().to(self.device).unsqueeze(0)
        query_t = torch.from_numpy(query_embedding).float().to(self.device).unsqueeze(0)
        # Combine (simplified – in reality would use more sophisticated model)
        combined = (user_t + query_t) / 2
        updated = self.gru(combined.squeeze(0), user_t.squeeze(0))
        updated_np = updated.cpu().numpy()

        # Normalise
        updated_np = updated_np / np.linalg.norm(updated_np)

        # Store back
        async with pool.get_redis() as redis_pool:
            await redis_pool.setex(f"user_embedding:{user_id}", 3600, updated_np.tobytes())

        # Also update DB asynchronously (could be a background task)
        # For simplicity, we'll not block.

    async def update_from_feedback(self, user_id: str, interaction_id: str, rating: int):
        """
        Simplified update based on feedback.
        """
        # In a real system, you'd retrieve the interaction details and adjust embedding.
        pass
