FROM python:3.11-slim

# Metadata
LABEL maintainer="RAG Chatbot Project"
LABEL description="Enterprise RAG Chatbot Backend — 100% Free Stack"

# Set working directory
WORKDIR /app

# Install system dependencies
# - libgomp1: required by sentence-transformers (OpenMP)
# - poppler-utils: required by PyMuPDF for PDF processing
RUN apt-get update && apt-get install -y \
    curl \
    libgomp1 \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download the reranker model at build time so startup is fast
# This is the cross-encoder model (runs locally, completely free)
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

# Copy application code
COPY . .

# Create data directory for ChromaDB + SQLite + uploaded files
RUN mkdir -p /app/data/uploads /app/data/chroma /app/data/logs

# Expose FastAPI port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=20s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start FastAPI with uvicorn
# --reload: hot-reload on code changes (remove in strict production)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--log-level", "info"]
