#!/usr/bin/env python3
"""Гейт синхронизации Excel-модели (excel_v4) ↔ Python engine (stressTest_v2).

Банковский принцип «два движка — схожие результаты» (bank_model/scripts/sync_gate.py),
перенесённый на корпоративные модели. Живой пересчёт Excel не требуется: читаем
кэш Model_Output (книга обязана быть свежей — finalize.py делает recalc).

ВАЖНО про допуски. Движки считают РАЗНЫЕ макровходы:
  Excel  — фиксированные сценарии 01_Macro (Base: LME Al 2800);
  engine — VECM/ECM-прогноз macro (своя траектория LME).
Поэтому гейт сравнивает:
  1) СТРУКТУРУ (input-insensitive): COGS%, EBITDA margin, Net margin — жёсткий

Определения метрик: docs/METRICS_GLOSSARY.md (EBITDA книги = ebitda_reported,
узкий ключ БД 'ebitda' не использовать для сверки).
     допуск (по умолчанию ±3 п.п.) — несовпадение = дефект маппинга/калибровки;
  2) УРОВНИ (Rev/EBITDA/NI) — мягкий допуск (по умолчанию ±20%) — несовпадение
     отражает разницу макро; FAIL только совместно со структурным.

Использование:
  python3 scripts/sync_gate_corp.py --company rusal --book model/rusal_v4.xlsx
  python3 scripts/sync_gate_corp.py --company rusal --book model/rusal_v4.xlsx \
      --tol-struct 0.03 --tol-level 0.20

Exit code: 0 = PASS, 1 = FAIL, 2 = engine недоступен (нет данных компании в БД).
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import openpyxl

# ── Model_Output layout (rows pinned in build_model.py; reg.json не содержит MO.* —
#    зафиксировано здесь как единственное место сверки) ──
MO_ROWS = {
    "revenue": 7,
    "cogs": 8,
    "ebitda": 10,
    "net_income": 12,
}
MO_FIRST_FC_COL = 6  # F = 2026E (C:E = hist 2023-2025)


def read_excel_outputs(book: Path, fc_years: list[int]) -> dict[int, dict[str, float]]:
    wb = openpyxl.load_workbook(str(book), data_only=True, read_only=True)
    ws = wb["Model_Output"]
    out: dict[int, dict[str, float]] = {}
    for i, yr in enumerate(fc_years):
        c = MO_FIRST_FC_COL + i
        row = {}
        for key, r in MO_ROWS.items():
            v = ws.cell(row=r, column=c).value
            row[key] = float(v) if isinstance(v, (int, float)) else None
        out[yr] = row
    wb.close()
    return out


def read_engine_outputs(company: str, fc_years: list[int]) -> dict[int, dict[str, float]]:
    from engine.orchestrator import build_model  # тяжёлый импорт — после argparse

    res = build_model(company, run_preprocessor=False, run_model=True,
                      run_stress=False, run_rating=False, run_covenants=False)
    out: dict[int, dict[str, float]] = {}
    for yr in fc_years:
        f = res.model_result.to_flat(yr)
        out[yr] = {k: (f.get(k) / 1e6 if isinstance(f.get(k), (int, float)) else None)
                   for k in ("revenue", "cogs", "sga", "ebitda", "net_income")}
    return out


def margins(d: dict[str, float]) -> dict[str, float]:
    rev = d.get("revenue") or 0.0
    if not rev:
        return {"cogs_pct": None, "ebitda_margin": None, "net_margin": None}
    return {
        "cogs_pct": abs(d.get("cogs") or 0.0) / rev,
        "ebitda_margin": (d.get("ebitda") or 0.0) / rev,
        "net_margin": (d.get("net_income") or 0.0) / rev,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", required=True)
    ap.add_argument("--book", required=True, help="путь к xlsx excel_v4")
    ap.add_argument("--tol-struct", type=float, default=0.03, help="допуск структуры, доля (0.03 = 3 п.п.)")
    ap.add_argument("--tol-level", type=float, default=0.20, help="допуск уровней, доля")
    a = ap.parse_args()

    logging.disable(logging.CRITICAL)
    book = Path(a.book)
    if not book.exists():
        print(f"BOOK NOT FOUND: {book}")
        return 2

    fc_years = [2026, 2027, 2028]

    xl = read_excel_outputs(book, fc_years)
    try:
        eng = read_engine_outputs(a.company, fc_years)
    except Exception as e:  # нет компании в локальной БД (Nornickel живёт в Vertex PG)
        print(f"ENGINE UNAVAILABLE ({a.company}): {e}")
        return 2

    fails: list[str] = []
    print(f"SYNC GATE: {a.company} | Excel={book.name} vs Python engine")
    print(f"{'метрика':<16}{'год':<6}{'Excel':>12}{'engine':>12}{'Δ':>10}  вердикт")
    print("-" * 62)

    def line(name: str, yr: int, vx: float, ve: float, tol: float, hard: bool,
             relative: bool = False) -> None:
        nonlocal fails

        def fmt(v):
            return f"{v:>12.4f}" if isinstance(v, float) and abs(v) < 10 else f"{v:>12.0f}"

        if vx is None or ve is None or not vx:
            print(f"{name:<16}{yr:<6}{vx!s:>12}{ve!s:>12}{'—':>10}  SKIP")
            return
        diff_abs = abs(ve - vx)
        # P1 (19.11): уровни (mln) сравниваются ОТНОСИТЕЛЬНО доле от книги;
        # структура (доли) — абсолютно в п.п. Было: abs(mln) <= 0.2 → всегда FAIL.
        diff = diff_abs / max(abs(vx), 1e-9) if relative else diff_abs
        ok = diff <= tol
        tag = "ok" if ok else ("FAIL" if hard else "info")
        if not ok and hard:
            fails.append(f"{name} {yr}: Δ={diff:.4f} (> {tol}) abs={diff_abs:,.0f}")
        d_show = f"{diff_abs:,.0f}" if relative else f"{diff:.4f}"
        print(f"{name:<16}{yr:<6}{fmt(vx)}{fmt(ve)}{d_show:>10}  {tag}")

    for yr in fc_years:
        m_x, m_e = margins(xl[yr]), margins(eng[yr])
        for key, label in (("cogs_pct", "COGS%"), ("ebitda_margin", "EBITDA%"), ("net_margin", "Net%")):
            line(label, yr, m_x[key], m_e[key], a.tol_struct, hard=True)

    level_struct_bad = bool(fails)
    for yr in fc_years:
        for key, label in (("revenue", "Revenue"), ("ebitda", "EBITDA"), ("net_income", "NI")):
            line(label, yr, xl[yr][key], eng[yr][key], a.tol_level, hard=level_struct_bad,
                 relative=True)

    print("-" * 62)
    if fails:
        print(f"FAIL ({len(fails)}):")
        for f_ in fails:
            print(f"  ✗ {f_}")
        return 1
    print("PASS — структура P&L движков совпадает в допуске")
    return 0


if __name__ == "__main__":
    sys.exit(main())
