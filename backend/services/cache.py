"""
services/cache.py — Semantic Cache
=====================================
Caches chatbot responses by semantic similarity — not just exact matches.
If a user asks "How do I reset my password?" and someone already asked
"What are the steps to change my password?", we return the cached answer.

Implementation:
  - In-memory TTLCache for speed
  - Embeddings stored for semantic similarity lookup
  - No Redis needed for small-medium scale

Replaces: AWS ElastiCache Redis ($50+/month) with cachetools (FREE)
"""

import json
import time
from typing import Dict, List, Optional

import structlog
from cachetools import TTLCache

from config import get_settings
from services.embedder import OllamaEmbedder

settings = get_settings()
logger = structlog.get_logger()


class SemanticCache:
    """
    Semantic cache that returns cached responses for similar queries.
    
    A cache hit saves:
    - ~2-40 seconds of LLM inference time
    - Compute resources on the free VM
    
    Uses cosine similarity between query embeddings to find matches.
    """

    def __init__(self):
        self._embedder = OllamaEmbedder()
        # TTLCache: max 1000 entries, expire after 1 hour
        self._cache: TTLCache = TTLCache(
            maxsize=1000,
            ttl=settings.cache_ttl_seconds,
        )
        # Store embeddings separately (same TTL managed via timestamp)
        self._embeddings: Dict[str, List[float]] = {}
        self._timestamps: Dict[str, float] = {}

    async def get(self, query: str, corpus: str = "public") -> Optional[Dict]:
        """
        Look up a cached response for the given query.
        
        Returns the cached response dict if a similar query is found,
        or None if no cache hit.
        """
        if not settings.enable_semantic_cache:
            return None

        try:
            query_embedding = await self._embedder.embed(query)
        except Exception:
            return None  # Cache miss on embedding failure

        best_key = None
        best_similarity = 0.0

        now = time.time()
        expired_keys = []

        for key, cached_embedding in self._embeddings.items():
            # Check if expired
            timestamp = self._timestamps.get(key, 0)
            if now - timestamp > settings.cache_ttl_seconds:
                expired_keys.append(key)
                continue

            # Compute similarity
            similarity = self._embedder.cosine_similarity(query_embedding, cached_embedding)
            if similarity > best_similarity:
                best_similarity = similarity
                best_key = key

        # Clean up expired entries
        for key in expired_keys:
            self._embeddings.pop(key, None)
            self._timestamps.pop(key, None)
            self._cache.pop(key, None)

        if best_similarity >= settings.cache_similarity_threshold and best_key in self._cache:
            logger.info(
                "💾 Semantic cache hit",
                similarity=round(best_similarity, 3),
                threshold=settings.cache_similarity_threshold,
            )
            return self._cache[best_key]

        return None

    async def set(
        self,
        query: str,
        response: str,
        sources: List[Dict],
        corpus: str = "public",
    ):
        """Store a query-response pair in the semantic cache."""
        if not settings.enable_semantic_cache:
            return

        try:
            query_embedding = await self._embedder.embed(query)
        except Exception:
            return  # Don't crash if caching fails

        # Use a hash of the query as the cache key
        import hashlib
        key = hashlib.md5(f"{corpus}:{query}".encode()).hexdigest()

        self._cache[key] = {
            "query": query,
            "response": response,
            "sources": sources,
            "corpus": corpus,
        }
        self._embeddings[key] = query_embedding
        self._timestamps[key] = time.time()

    def invalidate_corpus(self, corpus: str):
        """
        Invalidate all cache entries for a specific corpus.
        Called when new documents are added to that corpus.
        """
        keys_to_delete = [
            key for key, value in self._cache.items()
            if isinstance(value, dict) and value.get("corpus") == corpus
        ]
        for key in keys_to_delete:
            self._cache.pop(key, None)
            self._embeddings.pop(key, None)
            self._timestamps.pop(key, None)

        logger.info(f"🗑️  Cache invalidated for corpus '{corpus}', removed {len(keys_to_delete)} entries")

    def stats(self) -> Dict:
        """Return cache statistics for the monitoring dashboard."""
        return {
            "size": len(self._cache),
            "maxsize": self._cache.maxsize,
            "ttl_seconds": self._cache.ttl,
            "fill_pct": round(len(self._cache) / self._cache.maxsize * 100, 1),
        }
