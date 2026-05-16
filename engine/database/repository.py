"""
Единый репозиторий для всех операций с БД.
Принцип: один класс, UPSERT везде, батч-операции по умолчанию.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .schema import create_schema
from engine import ROOT as _ENGINE_ROOT

logger = logging.getLogger(__name__)

# Путь к БД относительно корня проекта
_DEFAULT_DB = _ENGINE_ROOT / "data_mart_v2.db"


class Repository:
    """
    Единая точка доступа к БД.
    Используется как context manager:
        with Repository() as repo:
            repo.upsert_history("us_steel", "IS", 2024, {"revenue": 15640000})
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._path = Path(db_path) if db_path else _DEFAULT_DB
        self._conn: Optional[sqlite3.Connection] = None

    # ── context manager ────────────────────────────────────────────────────────

    def __enter__(self) -> "Repository":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self.close()

    def connect(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        create_schema(self._conn)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Repository not connected. Use 'with Repository() as repo:'")
        return self._conn

    # ── низкоуровневые helpers ─────────────────────────────────────────────────

    def execute(self, sql: str, params: Tuple = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def query(self, sql: str, params: Tuple = ()) -> List[Dict[str, Any]]:
        cur = self.conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]

    def query_one(self, sql: str, params: Tuple = ()) -> Optional[Dict[str, Any]]:
        cur = self.conn.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None

    def query_scalar(self, sql: str, params: Tuple = (), default=None):
        row = self.query_one(sql, params)
        if row is None:
            return default
        return next(iter(row.values()), default)

    # ── компании и периоды ─────────────────────────────────────────────────────

    def upsert_company(
        self,
        company_id: str,
        name: str,
        industry: str = "",
        currency: str = "USD",
        accounting_standard: str = "US_GAAP",
        db_unit: str = "tUSD",
        **kwargs,
    ) -> None:
        self.execute(
            """
            INSERT INTO companies
                (company_id, name, industry, currency, accounting_standard, db_unit, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(company_id) DO UPDATE SET
                name                = excluded.name,
                industry            = excluded.industry,
                currency            = excluded.currency,
                accounting_standard = excluded.accounting_standard,
                db_unit             = excluded.db_unit,
                updated_at          = CURRENT_TIMESTAMP
            """,
            (company_id, name, industry, currency, accounting_standard, db_unit),
        )

    def get_company(self, company_id: str) -> Optional[Dict[str, Any]]:
        return self.query_one(
            "SELECT * FROM companies WHERE company_id = ?", (company_id,)
        )

    def list_companies(self) -> List[str]:
        rows = self.query("SELECT company_id FROM companies ORDER BY company_id")
        return [r["company_id"] for r in rows]

    def ensure_period(self, company_id: str, year: int, is_forecast: int = 0) -> int:
        """Возвращает period_id, создаёт запись если не существует."""
        existing = self.query_one(
            "SELECT period_id FROM periods WHERE company_id=? AND year=? AND is_annual=1",
            (company_id, year),
        )
        if existing:
            return existing["period_id"]
        cur = self.execute(
            "INSERT INTO periods (company_id, year, is_annual, is_forecast) VALUES (?,?,1,?)",
            (company_id, year, is_forecast),
        )
        return cur.lastrowid

    def get_period_id(self, company_id: str, year: int) -> int:
        row = self.query_one(
            "SELECT period_id FROM periods WHERE company_id=? AND year=? AND is_annual=1",
            (company_id, year),
        )
        if not row:
            raise ValueError(f"Period not found: company={company_id} year={year}")
        return row["period_id"]

    def get_years(self, company_id: str, is_forecast: int = 0) -> List[int]:
        rows = self.query(
            "SELECT year FROM periods WHERE company_id=? AND is_annual=1 AND is_forecast=? ORDER BY year",
            (company_id, is_forecast),
        )
        return [r["year"] for r in rows]

    # ── сценарии ───────────────────────────────────────────────────────────────

    def ensure_scenario(
        self, company_id: str, name: str, type_: str = "base", description: str = ""
    ) -> int:
        existing = self.query_one(
            "SELECT scenario_id FROM scenarios WHERE company_id=? AND name=?",
            (company_id, name),
        )
        if existing:
            return existing["scenario_id"]
        cur = self.execute(
            "INSERT INTO scenarios (company_id, name, type, description) VALUES (?,?,?,?)",
            (company_id, name, type_, description),
        )
        return cur.lastrowid

    def get_scenario_id(self, company_id: str, name: str) -> int:
        row = self.query_one(
            "SELECT scenario_id FROM scenarios WHERE company_id=? AND name=?",
            (company_id, name),
        )
        if not row:
            raise ValueError(f"Scenario not found: company={company_id} name={name}")
        return row["scenario_id"]

    # ── история (EAV) ──────────────────────────────────────────────────────────

    def upsert_history(
        self,
        company_id: str,
        statement: str,          # IS | BS | CF
        year: int,
        metrics: Dict[str, float],
        source: str = "",
    ) -> int:
        """
        Записывает словарь {metric: value} для одного года.
        Возвращает количество записанных строк.
        """
        table = _history_table(statement)
        period_id = self.ensure_period(company_id, year, is_forecast=0)
        rows = [
            (company_id, period_id, metric, value, source)
            for metric, value in metrics.items()
            if value is not None
        ]
        self.conn.executemany(
            f"""
            INSERT INTO {table} (company_id, period_id, metric, value, source, updated_at)
            VALUES (?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(company_id, period_id, metric) DO UPDATE SET
                value      = excluded.value,
                source     = excluded.source,
                updated_at = CURRENT_TIMESTAMP
            """,
            rows,
        )
        return len(rows)

    def get_history(
        self,
        company_id: str,
        statement: str,
        years: Optional[List[int]] = None,
    ) -> Dict[int, Dict[str, float]]:
        """
        Возвращает {year: {metric: value}}.
        Если years=None — все исторические годы.
        """
        table = _history_table(statement)
        if years:
            placeholders = ",".join("?" * len(years))
            sql = f"""
                SELECT p.year, h.metric, h.value
                FROM {table} h
                JOIN periods p ON h.period_id = p.period_id
                WHERE h.company_id=? AND p.year IN ({placeholders})
                ORDER BY p.year
            """
            rows = self.query(sql, (company_id, *years))
        else:
            sql = f"""
                SELECT p.year, h.metric, h.value
                FROM {table} h
                JOIN periods p ON h.period_id = p.period_id
                WHERE h.company_id=? AND p.is_forecast=0
                ORDER BY p.year
            """
            rows = self.query(sql, (company_id,))

        result: Dict[int, Dict[str, float]] = {}
        for row in rows:
            yr = row["year"]
            if yr not in result:
                result[yr] = {}
            result[yr][row["metric"]] = row["value"]
        return result

    def get_history_year(
        self, company_id: str, statement: str, year: int
    ) -> Dict[str, float]:
        """Возвращает {metric: value} для одного года."""
        data = self.get_history(company_id, statement, years=[year])
        return data.get(year, {})

    def get_metric_series(
        self, company_id: str, statement: str, metric: str
    ) -> Dict[int, float]:
        """Возвращает {year: value} временной ряд для одной метрики."""
        table = _history_table(statement)
        rows = self.query(
            f"""
            SELECT p.year, h.value
            FROM {table} h
            JOIN periods p ON h.period_id = p.period_id
            WHERE h.company_id=? AND h.metric=? AND p.is_forecast=0
            ORDER BY p.year
            """,
            (company_id, metric),
        )
        return {r["year"]: r["value"] for r in rows}

    # ── прогноз ────────────────────────────────────────────────────────────────

    def upsert_forecast(
        self,
        company_id: str,
        statement: str,          # IS | BS | CF
        year: int,
        scenario_id: int,
        metrics: Dict[str, float],
        version_id: Optional[int] = None,
    ) -> int:
        table = _forecast_table(statement)
        period_id = self.ensure_period(company_id, year, is_forecast=1)
        rows = [
            (company_id, period_id, scenario_id, version_id, metric, value)
            for metric, value in metrics.items()
            if value is not None
        ]
        self.conn.executemany(
            f"""
            INSERT INTO {table}
                (company_id, period_id, scenario_id, version_id, metric, value, updated_at)
            VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(company_id, period_id, scenario_id, metric) DO UPDATE SET
                value      = excluded.value,
                version_id = excluded.version_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            rows,
        )
        return len(rows)

    def get_forecast(
        self,
        company_id: str,
        statement: str,
        scenario_id: int,
        years: Optional[List[int]] = None,
    ) -> Dict[int, Dict[str, float]]:
        table = _forecast_table(statement)
        if years:
            placeholders = ",".join("?" * len(years))
            sql = f"""
                SELECT p.year, f.metric, f.value
                FROM {table} f
                JOIN periods p ON f.period_id = p.period_id
                WHERE f.company_id=? AND f.scenario_id=? AND p.year IN ({placeholders})
                ORDER BY p.year
            """
            rows = self.query(sql, (company_id, scenario_id, *years))
        else:
            sql = f"""
                SELECT p.year, f.metric, f.value
                FROM {table} f
                JOIN periods p ON f.period_id = p.period_id
                WHERE f.company_id=? AND f.scenario_id=?
                ORDER BY p.year
            """
            rows = self.query(sql, (company_id, scenario_id))

        result: Dict[int, Dict[str, float]] = {}
        for row in rows:
            yr = row["year"]
            if yr not in result:
                result[yr] = {}
            result[yr][row["metric"]] = row["value"]
        return result

    def delete_forecast(self, company_id: str, scenario_id: int) -> None:
        """Удалить все прогнозные данные сценария (для пересчёта)."""
        for table in ("forecast_is", "forecast_bs", "forecast_cf"):
            self.execute(
                f"DELETE FROM {table} WHERE company_id=? AND scenario_id=?",
                (company_id, scenario_id),
            )

    # ── препроцессор ───────────────────────────────────────────────────────────

    def upsert_preprocess(
        self,
        company_id: str,
        metric_group: str,
        metrics: Dict[str, Any],   # {metric_name: value} или {metric_name: {year: value}}
        source: str = "preprocessor",
    ) -> int:
        """
        Записывает метрики препроцессора.
        Если value — dict {year: float}, записывает по годам.
        Если value — scalar, записывает с year=-1 (сводная метрика).
        """
        rows = []
        for metric_name, val in metrics.items():
            if isinstance(val, dict):
                for year, v in val.items():
                    if v is None:
                        continue
                    if isinstance(year, str) and year.startswith("_"):
                        # _ewa/_mean/_last/_recommended → metric_name_ewa at year=-1
                        rows.append((company_id, metric_group, metric_name + year, -1, v, source))
                    else:
                        rows.append((company_id, metric_group, metric_name, year, v, source))
            elif val is not None:
                rows.append((company_id, metric_group, metric_name, -1, val, source))

        self.conn.executemany(
            """
            INSERT INTO preprocess_metrics
                (company_id, metric_group, metric_name, year, value, source, updated_at)
            VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(company_id, metric_group, metric_name, year) DO UPDATE SET
                value      = excluded.value,
                source     = excluded.source,
                updated_at = CURRENT_TIMESTAMP
            """,
            rows,
        )
        return len(rows)

    def get_preprocess(
        self,
        company_id: str,
        metric_group: str,
        metric_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Возвращает метрики группы.
        Для year=-1 возвращает scalar, для year>0 возвращает {year: value}.
        """
        if metric_name:
            rows = self.query(
                "SELECT metric_name, year, value FROM preprocess_metrics "
                "WHERE company_id=? AND metric_group=? AND metric_name=? ORDER BY year",
                (company_id, metric_group, metric_name),
            )
        else:
            rows = self.query(
                "SELECT metric_name, year, value FROM preprocess_metrics "
                "WHERE company_id=? AND metric_group=? ORDER BY metric_name, year",
                (company_id, metric_group),
            )

        result: Dict[str, Any] = {}
        for row in rows:
            name = row["metric_name"]
            year = row["year"]
            val  = row["value"]
            if year == -1:
                if isinstance(result.get(name), dict):
                    # Already has year-keyed entries → add -1 to the dict
                    result[name][-1] = val
                else:
                    result[name] = val
            else:
                if name not in result:
                    result[name] = {}
                elif not isinstance(result[name], dict):
                    # Was scalar (from year=-1) → convert to dict
                    result[name] = {-1: result[name]}
                result[name][year] = val
        return result

    def get_preprocess_scalar(
        self, company_id: str, metric_group: str, metric_name: str, default=None
    ):
        """Быстрый запрос сводной метрики (year=-1)."""
        return self.query_scalar(
            "SELECT value FROM preprocess_metrics "
            "WHERE company_id=? AND metric_group=? AND metric_name=? AND year=-1",
            (company_id, metric_group, metric_name),
            default=default,
        )

    # ── долговые расписания ────────────────────────────────────────────────────

    def upsert_debt_instrument(self, company_id: str, **fields) -> None:
        instrument_id = fields.pop("instrument_id")
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" * len(fields))
        updates = ", ".join(f"{k} = excluded.{k}" for k in fields)
        self.execute(
            f"""
            INSERT INTO debt_instruments (instrument_id, company_id, {cols})
            VALUES (?, ?, {placeholders})
            ON CONFLICT(instrument_id, company_id) DO UPDATE SET {updates}
            """,
            (instrument_id, company_id, *fields.values()),
        )

    def get_debt_instruments(self, company_id: str) -> List[Dict[str, Any]]:
        return self.query(
            "SELECT * FROM debt_instruments WHERE company_id=? ORDER BY instrument_id",
            (company_id,),
        )

    def upsert_debt_schedule(
        self, company_id: str, year: int, rows: List[Dict[str, Any]]
    ) -> int:
        period_id = self.ensure_period(company_id, year)
        data = [
            (
                company_id, period_id,
                r["instrument_id"], r.get("instrument_name"),
                r.get("opening_balance", 0), r.get("draw", 0),
                r.get("repay_mandatory", 0), r.get("repay_voluntary", 0),
                r.get("interest_expense", 0), r.get("interest_paid", 0),
                r.get("closing_balance", 0), r.get("interest_rate"),
                r.get("classification", "LT"), r.get("source"),
            )
            for r in rows
        ]
        self.conn.executemany(
            """
            INSERT INTO debt_schedule
                (company_id, period_id, instrument_id, instrument_name,
                 opening_balance, draw, repay_mandatory, repay_voluntary,
                 interest_expense, interest_paid, closing_balance,
                 interest_rate, classification, source, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(company_id, period_id, instrument_id) DO UPDATE SET
                opening_balance  = excluded.opening_balance,
                draw             = excluded.draw,
                repay_mandatory  = excluded.repay_mandatory,
                repay_voluntary  = excluded.repay_voluntary,
                interest_expense = excluded.interest_expense,
                interest_paid    = excluded.interest_paid,
                closing_balance  = excluded.closing_balance,
                interest_rate    = excluded.interest_rate,
                classification   = excluded.classification,
                source           = excluded.source,
                updated_at       = CURRENT_TIMESTAMP
            """,
            data,
        )
        return len(data)

    def get_debt_schedule(self, company_id: str, year: int) -> List[Dict[str, Any]]:
        return self.query(
            """
            SELECT d.* FROM debt_schedule d
            JOIN periods p ON d.period_id = p.period_id
            WHERE d.company_id=? AND p.year=?
            """,
            (company_id, year),
        )

    # ── макро ──────────────────────────────────────────────────────────────────

    def upsert_macro_factors(
        self,
        data: Dict[str, Dict[int, float]],   # {factor_name: {year: value}}
        scope: str = "global",
        company_id: Optional[str] = None,
        source: str = "",
    ) -> int:
        rows = []
        for factor_name, series in data.items():
            for year, value in series.items():
                rows.append((factor_name, year, value, scope, company_id or "", source))
        self.conn.executemany(
            """
            INSERT INTO macro_factors (factor_name, year, value, scope, company_id, source, updated_at)
            VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(factor_name, year, scope, company_id) DO UPDATE SET
                value      = excluded.value,
                source     = excluded.source,
                updated_at = CURRENT_TIMESTAMP
            """,
            rows,
        )
        return len(rows)

    def get_macro_factor(
        self, factor_name: str, scope: str = "global", company_id: Optional[str] = None
    ) -> Dict[int, float]:
        rows = self.query(
            "SELECT year, value FROM macro_factors "
            "WHERE factor_name=? AND scope=? ORDER BY year",
            (factor_name, scope),
        )
        return {r["year"]: r["value"] for r in rows}

    def upsert_macro_forecasts(
        self,
        company_id: str,
        scenario_id: int,
        data: Dict[str, Dict[int, float]],
        method: str = "",
    ) -> int:
        rows = []
        for factor_name, series in data.items():
            for year, value in series.items():
                rows.append((company_id, factor_name, year, value, method, scenario_id))
        self.conn.executemany(
            """
            INSERT INTO macro_forecasts
                (company_id, factor_name, year, value, method, scenario_id, updated_at)
            VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(company_id, factor_name, year, scenario_id) DO UPDATE SET
                value      = excluded.value,
                method     = excluded.method,
                updated_at = CURRENT_TIMESTAMP
            """,
            rows,
        )
        return len(rows)

    def get_macro_forecasts(
        self, company_id: str, scenario_id: Optional[int] = None
    ) -> Dict[str, Dict[int, float]]:
        if scenario_id is not None:
            rows = self.query(
                "SELECT factor_name, year, value FROM macro_forecasts "
                "WHERE company_id=? AND scenario_id=? ORDER BY factor_name, year",
                (company_id, scenario_id),
            )
        else:
            rows = self.query(
                "SELECT factor_name, year, value FROM macro_forecasts "
                "WHERE company_id=? ORDER BY factor_name, year",
                (company_id,),
            )
        result: Dict[str, Dict[int, float]] = {}
        for row in rows:
            fn = row["factor_name"]
            if fn not in result:
                result[fn] = {}
            result[fn][row["year"]] = row["value"]
        return result

    # ── результаты: стресс / ковенанты / рейтинг ──────────────────────────────

    def upsert_stress_results(
        self,
        company_id: str,
        stress_scenario_id: int,
        year: int,
        statement: str,
        metrics: Dict[str, float],
    ) -> int:
        period_id = self.ensure_period(company_id, year, is_forecast=1)
        rows = [
            (company_id, stress_scenario_id, period_id, statement, metric, value)
            for metric, value in metrics.items()
            if value is not None
        ]
        self.conn.executemany(
            """
            INSERT INTO stress_results
                (company_id, stress_scenario_id, period_id, statement_type, metric, value, updated_at)
            VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(company_id, stress_scenario_id, period_id, statement_type, metric) DO UPDATE SET
                value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """,
            rows,
        )
        return len(rows)

    def upsert_covenant_results(
        self,
        company_id: str,
        scenario_id: int,
        year: int,
        covenants: List[Dict[str, Any]],
    ) -> int:
        period_id = self.ensure_period(company_id, year, is_forecast=1)
        rows = [
            (
                company_id, scenario_id, period_id,
                c["covenant_name"], c.get("value"), c.get("threshold"),
                c.get("headroom_pct"), 1 if c.get("breached") else 0,
            )
            for c in covenants
        ]
        self.conn.executemany(
            """
            INSERT INTO covenant_results
                (company_id, scenario_id, period_id, covenant_name,
                 value, threshold, headroom_pct, breached, updated_at)
            VALUES (?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(company_id, scenario_id, period_id, covenant_name) DO UPDATE SET
                value       = excluded.value,
                threshold   = excluded.threshold,
                headroom_pct = excluded.headroom_pct,
                breached    = excluded.breached,
                updated_at  = CURRENT_TIMESTAMP
            """,
            rows,
        )
        return len(rows)

    def upsert_rating(
        self,
        company_id: str,
        scenario_id: int,
        year: int,
        methodology: str,
        grade: str,
        score: float,
        factor_metrics: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        period_id = self.ensure_period(company_id, year, is_forecast=1)
        self.execute(
            """
            INSERT INTO ratings
                (company_id, scenario_id, period_id, methodology, grade, score, updated_at)
            VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(company_id, scenario_id, period_id, methodology) DO UPDATE SET
                grade = excluded.grade, score = excluded.score, updated_at = CURRENT_TIMESTAMP
            """,
            (company_id, scenario_id, period_id, methodology, grade, score),
        )
        # rating_id
        row = self.query_one(
            "SELECT rowid FROM ratings WHERE company_id=? AND scenario_id=? "
            "AND period_id=? AND methodology=?",
            (company_id, scenario_id, period_id, methodology),
        )
        rating_id = row["rowid"] if row else None

        if factor_metrics and rating_id:
            fm_rows = [
                (rating_id, fm["factor_name"], fm["metric_name"],
                 fm.get("value"), fm.get("score"), fm.get("weight"))
                for fm in factor_metrics
            ]
            self.conn.executemany(
                """
                INSERT OR REPLACE INTO rating_metrics
                    (rating_id, factor_name, metric_name, value, score, weight)
                VALUES (?,?,?,?,?,?)
                """,
                fm_rows,
            )
        return rating_id or 0

    # ── аудит ──────────────────────────────────────────────────────────────────

    def log(
        self,
        operation: str,
        table_name: str = "",
        company_id: str = "",
        record_id: str = "",
        details: Optional[Dict] = None,
    ) -> None:
        self.execute(
            "INSERT INTO audit_log (operation, table_name, company_id, record_id, details) "
            "VALUES (?,?,?,?,?)",
            (operation, table_name, company_id, record_id,
             json.dumps(details) if details else None),
        )


# ── helpers ────────────────────────────────────────────────────────────────────

def _history_table(statement: str) -> str:
    t = statement.upper()
    if t not in ("IS", "BS", "CF"):
        raise ValueError(f"Unknown statement type: {statement!r}")
    return f"history_{t.lower()}"


def _forecast_table(statement: str) -> str:
    t = statement.upper()
    if t not in ("IS", "BS", "CF"):
        raise ValueError(f"Unknown statement type: {statement!r}")
    return f"forecast_{t.lower()}"
