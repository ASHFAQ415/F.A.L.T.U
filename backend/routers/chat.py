"""
routers/chat.py — Chat Endpoint (Streaming)
=============================================
POST /v1/chat → Streams LLM response via Server-Sent Events (SSE)

Flow:
  1. Authenticate user (JWT)
  2. Validate & sanitize query (guardrail)
  3. Check semantic cache — return cached answer if found
  4. Retrieve relevant chunks (ChromaDB hybrid search)
  5. Rerank chunks (cross-encoder)
  6. Stream response from Ollama (Llama 3.1)
  7. Save conversation to SQLite
  8. Update semantic cache
"""

import json
import time
import uuid
from typing import Annotated, AsyncGenerator

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from auth import get_current_user
from config import get_settings
from main import get_session
from models import ChatMessage, ChatRequest, ChatSession, User
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

    async def stream_response() -> AsyncGenerator[str, None]:
        full_response = ""
        sources = []

        try:
            if cached_response:
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

                system_prompt = f"""You are a helpful enterprise assistant. Answer the user's question using ONLY the provided context below.
If the answer is not in the context, say "I don't have enough information to answer that."
Always be concise, accurate, and cite your sources.

CONTEXT:
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
                    max_tokens=request.max_tokens,
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
            yield f"data: {json.dumps({'type': 'error', 'content': 'An error occurred. Please try again.'})}\n\n"
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
