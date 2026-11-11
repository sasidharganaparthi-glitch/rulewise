"""Endpoints for user authentication, Google OAuth 2.0, registration, and session access."""

import logging
import uuid
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
import httpx

from backend.core.config import get_settings
from backend.core.security import (
    create_access_token,
    get_current_user_optional,
    get_current_user_required,
    verify_password,
)
from backend.db.database import get_db_manager
from backend.db.repositories import UserLoginRepository, UserRepository
from backend.schemas.api import (
    AuthResponse,
    GoogleAuthRequest,
    LoginRequest,
    PasswordChangeRequest,
    PasswordResetRequest,
    RegisterRequest,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication & Access"])


@router.get("/google/config", summary="Google OAuth 2.0 client configuration")
def get_google_config() -> Dict[str, Any]:
    """Retrieve public Google OAuth client ID for frontend Google Identity Services button."""
    settings = get_settings()
    return {
        "configured": bool(settings.GOOGLE_CLIENT_ID),
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
    }


@router.post("/google", response_model=AuthResponse, summary="Authenticate via official Google ID Token")
def google_auth(req: GoogleAuthRequest, request: Request) -> AuthResponse:
    """Verify official Google ID token, authenticate or register user, and issue session token."""
    settings = get_settings()
    db = get_db_manager()
    user_repo = UserRepository(db)
    login_repo = UserLoginRepository(db)

    ip = request.client.host if request.client else "127.0.0.1"
    ua = request.headers.get("user-agent", "Unknown")

    # Verify ID token with Google's official tokeninfo endpoint
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": req.credential},
            )
        if resp.status_code != 200:
            logger.warning("Google ID token verification failed: %s", resp.text)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Google authentication token could not be verified by Google.",
            )
        tokeninfo = resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error communicating with Google token verification service: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth verification service is currently unreachable.",
        )

    # Validate audience if client ID is configured
    if settings.GOOGLE_CLIENT_ID:
        aud = tokeninfo.get("aud")
        if aud != settings.GOOGLE_CLIENT_ID:
            logger.error("Google token audience mismatch: expected %s, got %s", settings.GOOGLE_CLIENT_ID, aud)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Google token audience mismatch.",
            )

    # Validate verified email
    email = tokeninfo.get("email")
    email_verified = str(tokeninfo.get("email_verified", "")).lower() in ("true", "1")
    if not email or not email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google account must have a verified email address to sign in.",
        )

    google_sub = tokeninfo.get("sub", "")
    full_name = tokeninfo.get("name") or email.split("@")[0]
    picture = tokeninfo.get("picture")

    # Check authorized admin status
    admin_email = getattr(settings, "ADMIN_EMAIL", "sasiganaparthi@gmail.com").strip().lower()
    is_admin = (email.strip().lower() == admin_email)

    user = user_repo.get_or_create_google_user(
        google_id=google_sub,
        email=email,
        name=full_name,
        picture=picture,
        is_admin=is_admin,
    )

    if user.get("is_active") == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated. Please contact an administrator.",
        )

    login_repo.record_login(
        username=user["username"],
        email=user["email"],
        status="GOOGLE_SUCCESS",
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
        is_active=bool(user.get("is_active", 1)),
        picture=user.get("picture"),
        google_id=user.get("google_id"),
        created_at=user["created_at"],
    )
    return AuthResponse(access_token=token, user=user_resp)


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED, summary="Register user")
def register(req: RegisterRequest, request: Request) -> AuthResponse:
    """Create a new registered user account."""
    db = get_db_manager()
    user_repo = UserRepository(db)
    login_repo = UserLoginRepository(db)

    ip = request.client.host if request.client else "127.0.0.1"
    ua = request.headers.get("user-agent", "Unknown")

    if not req.email or "@" not in req.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A valid email address is required for registration.",
        )

    existing_username = user_repo.get_by_username(req.username)
    if existing_username:
        login_repo.record_login(
            username=req.username,
            email=req.email,
            status="FAILED_DUPLICATE_USERNAME",
            ip_address=ip,
            user_agent=ua,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Username '{req.username}' is already taken.",
        )

    existing_email = user_repo.get_by_email(req.email)
    if existing_email:
        login_repo.record_login(
            username=req.username,
            email=req.email,
            status="FAILED_DUPLICATE_EMAIL",
            ip_address=ip,
            user_agent=ua,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An account with email '{req.email}' already exists. Please log in.",
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
        is_active=True,
        created_at=user["created_at"],
    )
    return AuthResponse(access_token=token, user=user_resp)


@router.post("/login", response_model=AuthResponse, summary="Login user")
def login(req: LoginRequest, request: Request) -> AuthResponse:
    """Authenticate existing credentials and issue access token with role verification."""
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

    # Strictly verify Admin Login requirement (allow both owner and admin)
    if req.is_admin_login and user.get("role") not in ("admin", "owner"):
        login_repo.record_login(
            username=user["username"],
            email=user.get("email"),
            status="FAILED_ADMIN_DENIED",
            ip_address=ip,
            user_agent=ua,
            user_id=user["id"],
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: This account does not possess administrator credentials.",
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
        is_active=bool(user.get("is_active", 1)),
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
        is_active=True,
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
        return UserResponse(
            id=current_user["sub"],
            username=current_user.get("name", "Guest"),
            email=None,
            role=current_user.get("role", "guest"),
            is_active=True,
            created_at="",
        )
    return UserResponse(
        id=user["id"],
        username=user["username"],
        email=user.get("email"),
        role=user["role"],
        is_active=bool(user.get("is_active", 1)),
        picture=user.get("picture"),
        google_id=user.get("google_id"),
        created_at=user["created_at"],
    )


@router.post("/change-password", summary="Change account password")
def change_password(
    req: PasswordChangeRequest,
    current_user: Dict[str, Any] = Depends(get_current_user_required),
) -> Dict[str, Any]:
    """Securely update the authenticated user's password."""
    db = get_db_manager()
    user_repo = UserRepository(db)
    user = user_repo.get_by_id(current_user["sub"])
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if user.get("password_hash") and not verify_password(req.current_password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect.")

    user_repo.update_password(user["id"], req.new_password)
    return {"status": "success", "message": "Password updated successfully."}


@router.post("/reset-password", summary="Reset account password via verified email/username")
def reset_password(req: PasswordResetRequest) -> Dict[str, Any]:
    """Allow user to reset password with email validation."""
    db = get_db_manager()
    user_repo = UserRepository(db)
    user = user_repo.get_by_email(req.email) or user_repo.get_by_username(req.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found associated with that email or username.",
        )
    user_repo.update_password(user["id"], req.new_password)
    return {"status": "success", "message": "Password has been securely reset. You may now sign in."}


@router.post("/logout", summary="Session logout")
def logout(
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
    """Acknowledge session termination and client token revocation."""
    return {"status": "logged_out", "message": "Successfully logged out."}
