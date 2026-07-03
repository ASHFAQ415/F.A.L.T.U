"""
auth.py — Authentication & Authorization
==========================================
Handles:
  - User login → JWT token issuance
  - JWT verification on protected routes
  - Password hashing with bcrypt
  - Admin user creation on first startup

No external IdP needed — everything in SQLite.
"""

from datetime import datetime, timedelta
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import Session, select

from config import get_settings
from models import User

settings = get_settings()

# ── Password Hashing ──────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── OAuth2 token URL (used by FastAPI docs UI) ────────────
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ─────────────────────────────────────────────────────────
# Password Utilities
# ─────────────────────────────────────────────────────────

def hash_password(plain_password: str) -> str:
    """Hash a plain-text password using bcrypt."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a plain-text password against a stored bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


# ─────────────────────────────────────────────────────────
# JWT Token Utilities
# ─────────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a signed JWT access token.
    
    Args:
        data: Payload to encode (typically {"sub": username})
        expires_delta: How long the token is valid (default: from settings)
    
    Returns:
        Signed JWT string
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(hours=settings.jwt_expiry_hours)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """
    Decode and verify a JWT token.
    Raises HTTPException 401 if token is invalid or expired.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ─────────────────────────────────────────────────────────
# Database User Operations
# ─────────────────────────────────────────────────────────

def get_user_by_username(session: Session, username: str) -> Optional[User]:
    """Fetch a user from SQLite by username."""
    return session.exec(select(User).where(User.username == username)).first()


def get_user_by_id(session: Session, user_id: int) -> Optional[User]:
    """Fetch a user from SQLite by ID."""
    return session.get(User, user_id)


def authenticate_user(session: Session, username: str, password: str) -> Optional[User]:
    """
    Verify username + password against the database.
    Returns the User object if valid, None if not.
    """
    user = get_user_by_username(session, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user


def create_user_in_db(
    session: Session,
    username: str,
    email: str,
    password: str,
    full_name: Optional[str] = None,
    is_admin: bool = False,
    permissions: str = "public",
) -> User:
    """Create a new user in the database."""
    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        is_admin=is_admin,
        permissions=permissions,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


# ─────────────────────────────────────────────────────────
# FastAPI Dependency — Current User
# ─────────────────────────────────────────────────────────

def get_db_session():
    """
    Dependency: yields a SQLite session for each request.
    Imported from main.py to avoid circular imports.
    """
    # This is overridden in main.py with the actual engine
    raise NotImplementedError("Override get_db_session in main.py")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    """
    FastAPI dependency that extracts and validates the current user from JWT.
    
    Usage:
        @app.get("/protected")
        async def route(user: User = Depends(get_current_user)):
            ...
    """
    payload = decode_token(token)
    username: str = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user identifier.",
        )

    # Import here to avoid circular imports
    from main import get_session
    from sqlmodel import Session as SQLSession

    # We need a session — get one from the engine directly
    from main import engine
    with SQLSession(engine) as session:
        user = get_user_by_username(session, username)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account disabled.",
        )

    return user


async def require_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    FastAPI dependency that requires the current user to be an admin.
    Use this on admin-only endpoints.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this resource.",
        )
    return current_user
