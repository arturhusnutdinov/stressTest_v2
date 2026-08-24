"""sync_sv2_to_vertex.py — полная синхронизация SQLite → PG (stress_v2 схема).

Синхронизирует:
  ✅ IS/BS/CF прогнозы (base сценарий)     — уже синхронизировались
  🆕 stress_results (все стресс-сценарии) → forecast_is/bs/cf (стресс-сценарии)
  🆕 preprocess_metrics                   → sv2_versions.assumptions JSONB
  🆕 debt_instruments                     → stress_v2.debt

Запуск:
  cd /Users/arturhusnutdinov/Documents/IT\ Development/Docker/stressTest_v2
  python tools/sync_sv2_to_vertex.py [--company rusal] [--skip-stress] [--skip-preprocess] [--skip-debt]

Переменные окружения:
  PG_DSN — строка подключения (default: postgresql://vertex:vertex@localhost:15432/vertex_db)
  SQLITE_DB — путь к SQLite (default: data_mart_v2.db рядом со скриптом)
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import uuid
from pathlib import Path

import psycopg2
import psycopg2.extras

# ── Конфигурация ──────────────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parent.parent
SQLITE_DB  = os.environ.get("SQLITE_DB", str(_ROOT / "data_mart_v2.db"))
PG_DSN     = os.environ.get("PG_DSN", "postgresql://vertex:vertex@localhost:15432/vertex_db")

COMPANIES  = ["rusal", "us_steel"]
VERSION_TAG = "Q3_2026"
SCENARIO_BASE = "base"

# Маппинг statement_type → PG таблица
_STMT_TABLE = {
    "IS": "forecast_is",
    "BS": "forecast_bs",
    "CF": "forecast_cf",
}


# ── SQLite helpers ─────────────────────────────────────────────────────────────

def sqlite_connect() -> sqlite3.Connection:
    if not Path(SQLITE_DB).exists():
        print(f"[ERROR] SQLite DB не найдена: {SQLITE_DB}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = sqlite3.Row
    return conn


# ── PG helpers ────────────────────────────────────────────────────────────────

def pg_connect() -> psycopg2.extensions.connection:
    return psycopg2.connect(PG_DSN)


def _get_pg_ids(pg: psycopg2.extensions.connection, company_id: str, version_tag: str) -> tuple[str, str] | None:
    """Возвращает (version_id, base_scenario_id) из PG для компании."""
    with pg.cursor() as cur:
        cur.execute("""
            SELECT v.id
            FROM stress_v2.versions v
            WHERE v.company_id = %s AND v.version_tag = %s
            LIMIT 1
        """, (company_id, version_tag))
        row = cur.fetchone()
        if not row:
            return None
        version_id = str(row[0])

        cur.execute("""
            SELECT id FROM stress_v2.scenarios
            WHERE version_id = %s AND name = %s
            LIMIT 1
        """, (version_id, SCENARIO_BASE))
        sc_row = cur.fetchone()
        if not sc_row:
            return None
        return version_id, str(sc_row[0])


def _get_or_create_stress_scenario(
    pg: psycopg2.extensions.connection,
    version_id: str,
    scenario_name: str,
) -> str:
    """Возвращает scenario_id для стресс-сценария, создаёт если нет."""
    with pg.cursor() as cur:
        cur.execute("""
            SELECT id FROM stress_v2.scenarios
            WHERE version_id = %s AND name = %s
        """, (version_id, scenario_name))
        row = cur.fetchone()
        if row:
            return str(row[0])

        sc_id = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO stress_v2.scenarios (id, version_id, name, type, description)
            VALUES (%s, %s, %s, 'stress', %s)
        """, (sc_id, version_id, scenario_name, f"Stress scenario: {scenario_name}"))
        pg.commit()
        return sc_id


# ── Sync stress_results ───────────────────────────────────────────────────────

