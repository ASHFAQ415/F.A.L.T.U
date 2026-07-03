"""
routers/ingest.py — Document Ingestion Endpoint
=================================================
POST /v1/ingest → Upload and ingest a document into the RAG knowledge base
GET  /v1/documents → List all ingested documents
DELETE /v1/documents/{id} → Remove a document
"""

import hashlib
import shutil
from pathlib import Path
from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session, select

from auth import get_current_user, require_admin
from config import get_settings
from main import get_session
from models import Document, User

router = APIRouter()
logger = structlog.get_logger()
settings = get_settings()

ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/markdown": "md",
    "text/plain": "txt",
    "text/x-markdown": "md",
}


@router.post("/ingest", summary="Upload a document to the knowledge base")
async def ingest_document(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(description="PDF, DOCX, MD, or TXT file")],
    corpus: Annotated[str, Form(description="Which knowledge base to add to (e.g. 'public', 'engineering')")] = "public",
    required_permissions: Annotated[str, Form(description="Who can access this doc (e.g. 'public' or 'engineering,admin')")] = "public",
    current_user: Annotated[User, Depends(get_current_user)] = None,
    session: Annotated[Session, Depends(get_session)] = None,
):
    """
    Upload a document to be ingested into the RAG knowledge base.
    
    The document is:
    1. Saved to disk
    2. Parsed (PDF/DOCX/MD/TXT)
    3. Split into chunks
    4. Embedded with nomic-embed-text (Ollama)
    5. Stored in ChromaDB for retrieval
    
    Processing happens in the background — check `/v1/documents` for status.
    """
    # ── Validate file type ────────────────────────────────
    file_type = ALLOWED_TYPES.get(file.content_type)
    if not file_type:
        # Try to infer from extension
        suffix = Path(file.filename).suffix.lower().lstrip(".")
        if suffix in ("pdf", "docx", "md", "txt"):
            file_type = suffix
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file.content_type}. Allowed: PDF, DOCX, MD, TXT",
            )

    # ── Check file size (max 50MB) ────────────────────────
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 50MB.")

    # ── Compute content hash (deduplication) ──────────────
    content_hash = hashlib.md5(content).hexdigest()
    existing = session.exec(
        select(Document).where(Document.content_hash == content_hash)
    ).first()
    if existing:
        return {
            "message": "This document was already ingested.",
            "document_id": existing.id,
            "filename": existing.original_filename,
            "status": existing.status,
        }

    # ── Save file to disk ─────────────────────────────────
    safe_filename = f"{content_hash}_{Path(file.filename).name}"
    file_path = Path(settings.uploads_dir) / safe_filename
    with open(file_path, "wb") as f:
        f.write(content)

    # ── Create document record in SQLite ──────────────────
    doc = Document(
        filename=safe_filename,
        original_filename=file.filename,
        file_type=file_type,
        file_size_bytes=len(content),
        corpus=corpus,
        required_permissions=required_permissions,
        content_hash=content_hash,
        uploaded_by=current_user.id,
        status="pending",
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)

    # ── Process in background (don't block the HTTP response) ──
    background_tasks.add_task(
        process_document_background,
        doc_id=doc.id,
        file_path=str(file_path),
    )

    logger.info(
        "📄 Document queued for ingestion",
        filename=file.filename,
        corpus=corpus,
        doc_id=doc.id,
    )

    return {
        "message": "Document received and queued for processing.",
        "document_id": doc.id,
        "filename": file.filename,
        "status": "pending",
        "corpus": corpus,
    }


async def process_document_background(doc_id: int, file_path: str):
    """
    Background task: parse, chunk, embed, and index a document.
    Updates the Document status in SQLite as it progresses.
    """
    from services.ingestion import IngestionService
    from sqlmodel import Session as SQLSession
    from main import engine

    ingestion = IngestionService()

    with SQLSession(engine) as session:
        doc = session.get(Document, doc_id)
        if not doc:
            return

        try:
            doc.status = "processing"
            session.add(doc)
            session.commit()

            chunk_count = await ingestion.ingest_file(
                file_path=file_path,
                doc_id=str(doc_id),
                source=doc.original_filename,
                corpus=doc.corpus,
                required_permissions=doc.required_permissions,
            )

            from datetime import datetime
            doc.status = "ready"
            doc.chunk_count = chunk_count
            doc.processed_at = datetime.utcnow()
            session.add(doc)
            session.commit()

            logger.info(
                "✅ Document ingested",
                doc_id=doc_id,
                chunks=chunk_count,
            )

        except Exception as e:
            doc.status = "error"
            doc.error_message = str(e)
            session.add(doc)
            session.commit()
            logger.error("💥 Ingestion failed", doc_id=doc_id, error=str(e))


@router.get("/documents", summary="List all ingested documents")
async def list_documents(
    corpus: str = None,
    current_user: Annotated[User, Depends(get_current_user)] = None,
    session: Annotated[Session, Depends(get_session)] = None,
):
    """List all documents in the knowledge base (filtered by corpus if provided)."""
    query = select(Document)
    if corpus:
        query = query.where(Document.corpus == corpus)
    if not current_user.is_admin:
        # Non-admins can only see docs they have permission to access
        user_perms = set(current_user.permissions.split(","))
        docs = session.exec(query).all()
        docs = [d for d in docs if any(p in user_perms for p in d.required_permissions.split(","))]
        return docs
    return session.exec(query).all()


@router.delete("/documents/{doc_id}", summary="Remove a document from the knowledge base")
async def delete_document(
    doc_id: int,
    current_user: Annotated[User, Depends(require_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    """(Admin only) Delete a document and remove its vectors from ChromaDB."""
    doc = session.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    # Remove from ChromaDB
    try:
        from services.retriever import HybridRetriever
        retriever = HybridRetriever()
        retriever.delete_document(str(doc_id), corpus=doc.corpus)
    except Exception as e:
        logger.warning("Could not remove from ChromaDB", error=str(e))

    # Remove file from disk
    file_path = Path(settings.uploads_dir) / doc.filename
    if file_path.exists():
        file_path.unlink()

    session.delete(doc)
    session.commit()
    return {"message": f"Document '{doc.original_filename}' deleted successfully."}
