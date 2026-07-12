# F.A.L.T.U - RAG Chatbot

F.A.L.T.U stands for **Fantastically Accurate Language & Thinking Unit**. It is a document-based Retrieval-Augmented Generation (RAG) chatbot. Users upload documents, ask questions, and receive AI-generated answers grounded in those documents with source citations.

The project is designed as a full-stack, deployable chatbot system with authentication, document ingestion, hybrid retrieval, streaming responses, admin controls, and monitoring.

## What This Project Does

- Lets users upload PDF, DOCX, Markdown, and TXT documents.
- Extracts text from uploaded files.
- Splits document text into overlapping chunks.
- Creates embeddings with `sentence-transformers/all-MiniLM-L6-v2`.
- Stores document vectors in ChromaDB.
- Retrieves relevant chunks using hybrid search:
  - vector similarity search through ChromaDB
  - keyword search through BM25
- Optionally reranks retrieved chunks with a cross-encoder.
- Sends the selected context to a Groq-hosted LLM.
- Streams the answer back to the frontend using Server-Sent Events.
- Shows citations for the source chunks used in the answer.
- Saves chat sessions, messages, document metadata, users, and feedback.
- Provides admin-only user management and usage statistics.

## Main Use Case

This application is useful when a team wants a private chatbot over its own documents, such as:

- company policies
- engineering documentation
- HR material
- finance documents
- sales enablement material
- internal knowledge base files

Instead of answering from model memory alone, the chatbot searches uploaded documents first and answers from the retrieved context.

## Tech Stack

| Layer | Technology |
| --- | --- |
| Frontend | Streamlit |
| Backend | FastAPI |
| LLM | Groq API |
| Embeddings | sentence-transformers |
| Vector database | ChromaDB |
| Keyword search | rank-bm25 |
| Relational database | SQLite locally, PostgreSQL when `DATABASE_URL` is set |
| Auth | JWT + bcrypt |
| Monitoring | Prometheus + Grafana |
| Deployment | Docker Compose, Railway configs |

## Project Structure

```text
rag-chatbot/
|-- backend/
|   |-- main.py                  # FastAPI app setup, startup tasks, router registration
|   |-- config.py                # Environment-based settings
|   |-- auth.py                  # JWT auth, password hashing, current-user dependencies
|   |-- models.py                # SQLModel database models
|   |-- routers/
|   |   |-- auth_router.py       # Login, logout, current user
|   |   |-- chat.py              # Streaming RAG chat, feedback, chat sessions
|   |   |-- ingest.py            # Document upload/list/delete
|   |   |-- admin.py             # Admin user management and stats
|   |   `-- health.py            # Health checks
|   |-- services/
|   |   |-- ingestion.py         # Parse, chunk, embed, index documents
|   |   |-- retriever.py         # ChromaDB + BM25 hybrid retrieval
|   |   |-- reranker.py          # Cross-encoder reranking
|   |   |-- llm_client.py        # Groq streaming client
|   |   |-- embedder.py          # sentence-transformers embedder
|   |   |-- cache.py             # Semantic response cache
|   |   `-- guardrail.py         # Prompt-injection checks and PII redaction
|   `-- requirements.txt
|-- frontend/
|   |-- app.py                   # Streamlit UI
|   `-- requirements.txt
|-- monitoring/
|   |-- prometheus.yml
|   `-- grafana/
|-- nginx/
|   `-- nginx.conf
|-- docker-compose.yml
|-- Dockerfile.backend
|-- Dockerfile.frontend
|-- deployment_guide.md
`-- PROJECT_BRIEF.md
```

## Architecture

```text
User Browser
    |
    v
Streamlit Frontend
    |
    v
FastAPI Backend
    |
    +--> SQL database for users, documents, chat history, feedback
    |
    +--> ChromaDB for vector search
    |
    +--> sentence-transformers for embeddings
    |
    +--> BM25 for keyword retrieval
    |
    +--> Groq API for LLM responses
```

## Request Flow

### Document Upload Flow

1. User logs in.
2. User uploads a PDF, DOCX, Markdown, or TXT file.
3. Backend validates file type and size.
4. File is saved to disk.
5. Metadata is stored in the SQL database.
6. Background ingestion starts.
7. Text is extracted.
8. Text is chunked.
9. Chunks are embedded.
10. Chunks are indexed in ChromaDB.
11. Document status changes from `pending` to `processing` to `ready`.

### Chat Flow

1. User sends a question from the Streamlit UI.
2. Backend validates JWT authentication.
3. Guardrails check the input.
4. Backend checks whether the user can access the selected corpus.
5. Semantic cache is checked.
6. Relevant chunks are retrieved from ChromaDB and BM25.
7. Results are optionally reranked.
8. A context prompt is built from the selected chunks.
9. Groq streams the LLM answer.
10. The answer is returned to the UI token by token.
11. Sources and metadata are sent after completion.
12. Chat messages are stored in the database.

## Key Features

### Document Ingestion

Supported formats:

- PDF
- DOCX
- Markdown
- TXT

Uploaded documents are deduplicated using an MD5 content hash.

### Retrieval

The retriever combines two search methods:

- **Dense search:** semantic similarity over embeddings in ChromaDB.
- **Sparse search:** keyword matching with BM25.

The two result sets are merged with Reciprocal Rank Fusion.

### LLM

The backend uses Groq through `backend/services/llm_client.py`. The default model is:

```text
llama-3.1-8b-instant
```

Some code comments still mention Ollama because the project previously used that interface. The runtime client is Groq, and `OllamaClient` is kept as a compatibility alias.

### Authentication

The app uses:

- bcrypt for password hashing
- JWT bearer tokens for authentication
- admin-only routes for user management
- per-user corpus permissions

The first admin user is created automatically on backend startup using environment variables.

### Permissions

Users have comma-separated corpus permissions, for example:

```text
public,engineering,hr
```

When chatting, the user must have access to the selected corpus.

### Monitoring

The local Docker Compose stack includes:

- Prometheus at `http://localhost:9090`
- Grafana at `http://localhost:3000`
- backend metrics at `/metrics`

