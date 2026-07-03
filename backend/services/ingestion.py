"""
services/ingestion.py — Document Ingestion Pipeline
======================================================
Handles the full ingestion pipeline:
  1. Parse document (PDF / DOCX / MD / TXT)
  2. Semantic chunking (400 tokens, 60 token overlap)
  3. Generate embeddings (Ollama nomic-embed-text)
  4. Index in ChromaDB (vector DB)

Runs in the background after a file upload.
Also called by the daily APScheduler job for re-indexing.
"""

import hashlib
import uuid
from pathlib import Path
from typing import Dict, List

import structlog

from config import get_settings
from services.embedder import OllamaEmbedder
from services.retriever import HybridRetriever

settings = get_settings()
logger = structlog.get_logger()


class IngestionService:
    """
    Full document ingestion pipeline.
    Parses → Chunks → Embeds → Indexes.
    All free and local.
    """

    def __init__(self):
        self._embedder = OllamaEmbedder()
        self._retriever = HybridRetriever()

    async def ingest_file(
        self,
        file_path: str,
        doc_id: str,
        source: str,
        corpus: str = "public",
        required_permissions: str = "public",
    ) -> int:
        """
        Full pipeline for a single file.
        
        Args:
            file_path: Path to the saved file on disk
            doc_id: Unique identifier for this document (from SQLite)
            source: Human-readable source name (original filename)
            corpus: Which ChromaDB collection to add to
            required_permissions: Who can access this document
            
        Returns:
            Number of chunks ingested
        """
        path = Path(file_path)
        file_type = path.suffix.lower().lstrip(".")

        # ── Step 1: Extract text ──────────────────────────
        logger.info("📄 Extracting text", file=source, type=file_type)
        text = self._extract_text(path, file_type)

        if not text.strip():
            raise ValueError(f"No text could be extracted from {source}")

        # ── Step 2: Chunk ─────────────────────────────────
        logger.info("✂️  Chunking document", file=source, text_length=len(text))
        chunks = self._chunk_text(text, doc_id=doc_id, source=source)
        logger.info(f"   Created {len(chunks)} chunks")

        # ── Step 3: Embed ─────────────────────────────────
        logger.info("🔢 Embedding chunks", count=len(chunks))
        texts = [c["text"] for c in chunks]
        embeddings = await self._embedder.embed_batch(texts, batch_size=10)

        for chunk, embedding in zip(chunks, embeddings):
            chunk["embedding"] = embedding
            chunk["required_permissions"] = required_permissions

        # ── Step 4: Index in ChromaDB ─────────────────────
        logger.info("📥 Indexing in ChromaDB", corpus=corpus)
        self._retriever.add_to_index(chunks, corpus=corpus)

        return len(chunks)

    def _extract_text(self, path: Path, file_type: str) -> str:
        """
        Extract raw text from different file types.
        Uses free, open-source libraries:
        - PDF: PyMuPDF (fitz)
        - DOCX: python-docx
        - MD/TXT: read directly
        """
        if file_type == "pdf":
            return self._extract_pdf(path)
        elif file_type == "docx":
            return self._extract_docx(path)
        elif file_type in ("md", "markdown"):
            return self._extract_markdown(path)
        elif file_type == "txt":
            return path.read_text(encoding="utf-8", errors="ignore")
        else:
            raise ValueError(f"Unsupported file type: {file_type}")

    def _extract_pdf(self, path: Path) -> str:
        """Extract text from PDF using PyMuPDF (fast and accurate)."""
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(str(path))
            text_parts = []
            for page in doc:
                text_parts.append(page.get_text())
            doc.close()
            return "\n\n".join(text_parts)
        except Exception as e:
            raise RuntimeError(f"PDF extraction failed: {e}")

    def _extract_docx(self, path: Path) -> str:
        """Extract text from Word .docx files."""
        try:
            from docx import Document
            doc = Document(str(path))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n\n".join(paragraphs)
        except Exception as e:
            raise RuntimeError(f"DOCX extraction failed: {e}")

    def _extract_markdown(self, path: Path) -> str:
        """Read Markdown file and strip HTML tags for clean text."""
        import re
        import markdown
        raw = path.read_text(encoding="utf-8", errors="ignore")
        # Convert markdown to plain text (remove formatting)
        html = markdown.markdown(raw)
        clean = re.sub(r"<[^>]+>", " ", html)  # Strip HTML tags
        return clean

    def _chunk_text(
        self,
        text: str,
        doc_id: str,
        source: str,
        chunk_size: int = None,
        overlap: int = None,
    ) -> List[Dict]:
        """
        Split text into overlapping chunks for retrieval.
        
        Strategy: paragraph-aware chunking
        - Splits on double newlines (paragraph boundaries) first
        - Combines small paragraphs until reaching chunk_size
        - Adds overlap between chunks for context continuity
        
        Args:
            text: Full document text
            doc_id: Document identifier
            source: Human-readable source name
            chunk_size: Target tokens per chunk (default from settings)
            overlap: Overlap tokens between chunks (default from settings)
            
        Returns:
            List of chunk dicts ready for embedding
        """
        chunk_size = chunk_size or settings.chunk_size
        overlap = overlap or settings.chunk_overlap

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks = []
        current_chunk = []
        current_tokens = 0

        def approx_tokens(text: str) -> int:
            """Approximate token count (1 token ≈ 4 chars)."""
            return len(text) // 4

        for para in paragraphs:
            para_tokens = approx_tokens(para)

            # If a single paragraph is too long, split it further
            if para_tokens > chunk_size:
                words = para.split()
                sub_chunk = []
                sub_tokens = 0
                for word in words:
                    sub_chunk.append(word)
                    sub_tokens += 1
                    if sub_tokens >= chunk_size:
                        chunks.append(self._make_chunk(
                            " ".join(sub_chunk), doc_id, source, len(chunks)
                        ))
                        # Overlap: keep last `overlap` words
                        sub_chunk = sub_chunk[-overlap:]
                        sub_tokens = len(sub_chunk)
                if sub_chunk:
                    current_chunk = [" ".join(sub_chunk)]
                    current_tokens = sub_tokens
                continue

            if current_tokens + para_tokens > chunk_size and current_chunk:
                # Flush current chunk
                chunks.append(self._make_chunk(
                    "\n\n".join(current_chunk), doc_id, source, len(chunks)
                ))
                # Start new chunk with overlap
                overlap_text = " ".join(
                    "\n\n".join(current_chunk).split()[-overlap:]
                )
                current_chunk = [overlap_text, para] if overlap_text else [para]
                current_tokens = approx_tokens(overlap_text) + para_tokens
            else:
                current_chunk.append(para)
                current_tokens += para_tokens

        # Don't forget the last chunk
        if current_chunk:
            chunks.append(self._make_chunk(
                "\n\n".join(current_chunk), doc_id, source, len(chunks)
            ))

        return chunks

    def _make_chunk(self, text: str, doc_id: str, source: str, index: int) -> Dict:
        """Create a standardized chunk dictionary."""
        chunk_id = f"doc_{doc_id}_chunk_{index}_{hashlib.md5(text.encode()).hexdigest()[:8]}"
        return {
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "text": text.strip(),
            "source": source,
            "index": index,
        }

    async def reindex_all(self):
        """
        Re-ingests all documents in the uploads directory.
        Called by the daily APScheduler job.
        """
        from sqlmodel import Session, select
        from main import engine
        from models import Document

        with Session(engine) as session:
            docs = session.exec(
                select(Document).where(Document.status == "ready")
            ).all()

        logger.info(f"🔄 Re-indexing {len(docs)} documents...")
        for doc in docs:
            file_path = Path(settings.uploads_dir) / doc.filename
            if not file_path.exists():
                logger.warning("File not found, skipping", filename=doc.filename)
                continue
            try:
                await self.ingest_file(
                    file_path=str(file_path),
                    doc_id=str(doc.id),
                    source=doc.original_filename,
                    corpus=doc.corpus,
                    required_permissions=doc.required_permissions,
                )
            except Exception as e:
                logger.error("Re-index failed", doc=doc.original_filename, error=str(e))
