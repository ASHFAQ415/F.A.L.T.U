"""
config.py — Application Settings
=================================
All configuration is loaded from environment variables (your .env file).
Pydantic Settings automatically reads .env — you don't need to call load_dotenv().

Railway deployment:
  - Set these in the Railway dashboard → Variables tab
  - DATABASE_URL is auto-injected when you add a PostgreSQL plugin
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central configuration for the RAG chatbot backend.
    Values come from environment variables or .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Security ──────────────────────────────────────────
    jwt_secret_key: str = "change-me-in-production-use-32-char-random-string"
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24

    # ── Admin User (created on first startup) ─────────────
    admin_username: str = "admin"
    admin_password: str = "admin123"
    admin_email: str = "admin@example.com"

    # ── Groq API (FREE LLM — replaces Ollama for production) ──
    # Get your free key at: https://console.groq.com
    groq_api_key: str = "your-groq-api-key-here"
    groq_model: str = "llama-3.1-8b-instant"   # Fastest free model on Groq

    # ── Ollama (for local development only) ───────────────
    # These are kept for backward-compat with health checks / local dev
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_timeout: int = 120

    # ── Database ──────────────────────────────────────────
    # Railway PostgreSQL: auto-injected as DATABASE_URL when you add the plugin
    # Local dev: falls back to SQLite
    database_url: str = ""                       # Set by Railway PostgreSQL plugin
    data_dir: str = "/app/data"
    sqlite_db_path: str = "/app/data/rag.db"    # Used only if DATABASE_URL is empty
    uploads_dir: str = "/app/data/uploads"

    # ── ChromaDB ──────────────────────────────────────────
    chroma_collection_prefix: str = "rag"
    chroma_data_dir: str = "/app/data/chroma"   # Railway volume mount point

    # ── RAG Parameters ────────────────────────────────────
    retrieval_top_k: int = 20            # Chunks to fetch before reranking
    rerank_top_k: int = 5                # Chunks sent to LLM after reranking
    chunk_size: int = 400                # Tokens per chunk
    chunk_overlap: int = 60              # Overlap tokens between chunks
    max_context_tokens: int = 3000       # Max total tokens in LLM context

    # ── Semantic Cache ────────────────────────────────────
    enable_semantic_cache: bool = True
    cache_similarity_threshold: float = 0.92
    cache_ttl_seconds: int = 3600        # 1 hour

    # ── Rate Limiting ─────────────────────────────────────
    rate_limit_per_minute: int = 20      # Queries per user per minute

    # ── Feature Flags ─────────────────────────────────────
    enable_output_filtering: bool = True
    enable_pii_redaction: bool = True
    enable_reranking: bool = True

    # ── Logging ───────────────────────────────────────────
    log_level: str = "INFO"

    # ── Grafana ───────────────────────────────────────────
    grafana_password: str = "admin"

    @property
    def effective_db_url(self) -> str:
        """
        Returns the database URL to use.
        Prefers DATABASE_URL (Railway PostgreSQL) over SQLite.
        """
        if self.database_url:
            # Railway injects postgresql:// — SQLAlchemy needs postgresql+psycopg2://
            url = self.database_url
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+psycopg2://", 1)
            elif url.startswith("postgresql://") and "+psycopg2" not in url:
                url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
            return url
        return f"sqlite:///{self.sqlite_db_path}"


@lru_cache()
def get_settings() -> Settings:
    """
    Returns cached settings instance.
    The @lru_cache ensures settings are only parsed once at startup.
    """
    return Settings()
