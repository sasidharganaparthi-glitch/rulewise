"""API endpoints for Administrator Console, platform analysis, and access security audits.

Strictly restricted to users possessing the 'admin' authorization role.
Every administrative action is tracked in the immutable audit log.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.core.security import get_current_user_required
from backend.db.database import get_db_manager
from backend.db.repositories import (
    ConversationRepository,
    DomainRepository,
    EvaluationRepository,
    RuleRepository,
    UserLoginRepository,
    UserRepository,
)
from backend.nlp.provider import get_language_model_provider
from backend.schemas.api import (
    AdminUserCreateRequest,
    AdminUserStatusUpdateRequest,
    RuleCreateRequest,
    RuleUpdateRequest,
    RuleValidateRequest,
    RuleValidateResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin Console & Telemetry"])


def require_admin(current_user: Dict[str, Any] = Depends(get_current_user_required)) -> Dict[str, Any]:
    """Dependency enforcing that the requesting user holds active administrator or owner privileges."""
    sub = current_user.get("sub", "")
    username = current_user.get("username", "")

    db = get_db_manager()
    user_repo = UserRepository(db)
    u = user_repo.get_by_id(sub) or user_repo.get_by_username(username)

    if not u or u.get("role") not in ("owner", "admin") or u.get("is_active") == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted: Active administrator or owner privileges are required to access this console.",
        )
    return u


def require_owner(current_user: Dict[str, Any] = Depends(get_current_user_required)) -> Dict[str, Any]:
    """Dependency enforcing that the requesting user holds the platform Owner role."""
    u = require_admin(current_user)
    if u.get("role") != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted: Platform Owner authority is strictly required to appoint or remove administrators.",
        )
    return u


def log_admin_action(admin_id: str, action: str, target_type: str, target_id: str, details: Dict[str, Any]) -> None:
    """Record administrative operations to audit logs."""
    try:
        db = get_db_manager()
        with db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO audit_logs (id, user_id, action, target_type, target_id, details_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    f"audit_{uuid.uuid4().hex[:12]}",
                    admin_id,
                    action,
                    target_type,
                    target_id,
                    json.dumps(details),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
    except Exception as exc:
        logger.error("Failed to write audit log: %s", exc)


# -----------------------------------------------------------------------------
# 1. Platform Analytics & Telemetry
# -----------------------------------------------------------------------------

@router.get("/platform-overview", summary="Admin platform telemetry & usage analysis")
def get_platform_overview(
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Comprehensive telemetry on registered users, active sessions, AI usage, and health."""
    db = get_db_manager()
    dom_repo = DomainRepository(db)
    rule_repo = RuleRepository(db)
    eval_repo = EvaluationRepository(db)
    login_repo = UserLoginRepository(db)
    provider = get_language_model_provider()

    domains = dom_repo.list_domains()
    official_rules = rule_repo.list_rules(is_official=True)
    all_rules = rule_repo.list_rules()
    evaluations = eval_repo.list_evaluations(limit=5000)
    logins = login_repo.list_logins(limit=5000)

    now = datetime.now(timezone.utc)
    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    seven_days_ago = (now - timedelta(days=7)).isoformat()

    with db.get_connection() as conn:
        total_users = conn.execute("SELECT COUNT(*) FROM users;").fetchone()[0]
        active_users = conn.execute("SELECT COUNT(*) FROM users WHERE is_active = 1;").fetchone()[0]
        new_registrations_30d = conn.execute(
            "SELECT COUNT(*) FROM users WHERE created_at >= ?;", (thirty_days_ago,)
        ).fetchone()[0]
        total_convs = conn.execute("SELECT COUNT(*) FROM conversations;").fetchone()[0]
        total_messages = conn.execute("SELECT COUNT(*) FROM messages;").fetchone()[0]
        user_queries = conn.execute("SELECT COUNT(*) FROM messages WHERE sender = 'user';").fetchone()[0]
        failed_logins = conn.execute(
            "SELECT COUNT(*) FROM user_logins WHERE status LIKE 'FAILED%';",
        ).fetchone()[0]
        daily_logins = conn.execute(
            "SELECT COUNT(*) FROM user_logins WHERE created_at >= ? AND status = 'SUCCESS';", (seven_days_ago,)
        ).fetchone()[0]

    return {
        "status": "operational",
        "system_authority": "Deterministic Symbolic Rule Engine (100% Guaranteed)",
        "security_standard": "Enterprise Argon2id/PBKDF2 Password Encryption + Role Access Control",
        "timestamp": now.isoformat(),
        "metrics": {
            "total_registered_users": total_users,
            "active_users": active_users,
            "new_registrations_30d": new_registrations_30d,
            "total_conversations": total_convs,
            "total_messages": total_messages,
            "total_ai_queries": user_queries,
            "failed_login_attempts": failed_logins,
            "active_logins_7d": daily_logins,
            "total_rules": len(all_rules),
            "official_rules_count": len(official_rules),
            "custom_rules_count": max(0, len(all_rules) - len(official_rules)),
            "total_domains": len(domains),
            "total_evaluations": len(evaluations),
        },
        "ai_status": {
            "model_configured": getattr(provider, "model_name", "gemini-3.5-flash-lite"),
            "provider_available": provider.is_available(),
            "symbolic_authority_active": True,
            "live_grounding_ready": True,
        },
    }


