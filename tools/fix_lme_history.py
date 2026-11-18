#!/usr/bin/env python3
"""Исправление истории LME Aluminium на номинальные годовые средние (Westmetall).

Исходный ряд (driver CSV → БД) был занижен ~20-25% относительно номинальных
среднегодовых LME (напр. 2021: 1 783 vs номинал 2 484). Исправляет:
  - macro_factors: lme_aluminium (company_id='rusal'), lme_al / lme_aluminium (global)
  - macro_forecasts: исторические строки 2023-2025 тех же факторов
  - companies/rusal/_archive/drivers/lme_primary.csv (legacy fallback)

SSOT значений: templates/excel_v4/config/macro_scenarios.yaml → lme_al_history.
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.macro.scenario_config import get_lme_al_history  # noqa: E402

DB = ROOT / "data_mart_v2.db"
CSV_PATH = ROOT / "companies/rusal/_archive/drivers/lme_primary.csv"

FACTORS_DB = [
    ("lme_aluminium", "rusal"),
    ("lme_aluminium", None),
    ("lme_al", None),
]


def main() -> None:
    hist = get_lme_al_history()
    print(f"История: {len(hist)} лет, {min(hist)}-{max(hist)}; 2024={hist[2024]}, 2025={hist[2025]}, 2026={hist[2026]}")

    db = sqlite3.connect(DB)
    cur = db.cursor()
    n = 0
    for factor, company in FACTORS_DB:
        # company_id: 'rusal' для привязанных строк, '' (пустая строка) для global
        co_clause = "company_id=?" if company else "company_id=''"
        args0 = (factor,) if company else (factor,)
        for year, val in hist.items():
            if year == 2026:
                continue  # частичный год не пишем в историю
            if company:
                cur.execute(
                    f"UPDATE macro_factors SET value=? WHERE factor_name=? AND {co_clause} AND year=?",
                    (val, factor, company, year))
            else:
                cur.execute(
                    f"UPDATE macro_factors SET value=? WHERE factor_name=? AND {co_clause} AND year=?",
                    (val, factor, year))
            n += cur.rowcount
        # Исторические строки в macro_forecasts (2023-2025) — для консистентности
        for year in (2023, 2024, 2025):
            if company:
                cur.execute(
                    f"UPDATE macro_forecasts SET value=? WHERE factor_name=? AND {co_clause} AND year=?",
                    (hist[year], factor, company, year))
            else:
                cur.execute(
                    f"UPDATE macro_forecasts SET value=? WHERE factor_name=? AND {co_clause} AND year=?",
                    (hist[year], factor, year))
            n += cur.rowcount
    db.commit()
    print(f"БД обновлено, затронуто строк: {n}")

    # Driver CSV (legacy fallback)
    if CSV_PATH.exists():
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        header = rows[0]
        years = [c for c in header if c.isdigit()]
        for row in rows[1:]:
            if row and row[0] == "lme_al":
                for y in years:
                    yi = int(y)
                    if yi in hist:
                        idx = header.index(y)
                        if idx < len(row):
                            row[idx] = str(hist[yi])
                # прогнозные колонки 2027-2029 = base-путь (SSOT)
                base = {2027: 3050.0, 2028: 2900.0}
                for y, v in base.items():
                    if str(y) in header:
                        idx = header.index(str(y))
                        if idx < len(row):
                            row[idx] = str(v)
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
        print(f"CSV обновлён: {CSV_PATH}")

    # Проверка
    for f_, c_ in FACTORS_DB:
        q = ("SELECT year, value FROM macro_factors WHERE factor_name=? AND company_id IS NULL ORDER BY year DESC LIMIT 3"
             if c_ is None else
             "SELECT year, value FROM macro_factors WHERE factor_name=? AND company_id=? ORDER BY year DESC LIMIT 3")
        args = (f_,) if c_ is None else (f_, c_)
        print(f_, c_ or "global", [tuple(r) for r in cur.execute(q, args)])
    db.close()


if __name__ == "__main__":
    main()
