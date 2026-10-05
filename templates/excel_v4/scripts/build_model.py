#!/usr/bin/env python3
"""
Build Corporate Financial Model v4 — Excel-driven template.

Generates a complete 30-sheet Excel workbook with formulas.
Mirror of bank_model/scripts/build_all.py but for corporates.

Usage:
    python scripts/build_model.py --company rusal --output model/rusal_v4.xlsx
    python scripts/build_model.py --company nornickel --output model/nornickel_v4.xlsx
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

import openpyxl
from openpyxl.utils import get_column_letter

# Add parent to path for styles import
sys.path.insert(0, str(Path(__file__).resolve().parent))
from styles import *

# ── Constants ────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent
REG = json.loads((BASE_DIR / "reg.json").read_text(encoding="utf-8"))

# Sheet names and codes
SHEETS = [
    # (code, sheet_name, tab_color)
    ("GU", "00_Guide",       TAB_NAV),
    ("CV", "00_Cover",       TAB_NAV),
    ("CP", "Control_Panel",  TAB_INPUT),
    ("MA", "01_Macro",       TAB_INPUT),
    ("HI", "02_Hist",        TAB_INPUT),
    ("AS", "03_Assump",      TAB_INPUT),
    ("RI", "Raw_IFRS",       TAB_INPUT),
    ("RV", "10_Revenue",     TAB_ENGINE),
    ("SG", "11_Segments",    TAB_ENGINE),
    ("CG", "12_COGS",        TAB_ENGINE),
    ("SA", "13_SGA",         TAB_ENGINE),
    ("OI", "14_OtherIS",     TAB_ENGINE),
    ("PP", "15_PPE",         TAB_ENGINE),
    ("WC", "16_WC",          TAB_ENGINE),
    ("DT", "17_Debt",        TAB_ENGINE),
    ("LS", "18_Lease",       TAB_ENGINE),
    ("TX", "19_Tax",         TAB_ENGINE),
    ("BS", "20_BS",          TAB_ENGINE),
    ("PL", "21_PL",          TAB_ENGINE),
    ("CF", "23_CF",          TAB_ENGINE),
    ("EQ", "24_Equity",      TAB_ENGINE),
    ("RA", "30_Ratios",      TAB_REPORT),
    ("SC", "31_Score",       TAB_REPORT),
    ("CO", "32_Covenants",   TAB_REPORT),
    ("RS", "33_RevStress",   TAB_REPORT),
    ("VL", "35_Valuation",   TAB_REPORT),
    ("SN", "40_Scen",        TAB_REPORT),
    ("CK", "90_Checks",      TAB_CTRL),
    ("MO", "Model_Output",   TAB_CTRL),
    ("CL", "Changelog",      TAB_CTRL),
]

# Code → sheet name lookup
NAME = {code: name for code, name, _ in SHEETS}


def ref(code: str, key: str, col: str = "$C") -> str:
    """Build cross-sheet reference formula: ='sheet'!$C$row."""
    row = REG.get(f"{code}.{key}")
    if row is None:
        return f"#REF!_{code}.{key}"
    sheet = NAME.get(code, code)
    return f"'{sheet}'!{col}${row}"


def ref_col(code: str, key: str, col_idx: int) -> str:
    """Build reference with dynamic column index."""
    row = REG.get(f"{code}.{key}")
    if row is None:
        return f"#REF!_{code}.{key}"
    sheet = NAME.get(code, code)
    col_letter = get_column_letter(col_idx)
    return f"'{sheet}'!{col_letter}${row}"


# ── Company configs ──────────────────────────────────────────────────────────

COMPANY_CONFIGS = {
    "rusal": {
        "name": "UC RUSAL",
        "industry": "metals",
        "currency": "USD",
        "hist_years": [2021, 2022, 2023, 2024, 2025],
        "fc_years": [2026, 2027, 2028],
        "segments": [
            {"name": "Primary Aluminium", "key": "seg1", "driver": "LME Aluminium",
             "max_capacity_kt": 4100},
            {"name": "Alumina", "key": "seg2", "driver": "LME Alumina"},
            {"name": "Other (VAP, foil)", "key": "seg3", "driver": "EWA"},
        ],
        "macro_factors": ["LME Aluminium", "LME Alumina", "USD/RUB", "Brent", "CPI RU", "PPI RU"],
        "cogs_mode": "component",
        "cogs_components": {"material": 0.37, "energy": 0.27, "labour": 0.12, "other": 0.24},
        "debt_target_nd_ebitda": 3.5,
        "rating_ind_adj": -6.0,
        "rating_size_adj": 2.0,
        "rating_cycle_margin": 0.12,
        "covenants": {"nd_ebitda_max": 4.5, "icr_min": 1.5, "margin_min": 0.05},
    },
    "nornickel": {
        "name": "PJSC MMC Norilsk Nickel",
        "industry": "metals",
        "currency": "USD",
        "hist_years": [2021, 2022, 2023, 2024, 2025],
        "fc_years": [2026, 2027, 2028],
        "segments": [
            {"name": "Nickel", "key": "seg1", "driver": "LME Nickel"},
            {"name": "Copper", "key": "seg2", "driver": "LME Copper"},
            {"name": "PGM (Pd+Pt)", "key": "seg3", "driver": "LME Palladium"},
        ],
        "macro_factors": ["LME Nickel", "LME Copper", "LME Palladium", "LME Platinum",
                          "USD/RUB", "Brent", "GDP World"],
        "cogs_mode": "ratio",
        "cogs_ratio_default": 0.59,
        "debt_target_nd_ebitda": 1.5,
        "rating_ind_adj": -6.0,
        "rating_size_adj": 2.0,
        "rating_cycle_margin": 0.41,
        "covenants": {"nd_ebitda_max": 3.0, "icr_min": 3.0, "margin_min": 0.15},
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# SHEET BUILDERS
# ══════════════════════════════════════════════════════════════════════════════

def build_cover(wb, cfg):
    """00_Cover — company info + scenario selector."""
    ws = wb["00_Cover"]
    apply_col_widths(ws)

    ws.cell(1, 1, f"ФИНАНСОВАЯ МОДЕЛЬ — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "Corporate Financial Model v4 · stressTest_v2 · Excel-driven").font = F_SUBTITLE

    r = 3
    for label, key, val, fmt in [
        ("Компания", "company", cfg["name"], FMT_TEXT),
        ("Отрасль", "industry", cfg["industry"], FMT_TEXT),
        ("Аналитик", "analyst", "—", FMT_TEXT),
        ("Дата модели", "date", "2025-12-31", FMT_TEXT),
        ("Валюта", "currency", cfg["currency"], FMT_TEXT),
        ("Активный сценарий (1-N)", "scenario", 1, FMT_INT),
    ]:
        row = REG.get(f"CV.{key}", r)
        label_row(ws, row, label)
        input_cell(ws, row, 3, val, fmt)
        r = row + 2


def build_macro(wb, cfg):
    """01_Macro — macro scenarios + econometric equations."""
    ws = wb["01_Macro"]
    apply_col_widths(ws)

    ws.cell(1, 1, f"01_Macro — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "Макросценарии и эконометрические уравнения").font = F_SUBTITLE

    year_headers(ws, 4, cfg["hist_years"][-3:], cfg["fc_years"])

    # Section A: Scenario 1 (Base)
    section_header(ws, 6, "A. Сценарий 1: Базовый")
    for i, factor in enumerate(cfg["macro_factors"]):
        r = 8 + i
        label_row(ws, r, factor)
        # Forecast columns — yellow input
        for c in range(3 + len(cfg["hist_years"][-3:]), 3 + len(cfg["hist_years"][-3:]) + len(cfg["fc_years"])):
            input_cell(ws, r, c, 0, FMT_RATIO1)

    # Section B: Active scenario (CHOOSE)
    gap = len(cfg["macro_factors"]) + 4
    section_header(ws, 6 + gap, "Активный сценарий (CHOOSE)")
    ws.cell(6 + gap + 1, 1, "Определяется по номеру из 00_Cover").font = F_NOTE

    # Section C: Econometric display
    section_header(ws, 6 + 2 * gap, "C. Эконометрика: Revenue ~ β × Δln(Factor)")
    for i, label in enumerate(["β (эластичность)", "R² (коэфф. детерминации)", "α (константа)"]):
        r = 6 + 2 * gap + 2 + i
        label_row(ws, r, label)


def build_hist(wb, cfg):
    """02_Hist — historical IS/BS/CF."""
    ws = wb["02_Hist"]
    apply_col_widths(ws)

    ws.cell(1, 1, f"02_Hist — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "Историческая отчётность (МСФО)").font = F_SUBTITLE

    year_headers(ws, 4, cfg["hist_years"], [])

    # IS section
    section_header(ws, 6, "ОТЧЁТ О ПРИБЫЛЯХ И УБЫТКАХ (IS)")
    is_rows = [
        ("revenue", "Выручка", "mln"),
        ("cogs", "Себестоимость", "mln"),
        ("gp", "Валовая прибыль", "mln"),
        ("sga", "SGA", "mln"),
        ("da", "D&A", "mln"),
        ("ebitda", "EBITDA", "mln"),
        ("ebit", "EBIT", "mln"),
        ("interest", "Процентные расходы", "mln"),
        ("other_fin", "Прочие фин. расходы", "mln"),
        ("ebt", "Прибыль до налога", "mln"),
        ("tax", "Налог на прибыль", "mln"),
        ("ni", "Чистая прибыль", "mln"),
    ]
    for key, label, unit in is_rows:
        r = REG.get(f"HI.{key}", 7)
        label_row(ws, r, label, unit)
        for c in range(3, 3 + len(cfg["hist_years"])):
            input_cell(ws, r, c, 0, FMT_MLN)

    # BS section
    r_bs = REG.get("HI.ta", 22)
    section_header(ws, r_bs - 1, "БАЛАНС (BS)")
    bs_rows = [
        ("ta", "Итого активы", "mln"),
        ("cash", "Денежные средства", "mln"),
        ("ar", "Дебиторская задолженность", "mln"),
        ("inv", "Запасы", "mln"),
        ("ppe_net", "Основные средства (нетто)", "mln"),
        ("ppe_gross", "ОС (валовая стоимость)", "mln"),
        ("accdep", "Накопленная амортизация", "mln"),
        ("goodwill", "Гудвилл", "mln"),
        ("intang", "Нематериальные активы", "mln"),
        ("rou", "Активы ПИ (ROU)", "mln"),
        ("dta", "Отложенный налоговый актив", "mln"),
        ("ap", "Кредиторская задолженность", "mln"),
        ("st_debt", "Краткосрочный долг", "mln"),
        ("lt_debt", "Долгосрочный долг", "mln"),
        ("lease_cl", "Обяз. по аренде (кратк.)", "mln"),
        ("lease_ncl", "Обяз. по аренде (долг.)", "mln"),
        ("prov", "Резервы", "mln"),
        ("dtl", "Отложенное нал. обяз.", "mln"),
        ("tl", "Итого обязательства", "mln"),
        ("equity", "Собственный капитал", "mln"),
        ("re", "Нераспр. прибыль", "mln"),
    ]
    for key, label, unit in bs_rows:
        r = REG.get(f"HI.{key}", r_bs)
        label_row(ws, r, label, unit)
        for c in range(3, 3 + len(cfg["hist_years"])):
            input_cell(ws, r, c, 0, FMT_MLN)

    # CF section
    r_cf = REG.get("HI.cfo", 54)
    section_header(ws, r_cf - 1, "ДЕНЕЖНЫЕ ПОТОКИ (CF)")
    cf_rows = [
        ("cfo", "Операционный CF", "mln"),
        ("cfi", "Инвестиционный CF", "mln"),
        ("cff", "Финансовый CF", "mln"),
        ("net_change", "Чистое изменение ДС", "mln"),
        ("capex", "Капитальные затраты", "mln"),
    ]
    for key, label, unit in cf_rows:
        r = REG.get(f"HI.{key}", r_cf)
        label_row(ws, r, label, unit)
        for c in range(3, 3 + len(cfg["hist_years"])):
            input_cell(ws, r, c, 0, FMT_MLN)


def build_revenue(wb, cfg):
    """10_Revenue — segment-level revenue = Σ(Vol × Price)."""
    ws = wb["10_Revenue"]
    apply_col_widths(ws)

    ws.cell(1, 1, f"10_Revenue — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "Revenue = Σ (Volume × Price) по сегментам").font = F_SUBTITLE

    year_headers(ws, 4, cfg["hist_years"][-3:], cfg["fc_years"])

    section_header(ws, 6, "СЕГМЕНТНАЯ ВЫРУЧКА")

    for seg in cfg["segments"]:
        key = seg["key"]
        base_r = REG.get(f"RV.{key}_vol", 8)
        subsection_header(ws, base_r - 1, f"{seg['name']} (driver: {seg['driver']})")

        label_row(ws, base_r, "Объём продаж", "kt")
        label_row(ws, base_r + 1, "Средняя цена реализации", "$/t")
        label_row(ws, base_r + 2, "Выручка сегмента", "mln")

        # History: input
        n_hist = len(cfg["hist_years"][-3:])
        for c in range(3, 3 + n_hist):
            input_cell(ws, base_r, c, 0, FMT_INT)      # volume
            input_cell(ws, base_r + 1, c, 0, FMT_INT)   # price
            # revenue = vol × price / 1e6 (kt × $/t → $mln)
            col_l = get_column_letter(c)
            formula_cell(ws, base_r + 2, c,
                         f"={col_l}{base_r}*{col_l}{base_r+1}/1000", FMT_MLN, bold=True)

        # Forecast: formulas (volume=EWA, price=macro or input)
        for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
            input_cell(ws, base_r, c, 0, FMT_INT)      # volume forecast (input or EWA)
            input_cell(ws, base_r + 1, c, 0, FMT_INT)   # price forecast (macro or input)
            col_l = get_column_letter(c)
            formula_cell(ws, base_r + 2, c,
                         f"={col_l}{base_r}*{col_l}{base_r+1}/1000", FMT_MLN, bold=True)

    # Total revenue
    r_total = REG.get("RV.total_rev", 20)
    label_row(ws, r_total, "ИТОГО ВЫРУЧКА", "mln")
    ws.cell(r_total, 1).font = F_LABEL_B
    n_total = len(cfg["hist_years"][-3:]) + len(cfg["fc_years"])
    for c in range(3, 3 + n_total):
        col_l = get_column_letter(c)
        parts = []
        for seg in cfg["segments"]:
            rev_r = REG.get(f"RV.{seg['key']}_rev", 10)
            parts.append(f"{col_l}{rev_r}")
        formula_cell(ws, r_total, c, "=" + "+".join(parts), FMT_MLN, bold=True)

    # Revenue growth
    r_growth = REG.get("RV.rev_growth", 21)
    label_row(ws, r_growth, "Рост выручки", "%")
    for c in range(4, 3 + n_total):
        col_l = get_column_letter(c)
        prev_col = get_column_letter(c - 1)
        formula_cell(ws, r_growth, c,
                     f"=IF({prev_col}{r_total}<>0,{col_l}{r_total}/{prev_col}{r_total}-1,0)",
                     FMT_PCT)


def build_ppe(wb, cfg):
    """15_PPE — PP&E corkscrew: gross → capex → disp → dep → net."""
    ws = wb["15_PPE"]
    apply_col_widths(ws)

    ws.cell(1, 1, f"15_PPE — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "PP&E Corkscrew: Gross → CapEx → Disposals → Dep → Net").font = F_SUBTITLE

    year_headers(ws, 4, cfg["hist_years"][-1:], cfg["fc_years"])

    section_header(ws, 6, "PP&E GROSS")
    labels = [
        ("gross_open", "Начало периода (gross)", "mln"),
        ("capex", "Капитальные затраты", "mln"),
        ("disp_gross", "Выбытие (gross)", "mln"),
        ("gross_close", "Конец периода (gross)", "mln"),
    ]
    for key, label, unit in labels:
        r = REG.get(f"PP.{key}")
        label_row(ws, r, label, unit)

    section_header(ws, 11, "НАКОПЛЕННАЯ АМОРТИЗАЦИЯ")
    dep_labels = [
        ("dep_open", "Начало периода", "mln"),
        ("dep_charge", "Амортизация за год", "mln"),
        ("dep_disp", "Выбытие (аморт.)", "mln"),
        ("dep_close", "Конец периода", "mln"),
    ]
    for key, label, unit in dep_labels:
        r = REG.get(f"PP.{key}")
        label_row(ws, r, label, unit)

    section_header(ws, 16, "PP&E NET")
    label_row(ws, REG["PP.net_open"], "ОС нетто, начало", "mln")
    label_row(ws, REG["PP.net_close"], "ОС нетто, конец", "mln")

    # Formulas for forecast columns
    n_hist = 1  # only last hist year for opening balance
    for c_idx in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c_idx)
        prev = get_column_letter(c_idx - 1)

        # Gross: open = prev close
        formula_cell(ws, REG["PP.gross_open"], c_idx, f"={prev}{REG['PP.gross_close']}", FMT_MLN)
        # Gross close = open + capex - disposals
        formula_cell(ws, REG["PP.gross_close"], c_idx,
                     f"={cl}{REG['PP.gross_open']}+{cl}{REG['PP.capex']}-{cl}{REG['PP.disp_gross']}",
                     FMT_MLN, bold=True)

        # Dep: open = prev close
        formula_cell(ws, REG["PP.dep_open"], c_idx, f"={prev}{REG['PP.dep_close']}", FMT_MLN)
        # Dep charge = net_open × DA_rate (from Control_Panel)
        formula_cell(ws, REG["PP.dep_charge"], c_idx,
                     f"={cl}{REG['PP.net_open']}*{ref('CP', 'da_rate', '$C')}",
                     FMT_MLN)
        # Dep close = open + charge - disposals dep
        formula_cell(ws, REG["PP.dep_close"], c_idx,
                     f"={cl}{REG['PP.dep_open']}+{cl}{REG['PP.dep_charge']}-{cl}{REG['PP.dep_disp']}",
                     FMT_MLN)

        # Net: open = prev net close
        formula_cell(ws, REG["PP.net_open"], c_idx, f"={prev}{REG['PP.net_close']}", FMT_MLN)
        # Net close = gross close - dep close
        formula_cell(ws, REG["PP.net_close"], c_idx,
                     f"={cl}{REG['PP.gross_close']}-{cl}{REG['PP.dep_close']}",
                     FMT_MLN, bold=True)


def build_bs(wb, cfg):
    """20_BS — Balance Sheet with formula links to corkscrews."""
    ws = wb["20_BS"]
    apply_col_widths(ws)

    ws.cell(1, 1, f"20_BS — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "Баланс: Активы = Обязательства + Капитал").font = F_SUBTITLE

    year_headers(ws, 4, cfg["hist_years"][-1:], cfg["fc_years"])

    section_header(ws, 6, "АКТИВЫ")
    assets = [
        ("cash", "Денежные средства", "mln", "CF", "cash_close"),
        ("ar", "Дебиторская задолженность", "mln", "WC", "ar"),
        ("inv", "Запасы", "mln", "WC", "inv"),
        ("other_ca", "Прочие оборотные активы", "mln", None, None),
    ]

    for key, label, unit, src_code, src_key in assets:
        r = REG[f"BS.{key}"]
        label_row(ws, r, label, unit)

    # Total CA
    r_tca = REG["BS.tca"]
    label_row(ws, r_tca, "Итого оборотные активы", "mln")
    ws.cell(r_tca, 1).font = F_LABEL_B

    section_header(ws, REG["BS.ppe"] - 1, "ВНЕОБОРОТНЫЕ АКТИВЫ")
    nca = [
        ("ppe", "Основные средства", "mln", "PP", "net_close"),
        ("rou", "Активы ПИ (ROU)", "mln", "LS", "rou_close"),
        ("goodwill", "Гудвилл", "mln", None, None),
        ("intang", "Нематериальные активы", "mln", None, None),
        ("dta", "Отложенный нал. актив", "mln", "TX", "dta_close"),
        ("other_nca", "Прочие внеоборотные", "mln", None, None),
    ]
    for key, label, unit, src_code, src_key in nca:
        r = REG[f"BS.{key}"]
        label_row(ws, r, label, unit)

    r_tnca = REG["BS.tnca"]
    label_row(ws, r_tnca, "Итого внеоборотные активы", "mln")

    r_ta = REG["BS.ta"]
    label_row(ws, r_ta, "ИТОГО АКТИВЫ", "mln")
    ws.cell(r_ta, 1).font = F_LABEL_B

    section_header(ws, REG["BS.ap"] - 1, "ОБЯЗАТЕЛЬСТВА")
    liab = [
        ("ap", "Кредиторская задолженность", "mln", "WC", "ap"),
        ("st_debt", "Краткосрочный долг", "mln", "DT", "st"),
        ("lease_cl", "Аренда (кратк.)", "mln", "LS", "liab_close"),
        ("tax_pay", "Налоги к уплате", "mln", "TX", "current"),
        ("other_cl", "Прочие кратк. обяз.", "mln", None, None),
    ]
    for key, label, unit, src_code, src_key in liab:
        r = REG[f"BS.{key}"]
        label_row(ws, r, label, unit)

    r_tcl = REG["BS.tcl"]
    label_row(ws, r_tcl, "Итого краткосрочные обязательства", "mln")

    ncl = [
        ("lt_debt", "Долгосрочный долг", "mln", "DT", "lt"),
        ("lease_ncl", "Аренда (долг.)", "mln", None, None),
        ("prov", "Резервы", "mln", None, None),
        ("dtl", "Отложенное нал. обяз.", "mln", "TX", "dtl_close"),
        ("other_ncl", "Прочие долг. обяз.", "mln", None, None),
    ]
    for key, label, unit, src_code, src_key in ncl:
        r = REG[f"BS.{key}"]
        label_row(ws, r, label, unit)

    r_tncl = REG["BS.tncl"]
    label_row(ws, r_tncl, "Итого долгосрочные обязательства", "mln")
    r_tl = REG["BS.tl"]
    label_row(ws, r_tl, "ИТОГО ОБЯЗАТЕЛЬСТВА", "mln")

    section_header(ws, REG["BS.sc"] - 1, "СОБСТВЕННЫЙ КАПИТАЛ")
    eq = [
        ("sc", "Уставный капитал", "mln"),
        ("apic", "Добавочный капитал", "mln"),
        ("re", "Нераспределённая прибыль", "mln"),
        ("aoci", "Прочий совокупный доход", "mln"),
    ]
    for key, label, unit in eq:
        r = REG[f"BS.{key}"]
        label_row(ws, r, label, unit)

    r_te = REG["BS.te"]
    label_row(ws, r_te, "ИТОГО КАПИТАЛ", "mln")
    r_tlpe = REG["BS.tlpe"]
    label_row(ws, r_tlpe, "Итого обяз. + капитал", "mln")
    r_check = REG["BS.check"]
    label_row(ws, r_check, "Контроль: А − О − К", "mln", "Должно быть = 0")

    # Formulas for totals (all forecast columns)
    n_hist = 1
    for c_idx in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c_idx)

        # TCA = sum of CA items
        ca_keys = ["cash", "ar", "inv", "other_ca"]
        formula_cell(ws, r_tca, c_idx,
                     "=" + "+".join(f"{cl}{REG[f'BS.{k}']}" for k in ca_keys),
                     FMT_MLN, bold=True)

        # TNCA = sum of NCA items
        nca_keys = ["ppe", "rou", "goodwill", "intang", "dta", "other_nca"]
        formula_cell(ws, r_tnca, c_idx,
                     "=" + "+".join(f"{cl}{REG[f'BS.{k}']}" for k in nca_keys),
                     FMT_MLN, bold=True)

        # TA = TCA + TNCA
        formula_cell(ws, r_ta, c_idx,
                     f"={cl}{r_tca}+{cl}{r_tnca}", FMT_MLN, bold=True)

        # TCL = sum of CL items
        cl_keys = ["ap", "st_debt", "lease_cl", "tax_pay", "other_cl"]
        formula_cell(ws, r_tcl, c_idx,
                     "=" + "+".join(f"{cl}{REG[f'BS.{k}']}" for k in cl_keys),
                     FMT_MLN, bold=True)

        # TNCL = sum of NCL items
        ncl_keys = ["lt_debt", "lease_ncl", "prov", "dtl", "other_ncl"]
        formula_cell(ws, r_tncl, c_idx,
                     "=" + "+".join(f"{cl}{REG[f'BS.{k}']}" for k in ncl_keys),
                     FMT_MLN, bold=True)

        # TL = TCL + TNCL
        formula_cell(ws, r_tl, c_idx,
                     f"={cl}{r_tcl}+{cl}{r_tncl}", FMT_MLN, bold=True)

        # TE = sum of equity items
        eq_keys = ["sc", "apic", "re", "aoci"]
        formula_cell(ws, r_te, c_idx,
                     "=" + "+".join(f"{cl}{REG[f'BS.{k}']}" for k in eq_keys),
                     FMT_MLN, bold=True)

        # TL+E
        formula_cell(ws, r_tlpe, c_idx,
                     f"={cl}{r_tl}+{cl}{r_te}", FMT_MLN, bold=True)

        # Check: TA - TL - TE = 0
        formula_cell(ws, r_check, c_idx,
                     f"={cl}{r_ta}-{cl}{r_tl}-{cl}{r_te}", FMT_RATIO)

        # ── Cross-sheet links: BS items ← corkscrews ──
        # Cash ← CF cash_close
        ref_cell(ws, REG["BS.cash"], c_idx,
                 f"='{NAME['CF']}'!{cl}${REG['CF.cash_close']}", FMT_MLN)
        # AR ← WC
        ref_cell(ws, REG["BS.ar"], c_idx,
                 f"='{NAME['WC']}'!{cl}${REG['WC.ar']}", FMT_MLN)
        # Inventory ← WC
        ref_cell(ws, REG["BS.inv"], c_idx,
                 f"='{NAME['WC']}'!{cl}${REG['WC.inv']}", FMT_MLN)
        # PPE ← PP&E net_close
        ref_cell(ws, REG["BS.ppe"], c_idx,
                 f"='{NAME['PP']}'!{cl}${REG['PP.net_close']}", FMT_MLN)
        # AP ← WC (negative)
        ref_cell(ws, REG["BS.ap"], c_idx,
                 f"=ABS('{NAME['WC']}'!{cl}${REG['WC.ap']})", FMT_MLN)
        # ST debt ← Debt
        ref_cell(ws, REG["BS.st_debt"], c_idx,
                 f"='{NAME['DT']}'!{cl}${REG['DT.st']}", FMT_MLN)
        # LT debt ← Debt
        ref_cell(ws, REG["BS.lt_debt"], c_idx,
                 f"='{NAME['DT']}'!{cl}${REG['DT.lt']}", FMT_MLN)
        # DTA ← Tax
        ref_cell(ws, REG["BS.dta"], c_idx,
                 f"='{NAME['TX']}'!{cl}${REG['TX.dta_close']}", FMT_MLN)
        # DTL ← Tax
        ref_cell(ws, REG["BS.dtl"], c_idx,
                 f"='{NAME['TX']}'!{cl}${REG['TX.dtl_close']}", FMT_MLN)
        # Retained earnings ← Equity corkscrew
        ref_cell(ws, REG["BS.re"], c_idx,
                 f"='{NAME['EQ']}'!{cl}${REG['EQ.re_close']}", FMT_MLN)

    # Static items (prev year value carried forward)
    for c_idx in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c_idx)
        prev = get_column_letter(c_idx - 1)
        for key in ["other_ca", "goodwill", "intang", "other_nca",
                     "tax_pay", "other_cl", "lease_ncl", "prov",
                     "other_ncl", "sc", "apic", "aoci"]:
            formula_cell(ws, REG[f"BS.{key}"], c_idx, f"={prev}{REG[f'BS.{key}']}", FMT_MLN)


def build_pl(wb, cfg):
    """21_PL — Income Statement with formula references."""
    ws = wb["21_PL"]
    apply_col_widths(ws)

    ws.cell(1, 1, f"21_PL — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "Отчёт о прибылях и убытках").font = F_SUBTITLE

    year_headers(ws, 4, cfg["hist_years"][-1:], cfg["fc_years"])

    section_header(ws, 6, "ДОХОДЫ И РАСХОДЫ")
    pl_items = [
        ("revenue", "Выручка", "mln", "RV", "total_rev"),
        ("cogs", "Себестоимость", "mln", "CG", "total"),
        ("gp", "Валовая прибыль", "mln", None, None),  # = revenue + cogs
        ("sga", "SGA", "mln", "SA", "sga_total"),
        ("other_opex", "Прочие опер. расходы", "mln", "OI", "other_opex"),
        ("ebitda", "EBITDA", "mln", None, None),  # = GP + SGA + other
        ("da", "D&A", "mln", "PP", "dep_charge"),
        ("impairment", "Обесценение", "mln", "OI", "impairment"),
        ("ebit", "EBIT", "mln", None, None),  # = EBITDA - DA - impairment
        ("interest", "Процентные расходы", "mln", "DT", "interest"),
        ("interest_income", "Процентные доходы", "mln", "OI", "interest_income"),
        ("other_fin", "Прочие фин.", "mln", "OI", "other_fin"),
        ("associates", "Доля в ассоциированных", "mln", "OI", "associates"),
        ("ebt", "Прибыль до налога", "mln", None, None),
        ("tax", "Налог на прибыль", "mln", "TX", "total"),
        ("ni", "Чистая прибыль", "mln", None, None),
    ]

    for key, label, unit, src_code, src_key in pl_items:
        r = REG[f"PL.{key}"]
        label_row(ws, r, label, unit)

    # Margins
    r_em = REG["PL.ebitda_margin"]
    label_row(ws, r_em, "EBITDA margin", "%")
    r_nm = REG["PL.net_margin"]
    label_row(ws, r_nm, "Net margin", "%")

    # Formulas for forecast columns
    n_hist = 1
    for c_idx in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c_idx)

        # ── Cross-sheet refs: PL items ← engine sheets ──
        # Revenue ← 10_Revenue
        ref_cell(ws, REG["PL.revenue"], c_idx,
                 f"='{NAME['RV']}'!{cl}${REG['RV.total_rev']}", FMT_MLN, bold=True)
        # COGS ← 12_COGS
        ref_cell(ws, REG["PL.cogs"], c_idx,
                 f"='{NAME['CG']}'!{cl}${REG['CG.total']}", FMT_MLN)
        # SGA ← 13_SGA
        ref_cell(ws, REG["PL.sga"], c_idx,
                 f"='{NAME['SA']}'!{cl}${REG['SA.sga_total']}", FMT_MLN)
        # D&A ← 15_PPE dep_charge
        ref_cell(ws, REG["PL.da"], c_idx,
                 f"='{NAME['PP']}'!{cl}${REG['PP.dep_charge']}", FMT_MLN)
        # Interest ← 17_Debt
        ref_cell(ws, REG["PL.interest"], c_idx,
                 f"='{NAME['DT']}'!{cl}${REG['DT.interest']}", FMT_MLN)
        # Tax ← 19_Tax
        ref_cell(ws, REG["PL.tax"], c_idx,
                 f"='{NAME['TX']}'!{cl}${REG['TX.total']}", FMT_MLN)

        # GP = Revenue + COGS (COGS is negative)
        formula_cell(ws, REG["PL.gp"], c_idx,
                     f"={cl}{REG['PL.revenue']}+{cl}{REG['PL.cogs']}", FMT_MLN, bold=True)
        # EBITDA = GP + SGA + other_opex
        formula_cell(ws, REG["PL.ebitda"], c_idx,
                     f"={cl}{REG['PL.gp']}+{cl}{REG['PL.sga']}+{cl}{REG['PL.other_opex']}", FMT_MLN, bold=True)
        # EBIT = EBITDA - DA - impairment
        formula_cell(ws, REG["PL.ebit"], c_idx,
                     f"={cl}{REG['PL.ebitda']}-{cl}{REG['PL.da']}-{cl}{REG['PL.impairment']}", FMT_MLN, bold=True)
        # EBT = EBIT - interest + interest_income + other_fin + associates
        formula_cell(ws, REG["PL.ebt"], c_idx,
                     f"={cl}{REG['PL.ebit']}-{cl}{REG['PL.interest']}+{cl}{REG['PL.interest_income']}+"
                     f"{cl}{REG['PL.other_fin']}+{cl}{REG['PL.associates']}", FMT_MLN, bold=True)
        # NI = EBT - Tax
        formula_cell(ws, REG["PL.ni"], c_idx,
                     f"={cl}{REG['PL.ebt']}-{cl}{REG['PL.tax']}", FMT_MLN, bold=True)
        # Margins
        formula_cell(ws, r_em, c_idx,
                     f"=IF({cl}{REG['PL.revenue']}<>0,{cl}{REG['PL.ebitda']}/{cl}{REG['PL.revenue']},0)",
                     FMT_PCT)
        formula_cell(ws, r_nm, c_idx,
                     f"=IF({cl}{REG['PL.revenue']}<>0,{cl}{REG['PL.ni']}/{cl}{REG['PL.revenue']},0)",
                     FMT_PCT)


def build_ratios(wb, cfg):
    """30_Ratios — key financial ratios."""
    ws = wb["30_Ratios"]
    apply_col_widths(ws)

    ws.cell(1, 1, f"30_Ratios — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "Ключевые финансовые коэффициенты").font = F_SUBTITLE

    year_headers(ws, 4, cfg["hist_years"][-1:], cfg["fc_years"])

    section_header(ws, 6, "LEVERAGE")
    ratios = [
        ("nd_ebitda", "ND/EBITDA", "x"),
        ("icr", "EBITDA/Interest (ICR)", "x"),
        ("debt_equity", "Debt/Equity", "x"),
        ("debt_assets", "Debt/Assets", "%"),
    ]

    for key, label, unit in ratios:
        r = REG[f"RA.{key}"]
        label_row(ws, r, label, unit)

    section_header(ws, REG["RA.gp_margin"] - 1, "РЕНТАБЕЛЬНОСТЬ")
    margin_ratios = [
        ("gp_margin", "Gross margin", "%"),
        ("ebitda_margin", "EBITDA margin", "%"),
        ("ebit_margin", "EBIT margin", "%"),
        ("net_margin", "Net margin", "%"),
    ]
    for key, label, unit in margin_ratios:
        r = REG[f"RA.{key}"]
        label_row(ws, r, label, unit)

    section_header(ws, REG["RA.roe"] - 1, "ДОХОДНОСТЬ")
    for key, label in [("roe", "ROE"), ("roa", "ROA"), ("roic", "ROIC")]:
        label_row(ws, REG[f"RA.{key}"], label, "%")

    section_header(ws, REG["RA.current"] - 1, "ЛИКВИДНОСТЬ")
    for key, label in [("current", "Current ratio"), ("quick", "Quick ratio"), ("cash_ratio", "Cash ratio")]:
        label_row(ws, REG[f"RA.{key}"], label, "x")

    section_header(ws, REG["RA.dso"] - 1, "ОБОРОТНЫЙ КАПИТАЛ")
    for key, label in [("dso", "DSO"), ("dio", "DIH"), ("dpo", "DPO"), ("ccc", "CCC")]:
        label_row(ws, REG[f"RA.{key}"], label, "дни")

    # Key ratio formulas for forecast columns
    n_hist = 1
    for c_idx in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c_idx)

        # ND/EBITDA
        formula_cell(ws, REG["RA.nd_ebitda"], c_idx,
                     f"=IFERROR('{NAME['DT']}'!{cl}${REG['DT.nd']}/'{NAME['PL']}'!{cl}${REG['PL.ebitda']},0)",
                     FMT_MULT)
        # ICR
        formula_cell(ws, REG["RA.icr"], c_idx,
                     f"=IFERROR('{NAME['PL']}'!{cl}${REG['PL.ebitda']}/'{NAME['PL']}'!{cl}${REG['PL.interest']},0)",
                     FMT_MULT)
        # EBITDA margin
        formula_cell(ws, REG["RA.ebitda_margin"], c_idx,
                     f"=IFERROR('{NAME['PL']}'!{cl}${REG['PL.ebitda']}/'{NAME['PL']}'!{cl}${REG['PL.revenue']},0)",
                     FMT_PCT)
        # Net margin
        formula_cell(ws, REG["RA.net_margin"], c_idx,
                     f"=IFERROR('{NAME['PL']}'!{cl}${REG['PL.ni']}/'{NAME['PL']}'!{cl}${REG['PL.revenue']},0)",
                     FMT_PCT)
        # ROE
        formula_cell(ws, REG["RA.roe"], c_idx,
                     f"=IFERROR('{NAME['PL']}'!{cl}${REG['PL.ni']}/'{NAME['BS']}'!{cl}${REG['BS.te']},0)",
                     FMT_PCT)
        # Current ratio
        formula_cell(ws, REG["RA.current"], c_idx,
                     f"=IFERROR('{NAME['BS']}'!{cl}${REG['BS.tca']}/'{NAME['BS']}'!{cl}${REG['BS.tcl']},0)",
                     FMT_MULT)


def build_checks(wb, cfg):
    """90_Checks — integrity verification."""
    ws = wb["90_Checks"]
    apply_col_widths(ws)

    ws.cell(1, 1, f"90_Checks — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "Проверки целостности модели").font = F_SUBTITLE

    year_headers(ws, 4, cfg["hist_years"][-1:], cfg["fc_years"])

    section_header(ws, 6, "ПРОВЕРКИ (все должны = 0)")
    checks = [
        ("bs_check", "BS: Активы − Обяз. − Капитал", "BS", "check"),
        ("cf_check", "CF: ΔCash(BS) − (CFO+CFI+CFF)", None, None),
        ("ppe_roll", "PPE: Net(close) − Gross + AccDep", None, None),
        ("debt_roll", "Debt: Open + Draw − Repay − Close", None, None),
        ("equity_roll", "Equity: Open + NI − Div − Close", None, None),
    ]

    for key, label, src_code, src_key in checks:
        r = REG.get(f"CK.{key}", 7)
        label_row(ws, r, label, "mln", "= 0 ✓")

    # BS check formula
    n_hist = 1
    for c_idx in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c_idx)
        # BS check = direct reference from 20_BS
        ref_cell(ws, REG["CK.bs_check"], c_idx,
                 f"='{NAME['BS']}'!{cl}${REG['BS.check']}", FMT_RATIO)

    # Error count
    r_err = REG["CK.error_count"]
    label_row(ws, r_err, "ОШИБОК ВСЕГО", "", "Должно быть = 0")
    ws.cell(r_err, 1).font = F_LABEL_B


def build_cogs(wb, cfg):
    """12_COGS — cost of goods sold (component or ratio)."""
    ws = wb["12_COGS"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"12_COGS — {cfg['name']}").font = F_TITLE
    n_hist = len(cfg["hist_years"][-3:])
    year_headers(ws, 4, cfg["hist_years"][-3:], cfg["fc_years"])

    section_header(ws, 6, "СЕБЕСТОИМОСТЬ")
    if cfg.get("cogs_mode") == "component":
        comps = cfg.get("cogs_components", {})
        for i, (comp, share) in enumerate(comps.items()):
            r = REG.get(f"CG.{comp}", 8 + i)
            label_row(ws, r, f"{comp.title()} ({share*100:.0f}%)", "mln")
            for c in range(3, 3 + n_hist + len(cfg["fc_years"])):
                input_cell(ws, r, c, 0, FMT_MLN)
    else:
        label_row(ws, REG["CG.total"], "COGS (ratio-based)", "mln")

    # Total COGS
    r_total = REG["CG.total"]
    label_row(ws, r_total, "ИТОГО СЕБЕСТОИМОСТЬ", "mln")
    ws.cell(r_total, 1).font = F_LABEL_B

    if cfg.get("cogs_mode") == "component":
        comps = cfg.get("cogs_components", {})
        comp_keys = list(comps.keys())
        for c in range(3, 3 + n_hist + len(cfg["fc_years"])):
            cl = get_column_letter(c)
            parts = [f"{cl}{REG.get(f'CG.{k}', 8)}" for k in comp_keys]
            formula_cell(ws, r_total, c, "=-(" + "+".join(parts) + ")", FMT_MLN, bold=True)

    # COGS ratio
    r_ratio = REG["CG.ratio"]
    label_row(ws, r_ratio, "COGS / Revenue", "%")
    for c in range(3, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c)
        formula_cell(ws, r_ratio, c,
                     f"=IFERROR({cl}{r_total}/'{NAME['RV']}'!{cl}${REG['RV.total_rev']},0)", FMT_PCT)


def build_sga(wb, cfg):
    """13_SGA — selling, general & administrative."""
    ws = wb["13_SGA"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"13_SGA — {cfg['name']}").font = F_TITLE
    n_hist = len(cfg["hist_years"][-3:])
    year_headers(ws, 4, cfg["hist_years"][-3:], cfg["fc_years"])

    section_header(ws, 6, "ОПЕРАЦИОННЫЕ РАСХОДЫ (SGA)")
    for key, label in [("sga_total", "SGA итого"), ("admin", "Административные"),
                       ("distrib", "Коммерческие"), ("ecl", "ECL расходы")]:
        r = REG.get(f"SA.{key}", 8)
        label_row(ws, r, label, "mln")
        for c in range(3, 3 + n_hist + len(cfg["fc_years"])):
            input_cell(ws, r, c, 0, FMT_MLN)

    r_ratio = REG["SA.sga_ratio"]
    label_row(ws, r_ratio, "SGA / Revenue", "%")
    for c in range(3, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c)
        formula_cell(ws, r_ratio, c,
                     f"=IFERROR({cl}{REG['SA.sga_total']}/'{NAME['RV']}'!{cl}${REG['RV.total_rev']},0)", FMT_PCT)


def build_wc(wb, cfg):
    """16_WC — working capital (DSO/DIO/DPO → AR/INV/AP)."""
    ws = wb["16_WC"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"16_WC — {cfg['name']}").font = F_TITLE
    n_hist = len(cfg["hist_years"][-3:])
    year_headers(ws, 4, cfg["hist_years"][-3:], cfg["fc_years"])

    section_header(ws, 6, "ОБОРОТНЫЙ КАПИТАЛ")
    # Days inputs
    for key, label in [("dso", "DSO (дни)"), ("dio", "DIH (дни)"), ("dpo", "DPO (дни)")]:
        r = REG[f"WC.{key}"]
        label_row(ws, r, label, "дни")
        for c in range(3, 3 + n_hist + len(cfg["fc_years"])):
            input_cell(ws, r, c, 0, FMT_DAYS)

    # CCC = DSO + DIO - DPO
    r_ccc = REG["WC.ccc"]
    label_row(ws, r_ccc, "CCC (дни)", "дни")
    for c in range(3, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c)
        formula_cell(ws, r_ccc, c,
                     f"={cl}{REG['WC.dso']}+{cl}{REG['WC.dio']}-{cl}{REG['WC.dpo']}", FMT_DAYS)

    section_header(ws, REG["WC.ar"] - 1, "WC БАЛАНСОВЫЕ СТАТЬИ")
    # AR = Revenue × DSO / 365
    for key, label, driver, driver_key in [
        ("ar", "Дебиторская задолженность", "RV", "total_rev"),
        ("inv", "Запасы", "CG", "total"),
        ("ap", "Кредиторская задолженность", "CG", "total"),
    ]:
        r = REG[f"WC.{key}"]
        label_row(ws, r, label, "mln")
        days_key = {"ar": "dso", "inv": "dio", "ap": "dpo"}[key]
        for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
            cl = get_column_letter(c)
            sign = "" if key != "ap" else "-"
            formula_cell(ws, r, c,
                         f"={sign}ABS('{NAME[driver]}'!{cl}${REG[f'{driver}.{driver_key}']})*{cl}{REG[f'WC.{days_key}']}/365",
                         FMT_MLN)

    # NWC = AR + INV - AP
    r_nwc = REG["WC.nwc"]
    label_row(ws, r_nwc, "Чистый оборотный капитал", "mln")
    for c in range(3, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c)
        formula_cell(ws, r_nwc, c,
                     f"={cl}{REG['WC.ar']}+{cl}{REG['WC.inv']}-ABS({cl}{REG['WC.ap']})", FMT_MLN, bold=True)

    # ΔNWC
    r_delta = REG["WC.delta_nwc"]
    label_row(ws, r_delta, "Изменение NWC", "mln")
    for c in range(4, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c)
        prev = get_column_letter(c - 1)
        formula_cell(ws, r_delta, c, f"={cl}{r_nwc}-{prev}{r_nwc}", FMT_MLN)


def build_cf(wb, cfg):
    """23_CF — Cash Flow Statement (indirect method)."""
    ws = wb["23_CF"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"23_CF — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "ОДДС (косвенный метод)").font = F_SUBTITLE
    n_hist = 1
    year_headers(ws, 4, cfg["hist_years"][-1:], cfg["fc_years"])

    section_header(ws, 6, "ОПЕРАЦИОННАЯ ДЕЯТЕЛЬНОСТЬ (CFO)")
    cf_items = [
        ("ni", "Чистая прибыль", "PL", "ni"),
        ("da", "D&A (неденежное)", "PP", "dep_charge"),
        ("impairment", "Обесценение", "OI", "impairment"),
        ("deferred_tax", "Отложенный налог", "TX", "deferred"),
        ("wc_change", "Изменение оборотного капитала", "WC", "delta_nwc"),
        ("other_noncash", "Прочие неденежные", None, None),
    ]
    for key, label, src, src_key in cf_items:
        r = REG[f"CF.{key}"]
        label_row(ws, r, label, "mln")

    r_cfo = REG["CF.cfo"]
    label_row(ws, r_cfo, "ИТОГО CFO", "mln")
    ws.cell(r_cfo, 1).font = F_LABEL_B

    section_header(ws, REG["CF.capex"] - 1, "ИНВЕСТИЦИОННАЯ ДЕЯТЕЛЬНОСТЬ (CFI)")
    for key, label in [("capex", "Капитальные затраты"), ("disp_proceeds", "Поступления от выбытий"),
                       ("other_cfi", "Прочие CFI")]:
        label_row(ws, REG[f"CF.{key}"], label, "mln")

    r_cfi = REG["CF.cfi"]
    label_row(ws, r_cfi, "ИТОГО CFI", "mln")

    section_header(ws, REG["CF.debt_draw"] - 1, "ФИНАНСОВАЯ ДЕЯТЕЛЬНОСТЬ (CFF)")
    for key, label in [("debt_draw", "Привлечение долга"), ("debt_repay", "Погашение долга"),
                       ("lease_pay", "Платежи по аренде"), ("interest_paid", "Проценты уплаченные"),
                       ("div_paid", "Дивиденды уплаченные"), ("other_cff", "Прочие CFF")]:
        label_row(ws, REG[f"CF.{key}"], label, "mln")

    r_cff = REG["CF.cff"]
    label_row(ws, r_cff, "ИТОГО CFF", "mln")

    label_row(ws, REG["CF.fx"], "Курсовые разницы", "mln")
    r_net = REG["CF.net_change"]
    label_row(ws, r_net, "Чистое изменение ДС", "mln")
    label_row(ws, REG["CF.cash_open"], "ДС на начало", "mln")
    label_row(ws, REG["CF.cash_close"], "ДС на конец", "mln")

    # Formulas
    for c_idx in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c_idx)
        prev = get_column_letter(c_idx - 1)

        # ── Cross-sheet refs: CF items ← source sheets ──
        # NI ← PL
        ref_cell(ws, REG["CF.ni"], c_idx,
                 f"='{NAME['PL']}'!{cl}${REG['PL.ni']}", FMT_MLN)
        # DA ← PPE
        ref_cell(ws, REG["CF.da"], c_idx,
                 f"='{NAME['PP']}'!{cl}${REG['PP.dep_charge']}", FMT_MLN)
        # Deferred tax ← Tax
        ref_cell(ws, REG["CF.deferred_tax"], c_idx,
                 f"='{NAME['TX']}'!{cl}${REG['TX.deferred']}", FMT_MLN)
        # WC change ← WC delta
        ref_cell(ws, REG["CF.wc_change"], c_idx,
                 f"='{NAME['WC']}'!{cl}${REG['WC.delta_nwc']}", FMT_MLN)
        # CapEx ← PPE
        ref_cell(ws, REG["CF.capex"], c_idx,
                 f"='{NAME['PP']}'!{cl}${REG['PP.capex']}", FMT_MLN)
        # Dividends ← Equity
        ref_cell(ws, REG["CF.div_paid"], c_idx,
                 f"='{NAME['EQ']}'!{cl}${REG['EQ.div']}", FMT_MLN)
        # Interest paid ← Debt
        ref_cell(ws, REG["CF.interest_paid"], c_idx,
                 f"='{NAME['DT']}'!{cl}${REG['DT.interest']}", FMT_MLN)

        # CFO = NI + DA + impairment + deferred_tax - WC_change + other
        cfo_parts = [f"{cl}{REG['CF.ni']}", f"{cl}{REG['CF.da']}", f"{cl}{REG['CF.impairment']}",
                     f"{cl}{REG['CF.deferred_tax']}", f"-{cl}{REG['CF.wc_change']}", f"{cl}{REG['CF.other_noncash']}"]
        formula_cell(ws, r_cfo, c_idx, "=" + "+".join(cfo_parts), FMT_MLN, bold=True)

        # CFI = -capex + disp + other
        formula_cell(ws, r_cfi, c_idx,
                     f"=-ABS({cl}{REG['CF.capex']})+{cl}{REG['CF.disp_proceeds']}+{cl}{REG['CF.other_cfi']}",
                     FMT_MLN, bold=True)

        # CFF = draw - repay - lease - interest - div + other
        cff_parts = [f"{cl}{REG['CF.debt_draw']}", f"-ABS({cl}{REG['CF.debt_repay']})",
                     f"-ABS({cl}{REG['CF.lease_pay']})", f"-ABS({cl}{REG['CF.interest_paid']})",
                     f"-ABS({cl}{REG['CF.div_paid']})", f"{cl}{REG['CF.other_cff']}"]
        formula_cell(ws, r_cff, c_idx, "=" + "+".join(cff_parts), FMT_MLN, bold=True)

        # Net change = CFO + CFI + CFF + FX
        formula_cell(ws, r_net, c_idx,
                     f"={cl}{r_cfo}+{cl}{r_cfi}+{cl}{r_cff}+{cl}{REG['CF.fx']}", FMT_MLN, bold=True)

        # Cash opening = prev closing
        formula_cell(ws, REG["CF.cash_open"], c_idx, f"={prev}{REG['CF.cash_close']}", FMT_MLN)
        # Cash closing = opening + net change
        formula_cell(ws, REG["CF.cash_close"], c_idx,
                     f"={cl}{REG['CF.cash_open']}+{cl}{r_net}", FMT_MLN, bold=True)


def build_equity(wb, cfg):
    """24_Equity — retained earnings corkscrew."""
    ws = wb["24_Equity"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"24_Equity — {cfg['name']}").font = F_TITLE
    n_hist = 1
    year_headers(ws, 4, cfg["hist_years"][-1:], cfg["fc_years"])

    section_header(ws, 6, "НЕРАСПРЕДЕЛЁННАЯ ПРИБЫЛЬ")
    for key, label in [("re_open", "Начало периода"), ("ni", "Чистая прибыль"),
                       ("div", "Дивиденды"), ("buyback", "Выкуп акций"),
                       ("other", "Прочие изменения"), ("re_close", "Конец периода")]:
        r = REG[f"EQ.{key}"]
        label_row(ws, r, label, "mln")

    label_row(ws, REG["EQ.payout"], "Payout ratio", "%")

    for c_idx in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c_idx)
        prev = get_column_letter(c_idx - 1)

        # RE open = prev close
        formula_cell(ws, REG["EQ.re_open"], c_idx, f"={prev}{REG['EQ.re_close']}", FMT_MLN)
        # NI from PL
        ref_cell(ws, REG["EQ.ni"], c_idx,
                 f"='{NAME['PL']}'!{cl}${REG['PL.ni']}", FMT_MLN)
        # RE close = open + NI - div - buyback + other
        formula_cell(ws, REG["EQ.re_close"], c_idx,
                     f"={cl}{REG['EQ.re_open']}+{cl}{REG['EQ.ni']}"
                     f"-ABS({cl}{REG['EQ.div']})-ABS({cl}{REG['EQ.buyback']})+{cl}{REG['EQ.other']}",
                     FMT_MLN, bold=True)
        # Payout
        formula_cell(ws, REG["EQ.payout"], c_idx,
                     f"=IFERROR(ABS({cl}{REG['EQ.div']})/{cl}{REG['EQ.ni']},0)", FMT_PCT)


def build_tax(wb, cfg):
    """19_Tax — IAS 12 tax model."""
    ws = wb["19_Tax"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"19_Tax — {cfg['name']}").font = F_TITLE
    n_hist = 1
    year_headers(ws, 4, cfg["hist_years"][-1:], cfg["fc_years"])

    section_header(ws, 6, "НАЛОГ НА ПРИБЫЛЬ (IAS 12)")
    for key, label in [("ebt", "Прибыль до налога (EBT)"), ("nol_open", "NOL начало"),
                       ("nol_used", "NOL использовано"), ("taxable", "Налогооблагаемая прибыль"),
                       ("current", "Текущий налог"), ("deferred", "Отложенный налог"),
                       ("total", "ИТОГО налог"), ("eff_rate", "Эффективная ставка")]:
        r = REG.get(f"TX.{key}", 7)
        label_row(ws, r, label, "mln" if key != "eff_rate" else "%")

    section_header(ws, REG["TX.nol_close"] - 1, "NOL CARRYFORWARD")
    label_row(ws, REG["TX.nol_close"], "NOL конец", "mln")

    section_header(ws, REG["TX.dta_open"] - 1, "ОТЛОЖЕННЫЕ НАЛОГИ (DTA / DTL)")
    for key, label in [("dta_open", "DTA начало"), ("dta_close", "DTA конец"),
                       ("dtl_open", "DTL начало"), ("dtl_close", "DTL конец")]:
        label_row(ws, REG[f"TX.{key}"], label, "mln")

    # Tax formulas
    for c_idx in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c_idx)
        prev = get_column_letter(c_idx - 1)

        # EBT from PL
        ref_cell(ws, REG["TX.ebt"], c_idx,
                 f"='{NAME['PL']}'!{cl}${REG['PL.ebt']}", FMT_MLN)
        # NOL open = prev close
        formula_cell(ws, REG["TX.nol_open"], c_idx, f"={prev}{REG['TX.nol_close']}", FMT_MLN)
        # NOL used = min(NOL_open, EBT × 80%)
        formula_cell(ws, REG["TX.nol_used"], c_idx,
                     f"=MIN({cl}{REG['TX.nol_open']},MAX(0,{cl}{REG['TX.ebt']})*0.8)", FMT_MLN)
        # Taxable = EBT - NOL_used
        formula_cell(ws, REG["TX.taxable"], c_idx,
                     f"=MAX(0,{cl}{REG['TX.ebt']}-{cl}{REG['TX.nol_used']})", FMT_MLN)
        # Current tax = taxable × 25%
        formula_cell(ws, REG["TX.current"], c_idx,
                     f"={cl}{REG['TX.taxable']}*0.25", FMT_MLN)
        # Total = current + deferred
        formula_cell(ws, REG["TX.total"], c_idx,
                     f"={cl}{REG['TX.current']}+{cl}{REG['TX.deferred']}", FMT_MLN, bold=True)
        # Effective rate
        formula_cell(ws, REG["TX.eff_rate"], c_idx,
                     f"=IFERROR({cl}{REG['TX.total']}/{cl}{REG['TX.ebt']},0)", FMT_PCT)
        # NOL close = open - used
        formula_cell(ws, REG["TX.nol_close"], c_idx,
                     f"={cl}{REG['TX.nol_open']}-{cl}{REG['TX.nol_used']}", FMT_MLN)


def build_valuation(wb, cfg):
    """35_Valuation — DCF + SOTP + Sensitivity."""
    ws = wb["35_Valuation"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"35_Valuation — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "DCF + SOTP + Sensitivity Matrix").font = F_SUBTITLE

    section_header(ws, 6, "A. WACC (Cost of Capital)")
    for key, label, default in [
        ("rf", "Risk-free rate (Rf)", 0.10), ("beta", "Beta", 1.1),
        ("erp", "Equity Risk Premium", 0.07), ("crp", "Country Risk Premium", 0.04),
        ("scp", "Size/Company Premium", 0.01),
    ]:
        r = REG[f"VL.{key}"]
        label_row(ws, r, label, "%")
        input_cell(ws, r, 3, default, FMT_PCT2 if key != "beta" else FMT_RATIO)

    r_wacc = REG["VL.wacc"]
    label_row(ws, r_wacc, "WACC (Ke)", "%")
    formula_cell(ws, r_wacc, 3,
                 f"=$C${REG['VL.rf']}+$C${REG['VL.beta']}*$C${REG['VL.erp']}+"
                 f"$C${REG['VL.crp']}+$C${REG['VL.scp']}", FMT_PCT2, bold=True)

    section_header(ws, REG["VL.tg"] - 1, "B. TERMINAL VALUE")
    for key, label, default in [("tg", "Terminal growth (g)", 0.03),
                                 ("tm", "Terminal EV/EBITDA", 6.0)]:
        r = REG[f"VL.{key}"]
        label_row(ws, r, label)
        input_cell(ws, r, 3, default, FMT_PCT if key == "tg" else FMT_MULT)

    section_header(ws, REG["VL.ev"] - 1, "C. DCF RESULT")
    for key, label in [("ev", "Enterprise Value"), ("nd", "Net Debt"), ("eq_value", "Equity Value")]:
        r = REG[f"VL.{key}"]
        label_row(ws, r, label, "mln")

    section_header(ws, REG["VL.sotp_total"] - 1, "D. SOTP (Sum of the Parts)")
    label_row(ws, REG["VL.sotp_total"], "SOTP Enterprise Value", "mln")

    section_header(ws, REG["VL.sens_matrix"] - 1, "E. SENSITIVITY MATRIX (WACC × Terminal Growth)")
    label_row(ws, REG["VL.sens_matrix"], "5×5 матрица: Equity Value = f(WACC, g)")


def build_score(wb, cfg):
    """31_Score — S&P 4-factor rating scorecard."""
    ws = wb["31_Score"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"31_Score — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "S&P-like 4-factor Credit Rating").font = F_SUBTITLE
    n_hist = 1
    year_headers(ws, 4, cfg["hist_years"][-1:], cfg["fc_years"])

    section_header(ws, 6, "СКОРКАРТА")
    for key, label, weight in [
        ("leverage", "Leverage Score (ND/EBITDA)", "35%"),
        ("coverage", "Coverage Score (ICR)", "30%"),
        ("profit", "Profitability Score (EBITDA margin)", "20%"),
        ("liquidity", "Liquidity Score (Current + Cash)", "15%"),
    ]:
        r = REG[f"SC.{key}"]
        label_row(ws, r, f"{label} [{weight}]", "балл")

    section_header(ws, REG["SC.base"] - 1, "ИТОГОВЫЙ РЕЙТИНГ")
    for key, label in [("base", "Базовый балл"), ("ind_adj", "Отраслевая корректировка"),
                       ("size_adj", "Размерная корректировка"), ("final", "Итоговый балл"),
                       ("rating", "Рейтинг (S&P эквивалент)")]:
        r = REG[f"SC.{key}"]
        label_row(ws, r, label, "балл" if key != "rating" else "")

    # Industry/size adjustments as inputs
    input_cell(ws, REG["SC.ind_adj"], 3, cfg.get("rating_ind_adj", -6), FMT_RATIO1)
    input_cell(ws, REG["SC.size_adj"], 3, cfg.get("rating_size_adj", 2), FMT_RATIO1)


def build_covenants(wb, cfg):
    """32_Covenants — covenant monitoring."""
    ws = wb["32_Covenants"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"32_Covenants — {cfg['name']}").font = F_TITLE
    n_hist = 1
    year_headers(ws, 4, cfg["hist_years"][-1:], cfg["fc_years"])

    section_header(ws, 6, "МОНИТОРИНГ КОВЕНАНТОВ")
    covs = cfg.get("covenants", {})
    for key, label, threshold in [
        ("nd_ebitda", "ND/EBITDA", covs.get("nd_ebitda_max", 4.5)),
        ("icr", "Interest Coverage (ICR)", covs.get("icr_min", 2.0)),
        ("ebitda_margin", "EBITDA Margin", covs.get("margin_min", 0.10)),
    ]:
        r = REG.get(f"CO.{key}", 7)
        label_row(ws, r, label)
        # Threshold in col L
        ws.cell(r, 12, f"Порог: {threshold}").font = F_NOTE


def build_control_panel(wb, cfg):
    """Control_Panel — единая точка ввода 130+ параметров."""
    ws = wb["Control_Panel"]
    apply_col_widths(ws)
    ws.cell(1, 1, "ПАНЕЛЬ УПРАВЛЕНИЯ МОДЕЛЬЮ").font = F_TITLE
    ws.cell(2, 1, "Единственное место ввода. Синие = ввод. Зелёные = формулы (не редактировать).").font = F_SUBTITLE

    r = 4
    # ── A. МАКРОСЦЕНАРИЙ ──
    section_header(ws, r, "A. МАКРОСЦЕНАРИЙ"); r += 1
    label_row(ws, r, "Активный сценарий (1/2/3)", "", "1=Базовый, 2=Стресс, 3=Рецессия")
    input_cell(ws, r, 3, 1, FMT_INT); r += 2

    for i, factor in enumerate(cfg["macro_factors"]):
        label_row(ws, r, factor)
        for c in range(7, 7 + len(cfg["fc_years"])):
            input_cell(ws, r, c, 0, FMT_RATIO1)
        r += 1
    r += 1

    # ── B. ОПЕРАЦИОННЫЕ ПОКАЗАТЕЛИ ──
    section_header(ws, r, "B. ОПЕРАЦИОННЫЕ ПОКАЗАТЕЛИ"); r += 1
    for seg in cfg["segments"]:
        label_row(ws, r, f"{seg['name']}: объём (kt)")
        for c in range(7, 7 + len(cfg["fc_years"])):
            input_cell(ws, r, c, 0, FMT_INT)
        r += 1
        label_row(ws, r, f"{seg['name']}: рост цены (%)", "", f"Driver: {seg['driver']}")
        for c in range(7, 7 + len(cfg["fc_years"])):
            input_cell(ws, r, c, 0, FMT_PCT)
        r += 1
    r += 1

    # ── C. ВЫРУЧКА ──
    section_header(ws, r, "C. ВЫРУЧКА"); r += 1
    label_row(ws, r, "Revenue method (1=segment, 2=macro_ols, 3=ewa)")
    input_cell(ws, r, 3, 1, FMT_INT); r += 1
    label_row(ws, r, "Эластичность Revenue к macro-фактору", "", "β × Δln(factor)")
    input_cell(ws, r, 3, 1.0, FMT_RATIO); r += 1
    label_row(ws, r, "R² (коэфф. детерминации)")
    ref_cell(ws, r, 3, f"='{NAME['MA']}'!$C${REG.get('MA.econ_r2', 53)}", FMT_PCT2); r += 2

    # ── D. СЕБЕСТОИМОСТЬ ──
    section_header(ws, r, "D. СЕБЕСТОИМОСТЬ"); r += 1
    cogs_method = 2 if cfg.get("cogs_mode") == "component" else 1
    label_row(ws, r, "COGS method (1=ratio, 2=component, 3=ppi_uplift)")
    input_cell(ws, r, 3, cogs_method, FMT_INT); r += 1
    if cfg.get("cogs_mode") == "component":
        for comp, share in cfg.get("cogs_components", {}).items():
            label_row(ws, r, f"Доля {comp.title()}", "%")
            input_cell(ws, r, 3, share, FMT_PCT); r += 1
    else:
        label_row(ws, r, "COGS ratio (default)")
        input_cell(ws, r, 3, cfg.get("cogs_ratio_default", 0.60), FMT_PCT); r += 1
    label_row(ws, r, "PPI beta (COGS ~ PPI)")
    input_cell(ws, r, 3, 0.85, FMT_RATIO); r += 1
    label_row(ws, r, "Mean reversion dampening")
    input_cell(ws, r, 3, 0.30, FMT_RATIO); r += 2

    # ── E. SGA / ОПЕКС ──
    section_header(ws, r, "E. SGA / ОПЕРАЦИОННЫЕ РАСХОДЫ"); r += 1
    label_row(ws, r, "SGA ratio (EWA)")
    input_cell(ws, r, 3, 0.08, FMT_PCT); r += 1
    label_row(ws, r, "EWA halflife (лет)")
    input_cell(ws, r, 3, 5, FMT_INT); r += 2

    # ── F. CAPEX / PP&E ──
    cp_da_rate_row = r + 1  # save for ref from PPE sheet
    section_header(ws, r, "F. КАПИТАЛЬНЫЕ ЗАТРАТЫ / PP&E"); r += 1
    label_row(ws, r, "DA rate (амортизация / ОС нетто)", "%")
    input_cell(ws, r, 3, 0.07, FMT_PCT)
    # Store this row for cross-ref — we'll update reg.json
    REG["CP.da_rate"] = r
    r += 1
    label_row(ws, r, "Sustaining CapEx / DA ratio")
    input_cell(ws, r, 3, 1.8, FMT_RATIO); r += 1
    label_row(ws, r, "Expansion CapEx (% rev growth)")
    input_cell(ws, r, 3, 0.05, FMT_PCT); r += 1
    label_row(ws, r, "Useful life (лет)")
    input_cell(ws, r, 3, 16, FMT_INT); r += 1
    label_row(ws, r, "Disposal % of CapEx")
    input_cell(ws, r, 3, 0.0, FMT_PCT); r += 2

    # ── G. ОБОРОТНЫЙ КАПИТАЛ ──
    section_header(ws, r, "G. ОБОРОТНЫЙ КАПИТАЛ"); r += 1
    label_row(ws, r, "WC method (1=days, 2=ratio)")
    input_cell(ws, r, 3, 1, FMT_INT); r += 1
    for d, default in [("DSO (дни)", 30), ("DIH (дни)", 80), ("DPO (дни)", 40)]:
        label_row(ws, r, d)
        input_cell(ws, r, 3, default, FMT_DAYS); r += 1
    r += 1

    # ── H. ДОЛГ ──
    section_header(ws, r, "H. ДОЛГ"); r += 1
    label_row(ws, r, "Target ND/EBITDA")
    input_cell(ws, r, 3, cfg.get("debt_target_nd_ebitda", 2.0), FMT_MULT); r += 1
    label_row(ws, r, "Min cash target", "mln")
    input_cell(ws, r, 3, 500, FMT_MLN0); r += 1
    label_row(ws, r, "Max voluntary prepay (% FCF)")
    input_cell(ws, r, 3, 0.30, FMT_PCT); r += 2

    # ── I. НАЛОГИ ──
    section_header(ws, r, "I. НАЛОГИ"); r += 1
    label_row(ws, r, "Statutory tax rate")
    input_cell(ws, r, 3, 0.25, FMT_PCT); r += 1
    label_row(ws, r, "NOL opening balance", "mln")
    input_cell(ws, r, 3, 0, FMT_MLN0); r += 1
    label_row(ws, r, "NOL max utilization (%)")
    input_cell(ws, r, 3, 0.80, FMT_PCT); r += 2

    # ── J. ДИВИДЕНДЫ И КАПИТАЛ ──
    section_header(ws, r, "J. ДИВИДЕНДЫ И КАПИТАЛ"); r += 1
    payout = 0.0 if "RUSAL" in cfg["name"] else 0.60
    label_row(ws, r, "Dividend payout ratio")
    input_cell(ws, r, 3, payout, FMT_PCT); r += 1
    label_row(ws, r, "Buyback (% FCF)")
    input_cell(ws, r, 3, 0.0, FMT_PCT); r += 2

    # ── K. ОЦЕНКА (DCF) ──
    section_header(ws, r, "K. ОЦЕНКА (DCF)"); r += 1
    for param, val, fmt in [
        ("Risk-free rate (Rf)", 0.10, FMT_PCT),
        ("Beta", 1.1, FMT_RATIO),
        ("Equity Risk Premium", 0.07, FMT_PCT),
        ("Country Risk Premium", 0.04, FMT_PCT),
        ("Size Premium", 0.01, FMT_PCT),
        ("Terminal growth (g)", 0.03, FMT_PCT),
        ("Terminal EV/EBITDA", 6.0, FMT_MULT),
    ]:
        label_row(ws, r, param)
        input_cell(ws, r, 3, val, fmt); r += 1
    r += 1

    # ── L. СКОРКАРТА ──
    section_header(ws, r, "L. СКОРКАРТА (S&P 4-FACTOR)"); r += 1
    for param, val in [
        ("Leverage weight", 0.35), ("Coverage weight", 0.30),
        ("Profitability weight", 0.20), ("Liquidity weight", 0.15),
        ("Industry adjustment", cfg.get("rating_ind_adj", -6)),
        ("Size adjustment", cfg.get("rating_size_adj", 2)),
        ("Cycle avg EBITDA margin", cfg.get("rating_cycle_margin", 0.20)),
    ]:
        label_row(ws, r, param)
        fmt = FMT_PCT if "weight" in param or "margin" in param else FMT_RATIO1
        input_cell(ws, r, 3, val, fmt); r += 1

    # ── РЕЗУЛЬТАТ: СВОДКА ──
    r += 1
    section_header(ws, r, "СВОДКА КЛЮЧЕВЫХ ПОКАЗАТЕЛЕЙ"); r += 1
    year_headers(ws, r, cfg["hist_years"][-1:], cfg["fc_years"]); r += 1
    for label, code, key, fmt in [
        ("Revenue", "PL", "revenue", FMT_MLN),
        ("EBITDA", "PL", "ebitda", FMT_MLN),
        ("Net Income", "PL", "ni", FMT_MLN),
        ("EBITDA margin", "RA", "ebitda_margin", FMT_PCT),
        ("ND/EBITDA", "RA", "nd_ebitda", FMT_MULT),
        ("ICR", "RA", "icr", FMT_MULT),
        ("ROE", "RA", "roe", FMT_PCT),
    ]:
        label_row(ws, r, label)
        for c in range(4, 4 + len(cfg["fc_years"])):
            cl = get_column_letter(c)
            row_src = REG.get(f"{code}.{key}")
            if row_src:
                ref_cell(ws, r, c, f"='{NAME[code]}'!{cl}${row_src}", fmt)
        r += 1


def build_guide(wb, cfg):
    """00_Guide — navigation with hyperlinks."""
    ws = wb["00_Guide"]
    apply_col_widths(ws)
    ws.cell(1, 1, "РУКОВОДСТВО ПО МОДЕЛИ").font = F_TITLE
    ws.cell(2, 1, f"Финансовая модель {cfg['name']} · v4 · Excel-driven").font = F_SUBTITLE

    steps = [
        ("ЭТАП 1: ПОДГОТОВКА ДАННЫХ", [
            ("02_Hist", "Загрузить историческую отчётность МСФО (IS/BS/CF)"),
            ("Raw_IFRS", "Детальные раскрытия МСФО (ноты)"),
            ("11_Segments", "Операционные показатели по сегментам"),
            ("01_Macro", "Макро-факторы и сценарии"),
        ]),
        ("ЭТАП 2: КАЛИБРОВКА", [
            ("Control_Panel", "Настроить все 130+ параметров модели"),
            ("90_Checks", "Проверить калибровочные значения"),
        ]),
        ("ЭТАП 3: РАСЧЁТНЫЕ ЛИСТЫ (автоматически)", [
            ("10_Revenue", "Выручка = Σ(Volume × Price) по сегментам"),
            ("12_COGS", "Себестоимость (компонентная или ratio)"),
            ("15_PPE", "PP&E corkscrew (CapEx → Dep → Net)"),
            ("16_WC", "Оборотный капитал (DSO/DIO/DPO)"),
            ("17_Debt", "Долговой портфель (instrument-level)"),
            ("19_Tax", "Налоги (IAS 12, NOL, DTA/DTL)"),
        ]),
        ("ЭТАП 4: ФИНАНСОВЫЕ ОТЧЁТЫ", [
            ("21_PL", "P&L: Revenue → EBITDA → EBIT → NI"),
            ("20_BS", "Баланс: A = L + E (проверка)"),
            ("23_CF", "ОДДС (косвенный метод)"),
        ]),
        ("ЭТАП 5: АНАЛИЗ", [
            ("30_Ratios", "Ключевые коэффициенты (25+ метрик)"),
            ("31_Score", "Кредитный рейтинг (S&P 4-factor)"),
            ("32_Covenants", "Мониторинг ковенантов"),
            ("35_Valuation", "Оценка (DCF + SOTP + Sensitivity)"),
            ("Model_Output", "Сводный дашборд"),
        ]),
    ]

    r = 4
    for stage_title, items in steps:
        section_header(ws, r, stage_title); r += 1
        for sheet_name, description in items:
            ws.cell(r, 1).value = f'=HYPERLINK("#\'{sheet_name}\'!A1", "{sheet_name}")'
            ws.cell(r, 1).font = F_GUIDE_LINK
            ws.cell(r, 2, description).font = F_LABEL
            r += 1
        r += 1


def build_model_output(wb, cfg):
    """Model_Output — 12-section summary dashboard."""
    ws = wb["Model_Output"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"Model_Output — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "Сводный вывод модели (все ссылки — зелёные)").font = F_SUBTITLE

    n_hist = 1
    year_headers(ws, 4, cfg["hist_years"][-1:], cfg["fc_years"])

    r = 6
    sections = [
        ("1. ДОХОДЫ И РАСХОДЫ (PL)", [
            ("Выручка", "PL", "revenue", FMT_MLN),
            ("COGS", "PL", "cogs", FMT_MLN),
            ("Валовая прибыль", "PL", "gp", FMT_MLN),
            ("EBITDA", "PL", "ebitda", FMT_MLN),
            ("EBIT", "PL", "ebit", FMT_MLN),
            ("Чистая прибыль", "PL", "ni", FMT_MLN),
        ]),
        ("2. БАЛАНС (BS)", [
            ("Итого активы", "BS", "ta", FMT_MLN),
            ("Денежные средства", "BS", "cash", FMT_MLN),
            ("ОС нетто", "BS", "ppe", FMT_MLN),
            ("Итого обязательства", "BS", "tl", FMT_MLN),
            ("Собственный капитал", "BS", "te", FMT_MLN),
            ("Контроль BS", "BS", "check", FMT_RATIO),
        ]),
        ("3. ДЕНЕЖНЫЕ ПОТОКИ (CF)", [
            ("CFO", "CF", "cfo", FMT_MLN),
            ("CFI", "CF", "cfi", FMT_MLN),
            ("CFF", "CF", "cff", FMT_MLN),
            ("ДС на конец", "CF", "cash_close", FMT_MLN),
        ]),
        ("4. КЛЮЧЕВЫЕ КОЭФФИЦИЕНТЫ", [
            ("ND/EBITDA", "RA", "nd_ebitda", FMT_MULT),
            ("ICR", "RA", "icr", FMT_MULT),
            ("EBITDA margin", "RA", "ebitda_margin", FMT_PCT),
            ("Net margin", "RA", "net_margin", FMT_PCT),
            ("ROE", "RA", "roe", FMT_PCT),
            ("Current ratio", "RA", "current", FMT_MULT),
        ]),
        ("5. PP&E CORKSCREW", [
            ("ОС нетто, начало", "PP", "net_open", FMT_MLN),
            ("CapEx", "PP", "capex", FMT_MLN),
            ("Амортизация", "PP", "dep_charge", FMT_MLN),
            ("ОС нетто, конец", "PP", "net_close", FMT_MLN),
        ]),
        ("6. ОБОРОТНЫЙ КАПИТАЛ", [
            ("DSO", "WC", "dso", FMT_DAYS),
            ("DIH", "WC", "dio", FMT_DAYS),
            ("DPO", "WC", "dpo", FMT_DAYS),
            ("NWC", "WC", "nwc", FMT_MLN),
            ("ΔNWC", "WC", "delta_nwc", FMT_MLN),
        ]),
        ("7. ДОЛГ", [
            ("Долг, итого", "DT", "close", FMT_MLN),
            ("Процентные расходы", "DT", "interest", FMT_MLN),
            ("ND/EBITDA", "DT", "nd_ebitda", FMT_MULT),
        ]),
        ("8. НАЛОГИ", [
            ("EBT", "TX", "ebt", FMT_MLN),
            ("Текущий налог", "TX", "current", FMT_MLN),
            ("Эффективная ставка", "TX", "eff_rate", FMT_PCT),
            ("NOL", "TX", "nol_close", FMT_MLN),
        ]),
        ("9. ДИВИДЕНДЫ", [
            ("Чистая прибыль", "EQ", "ni", FMT_MLN),
            ("Дивиденды", "EQ", "div", FMT_MLN),
            ("Payout", "EQ", "payout", FMT_PCT),
        ]),
        ("10. РЕЙТИНГ", [
            ("Итоговый балл", "SC", "final", FMT_RATIO1),
            ("Рейтинг", "SC", "rating", FMT_TEXT),
        ]),
        ("11. ОЦЕНКА", [
            ("WACC", "VL", "wacc", FMT_PCT),
            ("Enterprise Value", "VL", "ev", FMT_MLN),
            ("Equity Value", "VL", "eq_value", FMT_MLN),
        ]),
        ("12. ПРОВЕРКИ", [
            ("BS Check", "CK", "bs_check", FMT_RATIO),
            ("Ошибок всего", "CK", "error_count", FMT_INT),
        ]),
    ]

    for sec_title, items in sections:
        section_header(ws, r, sec_title); r += 1
        for label, code, key, fmt in items:
            label_row(ws, r, label)
            row_src = REG.get(f"{code}.{key}")
            if row_src:
                for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
                    cl = get_column_letter(c)
                    ref_cell(ws, r, c, f"='{NAME[code]}'!{cl}${row_src}", fmt)
            r += 1
        r += 1  # gap between sections


def build_changelog(wb, cfg):
    """Changelog — version history."""
    ws = wb["Changelog"]
    ws.cell(1, 1, "Changelog").font = F_TITLE
    ws.cell(3, 1, "Версия").font = F_LABEL_B
    ws.cell(3, 2, "Дата").font = F_LABEL_B
    ws.cell(3, 3, "Изменения").font = F_LABEL_B
    ws.cell(4, 1, "v4.0")
    ws.cell(4, 2, "2026-10-05")
    ws.cell(4, 3, "Начальная версия шаблона v4 (Excel-driven)")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN BUILD
# ══════════════════════════════════════════════════════════════════════════════

def build(company: str, output: str):
    """Build complete workbook."""
    if company not in COMPANY_CONFIGS:
        print(f"Unknown company: {company}. Available: {list(COMPANY_CONFIGS.keys())}")
        return

    cfg = COMPANY_CONFIGS[company]
    print(f"Building model for {cfg['name']}...")

    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    # Create all sheets
    for code, name, tab_color in SHEETS:
        ws = wb.create_sheet(name)
        ws.sheet_properties.tabColor = tab_color

    # Build each sheet
    builders = [
        ("00_Guide",        build_guide),
        ("00_Cover",        build_cover),
        ("Control_Panel",   build_control_panel),
        ("01_Macro",        build_macro),
        ("02_Hist",         build_hist),
        ("10_Revenue",      build_revenue),
        ("12_COGS",         build_cogs),
        ("13_SGA",          build_sga),
        ("15_PPE",          build_ppe),
        ("16_WC",           build_wc),
        ("19_Tax",          build_tax),
        ("20_BS",           build_bs),
        ("21_PL",           build_pl),
        ("23_CF",           build_cf),
        ("24_Equity",       build_equity),
        ("30_Ratios",       build_ratios),
        ("31_Score",        build_score),
        ("32_Covenants",    build_covenants),
        ("35_Valuation",    build_valuation),
        ("90_Checks",       build_checks),
        ("Model_Output",    build_model_output),
        ("Changelog",       build_changelog),
    ]
    for name, builder in builders:
        print(f"  {name}...")
        builder(wb, cfg)

    # Set metadata
    wb.properties.creator = "Vertex Corporate Model v4"
    wb.properties.title = f"Финансовая модель — {cfg['name']}"

    # Save
    output_path = BASE_DIR / output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(output_path))
    print(f"\n✓ Saved: {output_path}")
    print(f"  Sheets: {len(wb.sheetnames)}")
    print(f"  Company: {cfg['name']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Corporate Financial Model v4")
    parser.add_argument("--company", required=True, choices=["rusal", "nornickel"])
    parser.add_argument("--output", default="model/model_v4.xlsx")
    args = parser.parse_args()
    build(args.company, args.output)
