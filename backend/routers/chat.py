"""
routers/chat.py — Chat Endpoint (Streaming)
=============================================
POST /v1/chat → Streams LLM response via Server-Sent Events (SSE)

Flow:
  1. Authenticate user (JWT)
  2. Validate & sanitize query (guardrail)
  3. Detect document-listing intent → inject real document list
  4. Check semantic cache — return cached answer if found
  5. Retrieve relevant chunks (ChromaDB hybrid search)
  6. Rerank chunks (cross-encoder)
  7. Stream response from Groq (Llama 3.1)
  8. Save conversation to SQLite
  9. Update semantic cache
"""

import json
import re
import time
import uuid
from typing import Annotated, AsyncGenerator, List

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from auth import get_current_user
from config import get_settings
from main import get_session
from models import ChatMessage, ChatRequest, ChatSession, Document, User
from services.cache import SemanticCache
from services.guardrail import Guardrail
from services.llm_client import OllamaClient
from services.retriever import HybridRetriever
from services.reranker import CrossEncoderReranker
from utils.citations import build_citations

router = APIRouter()
logger = structlog.get_logger()
settings = get_settings()

# ── Singleton services (initialized once, reused across requests) ──
_guardrail = Guardrail()
_retriever = HybridRetriever()
_reranker = CrossEncoderReranker()
_cache = SemanticCache()
_llm = OllamaClient()

# ── Document-listing intent keywords ──────────────────────
_DOC_LIST_PATTERNS = re.compile(
    r"(?i)(\blist\b|\bshow\b|\bwhat\b.*\bdocuments?\b|\bwhich\b.*\bdocuments?\b"
    r"|\bavailable\b.*\bdocuments?\b|\bdocuments?\b.*\bavailable\b"
    r"|\bfiles?\b.*\buploaded\b|\buploaded\b.*\bfiles?\b"
    r"|\bwhat.*\bfiles?\b|\bknowledge base\b|\bwhat.*\bdo you have\b"
    r"|\bwhat.*\bcan you access\b|\bgiven documents?\b|\bshare.*\bdocuments?\b)"
)


def _is_doc_listing_query(query: str) -> bool:
    """Return True if the user is asking about what documents are available."""
    return bool(_DOC_LIST_PATTERNS.search(query))


def _build_doc_list_context(session: Session, corpus: str, user: User) -> str:
    """
    Fetch the actual documents from the database and build a context string
    listing them. This replaces RAG retrieval for document-listing queries.
    """
    query = select(Document).where(
        Document.corpus == corpus,
        Document.status == "ready",
    )
    docs = session.exec(query).all()

    # Filter by user permissions (non-admins can only see permitted docs)
    if not user.is_admin:
        user_perms = set(user.permissions.split(","))
        docs = [
            d for d in docs
            if any(p in user_perms for p in d.required_permissions.split(","))
        ]

    if not docs:
        return "NO_DOCUMENTS"

    lines = []
    for i, doc in enumerate(docs, 1):
        size_kb = round(doc.file_size_bytes / 1024, 1) if doc.file_size_bytes else 0
        lines.append(
            f"{i}. **{doc.original_filename}** "
            f"(type: {doc.file_type.upper()}, size: {size_kb} KB, "
            f"chunks: {doc.chunk_count}, corpus: {doc.corpus})"
        )
    return "\n".join(lines)


