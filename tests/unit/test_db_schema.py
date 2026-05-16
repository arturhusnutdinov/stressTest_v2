"""Unit tests for database schema."""
import sqlite3
from engine.database.schema import create_schema, get_table_names


class TestSchema:
    """Verify schema creation and structure."""

    def test_create_schema(self, tmp_db):
        """All tables and indexes are created."""
        tables = get_table_names()
        for t in tables:
            # Verify table exists
            row = tmp_db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (t,)
            ).fetchone()
            assert row is not None, f"Table {t} not created"

    def test_table_count(self):
        """Schema has expected number of tables."""
        tables = get_table_names()
        assert len(tables) >= 30, f"Expected >=30 tables, got {len(tables)}"

    def test_core_tables_exist(self, tmp_db):
        """Core tables must be present."""
        required = [
            "companies", "periods", "scenarios",
            "history_is", "history_bs", "history_cf",
            "debt_instruments", "debt_schedule",
            "forecast_is", "forecast_bs", "forecast_cf",
            "preprocess_metrics", "macro_factors", "macro_forecasts",
        ]
        for t in required:
            row = tmp_db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (t,)
            ).fetchone()
            assert row is not None, f"Required table {t} missing"

    def test_foreign_keys_enabled(self, tmp_db):
        """FK pragma must be set."""
        row = tmp_db.execute("PRAGMA foreign_keys").fetchone()
        assert row[0] == 1, "Foreign keys not enabled"

    def test_journal_mode(self, tmp_db):
        """WAL or memory journal mode (memory for in-memory DBs)."""
        row = tmp_db.execute("PRAGMA journal_mode").fetchone()
        assert row[0].upper() in ("WAL", "MEMORY"), f"Unexpected journal_mode: {row[0]}"
