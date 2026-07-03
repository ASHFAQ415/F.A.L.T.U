"""
services/reranker.py — Cross-Encoder Reranker
================================================
Reranks retrieved chunks using a cross-encoder model.
Runs 100% locally via sentence-transformers — no Cohere API needed.

Why rerank?
  - Vector search is fast but not perfectly accurate
  - The cross-encoder reads query + chunk together for better scoring
  - Dramatically improves answer relevance (especially for edge cases)

Model: cross-encoder/ms-marco-MiniLM-L-6-v2
  - 22M parameters, fast on CPU
  - Trained on MS MARCO (passage ranking benchmark)
  - Excellent performance for Q&A retrieval tasks
"""

from typing import Dict, List

import structlog
from sentence_transformers import CrossEncoder

from config import get_settings

settings = get_settings()
logger = structlog.get_logger()


class CrossEncoderReranker:
    """
    Reranks retrieved chunks using a local cross-encoder model.
    
    Replaces: Cohere Rerank API (~$1/1000 calls) with
              sentence-transformers CrossEncoder (FREE, runs locally)
    """

    def __init__(self):
        logger.info("🔄 Loading cross-encoder reranker model...")
        self._model = CrossEncoder(
            "cross-encoder/ms-marco-MiniLM-L-6-v2",
            max_length=512,
            # device="cpu" is the default — works on Oracle Cloud free tier
        )
        logger.info("✅ Reranker model loaded")

    def rerank(
        self,
        query: str,
        chunks: List[Dict],
        top_k: int = 5,
    ) -> List[Dict]:
        """
        Rerank a list of retrieved chunks using the cross-encoder.
        
        Args:
            query: The user's question
            chunks: List of chunk dicts from the retriever (with 'text' key)
            top_k: How many top chunks to return after reranking
            
        Returns:
            Top-k chunks sorted by reranker score (highest first)
        """
        if not chunks:
            return []

        if not settings.enable_reranking:
            return chunks[:top_k]

        # Create (query, passage) pairs for the cross-encoder
        pairs = [(query, chunk["text"]) for chunk in chunks]

        try:
            # Score all pairs at once (batch inference)
            scores = self._model.predict(pairs, show_progress_bar=False)

            # Attach scores and sort
            for chunk, score in zip(chunks, scores):
                chunk["rerank_score"] = float(score)

            reranked = sorted(chunks, key=lambda c: c["rerank_score"], reverse=True)

            logger.info(
                "🎯 Reranking complete",
                input_count=len(chunks),
                output_count=min(top_k, len(reranked)),
                top_score=round(reranked[0]["rerank_score"], 3) if reranked else 0,
            )

            return reranked[:top_k]

        except Exception as e:
            logger.error("Reranking failed, returning original order", error=str(e))
            return chunks[:top_k]
