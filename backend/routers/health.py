"""
routers/health.py — Health Check Endpoint
==========================================
GET /health → System status check
Verifies Groq API, ChromaDB, and PostgreSQL/SQLite are reachable.
Used by Railway healthchecks and monitoring dashboards.
"""

from fastapi import APIRouter
from sqlmodel import Session, text

from config import get_settings
from main import engine

router = APIRouter()
settings = get_settings()


@router.get("/health", tags=["System"])
async def health_check():
    """
    System health check.

    Checks connectivity to:
    - Groq API (LLM service)
    - ChromaDB (vector database)
    - PostgreSQL/SQLite (metadata database)

    Returns 200 OK always — individual service statuses are in the response body.
    """
    groq_ok = False
    chroma_ok = False
    db_ok = False

    # ── Check Groq API ────────────────────────────────────
    try:
        from services.llm_client import GroqClient
        client = GroqClient()
        groq_ok = await client.is_available()
    except Exception:
        groq_ok = False

    # ── Check ChromaDB ────────────────────────────────────
    try:
        import chromadb
        client = chromadb.PersistentClient(path=settings.chroma_data_dir)
        client.heartbeat()
        chroma_ok = True
    except Exception:
        chroma_ok = False

    # ── Check Database ────────────────────────────────────
    try:
        with Session(engine) as session:
            session.exec(text("SELECT 1"))
            db_ok = True
    except Exception:
        db_ok = False

    db_type = "postgresql" if settings.database_url else "sqlite"
    overall_status = "healthy" if (groq_ok and chroma_ok and db_ok) else "degraded"

    return {
        "status": overall_status,
        "groq_available": groq_ok,
        "chroma_available": chroma_ok,
        "database_available": db_ok,
        "database_type": db_type,
        # Keep backward-compat fields for the frontend
        "ollama_available": groq_ok,
        "model": settings.groq_model,
        "version": "2.0.0",
    }