## Environment Variables

Create `.env` from `.env.example` and set the required values.

Important variables:

| Variable | Purpose |
| --- | --- |
| `GROQ_API_KEY` | Required Groq API key |
| `GROQ_MODEL` | Groq model name |
| `JWT_SECRET_KEY` | Secret used to sign JWT tokens |
| `ADMIN_USERNAME` | Initial admin username |
| `ADMIN_PASSWORD` | Initial admin password |
| `ADMIN_EMAIL` | Initial admin email |
| `DATABASE_URL` | PostgreSQL URL; leave empty for local SQLite fallback |
| `DATA_DIR` | Backend data directory |
| `CHROMA_DATA_DIR` | ChromaDB persistence directory |
| `RETRIEVAL_TOP_K` | Number of chunks retrieved before reranking |
| `RERANK_TOP_K` | Number of chunks sent to the LLM after reranking |
| `ENABLE_SEMANTIC_CACHE` | Enables similar-query response caching |
| `ENABLE_RERANKING` | Enables cross-encoder reranking |
| `ENABLE_PII_REDACTION` | Enables output PII redaction |

## Local Development With Docker

Prerequisites:

- Docker Desktop
- Groq API key

Steps:

```bash
cp .env.example .env
```

Edit `.env` and set:

```text
GROQ_API_KEY=your_key_here
JWT_SECRET_KEY=your_random_secret
ADMIN_PASSWORD=your_admin_password
```

Start the stack:

```bash
docker compose up --build
```

Open:

| Service | URL |
| --- | --- |
| Frontend | `http://localhost:8501` |
| Backend API docs | `http://localhost:8000/docs` |
| Backend health | `http://localhost:8000/health` |
| Prometheus | `http://localhost:9090` |
| Grafana | `http://localhost:3000` |

## Running Without Docker

Backend:

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd frontend
pip install -r requirements.txt
streamlit run app.py --server.port 8501
```

Set `BACKEND_URL` for the frontend if the backend is not reachable at the default URL.

## API Overview

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/` | Root API info |
| `GET` | `/health` | Service health check |
| `POST` | `/auth/login` | Login and get JWT token |
| `POST` | `/auth/logout` | Client-side logout helper |
| `GET` | `/auth/me` | Current user profile |
| `POST` | `/v1/ingest` | Upload a document |
| `GET` | `/v1/documents` | List documents |
| `DELETE` | `/v1/documents/{doc_id}` | Delete a document |
| `POST` | `/v1/chat` | Streaming RAG chat endpoint |
| `POST` | `/v1/feedback` | Submit answer feedback |
| `GET` | `/v1/sessions` | List chat sessions |
| `GET` | `/v1/sessions/{session_id}/messages` | Get messages in a session |
| `GET` | `/admin/users` | Admin: list users |
| `POST` | `/admin/users` | Admin: create user |
| `PATCH` | `/admin/users/{user_id}` | Admin: update user |
| `DELETE` | `/admin/users/{user_id}` | Admin: delete user |
| `GET` | `/admin/stats` | Admin: usage statistics |
| `GET` | `/metrics` | Prometheus metrics |

## Deployment

The repository includes Railway configuration files:

- `backend/railway.toml`
- `frontend/railway.toml`

For Railway deployment:

1. Deploy backend and frontend as separate services.
2. Add PostgreSQL to the Railway project.
3. Set backend environment variables:
   - `GROQ_API_KEY`
   - `JWT_SECRET_KEY`
   - `ADMIN_USERNAME`
   - `ADMIN_PASSWORD`
   - `ADMIN_EMAIL`
4. Set frontend environment variable:
   - `BACKEND_URL=https://your-backend-service-url`
5. Add a persistent volume for backend data if using ChromaDB persistence.

See `deployment_guide.md` for more deployment details.

## Known Notes

- The codebase contains some older comments that refer to Ollama. The active LLM implementation uses Groq.
- The FastAPI OAuth docs token URL in `backend/auth.py` currently points to `/api/auth/login`, while the registered login route is `/auth/login`.
- Some older files contain encoding artifacts in comments. The application logic is still readable, but documentation has been rewritten in clean ASCII Markdown.

## License

MIT
