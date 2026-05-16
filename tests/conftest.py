"""
Shared fixtures for stressTest v2 tests.
"""
import pytest
import sqlite3
import sys
import tempfile
from pathlib import Path

# Ensure project root is on path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def project_root():
    """Absolute path to project root."""
    return ROOT


@pytest.fixture(scope="session")
def db_path():
    """Path to the real data_mart_v2.db (read-only tests)."""
    p = ROOT / "data_mart_v2.db"
    if not p.exists():
        pytest.skip("data_mart_v2.db not found")
    return p


@pytest.fixture
def tmp_db():
    """In-memory SQLite DB with full schema for unit tests."""
    from engine.database.schema import create_schema
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def repo(db_path):
    """Repository connected to real DB (integration tests)."""
    from engine.database.repository import Repository
    with Repository(db_path=db_path) as r:
        yield r


@pytest.fixture(params=["us_steel", "rusal"])
def company_id(request):
    """Parametrized fixture — tests run for both companies."""
    return request.param
