"""
services/embedder.py — Text Embedding Service
===============================================
Generates vector embeddings using sentence-transformers (runs locally).
No API key needed. Runs on CPU in-process on Railway.

Model: all-MiniLM-L6-v2
  - 384-dimensional embeddings
  - ~80MB model size
  - Very fast on CPU (~10ms per embed)
  - Great quality for semantic search
"""

from typing import List

import numpy as np
import structlog

logger = structlog.get_logger()

# Global model singleton — loaded once, reused across all requests
_model = None


def _get_model():
    """Load sentence-transformers model once and cache it in-process."""
    global _model
    if _model is None:
        logger.info("📦 Loading sentence-transformers model (first time only)...")
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("✅ Embedding model loaded (all-MiniLM-L6-v2, 384-dim)")
    return _model


class SentenceTransformerEmbedder:
    """
    Generates text embeddings using sentence-transformers.

    Replaces: Ollama nomic-embed-text (required a separate Ollama server)
    With:     sentence-transformers all-MiniLM-L6-v2 (runs in-process, no server needed)

    Production advantages on Railway:
      - Zero external dependencies — no Ollama server to manage
      - Fast: ~10ms per batch on CPU
      - Small: 384-dim vectors (vs nomic's 768-dim), same quality for RAG
      - Free: model downloads once at Docker build time
    """

    def __init__(self):
        # Pre-load model at startup to avoid cold-start delay on first query
        self._model = _get_model()

    def _embed_sync(self, text: str) -> List[float]:
        """
        Core synchronous embed — used directly or via async wrapper.

        Args:
            text: Input text to embed

        Returns:
            List of 384 floats (normalized embedding vector)
        """
        text = text.strip().replace("\n", " ")
        if not text:
            raise ValueError("Cannot embed empty text")
        embedding = self._model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    async def embed(self, text: str) -> List[float]:
        """
        Async-compatible embed for use in async contexts (retriever, cache).
        sentence-transformers is CPU-bound/sync, so we call it directly.

        Args:
            text: Input text to embed

        Returns:
            List of 384 floats (normalized embedding vector)
        """
        return self._embed_sync(text)

    async def embed_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        Embed multiple texts efficiently using batched inference.

        sentence-transformers natively batches, which is significantly
        faster than calling embed() in a loop.

        Args:
            texts: List of strings to embed
            batch_size: Batch size for inference (32 is optimal for CPU)

        Returns:
            List of embedding vectors, same order as input texts
        """
        if not texts:
            return []

        cleaned = [t.strip().replace("\n", " ") or " " for t in texts]

        logger.info(f"🔢 Embedding {len(texts)} chunks (batch_size={batch_size})...")
        try:
            embeddings = self._model.encode(
                cleaned,
                batch_size=batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            return embeddings.tolist()
        except Exception as e:
            logger.error("Batch embedding failed", error=str(e))
            # Fallback: zero vectors (document still indexed, just won't match well)
            return [[0.0] * 384 for _ in texts]

    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Compute cosine similarity between two embedding vectors.
        Used by the semantic cache to find similar past queries.

        Returns:
            Float between -1.0 and 1.0 (1.0 = identical)
        """
        a = np.array(vec1)
        b = np.array(vec2)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))


# Backward-compatible alias — existing imports of OllamaEmbedder still work
OllamaEmbedder = SentenceTransformerEmbedder