@router.post("/chat", summary="Chat with the RAG chatbot (streaming)")
async def chat(
    request: ChatRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """
    Send a query and receive a streaming AI response.
    
    The response is streamed as **Server-Sent Events (SSE)**:
    ```
    data: {"type": "token", "content": "To"}
    data: {"type": "token", "content": " reset"}
    data: {"type": "metadata", "sources": [...], "latency_ms": 1234}
    data: [DONE]
    ```
    
    Requires: `Authorization: Bearer <token>`
    """
    start_time = time.time()

    # ── Step 1: Guardrail — block prompt injections ───────
    is_safe, reason = _guardrail.check_input(request.query)
    if not is_safe:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Query blocked by safety guardrail: {reason}",
        )

    # ── Step 2: Check permissions for the requested corpus ─
    user_perms = set(current_user.permissions.split(","))
    if request.corpus not in user_perms and "admin" not in user_perms:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You don't have access to the '{request.corpus}' corpus.",
        )

    # ── Step 3: Get or create chat session ────────────────
    session_id = request.session_id or str(uuid.uuid4())
    db_session = session.exec(
        select(ChatSession).where(ChatSession.session_id == session_id)
    ).first()

    if not db_session:
        db_session = ChatSession(
            session_id=session_id,
            user_id=current_user.id,
            title=request.query[:50] + "..." if len(request.query) > 50 else request.query,
        )
        session.add(db_session)
        session.commit()
        session.refresh(db_session)

    # ── Step 4: Check semantic cache ──────────────────────
    cached_response = None
    if settings.enable_semantic_cache:
        cached_response = await _cache.get(request.query, corpus=request.corpus)

    # ── Detect document-listing intent BEFORE cache check ──
    is_doc_query = _is_doc_listing_query(request.query)

    async def stream_response() -> AsyncGenerator[str, None]:
        full_response = ""
        sources = []

        try:
            # ── Document listing shortcut ──────────────────
            if is_doc_query:
                logger.info("📋 Document-listing intent detected", query=request.query[:60])
                doc_context = _build_doc_list_context(session, request.corpus, current_user)

                if doc_context == "NO_DOCUMENTS":
                    doc_system_prompt = (
                        f"You are F.A.L.T.U, a helpful enterprise AI assistant. "
                        f"The user is asking about available documents in the '{request.corpus}' knowledge base. "
                        f"There are currently NO documents uploaded in this knowledge base. "
                        f"Tell the user that no documents have been uploaded yet and they can upload some via the 'Docs' section."
                    )
                else:
                    doc_system_prompt = (
                        f"You are F.A.L.T.U, a helpful enterprise AI assistant. "
                        f"The user is asking what documents are available. "
                        f"Here is the EXACT list of documents currently in the '{request.corpus}' knowledge base:\n\n"
                        f"{doc_context}\n\n"
                        f"List these documents clearly for the user. Include file name, type, and size. "
                        f"Be friendly and tell them they can ask questions about any of these documents."
                    )

                async for token in _llm.stream_chat(
                    query=request.query,
                    system_prompt=doc_system_prompt,
                    temperature=0.3,
                    max_tokens=1024,
                ):
                    full_response += token
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

            elif cached_response:
                # ── Return cached response ─────────────────
                logger.info("✅ Cache hit", query=request.query[:50])
                for token in cached_response["response"].split(" "):
                    yield f"data: {json.dumps({'type': 'token', 'content': token + ' '})}\n\n"
                sources = cached_response.get("sources", [])
                full_response = cached_response["response"]

            else:
                # ── Step 5: Retrieve relevant chunks ───────
                retrieval_start = time.time()
                chunks = await _retriever.retrieve(
                    query=request.query,
                    corpus=request.corpus,
                    top_k=settings.retrieval_top_k,
                )
                retrieval_ms = int((time.time() - retrieval_start) * 1000)

                # ── Step 6: Rerank ──────────────────────────
                if settings.enable_reranking and len(chunks) > 1:
                    chunks = _reranker.rerank(
                        query=request.query,
                        chunks=chunks,
                        top_k=settings.rerank_top_k,
                    )

                # ── Step 7: Build context + prompt ─────────
                context = "\n\n---\n\n".join(
                    [f"[Source: {c['source']}]\n{c['text']}" for c in chunks]
                )
                sources = build_citations(chunks)

                system_prompt = f"""You are F.A.L.T.U (Fantastically Accurate Language & Thinking Unit), a helpful enterprise AI assistant.

Your job is to answer the user's question using ONLY the provided context below.
Rules:
- If the answer IS in the context, answer clearly and concisely.
- If the answer is NOT in the context, say exactly: "I don't have enough information in the provided documents to answer that."
- Always cite which document/source you used (e.g. "According to [filename]...").
- Use markdown formatting for clarity (bullet points, bold, etc.) when appropriate.
- Be direct and helpful. Do not add unnecessary disclaimers.

CONTEXT FROM DOCUMENTS:
{context}"""

                # ── Step 8: Stream from Ollama ──────────────
                logger.info(
                    "🤖 Streaming from Ollama",
                    model=settings.ollama_model,
                    chunks=len(chunks),
                    retrieval_ms=retrieval_ms,
                )
                async for token in _llm.stream_chat(
                    query=request.query,
                    system_prompt=system_prompt,
                    temperature=request.temperature,
                    max_tokens=max(request.max_tokens, 1024),  # Ensure at least 1024 tokens
                ):
                    full_response += token
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

                # ── Update cache ───────────────────────────
                if settings.enable_semantic_cache:
                    await _cache.set(
                        query=request.query,
                        response=full_response,
                        sources=sources,
                        corpus=request.corpus,
                    )

            # ── Apply output guardrail ─────────────────────
            if full_response:
                full_response, _ = _guardrail.check_output(full_response)

            # ── Step 9: Save to database ───────────────────
            total_ms = int((time.time() - start_time) * 1000)

            user_msg = ChatMessage(
                session_id=db_session.id,
                role="user",
                content=request.query,
            )
            assistant_msg = ChatMessage(
                session_id=db_session.id,
                role="assistant",
                content=full_response,
                sources=json.dumps(sources),
                latency_ms=total_ms,
            )
            session.add(user_msg)
            session.add(assistant_msg)
            session.commit()
            session.refresh(assistant_msg)

            # ── Send metadata ──────────────────────────────
            yield f"data: {json.dumps({'type': 'metadata', 'message_id': assistant_msg.id, 'sources': sources, 'latency_ms': total_ms, 'session_id': session_id, 'from_cache': cached_response is not None})}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error("💥 Chat error", error=str(e))
            # Provide a more informative error message
            error_detail = str(e)
            if "groq" in error_detail.lower() or "api" in error_detail.lower():
                user_msg = "The AI service is temporarily unavailable. Please try again in a moment."
            elif "chroma" in error_detail.lower() or "retriev" in error_detail.lower():
                user_msg = "Could not search documents right now. Please try again."
            else:
                user_msg = "Something went wrong. Please try again."
            yield f"data: {json.dumps({'type': 'error', 'content': user_msg})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",    # Tell Nginx not to buffer SSE
        },
    )


