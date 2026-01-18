"""
Authentication API endpoints.

Provides login/logout functionality with JWT tokens.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from admin_ui.backend.auth import (
    User,
    authenticate_user,
    create_access_token,
    get_current_user,
)

router = APIRouter()


class LoginRequest(BaseModel):
    """Login request body."""

    username: str
    password: str


class LoginResponse(BaseModel):
    """Login response."""

    access_token: str
    token_type: str
    user: User


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Authenticate user and return JWT token."""
    user = authenticate_user(request.username, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.username})

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=user,
    )


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """
    Logout current user.

    Note: With JWT tokens, logout is primarily handled client-side.
    This endpoint exists for consistency and future enhancements.
    """
    return {"message": f"User {current_user.username} logged out successfully"}


@router.get("/me", response_model=User)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user information."""
    return current_user


@router.get("/verify")
async def verify_token(current_user: User = Depends(get_current_user)):
    """Verify if the current token is valid."""
    return {"valid": True, "username": current_user.username}
