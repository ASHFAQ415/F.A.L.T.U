"""
routers/chat.py — Chat Endpoint (Streaming)
=============================================
POST /v1/chat -> Streams LLM response via Server-Sent Events (SSE)

Flow:
  1. Authenticate user (JWT)
  2. Validate & sanitize query (guardrail)
  3. Detect document-listing intent -> inject real document list
  4. Check semantic cache — return cached answer if found
  5. HyDE query expansion (generate hypothetical answer for better retrieval)
  6. Retrieve relevant chunks (ChromaDB hybrid search)
  7. Rerank chunks (cross-encoder)
  8. Load conversation history (last N messages for multi-turn memory)
  9. Stream response from Groq (Llama 3.1) with full history
  10. Save conversation to DB
  11. Update semantic cache
"""

import json
import re
import time
import uuid
from typing import Annotated, AsyncGenerator, List

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from auth import get_current_user
from config import get_settings
from main import get_session
from models import ChatMessage, ChatRequest, ChatSession, Document, User
from services.cache import SemanticCache
from services.guardrail import Guardrail
from services.llm_client import GroqClient
from services.retriever import HybridRetriever
from services.reranker import CrossEncoderReranker
from utils.citations import build_citations

router = APIRouter()
logger = structlog.get_logger()
settings = get_settings()

# Singleton services (initialized once, reused across requests)
_guardrail = Guardrail()
_retriever = HybridRetriever()
_reranker = CrossEncoderReranker()
_cache = SemanticCache()
_llm = GroqClient()

# Document-listing intent — ONLY fires when user clearly wants to know what docs EXIST.
# Does NOT fire for content queries that mention 'document' (e.g. 'summarize the given document').
_DOC_LIST_PATTERNS = re.compile(
    r"(?i)("
    # Explicit: list/show/display + documents/files
    r"\b(list|show me|tell me|display)\b.{0,40}\b(documents?|files?)\b"
    # What documents do you have / are available
    r"|\bwhat\b.{0,50}\b(documents?|files?)\b.{0,40}\b(do you have|available|uploaded|can access)\b"
    # Which documents are available/uploaded
    r"|\bwhich\b.{0,30}\b(documents?|files?)\b.{0,40}\b(available|uploaded|do you have)\b"
    # Documents available / uploaded documents
    r"|\bdocuments?\b.{0,20}\b(available|uploaded|in (the |your )?knowledge base)\b"
    r"|\buploaded (documents?|files?)\b"
    # Knowledge base queries
    r"|\bknowledge base\b"
    r"|\bwhat.{0,20}\bdo you (have|know about|contain)\b"
    r")"
)


def _is_doc_listing_query(query: str) -> bool:
    """Return True if the user is asking about what documents are available."""
    return bool(_DOC_LIST_PATTERNS.search(query))


def _build_doc_list_context(session: Session, corpus: str, user: User) -> str:
    """
    Fetch the actual documents from the database and return a formatted list.
    Returns 'NO_DOCUMENTS' if none found/accessible.
    """
    docs = session.exec(
        select(Document).where(
            Document.corpus == corpus,
            Document.status == "ready",
        )
    ).all()

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


def _load_recent_history(session: Session, chat_session_id: int, limit: int = 10) -> List[dict]:
    """
    Load the last `limit` messages from a chat session for multi-turn memory.
    Returns OpenAI-style message dicts: [{"role": "user"|"assistant", "content": str}]
    """
    messages = session.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == chat_session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    ).all()
    # Reverse to chronological order
    return [{"role": m.role, "content": m.content} for m in reversed(messages)]


