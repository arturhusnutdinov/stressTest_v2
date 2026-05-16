"""
Миграция данных US Steel из data_mart_v3.db → data_mart_v2.db.
Запуск: python3 refactoring_v2/tools/migrate_from_v1.py
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

# Путь к корню проекта
ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "refactoring_v2"))

from engine.database.repository import Repository

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OLD_DB = ROOT / "data_mart_v3.db"
NEW_DB = ROOT / "data_mart_v2.db"
COMPANY = "us_steel"


def connect_old() -> sqlite3.Connection:
    conn = sqlite3.connect(OLD_DB)
    conn.row_factory = sqlite3.Row
    return conn


def migrate_company(old: sqlite3.Connection, repo: Repository) -> None:
    row = old.execute(
        "SELECT * FROM companies WHERE company_id=?", (COMPANY,)
    ).fetchone()
    if row:
        repo.upsert_company(
            company_id=COMPANY,
            name=row["company_name"] if "company_name" in row.keys() else COMPANY,
            industry=row["industry"] or "metallurgy",
            currency=row["currency"] or "USD",
            accounting_standard="US_GAAP",
            db_unit="USD",
        )
        logger.info(f"Компания: {COMPANY}")


def migrate_history(old: sqlite3.Connection, repo: Repository, table: str, statement: str) -> int:
    """Мигрирует history_is / history_bs / history_cf."""
    rows = old.execute(f"""
        SELECT p.year, h.metric, h.value, h.source
        FROM {table} h
        JOIN periods p ON h.period_id = p.period_id
        WHERE h.company_id = ? AND p.is_annual = 1
        ORDER BY p.year, h.metric
    """, (COMPANY,)).fetchall()

    # Группируем по году
    by_year: dict = {}
    for row in rows:
        year = row["year"]
        if year not in by_year:
            by_year[year] = {}
        if row["value"] is not None:
            by_year[year][row["metric"]] = row["value"]

    total = 0
    for year, metrics in sorted(by_year.items()):
        n = repo.upsert_history(COMPANY, statement, year, metrics, source=f"migrate_v1:{table}")
        total += n

    logger.info(f"{table} → history_{statement.lower()}: {len(by_year)} лет, {total} строк")
    return total


def migrate_debt_instruments(old: sqlite3.Connection, repo: Repository) -> int:
    # Пробуем debt_instruments_ext, потом instruments
    for tbl in ("debt_instruments_ext", "instruments"):
        try:
            rows = old.execute(
                f"SELECT * FROM {tbl} WHERE company_id=?", (COMPANY,)
            ).fetchall()
            if not rows:
                continue
            cols = rows[0].keys()
            n = 0
            for row in rows:
                rec = dict(row)
                instrument_id = rec.get("instrument_id") or rec.get("id", "")
                if not instrument_id:
                    continue

                # маппинг типа инструмента
                raw_type = str(rec.get("instrument_type", rec.get("type", "other"))).lower()
                db_type = _map_instrument_type(raw_type)

                repo.upsert_debt_instrument(
                    company_id=COMPANY,
                    instrument_id=str(instrument_id),
                    instrument_name=str(rec.get("instrument_name", rec.get("name", instrument_id))),
                    db_type=db_type,
                    currency=str(rec.get("currency", "USD")),
                    opening_balance=float(rec.get("opening_balance") or 0),
                    maturity_date=str(rec.get("maturity_date", "") or ""),
                    interest_rate=_safe_float(rec.get("interest_rate", rec.get("rate"))),
                    rate_type=str(rec.get("rate_type", "fixed")),
                    payment_frequency=str(rec.get("payment_frequency", "semi_annual")),
                    amortization_profile=str(rec.get("amortization_profile", "bullet")),
                )
                n += 1
            logger.info(f"{tbl} → debt_instruments: {n} инструментов")
            return n
        except sqlite3.OperationalError:
            continue
    logger.warning("debt_instruments: таблица не найдена в старой БД")
    return 0


def migrate_debt_schedule(old: sqlite3.Connection, repo: Repository) -> int:
    try:
        rows = old.execute("""
            SELECT d.*, p.year
            FROM debt_schedule d
            JOIN periods p ON d.period_id = p.period_id
            WHERE d.company_id = ? AND p.is_annual = 1
            ORDER BY p.year, d.instrument_id
        """, (COMPANY,)).fetchall()
    except sqlite3.OperationalError:
        logger.warning("debt_schedule: таблица не найдена")
        return 0

    by_year: dict = {}
    for row in rows:
        year = row["year"]
        if year not in by_year:
            by_year[year] = []
        by_year[year].append({
            "instrument_id":   row["instrument_id"],
            "instrument_name": row["instrument_name"] if "instrument_name" in row.keys() else "",
            "opening_balance": _safe_float(row["opening_balance"]) or 0,
            "draw":            _safe_float(row["draw"]) or 0,
            "repay_mandatory": _safe_float(row["repay_mandatory"]) or 0,
            "repay_voluntary": _safe_float(row["repay_voluntary"]) or 0,
            "interest_expense":_safe_float(row["interest_expense"]) or 0,
            "interest_paid":   _safe_float(row["interest_paid"]) or 0,
            "closing_balance": _safe_float(row["closing_balance"]) or 0,
            "interest_rate":   _safe_float(row["interest_rate"]),
            "classification":  str(row["classification"] if "classification" in row.keys() else "LT"),
            "source":          "migrate_v1",
        })

    total = 0
    for year, schedule_rows in sorted(by_year.items()):
        n = repo.upsert_debt_schedule(COMPANY, year, schedule_rows)
        total += n

    logger.info(f"debt_schedule: {len(by_year)} лет, {total} записей")
    return total


def migrate_ppe_components(old: sqlite3.Connection, repo: Repository) -> int:
    try:
        rows = old.execute("""
            SELECT pc.*, p.year, c.component_name
            FROM ppe_components pc
            JOIN periods p ON pc.period_id = p.period_id
            LEFT JOIN components c ON pc.component_id = c.component_id
            WHERE pc.company_id = ? AND p.is_annual = 1
            ORDER BY p.year
        """, (COMPANY,)).fetchall()
    except sqlite3.OperationalError:
        logger.warning("ppe_components: таблица не найдена")
        return 0

    n = 0
    for row in rows:
        period_id = repo.ensure_period(COMPANY, row["year"])
        component_id = str(row["component_id"]).lower().replace(" ", "_")
        component_name = row["component_name"] if "component_name" in row.keys() else component_id
        if not component_name:
            component_name = row.get("component_name", component_id)

        repo.conn.execute("""
            INSERT INTO ppe_components
                (company_id, period_id, component_id, component_name, value_type, value, useful_life, source, updated_at)
            VALUES (?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(company_id, period_id, component_id, value_type) DO UPDATE SET
                value = excluded.value, updated_at = CURRENT_TIMESTAMP
        """, (
            COMPANY, period_id, component_id, component_name,
            row["value_type"], _safe_float(row["value"]),
            row["useful_life"] if "useful_life" in row.keys() else None,
            "migrate_v1",
        ))
        n += 1

    logger.info(f"ppe_components: {n} записей")
    return n


def migrate_macro_factors(old: sqlite3.Connection, repo: Repository) -> int:
    try:
        rows = old.execute("""
            SELECT factor_name, year, value, scope, source
            FROM macro_factors
            WHERE year > 0
            ORDER BY factor_name, year
        """).fetchall()
    except sqlite3.OperationalError:
        logger.warning("macro_factors: таблица не найдена")
        return 0

    data: dict = {}
    for row in rows:
        fn = row["factor_name"]
        if fn not in data:
            data[fn] = {}
        if row["value"] is not None:
            data[fn][row["year"]] = float(row["value"])

    if not data:
        return 0

    n = repo.upsert_macro_factors(data, scope="global", source="migrate_v1")
    logger.info(f"macro_factors: {len(data)} факторов, {n} точек данных")
    return n


def migrate_tax_schedule(old: sqlite3.Connection, repo: Repository) -> int:
    try:
        rows = old.execute("""
            SELECT ts.*, p.year
            FROM tax_schedule ts
            JOIN periods p ON ts.period_id = p.period_id
            WHERE ts.company_id = ? AND p.is_annual = 1
        """, (COMPANY,)).fetchall()
    except sqlite3.OperationalError:
        logger.warning("tax_schedule: таблица не найдена")
        return 0

    n = 0
    for row in rows:
        period_id = repo.ensure_period(COMPANY, row["year"])
        cols = row.keys()
        repo.conn.execute("""
            INSERT INTO tax_schedule
                (company_id, period_id, ebt, current_tax, deferred_tax,
                 effective_rate, dta_close, dtl_close, source, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(company_id, period_id) DO UPDATE SET
                ebt = excluded.ebt, current_tax = excluded.current_tax,
                deferred_tax = excluded.deferred_tax, updated_at = CURRENT_TIMESTAMP
        """, (
            COMPANY, period_id,
            _safe_float(row["earnings_before_taxes_total"] if "earnings_before_taxes_total" in cols else row.get("ebt")),
            _safe_float(row["current_tax_total"] if "current_tax_total" in cols else row.get("current_tax")),
            _safe_float(row["deferred_tax_total"] if "deferred_tax_total" in cols else row.get("deferred_tax")),
            _safe_float(row["effective_tax_rate"] if "effective_tax_rate" in cols else row.get("effective_rate")),
            _safe_float(row["dta_total"] if "dta_total" in cols else row.get("dta_close")),
            None,  # dtl_close
            "migrate_v1",
        ))
        n += 1

    logger.info(f"tax_schedule: {n} записей")
    return n


def migrate_equity_schedule(old: sqlite3.Connection, repo: Repository) -> int:
    try:
        rows = old.execute("""
            SELECT es.*, p.year
            FROM equity_schedule es
            JOIN periods p ON es.period_id = p.period_id
            WHERE es.company_id = ? AND p.is_annual = 1
        """, (COMPANY,)).fetchall()
    except sqlite3.OperationalError:
        logger.warning("equity_schedule: таблица не найдена")
        return 0

    n = 0
    for row in rows:
        rec = dict(row)
        period_id = repo.ensure_period(COMPANY, rec["year"])
        repo.conn.execute("""
            INSERT INTO equity_schedule
                (company_id, period_id, re_open, dividends, buybacks, re_close, source, updated_at)
            VALUES (?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(company_id, period_id) DO UPDATE SET
                re_close = excluded.re_close, updated_at = CURRENT_TIMESTAMP
        """, (
            COMPANY, period_id,
            _safe_float(rec.get("common_stock_opening") or rec.get("re_open")),
            _safe_float(rec.get("dividends_paid") or rec.get("dividends")),
            _safe_float(rec.get("common_stock_repurchased") or rec.get("buybacks")),
            _safe_float(rec.get("common_stock_ending") or rec.get("re_close")),
            "migrate_v1",
        ))
        n += 1

    logger.info(f"equity_schedule: {n} записей")
    return n


def migrate_preprocess_metrics(old: sqlite3.Connection, repo: Repository) -> int:
    """Мигрирует model_preprocess_metrics если есть."""
    try:
        rows = old.execute("""
            SELECT metric_group, metric_name, year, value
            FROM model_preprocess_metrics
            WHERE company = ?
        """, (COMPANY,)).fetchall()
    except sqlite3.OperationalError:
        logger.warning("model_preprocess_metrics: таблица не найдена")
        return 0

    # Группируем по group+name
    data: dict = {}
    for row in rows:
        group = row["metric_group"]
        name  = row["metric_name"]
        year  = row["year"]
        val   = _safe_float(row["value"])
        if val is None:
            continue
        key = (group, name)
        if key not in data:
            data[key] = {}
        data[key][year] = val

    n = 0
    for (group, name), series in data.items():
        n += repo.upsert_preprocess(
            COMPANY, group, {name: series}, source="migrate_v1"
        )

    logger.info(f"preprocess_metrics: {len(data)} метрик, {n} точек данных")
    return n


def run_migration() -> None:
    if not OLD_DB.exists():
        logger.error(f"Старая БД не найдена: {OLD_DB}")
        sys.exit(1)

    logger.info(f"Миграция: {OLD_DB} → {NEW_DB}")
    logger.info("=" * 60)

    old = connect_old()
    total = 0

    with Repository(db_path=NEW_DB) as repo:
        # Сначала компания — FK требует её наличия
        migrate_company(old, repo)

        # Создать сценарий base
        repo.ensure_scenario(COMPANY, "base", type_="base", description="Base scenario")
        total += migrate_history(old, repo, "history_is", "IS")
        total += migrate_history(old, repo, "history_bs", "BS")
        total += migrate_history(old, repo, "history_cf", "CF")
        total += migrate_debt_instruments(old, repo)
        total += migrate_debt_schedule(old, repo)
        total += migrate_ppe_components(old, repo)
        total += migrate_macro_factors(old, repo)
        total += migrate_tax_schedule(old, repo)
        total += migrate_equity_schedule(old, repo)
        total += migrate_preprocess_metrics(old, repo)

    old.close()

    logger.info("=" * 60)
    logger.info(f"Миграция завершена. Всего записей: {total}")
    logger.info(f"Новая БД: {NEW_DB}")

    # Верификация
    _verify(NEW_DB)


def _verify(db_path: Path) -> None:
    logger.info("\nВерификация новой БД:")
    with Repository(db_path=db_path) as repo:
        companies = repo.list_companies()
        logger.info(f"  Компании: {companies}")

        years_is = repo.get_years(COMPANY, is_forecast=0)
        logger.info(f"  Периоды IS (история): {years_is}")

        hist_2024 = repo.get_history_year(COMPANY, "IS", 2024)
        logger.info(f"  IS 2024 метрик: {len(hist_2024)}")
        for m in ["revenue", "cogs", "gross_profit", "ebitda", "net_income"]:
            v = hist_2024.get(m)
            if v is not None:
                logger.info(f"    {m}: {v:,.0f}")

        debt_instr = repo.get_debt_instruments(COMPANY)
        logger.info(f"  Долговых инструментов: {len(debt_instr)}")

        macro = repo.get_macro_factor("steel_price_hrc")
        logger.info(f"  steel_price_hrc: {len(macro)} точек данных")


# ── helpers ────────────────────────────────────────────────────────────────────

def _safe_float(val) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _map_instrument_type(raw: str) -> str:
    mapping = {
        "revolver": "revolving",
        "revolving_credit": "revolving",
        "rc": "revolving",
        "term_loan": "term_amort",
        "term": "term_amort",
        "bond": "bond_fixed",
        "senior_notes": "bond_fixed",
        "notes": "bond_fixed",
        "finance_lease": "finance_lease",
        "lease": "finance_lease",
    }
    for key, val in mapping.items():
        if key in raw:
            return val
    return "other"


if __name__ == "__main__":
    run_migration()
