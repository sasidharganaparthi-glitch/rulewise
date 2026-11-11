"""Pytest configuration and database isolation fixture."""

import os
import tempfile
from pathlib import Path
import pytest

# Ensure tests run against an isolated temporary database
_temp_dir = tempfile.TemporaryDirectory()
_test_db = Path(_temp_dir.name) / "test_rulewise.db"
os.environ["DATABASE_PATH"] = str(_test_db)

from backend.db.database import get_db_manager, reset_db_manager
from backend.db.seeder import seed_database

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    db = reset_db_manager(db_path=_test_db)
    seed_database(db)
    yield db
    reset_db_manager()
    try:
        _temp_dir.cleanup()
    except Exception:
        pass
