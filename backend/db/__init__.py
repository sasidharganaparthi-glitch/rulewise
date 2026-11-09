"""Database module for RuleWise AI."""

from backend.db.database import DatabaseManager, get_db_manager, reset_db_manager
from backend.db.repositories import (
    AuditRepository,
    ConversationRepository,
    DomainRepository,
    EvaluationRepository,
    RuleRepository,
    UserRepository,
    hash_password,
    verify_password,
)
from backend.db.seeder import seed_database

__all__ = [
    "DatabaseManager",
    "get_db_manager",
    "reset_db_manager",
    "UserRepository",
    "DomainRepository",
    "RuleRepository",
    "EvaluationRepository",
    "ConversationRepository",
    "AuditRepository",
    "hash_password",
    "verify_password",
    "seed_database",
]

