#!/usr/bin/env python3
"""Экспорт компании из Vertex PostgreSQL в standalone data_mart_v2.db.

Нужен для запуска engine компаний, живущих только в Vertex (Nornickel и др.):
SQLite-март — рабочая БД движка, Vertex — production с версионированием.

Маппинг (Vertex stress_v2 → SQLite):
  versions (последний draft/baseline)   → выбор version_id
  historical_data (EAV statement/year)  → history_is / history_bs / history_cf
  debt_instruments                      → debt_instruments (opening_balance=outstanding, USD)
  preprocess_metrics                    → preprocess_metrics
  companies                             → companies
  scenarios: создаётся 'base' при отсутствии
Сегментная история берётся из project.yaml (volume/price_history), макро-история
глобальная (уже в SQLite); base-макро-путь допишет engine/macro/scenario_config.py.

Использование:
  python3 tools/export_vertex_to_mart.py --company nornickel
  PG_DSN="postgresql://vertex:PASS@localhost:5432/vertex_db" python3 tools/export_vertex_to_mart.py
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PG_DSN = os.environ.get(
    "PG_DSN", "postgresql://vertex:VxwQLqiNmaZKblDN7pg@localhost:5432/vertex_db"
)
MART = ROOT / "data_mart_v2.db"

STMT_MAP = {"is": "history_is", "bs": "history_bs", "cf": "history_cf"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def export(company: str) -> None:
    pg = psycopg2.connect(PG_DSN)
    pg.cursor_factory = psycopg2.extras.RealDictCursor
    cur = pg.cursor()

    cur.execute(
        "SELECT id, version_tag, status, created_at FROM stress_v2.versions "
        "WHERE company_id=%s ORDER BY created_at DESC LIMIT 1", (company,))
    ver = cur.fetchone()
    if not ver:
        raise SystemExit(f"В Vertex нет версий для {company}")
    vid = ver["id"]
    print(f"Vertex version: {ver['version_tag']} ({ver['status']}, {ver['created_at']})")

    mart = sqlite3.connect(MART)
    mart.execute("PRAGMA foreign_keys=OFF")
    now = _now()

    # companies
    cur.execute("SELECT name, sector, currency, country FROM stress_v2.companies WHERE id=%s", (company,))
    co = cur.fetchone()
    mart.execute(
        "INSERT OR REPLACE INTO companies (company_id, name, industry, currency, "
        "accounting_standard, db_unit, fiscal_year_end, country, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (company, co["name"], co["sector"] or "", co["currency"] or "USD", "IFRS", "USD", "12-31",
         co["country"] or "", now, now))

    # periods: history 2009-2025 + forecast 2026-2028
    cur.execute("SELECT MIN(year) y0, MAX(year) y1 FROM stress_v2.historical_data WHERE version_id=%s", (vid,))
    yrs = cur.fetchone()
    y0, y1 = int(yrs["y0"]), int(yrs["y1"])
    fc_end = y1 + 3
    pid: dict[int, int] = {}
    for y in range(y0, fc_end + 1):
        row = mart.execute(
            "SELECT period_id FROM periods WHERE company_id=? AND year=?", (company, y)).fetchone()
        if row:
            pid[y] = row[0]
            mart.execute("UPDATE periods SET is_forecast=? WHERE period_id=?",
                         (1 if y > y1 else 0, row[0]))
        else:
            new_id = (mart.execute("SELECT COALESCE(MAX(period_id),0)+1 FROM periods").fetchone()[0])
            mart.execute("INSERT INTO periods (period_id, company_id, year, is_annual, is_forecast) "
                         "VALUES (?,?,?,1,?)", (new_id, company, y, 1 if y > y1 else 0))
            pid[y] = new_id

    # history statements
    for st, tbl in STMT_MAP.items():
        mart.execute(f"DELETE FROM {tbl} WHERE company_id=?", (company,))
        cur.execute(
            "SELECT year, metric, value, source FROM stress_v2.historical_data "
            "WHERE version_id=%s AND statement=%s ORDER BY year, metric", (vid, st))
        n = 0
        for r in cur.fetchall():
            if r["value"] is None or r["year"] not in pid:
                continue
            mart.execute(
                f"INSERT OR REPLACE INTO {tbl} (company_id, period_id, metric, value, source, updated_at) "
                "VALUES (?,?,?,?,?,?)",
                (company, pid[int(r["year"])], r["metric"], float(r["value"]),
                 r["source"] or "vertex", now))
            n += 1
        print(f"  {tbl}: {n} строк ({y0}-{y1})")

    # debt instruments
    mart.execute("DELETE FROM debt_instruments WHERE company_id=?", (company,))
    cur.execute(
        "SELECT instrument_id, instrument_name, instrument_type, currency, outstanding, "
        "interest_rate, is_fixed_rate, maturity_date, amortization_type "
        "FROM stress_v2.debt_instruments WHERE version_id=%s", (vid,))
    n = 0
    for r in cur.fetchall():
        rate = float(r["interest_rate"] or 0)
        mart.execute(
            "INSERT OR REPLACE INTO debt_instruments "
            "(instrument_id, company_id, instrument_name, db_type, currency, opening_balance, "
            "committed_amount, maturity_date, interest_rate, rate_type, base_rate_factor, "
            "payment_frequency, amortization_profile, callable_flag, covenant_package, source, "
            "updated_at, schedule_year, instrument_class, rate_description) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (r["instrument_id"], company, r["instrument_name"], r["instrument_type"] or "term_loan",
             r["currency"] or "USD", float(r["outstanding"] or 0), None,
             str(r["maturity_date"] or ""), rate,
             "fixed" if r["is_fixed_rate"] else "floating",
             # P2: базис флоатеров (RUB→ЦБ, EUR→Euribor; USD-SOFR — не поддержан, fixed)
             (None if r["is_fixed_rate"]
              else ("euribor_6m" if (r["currency"] or "") == "EUR" else "cbr_key_rate")),
             "semi_annual", r["amortization_type"] or "bullet", 0, None, "vertex", now,
             y1, r["instrument_type"] or "", None))
        n += 1
    print(f"  debt_instruments: {n}")

    # preprocess_metrics
    mart.execute("DELETE FROM preprocess_metrics WHERE company_id=?", (company,))
    cur.execute(
        "SELECT metric_group, metric_name, year, value, source FROM stress_v2.preprocess_metrics "
        "WHERE version_id=%s", (vid,))
    n = 0
    for r in cur.fetchall():
        if r["value"] is None:
            continue
        mart.execute(
            "INSERT OR REPLACE INTO preprocess_metrics "
            "(company_id, metric_group, metric_name, year, value, source, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (company, r["metric_group"], r["metric_name"], int(r["year"]),
             float(r["value"]), r["source"] or "vertex", now))
        n += 1
    print(f"  preprocess_metrics: {n}")

    # ── LME-история для металлических компаний ────────────────────────────────
    # В Vertex истории LME-металлов нет (только РФ-макро) → сидируем из
    # ols_supplement конфига SSOT (номинальные средние, та же база, что у книг).
    import yaml as _yaml
    mc = _yaml.safe_load((ROOT / "templates/excel_v4/config/macro_scenarios.yaml").read_text(encoding="utf-8"))
    supp = mc.get("ols_supplement", {})
    lme_map = {"lme_nickel": "lme_ni_usd", "lme_copper": "lme_cu_usd",
               "lme_palladium": "lme_pd_usd", "lme_platinum": "lme_pt_usd"}
    for src_f, dst_f in lme_map.items():
        rows = supp.get(src_f, {})
        if not rows:
            continue
        n = 0
        for y, v in rows.items():
            mart.execute(
                "INSERT OR REPLACE INTO macro_factors (factor_name, year, value, unit, scope, company_id, source, updated_at) "
                "VALUES (?,?,?,?, 'global', '', 'ols_supplement(yaml)', ?)",
                (dst_f, int(y), float(v), "USD/t", now))
            n += 1
        if n:
            print(f"  macro_factors {dst_f}: {n} лет ({min(rows)}-{max(rows)})")

    # scenario base
    row = mart.execute("SELECT scenario_id FROM scenarios WHERE company_id=? AND name='base'", (company,)).fetchone()
    if not row:
        new_id = mart.execute("SELECT COALESCE(MAX(scenario_id),0)+1 FROM scenarios").fetchone()[0]
        mart.execute("INSERT INTO scenarios (scenario_id, company_id, name, type, description, created_at, scenario_name) "
                     "VALUES (?,?,'base','base','Base scenario (Vertex export)',?, 'base')", (new_id, company, now))
        print(f"  scenario base: id={new_id}")

    mart.commit()
    mart.close()
    pg.close()
    print(f"✓ {company} экспортирован в {MART}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", default="nornickel")
    args = ap.parse_args()
    export(args.company)
