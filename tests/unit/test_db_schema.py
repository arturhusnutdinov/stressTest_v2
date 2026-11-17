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


class TestRatingSavePath:
    """Regression (17.11): rating runner kwargs must persist without TypeError.

    Bug: runner called upsert_rating(score_detail=..., nd_ebitda=..., icr=...),
    signature accepted only factor_metrics -> ERROR on every scenario save.
    """

    def test_upsert_rating_with_score_detail(self, tmp_path):
        import json
        from engine.database.repository import Repository

        db = tmp_path / "ratings.db"
        with Repository(db_path=db) as repo:
            repo.execute(
                "INSERT INTO companies (company_id, name) VALUES ('tst', 'Test')"
            )
            sid = repo.ensure_scenario('tst', 'base', type_='base')
            rid = repo.upsert_rating(
                company_id='tst', scenario_id=sid, year=2026,
                methodology='sp_scoring', grade='B+', score=12.5,
                score_detail={'sub_scores': {'leverage': 4}, 'headroom_to_ig': 1.2},
                nd_ebitda=7.2, icr=1.1,
            )
            assert rid > 0

            row = repo.query_one(
                "SELECT grade, score, score_detail FROM ratings WHERE rowid=?", (rid,)
            )
            assert row["grade"] == "B+" and row["score"] == 12.5
            assert json.loads(row["score_detail"])["sub_scores"]["leverage"] == 4

            metrics = {
                r["metric_name"]: r["value"]
                for r in repo.execute(
                    "SELECT metric_name, value FROM rating_metrics WHERE rating_id=?",
                    (rid,),
                ).fetchall()
            }
            assert metrics["net_debt_ebitda"] == 7.2
            assert metrics["interest_coverage"] == 1.1

            # Idempotent upsert (ON CONFLICT) — второй вызов не падает
            rid2 = repo.upsert_rating(
                company_id='tst', scenario_id=sid, year=2026,
                methodology='sp_scoring', grade='BB-', score=14.0,
                nd_ebitda=8.1,
            )
            assert rid2 == rid
            row2 = repo.query_one(
                "SELECT grade, score_detail FROM ratings WHERE rowid=?", (rid,)
            )
            assert row2["grade"] == "BB-"
