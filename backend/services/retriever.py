"""
services/retriever.py — Hybrid Retrieval (ChromaDB + BM25)
===========================================================
Implements hybrid search:
  1. Dense retrieval: vector similarity via ChromaDB (nomic-embed-text)
  2. Sparse retrieval: BM25 keyword matching (rank-bm25 library)
  3. Reciprocal Rank Fusion (RRF) to merge both result lists

This is the same technique used by production RAG systems (e.g., Azure AI Search).
Running it for FREE with ChromaDB + rank-bm25.
"""

from typing import Dict, List, Optional

import chromadb
import structlog
from rank_bm25 import BM25Okapi

from config import get_settings
from services.embedder import OllamaEmbedder

settings = get_settings()
logger = structlog.get_logger()


class HybridRetriever:
    """
    Hybrid retrieval combining vector search (ChromaDB) with BM25 keyword search.
    
    Replaces: Pinecone ($70+/month) with ChromaDB (FREE, on-disk)
    Replaces: Elasticsearch with rank-bm25 (FREE, pure Python)
    """

    def __init__(self):
        # ChromaDB persistent client (stores vectors on disk)
        self._chroma_client = chromadb.PersistentClient(
            path=f"{settings.data_dir}/chroma"
        )
        self._embedder = OllamaEmbedder()
        # Cache of BM25 indexes per corpus (rebuilt on new document ingestion)
        self._bm25_indexes: Dict[str, tuple] = {}

    def _get_collection(self, corpus: str):
        """
        Get (or create) a ChromaDB collection for the given corpus.
        Each corpus (e.g. 'public', 'engineering') is a separate collection.
        """
        collection_name = f"{settings.chroma_collection_prefix}_{corpus}"
        return self._chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},   # Use cosine similarity
        )

    async def retrieve(
        self,
        query: str,
        corpus: str = "public",
        top_k: int = 20,
        permission_filter: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Retrieve relevant chunks using hybrid search (vector + BM25).
        
        Args:
            query: User's question
            corpus: Which knowledge base to search
            top_k: Number of chunks to retrieve (before reranking)
            permission_filter: List of permissions the user has
            
        Returns:
            List of chunk dicts with 'text', 'source', 'score', 'metadata'
        """
        collection = self._get_collection(corpus)
        doc_count = collection.count()

        if doc_count == 0:
            logger.warning("⚠️  No documents in corpus", corpus=corpus)
            return []

        actual_top_k = min(top_k, doc_count)

        # ── Dense Retrieval (Vector Search) ──────────────
        query_embedding = await self._embedder.embed(query)
        vector_results = collection.query(
            query_embeddings=[query_embedding],
            n_results=actual_top_k,
            include=["documents", "metadatas", "distances"],
        )

        vector_chunks = []
        if vector_results and vector_results["documents"]:
            for i, (doc, meta, dist) in enumerate(zip(
                vector_results["documents"][0],
                vector_results["metadatas"][0],
                vector_results["distances"][0],
            )):
                # Convert distance to similarity score (ChromaDB cosine returns distance 0-2)
                similarity = 1 - (dist / 2)
                vector_chunks.append({
                    "text": doc,
                    "source": meta.get("source", "Unknown"),
                    "doc_id": meta.get("doc_id", ""),
                    "chunk_id": meta.get("chunk_id", ""),
                    "required_permissions": meta.get("required_permissions", "public"),
                    "vector_score": similarity,
                    "vector_rank": i + 1,
                })

        # ── Sparse Retrieval (BM25 Keyword Search) ────────
        bm25_chunks = self._bm25_search(query, corpus, top_k=actual_top_k)

        # ── Reciprocal Rank Fusion (RRF) Merge ────────────
        merged = self._reciprocal_rank_fusion(vector_chunks, bm25_chunks, k=60)

        # ── Permission Filter ─────────────────────────────
        if permission_filter:
            user_perms = set(permission_filter)
            merged = [
                chunk for chunk in merged
                if any(p in user_perms for p in chunk["required_permissions"].split(","))
            ]

        return merged[:top_k]

    def _bm25_search(self, query: str, corpus: str, top_k: int) -> List[Dict]:
        """
        BM25 keyword search over the corpus.
        BM25 index is built lazily and cached in memory.
        """
        if corpus not in self._bm25_indexes:
            self._rebuild_bm25_index(corpus)

        if corpus not in self._bm25_indexes:
            return []

        corpus_docs, tokenized_corpus = self._bm25_indexes[corpus]
        if not tokenized_corpus:
            return []

        bm25 = BM25Okapi(tokenized_corpus)
        query_tokens = query.lower().split()
        scores = bm25.get_scores(query_tokens)

        # Get top-k by score
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

        results = []
        for rank, idx in enumerate(top_indices):
            if scores[idx] > 0:
                chunk = corpus_docs[idx].copy()
                chunk["bm25_score"] = float(scores[idx])
                chunk["bm25_rank"] = rank + 1
                results.append(chunk)

        return results

    def _rebuild_bm25_index(self, corpus: str):
        """Fetch all documents from ChromaDB and build a BM25 index."""
        try:
            collection = self._get_collection(corpus)
            if collection.count() == 0:
                return

            all_docs = collection.get(include=["documents", "metadatas"])
            docs = []
            tokenized = []

            for doc, meta in zip(all_docs["documents"], all_docs["metadatas"]):
                chunk = {
                    "text": doc,
                    "source": meta.get("source", "Unknown"),
                    "doc_id": meta.get("doc_id", ""),
                    "chunk_id": meta.get("chunk_id", ""),
                    "required_permissions": meta.get("required_permissions", "public"),
                }
                docs.append(chunk)
                tokenized.append(doc.lower().split())

            self._bm25_indexes[corpus] = (docs, tokenized)
            logger.info(f"🔍 BM25 index built", corpus=corpus, documents=len(docs))

        except Exception as e:
            logger.error("Failed to build BM25 index", corpus=corpus, error=str(e))

    def _reciprocal_rank_fusion(
        self,
        vector_results: List[Dict],
        bm25_results: List[Dict],
        k: int = 60,
    ) -> List[Dict]:
        """
        Merge vector and BM25 results using Reciprocal Rank Fusion.
        
        RRF score = Σ 1/(k + rank_i)
        This is a parameter-free, robust way to combine two ranked lists.
        """
        rrf_scores: Dict[str, float] = {}
        chunk_map: Dict[str, Dict] = {}

        for rank, chunk in enumerate(vector_results):
            key = chunk.get("chunk_id") or f"{chunk['source']}_{chunk['text'][:50]}"
            rrf_scores[key] = rrf_scores.get(key, 0) + 1 / (k + rank + 1)
            chunk_map[key] = chunk

        for rank, chunk in enumerate(bm25_results):
            key = chunk.get("chunk_id") or f"{chunk['source']}_{chunk['text'][:50]}"
            rrf_scores[key] = rrf_scores.get(key, 0) + 1 / (k + rank + 1)
            if key not in chunk_map:
                chunk_map[key] = chunk

        # Sort by RRF score descending
        sorted_keys = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)

        results = []
        for key in sorted_keys:
            chunk = chunk_map[key].copy()
            chunk["rrf_score"] = rrf_scores[key]
            results.append(chunk)

        return results

    def add_to_index(self, chunks: List[Dict], corpus: str):
        """
        Add new chunks to ChromaDB and invalidate BM25 cache.
        Called by the ingestion pipeline.
        """
        collection = self._get_collection(corpus)

        ids = [c["chunk_id"] for c in chunks]
        documents = [c["text"] for c in chunks]
        embeddings = [c["embedding"] for c in chunks]
        metadatas = [
            {
                "source": c["source"],
                "doc_id": c["doc_id"],
                "chunk_id": c["chunk_id"],
                "required_permissions": c.get("required_permissions", "public"),
            }
            for c in chunks
        ]

        # Upsert (insert or update if chunk_id already exists)
        collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        # Invalidate BM25 cache so it's rebuilt on next search
        self._bm25_indexes.pop(corpus, None)

        logger.info("✅ Chunks indexed in ChromaDB", count=len(chunks), corpus=corpus)

    def delete_document(self, doc_id: str, corpus: str):
        """Remove all chunks belonging to a document from ChromaDB."""
        collection = self._get_collection(corpus)
        collection.delete(where={"doc_id": doc_id})
        self._bm25_indexes.pop(corpus, None)
