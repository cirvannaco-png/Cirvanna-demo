"""
Fast vector similarity search using FAISS (with NumPy fallback).
"""
import numpy as np

class VectorSimilarityEngine:
    def __init__(self, embedding_dim=256):
        self.embedding_dim = embedding_dim
        self.product_embeddings = None
        self.product_ids = None
        try:
            import faiss
            self.index = faiss.IndexFlatIP(embedding_dim)
            self.use_faiss = True
        except ImportError:
            self.use_faiss = False

    def build_index(self, product_embeddings, product_ids):
        self.product_embeddings = product_embeddings
        self.product_ids = product_ids
        if self.use_faiss and len(product_embeddings) > 100:
            import faiss
            faiss.normalize_L2(product_embeddings)
            self.index.add(product_embeddings)
        else:
            norms = np.linalg.norm(product_embeddings, axis=1, keepdims=True)
            norms[norms == 0] = 1
            self.product_embeddings = product_embeddings / norms

    def search(self, query_embedding, k=10, threshold=0.0):
        if len(self.product_embeddings) == 0:
            return []
        query_norm = np.linalg.norm(query_embedding)
        if query_norm > 0:
            query_embedding = query_embedding / query_norm
        if self.use_faiss and len(self.product_embeddings) > 100:
            import faiss
            query_embedding = query_embedding.reshape(1, -1)
            distances, indices = self.index.search(query_embedding, k)
            results = [
                (self.product_ids[idx], float(dist))
                for dist, idx in zip(distances[0], indices[0])
                if dist > threshold and idx != -1
            ]
        else:
            similarities = np.dot(self.product_embeddings, query_embedding)
            top_indices = np.argpartition(similarities, -k)[-k:]
            top_indices = top_indices[np.argsort(-similarities[top_indices])]
            results = [
                (self.product_ids[idx], float(similarities[idx]))
                for idx in top_indices
                if similarities[idx] > threshold
            ]
        return results