@router.post("/chat", summary="Chat with the RAG chatbot (streaming)")
async def chat(
    request: ChatRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """
    Send a query and receive a streaming AI response.

    The response is streamed as Server-Sent Events (SSE):
      data: {"type": "token", "content": "To"}
      data: {"type": "metadata", "sources": [...], "latency_ms": 1234}
      data: [DONE]

    Requires: Authorization: Bearer <token>
    """
    start_time = time.time()

    # Step 1: Guardrail
    is_safe, reason = _guardrail.check_input(request.query)
    if not is_safe:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Query blocked: {reason}",
        )

    # Step 2: Permission check
    user_perms = set(current_user.permissions.split(","))
    if request.corpus not in user_perms and "admin" not in user_perms:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You don't have access to the '{request.corpus}' corpus.",
        )

    # Step 3: Get or create chat session
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

    # Step 4: Semantic cache check
    cached_response = None
    if settings.enable_semantic_cache:
        cached_response = await _cache.get(request.query, corpus=request.corpus)

    # Step 5: Document-listing intent
    is_doc_query = _is_doc_listing_query(request.query)

    async def stream_response() -> AsyncGenerator[str, None]:
        full_response = ""
        sources = []

        try:
            # Branch A: Document listing
            if is_doc_query:
                logger.info("Document-listing intent", query=request.query[:60])
                doc_context = _build_doc_list_context(session, request.corpus, current_user)

                if doc_context == "NO_DOCUMENTS":
                    doc_sys = (
                        f"You are F.A.L.T.U, a helpful enterprise AI assistant. "
                        f"No documents are uploaded in the '{request.corpus}' knowledge base yet. "
                        f"Tell the user to upload documents via the 'Docs' section to get started."
                    )
                else:
                    doc_sys = (
                        f"You are F.A.L.T.U, a helpful enterprise AI assistant. "
                        f"Here is the EXACT list of documents in the '{request.corpus}' knowledge base:\n\n"
                        f"{doc_context}\n\n"
                        f"List these documents clearly. Include file name, type, and size. "
                        f"Be friendly and tell the user they can ask questions about any of these."
                    )

                async for token in _llm.stream_chat(
                    query=request.query,
                    system_prompt=doc_sys,
                    temperature=0.3,
                    max_tokens=1024,
                ):
                    full_response += token
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

            # Branch B: Cache hit
            elif cached_response:
                logger.info("Cache hit", query=request.query[:50])
                for token in cached_response["response"].split(" "):
                    yield f"data: {json.dumps({'type': 'token', 'content': token + ' '})}\n\n"
                sources = cached_response.get("sources", [])
                full_response = cached_response["response"]

            # Branch C: Full RAG pipeline
            else:
                # Step 6: HyDE — expand short queries for better retrieval
                retrieval_query = request.query
                if settings.hyde_enabled and len(request.query.split()) < 20:
                    logger.info("HyDE expansion starting", original=request.query[:40])
                    retrieval_query = await _llm.generate_hyde(request.query)
                    logger.info("HyDE done", expanded=retrieval_query[:80])

                # Step 7: Retrieve chunks
                retrieval_start = time.time()
                chunks = await _retriever.retrieve(
                    query=retrieval_query,
                    corpus=request.corpus,
                    top_k=settings.retrieval_top_k,
                )
                retrieval_ms = int((time.time() - retrieval_start) * 1000)

                # Graceful empty context
                if not chunks:
                    logger.warning("No chunks found", corpus=request.corpus)
                    no_info = (
                        "I couldn't find relevant information in the uploaded documents for your question.\n\n"
                        "**Possible reasons:**\n"
                        "- The documents don't cover this topic\n"
                        "- Try rephrasing with different keywords\n"
                        "- Check the **Docs** page — documents need status to be searchable\n\n"
                        f"*Searched in: **{request.corpus}** knowledge base*"
                    )
                    for word in no_info.split(" "):
                        yield f"data: {json.dumps({'type': 'token', 'content': word + ' '})}\n\n"
                    full_response = no_info

                else:
                    # Step 8: Rerank
                    if settings.enable_reranking and len(chunks) > 1:
                        chunks = _reranker.rerank(
                            query=request.query,
                            chunks=chunks,
                            top_k=settings.rerank_top_k,
                        )

                    # Step 9: Build context with token limit guard
                    context_parts = []
                    total_chars = 0
                    max_chars = settings.max_context_tokens * 4
                    for c in chunks:
                        if total_chars + len(c["text"]) > max_chars:
                            break
                        context_parts.append(f"[Source: {c['source']}]\n{c['text']}")
                        total_chars += len(c["text"])

                    context = "\n\n---\n\n".join(context_parts)
                    sources = build_citations(chunks)

                    system_prompt = (
                        "You are F.A.L.T.U (Fantastically Accurate Language & Thinking Unit), "
                        "a helpful enterprise AI assistant.\n\n"
                        "Answer the user's question using the document context below. Rules:\n"
                        "- Answer clearly and concisely if the context contains the answer.\n"
                        "- If the answer is NOT in the context, say: "
                        "'I don't have enough information in the provided documents to answer that.'\n"
                        "- Always cite your source (e.g. 'According to [filename]...').\n"
                        "- Use markdown: bullet points, bold text, code blocks where appropriate.\n"
                        "- Be aware of the conversation history — if the user is following up, answer in context.\n"
                        "- Do NOT repeat previous answers.\n\n"
                        f"CONTEXT FROM DOCUMENTS:\n{context}"
                    )

                    # Step 10: Load conversation history
                    history = _load_recent_history(
                        session,
                        db_session.id,
                        limit=settings.conversation_history_limit,
                    )

                    # Step 11: Stream with history
                    logger.info(
                        "Streaming from Groq",
                        model=settings.groq_model,
                        chunks=len(chunks),
                        history_turns=len(history),
                        retrieval_ms=retrieval_ms,
                    )

                    async for token in _llm.stream_chat_with_history(
                        query=request.query,
                        system_prompt=system_prompt,
                        history=history,
                        temperature=request.temperature,
                        max_tokens=max(request.max_tokens, 1024),
                    ):
                        full_response += token
                        yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

                    # Update cache
                    if settings.enable_semantic_cache and full_response:
                        await _cache.set(
                            query=request.query,
                            response=full_response,
                            sources=sources,
                            corpus=request.corpus,
                        )

            # Output guardrail
            if full_response:
                full_response, _ = _guardrail.check_output(full_response)

            # Save to database
            total_ms = int((time.time() - start_time) * 1000)
            session.add(ChatMessage(session_id=db_session.id, role="user", content=request.query))
            assistant_msg = ChatMessage(
                session_id=db_session.id,
                role="assistant",
                content=full_response,
                sources=json.dumps(sources),
                latency_ms=total_ms,
            )
            session.add(assistant_msg)
            session.commit()
            session.refresh(assistant_msg)

            yield f"data: {json.dumps({'type': 'metadata', 'message_id': assistant_msg.id, 'sources': sources, 'latency_ms': total_ms, 'session_id': session_id, 'from_cache': cached_response is not None})}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error("Chat error", error=str(e))
            err = str(e).lower()
            if "groq" in err or "api" in err or "rate" in err or "limit" in err:
                msg = "The AI service is temporarily unavailable or rate-limited. Please try again in a moment."
            elif "chroma" in err or "retriev" in err or "embed" in err:
                msg = "Could not search documents right now. Please try again."
            elif "context" in err and "length" in err:
                msg = "Your conversation is very long. Please start a fresh chat session."
            else:
                msg = "Something went wrong. Please try again."
            yield f"data: {json.dumps({'type': 'error', 'content': msg})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/feedback", summary="Submit feedback on a response")
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
        raise HTTPException(status_code=400, detail="Rating must be 1 or -1")
    session.add(Feedback(message_id=message_id, user_id=current_user.id, rating=rating, comment=comment))
    session.commit()
    return {"message": "Feedback recorded. Thank you!"}


@router.get("/sessions", summary="Get user's chat session history")
async def get_sessions(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: int = 20,
):
    """Returns a list of the user's recent chat sessions."""
    return session.exec(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.updated_at.desc())
        .limit(limit)
    ).all()


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
    return session.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == chat_session.id)
        .order_by(ChatMessage.created_at.asc())
    ).all()
