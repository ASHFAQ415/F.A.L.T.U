"""
routers/admin.py — Admin Endpoints
=====================================
Admin-only endpoints for user management and system stats.
All require is_admin=True in the user's JWT.
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, func, select

from auth import create_user_in_db, get_user_by_username, require_admin
from main import get_session
from models import ChatMessage, Document, Feedback, User, UserCreate, UserRead, UserUpdate

router = APIRouter()
logger = structlog.get_logger()


# ── User Management ───────────────────────────────────────

@router.get("/users", response_model=list[UserRead], summary="List all users")
async def list_users(
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    """(Admin) Get a list of all registered users."""
    return session.exec(select(User)).all()


@router.post("/users", response_model=UserRead, summary="Create a new user")
async def create_user(
    user_data: UserCreate,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    """(Admin) Create a new user account."""
    existing = get_user_by_username(session, user_data.username)
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken.")

    user = create_user_in_db(
        session=session,
        username=user_data.username,
        email=user_data.email,
        password=user_data.password,
        full_name=user_data.full_name,
        is_admin=user_data.is_admin,
        permissions=user_data.permissions,
    )
    logger.info("👤 User created by admin", new_user=user.username, by=admin.username)
    return user


@router.patch("/users/{user_id}", response_model=UserRead, summary="Update a user")
async def update_user(
    user_id: int,
    updates: UserUpdate,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    """(Admin) Update a user's permissions, active status, etc."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    update_data = updates.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)

    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.delete("/users/{user_id}", summary="Delete a user")
async def delete_user(
    user_id: int,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    """(Admin) Delete a user account."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")

    session.delete(user)
    session.commit()
    return {"message": f"User '{user.username}' deleted."}


# ── System Stats ──────────────────────────────────────────

@router.get("/stats", summary="System usage statistics")
async def get_stats(
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[Session, Depends(get_session)],
):
    """(Admin) Get system-wide usage statistics for the dashboard."""
    total_users = session.exec(select(func.count(User.id))).one()
    total_docs = session.exec(select(func.count(Document.id))).one()
    total_messages = session.exec(select(func.count(ChatMessage.id))).one()
    total_feedback = session.exec(select(func.count(Feedback.id))).one()

    # Positive feedback rate
    positive = session.exec(
        select(func.count(Feedback.id)).where(Feedback.rating == 1)
    ).one()
    feedback_rate = (positive / total_feedback * 100) if total_feedback > 0 else 0

    # Docs by corpus
    docs_by_corpus = {}
    docs = session.exec(select(Document)).all()
    for doc in docs:
        docs_by_corpus[doc.corpus] = docs_by_corpus.get(doc.corpus, 0) + 1

    # Avg response latency
    latencies = session.exec(
        select(ChatMessage.latency_ms).where(
            ChatMessage.role == "assistant",
            ChatMessage.latency_ms != None,
        )
    ).all()
    avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0

    return {
        "total_users": total_users,
        "total_documents": total_docs,
        "total_messages": total_messages,
        "total_feedback": total_feedback,
        "positive_feedback_rate_pct": round(feedback_rate, 1),
        "documents_by_corpus": docs_by_corpus,
        "avg_response_latency_ms": avg_latency,
    }
