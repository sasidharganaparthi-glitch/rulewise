"""Endpoints for user authentication, registration, and guest access sessions."""

import logging
import uuid
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.core.security import (
    create_access_token,
    get_current_user_optional,
    get_current_user_required,
)
from backend.db.database import get_db_manager
from backend.db.repositories import UserLoginRepository, UserRepository
from backend.schemas.api import AuthResponse, LoginRequest, RegisterRequest, UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication & Access"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED, summary="Register user")
def register(req: RegisterRequest, request: Request) -> AuthResponse:
    """Create a new registered user account."""
    db = get_db_manager()
    user_repo = UserRepository(db)
    login_repo = UserLoginRepository(db)

    ip = request.client.host if request.client else "127.0.0.1"
    ua = request.headers.get("user-agent", "Unknown")

    existing = user_repo.get_by_username(req.username)
    if existing:
        login_repo.record_login(
            username=req.username,
            email=req.email,
            status="FAILED_DUPLICATE",
            ip_address=ip,
            user_agent=ua,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Username '{req.username}' is already taken.",
        )

    user = user_repo.create_user(
        username=req.username,
        password=req.password,
        email=req.email,
        role="user",
    )
    login_repo.record_login(
        username=user["username"],
        email=user.get("email"),
        status="REGISTERED",
        ip_address=ip,
        user_agent=ua,
        user_id=user["id"],
    )
    token = create_access_token(user_id=user["id"], username=user["username"], role=user["role"])
    user_resp = UserResponse(
        id=user["id"],
        username=user["username"],
        email=user.get("email"),
        role=user["role"],
        created_at=user["created_at"],
    )
    return AuthResponse(access_token=token, user=user_resp)


@router.post("/login", response_model=AuthResponse, summary="Login user")
def login(req: LoginRequest, request: Request) -> AuthResponse:
    """Authenticate existing credentials and issue access token."""
    db = get_db_manager()
    user_repo = UserRepository(db)
    login_repo = UserLoginRepository(db)

    ip = request.client.host if request.client else "127.0.0.1"
    ua = request.headers.get("user-agent", "Unknown")

    user = user_repo.authenticate(username=req.username, password=req.password)
    if not user:
        login_repo.record_login(
            username=req.username,
            email=req.username if "@" in req.username else None,
            status="FAILED",
            ip_address=ip,
            user_agent=ua,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/email or password.",
        )

    login_repo.record_login(
        username=user["username"],
        email=user.get("email"),
        status="SUCCESS",
        ip_address=ip,
        user_agent=ua,
        user_id=user["id"],
    )

    token = create_access_token(user_id=user["id"], username=user["username"], role=user["role"])
    user_resp = UserResponse(
        id=user["id"],
        username=user["username"],
        email=user.get("email"),
        role=user["role"],
        created_at=user["created_at"],
    )
    return AuthResponse(access_token=token, user=user_resp)


@router.post("/guest", response_model=AuthResponse, summary="Create temporary guest session")
def create_guest_session() -> AuthResponse:
    """Issue a zero-friction guest session token enabling immediate platform exploration."""
    guest_id = f"guest_{uuid.uuid4().hex[:8]}"
    guest_name = f"Guest_{guest_id[-4:]}"
    token = create_access_token(user_id=guest_id, username=guest_name, role="guest")
    user_resp = UserResponse(
        id=guest_id,
        username=guest_name,
        email=None,
        role="guest",
        created_at="",
    )
    return AuthResponse(access_token=token, user=user_resp)


@router.get("/me", response_model=UserResponse, summary="Current user profile")
def get_current_user_profile(
    current_user: Dict[str, Any] = Depends(get_current_user_required),
) -> UserResponse:
    """Retrieve details of the active authenticated user."""
    db = get_db_manager()
    user_repo = UserRepository(db)
    user = user_repo.get_by_id(current_user["sub"])
    if not user:
        # If guest
        return UserResponse(
            id=current_user["sub"],
            username=current_user.get("name", "Guest"),
            email=None,
            role=current_user.get("role", "guest"),
            created_at="",
        )
    return UserResponse(
        id=user["id"],
        username=user["username"],
        email=user.get("email"),
        role=user["role"],
        created_at=user["created_at"],
    )

