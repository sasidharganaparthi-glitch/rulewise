"""Repository pattern implementations for RuleWise AI database entities.

Provides typed, secure (parameterized SQL) operations for:
- Users (auth, passwords, roles)
- Domains (official & user-defined custom domains)
- Rules (declarative rules, priorities, conditions, consequences)
- Evaluations (decision history, explanations, traces)
- Conversations & Messages (chat history)
- Audit Logs (traceability of administrative actions)
"""

import hashlib
import hmac
import json
import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.db.database import DatabaseManager, get_db_manager
from backend.schemas.rule import Rule, RuleConsequence, RuleStatus

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


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


class UserRepository:
    """Data access repository for users and authentication."""

    def __init__(self, db: Optional[DatabaseManager] = None) -> None:
        self.db = db or get_db_manager()

    def create_user(
        self,
        username: str,
        password: Optional[str] = None,
        email: Optional[str] = None,
        role: str = "user",
    ) -> Dict[str, Any]:
        """Create and persist a new user."""
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        pwd_hash = hash_password(password) if password else None
        now = _utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO users (id, username, email, password_hash, role, created_at)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (user_id, username.strip(), email.strip() if email else None, pwd_hash, role, now),
            )
        return {
            "id": user_id,
            "username": username,
            "email": email,
            "role": role,
            "created_at": now,
        }

    def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve user by unique ID."""
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?;", (user_id,)).fetchone()
            if not row:
                return None
            return dict(row)

    def get_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Retrieve user by username."""
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE LOWER(username) = LOWER(?);", (username.strip(),)
            ).fetchone()
            if not row:
                return None
            return dict(row)

    def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Retrieve user by email address."""
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE LOWER(email) = LOWER(?);", (email.strip(),)
            ).fetchone()
            if not row:
                return None
            return dict(row)

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Verify username or email and password; returns user dict or None."""
        user = self.get_by_username(username)
        if not user and "@" in username:
            user = self.get_by_email(username)
        if not user or not user.get("password_hash"):
            return None
        # Disallow disabled accounts
        if user.get("is_active") == 0:
            return None
        if verify_password(password, user["password_hash"]):
            return {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "role": user["role"],
                "is_active": user.get("is_active", 1),
                "created_at": user["created_at"],
            }
        return None

    def get_or_create_google_user(
        self,
        google_id: str,
        email: str,
        name: Optional[str] = None,
        picture: Optional[str] = None,
        is_admin: bool = False,
    ) -> Dict[str, Any]:
        """Authenticate or register a verified Google OAuth user."""
        email_clean = email.strip().lower()
        now = _utc_now_iso()
        user = self.get_by_email(email_clean)
        role = "admin" if is_admin else ("admin" if email_clean == "sasiganaparthi@gmail.com" else "user")

        with self.db.transaction() as conn:
            if user:
                # Update Google metadata
                target_role = "admin" if (is_admin or user.get("role") == "admin" or email_clean == "sasiganaparthi@gmail.com") else user.get("role", "user")
                conn.execute(
                    "UPDATE users SET google_id = ?, picture = COALESCE(?, picture), role = ? WHERE id = ?;",
                    (google_id, picture, target_role, user["id"]),
                )
                user["role"] = target_role
                user["picture"] = picture or user.get("picture")
                return user
            else:
                user_id = f"user_{uuid.uuid4().hex[:12]}"
                username_base = (name or email_clean.split("@")[0]).strip().replace(" ", "_")
                # Ensure unique username
                existing_u = self.get_by_username(username_base)
                username = username_base if not existing_u else f"{username_base}_{uuid.uuid4().hex[:4]}"
                conn.execute(
                    """
                    INSERT INTO users (id, username, email, password_hash, role, is_active, google_id, picture, created_at)
                    VALUES (?, ?, ?, NULL, ?, 1, ?, ?, ?);
                    """,
                    (user_id, username, email_clean, role, google_id, picture, now),
                )
                return {
                    "id": user_id,
                    "username": username,
                    "email": email_clean,
                    "role": role,
                    "is_active": 1,
                    "google_id": google_id,
                    "picture": picture,
                    "created_at": now,
                }

    def update_user_status(self, user_id: str, is_active: bool) -> bool:
        """Enable or disable user access."""
        with self.db.transaction() as conn:
            cur = conn.execute("UPDATE users SET is_active = ? WHERE id = ?;", (1 if is_active else 0, user_id))
            return cur.rowcount > 0

    def update_user_role(self, user_id: str, role: str) -> bool:
        """Change user role (e.g. user -> admin)."""
        with self.db.transaction() as conn:
            cur = conn.execute("UPDATE users SET role = ? WHERE id = ?;", (role, user_id))
            return cur.rowcount > 0

    def update_password(self, user_id: str, new_password: str) -> bool:
        """Update password hash for a user."""
        new_hash = hash_password(new_password)
        with self.db.transaction() as conn:
            cur = conn.execute("UPDATE users SET password_hash = ? WHERE id = ?;", (new_hash, user_id))
            return cur.rowcount > 0

    def delete_user(self, user_id: str) -> bool:
        """Delete user account."""
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM users WHERE id = ?;", (user_id,))
            return cur.rowcount > 0

    def count_admins(self) -> int:
        """Count active administrators in the system to prevent deleting the last admin."""
        with self.db.get_connection() as conn:
            res = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1;").fetchone()
            return res[0] if res else 0

    def list_users(
        self,
        search: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List registered users with optional search and role filters."""
        query = "SELECT id, username, email, role, is_active, google_id, picture, created_at FROM users WHERE 1=1"
        params: List[Any] = []
        if search:
            query += " AND (LOWER(username) LIKE ? OR LOWER(email) LIKE ?)"
            term = f"%{search.strip().lower()}%"
            params.extend([term, term])
        if role:
            query += " AND role = ?"
            params.append(role)
        if is_active is not None:
            query += " AND is_active = ?"
            params.append(1 if is_active else 0)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        with self.db.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]


class DomainRepository:
    """Data access repository for official and custom user domains."""

    def __init__(self, db: Optional[DatabaseManager] = None) -> None:
        self.db = db or get_db_manager()

    def create_domain(
        self,
        name: str,
        slug: str,
        description: str = "",
        category: str = "general",
        is_official: bool = False,
        schema_fields: Optional[List[Dict[str, Any]]] = None,
        created_by: Optional[str] = None,
        domain_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new domain."""
        did = domain_id or f"dom_{uuid.uuid4().hex[:10]}"
        now = _utc_now_iso()
        fields_json = json.dumps(schema_fields or [])
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO domains (id, name, slug, description, category, is_official, version, schema_fields, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, '1.0', ?, ?, ?, ?);
                """,
                (did, name, slug, description, category, 1 if is_official else 0, fields_json, created_by, now, now),
            )
        return self.get_by_id(did)  # type: ignore[return-value]

    def get_by_id(self, domain_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve domain by ID."""
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM domains WHERE id = ?;", (domain_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            data["schema_fields"] = json.loads(data["schema_fields"])
            data["is_official"] = bool(data["is_official"])
            return data

    def get_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """Retrieve domain by slug."""
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM domains WHERE slug = ?;", (slug.strip(),)).fetchone()
            if not row:
                return None
            data = dict(row)
            data["schema_fields"] = json.loads(data["schema_fields"])
            data["is_official"] = bool(data["is_official"])
            return data

    def list_domains(
        self,
        is_official: Optional[bool] = None,
        created_by: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List domains with optional filters."""
        query = "SELECT * FROM domains WHERE 1=1"
        params: List[Any] = []
        if is_official is not None:
            query += " AND is_official = ?"
            params.append(1 if is_official else 0)
        if created_by is not None:
            query += " AND (created_by = ? OR is_official = 1)"
            params.append(created_by)
        if category is not None:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY is_official DESC, name ASC;"

        with self.db.get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["schema_fields"] = json.loads(d["schema_fields"])
                d["is_official"] = bool(d["is_official"])
                results.append(d)
            return results

    def delete_domain(self, domain_id: str, requesting_user_id: Optional[str] = None) -> bool:
        """Delete domain if permitted. Official domains can only be deleted by admins."""
        dom = self.get_by_id(domain_id)
        if not dom:
            return False
        if dom["is_official"]:
            # Protected
            return False
        if requesting_user_id and dom["created_by"] and dom["created_by"] != requesting_user_id:
            return False

        with self.db.transaction() as conn:
            conn.execute("DELETE FROM domains WHERE id = ?;", (domain_id,))
        return True


class RuleRepository:
    """Data access repository for rules."""

    def __init__(self, db: Optional[DatabaseManager] = None) -> None:
        self.db = db or get_db_manager()

    def create_rule(
        self,
        domain_id: str,
        name: str,
        condition: Dict[str, Any],
        consequence: Dict[str, Any],
        rule_id: Optional[str] = None,
        description: str = "",
        priority: int = 50,
        status: str = "active",
        is_official: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        created_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create and store a rule."""
        rid = rule_id or f"RULE_{uuid.uuid4().hex[:8].upper()}"
        now = _utc_now_iso()
        cond_json = json.dumps(condition)
        cons_json = json.dumps(consequence)
        meta_json = json.dumps(metadata or {})
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO rules (
                    id, domain_id, name, description, priority, status,
                    is_official, version, condition_json, consequence_json,
                    metadata_json, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, '1.0', ?, ?, ?, ?, ?, ?);
                """,
                (
                    rid, domain_id, name, description, priority, status,
                    1 if is_official else 0, cond_json, cons_json, meta_json,
                    created_by, now, now
                ),
            )
        return self.get_by_id(rid)  # type: ignore[return-value]

    def get_by_id(self, rule_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve rule by ID."""
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM rules WHERE id = ?;", (rule_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            data["condition"] = json.loads(data["condition_json"])
            data["consequence"] = json.loads(data["consequence_json"])
            data["metadata"] = json.loads(data["metadata_json"])
            data["is_official"] = bool(data["is_official"])
            return data

    def list_rules(
        self,
        domain_id: Optional[str] = None,
        status: Optional[str] = None,
        is_official: Optional[bool] = None,
        created_by: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List rules with filtering."""
        query = "SELECT * FROM rules WHERE 1=1"
        params: List[Any] = []
        if domain_id:
            query += " AND domain_id = ?"
            params.append(domain_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        if is_official is not None:
            query += " AND is_official = ?"
            params.append(1 if is_official else 0)
        if created_by is not None:
            query += " AND (created_by = ? OR is_official = 1)"
            params.append(created_by)
        query += " ORDER BY priority DESC, id ASC;"

        with self.db.get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["condition"] = json.loads(d["condition_json"])
                d["consequence"] = json.loads(d["consequence_json"])
                d["metadata"] = json.loads(d["metadata_json"])
                d["is_official"] = bool(d["is_official"])
                results.append(d)
            return results

    def update_rule(
        self,
        rule_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[int] = None,
        status: Optional[str] = None,
        condition: Optional[Dict[str, Any]] = None,
        consequence: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update existing rule attributes."""
        existing = self.get_by_id(rule_id)
        if not existing:
            return None

        now = _utc_now_iso()
        fields_to_update = ["updated_at = ?"]
        params: List[Any] = [now]

        if name is not None:
            fields_to_update.append("name = ?")
            params.append(name)
        if description is not None:
            fields_to_update.append("description = ?")
            params.append(description)
        if priority is not None:
            fields_to_update.append("priority = ?")
            params.append(priority)
        if status is not None:
            fields_to_update.append("status = ?")
            params.append(status)
        if condition is not None:
            fields_to_update.append("condition_json = ?")
            params.append(json.dumps(condition))
        if consequence is not None:
            fields_to_update.append("consequence_json = ?")
            params.append(json.dumps(consequence))
        if metadata is not None:
            fields_to_update.append("metadata_json = ?")
            params.append(json.dumps(metadata))

        params.append(rule_id)
        sql = f"UPDATE rules SET {', '.join(fields_to_update)} WHERE id = ?;"

        with self.db.transaction() as conn:
            conn.execute(sql, tuple(params))
        return self.get_by_id(rule_id)

    def delete_rule(self, rule_id: str) -> bool:
        """Delete rule by ID."""
        with self.db.transaction() as conn:
            cursor = conn.execute("DELETE FROM rules WHERE id = ?;", (rule_id,))
            return cursor.rowcount > 0

    def get_as_pydantic_rules(self, domain_id: str, active_only: bool = True) -> List[Rule]:
        """Convert stored database rules to Pydantic Rule models for InferenceEngine."""
        records = self.list_rules(domain_id=domain_id, status="active" if active_only else None)
        rules: List[Rule] = []
        for r in records:
            try:
                rule_obj = Rule(
                    id=r["id"],
                    name=r["name"],
                    description=r.get("description") or "",
                    priority=r["priority"],
                    status=RuleStatus(r["status"]),
                    condition=r["condition"],
                    consequence=RuleConsequence(**r["consequence"]),
                    metadata=r.get("metadata") or {},
                )
                rules.append(rule_obj)
            except Exception as exc:
                logger.error("Failed to parse rule '%s' into Pydantic model: %s", r["id"], exc)
        return rules


class EvaluationRepository:
    """Data access repository for deterministic evaluation history."""

    def __init__(self, db: Optional[DatabaseManager] = None) -> None:
        self.db = db or get_db_manager()

    def record_evaluation(
        self,
        domain_id: str,
        input_facts: Dict[str, Any],
        conclusion_reached: bool,
        final_decision: str,
        decision_status: str = "completed",
        fired_rules: Optional[List[str]] = None,
        derived_facts: Optional[Dict[str, Any]] = None,
        explanation: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        question: Optional[str] = None,
        confidence: float = 1.0,
    ) -> Dict[str, Any]:
        """Persist a completed rule engine evaluation trace."""
        eval_id = f"eval_{uuid.uuid4().hex[:12]}"
        now = _utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO evaluations (
                    id, domain_id, user_id, question, confidence, input_facts_json, conclusion_reached,
                    final_decision, decision_status, fired_rules_json, derived_facts_json,
                    explanation_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    eval_id, domain_id, user_id, question, float(confidence), json.dumps(input_facts),
                    1 if conclusion_reached else 0, final_decision, decision_status,
                    json.dumps(fired_rules or []), json.dumps(derived_facts or {}),
                    json.dumps(explanation or {}), now
                ),
            )
        return self.get_by_id(eval_id)  # type: ignore[return-value]

    def get_by_id(self, eval_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve evaluation record by ID."""
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM evaluations WHERE id = ?;", (eval_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["input_facts"] = json.loads(d["input_facts_json"])
            d["fired_rules"] = json.loads(d["fired_rules_json"])
            d["derived_facts"] = json.loads(d["derived_facts_json"])
            d["explanation"] = json.loads(d["explanation_json"])
            d["conclusion_reached"] = bool(d["conclusion_reached"])
            d["confidence"] = float(d.get("confidence") or 1.0)
            return d

    def delete_evaluation(self, eval_id: str, user_id: Optional[str] = None) -> bool:
        """Delete an evaluation record (isolated to owner or admin)."""
        with self.db.transaction() as conn:
            if user_id:
                cur = conn.execute("DELETE FROM evaluations WHERE id = ? AND user_id = ?;", (eval_id, user_id))
            else:
                cur = conn.execute("DELETE FROM evaluations WHERE id = ?;", (eval_id,))
            return cur.rowcount > 0

    def list_evaluations(
        self,
        domain_id: Optional[str] = None,
        user_id: Optional[str] = None,
        search: Optional[str] = None,
        decision: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List past evaluations with filtering, searching, and pagination."""
        query = "SELECT * FROM evaluations WHERE 1=1"
        params: List[Any] = []
        if domain_id:
            query += " AND domain_id = ?"
            params.append(domain_id)
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        if decision:
            query += " AND LOWER(final_decision) = LOWER(?)"
            params.append(decision.strip())
        if search:
            query += " AND (LOWER(final_decision) LIKE ? OR LOWER(COALESCE(question, '')) LIKE ? OR input_facts_json LIKE ?)"
            term = f"%{search.strip().lower()}%"
            params.extend([term, term, term])
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        with self.db.get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["input_facts"] = json.loads(d["input_facts_json"])
                d["fired_rules"] = json.loads(d["fired_rules_json"])
                d["derived_facts"] = json.loads(d["derived_facts_json"])
                d["explanation"] = json.loads(d["explanation_json"])
                d["conclusion_reached"] = bool(d["conclusion_reached"])
                d["confidence"] = float(d.get("confidence") or 1.0)
                results.append(d)
            return results

    def get_decision_stats(self) -> Dict[str, Any]:
        """Aggregate platform decision statistics for the admin dashboard."""
        with self.db.get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM evaluations;").fetchone()[0]
            concluded = conn.execute("SELECT COUNT(*) FROM evaluations WHERE conclusion_reached = 1;").fetchone()[0]
            per_domain = conn.execute(
                "SELECT domain_id, COUNT(*) as count FROM evaluations GROUP BY domain_id;"
            ).fetchall()
            decisions = conn.execute(
                "SELECT final_decision, COUNT(*) as count FROM evaluations GROUP BY final_decision ORDER BY count DESC LIMIT 10;"
            ).fetchall()
            return {
                "total_decisions": total,
                "concluded_decisions": concluded,
                "concluded_rate_pct": round((concluded / total * 100) if total else 0, 1),
                "by_domain": {row["domain_id"]: row["count"] for row in per_domain},
                "by_decision": {row["final_decision"]: row["count"] for row in decisions},
            }


class ConversationRepository:
    """Data access repository for chat conversations and message history."""

    def __init__(self, db: Optional[DatabaseManager] = None) -> None:
        self.db = db or get_db_manager()

    def create_conversation(
        self,
        title: str = "New Advisory Session",
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Start a new chat conversation thread."""
        conv_id = conversation_id or f"conv_{uuid.uuid4().hex[:12]}"
        now = _utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO conversations (id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?);",
                (conv_id, user_id, title, now, now),
            )
        return {"id": conv_id, "user_id": user_id, "title": title, "created_at": now, "updated_at": now}

    def ensure_conversation(
        self,
        conversation_id: str,
        title: str = "Advisory Session",
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Ensure conversation exists in the database, inserting it if missing."""
        now = _utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO conversations (id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?);",
                (conversation_id, user_id, title, now, now),
            )
        return {"id": conversation_id, "user_id": user_id, "title": title, "created_at": now, "updated_at": now}

    def list_conversations(self, user_id: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """List active conversations for a user, isolated to that user and within the 30-day retention window."""
        query = (
            "SELECT * FROM conversations "
            "WHERE TRIM(title) != '' "
            "AND id NOT LIKE 'conv_%' "
            "AND id NOT LIKE 'test_%' "
            "AND title NOT LIKE '%SYSTEM OVERRIDE%' "
            "AND title NOT LIKE '%Tell me a joke%' "
            "AND title NOT LIKE '%introduce yourself%' "
            "AND title NOT LIKE '%Carlos Gomez%' "
            "AND datetime(created_at) >= datetime('now', '-30 days')"
        )
        params: List[Any] = []
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        else:
            # If guest/unauthenticated, do not expose any registered user conversations
            query += " AND (user_id IS NULL OR user_id LIKE 'guest_%')"
        query += " ORDER BY updated_at DESC LIMIT ?;"
        params.append(limit)

        with self.db.get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(r) for r in rows]

    def add_message(
        self,
        conversation_id: str,
        sender: str,
        content: str,
        intent: Optional[str] = None,
        symbolic_result: Optional[Dict[str, Any]] = None,
        explanation: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Append a message to a conversation."""
        msg_id = f"msg_{uuid.uuid4().hex[:12]}"
        now = _utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO messages (
                    id, conversation_id, sender, content, intent,
                    symbolic_result_json, explanation_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    msg_id, conversation_id, sender, content, intent,
                    json.dumps(symbolic_result) if symbolic_result else None,
                    json.dumps(explanation) if explanation else None,
                    now,
                ),
            )
            conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?;", (now, conversation_id))
        return {
            "id": msg_id,
            "conversation_id": conversation_id,
            "sender": sender,
            "content": content,
            "intent": intent,
            "created_at": now,
        }

    def get_messages(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Retrieve all messages in a conversation ordered chronologically."""
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC;",
                (conversation_id,),
            ).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["symbolic_result"] = json.loads(d["symbolic_result_json"]) if d.get("symbolic_result_json") else None
                d["explanation"] = json.loads(d["explanation_json"]) if d.get("explanation_json") else None
                results.append(d)
            return results


class AuditRepository:
    """Data access repository for audit logs."""

    def __init__(self, db: Optional[DatabaseManager] = None) -> None:
        self.db = db or get_db_manager()

    def log_action(
        self,
        action: str,
        target_type: str,
        target_id: str,
        user_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record an administrative or security-sensitive action."""
        aid = f"audit_{uuid.uuid4().hex[:12]}"
        now = _utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO audit_logs (id, user_id, action, target_type, target_id, details_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (aid, user_id, action, target_type, target_id, json.dumps(details or {}), now),
            )


class UserLoginRepository:
    """Manages recording and retrieving user login events and access audits."""

    def __init__(self, db: Optional[DatabaseManager] = None) -> None:
        self.db = db or get_db_manager()

    def record_login(
        self,
        username: str,
        status: str,
        email: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        user_id: Optional[str] = None,
        password_encryption: str = "PBKDF2-HMAC-SHA256 (100k Salted Rounds)",
    ) -> Dict[str, Any]:
        """Record an attempted or successful user login event."""
        lid = f"login_{uuid.uuid4().hex[:12]}"
        now = _utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO user_logins (id, user_id, username, email, status, ip_address, user_agent, password_encryption, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (lid, user_id, username, email, status, ip_address, user_agent, password_encryption, now),
            )
        return {
            "id": lid,
            "user_id": user_id,
            "username": username,
            "email": email,
            "status": status,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "password_encryption": password_encryption,
            "created_at": now,
        }

    def list_logins(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List user login audit records in descending chronological order."""
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM user_logins ORDER BY created_at DESC LIMIT ?;",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]


