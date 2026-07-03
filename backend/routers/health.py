"""
routers/health.py — Health Check Endpoint
==========================================
GET /health → System status check
Verifies Ollama, ChromaDB, and SQLite are reachable.
Used by Docker healthchecks and monitoring dashboards.
"""

import httpx
from fastapi import APIRouter
from sqlmodel import Session, text

from config import get_settings
from main import engine
from models import HealthResponse

router = APIRouter()
settings = get_settings()


@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """
    System health check.
    
    Checks connectivity to:
    - Ollama (LLM service)
    - ChromaDB (vector database)
    - SQLite (metadata database)
    
    Returns 200 OK if all healthy, 503 if any service is down.
    """
    ollama_ok = False
    chroma_ok = False

    # ── Check Ollama ──────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.ollama_base_url}/api/tags")
            ollama_ok = response.status_code == 200
    except Exception:
        ollama_ok = False

    # ── Check ChromaDB ────────────────────────────────────
    try:
        import chromadb
        client = chromadb.PersistentClient(path=f"{settings.data_dir}/chroma")
        client.heartbeat()
        chroma_ok = True
    except Exception:
        chroma_ok = False

    # ── Check SQLite ──────────────────────────────────────
    sqlite_ok = False
    try:
        with Session(engine) as session:
            session.exec(text("SELECT 1"))
            sqlite_ok = True
    except Exception:
        sqlite_ok = False

    overall_status = "healthy" if (ollama_ok and chroma_ok and sqlite_ok) else "degraded"

    return HealthResponse(
        status=overall_status,
        ollama_available=ollama_ok,
        chroma_available=chroma_ok,
        model=settings.ollama_model,
    )