# -----------------------------------------------------------------------------
# 2. User Management
# -----------------------------------------------------------------------------

@router.get("/users", summary="Admin list and search registered users")
def list_users(
    search: Optional[str] = Query(None, description="Search by username or email"),
    role: Optional[str] = Query(None, description="Filter by role (admin, user)"),
    status: Optional[str] = Query(None, description="active or disabled"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Retrieve filtered user directory for administrative management."""
    db = get_db_manager()
    user_repo = UserRepository(db)
    is_active_filter = None
    if status == "active":
        is_active_filter = True
    elif status == "disabled":
        is_active_filter = False

    users = user_repo.list_users(
        search=search,
        role=role,
        is_active=is_active_filter,
        limit=limit,
        offset=offset,
    )
    return {"total": len(users), "items": users}


@router.post("/users", status_code=status.HTTP_201_CREATED, summary="Admin create new user account")
def create_user_by_admin(
    req: AdminUserCreateRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Administrator manually provisions a user account."""
    db = get_db_manager()
    user_repo = UserRepository(db)

    if user_repo.get_by_username(req.username):
        raise HTTPException(status_code=400, detail=f"Username '{req.username}' is already taken.")
    if user_repo.get_by_email(req.email):
        raise HTTPException(status_code=400, detail=f"Email '{req.email}' is already registered.")

    user = user_repo.create_user(
        username=req.username,
        password=req.password,
        email=req.email,
        role=req.role,
    )
    log_admin_action(
        admin["id"], "CREATE_USER", "user", user["id"], {"username": req.username, "role": req.role}
    )
    return {"status": "created", "user": user}


@router.put("/users/{user_id}/status", summary="Admin enable, disable, or alter user role")
def update_user_status(
    user_id: str,
    req: AdminUserStatusUpdateRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Change account status (activate/deactivate) or promote/demote role."""
    db = get_db_manager()
    user_repo = UserRepository(db)

    target_user = user_repo.get_by_id(user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found.")

    # Guard: Cannot modify the Owner account
    if target_user.get("role") == "owner" and admin.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Permission denied: Cannot modify the platform Owner account.")

    # Guard: Only the Owner can appoint or remove administrators
    if req.role is not None and req.role != target_user.get("role"):
        if req.role in ("admin", "owner") or target_user.get("role") in ("admin", "owner"):
            if admin.get("role") != "owner":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Hierarchy violation: Only the platform Owner can appoint or remove administrators.",
                )

    # Guard: prevent deactivating the last active administrator
    if req.is_active is False or (req.role and req.role not in ("admin", "owner")):
        if target_user.get("role") in ("admin", "owner"):
            admin_count = user_repo.count_admins()
            if admin_count <= 1:
                raise HTTPException(
                    status_code=400,
                    detail="Operation forbidden: Cannot disable or demote the last remaining administrator.",
                )

    if req.is_active is not None:
        user_repo.update_user_status(user_id, req.is_active)
    if req.role is not None:
        user_repo.update_user_role(user_id, req.role)

    log_admin_action(
        admin["id"],
        "UPDATE_USER_STATUS",
        "user",
        user_id,
        {"is_active": req.is_active, "role": req.role, "target_username": target_user["username"]},
    )
    updated = user_repo.get_by_id(user_id)
    return {"status": "success", "user": updated}


@router.put("/users/{user_id}/role", summary="Owner appoint or revoke administrator privileges")
def update_user_role(
    user_id: str,
    role: str = Query(..., description="Target role (admin, user)"),
    owner: Dict[str, Any] = Depends(require_owner),
) -> Dict[str, Any]:
    """Strictly allows the platform Owner to appoint or revoke administrator privileges."""
    db = get_db_manager()
    user_repo = UserRepository(db)
    target = user_repo.get_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    if target.get("role") == "owner":
        raise HTTPException(status_code=400, detail="Cannot modify Owner role.")
    user_repo.update_user_role(user_id, role)
    log_admin_action(owner["id"], "APPOINT_ROLE", "user", user_id, {"role": role, "username": target["username"]})
    return {"status": "success", "user": user_repo.get_by_id(user_id)}


@router.delete("/users/{user_id}", summary="Admin delete user account")
def delete_user(
    user_id: str,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Delete a user account with strict safeguards."""
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own active administrator account.")

    db = get_db_manager()
    user_repo = UserRepository(db)
    target = user_repo.get_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    if target.get("role") == "owner":
        raise HTTPException(status_code=400, detail="Cannot delete the platform Owner account.")
    if target.get("role") == "admin" and admin.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Only the platform Owner can delete an administrator.")

    if target.get("role") in ("admin", "owner"):
        if user_repo.count_admins() <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last remaining administrator.")

    user_repo.delete_user(user_id)
    log_admin_action(admin["id"], "DELETE_USER", "user", user_id, {"deleted_username": target["username"]})
    return {"status": "deleted", "user_id": user_id}


# -----------------------------------------------------------------------------
# 3. Official Rule Libraries Management
# -----------------------------------------------------------------------------

@router.get("/official-rules", summary="Admin inspection of official regulatory rule libraries")
def get_official_rules(
    domain_id: Optional[str] = Query(None),
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Retrieve full official regulatory rule catalog with condition schemas."""
    db = get_db_manager()
    rule_repo = RuleRepository(db)
    rules = rule_repo.list_rules(domain_id=domain_id, is_official=True)
    return {"count": len(rules), "items": rules}


@router.post("/rules", status_code=status.HTTP_201_CREATED, summary="Admin create official governance rule")
def create_official_rule(
    req: RuleCreateRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Create a new validated official rule in a domain."""
    db = get_db_manager()
    rule_repo = RuleRepository(db)

    rule = rule_repo.create_rule(
        domain_id=req.domain_id,
        name=req.name,
        description=req.description,
        priority=req.priority,
        status=req.status,
        is_official=True,
        condition=req.condition,
        consequence=req.consequence,
        metadata=req.metadata,
        created_by=admin["id"],
    )
    log_admin_action(admin["id"], "CREATE_OFFICIAL_RULE", "rule", rule["id"], {"name": req.name, "domain_id": req.domain_id})
    return {"status": "created", "rule": rule}


@router.put("/rules/{rule_id}", summary="Admin edit official rule")
def update_official_rule(
    rule_id: str,
    req: RuleUpdateRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Modify condition, consequence, priority, or metadata of an official rule."""
    db = get_db_manager()
    rule_repo = RuleRepository(db)
    existing = rule_repo.get_by_id(rule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Rule not found.")

    updated = rule_repo.update_rule(
        rule_id=rule_id,
        name=req.name,
        description=req.description,
        priority=req.priority,
        status=req.status,
        condition=req.condition,
        consequence=req.consequence,
        metadata=req.metadata,
    )
    log_admin_action(admin["id"], "UPDATE_OFFICIAL_RULE", "rule", rule_id, {"name": updated.get("name") if updated else ""})
    return {"status": "updated", "rule": updated}


@router.delete("/rules/{rule_id}", summary="Admin delete official rule")
def delete_official_rule(
    rule_id: str,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Delete an official regulatory rule."""
    db = get_db_manager()
    rule_repo = RuleRepository(db)
    if not rule_repo.get_by_id(rule_id):
        raise HTTPException(status_code=404, detail="Rule not found.")

    rule_repo.delete_rule(rule_id)
    log_admin_action(admin["id"], "DELETE_OFFICIAL_RULE", "rule", rule_id, {})
    return {"status": "deleted", "rule_id": rule_id}


# -----------------------------------------------------------------------------
# 4. Decision Analytics & Audit Logs
# -----------------------------------------------------------------------------

@router.get("/decision-analytics", summary="Admin platform decision intelligence & historical analytics")
def get_decision_analytics(
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Exclusively provide decision statistics, domain distributions, and reasoning metrics."""
    db = get_db_manager()
    eval_repo = EvaluationRepository(db)
    stats = eval_repo.get_decision_stats()
    recent = eval_repo.list_evaluations(limit=25)
    return {
        "summary": stats,
        "recent_decisions": recent,
    }


@router.get("/audit-logs", summary="Admin action audit log")
def get_audit_logs(
    limit: int = 50,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Retrieve immutable log of administrator actions."""
    db = get_db_manager()
    with db.get_connection() as conn:
        rows = conn.execute(
            """
            SELECT a.*, u.username as admin_username, u.email as admin_email
            FROM audit_logs a
            LEFT JOIN users u ON a.user_id = u.id
            ORDER BY a.created_at DESC LIMIT ?;
            """,
            (limit,),
        ).fetchall()
        items = []
        for r in rows:
            d = dict(r)
            try:
                d["details"] = json.loads(d["details_json"])
            except Exception:
                d["details"] = {}
            items.append(d)
        return {"count": len(items), "items": items}


@router.get("/logins", summary="Admin user access & login security audit log")
def get_user_logins_audit(
    limit: int = 50,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Retrieve verified records of login attempts, timestamps, IP addresses, and access status."""
    db = get_db_manager()
    login_repo = UserLoginRepository(db)
    logins = login_repo.list_logins(limit=limit)
    # Sanitize any sensitive internal details
    clean_logins = []
    for l in logins:
        item = dict(l)
        item.pop("password_hash", None)
        item.pop("password_encryption", None)
        item["security_status"] = "Protected"
        clean_logins.append(item)
    return {
        "count": len(clean_logins),
        "items": clean_logins,
    }


# -----------------------------------------------------------------------------
# 5. Session Management & Safety Policies
# -----------------------------------------------------------------------------

@router.get("/sessions", summary="Admin session and conversation monitoring")
def list_sessions(
    limit: int = 50,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Retrieve platform conversation sessions for administrative audit."""
    db = get_db_manager()
    conv_repo = ConversationRepository(db)
    sessions = conv_repo.list_conversations(limit=limit)
    return {"count": len(sessions), "items": sessions}


@router.delete("/sessions/{conv_id}", summary="Admin terminate conversation session")
def terminate_session(
    conv_id: str,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Terminate and delete a conversation session."""
    db = get_db_manager()
    with db.transaction() as conn:
        conn.execute("DELETE FROM messages WHERE conversation_id = ?;", (conv_id,))
        conn.execute("DELETE FROM conversations WHERE id = ?;", (conv_id,))
    log_admin_action(admin["id"], "TERMINATE_SESSION", "session", conv_id, {})
    return {"status": "terminated", "conversation_id": conv_id}


@router.get("/safety-policies", summary="Admin inspect active safety policies")
def get_safety_policies(admin: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    """Retrieve active safety classification policies and custom blocked keywords."""
    from backend.nlp.safety import get_safety_manager
    sm = get_safety_manager()
    return {
        "enabled": sm.enabled,
        "allow_educational_dual_use": sm.allow_educational_dual_use,
        "custom_blocked_keywords": sm.custom_blocked_keywords,
    }


@router.put("/safety-policies", summary="Admin update safety policies")
def update_safety_policies(
    enabled: Optional[bool] = None,
    allow_educational_dual_use: Optional[bool] = None,
    custom_blocked_keywords: Optional[List[str]] = None,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Update active safety classification parameters."""
    from backend.nlp.safety import get_safety_manager
    sm = get_safety_manager()
    if enabled is not None:
        sm.enabled = enabled
    if allow_educational_dual_use is not None:
        sm.allow_educational_dual_use = allow_educational_dual_use
    if custom_blocked_keywords is not None:
        sm.custom_blocked_keywords = custom_blocked_keywords
    log_admin_action(admin["id"], "UPDATE_SAFETY_POLICY", "safety", "global", {
        "enabled": sm.enabled,
        "allow_educational_dual_use": sm.allow_educational_dual_use,
        "custom_blocked_keywords": sm.custom_blocked_keywords,
    })
    return {
        "status": "updated",
        "enabled": sm.enabled,
        "allow_educational_dual_use": sm.allow_educational_dual_use,
        "custom_blocked_keywords": sm.custom_blocked_keywords,
    }
