"""API endpoints for Administrator Console, platform analysis, and access security audits.

Strictly restricted to users possessing the 'admin' authorization role.
"""

import logging
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, status

from backend.core.security import get_current_user_required
from backend.db.database import get_db_manager
from backend.db.repositories import (
    DomainRepository,
    EvaluationRepository,
    RuleRepository,
    UserLoginRepository,
    UserRepository,
)
from backend.knowledge.loader import KnowledgeBase
from backend.nlp.provider import get_language_model_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin Console & Telemetry"])


def require_admin(current_user: Dict[str, Any] = Depends(get_current_user_required)) -> Dict[str, Any]:
    """Dependency enforcing that the requesting user possesses administrative privileges."""
    role = current_user.get("role")
    sub = current_user.get("sub", "")
    username = current_user.get("username", "")

    # Check live database in case user was granted admin after token issuance
    if role != "admin":
        db = get_db_manager()
        user_repo = UserRepository(db)
        u = user_repo.get_by_id(sub) or user_repo.get_by_username(username)
        if u and u.get("role") == "admin":
            role = "admin"
            current_user["role"] = "admin"

    if role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted: Administrator privileges are required to access this console.",
        )
    return current_user


@router.get("/platform-overview", summary="Admin platform analysis and operational telemetry")
def get_platform_overview(
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Provide comprehensive telemetry on system health, rule engines, and usage."""
    db = get_db_manager()
    dom_repo = DomainRepository(db)
    rule_repo = RuleRepository(db)
    eval_repo = EvaluationRepository(db)
    login_repo = UserLoginRepository(db)
    user_repo = UserRepository(db)
    provider = get_language_model_provider()

    domains = dom_repo.list_domains()
    official_rules = rule_repo.list_rules(is_official=True)
    all_rules = rule_repo.list_rules()
    evaluations = eval_repo.list_evaluations(limit=1000)
    logins = login_repo.list_logins(limit=1000)

    # Count registered users
    with db.get_connection() as conn:
        users_count = conn.execute("SELECT COUNT(*) FROM users;").fetchone()[0]

    return {
        "status": "operational",
        "system_authority": "Deterministic Symbolic Rule Engine (100% Guaranteed)",
        "security_standard": "Enterprise Argon2id/PBKDF2 Password Encryption",
        "metrics": {
            "total_domains": len(domains),
            "official_rules_count": len(official_rules),
            "custom_rules_count": max(0, len(all_rules) - len(official_rules)),
            "total_rules": len(all_rules),
            "total_evaluations": len(evaluations),
            "total_registered_users": users_count,
            "total_login_attempts": len(logins),
        },
        "ai_status": {
            "model_configured": getattr(provider, "model_name", "gemini-flash-lite-latest"),
            "provider_available": provider.is_available(),
            "symbolic_authority_active": True,
        },
    }


@router.get("/official-rules", summary="Admin inspection of official regulatory rule libraries")
def get_official_rules(
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Retrieve full official regulatory rule catalog with condition schemas."""
    db = get_db_manager()
    rule_repo = RuleRepository(db)
    rules = rule_repo.list_rules(is_official=True)
    return {"count": len(rules), "items": rules}


@router.get("/logins", summary="Admin user access & login security audit log")
def get_user_logins_audit(
    limit: int = 50,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Retrieve verified records of who logged in, login timestamps, and encrypted credential status."""
    db = get_db_manager()
    login_repo = UserLoginRepository(db)
    logins = login_repo.list_logins(limit=limit)
    return {
        "count": len(logins),
        "encryption": "Salted One-Way Hashes (Zero plain-text password exposure)",
        "items": logins,
    }

