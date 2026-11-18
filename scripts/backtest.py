#!/usr/bin/env python3
"""
Backtest-пайплайн (AUDIT_ADEQUACY §3.3): формальный бэктест engine.

Прогон окна [END_YEAR+1 .. END_YEAR+span] от истории ≤ END_YEAR:
  1. Копия БД → /tmp/bt_<company>_<end>.db, усечение history/preprocess/macro/forecast > END
     (полная изоляция от look-ahead: препроцессор и макро видят только ≤ END)
  2. build_model(company, backtest_end_year=END, scenario='backtest', sanity=warn)
     — auto-detect базового года отключён (флаг W3)
  3. MAPE прогноз vs факт (факт читается из ОРИГИНАЛЬНОЙ БД)
  4. Отчёт audit/backtest_<company>_<date>.md

Usage:
    python3 scripts/backtest.py --company rusal --end-year 2023
    python3 scripts/backtest.py --company us_steel --end-year 2022 --sanity fail
"""
from __future__ import annotations

import argparse
import datetime
import logging
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.orchestrator import build_model  # noqa: E402

logger = logging.getLogger("backtest")

# Метрики для MAPE: (имя, таблица_истории, ключ_истории, ключ_прогноза)
# Для долга — агрегат STD+LT (ниже спец-обработка).
# EBITDA: факт = ebitda_reported (книжное определение, METRICS_GLOSSARY.md),
# прогноз = engine state.ebitda (та же база) — узкий ключ БД 'ebitda' НЕ использовать.
IS_METRICS = ["revenue", "ebitda", "net_income"]
HIST_KEY = {"revenue": "revenue", "ebitda": "ebitda_reported", "net_income": "net_income"}

# Таблицы с year-колонкой, усечённые до END (look-ahead isolation)
YEAR_TABLES = ["preprocess_metrics", "macro_factors", "macro_forecasts", "debt_schedule"]
# Таблицы истории с period_id (year через periods)
PERIOD_TABLES = ["history_is", "history_bs", "history_cf"]
# Прогнозные таблицы — чистим для компании полностью (чистый лист бэктеста)
FORECAST_TABLES = ["forecast_is", "forecast_bs", "forecast_cf",
                   "stress_results", "covenant_results", "ratings", "rating_history"]


def truncate_copy(src_db: Path, dst_db: Path, company: str, end_year: int) -> None:
    """Копия БД с усечением всех данных > end_year для company."""
    shutil.copy2(src_db, dst_db)
    db = sqlite3.connect(dst_db)
    # periods → year map
    periods = dict(db.execute(
        "SELECT period_id, year FROM periods WHERE company_id=?", (company,)
    ).fetchall())
    future_pids = [pid for pid, yr in periods.items() if yr > end_year]
    for t in PERIOD_TABLES:
        if future_pids:
            ph = ",".join("?" * len(future_pids))
            db.execute(
                f"DELETE FROM {t} WHERE company_id=? AND period_id IN ({ph})",
                (company, *future_pids))
    for t in YEAR_TABLES:
        try:
            db.execute(f"DELETE FROM {t} WHERE company_id=? AND year > ?", (company, end_year))
        except sqlite3.OperationalError:
            pass  # таблица без company_id/year — пропуск
    for t in FORECAST_TABLES:
        try:
            db.execute(f"DELETE FROM {t} WHERE company_id=?", (company,))
        except sqlite3.OperationalError:
            pass
    # periods НЕ трогаем — это календарь; look-ahead изолируется удалением
    # данных (history/preprocess/macro), а saver прогноза нуждается в period_id
    db.commit()
    db.close()


def _scenario_id(db: sqlite3.Connection, company: str, scenario: str) -> int | None:
    row = db.execute(
        "SELECT scenario_id FROM scenarios WHERE company_id=? AND name=?",
        (company, scenario)).fetchone()
    return row[0] if row else None


