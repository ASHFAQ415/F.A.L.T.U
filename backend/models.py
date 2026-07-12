"""
models.py — Database Models
=============================
SQLModel (= SQLAlchemy + Pydantic) models for SQLite.
Covers: Users, Documents, Chunks, ChatHistory, Feedback.

SQLite is used for all relational data — zero cost, zero setup.
ChromaDB (separate) handles vector embeddings.
"""

from datetime import datetime
from typing import Optional
from sqlmodel import Field, Relationship, SQLModel


# ═══════════════════════════════════════════════════════════
# USER MODELS
# ═══════════════════════════════════════════════════════════

class UserBase(SQLModel):
    username: str = Field(index=True, unique=True, min_length=3, max_length=50)
    email: str = Field(index=True, unique=True)
    full_name: Optional[str] = None
    is_active: bool = True
    is_admin: bool = False
    # Comma-separated corpus permissions, e.g. "public,engineering,hr"
    permissions: str = Field(default="public")


class User(UserBase, table=True):
    """Stored in SQLite users table"""
    id: Optional[int] = Field(default=None, primary_key=True)
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None

    # Relationships
    sessions: list["ChatSession"] = Relationship(back_populates="user")
    feedback: list["Feedback"] = Relationship(back_populates="user")


class UserCreate(UserBase):
    """Request body when creating a new user"""
    password: str = Field(min_length=8)


class UserRead(UserBase):
    """Safe response — never exposes hashed_password"""
    id: int
    created_at: datetime
    last_login: Optional[datetime]


class UserUpdate(SQLModel):
    """Partial update for user settings"""
    full_name: Optional[str] = None
    permissions: Optional[str] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None


# ═══════════════════════════════════════════════════════════
# DOCUMENT MODELS
# ═══════════════════════════════════════════════════════════

class Document(SQLModel, table=True):
    """Tracks uploaded documents and their ingestion status"""
    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str
    original_filename: str
    file_type: str                     # "pdf", "docx", "md", "txt"
    file_size_bytes: int
    corpus: str = Field(default="public", index=True)
    # Comma-separated required permissions to view this doc
    required_permissions: str = Field(default="public")

    status: str = Field(default="pending")   # pending | processing | ready | error
    error_message: Optional[str] = None
    chunk_count: int = Field(default=0)

    uploaded_by: Optional[int] = Field(default=None, foreign_key="user.id")
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None

    # MD5 hash of file content (for deduplication)
    content_hash: Optional[str] = Field(default=None, index=True)


# ═══════════════════════════════════════════════════════════
# CHAT SESSION & MESSAGE MODELS
# ═══════════════════════════════════════════════════════════

class ChatSession(SQLModel, table=True):
    """Groups messages into a conversation"""
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(index=True, unique=True)   # UUID
    title: Optional[str] = None                         # Auto-generated from first query
    user_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    user: Optional[User] = Relationship(back_populates="sessions")
    messages: list["ChatMessage"] = Relationship(back_populates="session")


class ChatMessage(SQLModel, table=True):
    """Individual message in a chat session"""
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="chatsession.id")
    role: str                          # "user" or "assistant"
    content: str
    sources: Optional[str] = None      # JSON string of citation sources
    latency_ms: Optional[int] = None   # How long the response took
    created_at: datetime = Field(default_factory=datetime.utcnow)

    session: Optional[ChatSession] = Relationship(back_populates="messages")


# ═══════════════════════════════════════════════════════════
# FEEDBACK MODEL
# ═══════════════════════════════════════════════════════════

class Feedback(SQLModel, table=True):
    """👍 / 👎 feedback on chatbot answers"""
    id: Optional[int] = Field(default=None, primary_key=True)
    message_id: int = Field(foreign_key="chatmessage.id")
    user_id: int = Field(foreign_key="user.id")
    rating: int                        # 1 = thumbs up, -1 = thumbs down
    comment: Optional[str] = None      # Optional text feedback
    created_at: datetime = Field(default_factory=datetime.utcnow)

    user: Optional[User] = Relationship(back_populates="feedback")


# ═══════════════════════════════════════════════════════════
# API REQUEST / RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════════════

class ChatRequest(SQLModel):
    """Body of POST /v1/chat"""
    query: str = Field(min_length=1, max_length=2000)
    session_id: Optional[str] = None   # Omit for new session
    corpus: str = Field(default="public")
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)
    max_tokens: int = Field(default=1024, ge=50, le=4096)


class FeedbackRequest(SQLModel):
    """Body of POST /v1/feedback"""
    message_id: int
    rating: int = Field(ge=-1, le=1)
    comment: Optional[str] = Field(default=None, max_length=500)


class IngestRequest(SQLModel):
    """Metadata for document ingestion"""
    corpus: str = Field(default="public")
    required_permissions: str = Field(default="public")


class HealthResponse(SQLModel):
    """GET /health response"""
    status: str
    ollama_available: bool
    chroma_available: bool
    model: str
    version: str = "1.0.0"
