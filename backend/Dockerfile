FROM python:3.11-slim

LABEL maintainer="RAG Chatbot Project"
LABEL description="Enterprise RAG Chatbot Backend — Groq + sentence-transformers"

WORKDIR /app

# ── System dependencies ──────────────────────────────────
# libgomp1: required by sentence-transformers (OpenMP parallelism)
# curl: used by Docker/Railway health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies (cached layer) ───────────────────
# Copy requirements first so Docker caches this layer
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Pre-download ML models at build time ─────────────────
# This avoids slow cold-starts when the container first receives a request.
# Models are baked into the image layer.

# 1. sentence-transformers embedding model (~80MB)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2'); print('✅ Embedding model ready')"

# 2. Cross-encoder reranking model (~170MB)
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2'); print('✅ Reranker model ready')"

# ── Application code ─────────────────────────────────────
COPY . .

# ── Data directories ─────────────────────────────────────
# On Railway: /app/data is a persistent volume mount
# Locally: Docker named volume 'rag_data' maps here
RUN mkdir -p /app/data/uploads /app/data/chroma /app/data/logs

# ── Expose port ──────────────────────────────────────────
# Railway injects $PORT — uvicorn CMD reads it
EXPOSE 8000

# ── Health check ─────────────────────────────────────────
HEALTHCHECK --interval=20s --timeout=10s --start-period=120s --retries=5 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# ── Start command ─────────────────────────────────────────
# Uses $PORT from Railway (defaults to 8000 for local Docker)
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --log-level info
