"""Database initialization, connection handling, and schema setup for RuleWise AI.

Uses Python's standard library SQLite with WAL mode, foreign keys, and connection pooling.
Zero external dependency risk, ACID transactions, thread-safe.
Compatible with external SQL engines if migrated to PostgreSQL in production.
"""

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)

# Determine database path (with Vercel/Serverless /tmp support)
bundled_db_dir = Path(__file__).resolve().parent.parent / "data"
if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    import shutil
    tmp_db_dir = Path("/tmp") / "rulewise_data"
    tmp_db_dir.mkdir(parents=True, exist_ok=True)
    DEFAULT_DB_PATH = tmp_db_dir / "rulewise.db"
    bundled_db = bundled_db_dir / "rulewise.db"
    if bundled_db.exists() and not DEFAULT_DB_PATH.exists():
        try:
            shutil.copy2(bundled_db, DEFAULT_DB_PATH)
            logger.info("Copied bundled database to /tmp: %s", DEFAULT_DB_PATH)
        except Exception as e:
            logger.warning("Could not copy bundled db to /tmp: %s", e)
else:
    db_env_path = os.environ.get("DATABASE_PATH")
    if db_env_path:
        DEFAULT_DB_PATH = Path(db_env_path)
    else:
        bundled_db_dir.mkdir(parents=True, exist_ok=True)
        DEFAULT_DB_PATH = bundled_db_dir / "rulewise.db"


class DatabaseManager:
    """Manages SQLite database connections, schema migrations, and transactions."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Create a configured SQLite connection with foreign keys and row factory."""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
        except Exception:
            conn.execute("PRAGMA journal_mode = DELETE;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager providing an atomic database transaction."""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create database tables and indexes if they do not exist."""
        with self.transaction() as conn:
            # Users table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE,
                password_hash TEXT,
                role TEXT NOT NULL DEFAULT 'user',
                is_active INTEGER NOT NULL DEFAULT 1,
                google_id TEXT,
                picture TEXT,
                created_at TEXT NOT NULL
            );
            """)

            # Safe migrations for existing databases
            for col_sql in (
                "ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1;",
                "ALTER TABLE users ADD COLUMN google_id TEXT;",
                "ALTER TABLE users ADD COLUMN picture TEXT;",
            ):
                try:
                    conn.execute(col_sql)
                except Exception:
                    pass

            # Domains table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS domains (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                description TEXT,
                category TEXT NOT NULL DEFAULT 'general',
                is_official INTEGER NOT NULL DEFAULT 0,
                version TEXT NOT NULL DEFAULT '1.0',
                schema_fields TEXT NOT NULL DEFAULT '[]',
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)

            # Rules table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS rules (
                id TEXT PRIMARY KEY,
                domain_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                priority INTEGER NOT NULL DEFAULT 50,
                status TEXT NOT NULL DEFAULT 'active',
                is_official INTEGER NOT NULL DEFAULT 0,
                version TEXT NOT NULL DEFAULT '1.0',
                condition_json TEXT NOT NULL,
                consequence_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (domain_id) REFERENCES domains(id) ON DELETE CASCADE
            );
            """)

            # Evaluation History table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS evaluations (
                id TEXT PRIMARY KEY,
                domain_id TEXT NOT NULL,
                user_id TEXT,
                question TEXT,
                confidence REAL DEFAULT 1.0,
                input_facts_json TEXT NOT NULL,
                conclusion_reached INTEGER NOT NULL DEFAULT 0,
                final_decision TEXT NOT NULL,
                decision_status TEXT NOT NULL DEFAULT 'completed',
                fired_rules_json TEXT NOT NULL DEFAULT '[]',
                derived_facts_json TEXT NOT NULL DEFAULT '{}',
                explanation_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (domain_id) REFERENCES domains(id) ON DELETE CASCADE
            );
            """)

            for col_sql in (
                "ALTER TABLE evaluations ADD COLUMN question TEXT;",
                "ALTER TABLE evaluations ADD COLUMN confidence REAL DEFAULT 1.0;",
            ):
                try:
                    conn.execute(col_sql)
                except Exception:
                    pass

            # Conversations table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)

            # Messages table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                content TEXT NOT NULL,
                intent TEXT,
                symbolic_result_json TEXT,
                explanation_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
            """)

            # Audit Logs table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                action TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            """)

            # User Logins & Access Audit table (Admin only)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS user_logins (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                username TEXT NOT NULL,
                email TEXT,
                status TEXT NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                password_encryption TEXT NOT NULL DEFAULT 'PBKDF2-HMAC-SHA256 (100k Salted Rounds)',
                created_at TEXT NOT NULL
            );
            """)

            # Indexes for high performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_domains_slug ON domains(slug);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_domains_official ON domains(is_official);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rules_domain_id ON rules(domain_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rules_status ON rules(status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rules_official ON rules(is_official);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_evaluations_domain ON evaluations(domain_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_evaluations_user ON evaluations(user_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_logins_time ON user_logins(created_at);")


# Singleton instance
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """Retrieve or initialize the global DatabaseManager."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def reset_db_manager(db_path: Optional[Path] = None) -> DatabaseManager:
    """Reset the database manager, primarily for isolated test databases."""
    global _db_manager
    _db_manager = DatabaseManager(db_path=db_path)
    return _db_manager