def sync_stress_results(
    sq: sqlite3.Connection,
    pg: psycopg2.extensions.connection,
    company_id: str,
    ids: tuple[str, str],
) -> int:
    """Синхронизирует stress_results (IS/BS/CF) → PG forecast_is/bs/cf.

    Читает все стресс-сценарии компании из SQLite, создаёт соответствующие
    сценарии в PG и записывает прогнозы.
    """
    version_id, _ = ids
    total = 0

    # Получаем стресс-сценарии компании из SQLite
    stress_scenarios = sq.execute("""
        SELECT s.scenario_id, s.name
        FROM scenarios s
        WHERE s.company_id = ?
          AND s.type IN ('stress', 'bear', 'bull', 'severe', 'custom')
        ORDER BY s.scenario_id
    """, (company_id,)).fetchall()

    if not stress_scenarios:
        print(f"  [SKIP] {company_id}: нет стресс-сценариев в SQLite")
        return 0

    print(f"  Стресс-сценарии: {[s['name'] for s in stress_scenarios]}")

    for sc_sqlite in stress_scenarios:
        sc_name = sc_sqlite["name"]
        sc_id_sqlite = sc_sqlite["scenario_id"]

        # Читаем stress_results из SQLite
        results = sq.execute("""
            SELECT sr.period_id, p.year, sr.statement_type, sr.metric, sr.value
            FROM stress_results sr
            JOIN periods p ON p.period_id = sr.period_id
            WHERE sr.company_id = ? AND sr.stress_scenario_id = ?
            ORDER BY p.year, sr.statement_type, sr.metric
        """, (company_id, sc_id_sqlite)).fetchall()

        if not results:
            print(f"  [SKIP] {company_id}/{sc_name}: пустые stress_results")
            continue

        # Получаем/создаём PG scenario для этого стресс-сценария
        pg_sc_id = _get_or_create_stress_scenario(pg, version_id, sc_name)

        # Группируем по statement_type и записываем
        from collections import defaultdict
        by_stmt: dict[str, list] = defaultdict(list)
        for row in results:
            by_stmt[row["statement_type"]].append(row)

        with pg.cursor() as cur:
            n_written = 0
            for stmt_type, rows in by_stmt.items():
                table = _STMT_TABLE.get(stmt_type.upper())
                if not table:
                    continue
                for row in rows:
                    cur.execute(f"""
                        INSERT INTO stress_v2.{table}
                            (version_id, scenario_id, year, is_forecast, metric, value)
                        VALUES (%s, %s, %s, TRUE, %s, %s)
                        ON CONFLICT (version_id, scenario_id, year, metric) DO UPDATE
                        SET value = EXCLUDED.value
                    """, (version_id, pg_sc_id, row["year"],
                          row["metric"], row["value"]))
                    n_written += 1

        pg.commit()
        print(f"  {company_id}/{sc_name}: {n_written} строк stress_results → PG")
        total += n_written

    return total


# ── Sync preprocess_metrics ───────────────────────────────────────────────────

def sync_preprocess_metrics(
    sq: sqlite3.Connection,
    pg: psycopg2.extensions.connection,
    company_id: str,
    ids: tuple[str, str],
) -> int:
    """Синхронизирует preprocess_metrics → sv2_versions.assumptions JSONB.

    Структура JSON: {"preprocess_metrics": {metric_group: {metric_name: {year: value}}}}
    """
    version_id, _ = ids

    rows = sq.execute("""
        SELECT metric_group, metric_name, year, value
        FROM preprocess_metrics
        WHERE company_id = ?
        ORDER BY metric_group, metric_name, year
    """, (company_id,)).fetchall()

    if not rows:
        print(f"  [SKIP] {company_id}: нет preprocess_metrics")
        return 0

    # Строим вложенный dict
    pm: dict[str, dict[str, dict]] = {}
    for row in rows:
        mg = row["metric_group"]
        mn = row["metric_name"]
        yr = row["year"]
        val = row["value"]
        pm.setdefault(mg, {}).setdefault(mn, {})[str(yr)] = val

    # Читаем текущий assumptions из PG
    with pg.cursor() as cur:
        cur.execute("""
            SELECT assumptions FROM stress_v2.versions WHERE id = %s
        """, (version_id,))
        existing = cur.fetchone()
        current_assumptions = existing[0] if existing and existing[0] else {}
        if isinstance(current_assumptions, str):
            current_assumptions = json.loads(current_assumptions)

        # Мержим preprocess_metrics в assumptions
        current_assumptions["preprocess_metrics"] = pm

        cur.execute("""
            UPDATE stress_v2.versions
            SET assumptions = %s
            WHERE id = %s
        """, (json.dumps(current_assumptions), version_id))

    pg.commit()
    n = sum(
        len(vals)
        for mg in pm.values()
        for vals in mg.values()
    )
    print(f"  {company_id}: preprocess_metrics → assumptions JSONB ({len(pm)} групп, {n} значений)")
    return n


# ── Sync debt_instruments ─────────────────────────────────────────────────────

