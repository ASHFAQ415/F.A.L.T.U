"""
main.py — FastAPI Application Entry Point
==========================================
This is the heart of the backend. It:
  - Creates the FastAPI app with metadata (great for resume!)
  - Sets up SQLite database tables on startup
  - Creates the admin user on first run
  - Registers all routers (chat, ingest, health, admin, auth)
  - Exposes Prometheus metrics at /metrics
  - Starts the APScheduler for daily document re-ingestion
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from sqlmodel import Session, SQLModel, create_engine, select

from auth import create_user_in_db, get_user_by_username
from config import get_settings
from models import User

settings = get_settings()

# ── Structured Logger ─────────────────────────────────────
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(logging, settings.log_level.upper(), logging.INFO)
    )
)
logger = structlog.get_logger()

# ── SQLite Engine ─────────────────────────────────────────
# connect_args: needed for SQLite to work with FastAPI's thread pool
engine = create_engine(
    f"sqlite:///{settings.sqlite_db_path}",
    connect_args={"check_same_thread": False},
    echo=False,
)


def get_session():
    """FastAPI dependency — yields a database session per request."""
    with Session(engine) as session:
        yield session


# ── APScheduler (background jobs) ────────────────────────
scheduler = AsyncIOScheduler()


async def scheduled_reingestion():
    """Runs daily at 2 AM — re-processes any new/changed documents."""
    logger.info("🔄 Starting scheduled document re-ingestion...")
    from services.ingestion import IngestionService
    ingestion = IngestionService()
    await ingestion.reindex_all()
    logger.info("✅ Scheduled re-ingestion complete.")


# ── Application Lifespan ──────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs on startup and shutdown.
    Startup: create DB tables, create admin user, start scheduler.
    Shutdown: stop scheduler gracefully.
    """
    # ── Ensure data directories exist ────────────────────
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.uploads_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.sqlite_db_path).parent.mkdir(parents=True, exist_ok=True)

    # ── Create database tables ────────────────────────────
    logger.info("🗄️  Initializing SQLite database...")
    SQLModel.metadata.create_all(engine)

    # ── Create admin user on first run ────────────────────
    with Session(engine) as session:
        existing_admin = get_user_by_username(session, settings.admin_username)
        if not existing_admin:
            logger.info(f"👤 Creating admin user: {settings.admin_username}")
            create_user_in_db(
                session=session,
                username=settings.admin_username,
                email=settings.admin_email,
                password=settings.admin_password,
                full_name="System Administrator",
                is_admin=True,
                permissions="public,engineering,hr,finance,sales",
            )
            logger.info("✅ Admin user created successfully!")
        else:
            logger.info(f"👤 Admin user already exists: {settings.admin_username}")

    # ── Start background scheduler ────────────────────────
    scheduler.add_job(
        scheduled_reingestion,
        trigger="cron",
        hour=2,
        minute=0,
        id="daily_reingestion",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("⏰ Background scheduler started (daily re-ingestion at 2 AM)")

    logger.info("🚀 RAG Chatbot Backend is ready!")
    logger.info(f"   LLM Model: {settings.ollama_model}")
    logger.info(f"   Embed Model: {settings.ollama_embed_model}")
    logger.info(f"   Data Dir: {settings.data_dir}")

    yield  # ← Application runs here

    # ── Shutdown ──────────────────────────────────────────
    scheduler.shutdown(wait=False)
    logger.info("👋 Backend shutting down gracefully.")


# ── FastAPI App ───────────────────────────────────────────
app = FastAPI(
    title="Enterprise RAG Chatbot API",
    description="""
## 🤖 Enterprise RAG Chatbot — 100% Free Self-Hosted Stack

A production-grade **Retrieval-Augmented Generation (RAG)** chatbot that runs
entirely on free, open-source software. No subscriptions, no API bills.

### Stack
- **LLM**: Ollama (Llama 3.1 8B — runs locally)
- **Embeddings**: Ollama nomic-embed-text (runs locally)
- **Vector DB**: ChromaDB (on-disk)
- **Reranking**: Cross-encoder (sentence-transformers)
- **Database**: SQLite
- **Hosting**: Oracle Cloud Always Free

### Features
- 📄 Ingest PDF, DOCX, Markdown, and TXT files
- 🔍 Hybrid retrieval (vector + BM25 keyword)
- 🎯 Cross-encoder reranking for better accuracy
- 💬 Real-time streaming responses (SSE)
- 🔒 JWT authentication with role-based access
- 🛡️ Input/output guardrails + PII redaction
- 📊 Prometheus metrics + Grafana dashboards
    """,
    version="1.0.0",
    contact={
        "name": "RAG Chatbot",
        "url": "https://github.com/your-repo/rag-chatbot",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    lifespan=lifespan,
)

# ── CORS — Allow Streamlit frontend to talk to FastAPI ────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # In production, replace * with your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Prometheus Metrics ────────────────────────────────────
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# ── Register Routers ──────────────────────────────────────
from routers import admin, auth_router, chat, health, ingest

app.include_router(health.router)
app.include_router(auth_router.router, prefix="/auth", tags=["Authentication"])
app.include_router(chat.router, prefix="/v1", tags=["Chat"])
app.include_router(ingest.router, prefix="/v1", tags=["Document Ingestion"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])


@app.get("/", tags=["Root"])
async def root():
    """API root — redirects to docs."""
    return {
        "message": "🤖 Enterprise RAG Chatbot API",
        "docs": "/docs",
        "health": "/health",
        "version": "1.0.0",
    }