def _get_metric(db: sqlite3.Connection, table: str, company: str, scenario: str,
                year: int, metric: str) -> float | None:
    """Значение метрики за год (forecast: scenario_id разрешён из имени; history: periods join)."""
    if table.startswith("history"):
        row = db.execute(
            f"""SELECT m.value FROM {table} m
                JOIN periods p ON p.period_id=m.period_id AND p.company_id=m.company_id
                WHERE m.company_id=? AND p.year=? AND m.metric=?""",
            (company, year, metric)).fetchone()
    else:
        sid = _scenario_id(db, company, scenario)
        if sid is None:
            return None
        row = db.execute(
            f"""SELECT m.value FROM {table} m
                JOIN periods p ON p.period_id=m.period_id AND p.company_id=m.company_id
                WHERE m.company_id=? AND p.year=? AND m.metric=? AND m.scenario_id=?""",
            (company, year, metric, sid)).fetchone()
    return row[0] if row else None


def _get_debt(db: sqlite3.Connection, table: str, company: str, scenario: str,
              year: int) -> float | None:
    st = _get_metric(db, table, company, scenario, year, "short_term_debt")
    lt = _get_metric(db, table, company, scenario, year, "long_term_debt")
    td = _get_metric(db, table, company, scenario, year, "total_debt")
    if td is not None:
        return abs(td)
    if st is None and lt is None:
        return None
    return abs(st or 0) + abs(lt or 0)


