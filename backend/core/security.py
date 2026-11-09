"""Security, input validation, authentication, and credential protection utilities for RuleWise AI.

Strict security policies:
- No dynamic code execution (eval, exec, compile, subprocess).
- Secrets must never be logged, printed, or leaked in API responses.
- User input is treated as untrusted and strictly sanitized.
- Cryptographically secure session tokens and password verification.
"""

import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from typing import Any, Dict, Optional
from fastapi import Depends, Header, HTTPException, status


def hash_password(password: str) -> str:
    """Hash a plaintext password using PBKDF2-HMAC-SHA256 with a cryptographically secure salt."""
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000
    )
    return f"{salt}${key.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored PBKDF2-HMAC-SHA256 hash."""
    if not password_hash or "$" not in password_hash:
        return False
    salt, expected_hex = password_hash.split("$", 1)
    key = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000
    )
    return hmac.compare_digest(key.hex(), expected_hex)

logger = logging.getLogger(__name__)

# Server-side token signing secret (persisted or randomized per instance)
_JWT_SECRET = secrets.token_hex(32)
TOKEN_EXPIRY_SECONDS = 86400 * 7  # 7 days


def sanitize_user_input(text: str, max_length: int = 2000) -> str:
    """Sanitize and validate untrusted user input strings.

    Args:
        text: Raw user input text.
        max_length: Maximum allowed string length.

    Returns:
        Cleaned, stripped string safe for downstream parsing.

    Raises:
        ValueError: If input is empty or exceeds maximum permitted length.
    """
    if not isinstance(text, str):
        raise ValueError(f"User input must be a string, got {type(text).__name__}")

    # Remove null bytes and non-printable control characters (except newline, tab, carriage return)
    cleaned = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
    cleaned = cleaned.strip()

    if not cleaned:
        raise ValueError("User message cannot be empty or purely whitespace.")

    if len(cleaned) > max_length:
        raise ValueError(f"User message length ({len(cleaned)}) exceeds limit of {max_length} characters.")

    return cleaned


def mask_secret(secret: Optional[str]) -> str:
    """Safely mask sensitive credentials for logging or debugging."""
    if not secret:
        return "[NOT CONFIGURED]"
    if len(secret) <= 8:
        return "***"
    return f"{secret[:4]}...{secret[-4:]}"


def create_access_token(user_id: str, username: str, role: str = "user") -> str:
    """Generate a signed, tamper-proof access token (base64 JSON + HMAC-SHA256 signature)."""
    payload = {
        "sub": user_id,
        "name": username,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_EXPIRY_SECONDS,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("utf-8").rstrip("=")
    signature = hmac.new(
        _JWT_SECRET.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"{payload_b64}.{signature}"


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify and decode a signed access token. Returns None if expired or tampered."""
    if not token or "." not in token:
        return None
    try:
        payload_b64, signature = token.split(".", 1)
        expected_sig = hmac.new(
            _JWT_SECRET.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None

        # Add padding back if necessary
        rem = len(payload_b64) % 4
        padded = payload_b64 + ("=" * ((4 - rem) % 4))
        payload_data = json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8"))

        if payload_data.get("exp", 0) < time.time():
            return None  # Expired

        return payload_data
    except Exception as exc:
        logger.debug("Token verification failure: %s", exc)
        return None


def get_current_user_optional(authorization: Optional[str] = Header(None)) -> Optional[Dict[str, Any]]:
    """Optional user dependency: returns user dict if valid Bearer token provided, else None."""
    if not authorization:
        return None
    parts = authorization.strip().split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return decode_access_token(parts[1])
    return None


def get_current_user_required(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Required user dependency: raises HTTP 401 if not authenticated."""
    user = get_current_user_optional(authorization)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required for this operation. Please log in or provide a valid Bearer token.",
        )
    return user


def require_admin(user: Dict[str, Any] = Depends(get_current_user_required)) -> Dict[str, Any]:
    """Admin-only dependency: raises HTTP 403 if user does not hold admin privileges."""
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required to modify official system resources.",
        )
    return user
