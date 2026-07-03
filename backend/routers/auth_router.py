"""
routers/auth_router.py — Authentication Endpoints
===================================================
POST /auth/login  → Returns JWT token
POST /auth/logout → Invalidates session (client-side)
GET  /auth/me     → Returns current user info
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session

from auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
)
from models import User, UserRead
from main import get_session

router = APIRouter()


@router.post("/login", summary="Login and get access token")
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[Session, Depends(get_session)],
):
    """
    Login with username and password.
    
    Returns a JWT bearer token — include this in the Authorization header:
    `Authorization: Bearer <token>`
    """
    user = authenticate_user(session, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Update last login timestamp
    user.last_login = datetime.utcnow()
    session.add(user)
    session.commit()

    access_token = create_access_token(data={"sub": user.username})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in_hours": 24,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_admin": user.is_admin,
            "permissions": user.permissions.split(","),
        },
    }


@router.post("/logout", summary="Logout (client-side token removal)")
async def logout():
    """
    Logout endpoint.
    
    Since we use stateless JWTs, the token is simply discarded on the client.
    For stricter security, implement a token blacklist in the cache layer.
    """
    return {"message": "Logged out successfully. Please discard your token."}


@router.get("/me", response_model=UserRead, summary="Get current user info")
async def get_me(current_user: Annotated[User, Depends(get_current_user)]):
    """Returns the profile of the currently logged-in user."""
    return current_user