def run_backtest(company: str, end_year: int, db_path: Path,
                 sanity: str = "warn", scenario: str = "backtest") -> Path:
    span = 3  # RUSAL/Nornickel: 3-летний горизонт (US Steel: 5)
    if company == "us_steel":
        span = 5
    fc_years = list(range(end_year + 1, end_year + span + 1))
    out_path = ROOT / "audit" / f"backtest_{company}_{sanity}_{datetime.date.today()}.md"

    tmp_db = Path(f"/tmp/bt_{company}_{end_year}.db")
    truncate_copy(db_path, tmp_db, company, end_year)
    logger.info(f"Усечённая копия: {tmp_db} (история ≤ {end_year})")

    result = build_model(
        company_id=company,
        db_path=tmp_db,
        scenario_name=scenario,
        run_preprocessor=True,
        run_macro=True,
        run_model=True,
        run_stress=False,
        run_rating=False,
        run_covenants=False,
        sanity_mode=sanity,
        backtest_end_year=end_year,
        log_level=logging.WARNING,
    )

    # Факт — из ОРИГИНАЛЬНОЙ БД (не усечённой)
    orig = sqlite3.connect(db_path)
    fc = sqlite3.connect(tmp_db)

    lines = []
    lines.append(f"# Backtest {company}: прогноз {fc_years[0]}–{fc_years[-1]} от истории ≤ {end_year}")
    lines.append("")
    lines.append(f"Дата: {datetime.date.today()} · Сценарий: `{scenario}` (temp БД) · sanity: {sanity}")
    lines.append("")

    if not result.success:
        lines.append("## Статус: FAIL (прогон прерван)")
        for e in result.errors[:10]:
            lines.append(f"- ✗ {e}")
        for w in result.warnings[:10]:
            lines.append(f"- ⚠ {w}")
        lines.append("")
        lines.append("Sanity bounds отработали как fail-fast гейты adequacy — "
                     "см. AUDIT_ADEQUACY §3.3 (на усечённых данных без bounds раньше "
                     "получали STD=5.6e15 при BS diff=0).")
        out = out_path
        out.write_text("\n".join(lines), encoding="utf-8")
        return out

    lines.append("## MAPE по метрикам (прогноз vs факт МСФО)")
    lines.append("")
    lines.append("| Метрика | " + " | ".join(str(y) for y in fc_years) + " |")
    lines.append("|---|" + "---|" * len(fc_years))
    all_pass = True
    n_computed = 0
    for metric in IS_METRICS:
        cells = []
        for y in fc_years:
            f = _get_metric(fc, "forecast_is", company, scenario, y, metric)
            a = _get_metric(orig, "history_is", company, scenario, y, HIST_KEY[metric])
            if f is None or a in (None, 0):
                cells.append("n/a")
                continue
            n_computed += 1
            mape = abs(f - abs(a)) / abs(a)
            cells.append(f"{mape:.1%}" + (" ❌" if mape > 0.30 else ""))
            if mape > 0.30:
                all_pass = False
        lines.append(f"| {metric} | " + " | ".join(cells) + " |")
    # Долг (BS)
    cells = []
    for y in fc_years:
        f = _get_debt(fc, "forecast_bs", company, scenario, y)
        a = _get_debt(orig, "history_bs", company, scenario, y)
        if f is None or a in (None, 0):
            cells.append("n/a")
            continue
        n_computed += 1
        mape = abs(f - a) / abs(a)
        cells.append(f"{mape:.1%}" + (" ❌" if mape > 0.30 else ""))
        if mape > 0.30:
            all_pass = False
    lines.append(f"| total_debt | " + " | ".join(cells) + " |")
    lines.append("")
    if n_computed == 0:
        lines.append("**Статус**: MAPE не вычислен (прогноз не сохранён или sanity fail-fast)")
    else:
        lines.append(f"**Порог 30%** (по {n_computed} ячейкам): "
                     f"{'все метрики в допуске ✅' if all_pass else 'есть превышения ❌'}")
    lines.append("")
    lines.append("## Абсолютные значения (mln USD)")
    lines.append("")
    lines.append("| Год | Revenue прогн/факт | EBITDA прогн/факт | NI прогн/факт | Debt прогн/факт |")
    lines.append("|---|---|---|---|---|")
    for y in fc_years:
        def pf(f_tbl, h_tbl, m, getter=None, h_key=None):
            f = getter(fc, f_tbl, company, scenario, y) if getter else _get_metric(fc, f_tbl, company, scenario, y, m)
            a = getter(orig, h_tbl, company, scenario, y) if getter else _get_metric(orig, h_tbl, company, scenario, y, h_key or m)
            fmt = lambda v: f"{v:,.0f}" if v is not None else "n/a"
            return f"{fmt(f)} / {fmt(a)}"
        lines.append(f"| {y} | {pf('forecast_is','history_is','revenue')} | {pf('forecast_is','history_is','ebitda',h_key='ebitda_reported')} "
                     f"| {pf('forecast_is','history_is','net_income')} | {pf('forecast_bs','history_bs',None,_get_debt)} |")
    lines.append("")
    if result.warnings:
        lines.append("## Warnings прогона")
        for w in result.warnings[:15]:
            lines.append(f"- ⚠ {w}")
        lines.append("")
    orig.close()
    fc.close()

    out = out_path
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main():
    ap = argparse.ArgumentParser(description="Backtest: прогноз от истории ≤ END_YEAR")
    ap.add_argument("--company", required=True, choices=["rusal", "us_steel", "nornickel"])
    ap.add_argument("--end-year", type=int, required=True, help="Последний год истории (базовый)")
    ap.add_argument("--db", default=str(ROOT / "data_mart_v2.db"))
    ap.add_argument("--sanity", choices=["fail", "warn"], default="warn",
                    help="fail-fast гейты (warn позволяет докрутить и увидеть MAPE)")
    ap.add_argument("--scenario", default="backtest")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"✗ БД не найдена: {db_path}")
        sys.exit(1)
    # Валидация полноты входов: история ≥ 5 лет до END
    db = sqlite3.connect(db_path)
    n_hist = db.execute(
        """SELECT COUNT(DISTINCT p.year) FROM history_is m
           JOIN periods p ON p.period_id=m.period_id AND p.company_id=m.company_id
           WHERE m.company_id=? AND p.year<=?""",
        (args.company, args.end_year)).fetchone()[0]
    db.close()
    if n_hist < 5:
        print(f"✗ История до {args.end_year} всего {n_hist} лет (< 5) — backtest недостоверен")
        sys.exit(2)
    print(f"История ≤ {args.end_year}: {n_hist} лет ✓")

    out = run_backtest(args.company, args.end_year, db_path, args.sanity, args.scenario)
    print(f"\nОтчёт: {out}")


if __name__ == "__main__":
    main()