def sync_debt_instruments(
    sq: sqlite3.Connection,
    pg: psycopg2.extensions.connection,
    company_id: str,
    ids: tuple[str, str],
) -> int:
    """Синхронизирует debt_instruments → stress_v2.debt."""
    version_id, _ = ids

    rows = sq.execute("""
        SELECT instrument_id, instrument_name, db_type, currency,
               opening_balance, committed_amount, maturity_date,
               interest_rate, rate_type
        FROM debt_instruments
        WHERE company_id = ?
        ORDER BY instrument_id
    """, (company_id,)).fetchall()

    if not rows:
        print(f"  [SKIP] {company_id}: нет debt_instruments")
        return 0

    # Удаляем старые записи для этой версии (idempotent)
    with pg.cursor() as cur:
        cur.execute("DELETE FROM stress_v2.debt WHERE version_id = %s", (version_id,))

    n_written = 0
    with pg.cursor() as cur:
        for row in rows:
            # Извлекаем год погашения из maturity_date (YYYY-MM-DD → год)
            maturity_year = None
            maturity_date_str = row["maturity_date"]
            if maturity_date_str:
                try:
                    maturity_year = int(maturity_date_str[:4])
                except (ValueError, TypeError):
                    pass

            # amount: открытый баланс (основной долг)
            amount = row["opening_balance"] or row["committed_amount"]

            cur.execute("""
                INSERT INTO stress_v2.debt
                    (id, version_id, instrument_name, instrument_type, currency,
                     amount, maturity_year, maturity_date, rate, rate_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                str(uuid.uuid4()),
                version_id,
                row["instrument_name"],
                row["db_type"],
                row["currency"] or "USD",
                amount,
                maturity_year,
                maturity_date_str,
                row["interest_rate"],
                row["rate_type"] or "fixed",
            ))
            n_written += 1

    pg.commit()
    print(f"  {company_id}: {n_written} debt_instruments → stress_v2.debt")
    return n_written


# ── Главная функция ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="sync_sv2_to_vertex: полная синхронизация")
    parser.add_argument("--company", nargs="+", default=COMPANIES, help="Компании для синхронизации")
    parser.add_argument("--skip-stress",     action="store_true", help="Пропустить stress_results")
    parser.add_argument("--skip-preprocess", action="store_true", help="Пропустить preprocess_metrics")
    parser.add_argument("--skip-debt",       action="store_true", help="Пропустить debt_instruments")
    parser.add_argument("--version-tag", default=VERSION_TAG, help=f"Версия (default: {VERSION_TAG})")
    args = parser.parse_args()

    print(f"SQLite DB:   {SQLITE_DB}")
    print(f"PG target:   {PG_DSN.split('@')[-1]}")
    print(f"Companies:   {args.company}")
    print(f"Version tag: {args.version_tag}")
    print()

    sq = sqlite_connect()
    pg = pg_connect()

    total_ok = 0
    total_fail = 0

    for company_id in args.company:
        print("=" * 60)
        print(f"  {company_id}")
        print("=" * 60)

        ids = _get_pg_ids(pg, company_id, args.version_tag)
        if not ids:
            print(f"  [ERROR] {company_id}: версия {args.version_tag} не найдена в PG — пропускаем")
            print(f"          Сначала запустите базовую синхронизацию IS/BS/CF")
            total_fail += 1
            continue

        version_id, base_sc_id = ids
        print(f"  version_id={version_id[:8]}..., base_sc_id={base_sc_id[:8]}...")

        try:
            if not args.skip_stress:
                n = sync_stress_results(sq, pg, company_id, ids)
                print(f"  ✓ stress_results: {n} строк")

            if not args.skip_preprocess:
                n = sync_preprocess_metrics(sq, pg, company_id, ids)
                print(f"  ✓ preprocess_metrics: {n} значений")

            if not args.skip_debt:
                n = sync_debt_instruments(sq, pg, company_id, ids)
                print(f"  ✓ debt_instruments: {n} инструментов")

            print(f"  OK: {company_id} синхронизирован")
            total_ok += 1

        except Exception as exc:
            import traceback
            print(f"  [ERROR] {company_id}: {exc}")
            traceback.print_exc()
            pg.rollback()
            total_fail += 1

    sq.close()
    pg.close()

    print()
    print(f"Итого: {total_ok}/{total_ok + total_fail} компаний синхронизировано")
    if total_fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
