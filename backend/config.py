"""
config.py — Application Settings
=================================
All configuration is loaded from environment variables (your .env file).
Pydantic Settings automatically reads .env — you don't need to call load_dotenv().
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
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24

    # ── Admin User (created on first startup) ─────────────
    admin_username: str = "admin"
    admin_password: str = "admin123"
    admin_email: str = "admin@example.com"

    # ── Ollama / LLM ──────────────────────────────────────
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_timeout: int = 120             # Seconds to wait for LLM response

    # ── Data Storage ──────────────────────────────────────
    data_dir: str = "/app/data"
    chroma_collection_prefix: str = "rag"
    sqlite_db_path: str = "/app/data/rag.db"
    uploads_dir: str = "/app/data/uploads"

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


@lru_cache()
def get_settings() -> Settings:
    """
    Returns cached settings instance.
    The @lru_cache ensures settings are only parsed once at startup.
    """
    return Settings()
