"""
services/embedder.py — Text Embedding Service
===============================================
Generates vector embeddings using Ollama's nomic-embed-text model.
Runs completely locally — no OpenAI API, no cost, no data leaves your server.

nomic-embed-text produces 768-dimensional embeddings.
"""

from typing import List

import httpx
import numpy as np
import structlog

from config import get_settings

settings = get_settings()
logger = structlog.get_logger()


class OllamaEmbedder:
    """
    Generates text embeddings using Ollama's local embedding model.
    
    Replaces: OpenAI text-embedding-3-small ($0.02/M tokens) with
              Ollama nomic-embed-text (FREE, runs locally)
    """

    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_embed_model

    async def embed(self, text: str) -> List[float]:
        """
        Embed a single text string.
        
        Args:
            text: Input text to embed
            
        Returns:
            List of floats (768-dimensional vector)
        """
        text = text.strip().replace("\n", " ")
        if not text:
            raise ValueError("Cannot embed empty text")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
            )
            response.raise_for_status()
            return response.json()["embedding"]

    async def embed_batch(self, texts: List[str], batch_size: int = 20) -> List[List[float]]:
        """
        Embed multiple texts efficiently by batching requests.
        
        Ollama processes one at a time, so we batch to show progress
        and handle errors gracefully.
        
        Args:
            texts: List of strings to embed
            batch_size: How many to process per batch (for logging)
            
        Returns:
            List of embedding vectors, same order as input texts
        """
        embeddings = []
        total = len(texts)

        for i in range(0, total, batch_size):
            batch = texts[i : i + batch_size]
            logger.info(f"Embedding batch {i // batch_size + 1}", progress=f"{min(i+batch_size, total)}/{total}")

            for text in batch:
                try:
                    embedding = await self.embed(text)
                    embeddings.append(embedding)
                except Exception as e:
                    logger.error("Embedding failed for text", error=str(e), text_preview=text[:50])
                    # Use a zero vector as fallback (document will still be indexed, just won't match well)
                    embeddings.append([0.0] * 768)

        return embeddings

    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Compute cosine similarity between two embedding vectors.
        Used by the semantic cache to find similar past queries.
        
        Returns:
            Float between -1.0 and 1.0 (1.0 = identical)
        """
        a = np.array(vec1)
        b = np.array(vec2)
        if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
            return 0.0
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