@router.post("/feedback", summary="Submit 👍/👎 feedback on a response")
async def submit_feedback(
    message_id: int,
    rating: int,
    comment: str = None,
    current_user: Annotated[User, Depends(get_current_user)] = None,
    session: Annotated[Session, Depends(get_session)] = None,
):
    """Submit thumbs up/down feedback on a chatbot response."""
    from models import Feedback

    if rating not in (-1, 1):
        raise HTTPException(status_code=400, detail="Rating must be 1 (👍) or -1 (👎)")

    feedback = Feedback(
        message_id=message_id,
        user_id=current_user.id,
        rating=rating,
        comment=comment,
    )
    session.add(feedback)
    session.commit()
    return {"message": "Feedback recorded. Thank you!"}


@router.get("/sessions", summary="Get user's chat session history")
async def get_sessions(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: int = 20,
):
    """Returns a list of the user's recent chat sessions."""
    sessions = session.exec(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.updated_at.desc())
        .limit(limit)
    ).all()
    return sessions


@router.get("/sessions/{session_id}/messages", summary="Get messages in a session")
async def get_messages(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Returns all messages in a specific chat session."""
    chat_session = session.exec(
        select(ChatSession).where(
            ChatSession.session_id == session_id,
            ChatSession.user_id == current_user.id,
        )
    ).first()

    if not chat_session:
        raise HTTPException(status_code=404, detail="Session not found.")

    messages = session.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == chat_session.id)
        .order_by(ChatMessage.created_at.asc())
    ).all()
    return messages
