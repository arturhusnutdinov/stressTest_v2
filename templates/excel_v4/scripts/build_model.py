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
    ("DR", "05_Drivers",     TAB_INPUT),
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
    ("DS", "_Debt_Schedule",  TAB_ENGINE),  # Technical: per-instrument schedule (hidden)
    ("CL", "Changelog",      TAB_CTRL),
]

# Code → sheet name lookup
NAME = {code: name for code, name, _ in SHEETS}


def col_layout(cfg):
    """Return unified column layout: hist_cols + fc_cols indices.

    ALL sheets use same layout:
      C=2023, D=2024, E=2025, F=2026E, G=2027E, H=2028E

    Returns (hist_col_start, fc_col_start, hist_years_display, fc_years)
    """
    hist_yrs = cfg["hist_years"][-3:]  # last 3 history years
    fc_yrs = cfg["fc_years"]
    h_start = 3  # col C
    f_start = 3 + len(hist_yrs)  # col F (index 6)
    return h_start, f_start, hist_yrs, fc_yrs


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
        "macro_factors": ["LME Aluminium", "LME Alumina", "USD/RUB", "USD/CNY", "Brent", "CPI RU", "PPI RU"],
        "cogs_mode": "component",
        "cogs_components": {"material": 0.37, "energy": 0.27, "labour": 0.12, "other": 0.24},
        "debt_target_nd_ebitda": 3.5,
        "rc_limit": 2500,
        "rc_rate": 0.14,
        "commit_fee_rate": 0.005,
        "min_cash": 500,
        "cash_buffer": 200,
        "maint_share": 0.65,
        "refi_pct_bonds": 1.0,
        "refi_pct_bank": 1.0,
        "spread_base": 0.04,
        "spread_step": 0.005,
        "term_tenor": 5,
        # FX: revenue/cost currency split from IFRS Note 4 (2025)
        "rev_cny_share": 0.35,   # China = $5,176M / $14,812M = 34.9%
        "rev_rub_share": 0.26,   # Russia = $3,856M / $14,812M = 26.0%
        "cost_rub_share": 0.55,  # personnel + energy ~ 55% RUB-denominated
        "rating_ind_adj": -6.0,
        "rating_size_adj": 2.0,
        "rating_cycle_margin": 0.12,
        "covenants": {"nd_ebitda_max": 4.5, "icr_min": 1.5, "margin_min": 0.05},
        "nci_pct": 0.0,
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
        "rc_limit": 1500,
        "rc_rate": 0.10,
        "commit_fee_rate": 0.004,
        "min_cash": 500,
        "cash_buffer": 200,
        "maint_share": 0.60,
        "refi_pct_bonds": 1.0,
        "refi_pct_bank": 1.0,
        "spread_base": 0.03,
        "spread_step": 0.005,
        "term_tenor": 5,
        # FX: metals priced in USD globally, costs mostly RUB
        "rev_cny_share": 0.03,   # minimal CNY exposure
        "rev_rub_share": 0.05,   # ~5% domestic Russian sales
        "cost_rub_share": 0.65,  # bulk of costs in RUB (labor, energy, mining)
        "rating_ind_adj": -6.0,
        "rating_size_adj": 2.0,
        "rating_cycle_margin": 0.41,
        "covenants": {"nd_ebitda_max": 3.0, "icr_min": 3.0, "margin_min": 0.15},
        "nci_pct": 0.158,
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


    # ── Traffic light (C5): model health indicator ──
    r = 16
    section_header(ws, r, "СТАТУС МОДЕЛИ")
    r += 1
    label_row(ws, r, "Ошибки (из 90_Checks)", "")
    # Sum error counts across all forecast years
    fc_cols = [get_column_letter(3 + len(cfg["hist_years"][-3:]) + i)
               for i in range(len(cfg["fc_years"]))]
    err_refs = "+".join(f"'90_Checks'!{c}${REG['CK.error_count']}" for c in fc_cols)
    formula_cell(ws, r, 3, f"={err_refs}", FMT_INT)
    r += 1
    label_row(ws, r, "Статус", "")
    formula_cell(ws, r, 3,
                 f"=IF({get_column_letter(3)}{r-1}=0,\"✅ ОК\","
                 f"IF({get_column_letter(3)}{r-1}<=3,\"⚠ ПРЕДУПРЕЖДЕНИЯ\",\"❌ ОШИБКИ\"))",
                 FMT_TEXT, bold=True)
    r += 1
    label_row(ws, r, "Funding gap", "mln")
    fg_refs = "+".join(f"'{NAME['DT']}'!{c}${REG['DT.funding_gap']}" for c in fc_cols)
    formula_cell(ws, r, 3, f"={fg_refs}", FMT_MLN)
    r += 1
    label_row(ws, r, "calc_reset режим", "")
    formula_cell(ws, r, 3, "=IF(calc_reset=1,\"SEED (не финальный)\",\"ITERATE (финальный)\")", FMT_TEXT)


def build_macro(wb, cfg):
    """01_Macro — macro scenarios + econometric equations + CHOOSE."""
    ws = wb["01_Macro"]
    apply_col_widths(ws)

    ws.cell(1, 1, f"01_Macro — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "Макросценарии (3) + Active row + Эконометрика OLS").font = F_SUBTITLE

    n_hist = len(cfg["hist_years"][-3:])
    n_fc = len(cfg["fc_years"])
    fc_start = 3 + n_hist
    year_headers(ws, 4, cfg["hist_years"][-3:], cfg["fc_years"])

    factors = cfg["macro_factors"]
    n_f = len(factors)

    # ── Scenario blocks: 3 scenarios with same factor list ──
    scenario_names = ["Базовый", "Стресс", "Severe"]
    scenario_starts = {}  # factor_idx → (s1_row, s2_row, s3_row)

    # Shock multipliers: Stress = Base × (1+shock), Severe = Base × (1+severe_shock)
    # Commodities: -20%/-40%, FX: +15%/+30%, Rates: +2pp/+4pp
    commodity_factors = {"LME Aluminium", "LME Alumina", "LME Nickel", "LME Copper",
                         "LME Palladium", "LME Platinum", "Brent"}
    fx_factors = {"USD/RUB", "USD/CNY"}
    rate_factors = {"CPI RU", "PPI RU"}

    for s_idx, s_name in enumerate(scenario_names):
        s_base = 6 + s_idx * (n_f + 3)
        section_header(ws, s_base, f"Сценарий {s_idx+1}: {s_name}")
        for i, factor in enumerate(factors):
            r = s_base + 2 + i
            label_row(ws, r, factor)
            if s_idx == 0:
                # Base: input cells (fill_data writes web consensus)
                for c in range(fc_start, fc_start + n_fc):
                    input_cell(ws, r, c, 0, FMT_RATIO1)
                scenario_starts[i] = [r]
            else:
                # Stress/Severe: formulas from Base
                base_r = scenario_starts[i][0]
                for c in range(fc_start, fc_start + n_fc):
                    cl = get_column_letter(c)
                    if factor in commodity_factors:
                        shock = -0.20 if s_idx == 1 else -0.40
                        formula_cell(ws, r, c, f"={cl}{base_r}*(1+{shock})", FMT_RATIO1)
                    elif factor in fx_factors:
                        shock = 0.15 if s_idx == 1 else 0.30
                        formula_cell(ws, r, c, f"={cl}{base_r}*(1+{shock})", FMT_RATIO1)
                    elif factor in rate_factors:
                        shock = 0.02 if s_idx == 1 else 0.04
                        formula_cell(ws, r, c, f"={cl}{base_r}+{shock}", FMT_RATIO1)
                    else:
                        # Default: carry Base
                        formula_cell(ws, r, c, f"={cl}{base_r}", FMT_RATIO1)
                scenario_starts[i].append(r)

    # ── Active scenario: CHOOSE based on CP.C5 ──
    act_base = 6 + 3 * (n_f + 3) + 1
    section_header(ws, act_base, "АКТИВНЫЙ СЦЕНАРИЙ (CHOOSE по номеру из Control_Panel)")
    # Scenario selector ref
    cp_scen = "Control_Panel!$C$5"

    for i, factor in enumerate(factors):
        r_act = act_base + 2 + i
        label_row(ws, r_act, factor, "", "IF(CP!C5) по сценарию")
        s1, s2, s3 = scenario_starts[i]
        for c in range(fc_start, fc_start + n_fc):
            cl = get_column_letter(c)
            formula_cell(ws, r_act, c,
                         f"=IF({cp_scen}=1,{cl}{s1},IF({cp_scen}=2,{cl}{s2},{cl}{s3}))",
                         FMT_RATIO1)
        # Store active row for REG
        reg_key = REG.get(f"MA.act_{['kr','brent','lme1','lme2','fx','gdp','cpi','ppi'][i]}"
                          if i < 8 else None)

    # Store active scenario base row for other sheets
    REG["MA.act_base"] = act_base + 2

    # ── Econometric display: OLS Revenue ~ β × Δln(Factor) ──
    econ_base = act_base + n_f + 4
    section_header(ws, econ_base, "ЭКОНОМЕТРИКА: Revenue ~ β × Δln(Factor)")
    ws.cell(econ_base + 1, 1, "Результаты OLS из fill_data (β, R², α)").font = F_NOTE
    r_beta = econ_base + 2
    r_r2 = econ_base + 3
    r_alpha = econ_base + 4
    label_row(ws, r_beta, "β (эластичность)", "x", "fill_data computes from history")
    input_cell(ws, r_beta, 3, 1.0, FMT_RATIO)
    label_row(ws, r_r2, "R² (коэфф. детерминации)", "%")
    input_cell(ws, r_r2, 3, 0, FMT_PCT2)
    label_row(ws, r_alpha, "α (константа)", "x")
    input_cell(ws, r_alpha, 3, 0, FMT_RATIO)
    REG["MA.econ_beta"] = r_beta
    REG["MA.econ_r2"] = r_r2
    REG["MA.econ_alpha"] = r_alpha


def build_assump(wb, cfg):
    """03_Assump — preprocessing layer: EWA-calibrated ratios from history.

    Mirrors Python preprocessor/core.py logic:
    - Margin ratios: COGS/Rev, SGA/Rev → EWA summary
    - WC days: DSO, DIH, DPO → EWA
    - CapEx: capex_to_rev, dep_rate → EWA
    - All calibrated from 02_Hist data
    """
    ws = wb["03_Assump"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"03_Assump — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "Препроцессинг: калибровка параметров из истории (EWA + AR(1))").font = F_SUBTITLE

    hist = cfg["hist_years"][-3:]
    fc = cfg["fc_years"]
    year_headers(ws, 4, hist, fc)
    n_hist = len(hist)

    r = 6
    # ── SECTION 1: MARGIN RATIOS ──
    section_header(ws, r, "1. МАРЖИНАЛЬНЫЕ КОЭФФИЦИЕНТЫ (из 02_Hist)"); r += 1

    # For each ratio, compute per-year from history, then show EWA recommended
    ratio_defs = [
        ("COGS / Revenue", "PL", "cogs", "PL", "revenue", False, "COGS ratio"),
        ("SGA / Revenue", "PL", "sga", "PL", "revenue", False, "SGA ratio"),
        ("EBITDA margin", "PL", "ebitda", "PL", "revenue", True, "EBITDA margin"),
        ("Net margin", "PL", "ni", "PL", "revenue", True, "Net margin"),
    ]

    for label, num_code, num_key, den_code, den_key, signed, note in ratio_defs:
        label_row(ws, r, label, "%", note)
        num_r = REG.get(f"{num_code}.{num_key}")
        den_r = REG.get(f"{den_code}.{den_key}")
        if num_r and den_r:
            for i in range(n_hist):
                c = 3 + i
                cl = get_column_letter(c)
                num_ref = f"'{NAME[num_code]}'!{cl}${num_r}"
                den_ref = f"'{NAME[den_code]}'!{cl}${den_r}"
                if signed:
                    formula_cell(ws, r, c, f"=IFERROR({num_ref}/{den_ref},0)", FMT_PCT)
                else:
                    formula_cell(ws, r, c, f"=IFERROR(ABS({num_ref})/ABS({den_ref}),0)", FMT_PCT)
            # Forecast = EWA (simplified: average of last 3 history years as proxy for EWA)
            # Python: ewa with halflife=3 → approximately weighted average of recent years
            hist_cols = [get_column_letter(3 + i) for i in range(n_hist)]
            avg_formula = f"=AVERAGE({','.join(f'{c}{r}' for c in hist_cols)})"
            for i in range(len(fc)):
                formula_cell(ws, r, 3 + n_hist + i, avg_formula, FMT_PCT)
        r += 1

    r += 1
    # ── SECTION 2: WC DAYS ──
    section_header(ws, r, "2. ОБОРОТНЫЙ КАПИТАЛ (DSO / DIH / DPO)"); r += 1
    # DSO = AR / Rev × 365, DIH = INV / COGS × 365, DPO = AP / COGS × 365
    wc_defs = [
        ("DSO (дни)", "BS", "ar", "PL", "revenue"),
        ("DIH (дни)", "BS", "inv", "PL", "cogs"),
        ("DPO (дни)", "BS", "ap", "PL", "cogs"),
    ]
    for label, bs_code, bs_key, is_code, is_key in wc_defs:
        label_row(ws, r, label, "дни")
        bs_r = REG.get(f"{bs_code}.{bs_key}")
        is_r = REG.get(f"{is_code}.{is_key}")
        if bs_r and is_r:
            for i in range(n_hist):
                c = 3 + i
                cl = get_column_letter(c)
                formula_cell(ws, r, c,
                             f"=IFERROR(ABS('{NAME[bs_code]}'!{cl}${bs_r})"
                             f"/ABS('{NAME[is_code]}'!{cl}${is_r})*365,0)",
                             FMT_DAYS)
            # Forecast: carry forward EWA (average of 3 hist)
            hist_cols = [get_column_letter(3 + i) for i in range(n_hist)]
            avg_f = f"=ROUND(AVERAGE({','.join(f'{c}{r}' for c in hist_cols)}),0)"
            for i in range(len(fc)):
                formula_cell(ws, r, 3 + n_hist + i, avg_f, FMT_DAYS)
        r += 1

    r += 1
    # ── SECTION 3: CAPEX / DA ──
    section_header(ws, r, "3. КАПИТАЛЬНЫЕ ЗАТРАТЫ И АМОРТИЗАЦИЯ"); r += 1
    capex_defs = [
        ("CapEx / Revenue", "CF", "capex", "PL", "revenue"),
        ("DA / PPE_net (dep rate)", "PL", "da", "BS", "ppe"),
        ("CapEx / DA (sustaining)", "CF", "capex", "PL", "da"),
    ]
    for label, num_code, num_key, den_code, den_key in capex_defs:
        label_row(ws, r, label, "%")
        num_r = REG.get(f"{num_code}.{num_key}")
        den_r = REG.get(f"{den_code}.{den_key}")
        if num_r and den_r:
            for i in range(n_hist):
                c = 3 + i
                cl = get_column_letter(c)
                formula_cell(ws, r, c,
                             f"=IFERROR(ABS('{NAME[num_code]}'!{cl}${num_r})"
                             f"/ABS('{NAME[den_code]}'!{cl}${den_r}),0)",
                             FMT_PCT)
            hist_cols = [get_column_letter(3 + i) for i in range(n_hist)]
            avg_f = f"=AVERAGE({','.join(f'{c}{r}' for c in hist_cols)})"
            for i in range(len(fc)):
                formula_cell(ws, r, 3 + n_hist + i, avg_f, FMT_PCT)
        r += 1

    r += 1
    # ── SECTION 4: DEBT ──
    section_header(ws, r, "4. ДОЛГ"); r += 1
    label_row(ws, r, "Implied Interest Rate")
    for i in range(n_hist):
        c = 3 + i
        cl = get_column_letter(c)
        formula_cell(ws, r, c,
                     f"=IFERROR(ABS('{NAME['PL']}'!{cl}${REG['PL.interest']})"
                     f"/(('{NAME['BS']}'!{cl}${REG['BS.st_debt']}+'{NAME['BS']}'!{cl}${REG['BS.lt_debt']})),0)",
                     FMT_PCT)
    r += 1
    label_row(ws, r, "ND / EBITDA")
    for i in range(n_hist):
        c = 3 + i
        cl = get_column_letter(c)
        st = f"'{NAME['BS']}'!{cl}${REG['BS.st_debt']}"
        lt = f"'{NAME['BS']}'!{cl}${REG['BS.lt_debt']}"
        cash_ref = f"'{NAME['BS']}'!{cl}${REG['BS.cash']}"
        ebitda_ref = f"'{NAME['PL']}'!{cl}${REG['PL.ebitda']}"
        formula_cell(ws, r, c, f"=IFERROR(({st}+{lt}-{cash_ref})/{ebitda_ref},0)", FMT_MULT)
    r += 1

    r += 1
    # ── SECTION 5: TAX ──
    section_header(ws, r, "5. НАЛОГИ"); r += 1
    label_row(ws, r, "Effective Tax Rate")
    for i in range(n_hist):
        c = 3 + i
        cl = get_column_letter(c)
        formula_cell(ws, r, c,
                     f"=IFERROR(ABS('{NAME['PL']}'!{cl}${REG['PL.tax']})"
                     f"/ABS('{NAME['PL']}'!{cl}${REG['PL.ebt']}),0)", FMT_PCT)
    r += 1

    r += 1
    # ── SECTION 6: FORECAST SUMMARY ──
    section_header(ws, r, "6. ПРОГНОЗНЫЕ ПРЕДПОЛОЖЕНИЯ (СВОДКА)"); r += 1
    year_headers(ws, r, hist, fc); r += 1
    summary_items = [
        ("Revenue growth", "RV", "rev_growth", FMT_PCT),
        ("COGS ratio", "CG", "ratio", FMT_PCT),
        ("SGA ratio", "SA", "sga_ratio", FMT_PCT),
        ("EBITDA margin", "PL", "ebitda_margin", FMT_PCT),
        ("CapEx / Revenue", "PP", "capex_rev", FMT_PCT),
        ("DA rate", "PP", "da_rate", FMT_PCT),
        ("ND/EBITDA", "DT", "nd_ebitda", FMT_MULT),
        ("Interest rate", "DT", "avg_rate", FMT_PCT),
        ("Tax rate (effective)", "TX", "eff_rate", FMT_PCT),
        ("Payout ratio", "EQ", "payout", FMT_PCT),
    ]
    for label, code, key, fmt in summary_items:
        label_row(ws, r, label)
        row_src = REG.get(f"{code}.{key}")
        if row_src:
            for c in range(3 + n_hist, 3 + n_hist + len(fc)):
                cl = get_column_letter(c)
                ref_cell(ws, r, c, f"='{NAME[code]}'!{cl}${row_src}", fmt)
        r += 1

    # Margins / COGS — use REG for CP rows (not hardcoded)
    section_header(ws, r, "СЕБЕСТОИМОСТЬ"); r += 1
    label_row(ws, r, "COGS ratio")
    cp_cr = REG.get("CP.cogs_ratio")
    if cp_cr:
        ref_cell(ws, r, 3, f"='Control_Panel'!$C${cp_cr}", FMT_PCT)
    r += 1
    if cfg.get("cogs_mode") == "component":
        for comp in cfg.get("cogs_components", {}):
            label_row(ws, r, f"Доля {comp.title()}")
            cp_comp = REG.get(f"CP.cogs_{comp}")
            if cp_comp:
                ref_cell(ws, r, 3, f"='Control_Panel'!$C${cp_comp}", FMT_PCT)
            r += 1
    r += 1

    # PP&E — use REG
    section_header(ws, r, "ОСНОВНЫЕ СРЕДСТВА"); r += 1
    for label, key in [("DA rate", "CP.da_rate"), ("Sustaining CapEx / DA", "CP.sustaining_ratio"),
                        ("Expansion CapEx", "CP.expansion_pct")]:
        label_row(ws, r, label)
        cp_r = REG.get(key)
        if cp_r:
            ref_cell(ws, r, 3, f"='Control_Panel'!$C${cp_r}", FMT_PCT if "%" in label or "rate" in label else FMT_RATIO)
        r += 1
    r += 1

    # WC
    section_header(ws, r, "ОБОРОТНЫЙ КАПИТАЛ"); r += 1
    wc_cp_keys = {"DSO": "CP.wc_dso", "DIH": "CP.wc_dio", "DPO": "CP.wc_dpo"}
    for d in ["DSO (дни)", "DIH (дни)", "DPO (дни)"]:
        label_row(ws, r, d)
        cp_wc = REG.get(wc_cp_keys.get(d[:3], ""), 50)
        ref_cell(ws, r, 3, f"='Control_Panel'!$C${cp_wc}", FMT_DAYS)
        r += 1
    r += 1

    # Debt
    section_header(ws, r, "ДОЛГ"); r += 1
    for label in ["Target ND/EBITDA", "Min cash", "Max prepay (% FCF)"]:
        label_row(ws, r, label)
        r += 1
    r += 1

    # Tax
    section_header(ws, r, "НАЛОГИ"); r += 1
    for label in ["Statutory rate", "NOL opening", "NOL max utilization"]:
        label_row(ws, r, label)
        r += 1
    r += 1

    # Dividends
    section_header(ws, r, "ДИВИДЕНДЫ"); r += 1
    for label in ["Payout ratio", "Buyback (% FCF)"]:
        label_row(ws, r, label)
        r += 1
    r += 1

    # Forecast schedule summary (years as columns)
    section_header(ws, r, "ПРОГНОЗНЫЕ ПРЕДПОЛОЖЕНИЯ ПО ГОДАМ"); r += 1
    year_headers(ws, r, [], fc); r += 1
    summary_items = [
        ("Revenue growth", "RV", "rev_growth", FMT_PCT),
        ("COGS ratio", "CG", "ratio", FMT_PCT),
        ("SGA ratio", "SA", "sga_ratio", FMT_PCT),
        ("EBITDA margin", "PL", "ebitda_margin", FMT_PCT),
        ("CapEx / Revenue", "PP", "capex_rev", FMT_PCT),
        ("DA rate", "PP", "da_rate", FMT_PCT),
        ("ND/EBITDA", "DT", "nd_ebitda", FMT_MULT),
        ("Interest rate", "DT", "avg_rate", FMT_PCT),
        ("Tax rate (effective)", "TX", "eff_rate", FMT_PCT),
        ("Payout ratio", "EQ", "payout", FMT_PCT),
    ]
    for label, code, key, fmt in summary_items:
        label_row(ws, r, label)
        row_src = REG.get(f"{code}.{key}")
        if row_src:
            for i, yr in enumerate(fc):
                c = 7 + i
                cl = get_column_letter(c)
                ref_cell(ws, r, c, f"='{NAME[code]}'!{cl}${row_src}", fmt)
        r += 1


def build_raw_ifrs(wb, cfg):
    """Raw_IFRS — template for detailed IFRS data (167+ keys)."""
    ws = wb["Raw_IFRS"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"Raw_IFRS — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "Детальные данные из раскрытий МСФО (заполняется вручную из нот)").font = F_SUBTITLE

    year_headers(ws, 4, cfg["hist_years"][-4:], [])

    r = 6
    sections = {
        "BS — ДЕТАЛИ": [
            "ppe_gross", "ppe_accum_dep", "ppe_net",
            "ppe_land", "ppe_buildings", "ppe_machinery", "ppe_construction_in_progress",
            "goodwill", "intangibles_gross", "intangibles_accum_amort",
            "investments_in_associates", "other_investments",
            "dta_nol", "dta_provisions", "dta_other",
            "dtl_ppe", "dtl_inventory", "dtl_other",
            "provisions_pension", "provisions_restoration", "provisions_legal",
        ],
        "IS — ДЕТАЛИ": [
            "revenue_segment_1", "revenue_segment_2", "revenue_segment_3",
            "cogs_materials", "cogs_energy", "cogs_labour", "cogs_transport",
            "dep_ppe", "dep_rou", "amort_intangibles",
            "current_tax", "deferred_tax",
            "interest_expense_debt", "interest_expense_lease", "interest_income",
        ],
        "CF — ДЕТАЛИ": [
            "cfo_net_income", "cfo_da", "cfo_deferred_tax", "cfo_wc_change",
            "cfo_interest_paid", "cfo_tax_paid",
            "capex", "disposal_proceeds",
            "debt_issuance", "debt_repayment", "dividends_paid",
            "lease_payments_principal",
        ],
        "CAPITAL — ДЕТАЛИ": [
            "shares_outstanding_mln", "share_price_usd",
            "market_cap", "book_value_per_share",
            "dividends_per_share",
        ],
    }

    for section_name, keys in sections.items():
        section_header(ws, r, section_name); r += 1
        for key in keys:
            label_row(ws, r, key, "mln")
            for c in range(3, 3 + len(cfg["hist_years"][-4:])):
                input_cell(ws, r, c, None, FMT_MLN)
            r += 1
        r += 1

    # ── ДОЛГОВОЙ ПОРТФЕЛЬ — ИНСТРУМЕНТЫ ──
    max_inst = 20
    section_header(ws, r, "ДОЛГОВОЙ ПОРТФЕЛЬ — ИНСТРУМЕНТЫ"); r += 1
    debt_headers = ["Инструмент", "Kind", "CCY", "Balance (mln)", "Rate", "Maturity"]
    for j, h in enumerate(debt_headers):
        ws.cell(r, 1 + j, h).font = F_YEAR
    REG["RI.debt_header_row"] = r; r += 1
    REG["RI.debt_start_row"] = r
    for i in range(max_inst + 1):
        for col_idx, fmt in [(1, "General"), (2, "General"), (3, "General"),
                              (4, FMT_MLN), (5, FMT_PCT2), (6, "General")]:
            c = ws.cell(r + i, col_idx)
            c.font = F_INPUT
            c.number_format = fmt
    REG["RI.debt_end_row"] = r + max_inst
    REG["RI.debt_other_row"] = r + max_inst
    REG["RI.debt_count"] = max_inst
    r += max_inst + 2

    section_header(ws, r, "СТАВКА ЦБ (прогноз)"); r += 1
    label_row(ws, r, "KeyRate forecast", "%")
    REG["RI.kr_row"] = r
    for c_idx, yr in enumerate(cfg["fc_years"]):
        ws.cell(r, 7 + c_idx, yr).font = F_YEAR
        input_cell(ws, r, 7 + c_idx, 0.12, FMT_PCT)
    r += 2


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
        ("other_cl", "Прочие кратк. обяз.", "mln"),
        ("other_ncl", "Прочие долг. обяз.", "mln"),
        ("dtl", "Отложенное нал. обяз.", "mln"),
        ("tl", "Итого обязательства", "mln"),
        ("equity", "Собственный капитал", "mln"),
        ("re", "Нераспр. прибыль", "mln"),
        ("sc", "Уставный капитал", "mln"),
        ("apic", "Добавочный капитал", "mln"),
        ("aoci", "Прочий совокупный доход", "mln"),
        ("other_ca", "Прочие оборотные активы", "mln"),
        ("other_nca", "Прочие внеоборотные", "mln"),
        ("tax_pay", "Налоги к уплате", "mln"),
        ("tca", "Итого оборотные активы", "mln"),
        ("tnca", "Итого внеоборотные активы", "mln"),
        ("tcl", "Итого краткосрочные обяз.", "mln"),
        ("tncl", "Итого долгосрочные обяз.", "mln"),
        ("other_opex", "Прочие опер. расходы (IS)", "mln"),
        ("impairment", "Обесценение (IS)", "mln"),
    ]
    # Assign missing HI rows dynamically
    hi_next = max((v for k, v in REG.items() if k.startswith("HI.")), default=58) + 1
    for key, label, unit in bs_rows:
        r = REG.get(f"HI.{key}")
        if r is None:
            r = hi_next
            REG[f"HI.{key}"] = r
            hi_next += 1
        label_row(ws, r, label, unit)
        for c in range(3, 3 + len(cfg["hist_years"])):
            input_cell(ws, r, c, 0, FMT_MLN)

    # TCA/TNCA/TA as formulas (not source values — ensures self-consistency)
    n_hist_full = len(cfg["hist_years"])
    hi_tca = REG.get("HI.tca")
    hi_tnca = REG.get("HI.tnca")
    hi_ta = REG.get("HI.ta")
    if hi_tca and hi_tnca and hi_ta:
        ca_keys = ["cash", "ar", "inv", "other_ca"]
        nca_keys = ["ppe_net", "rou", "goodwill", "intang", "dta", "other_nca"]
        for c in range(3, 3 + n_hist_full):
            cl = get_column_letter(c)
            ca_sum = "+".join(f"ABS({cl}{REG.get(f'HI.{k}', 99)})" for k in ca_keys if REG.get(f"HI.{k}"))
            nca_sum = "+".join(f"ABS({cl}{REG.get(f'HI.{k}', 99)})" for k in nca_keys if REG.get(f"HI.{k}"))
            if ca_sum:
                formula_cell(ws, hi_tca, c, f"={ca_sum}", FMT_MLN)
            if nca_sum:
                formula_cell(ws, hi_tnca, c, f"={nca_sum}", FMT_MLN)
            formula_cell(ws, hi_ta, c, f"={cl}{hi_tca}+{cl}{hi_tnca}", FMT_MLN)

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


def build_drivers(wb, cfg):
    """05_Drivers — operating drivers: volumes, unit costs, associates, FX."""
    ws = wb["05_Drivers"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"05_Drivers — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "Операционные драйверы модели (volume, cost, FX)").font = F_SUBTITLE

    n_hist = len(cfg["hist_years"][-3:])
    year_headers(ws, 4, cfg["hist_years"][-3:], cfg["fc_years"])

    r = 6
    # ── A. VOLUME DRIVERS ──
    section_header(ws, r, "A. ОБЪЁМЫ ПРОИЗВОДСТВА И ПРОДАЖ"); r += 1
    for i, seg in enumerate(cfg["segments"]):
        key = seg["key"]
        label_row(ws, r, f"{seg['name']}: рост объёма (%)", "%")
        REG[f"DR.{key}_vol_growth"] = r
        # History: compute from 11_Segments
        sg_vol = REG.get(f"SG.{key}_vol")
        if sg_vol:
            for c in range(4, 3 + n_hist):  # start from 2nd year
                cl = get_column_letter(c)
                prev = get_column_letter(c - 1)
                formula_cell(ws, r, c,
                             f"=IFERROR('{NAME['SG']}'!{cl}${sg_vol}/'{NAME['SG']}'!{prev}${sg_vol}-1,0)",
                             FMT_PCT)
        # Forecast: input (carry-forward from CP or manual)
        for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
            prev = get_column_letter(c - 1)
            input_cell(ws, r, c, 0, FMT_PCT)  # default 0% growth
        r += 1

    label_row(ws, r, "Capacity utilisation proxy", "%")
    REG["DR.capacity_util"] = r
    for c in range(3, 3 + n_hist + len(cfg["fc_years"])):
        input_cell(ws, r, c, 0.95, FMT_PCT)
    r += 2

    # ── B. COST DRIVERS (indexation) ──
    section_header(ws, r, "B. ИНДЕКСАЦИЯ УДЕЛЬНЫХ ЗАТРАТ"); r += 1
    cost_drivers = [
        ("energy_idx", "Индекс энергозатрат (Power price, YoY)", "PPI"),
        ("labour_idx", "Индекс трудозатрат (CPI, YoY)", "CPI"),
        ("transport_idx", "Индекс транспорта (PPI, YoY)", "PPI"),
    ]
    # Link to 01_Macro CPI/PPI
    act_base = REG.get("MA.act_base", 39)
    # Find CPI/PPI rows by name in macro_factors (not by fixed offset)
    factors_list = cfg.get("macro_factors", [])
    cpi_offset = next((i for i, f in enumerate(factors_list) if "CPI" in f.upper()), len(factors_list) - 2)
    ppi_offset = next((i for i, f in enumerate(factors_list) if "PPI" in f.upper()), len(factors_list) - 1)

    for drv_key, label, macro_type in cost_drivers:
        label_row(ws, r, label, "%")
        REG[f"DR.{drv_key}"] = r
        for c in range(3, 3 + n_hist):
            input_cell(ws, r, c, 0, FMT_PCT)
        # Forecast: CPI/PPI from active scenario by name
        macro_row = act_base + cpi_offset if macro_type == "CPI" else act_base + ppi_offset
        for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
            cl = get_column_letter(c)
            formula_cell(ws, r, c,
                         f"='{NAME['MA']}'!{cl}${macro_row}", FMT_PCT)
        r += 1
    # FX change row: Δ USD/RUB YoY (for cost conversion to USD)
    label_row(ws, r, "Δ USD/RUB, YoY", "%", "Cost FX adjustment")
    REG["DR.fx_usdrub_chg"] = r
    # USD/RUB active scenario row
    act_base = REG.get("MA.act_base", 39)
    usdrub_row = act_base  # first factor after act_base is usually LME Al, 3rd is USD/RUB
    # Find USD/RUB row in macro factors
    for fi, f in enumerate(cfg.get("macro_factors", [])):
        if "usd" in f.lower() and "rub" in f.lower():
            usdrub_row = act_base + fi
            break
    # For first forecast year: use last non-empty hist col as anchor
    # IF E38 empty, try D38, then C38 — handles missing 2025 data
    first_fc_col = 3 + n_hist
    cl_fc1 = get_column_letter(first_fc_col)
    # Build anchor: last available value before forecast
    anchor_parts = []
    for hc in range(3 + n_hist - 1, 2, -1):
        anchor_parts.append(f"'{NAME['MA']}'!{get_column_letter(hc)}${usdrub_row}")
    anchor = anchor_parts[0]  # E38
    if len(anchor_parts) > 1:
        # Use fallback chain: IF(E38>0, E38, IF(D38>0, D38, C38))
        anchor = anchor_parts[-1]
        for a in reversed(anchor_parts[:-1]):
            anchor = f"IF({a}>0,{a},{anchor})"
    formula_cell(ws, r, first_fc_col,
                 f"=IFERROR('{NAME['MA']}'!{cl_fc1}${usdrub_row}/{anchor}-1,0)",
                 FMT_PCT)
    # Subsequent years: simple YoY
    for c in range(first_fc_col + 1, first_fc_col + len(cfg["fc_years"])):
        cl = get_column_letter(c)
        prev_cl = get_column_letter(c - 1)
        formula_cell(ws, r, c,
                     f"=IFERROR('{NAME['MA']}'!{cl}${usdrub_row}/'{NAME['MA']}'!{prev_cl}${usdrub_row}-1,0)",
                     FMT_PCT)
    r += 1

    # RUB cost share
    label_row(ws, r, "Доля затрат в RUB", "%")
    REG["DR.rub_cost_share"] = r
    cp_cost_rub = REG.get("CP.cost_rub_share")
    for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        if cp_cost_rub:
            ref_cell(ws, r, c, f"='Control_Panel'!$C${cp_cost_rub}", FMT_PCT)
        else:
            input_cell(ws, r, c, 0.55, FMT_PCT)
    r += 1

    # Δ USD/CNY YoY
    label_row(ws, r, "Δ USD/CNY, YoY", "%")
    REG["DR.fx_usdcny_chg"] = r
    # Find USD/CNY row in macro
    usdcny_row = None
    for fi, f in enumerate(cfg.get("macro_factors", [])):
        if "cny" in f.lower():
            usdcny_row = act_base + fi
            break
    if usdcny_row:
        first_fc_col_c = 3 + n_hist
        cl_fc1_c = get_column_letter(first_fc_col_c)
        anchor_cny = f"IF('{NAME['MA']}'!{get_column_letter(first_fc_col_c-1)}${usdcny_row}>0," \
                     f"'{NAME['MA']}'!{get_column_letter(first_fc_col_c-1)}${usdcny_row}," \
                     f"'{NAME['MA']}'!{get_column_letter(first_fc_col_c-2)}${usdcny_row})"
        formula_cell(ws, r, first_fc_col_c,
                     f"=IFERROR('{NAME['MA']}'!{cl_fc1_c}${usdcny_row}/{anchor_cny}-1,0)", FMT_PCT)
        for c in range(first_fc_col_c + 1, first_fc_col_c + len(cfg["fc_years"])):
            cl = get_column_letter(c)
            prev_cl = get_column_letter(c - 1)
            formula_cell(ws, r, c,
                         f"=IFERROR('{NAME['MA']}'!{cl}${usdcny_row}/'{NAME['MA']}'!{prev_cl}${usdcny_row}-1,0)", FMT_PCT)
    r += 2

    # ── C. COMMODITY CHAIN ──
    section_header(ws, r, "C. ТОВАРНАЯ ЦЕПОЧКА (цена → выручка)"); r += 1
    for i, seg in enumerate(cfg["segments"]):
        if i >= 2:  # only commodity segments
            continue
        key = seg["key"]
        label_row(ws, r, f"{seg['name']}: Δ цены к базовому сценарию", "%")
        REG[f"DR.{key}_price_delta"] = r
        for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
            cl = get_column_letter(c)
            prev = get_column_letter(c - 1)
            # Delta = (macro_price - prev_macro_price) / prev_macro_price
            sg_price = REG.get(f"SG.{key}_price")
            if sg_price:
                formula_cell(ws, r, c,
                             f"=IFERROR('{NAME['SG']}'!{cl}${sg_price}/'{NAME['SG']}'!{prev}${sg_price}-1,0)",
                             FMT_PCT)
        r += 1
    r += 1

    # ── D. ASSOCIATES ──
    section_header(ws, r, "D. ДОЛЯ В АССОЦИИРОВАННЫХ"); r += 1
    label_row(ws, r, "Income from associates (carry-forward)", "mln")
    REG["DR.associates"] = r
    oi_assoc = REG.get("OI.associates")
    if oi_assoc:
        for c in range(3, 3 + n_hist + len(cfg["fc_years"])):
            cl = get_column_letter(c)
            ref_cell(ws, r, c, f"='{NAME['OI']}'!{cl}${oi_assoc}", FMT_MLN)
    r += 1

    label_row(ws, r, "Interest income", "mln")
    REG["DR.interest_income"] = r
    oi_int = REG.get("OI.interest_income")
    if oi_int:
        for c in range(3, 3 + n_hist + len(cfg["fc_years"])):
            cl = get_column_letter(c)
            ref_cell(ws, r, c, f"='{NAME['OI']}'!{cl}${oi_int}", FMT_MLN)
    r += 2

    # ── E. FX EXPOSURE ──
    section_header(ws, r, "E. ВАЛЮТНАЯ ЭКСПОЗИЦИЯ"); r += 1
    # CNY share from instruments
    ri_s = REG.get("RI.debt_start_row", 69)
    ri_e = REG.get("RI.debt_end_row", 89)
    label_row(ws, r, "Доля CNY в долге (из Raw_IFRS)", "%")
    REG["DR.cny_share"] = r
    formula_cell(ws, r, 3,
                 f"=IFERROR(SUMPRODUCT('{NAME['RI']}'!D${ri_s}:D${ri_e},"
                 f"('{NAME['RI']}'!C${ri_s}:C${ri_e}=\"CNY\")*1)"
                 f"/SUM('{NAME['RI']}'!D${ri_s}:D${ri_e}),0)",
                 FMT_PCT)
    r += 1

    label_row(ws, r, "Доля RUB в долге", "%")
    REG["DR.rub_share"] = r
    formula_cell(ws, r, 3,
                 f"=IFERROR(SUMPRODUCT('{NAME['RI']}'!D${ri_s}:D${ri_e},"
                 f"('{NAME['RI']}'!C${ri_s}:C${ri_e}=\"RUB\")*1)"
                 f"/SUM('{NAME['RI']}'!D${ri_s}:D${ri_e}),0)",
                 FMT_PCT)
    r += 1

    label_row(ws, r, "FX impact on debt (mln)", "mln")
    REG["DR.fx_impact"] = r
    for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c)
        ref_cell(ws, r, c, f"='{NAME['DT']}'!{cl}${REG['DT.fx_reval']}", FMT_MLN)
    r += 2

    # ── F. CAPEX PROJECTS ──
    section_header(ws, r, "F. ПРОЕКТЫ CAPEX (дополнительно к базовому CapEx из 15_PPE)"); r += 1
    for j in range(3):
        label_row(ws, r, f"Проект {j+1}: название", "")
        REG[f"DR.capex_proj{j+1}_name"] = r
        input_cell(ws, r, 1, "", "General")
        r += 1
        label_row(ws, r, f"Проект {j+1}: CapEx (mln)", "mln")
        REG[f"DR.capex_proj{j+1}"] = r
        for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
            input_cell(ws, r, c, 0, FMT_MLN)
        r += 1
    # Total project CapEx
    label_row(ws, r, "ИТОГО проектный CapEx", "mln")
    REG["DR.capex_projects_total"] = r
    for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c)
        proj_parts = "+".join(f"{cl}{REG[f'DR.capex_proj{j+1}']}" for j in range(3))
        formula_cell(ws, r, c, f"={proj_parts}", FMT_MLN, bold=True)
    r += 2

    # ── G. OVERRIDES (переопределения любого прогноза) ──
    section_header(ws, r, "F. ПЕРЕОПРЕДЕЛЕНИЯ (аналитик заполняет для ручной корректировки)"); r += 1
    ws.cell(r, 1, "Если ячейка ≠ 0, модель использует override вместо формулы").font = F_NOTE
    r += 1
    overrides = [
        ("ovr_revenue", "Override Revenue (mln)", "mln"),
        ("ovr_ebitda", "Override EBITDA (mln)", "mln"),
        ("ovr_capex", "Override CapEx (mln)", "mln"),
        ("ovr_div", "Override Dividends (mln)", "mln"),
        ("ovr_tax_rate", "Override Tax rate (%)", "%"),
    ]
    for key, label, unit in overrides:
        label_row(ws, r, label, unit)
        REG[f"DR.{key}"] = r
        for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
            input_cell(ws, r, c, 0, FMT_MLN if unit == "mln" else FMT_PCT)
        r += 1
    r += 1

    # ── G. SUMMARY (ключевые показатели для быстрого контроля) ──
    section_header(ws, r, "G. СВОДКА КЛЮЧЕВЫХ ПОКАЗАТЕЛЕЙ"); r += 1
    summary_items = [
        ("Revenue", f"'{NAME['PL']}'", REG.get("PL.revenue"), FMT_MLN),
        ("EBITDA", f"'{NAME['PL']}'", REG.get("PL.ebitda"), FMT_MLN),
        ("NI", f"'{NAME['PL']}'", REG.get("PL.ni"), FMT_MLN),
        ("Cash", f"'{NAME['BS']}'", REG.get("BS.cash"), FMT_MLN),
        ("Total Debt", f"'{NAME['DT']}'", REG.get("DT.close"), FMT_MLN),
        ("ND/EBITDA", f"'{NAME['DT']}'", REG.get("DT.nd_ebitda"), FMT_MULT),
        ("Avg Rate", f"'{NAME['DT']}'", REG.get("DT.avg_rate"), FMT_PCT),
    ]
    for label, sheet_ref, row, fmt in summary_items:
        label_row(ws, r, label)
        if row:
            for c in range(3, 3 + n_hist + len(cfg["fc_years"])):
                cl = get_column_letter(c)
                ref_cell(ws, r, c, f"={sheet_ref}!{cl}${row}", fmt)
        r += 1


def build_segments(wb, cfg):
    """11_Segments — operational data structure (filled by fill_data)."""
    ws = wb["11_Segments"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"11_Segments — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "Операционные показатели по сегментам (history + forecast)").font = F_SUBTITLE

    n_hist = len(cfg["hist_years"][-3:])
    year_headers(ws, 4, cfg["hist_years"][-3:], cfg["fc_years"])

    r = 6
    for i, seg in enumerate(cfg["segments"]):
        key = seg["key"]
        section_header(ws, r, f"{seg['name']} (driver: {seg['driver']})")
        r += 1
        # Volume
        label_row(ws, r, "Объём продаж", "kt")
        REG[f"SG.{key}_vol"] = r
        for c in range(3, 3 + n_hist):
            input_cell(ws, r, c, 0, FMT_INT)
        # Forecast: volume = prev × (1 + growth from 05_Drivers)
        dr_growth = REG.get(f"DR.{key}_vol_growth")
        for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
            prev = get_column_letter(c - 1)
            cl = get_column_letter(c)
            if dr_growth:
                formula_cell(ws, r, c,
                             f"={prev}{r}*(1+'{NAME['DR']}'!{cl}${dr_growth})", FMT_INT)
            else:
                formula_cell(ws, r, c, f"={prev}{r}", FMT_INT)
        r += 1
        # Price
        label_row(ws, r, "Средняя цена реализации", "$/t")
        REG[f"SG.{key}_price"] = r
        for c in range(3, 3 + n_hist):
            input_cell(ws, r, c, 0, FMT_INT)
        # Forecast: from 01_Macro if segment has commodity driver, else carry-forward
        act_base = REG.get("MA.act_base", 36)
        has_driver = i < len(cfg.get("macro_factors", [])) - 2  # first N-2 factors are segment drivers
        # Only seg1 and seg2 have commodity price drivers; seg3+ = carry-forward
        for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
            cl = get_column_letter(c)
            prev = get_column_letter(c - 1)
            if i < 2:  # seg1, seg2: macro price driver
                formula_cell(ws, r, c,
                             f"='{NAME['MA']}'!{cl}${act_base + i}", FMT_INT)
            else:  # seg3+: carry-forward (no commodity driver)
                formula_cell(ws, r, c, f"={prev}{r}", FMT_INT)
        r += 1
        # Revenue
        label_row(ws, r, "Выручка сегмента", "mln")
        REG[f"SG.{key}_rev"] = r
        for c in range(3, 3 + n_hist + len(cfg["fc_years"])):
            cl = get_column_letter(c)
            formula_cell(ws, r, c,
                         f"={cl}{REG[f'SG.{key}_vol']}*{cl}{REG[f'SG.{key}_price']}/1000",
                         FMT_MLN, bold=True)
        r += 2


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

        # History: reference 11_Segments (single source)
        n_hist = len(cfg["hist_years"][-3:])
        sg_vol = REG.get(f"SG.{key}_vol")
        sg_price = REG.get(f"SG.{key}_price")
        for c in range(3, 3 + n_hist):
            col_l = get_column_letter(c)
            if sg_vol:
                ref_cell(ws, base_r, c,
                         f"='{NAME['SG']}'!{col_l}${sg_vol}", FMT_INT)
            else:
                input_cell(ws, base_r, c, 0, FMT_INT)
            if sg_price:
                ref_cell(ws, base_r + 1, c,
                         f"='{NAME['SG']}'!{col_l}${sg_price}", FMT_INT)
            else:
                input_cell(ws, base_r + 1, c, 0, FMT_INT)
            # revenue = vol × price / 1e6 (kt × $/t → $mln)
            formula_cell(ws, base_r + 2, c,
                         f"={col_l}{base_r}*{col_l}{base_r+1}/1000", FMT_MLN, bold=True)

        # Forecast: volume = EWA (carry forward), price = OLS chain-link or EWA
        for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
            col_l = get_column_letter(c)
            prev_col = get_column_letter(c - 1)

            # Volume forecast: EWA carry-forward from last history
            # Python: val × exp(ewa_growth) — simplified to carry forward
            formula_cell(ws, base_r, c, f"={prev_col}{base_r}", FMT_INT)

            # Price forecast: from 01_Macro active scenario row
            # seg["driver"] maps to macro factor → active row
            # Active scenario rows start at REG.get("MA.act_base", 36)
            act_base = REG.get("MA.act_base", 36)
            seg_idx = cfg["segments"].index(seg)
            # Price: macro driver for seg1/seg2, carry-forward for seg3+
            if seg_idx < 2:
                macro_price_row = act_base + seg_idx
                formula_cell(ws, base_r + 1, c,
                             f"='{NAME['MA']}'!{col_l}${macro_price_row}", FMT_INT)
            else:
                formula_cell(ws, base_r + 1, c,
                             f"={prev_col}{base_r + 1}", FMT_INT)

            # Revenue = vol × price / 1000
            formula_cell(ws, base_r + 2, c,
                         f"={col_l}{base_r}*{col_l}{base_r+1}/1000", FMT_MLN, bold=True)

    # Reconciliation = reported revenue - Σ segments
    r_recon = REG.get("RV.recon", 19)
    label_row(ws, r_recon, "Other revenue (VAP, foil, elim.)", "mln",
              "02_Hist rev minus segments (~25%). Grows proportionally")
    # History: formula
    hi_rev = REG.get("HI.revenue", 7)
    for c in range(3, 3 + n_hist):
        cl = get_column_letter(c)
        seg_parts = "+".join(
            f"{cl}{REG.get('RV.' + seg['key'] + '_rev', 10)}"
            for seg in cfg["segments"])
        formula_cell(ws, r_recon, c,
                     f"='{NAME['HI']}'!{cl}${hi_rev}-({seg_parts})", FMT_MLN)
    # Forecast
    for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        # Д2: Reconciliation grows proportionally to segment total (not frozen)
        # recon_t = recon_prev × (Σseg_t / Σseg_prev)
        cl = get_column_letter(c)
        prev_col = get_column_letter(c - 1)
        seg_rev_rows = [REG.get(f"RV.{seg['key']}_rev", 10) for seg in cfg["segments"]]
        seg_parts_t = "+".join(f"{cl}{sr}" for sr in seg_rev_rows)
        seg_parts_p = "+".join(f"{prev_col}{sr}" for sr in seg_rev_rows)
        formula_cell(ws, r_recon, c,
                     f"=IFERROR({prev_col}{r_recon}*({seg_parts_t})"
                     f"/MAX(1,{seg_parts_p}),{prev_col}{r_recon})", FMT_MLN)

    # Total revenue = Σ segments + reconciliation
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
        parts.append(f"{col_l}{r_recon}")  # + reconciliation
        formula_cell(ws, r_total, c, "=" + "+".join(parts), FMT_MLN, bold=True)

    # Revenue method switch for total (method 2=macro_ols, 3=ewa override total)
    # Method 1 (segment): already computed above as Σ segments + recon
    # Method 2 (macro_ols): Rev = prev × (1 + β × Δln(factor))
    # Method 3 (ewa): Rev = prev × (1 + EWA_growth_from_history)
    cp_rev_method = f"'Control_Panel'!$C${REG.get('CP.rev_method', 20)}"
    for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        col_l = get_column_letter(c)
        prev_col = get_column_letter(c - 1)
        seg_total = "+".join(
            f"{col_l}{REG.get('RV.' + seg['key'] + '_rev', 10)}"
            for seg in cfg["segments"])
        seg_total = f"{seg_total}+{col_l}{r_recon}"  # method 1
        # Method 2: macro OLS = prev × (1 + β × Δln(macro_factor))
        # β from CP.rev_elasticity, macro_factor from 01_Macro active row
        cp_beta = f"'Control_Panel'!$C${REG.get('CP.rev_elasticity', 20)}"
        act_base = REG.get("MA.act_base", 36)
        macro_t = f"'{NAME['MA']}'!{col_l}${act_base}"
        macro_prev = f"'{NAME['MA']}'!{prev_col}${act_base}"
        method2 = f"{prev_col}{r_total}*(1+{cp_beta}*LN(MAX(1,{macro_t})/MAX(1,{macro_prev})))"
        # Method 3: EWA = carry-forward growth (simpler, from prev year)
        method3 = f"{prev_col}{r_total}*(1+IFERROR(({prev_col}{r_total}/{get_column_letter(c-2)}{r_total}-1),0))"
        formula_cell(ws, r_total, c,
                     f"=IF({cp_rev_method}=1,{seg_total},"
                     f"IF({cp_rev_method}=2,{method2},{method3}))",
                     FMT_MLN, bold=True)

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

    year_headers(ws, 4, cfg["hist_years"][-3:], cfg["fc_years"])

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

    # Additional rows for CapEx breakdown and DA rate
    r_capex_rev = REG.get("PP.capex_rev", 20)
    r_da_rate = REG.get("PP.da_rate", 21)
    label_row(ws, r_capex_rev, "CapEx / Revenue", "%")
    label_row(ws, r_da_rate, "DA / ОС нетто (rate)", "%")

    # CP references for CapEx parameters
    # CP references (dynamic rows from REG, set in build_control_panel)
    cp_da_rate = ref('CP', 'da_rate', '$C')
    cp_sustaining = ref('CP', 'sustaining_ratio', '$C')
    cp_expansion = ref('CP', 'expansion_pct', '$C')

    # Formulas for forecast columns
    n_hist = len(cfg["hist_years"][-3:])
    for c_idx in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c_idx)
        prev = get_column_letter(c_idx - 1)

        # Gross: open = prev close
        formula_cell(ws, REG["PP.gross_open"], c_idx, f"={prev}{REG['PP.gross_close']}", FMT_MLN)

        # ── CapEx = sustaining + expansion ──
        # sustaining = prev_DA × sustaining_ratio
        # expansion = MAX(0, volume_growth) × capex_per_unit
        #   volume_growth from seg1 (primary product)
        #   capex_per_unit ≈ PPE_net / capacity → expansion_pct × rev as proxy
        rev_ref = f"'{NAME['RV']}'!{cl}${REG['RV.total_rev']}"
        prev_rev_ref = f"'{NAME['RV']}'!{prev}${REG['RV.total_rev']}"
        # Volume-driven expansion: growth in seg1 volume → capex
        vol_ref = f"'{NAME['RV']}'!{cl}${REG.get('RV.seg1_vol', 8)}"
        prev_vol_ref = f"'{NAME['RV']}'!{prev}${REG.get('RV.seg1_vol', 8)}"
        # expansion = MAX(0, Δvol/vol_prev) × PPE_net × expansion_pct
        # If volumes don't grow → expansion = 0 (no capex for declining business)
        formula_cell(ws, REG["PP.capex"], c_idx,
                     f"=MAX("
                     f"{prev}{REG['PP.dep_charge']}*{cp_sustaining}"  # sustaining
                     f"+IFERROR(MAX(0,{vol_ref}/{prev_vol_ref}-1),0)*{prev}{REG['PP.net_close']}*{cp_expansion}"  # expansion from volume
                     f","
                     f"ABS({rev_ref})*{cp_da_rate}*0.5"  # floor: 50% of rev-based
                     f")",
                     FMT_MLN)

        # Disposals = CapEx × disposal_pct (from CP, default 0)
        cp_disposal = f"'Control_Panel'!$C${REG.get('CP.disposal_pct', 46)}"
        formula_cell(ws, REG["PP.disp_gross"], c_idx,
                     f"={cl}{REG['PP.capex']}*{cp_disposal}", FMT_MLN)

        # Gross close = open + capex - disposals
        formula_cell(ws, REG["PP.gross_close"], c_idx,
                     f"={cl}{REG['PP.gross_open']}+{cl}{REG['PP.capex']}-{cl}{REG['PP.disp_gross']}",
                     FMT_MLN, bold=True)

        # Dep: open = prev close
        formula_cell(ws, REG["PP.dep_open"], c_idx, f"={prev}{REG['PP.dep_close']}", FMT_MLN)
        # Dep charge = gross_open / useful_life (Д5: from gross, not net × rate)
        cp_useful_life = f"'Control_Panel'!$C${REG.get('CP.useful_life', 44)}"
        formula_cell(ws, REG["PP.dep_charge"], c_idx,
                     f"=IFERROR({cl}{REG['PP.gross_open']}/{cp_useful_life},"
                     f"{cl}{REG['PP.net_open']}*{cp_da_rate})",
                     FMT_MLN)
        # Dep on disposals = disposal_gross × (accum_dep / gross) proportion
        formula_cell(ws, REG["PP.dep_disp"], c_idx,
                     f"=IFERROR({cl}{REG['PP.disp_gross']}*{cl}{REG['PP.dep_open']}"
                     f"/{cl}{REG['PP.gross_open']},0)", FMT_MLN)
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

    year_headers(ws, 4, cfg["hist_years"][-3:], cfg["fc_years"])

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

    # ── History: line items filled by fill_data (refs to 02_Hist) ──
    # Totals as formulas (not literals) for history too
    n_hist = len(cfg["hist_years"][-3:])
    for c in range(3, 3 + n_hist):
        cl = get_column_letter(c)
        ca_keys = ["cash", "ar", "inv", "other_ca"]
        formula_cell(ws, r_tca, c,
                     "=" + "+".join(f"{cl}{REG[f'BS.{k}']}" for k in ca_keys),
                     FMT_MLN, bold=True)
        nca_keys = ["ppe", "rou", "goodwill", "intang", "dta", "other_nca"]
        formula_cell(ws, r_tnca, c,
                     "=" + "+".join(f"{cl}{REG[f'BS.{k}']}" for k in nca_keys),
                     FMT_MLN, bold=True)
        formula_cell(ws, r_ta, c, f"={cl}{r_tca}+{cl}{r_tnca}", FMT_MLN, bold=True)
        cl_keys = ["ap", "st_debt", "lease_cl", "tax_pay", "other_cl"]
        formula_cell(ws, r_tcl, c,
                     "=" + "+".join(f"{cl}{REG[f'BS.{k}']}" for k in cl_keys),
                     FMT_MLN, bold=True)
        ncl_keys = ["lt_debt", "lease_ncl", "prov", "dtl", "other_ncl"]
        formula_cell(ws, r_tncl, c,
                     "=" + "+".join(f"{cl}{REG[f'BS.{k}']}" for k in ncl_keys),
                     FMT_MLN, bold=True)
        formula_cell(ws, r_tl, c, f"={cl}{r_tcl}+{cl}{r_tncl}", FMT_MLN, bold=True)
        eq_keys = ["sc", "apic", "re", "aoci"]
        formula_cell(ws, r_te, c,
                     "=" + "+".join(f"{cl}{REG[f'BS.{k}']}" for k in eq_keys),
                     FMT_MLN, bold=True)
        formula_cell(ws, r_check, c,
                     f"={cl}{r_ta}-{cl}{r_tl}-{cl}{r_te}", FMT_RATIO, bold=True)

    # ── Forecast columns: cross-sheet links ──
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

        # TCL = sum of ABS(CL items) — handles negative tax_pay
        cl_keys = ["ap", "st_debt", "lease_cl", "tax_pay", "other_cl"]
        formula_cell(ws, r_tcl, c_idx,
                     "=" + "+".join(f"ABS({cl}{REG[f'BS.{k}']})" for k in cl_keys),
                     FMT_MLN, bold=True)

        # TNCL = sum of ABS(NCL items)
        ncl_keys = ["lt_debt", "lease_ncl", "prov", "dtl", "other_ncl"]
        formula_cell(ws, r_tncl, c_idx,
                     "=" + "+".join(f"ABS({cl}{REG[f'BS.{k}']})" for k in ncl_keys),
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
        # Cash ← CF cash_close (always funded — model always attracts debt)
        formula_cell(ws, REG["BS.cash"], c_idx,
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
        # Tax Payable = current tax (can be negative = receivable)
        formula_cell(ws, REG["BS.tax_pay"], c_idx,
                     f"='{NAME['TX']}'!{cl}${REG['TX.current']}",
                     FMT_MLN)

        # Other CL = TCL(history) - known_CL (plug to preserve total)
        # In history: other_cl includes lease, provisions, etc.
        # In forecast: carry forward
        # AOCI/NCI: grow by NCI income if company has NCI
        nci_pct = cfg.get("nci_pct", 0.0)
        if nci_pct > 0:
            # AOCI_NCI(t) = AOCI_NCI(t-1) + NI × nci_pct
            formula_cell(ws, REG["BS.aoci"], c_idx,
                         f"={prev}{REG['BS.aoci']}+'{NAME['PL']}'!{cl}${REG['PL.ni']}*{nci_pct}",
                         FMT_MLN)

        # Lease: link to LS sheet (not carry-forward)
        # lease_cl ≈ next year's payment, lease_ncl = total - CL
        formula_cell(ws, REG["BS.lease_cl"], c_idx,
                     f"=MIN(ABS('{NAME['LS']}'!{cl}${REG['LS.liab_pay']}),"
                     f"'{NAME['LS']}'!{cl}${REG['LS.liab_close']})", FMT_MLN)
        formula_cell(ws, REG["BS.lease_ncl"], c_idx,
                     f"=MAX(0,'{NAME['LS']}'!{cl}${REG['LS.liab_close']}"
                     f"-{cl}{REG['BS.lease_cl']})", FMT_MLN)
        # ROU → LS sheet
        formula_cell(ws, REG["BS.rou"], c_idx,
                     f"='{NAME['LS']}'!{cl}${REG['LS.rou_close']}", FMT_MLN)

        for key in ["other_ca", "goodwill", "intang",
                     "other_cl", "prov",
                     "other_ncl", "sc", "apic"] + (["aoci"] if nci_pct == 0 else []):
            formula_cell(ws, REG[f"BS.{key}"], c_idx, f"={prev}{REG[f'BS.{key}']}", FMT_MLN)
        # Other NCA: carry-forward + associates income (equity method increases investment)
        oi_assoc = REG.get("OI.associates")
        if oi_assoc:
            formula_cell(ws, REG["BS.other_nca"], c_idx,
                         f"={prev}{REG['BS.other_nca']}+'{NAME['OI']}'!{cl}${oi_assoc}",
                         FMT_MLN)
        else:
            formula_cell(ws, REG["BS.other_nca"], c_idx,
                         f"={prev}{REG['BS.other_nca']}", FMT_MLN)


def build_pl(wb, cfg):
    """21_PL — Income Statement with formula references."""
    ws = wb["21_PL"]
    apply_col_widths(ws)

    ws.cell(1, 1, f"21_PL — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "Отчёт о прибылях и убытках").font = F_SUBTITLE

    year_headers(ws, 4, cfg["hist_years"][-3:], cfg["fc_years"])

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

    # ── History: filled by fill_data (fill_statement_history writes refs to 02_Hist) ──
    n_hist = len(cfg["hist_years"][-3:])

    # ── Forecast columns ──
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
        # Interest ← 17_Debt (always negative in PL — expense)
        formula_cell(ws, REG["PL.interest"], c_idx,
                     f"=-ABS('{NAME['DT']}'!{cl}${REG['DT.interest']})", FMT_MLN)
        # Interest income ← 14_OtherIS
        ref_cell(ws, REG["PL.interest_income"], c_idx,
                 f"='{NAME['OI']}'!{cl}${REG['OI.interest_income']}", FMT_MLN)
        # Associates ← 14_OtherIS
        ref_cell(ws, REG["PL.associates"], c_idx,
                 f"='{NAME['OI']}'!{cl}${REG['OI.associates']}", FMT_MLN)
        # Other financial: OI.other_fin + net FX impact
        # FX on debt: negative (positive reval = debt up = loss)
        # FX on revenue: positive (CNY/RUB strengthening → USD revenue up from local-ccy sales)
        # FX on costs: negative (RUB strengthening → costs up in USD)
        # Net FX = -debt_reval + rev × rev_share × (-fx_chg) - cogs × cost_share × (-fx_chg)
        # Simplified: rev_fx_gain = Revenue × rev_cny_share × (-USDCNY_chg) + Revenue × rev_rub_share × (-USDRUB_chg)
        #             cost_fx_loss = ABS(COGS) × cost_rub_share × (-USDRUB_chg)
        cp_rev_cny = f"'Control_Panel'!$C${REG.get('CP.rev_cny_share', 80)}"
        cp_rev_rub = f"'Control_Panel'!$C${REG.get('CP.rev_rub_share', 81)}"
        cp_cost_rub = f"'Control_Panel'!$C${REG.get('CP.cost_rub_share', 82)}"
        cp_fx_cny = f"'Control_Panel'!$C${REG.get('CP.fx_usdcny_chg', 75)}"
        cp_fx_rub = f"'Control_Panel'!$C${REG.get('CP.fx_usdrub_chg', 76)}"
        rev_ref = f"'{NAME['PL']}'!{cl}${REG['PL.revenue']}"
        cogs_ref = f"ABS('{NAME['PL']}'!{cl}${REG['PL.cogs']})"
        # Per-year FX from 05_Drivers (not CP scalar)
        dr_fx_r = REG.get("DR.fx_usdrub_chg")
        fx_rub_yr = f"'{NAME['DR']}'!{cl}${dr_fx_r}" if dr_fx_r else cp_fx_rub
        # Revenue FX gain: when local ccy strengthens, rev in USD goes up
        rev_fx = (f"{rev_ref}*{cp_rev_cny}*(-{cp_fx_cny})"
                  f"+{rev_ref}*{cp_rev_rub}*(-{fx_rub_yr})")
        # Cost FX: now in 12_COGS (÷(1+ΔFXRUB)), not here (no double-count)
        formula_cell(ws, REG["PL.other_fin"], c_idx,
                     f"='{NAME['OI']}'!{cl}${REG['OI.other_fin']}"
                     f"-'{NAME['DT']}'!{cl}${REG['DT.fx_reval']}"
                     f"+{rev_fx}",
                     FMT_MLN)
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
        # EBT = EBIT + interest(negative) + interest_income + other_fin + associates
        formula_cell(ws, REG["PL.ebt"], c_idx,
                     f"={cl}{REG['PL.ebit']}+{cl}{REG['PL.interest']}+{cl}{REG['PL.interest_income']}+"
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

    year_headers(ws, 4, cfg["hist_years"][-3:], cfg["fc_years"])

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
    n_hist = len(cfg["hist_years"][-3:])
    for c_idx in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c_idx)

        # ND/EBITDA
        formula_cell(ws, REG["RA.nd_ebitda"], c_idx,
                     f"=IFERROR('{NAME['DT']}'!{cl}${REG['DT.nd']}/'{NAME['PL']}'!{cl}${REG['PL.ebitda']},0)",
                     FMT_MULT)
        # ICR = EBITDA / |Interest| (interest is negative in PL)
        formula_cell(ws, REG["RA.icr"], c_idx,
                     f"=IFERROR('{NAME['PL']}'!{cl}${REG['PL.ebitda']}/ABS('{NAME['PL']}'!{cl}${REG['PL.interest']}),0)",
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

        # ── Previously empty metrics (H1 audit) ──

        # Debt/Equity
        formula_cell(ws, REG["RA.debt_equity"], c_idx,
                     f"=IFERROR('{NAME['DT']}'!{cl}${REG['DT.close']}/'{NAME['BS']}'!{cl}${REG['BS.te']},0)",
                     FMT_MULT)
        # Debt/Assets
        formula_cell(ws, REG["RA.debt_assets"], c_idx,
                     f"=IFERROR('{NAME['DT']}'!{cl}${REG['DT.close']}/'{NAME['BS']}'!{cl}${REG['BS.ta']},0)",
                     FMT_PCT)
        # Gross margin
        formula_cell(ws, REG["RA.gp_margin"], c_idx,
                     f"=IFERROR('{NAME['PL']}'!{cl}${REG['PL.gp']}/'{NAME['PL']}'!{cl}${REG['PL.revenue']},0)",
                     FMT_PCT)
        # EBIT margin
        formula_cell(ws, REG["RA.ebit_margin"], c_idx,
                     f"=IFERROR('{NAME['PL']}'!{cl}${REG['PL.ebit']}/'{NAME['PL']}'!{cl}${REG['PL.revenue']},0)",
                     FMT_PCT)
        # ROA
        formula_cell(ws, REG["RA.roa"], c_idx,
                     f"=IFERROR('{NAME['PL']}'!{cl}${REG['PL.ni']}/'{NAME['BS']}'!{cl}${REG['BS.ta']},0)",
                     FMT_PCT)
        # ROIC = EBIT × (1-tax) / (Equity + Net Debt)
        cp_tax = f"'Control_Panel'!$C${REG.get('CP.tax_rate', 80)}"
        formula_cell(ws, REG["RA.roic"], c_idx,
                     f"=IFERROR('{NAME['PL']}'!{cl}${REG['PL.ebit']}*(1-{cp_tax})"
                     f"/('{NAME['BS']}'!{cl}${REG['BS.te']}+'{NAME['DT']}'!{cl}${REG['DT.nd']}),0)",
                     FMT_PCT)
        # Quick ratio = (Cash + AR) / TCL
        formula_cell(ws, REG["RA.quick"], c_idx,
                     f"=IFERROR(('{NAME['BS']}'!{cl}${REG['BS.cash']}+'{NAME['BS']}'!{cl}${REG['BS.ar']})"
                     f"/'{NAME['BS']}'!{cl}${REG['BS.tcl']},0)",
                     FMT_MULT)
        # Cash ratio = Cash / TCL
        formula_cell(ws, REG["RA.cash_ratio"], c_idx,
                     f"=IFERROR('{NAME['BS']}'!{cl}${REG['BS.cash']}/'{NAME['BS']}'!{cl}${REG['BS.tcl']},0)",
                     FMT_MULT)
        # DSO, DIH, DPO, CCC from WC sheet
        for wc_key, ra_key in [("dso", "dso"), ("dio", "dio"), ("dpo", "dpo"), ("ccc", "ccc")]:
            ref_cell(ws, REG[f"RA.{ra_key}"], c_idx,
                     f"='{NAME['WC']}'!{cl}${REG[f'WC.{wc_key}']}", FMT_DAYS)
        # CapEx/Revenue
        formula_cell(ws, REG["RA.capex_rev"], c_idx,
                     f"=IFERROR(ABS('{NAME['PP']}'!{cl}${REG['PP.capex']})/'{NAME['PL']}'!{cl}${REG['PL.revenue']},0)",
                     FMT_PCT)
        # D&A/Revenue
        formula_cell(ws, REG["RA.da_rev"], c_idx,
                     f"=IFERROR('{NAME['PP']}'!{cl}${REG['PP.dep_charge']}/'{NAME['PL']}'!{cl}${REG['PL.revenue']},0)",
                     FMT_PCT)


def build_checks(wb, cfg):
    """90_Checks — integrity verification."""
    ws = wb["90_Checks"]
    apply_col_widths(ws)

    ws.cell(1, 1, f"90_Checks — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "Проверки целостности модели").font = F_SUBTITLE

    year_headers(ws, 4, cfg["hist_years"][-3:], cfg["fc_years"])

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
        label_row(ws, r, label, "mln", "Должно быть 0")

    # All check formulas for forecast years
    n_hist = len(cfg["hist_years"][-3:])
    for c_idx in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c_idx)
        prev = get_column_letter(c_idx - 1)

        # 1. BS check = TA - TL - TE (from 20_BS)
        ref_cell(ws, REG["CK.bs_check"], c_idx,
                 f"='{NAME['BS']}'!{cl}${REG['BS.check']}", FMT_RATIO)

        # 2. CF bridge = ΔCash(BS) - (CFO + CFI + CFF)
        # ΔCash = Cash_close - Cash_open in BS
        cash_delta = (f"'{NAME['BS']}'!{cl}${REG['BS.cash']}"
                      f"-'{NAME['BS']}'!{prev}${REG['BS.cash']}")
        cf_sum = (f"'{NAME['CF']}'!{cl}${REG['CF.cfo']}"
                  f"+'{NAME['CF']}'!{cl}${REG['CF.cfi']}"
                  f"+'{NAME['CF']}'!{cl}${REG['CF.cff']}")
        formula_cell(ws, REG["CK.cf_check"], c_idx,
                     f"=IFERROR(({cash_delta})-({cf_sum}),0)", FMT_RATIO)

        # 3. PPE roll = net_close - (gross_close - dep_close)
        formula_cell(ws, REG["CK.ppe_roll"], c_idx,
                     f"='{NAME['PP']}'!{cl}${REG['PP.net_close']}"
                     f"-('{NAME['PP']}'!{cl}${REG['PP.gross_close']}"
                     f"-'{NAME['PP']}'!{cl}${REG['PP.dep_close']})",
                     FMT_RATIO)

        # 4. Debt roll = (term_open - mandatory + refi + new - vol - term_close)
        #              + (rc_open + rc_draw - rc_repay - rc_close)
        formula_cell(ws, REG["CK.debt_roll"], c_idx,
                     f"='{NAME['DT']}'!{cl}${REG['DT.term_open']}"
                     f"-ABS('{NAME['DT']}'!{cl}${REG['DT.mandatory']})"
                     f"+'{NAME['DT']}'!{cl}${REG['DT.refi']}"
                     f"+'{NAME['DT']}'!{cl}${REG['DT.new_term']}"
                     f"-ABS('{NAME['DT']}'!{cl}${REG['DT.voluntary_term']})"
                     f"-'{NAME['DT']}'!{cl}${REG['DT.term_close']}"
                     f"+'{NAME['DT']}'!{cl}${REG['DT.rc_open']}"
                     f"+'{NAME['DT']}'!{cl}${REG['DT.rc_draw']}"
                     f"-'{NAME['DT']}'!{cl}${REG['DT.rc_repay']}"
                     f"-'{NAME['DT']}'!{cl}${REG['DT.rc_close']}",
                     FMT_RATIO)

        # 5. Equity roll = RE_open + NI - Div - RE_close
        formula_cell(ws, REG["CK.equity_roll"], c_idx,
                     f"='{NAME['EQ']}'!{cl}${REG['EQ.re_open']}"
                     f"+'{NAME['EQ']}'!{cl}${REG['EQ.ni']}"
                     f"-ABS('{NAME['EQ']}'!{cl}${REG['EQ.div']})"
                     f"-'{NAME['EQ']}'!{cl}${REG['EQ.re_close']}",
                     FMT_RATIO)

    # ── Additional checks: RC + Sources & Uses ──
    new_checks = [
        ("rc_limit", "RC: Close ≤ Limit", None, None),
        ("funding_gap", "Penalty debt (0 = no breach)", None, None),
        ("su_balance", "S&U: Gap = RC_draw + NewTerm + FundGap", None, None),
        ("st_lt_check", "ST + LT = DT.close", None, None),
        ("schedule_check", "DT.close = Term + RC + FX", None, None),
        ("cash_min", "Cash ≥ min_cash ИЛИ FundGap > 0", None, None),
        ("maint_debt", "Подд. CapEx не финансируется долгом", None, None),
        ("interest_check", "Int = Term + RC + Fee + Penalty", None, None),
        ("it_res", "Невязка кольца (Cash vs est_cash)", None, None),
    ]
    for key, label, _, _ in new_checks:
        r = REG.get(f"CK.{key}")
        if r:
            label_row(ws, r, label, "mln", "Должно быть 0 / TRUE")

    for c_idx in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c_idx)
        # RC limit: 0 if within limit, 1 if breach
        formula_cell(ws, REG["CK.rc_limit"], c_idx,
                     f"=IF('{NAME['DT']}'!{cl}${REG['DT.rc_close']}"
                     f"<='{NAME['DT']}'!{cl}${REG['DT.rc_limit']},0,1)",
                     FMT_INT)
        # Funding gap: should be 0
        ref_cell(ws, REG["CK.funding_gap"], c_idx,
                 f"='{NAME['DT']}'!{cl}${REG['DT.funding_gap']}", FMT_RATIO)
        # S&U balance: need = rc_draw + new_term
        # (funding_gap is a subset of new_term — rate attribute, not extra source)
        formula_cell(ws, REG["CK.su_balance"], c_idx,
                     f"='{NAME['DT']}'!{cl}${REG['DT.su_gap']}"
                     f"-'{NAME['DT']}'!{cl}${REG['DT.rc_draw']}"
                     f"-'{NAME['DT']}'!{cl}${REG['DT.new_term']}",
                     FMT_RATIO)
        # ST + LT = close
        formula_cell(ws, REG["CK.st_lt_check"], c_idx,
                     f"='{NAME['DT']}'!{cl}${REG['DT.st']}"
                     f"+'{NAME['DT']}'!{cl}${REG['DT.lt']}"
                     f"-'{NAME['DT']}'!{cl}${REG['DT.close']}",
                     FMT_RATIO)
        # Schedule: close = term + RC + FX
        formula_cell(ws, REG["CK.schedule_check"], c_idx,
                     f"='{NAME['DT']}'!{cl}${REG['DT.close']}"
                     f"-'{NAME['DT']}'!{cl}${REG['DT.term_close']}"
                     f"-'{NAME['DT']}'!{cl}${REG['DT.rc_close']}"
                     f"-'{NAME['DT']}'!{cl}${REG['DT.fx_reval']}",
                     FMT_RATIO)

        # #6 Cash ≥ min_cash OR FundingGap > 0 (both = OK, neither = fail)
        # Returns 0 if OK, 1 if fail (cash < min AND gap = 0)
        cp_min = f"'Control_Panel'!$C${REG.get('CP.min_cash', 54)}"
        formula_cell(ws, REG["CK.cash_min"], c_idx,
                     f"=IF(OR('{NAME['BS']}'!{cl}${REG['BS.cash']}>={cp_min},"
                     f"'{NAME['DT']}'!{cl}${REG['DT.funding_gap']}>0),0,1)",
                     FMT_INT)

        # #7 Maintenance capex not financed by new debt
        # su_maint_gap > 0 AND new_term > 0 = problem
        formula_cell(ws, REG["CK.maint_debt"], c_idx,
                     f"=IF(AND('{NAME['DT']}'!{cl}${REG['DT.su_maint_gap']}>0,"
                     f"'{NAME['DT']}'!{cl}${REG['DT.new_term']}>0),1,0)",
                     FMT_INT)

        # #8 Interest = term + RC + fee + penalty (verify decomposition)
        prev_cl = get_column_letter(c_idx - 1)
        cp_pen = f"'Control_Panel'!$C${REG.get('CP.penalty_rate', 72)}"
        formula_cell(ws, REG["CK.interest_check"], c_idx,
                     f"='{NAME['DT']}'!{cl}${REG['DT.interest']}"
                     f"-'{NAME['DT']}'!{cl}${REG['DT.interest_term']}"
                     f"-'{NAME['DT']}'!{cl}${REG['DT.interest_rc']}"
                     f"-'{NAME['DT']}'!{cl}${REG['DT.commit_fee']}"
                     f"-'{NAME['DT']}'!{prev_cl}${REG['DT.funding_gap_accum']}*{cp_pen}",
                     FMT_RATIO)

        # C3: Iteration residual — cash convergence check
        # If RC_draw > 0, actual cash should ≈ min_cash (model always finances)
        cp_min = f"'Control_Panel'!$C${REG.get('CP.min_cash', 54)}"
        formula_cell(ws, REG["CK.it_res"], c_idx,
                     f"=IF('{NAME['DT']}'!{cl}${REG['DT.rc_draw']}>0,"
                     f"ABS('{NAME['BS']}'!{cl}${REG['BS.cash']}-{cp_min}),0)",
                     FMT_RATIO)

    # ── ТОЖДЕСТВА: error count (always must be 0) ──
    r_err = 24
    REG["CK.error_count"] = r_err
    label_row(ws, r_err, "ОШИБКИ ТОЖДЕСТВ (всегда должно быть 0)", "", "Книга неверна если > 0")

    # ── ФЛАГИ СОСТОЯНИЯ (в стрессе могут быть > 0) ──
    r_flags = r_err + 2
    label_row(ws, r_flags, "ФЛАГИ СОСТОЯНИЯ (стресс)", "", "Сигнал о заёмщике, не ошибка книги")

    # ── СВЕРКА ИСТОРИИ (отдельный блок, cols C-E only) ──
    r_hist_base = r_flags + 2
    section_header(ws, r_hist_base, "СВЕРКА ИСТОРИИ (прогнозный лист = 02_Hist)")
    hist_checks = [
        ("Rev: 10_Revenue = 02_Hist", f"'{NAME['RV']}'", REG['RV.total_rev'], "HI.revenue"),
        ("COGS: 12_COGS = 02_Hist", f"'{NAME['CG']}'", REG['CG.total'], "HI.cogs"),
        ("SGA: 13_SGA = 02_Hist", f"'{NAME['SA']}'", REG['SA.sga_total'], "HI.sga"),
        ("PPE: 15_PPE = 02_Hist (col E only)", f"'{NAME['PP']}'", REG['PP.net_close'], "HI.ppe_net"),
        ("BS: 20_BS TA = 02_Hist", f"'{NAME['BS']}'", REG['BS.ta'], "HI.ta"),
    ]
    for i, (label, sheet_ref, calc_row, hi_key) in enumerate(hist_checks):
        r_hc = r_hist_base + 1 + i
        label_row(ws, r_hc, label, "mln", "Должно быть ~0")
        hi_row = REG.get(hi_key)
        if hi_row:
            # PPE: only last hist year (earlier years may be empty)
            cols_range = [3 + n_hist - 1] if "PPE" in label else range(3, 3 + n_hist)
            for c in cols_range:
                cl = get_column_letter(c)
                formula_cell(ws, r_hc, c,
                             f"=ROUND({sheet_ref}!{cl}${calc_row}"
                             f"-'{NAME['HI']}'!{cl}${hi_row},1)",
                             FMT_RATIO)

    r_hist_err = r_hist_base + len(hist_checks) + 1
    label_row(ws, r_hist_err, "ОШИБКИ ИСТОРИИ", "", "Должно быть 0")
    ws.cell(r_hist_err, 1).font = F_LABEL_B
    ws.cell(r_err, 1).font = F_LABEL_B
    ws.cell(r_flags, 1).font = F_LABEL_B
    for c_idx in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c_idx)
        # ТОЖДЕСТВА: always 0, otherwise model is broken
        identity_rows = [REG["CK.bs_check"], REG["CK.cf_check"], REG["CK.ppe_roll"],
                         REG["CK.debt_roll"], REG["CK.equity_roll"],
                         REG["CK.st_lt_check"], REG["CK.schedule_check"],
                         REG["CK.interest_check"], REG["CK.su_balance"]]
        id_parts = [f"IF(ISERROR({cl}{r}),1,IF(ABS({cl}{r})>1,1,0))" for r in identity_rows]
        # + ISERROR on key cells
        key_cells = [
            f"'{NAME['PL']}'!{cl}${REG['PL.ni']}",
            f"'{NAME['BS']}'!{cl}${REG['BS.ta']}",
            f"'{NAME['BS']}'!{cl}${REG['BS.cash']}",
            f"'{NAME['CF']}'!{cl}${REG['CF.cfo']}",
        ]
        id_parts += [f"IF(ISERROR({ref}),1,0)" for ref in key_cells]
        formula_cell(ws, r_err, c_idx, "=" + "+".join(id_parts), FMT_INT, bold=True)

        # ФЛАГИ СОСТОЯНИЯ: OK to be > 0 in stress
        flag_rows = [REG["CK.rc_limit"], REG["CK.funding_gap"],
                     REG["CK.cash_min"], REG["CK.maint_debt"]]
        fl_parts = [f"IF(IFERROR({cl}{r},0)>0,1,0)" for r in flag_rows]
        formula_cell(ws, r_flags, c_idx, "=" + "+".join(fl_parts), FMT_INT)

    # History error count (cols C:E)
    for c in range(3, 3 + n_hist):
        cl = get_column_letter(c)
        hist_parts = [f"IF(ABS(IFERROR({cl}{r_hist_base+1+i},0))>1,1,0)"
                      for i in range(len(hist_checks))]
        formula_cell(ws, r_hist_err, c, "=" + "+".join(hist_parts), FMT_INT, bold=True)


def build_cogs(wb, cfg):
    """12_COGS — component-based or ratio-based COGS.

    Component mode (Rusal): each component = base × factor_index × vol_adj
    Then: COGS_ratio = anchor × (1 + macro_deviation × dampening), clamped
    Ratio mode (Nornickel): COGS = Revenue × historical_ratio (from 03_Assump)
    """
    ws = wb["12_COGS"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"12_COGS — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1,
            "Компонентная модель: COGS = Σ(base_comp × factor_index × vol_adj)"
            if cfg.get("cogs_mode") == "component"
            else "Ratio × Revenue (калиброван из истории)").font = F_SUBTITLE
    n_hist = len(cfg["hist_years"][-3:])
    year_headers(ws, 4, cfg["hist_years"][-3:], cfg["fc_years"])

    if cfg.get("cogs_mode") == "component":
        comps = cfg.get("cogs_components", {})

        # Component rows (history: input, forecast: calculated)
        section_header(ws, 6, "КОМПОНЕНТЫ СЕБЕСТОИМОСТИ")
        comp_info = {
            "material": ("Material (alumina, raw)", "Driven by commodity factor"),
            "energy": ("Energy (electricity)", "Driven by power price × FX"),
            "labour": ("Labour", "Driven by CPI inflation × FX"),
            "other": ("Other (transport, etc.)", "Driven by PPI"),
        }
        for i, (comp, share) in enumerate(comps.items()):
            r = REG.get(f"CG.{comp}", 8 + i)
            info = comp_info.get(comp, (comp.title(), ""))
            label_row(ws, r, f"{info[0]} ({share*100:.0f}%)", "mln", info[1])
            # History: input cells
            for c in range(3, 3 + n_hist):
                input_cell(ws, r, c, 0, FMT_MLN)
            # Forecast: operating leverage via fixed/variable split (Д3)
            # Material: volume-driven (aluminium volume × alumina_norm × price)
            #   → proportional to volume, not revenue
            # Energy/Labour: fixed per tonne (cost = volume × unit_cost)
            #   → doesn't scale with price, only with volume
            # Other: from revenue (transport, commissions)
            cp_cogs_ratio = f"'Control_Panel'!$C${REG.get('CP.cogs_ratio', 20)}"
            cp_share_key = f"CP.cogs_{comp}"
            cp_share_row = REG.get(cp_share_key)
            vol_ref = f"'{NAME['RV']}'!{{cl}}${REG.get('RV.seg1_vol', 8)}"  # aluminium volume

            for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
                cl = get_column_letter(c)
                prev_cl = get_column_letter(c - 1)
                rev_ref = f"ABS('{NAME['RV']}'!{cl}${REG['RV.total_rev']})"
                share_ref = f"'Control_Panel'!$C${cp_share_row}" if cp_share_row else str(share)

                if comp == "material":
                    # Material = Volume_Al(kt) × alumina_norm(t/t) × alumina_price($/t) / 1000
                    # alumina_norm ≈ 1.93 t alumina per t aluminium (industry standard)
                    # alumina_price from 10_Revenue seg2 price row
                    vol_t = vol_ref.format(cl=cl)
                    alumina_price = f"'{NAME['RV']}'!{cl}${REG.get('RV.seg2_price', 13)}"
                    alumina_norm = "1.93"  # t alumina / t Al
                    formula_cell(ws, r, c,
                                 f"=IFERROR({vol_t}*{alumina_norm}*{alumina_price}/1000,"
                                 f"{rev_ref}*{cp_cogs_ratio}*{share_ref})",
                                 FMT_MLN)
                elif comp in ("energy", "labour"):
                    # Per tonne × volume × (1 + cost_indexation)
                    vol_t = vol_ref.format(cl=cl)
                    vol_prev = vol_ref.format(cl=prev_cl)
                    # Indexation + FX: (1+CPI/PPI) / (1+ΔUSD/RUB) for RUB costs
                    dr_idx = REG.get(f"DR.{'energy_idx' if comp == 'energy' else 'labour_idx'}")
                    dr_fx = REG.get("DR.fx_usdrub_chg")
                    idx_num = f"*(1+'{NAME['DR']}'!{cl}${dr_idx})" if dr_idx else ""
                    # Energy/labour are ~100% RUB, divide by FX change directly
                    fx_div = f"/(1+'{NAME['DR']}'!{cl}${dr_fx})" if dr_fx else ""
                    formula_cell(ws, r, c,
                                 f"=IFERROR({prev_cl}{r}*{vol_t}/MAX(1,{vol_prev}){idx_num}{fx_div},"
                                 f"{rev_ref}*{cp_cogs_ratio}*{share_ref})",
                                 FMT_MLN)
                else:
                    # Other: proportional to revenue (transport, commissions)
                    formula_cell(ws, r, c,
                                 f"={rev_ref}*{cp_cogs_ratio}*{share_ref}",
                                 FMT_MLN)

        # D&A in COGS (if applicable)
        r_da = REG.get("CG.da_in_cogs", 13)
        label_row(ws, r_da, "D&A в себестоимости (если да)", "mln", "da_in_cogs=false для Rusal IFRS")
        for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
            formula_cell(ws, r_da, c, "=0", FMT_MLN)  # Rusal: DA separate line (not in COGS)

    else:
        # Ratio mode — COGS = Revenue × calibrated ratio from preprocessing
        section_header(ws, 6, "СЕБЕСТОИМОСТЬ (RATIO × REVENUE)")
        label_row(ws, 8, "COGS calibrated ratio", "%", "Из 03_Assump EWA")

    # Total COGS
    r_total = REG["CG.total"]
    label_row(ws, r_total, "ИТОГО СЕБЕСТОИМОСТЬ", "mln")
    ws.cell(r_total, 1).font = F_LABEL_B

    cp_cogs_method = f"'Control_Panel'!$C${REG.get('CP.cogs_method', 20)}"
    cp_cogs_ratio = f"'Control_Panel'!$C${REG.get('CP.cogs_ratio', 20)}"

    if cfg.get("cogs_mode") == "component":
        comps = cfg.get("cogs_components", {})
        comp_keys = list(comps.keys())
        # History: always sum of components
        for c in range(3, 3 + n_hist):
            cl = get_column_letter(c)
            parts = [f"{cl}{REG.get(f'CG.{k}', 8)}" for k in comp_keys]
            formula_cell(ws, r_total, c, "=-(" + "+".join(parts) + ")", FMT_MLN, bold=True)
        # Forecast: switch (1=ratio, 2=component, 3=ppi_uplift as ratio×(1+ppi))
        for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
            cl = get_column_letter(c)
            prev_cl = get_column_letter(c - 1)
            rev_ref = f"ABS('{NAME['RV']}'!{cl}${REG['RV.total_rev']})"
            comp_sum = "+".join(f"{cl}{REG.get(f'CG.{k}', 8)}" for k in comp_keys)
            method1 = f"-{rev_ref}*{cp_cogs_ratio}"  # ratio
            method2 = f"-({comp_sum})"  # component
            # PPI uplift: prev × (1 + ppi_beta × dampening × macro_ppi_growth)
            cp_ppi = f"'Control_Panel'!$C${REG.get('CP.ppi_beta', 20)}"
            cp_damp = f"'Control_Panel'!$C${REG.get('CP.mr_dampening', 20)}"
            method3 = f"{prev_cl}{r_total}*(1+{cp_ppi}*{cp_damp}*0.05)"  # 5% PPI proxy
            formula_cell(ws, r_total, c,
                         f"=IF({cp_cogs_method}=1,{method1},"
                         f"IF({cp_cogs_method}=2,{method2},{method3}))",
                         FMT_MLN, bold=True)
    else:
        # Ratio mode only (no components built)
        for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
            cl = get_column_letter(c)
            rev_ref = f"'{NAME['RV']}'!{cl}${REG['RV.total_rev']}"
            formula_cell(ws, r_total, c,
                         f"=-ABS({rev_ref})*{cp_cogs_ratio}", FMT_MLN, bold=True)

    # COGS ratio
    r_ratio = REG["CG.ratio"]
    label_row(ws, r_ratio, "COGS / Revenue", "%")
    for c in range(3, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c)
        formula_cell(ws, r_ratio, c,
                     f"=IFERROR(ABS({cl}{r_total})/ABS('{NAME['RV']}'!{cl}${REG['RV.total_rev']}),0)",
                     FMT_PCT)


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
        # Д4: History cells for sga_total reference 21_PL (single source)
        if key == "sga_total":
            for c in range(3, 3 + n_hist):
                cl = get_column_letter(c)
                ref_cell(ws, r, c, f"='{NAME['PL']}'!{cl}${REG['PL.sga']}", FMT_MLN)
            # Forecast: SGA = -Revenue × SGA_ratio (from CP)
            cp_sga = f"'Control_Panel'!$C${REG.get('CP.sga_ratio', 30)}"
            for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
                cl = get_column_letter(c)
                rev_ref = f"ABS('{NAME['RV']}'!{cl}${REG['RV.total_rev']})"
                formula_cell(ws, r, c, f"=-{rev_ref}*{cp_sga}", FMT_MLN)
        else:
            for c in range(3, 3 + n_hist):
                input_cell(ws, r, c, 0, FMT_MLN)
            # Sub-components: input for fill_data override
            for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
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
    # Days: history = input (from fill_data EWA), forecast = from Control_Panel
    cp_days = {
        "dso": REG.get("CP.wc_dso"),
        "dio": REG.get("CP.wc_dio"),
        "dpo": REG.get("CP.wc_dpo"),
    }
    for key, label in [("dso", "DSO (дни)"), ("dio", "DIH (дни)"), ("dpo", "DPO (дни)")]:
        r = REG[f"WC.{key}"]
        label_row(ws, r, label, "дни")
        # History: computed from BS/PL (eliminate literals)
        # DSO = AR/Revenue×365, DIH = INV/COGS×365, DPO = AP/COGS×365
        driver_map = {"dso": ("HI.ar", "HI.revenue"), "dio": ("HI.inv", "HI.cogs"), "dpo": ("HI.ap", "HI.cogs")}
        num_key, den_key = driver_map[key]
        for c in range(3, 3 + n_hist):
            cl = get_column_letter(c)
            num_r = REG.get(num_key)
            den_r = REG.get(den_key)
            if num_r and den_r:
                formula_cell(ws, r, c,
                             f"=IFERROR(ABS('{NAME['HI']}'!{cl}${num_r})"
                             f"/ABS('{NAME['HI']}'!{cl}${den_r})*365,0)",
                             FMT_DAYS)
            else:
                input_cell(ws, r, c, 0, FMT_DAYS)
        # Forecast: reference Control_Panel if available, else carry forward
        cp_row = cp_days.get(key)
        for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
            prev = get_column_letter(c - 1)
            if cp_row:
                ref_cell(ws, r, c, f"='Control_Panel'!$C${cp_row}", FMT_DAYS)
            else:
                formula_cell(ws, r, c, f"={prev}{r}", FMT_DAYS)

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
    # WC method switch: 1=days (AR/INV/AP from DSO/DIH/DPO), 2=ratio (NWC = prev_NWC/Rev × Rev)
    cp_wc_method = f"'Control_Panel'!$C${REG.get('CP.wc_method', 30)}"
    r_nwc = REG["WC.nwc"]
    label_row(ws, r_nwc, "Чистый оборотный капитал", "mln")
    # History: always from components
    for c in range(3, 3 + n_hist):
        cl = get_column_letter(c)
        formula_cell(ws, r_nwc, c,
                     f"={cl}{REG['WC.ar']}+{cl}{REG['WC.inv']}-ABS({cl}{REG['WC.ap']})", FMT_MLN, bold=True)
    # Forecast: method switch
    for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c)
        prev_cl = get_column_letter(c - 1)
        rev_ref = f"ABS('{NAME['RV']}'!{cl}${REG['RV.total_rev']})"
        prev_rev = f"ABS('{NAME['RV']}'!{prev_cl}${REG['RV.total_rev']})"
        method1 = f"{cl}{REG['WC.ar']}+{cl}{REG['WC.inv']}-ABS({cl}{REG['WC.ap']})"
        method2 = f"IFERROR({prev_cl}{r_nwc}/{prev_rev}*{rev_ref},{prev_cl}{r_nwc})"
        formula_cell(ws, r_nwc, c,
                     f"=IF({cp_wc_method}=1,{method1},{method2})",
                     FMT_MLN, bold=True)

    # ΔNWC
    r_delta = REG["WC.delta_nwc"]
    label_row(ws, r_delta, "Изменение NWC", "mln")
    for c in range(4, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c)
        prev = get_column_letter(c - 1)
        formula_cell(ws, r_delta, c, f"={cl}{r_nwc}-{prev}{r_nwc}", FMT_MLN)


def build_debt(wb, cfg):
    """17_Debt — Sources & Uses, Term Debt, RC, Interest, ST/LT.

    Architecture (per TASK_debt_module.md):
    A. Sources & Uses — explicit decomposition of financing needs
    B. Term Debt — schedule-driven, deterministic (from _Debt_Schedule)
    C. Revolving Credit — single balancing plug, always ST, limited
    D. Total Debt — term_close + rc_close
    E. Interest — term (schedule) + RC + commitment fee
    F. ST/LT — maturity-based from schedule + RC_close
    """
    ws = wb["17_Debt"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"17_Debt — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "Sources & Uses · Term Debt · RC · Interest · ST/LT").font = F_SUBTITLE
    n_hist = len(cfg["hist_years"][-3:])
    year_headers(ws, 4, cfg["hist_years"][-3:], cfg["fc_years"])

    # ── A. SOURCES & USES ──
    section_header(ws, 6, "A. SOURCES & USES")
    for key, label, unit in [
        ("su_oper_flow", "EBITDA − налоги уплаченные", "mln"),
        ("su_maint_capex", "Поддерживающий CapEx", "mln"),
        ("su_growth_capex", "Проектный CapEx", "mln"),
        ("su_delta_nwc", "Прирост оборотного капитала", "mln"),
        ("su_mandatory", "Обязательные погашения", "mln"),
        ("su_interest", "Проценты (срочный долг)", "mln"),
        ("su_dividends", "Дивиденды", "mln"),
        ("su_total_uses", "ИТОГО USES", "mln"),
    ]:
        label_row(ws, REG[f"DT.{key}"], label, unit)
    ws.cell(REG["DT.su_total_uses"], 1).font = F_LABEL_B

    section_header(ws, REG["DT.su_refi"] - 1, "SOURCES")
    for key, label, unit in [
        ("su_refi", "Рефинансирование", "mln"),
        ("su_excess_cash", "Кэш сверх минимума", "mln"),
        ("su_total_sources", "ИТОГО SOURCES", "mln"),
    ]:
        label_row(ws, REG[f"DT.{key}"], label, unit)
    ws.cell(REG["DT.su_total_sources"], 1).font = F_LABEL_B

    label_row(ws, REG["DT.su_gap"], "ИТОГО ПРИВЛЕЧЕНИЕ (RC + NewTerm)", "mln",
              "Покрывается RC / новым траншем")
    ws.cell(REG["DT.su_gap"], 1).font = F_LABEL_B
    label_row(ws, REG["DT.su_maint_gap"], "Дефицит по подд. CapEx", "mln",
              "Флаг: опер. поток < подд. CapEx")

    label_row(ws, REG["DT.funding_need"], "ПОТРЕБНОСТЬ В ФИНАНСИРОВАНИИ", "mln",
              "MAX(0, min_cash - cash_before_RC) / (1-r/2(1-t))")
    ws.cell(REG["DT.funding_need"], 1).font = F_LABEL_B

    # ── B. TERM DEBT ──
    section_header(ws, REG["DT.term_open"] - 1, "B. СРОЧНЫЙ ДОЛГ (из _Debt_Schedule)")
    for key, label, unit in [
        ("term_open", "Срочный долг, начало", "mln"),
        ("mandatory", "Обязательное погашение", "mln"),
        ("refi", "Рефинансирование", "mln"),
        ("new_term", "Новый срочный транш", "mln"),
        ("voluntary_term", "Добровольное погашение", "mln"),
        ("term_close", "Срочный долг, конец (до FX)", "mln"),
        ("fx_reval", "Валютная переоценка долга", "mln"),
    ]:
        label_row(ws, REG[f"DT.{key}"], label, unit)
    ws.cell(REG["DT.term_close"], 1).font = F_LABEL_B

    # ── C. REVOLVING CREDIT ──
    section_header(ws, REG["DT.rc_limit"] - 1, "C. REVOLVING CREDIT (RC)")
    for key, label, unit in [
        ("rc_limit", "Лимит RC", "mln"),
        ("rc_open", "RC, начало", "mln"),
        ("rc_draw", "RC draw", "mln"),
        ("rc_repay", "RC repay (cash sweep + term-out)", "mln"),
        ("rc_close", "RC, конец", "mln"),
        ("rc_util", "Utilization (RC / лимит)", "%"),
        ("funding_gap", "Привлечено по штрафной ставке", "mln"),
        ("funding_gap_accum", "Долг по штрафной ставке (накопл.)", "mln"),
    ]:
        label_row(ws, REG[f"DT.{key}"], label, unit)
    ws.cell(REG["DT.funding_gap"], 1).font = F_LABEL_B
    ws.cell(REG["DT.funding_gap_accum"], 1).font = F_LABEL_B

    # ── D. TOTAL DEBT ──
    section_header(ws, REG["DT.open"] - 1, "D. ИТОГО ДОЛГ")
    label_row(ws, REG["DT.open"], "Долг, начало периода", "mln")
    label_row(ws, REG["DT.close"], "Долг, конец периода", "mln")
    ws.cell(REG["DT.close"], 1).font = F_LABEL_B

    # ── E. INTEREST ──
    section_header(ws, REG["DT.interest_term"] - 1, "E. ПРОЦЕНТНЫЕ РАСХОДЫ")
    for key, label, unit in [
        ("interest_term", "Проценты по срочному долгу", "mln"),
        ("interest_rc", "Проценты по RC", "mln"),
        ("commit_fee", "Комиссия за неисп. лимит", "mln"),
        ("interest", "ИТОГО проценты", "mln"),
        ("avg_rate", "Средневзвешенная ставка", "%"),
    ]:
        label_row(ws, REG[f"DT.{key}"], label, unit)
    ws.cell(REG["DT.interest"], 1).font = F_LABEL_B

    # ── F. ST/LT ──
    section_header(ws, REG["DT.st"] - 1, "F. ST / LT РАЗБИВКА")
    label_row(ws, REG["DT.st"], "Краткосрочный долг (ST)", "mln",
              "schedule_ST + RC + covenant reclass")
    label_row(ws, REG["DT.lt"], "Долгосрочный долг (LT)", "mln")
    label_row(ws, REG["DT.nd"], "Чистый долг (ND)", "mln")
    label_row(ws, REG["DT.nd_ebitda"], "ND / EBITDA", "x")

    # ══════════════ FORMULAS ══════════════
    # CP references (dynamic rows set by build_control_panel)
    cp_min_cash = f"'Control_Panel'!$C${REG.get('CP.min_cash', 55)}"
    cp_rc_limit = f"'Control_Panel'!$C${REG.get('CP.rc_limit', 56)}"
    cp_rc_rate = f"'Control_Panel'!$C${REG.get('CP.rc_rate', 57)}"
    cp_commit_fee = f"'Control_Panel'!$C${REG.get('CP.commit_fee_rate', 58)}"
    cp_maint_share = f"'Control_Panel'!$C${REG.get('CP.maint_share', 59)}"
    cp_sweep_pct = f"'Control_Panel'!$C${REG.get('CP.sweep_pct', 60)}"
    cp_target_lev = f"'Control_Panel'!$C${REG.get('CP.target_leverage', 61)}"
    cp_buffer = f"'Control_Panel'!$C${REG.get('CP.buffer', 62)}"

    last_fc_idx = 3 + n_hist + len(cfg["fc_years"]) - 1
    for c_idx in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c_idx)
        prev = get_column_letter(c_idx - 1)
        is_last_fc = (c_idx == last_fc_idx)
        next_cl = get_column_letter(c_idx + 1) if not is_last_fc else cl

        # ── Refs to other sheets (non-circular) ──
        ebitda_ref = f"'{NAME['PL']}'!{cl}${REG['PL.ebitda']}"
        capex_ref = f"'{NAME['PP']}'!{cl}${REG['PP.capex']}"
        da_ref = f"'{NAME['PP']}'!{cl}${REG['PP.dep_charge']}"
        wc_ref = f"'{NAME['WC']}'!{cl}${REG['WC.delta_nwc']}"
        ni_ref = f"'{NAME['PL']}'!{cl}${REG['PL.ni']}"
        div_ref = f"ABS('{NAME['EQ']}'!{cl}${REG['EQ.div']})"
        cash_prev = f"'{NAME['BS']}'!{prev}${REG['BS.cash']}"
        tax_current = f"'{NAME['TX']}'!{cl}${REG['TX.current']}"

        # Interest estimate: term debt only, opening balance × avg_rate (non-circular)
        interest_term_est = f"{cl}{REG['DT.term_open']}*{cl}{REG['DT.avg_rate']}"

        # ── A. SOURCES & USES formulas ──
        # Sources
        formula_cell(ws, REG["DT.su_oper_flow"], c_idx,
                     f"={ebitda_ref}-{tax_current}", FMT_MLN)
        formula_cell(ws, REG["DT.su_maint_capex"], c_idx,
                     f"=ABS({capex_ref})*{cp_maint_share}", FMT_MLN)
        formula_cell(ws, REG["DT.su_growth_capex"], c_idx,
                     f"=ABS({capex_ref})*(1-{cp_maint_share})", FMT_MLN)
        formula_cell(ws, REG["DT.su_delta_nwc"], c_idx,
                     f"=MAX(0,{wc_ref})", FMT_MLN)
        # su_mandatory ← term mandatory
        ref_cell(ws, REG["DT.su_mandatory"], c_idx,
                 f"=ABS({cl}{REG['DT.mandatory']})", FMT_MLN)
        # su_interest ← term interest estimate (no RC — pre-RC view)
        formula_cell(ws, REG["DT.su_interest"], c_idx,
                     f"={cl}{REG['DT.interest_term']}", FMT_MLN)
        formula_cell(ws, REG["DT.su_dividends"], c_idx,
                     f"={div_ref}", FMT_MLN)
        # Total uses
        su_use_rows = [REG[f"DT.su_{k}"] for k in
                       ["maint_capex", "growth_capex", "delta_nwc",
                        "mandatory", "interest", "dividends"]]
        formula_cell(ws, REG["DT.su_total_uses"], c_idx,
                     "=" + "+".join(f"{cl}{r}" for r in su_use_rows),
                     FMT_MLN, bold=True)

        # Sources
        ref_cell(ws, REG["DT.su_refi"], c_idx,
                 f"={cl}{REG['DT.refi']}", FMT_MLN)
        formula_cell(ws, REG["DT.su_excess_cash"], c_idx,
                     f"=MAX(0,{cash_prev}-{cp_min_cash})", FMT_MLN)
        formula_cell(ws, REG["DT.su_total_sources"], c_idx,
                     f"={cl}{REG['DT.su_oper_flow']}+{cl}{REG['DT.su_refi']}"
                     f"+{cl}{REG['DT.su_excess_cash']}",
                     FMT_MLN, bold=True)

        # Gap = actual debt issuance: RC_draw + new_term (includes term_out)
        # This equals funding_need + term_out, so S&U check = 0 always
        formula_cell(ws, REG["DT.su_gap"], c_idx,
                     f"={cl}{REG['DT.rc_draw']}+{cl}{REG['DT.new_term']}",
                     FMT_MLN, bold=True)
        formula_cell(ws, REG["DT.su_maint_gap"], c_idx,
                     f"=MAX(0,{cl}{REG['DT.su_maint_capex']}"
                     f"-{cl}{REG['DT.su_oper_flow']})",
                     FMT_MLN)

        # ── B. TERM DEBT corkscrew ──
        # term_open = prev term_close + prev FX_reval (carry revaluation forward)
        formula_cell(ws, REG["DT.term_open"], c_idx,
                     f"={prev}{REG['DT.term_close']}+{prev}{REG['DT.fx_reval']}", FMT_MLN)
        # Mandatory — input, filled by fill_data from schedule
        input_cell(ws, REG["DT.mandatory"], c_idx, 0, FMT_MLN)
        # Refi — input, filled by fill_data (= mandatory × refi_pct)
        input_cell(ws, REG["DT.refi"], c_idx, 0, FMT_MLN)

        # ── cash_before_RC: from CF totals ──
        # NO CIRCULAR because RC_interest = opening × rate (deterministic)
        # RC_opening(T) = RC_close(T-1) — known from previous year
        # → interest(T) deterministic → NI deterministic → CFO deterministic
        # → cash_before_RC = cash_open + CFO + CFI + CFF_no_RC — NO CYCLE
        cff_no_rc_ref = f"'{NAME['CF']}'!{cl}${REG['CF.cff_no_rc']}"
        cfo_ref = f"'{NAME['CF']}'!{cl}${REG['CF.cfo']}"
        cfi_ref = f"'{NAME['CF']}'!{cl}${REG['CF.cfi']}"

        label_row(ws, REG["DT.cash_before_rc"], "ДС до RC (из CF, без кольца)", "mln") if c_idx == 3 + n_hist else None
        formula_cell(ws, REG["DT.cash_before_rc"], c_idx,
                     f"={cash_prev}+{cfo_ref}+{cfi_ref}+{cff_no_rc_ref}", FMT_MLN)

        # ── Covenant check ──
        cp_new_debt = f"'Control_Panel'!$C${REG.get('CP.new_debt_available', 70)}"
        cp_cov_nd = f"'Control_Panel'!$C${REG.get('CP.cov_nd_ebitda', 71)}"
        # Covenant breach: EBITDA ≤ 0 is ALWAYS breach (negative ratio ≠ "OK")
        prev_ebitda = f"'{NAME['PL']}'!{prev}${REG['PL.ebitda']}"
        prev_nd_ebitda = f"IFERROR({prev}{REG['DT.nd']}/{prev_ebitda},99)"
        cov_breach = f"OR({prev_ebitda}<=0,{prev_nd_ebitda}>{cp_cov_nd})"

        cbrc = f"{cl}{REG['DT.cash_before_rc']}"

        # ── FUNDING NEED = MAX(0, min_cash - cash_before_RC) ──
        # Exact: CF is deterministic (RC interest from opening, no cycle)
        # No analytical correction needed — CF already includes all items
        need = f"{cl}{REG['DT.funding_need']}"
        formula_cell(ws, REG["DT.funding_need"], c_idx,
                     f"=MAX(0,{cp_min_cash}-{cbrc})", FMT_MLN)

        # ── RC DRAW: covers need up to free limit ──
        free_limit = f"MAX(0,{cl}{REG['DT.rc_limit']}-{cl}{REG['DT.rc_open']})"
        formula_cell(ws, REG["DT.rc_draw"], c_idx,
                     f"=IFERROR(MIN({free_limit},{need}),0)", FMT_MLN)

        # ── Residual after RC ──
        residual = f"MAX(0,{need}-{cl}{REG['DT.rc_draw']})"

        # ── TERM-OUT: if utilization > trigger, convert RC to term ──
        cp_rc_trigger = f"'Control_Panel'!$C${REG.get('CP.rc_trigger', 65)}"
        util_after = f"IFERROR(({cl}{REG['DT.rc_open']}+{cl}{REG['DT.rc_draw']})/{cl}{REG['DT.rc_limit']},0)"
        term_out = f"IF({util_after}>{cp_rc_trigger},({cl}{REG['DT.rc_open']}+{cl}{REG['DT.rc_draw']})-{cp_rc_trigger}*{cl}{REG['DT.rc_limit']},0)"

        # ── NEW TERM: covers residual + term-out ──
        # Gate determines RATE, not ACCESS: model finances the company
        # When covenant breach → debt at penalty_rate, capped by penalty_limit
        # If penalty_limit > 0 AND gate closed: new_term ≤ penalty_limit, rest → real gap
        cp_cov_icr = f"'Control_Panel'!$C${REG.get('CP.cov_icr', 78)}"
        prev_icr = f"IFERROR('{NAME['RA']}'!{prev}${REG['RA.icr']},99)"
        gate = f"AND({cp_new_debt}=1,NOT({cov_breach}),{prev_icr}>={cp_cov_icr})"
        cp_pen_limit = f"'Control_Panel'!$C${REG.get('CP.penalty_limit', 73)}"
        full_need = f"({residual}+{term_out})"
        # Gate open: full amount at normal rate
        # Gate closed, limit=0: full amount at penalty rate (unlimited)
        # Gate closed, limit>0: MIN(need, limit) at penalty, rest = unfunded gap
        gated_amount = f"IF({cp_pen_limit}>0,MIN({full_need},{cp_pen_limit}),{full_need})"
        formula_cell(ws, REG["DT.new_term"], c_idx,
                     f"=IFERROR(IF({gate},{full_need},{gated_amount}),0)",
                     FMT_MLN)

        # ── Voluntary term: after RC repay, with covenant stops ──
        est_nd = f"({cl}{REG['DT.term_open']}-{cash_prev})"
        vol_available = f"MAX(0,{cbrc}-{cp_min_cash}-{cp_buffer}-{cl}{REG['DT.rc_open']})"
        # Voluntary: waterfall RC → ST → LT, with covenant stops
        # Stop 1: not if covenant breach
        # Stop 2: not if NI < 0
        # Stop 3: only if overleveraged (ND/EBITDA > target)
        # Priority: RC already repaid via cash sweep.
        #   Then: ST term first (cheaper to prepay, reduces refi peak)
        #   Then: LT (with prepay premium)
        cp_prepay_prem = f"'Control_Panel'!$C${REG.get('CP.prepay_premium', 72)}"
        # Max voluntary by leverage target
        vol_max_lev = f"MAX(0,{est_nd}-{cp_target_lev}*ABS({ebitda_ref}))"
        # Total available
        vol_total = f"MIN({vol_available}*{cp_sweep_pct},{vol_max_lev})"
        # ST balance proxy: prev year ST debt (from DT.st)
        st_balance = f"IFERROR({prev}{REG['DT.st']},0)"
        # vol_st = MIN(total, ST balance) — repay ST first, no premium
        vol_st = f"MIN({vol_total},{st_balance})"
        # vol_lt = remaining × (1/(1+premium)) — LT with prepay cost
        vol_lt = f"MAX(0,{vol_total}-{vol_st})/(1+{cp_prepay_prem})"
        # voluntary_term = vol_st + vol_lt
        formula_cell(ws, REG["DT.voluntary_term"], c_idx,
                     f"=IFERROR(IF(AND(IFERROR({ni_ref},0)>0,"
                     f"NOT({cov_breach}),"
                     f"IFERROR({est_nd}/ABS({ebitda_ref}),99)>{cp_target_lev}),"
                     f"MAX(0,{vol_st}+{vol_lt}),"
                     f"0),0)",
                     FMT_MLN)

        # term_close = open - mandatory + refi + new_term - voluntary
        formula_cell(ws, REG["DT.term_close"], c_idx,
                     f"={cl}{REG['DT.term_open']}"
                     f"-ABS({cl}{REG['DT.mandatory']})"
                     f"+{cl}{REG['DT.refi']}"
                     f"+{cl}{REG['DT.new_term']}"
                     f"-ABS({cl}{REG['DT.voluntary_term']})",
                     FMT_MLN, bold=True)

        # ── C. REVOLVING CREDIT ──
        # RC limit from CP
        ref_cell(ws, REG["DT.rc_limit"], c_idx,
                 f"={cp_rc_limit}", FMT_MLN)
        # RC open = prev close
        formula_cell(ws, REG["DT.rc_open"], c_idx,
                     f"={prev}{REG['DT.rc_close']}", FMT_MLN)

        # RC repay = cash sweep + term-out
        # Cash sweep: if cash_before_RC > min_cash, repay RC
        sweep = f"MIN({cl}{REG['DT.rc_open']}+{cl}{REG['DT.rc_draw']},MAX(0,{cbrc}-{cp_min_cash}))"
        # Term-out portion: if new_term includes term-out, reduce RC
        term_out_actual = f"IF({cl}{REG['DT.new_term']}>0,MIN({term_out},{cl}{REG['DT.new_term']}),0)"
        formula_cell(ws, REG["DT.rc_repay"], c_idx,
                     f"=IFERROR({sweep}+{term_out_actual},0)",
                     FMT_MLN)

        # RC close = open + draw - repay
        formula_cell(ws, REG["DT.rc_close"], c_idx,
                     f"={cl}{REG['DT.rc_open']}"
                     f"+{cl}{REG['DT.rc_draw']}"
                     f"-{cl}{REG['DT.rc_repay']}",
                     FMT_MLN, bold=True)

        # Utilization
        formula_cell(ws, REG["DT.rc_util"], c_idx,
                     f"=IFERROR({cl}{REG['DT.rc_close']}/{cl}{REG['DT.rc_limit']},0)",
                     FMT_PCT)

        # Penalty-financed portion = new_term attracted at penalty_rate
        # Gate open → 0; Gate closed → new_term (= capped by penalty_limit if set)
        formula_cell(ws, REG["DT.funding_gap"], c_idx,
                     f"=IFERROR(IF({gate},0,{cl}{REG['DT.new_term']}),0)",
                     FMT_MLN)
        # Accumulated = total outstanding penalty-rate debt
        formula_cell(ws, REG["DT.funding_gap_accum"], c_idx,
                     f"={prev}{REG['DT.funding_gap_accum']}+{cl}{REG['DT.funding_gap']}",
                     FMT_MLN)

        # ── D. TOTAL DEBT ──
        formula_cell(ws, REG["DT.open"], c_idx,
                     f"={cl}{REG['DT.term_open']}+{cl}{REG['DT.rc_open']}",
                     FMT_MLN)
        # FX revaluation = debt × currency_share × fx_change
        # CNY share from Raw_IFRS instruments, FX change from CP
        ri_s = REG.get("RI.debt_start_row", 69)
        ri_e = REG.get("RI.debt_end_row", 89)
        cp_fx_cny_chg = f"'Control_Panel'!$C${REG.get('CP.fx_usdcny_chg', 75)}"
        cp_fx_rub_chg = f"'Control_Panel'!$C${REG.get('CP.fx_usdrub_chg', 76)}"
        # CNY share = SUMPRODUCT(balance × (CCY="CNY")) / SUM(balance)
        cny_share = (f"IFERROR(SUMPRODUCT('{NAME['RI']}'!D${ri_s}:D${ri_e},"
                     f"('{NAME['RI']}'!C${ri_s}:C${ri_e}=\"CNY\")*1)"
                     f"/SUM('{NAME['RI']}'!D${ri_s}:D${ri_e}),0)")
        rub_share = (f"IFERROR(SUMPRODUCT('{NAME['RI']}'!D${ri_s}:D${ri_e},"
                     f"('{NAME['RI']}'!C${ri_s}:C${ri_e}=\"RUB\")*1)"
                     f"/SUM('{NAME['RI']}'!D${ri_s}:D${ri_e}),0)")
        # FX effect = -close × (cny_share × cny_chg + rub_share × rub_chg)
        # Per-year FX from 05_Drivers
        # Per-year FX from 05_Drivers for both CNY and RUB
        dr_fx_rub = REG.get("DR.fx_usdrub_chg")
        dr_fx_cny = REG.get("DR.fx_usdcny_chg")
        fx_rub_yr = f"'{NAME['DR']}'!{cl}${dr_fx_rub}" if dr_fx_rub else cp_fx_rub_chg
        fx_cny_yr = f"'{NAME['DR']}'!{cl}${dr_fx_cny}" if dr_fx_cny else cp_fx_cny_chg
        formula_cell(ws, REG["DT.fx_reval"], c_idx,
                     f"=-{cl}{REG['DT.term_close']}*({cny_share}*{fx_cny_yr}"
                     f"+{rub_share}*{fx_rub_yr})",
                     FMT_MLN)

        formula_cell(ws, REG["DT.close"], c_idx,
                     f"={cl}{REG['DT.term_close']}+{cl}{REG['DT.rc_close']}"
                     f"+{cl}{REG['DT.fx_reval']}",
                     FMT_MLN, bold=True)

        # ── E. INTEREST ──
        # Term interest: from _Debt_Schedule total (fill_data overrides)
        # Default: OPENING × avg_rate (not avg — avoids circular)
        formula_cell(ws, REG["DT.interest_term"], c_idx,
                     f"={cl}{REG['DT.term_open']}*{cl}{REG['DT.avg_rate']}",
                     FMT_MLN)
        # RC interest: opening × (KeyRate + RC spread from CP)
        # KeyRate from Raw_IFRS for each forecast year
        ri_kr = REG.get("RI.kr_row")
        yr_idx_rc = c_idx - (3 + n_hist)
        if ri_kr:
            kr_ref = f"'{NAME['RI']}'!{get_column_letter(7 + yr_idx_rc)}${ri_kr}"
            formula_cell(ws, REG["DT.interest_rc"], c_idx,
                         f"={cl}{REG['DT.rc_open']}*({kr_ref}+{cp_rc_rate})",
                         FMT_MLN)
        else:
            formula_cell(ws, REG["DT.interest_rc"], c_idx,
                         f"={cl}{REG['DT.rc_open']}*{cp_rc_rate}",
                         FMT_MLN)
        # Commitment fee: (limit - opening) × fee_rate
        formula_cell(ws, REG["DT.commit_fee"], c_idx,
                     f"=({cl}{REG['DT.rc_limit']}-{cl}{REG['DT.rc_open']})"
                     f"*{cp_commit_fee}",
                     FMT_MLN)
        # Penalty interest on accumulated funding gap (opening balance × penalty_rate)
        # Uses opening gap_accum (= prev close) to avoid circularity
        cp_penalty_rate = f"'Control_Panel'!$C${REG.get('CP.penalty_rate', 72)}"
        penalty_int = f"{prev}{REG['DT.funding_gap_accum']}*{cp_penalty_rate}"
        # Total interest = term + RC + fee + penalty
        formula_cell(ws, REG["DT.interest"], c_idx,
                     f"={cl}{REG['DT.interest_term']}"
                     f"+{cl}{REG['DT.interest_rc']}"
                     f"+{cl}{REG['DT.commit_fee']}"
                     f"+{penalty_int}",
                     FMT_MLN, bold=True)
        # Avg rate = total interest / total opening balance (from _Debt_Schedule)
        ds_total = REG.get("DS.total_row", 27)
        ds_yr_start = REG.get("DS.yr_start_col", 8)
        ds_cols_per = REG.get("DS.cols_per_year", 5)
        yr_idx = c_idx - (3 + n_hist)
        ds_open_col = get_column_letter(ds_yr_start + yr_idx * ds_cols_per)      # Open
        ds_int_col = get_column_letter(ds_yr_start + yr_idx * ds_cols_per + 3)   # Interest
        formula_cell(ws, REG["DT.avg_rate"], c_idx,
                     f"=IFERROR('{NAME['DS']}'!{ds_int_col}${ds_total}"
                     f"/'{NAME['DS']}'!{ds_open_col}${ds_total},0.08)",
                     FMT_PCT)

        # ── F. ST/LT: mandatory next year + RC + covenant reclass ──
        # ST = mandatory payments due within 12 months + RC balance
        # This avoids static text maturity issues (audit defect 3)
        # Next year mandatory: from _Debt_Schedule next year block (fill_data sets)
        # Default: use mandatory from this year as proxy
        cp_cov_reclass = f"'Control_Panel'!$C${REG.get('CP.cov_reclass', 75)}"
        cov_breached = f"OR({prev_ebitda}<=0,{prev_nd_ebitda}>{cp_cov_nd},{prev_icr}<{cp_cov_icr})"
        reclass = f"AND({cp_cov_reclass}=1,{cov_breached})"
        # Normal ST = mandatory(NEXT year per IAS 1) + RC close
        # IAS 1: current liabilities = due within 12 months from balance date
        # On 31.12.2026, ST = mandatory_2027 + RC
        # Last forecast year: avg ST share from prior 2 years × close (no 2029 col)
        if is_last_fc:
            prev2 = get_column_letter(c_idx - 2)
            avg_st_share = (f"IFERROR(({prev}{REG['DT.st']}/{prev}{REG['DT.close']}"
                           f"+{prev2}{REG['DT.st']}/{prev2}{REG['DT.close']})/2,0.5)")
            st_normal = f"{cl}{REG['DT.close']}*{avg_st_share}"
        else:
            st_mand = f"{next_cl}{REG['DT.mandatory']}"
            st_normal = f"{st_mand}+{cl}{REG['DT.rc_close']}"
        # LT independent = total - ST (not residual — allows real check)
        lt_normal = f"MAX(0,{cl}{REG['DT.close']}-({st_normal}))"
        # With reclass: all debt becomes ST
        formula_cell(ws, REG["DT.st"], c_idx,
                     f"=IF({reclass},{cl}{REG['DT.close']},"
                     f"MIN({cl}{REG['DT.close']},{st_normal}))", FMT_MLN)
        formula_cell(ws, REG["DT.lt"], c_idx,
                     f"=IF({reclass},0,{lt_normal})", FMT_MLN)
        # Net Debt
        formula_cell(ws, REG["DT.nd"], c_idx,
                     f"={cl}{REG['DT.close']}-'{NAME['BS']}'!{cl}${REG['BS.cash']}",
                     FMT_MLN, bold=True)
        # ND/EBITDA
        formula_cell(ws, REG["DT.nd_ebitda"], c_idx,
                     f"=IFERROR({cl}{REG['DT.nd']}/{ebitda_ref},0)",
                     FMT_MULT)

    # Historical inputs — formulas from 02_Hist for ALL hist years
    hi_st = REG.get("HI.st_debt")
    hi_lt = REG.get("HI.lt_debt")
    hi_cash = REG.get("HI.cash")
    hi_int = REG.get("HI.interest")
    for hc in range(3, 3 + n_hist):
        cl_h = get_column_letter(hc)
        if hi_st and hi_lt:
            td = f"ABS('{NAME['HI']}'!{cl_h}${hi_st})+ABS('{NAME['HI']}'!{cl_h}${hi_lt})"
            for k in ["term_open", "term_close", "open", "close"]:
                ref_cell(ws, REG[f"DT.{k}"], hc, f"={td}", FMT_MLN)
            ref_cell(ws, REG["DT.st"], hc, f"=ABS('{NAME['HI']}'!{cl_h}${hi_st})", FMT_MLN)
            ref_cell(ws, REG["DT.lt"], hc, f"=ABS('{NAME['HI']}'!{cl_h}${hi_lt})", FMT_MLN)
            if hi_cash:
                ref_cell(ws, REG["DT.nd"], hc, f"={td}-ABS('{NAME['HI']}'!{cl_h}${hi_cash})", FMT_MLN)
        if hi_int:
            ref_cell(ws, REG["DT.interest_term"], hc, f"=ABS('{NAME['HI']}'!{cl_h}${hi_int})", FMT_MLN)
            ref_cell(ws, REG["DT.interest"], hc, f"=ABS('{NAME['HI']}'!{cl_h}${hi_int})", FMT_MLN)
        if hi_int and hi_st and hi_lt:
            formula_cell(ws, REG["DT.avg_rate"], hc,
                         f"=IFERROR(ABS('{NAME['HI']}'!{cl_h}${hi_int})/({td}),0.08)", FMT_PCT)
        input_cell(ws, REG["DT.rc_open"], hc, 0, FMT_MLN)
        input_cell(ws, REG["DT.rc_close"], hc, 0, FMT_MLN)
        ref_cell(ws, REG["DT.rc_limit"], hc, f"='Control_Panel'!$C${REG.get('CP.rc_limit',56)}", FMT_MLN)
        input_cell(ws, REG["DT.funding_gap_accum"], hc, 0, FMT_MLN)
        input_cell(ws, REG["DT.funding_need"], hc, 0, FMT_MLN)
        input_cell(ws, REG["DT.fx_reval"], hc, 0, FMT_MLN)

    # ── G. HISTORICAL CALIBRATION (informational) ──
    section_header(ws, REG["DT.cal_st_share"] - 1,
                   "G. КАЛИБРОВКА ПО ИСТОРИИ (информационно)")
    for key, label, fmt in [
        ("cal_st_share", "Историческая доля ST = ST/(ST+LT)", FMT_PCT),
        ("cal_maint_share", "D&A / CapEx (подд. CapEx ≈)", FMT_PCT),
        ("cal_spread", "Спред к базовой ставке", FMT_PCT2),
        ("cal_tenor", "Средний тенор инструментов, лет", FMT_RATIO),
        ("cal_debt_capex", "Δ Долг − Refi / CapEx", FMT_PCT),
        ("cal_st_flag", "Флаг: модельная ST/LT ≠ ист. ±15 п.п.", ""),
    ]:
        label_row(ws, REG[f"DT.{key}"], label, "")
    # Calibration formulas for last hist column
    lhc = 3 + n_hist - 1
    cl_lh = get_column_letter(lhc)
    if hi_st and hi_lt:
        formula_cell(ws, REG["DT.cal_st_share"], lhc,
                     f"=IFERROR({cl_lh}{REG['DT.st']}/({cl_lh}{REG['DT.st']}+{cl_lh}{REG['DT.lt']}),0)", FMT_PCT)
    hi_da = REG.get("HI.da")
    hi_capex = REG.get("HI.capex")
    if hi_da and hi_capex:
        formula_cell(ws, REG["DT.cal_maint_share"], lhc,
                     f"=IFERROR(ABS('{NAME['HI']}'!{cl_lh}${hi_da})/ABS('{NAME['HI']}'!{cl_lh}${hi_capex}),0)", FMT_PCT)
    ri_kr = REG.get("RI.kr_row")
    if ri_kr:
        formula_cell(ws, REG["DT.cal_spread"], lhc,
                     f"=MAX(0,{cl_lh}{REG['DT.avg_rate']}-'{NAME['RI']}'!G${ri_kr})", FMT_PCT2)
    # Avg tenor = SUMPRODUCT(balance × (maturity_year - last_yr)) / SUM(balance)
    # Extract year from maturity text via RIGHT(text,4)
    ri_s = REG.get("RI.debt_start_row", 69)
    ri_e = REG.get("RI.debt_end_row", 89)
    last_yr = cfg["hist_years"][-1]
    formula_cell(ws, REG["DT.cal_tenor"], lhc,
                 f"=IFERROR(SUMPRODUCT('{NAME['RI']}'!D${ri_s}:D${ri_e},"
                 f"MAX(0,VALUE(RIGHT('{NAME['RI']}'!F${ri_s}:F${ri_e},4))-{last_yr}))"
                 f"/SUM('{NAME['RI']}'!D${ri_s}:D${ri_e}),2)",
                 FMT_RATIO)


def build_lease(wb, cfg):
    """18_Lease — IFRS 16 ROU asset + lease liability corkscrew."""
    ws = wb["18_Lease"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"18_Lease — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "IFRS 16: ROU Asset dep + Lease Liability interest/payment").font = F_SUBTITLE
    n_hist = len(cfg["hist_years"][-3:])
    year_headers(ws, 4, cfg["hist_years"][-3:], cfg["fc_years"])

    section_header(ws, 6, "ROU ASSET (ПРАВО ПОЛЬЗОВАНИЯ)")
    rou_items = [
        ("rou_open", "ROU начало", "mln"),
        ("rou_dep", "Амортизация ROU", "mln"),
        ("rou_close", "ROU конец", "mln"),
    ]
    for key, label, unit in rou_items:
        r = REG[f"LS.{key}"]
        label_row(ws, r, label, unit)

    section_header(ws, REG["LS.liab_open"] - 1, "LEASE LIABILITY (ОБЯЗАТЕЛЬСТВО)")
    liab_items = [
        ("liab_open", "Обязательство, начало", "mln"),
        ("liab_int", "Процент по аренде", "mln"),
        ("liab_pay", "Арендный платёж", "mln"),
        ("liab_close", "Обязательство, конец", "mln"),
    ]
    for key, label, unit in liab_items:
        r = REG[f"LS.{key}"]
        label_row(ws, r, label, unit)

    # Formulas
    for c_idx in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c_idx)
        prev = get_column_letter(c_idx - 1)

        # ROU: open = prev close
        formula_cell(ws, REG["LS.rou_open"], c_idx, f"={prev}{REG['LS.rou_close']}", FMT_MLN)
        # ROU dep (input or formula: open / remaining_life)
        input_cell(ws, REG["LS.rou_dep"], c_idx, 0, FMT_MLN)
        # ROU close = open - dep
        formula_cell(ws, REG["LS.rou_close"], c_idx,
                     f"={cl}{REG['LS.rou_open']}-ABS({cl}{REG['LS.rou_dep']})", FMT_MLN)

        # Liab: open = prev close
        formula_cell(ws, REG["LS.liab_open"], c_idx, f"={prev}{REG['LS.liab_close']}", FMT_MLN)
        # Interest = open × discount_rate (input)
        formula_cell(ws, REG["LS.liab_int"], c_idx,
                     f"={cl}{REG['LS.liab_open']}*'Control_Panel'!$C${REG.get('CP.rc_rate', 56)}*0.5",
                     FMT_MLN)  # Lease discount ≈ 50% of RC rate as proxy
        # Payment (input)
        input_cell(ws, REG["LS.liab_pay"], c_idx, 0, FMT_MLN)
        # Close = open + interest - payment
        formula_cell(ws, REG["LS.liab_close"], c_idx,
                     f"={cl}{REG['LS.liab_open']}+{cl}{REG['LS.liab_int']}-ABS({cl}{REG['LS.liab_pay']})",
                     FMT_MLN)

    # Historical opening (last hist year)
    for k in ["rou_open", "rou_close", "liab_open", "liab_close"]:
        input_cell(ws, REG[f"LS.{k}"], 3, 0, FMT_MLN)


def build_cf(wb, cfg):
    """23_CF — Cash Flow Statement (indirect method)."""
    ws = wb["23_CF"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"23_CF — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "ОДДС (косвенный метод)").font = F_SUBTITLE
    n_hist = len(cfg["hist_years"][-3:])
    year_headers(ws, 4, cfg["hist_years"][-3:], cfg["fc_years"])

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
        # Debt draw ← Debt (refi + new_term + RC_draw)
        formula_cell(ws, REG["CF.debt_draw"], c_idx,
                     f"='{NAME['DT']}'!{cl}${REG['DT.refi']}"
                     f"+'{NAME['DT']}'!{cl}${REG['DT.new_term']}"
                     f"+'{NAME['DT']}'!{cl}${REG['DT.rc_draw']}",
                     FMT_MLN)
        # Debt repay ← Debt (mandatory + voluntary_term + RC_repay)
        formula_cell(ws, REG["CF.debt_repay"], c_idx,
                     f"='{NAME['DT']}'!{cl}${REG['DT.mandatory']}"
                     f"+'{NAME['DT']}'!{cl}${REG['DT.voluntary_term']}"
                     f"+'{NAME['DT']}'!{cl}${REG['DT.rc_repay']}",
                     FMT_MLN)
        # Lease pay ← Lease
        ref_cell(ws, REG["CF.lease_pay"], c_idx,
                 f"='{NAME['LS']}'!{cl}${REG['LS.liab_pay']}", FMT_MLN)
        # Dividends ← Equity
        ref_cell(ws, REG["CF.div_paid"], c_idx,
                 f"='{NAME['EQ']}'!{cl}${REG['EQ.div']}", FMT_MLN)
        # Other non-cash: ΔTaxPay + Lease_dep + Lease_int + FX_reval_reversal
        formula_cell(ws, REG["CF.other_noncash"], c_idx,
                     f"='{NAME['BS']}'!{cl}${REG['BS.tax_pay']}-'{NAME['BS']}'!{prev}${REG['BS.tax_pay']}"
                     f"+ABS('{NAME['LS']}'!{cl}${REG['LS.rou_dep']})"
                     f"+'{NAME['LS']}'!{cl}${REG['LS.liab_int']}"
                     f"+'{NAME['DT']}'!{cl}${REG['DT.fx_reval']}",
                     FMT_MLN)
        # Interest paid: 0 in CFF (interest flows through NI in CFO)
        # US GAAP style: interest is operating, not financing
        formula_cell(ws, REG["CF.interest_paid"], c_idx, "=0", FMT_MLN)

        # CFO = NI + DA + impairment + deferred_tax - WC_change - associates + other_noncash
        # Associates: non-cash equity method income, subtract from CFO
        # FX reval: in other_noncash (not separate — matches auditor's fix)
        assoc_adj = f"-'{NAME['OI']}'!{cl}${REG['OI.associates']}"
        cfo_parts = [f"{cl}{REG['CF.ni']}", f"{cl}{REG['CF.da']}", f"{cl}{REG['CF.impairment']}",
                     f"{cl}{REG['CF.deferred_tax']}", f"-{cl}{REG['CF.wc_change']}",
                     assoc_adj,
                     f"{cl}{REG['CF.other_noncash']}"]
        formula_cell(ws, r_cfo, c_idx, "=" + "+".join(cfo_parts), FMT_MLN, bold=True)

        # Disposal proceeds = gross disposal - accumulated dep portion (net book value)
        formula_cell(ws, REG["CF.disp_proceeds"], c_idx,
                     f"='{NAME['PP']}'!{cl}${REG['PP.disp_gross']}"
                     f"-'{NAME['PP']}'!{cl}${REG['PP.dep_disp']}",
                     FMT_MLN)
        # CFI = -capex + disp + other
        formula_cell(ws, r_cfi, c_idx,
                     f"=-ABS({cl}{REG['CF.capex']})+{cl}{REG['CF.disp_proceeds']}+{cl}{REG['CF.other_cfi']}",
                     FMT_MLN, bold=True)

        # CFF_без_RC_и_NewTerm: deterministic financing flows only
        # Excludes RC draw/repay AND new_term (both determined by the plug)
        # = refi - mandatory - voluntary_term - lease - div + other
        cff_no_rc = (f"='{NAME['DT']}'!{cl}${REG['DT.refi']}"
                     f"-ABS('{NAME['DT']}'!{cl}${REG['DT.mandatory']})"
                     f"-ABS('{NAME['DT']}'!{cl}${REG['DT.voluntary_term']})"
                     f"-ABS({cl}{REG['CF.lease_pay']})"
                     f"-ABS({cl}{REG['CF.div_paid']})"
                     f"+{cl}{REG['CF.other_cff']}")
        label_row(ws, REG["CF.cff_no_rc"], "CFF без RC", "mln") if c_idx == 3 + n_hist else None
        formula_cell(ws, REG["CF.cff_no_rc"], c_idx, cff_no_rc, FMT_MLN)

        # CFF = CFF_base + new_term + RC_draw - RC_repay
        formula_cell(ws, r_cff, c_idx,
                     f"={cl}{REG['CF.cff_no_rc']}"
                     f"+'{NAME['DT']}'!{cl}${REG['DT.new_term']}"
                     f"+'{NAME['DT']}'!{cl}${REG['DT.rc_draw']}"
                     f"-'{NAME['DT']}'!{cl}${REG['DT.rc_repay']}",
                     FMT_MLN, bold=True)

        # FX effect: reverse non-cash FX from NI
        # Debt reval: add back (was subtracted from PL.other_fin)
        # FX on cash = 0 (debt FX is non-cash, reversed in CFO other_noncash)
        formula_cell(ws, REG["CF.fx"], c_idx, "=0", FMT_MLN)

        # Net change = CFO + CFI + CFF (no separate FX — already in CFO reversal)
        formula_cell(ws, r_net, c_idx,
                     f"={cl}{r_cfo}+{cl}{r_cfi}+{cl}{r_cff}", FMT_MLN, bold=True)

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
    n_hist = len(cfg["hist_years"][-3:])
    year_headers(ws, 4, cfg["hist_years"][-3:], cfg["fc_years"])

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
        # NI from PL (parent only — subtract NCI share)
        nci_pct = cfg.get("nci_pct", 0.0)
        if nci_pct > 0:
            formula_cell(ws, REG["EQ.ni"], c_idx,
                         f"='{NAME['PL']}'!{cl}${REG['PL.ni']}*(1-{nci_pct})", FMT_MLN)
        else:
            ref_cell(ws, REG["EQ.ni"], c_idx,
                     f"='{NAME['PL']}'!{cl}${REG['PL.ni']}", FMT_MLN)
        # Dividends = NI × payout_ratio (from CP)
        # Covenant circuit: blocked if ND/EBITDA > covenant max
        cp_payout_row = REG.get("CP.payout_ratio")
        cp_cov_nd = REG.get("CP.cov_nd_ebitda")
        # Covenant check on PREVIOUS year ND/EBITDA
        if cp_cov_nd:
            cov_check = (f"IFERROR('{NAME['DT']}'!{prev}${REG['DT.nd']}"
                         f"/'{NAME['PL']}'!{prev}${REG['PL.ebitda']},0)"
                         f">'Control_Panel'!$C${cp_cov_nd}")
        else:
            cov_check = "FALSE"
        # Dividends from PREV year NI (breaks circular: NI→div→CF→cash→RC→interest→NI)
        # Dividends are declared by year-end results — methodologically correct
        if cp_payout_row:
            formula_cell(ws, REG["EQ.div"], c_idx,
                         f"=IF({cov_check},0,"
                         f"MAX(0,{prev}{REG['EQ.ni']})*'Control_Panel'!$C${cp_payout_row})",
                         FMT_MLN)
        else:
            payout = 0.6 if "Nornickel" in cfg.get("name", "") else 0.0
            if payout > 0:
                formula_cell(ws, REG["EQ.div"], c_idx,
                             f"=IF({cov_check},0,"
                             f"MAX(0,{prev}{REG['EQ.ni']})*{payout})",
                             FMT_MLN)

        # Buyback = MAX(0, NI) × buyback_pct (from CP), blocked by covenant
        cp_buyback = REG.get("CP.buyback_pct")
        if cp_buyback:
            formula_cell(ws, REG["EQ.buyback"], c_idx,
                         f"=IF({cov_check},0,"
                         f"MAX(0,{cl}{REG['EQ.ni']})*'Control_Panel'!$C${cp_buyback})",
                         FMT_MLN)

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
    n_hist = len(cfg["hist_years"][-3:])
    year_headers(ws, 4, cfg["hist_years"][-3:], cfg["fc_years"])

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

    # History: DTA/DTL from 02_Hist (last hist col)
    lhc = 3 + n_hist - 1
    cl_lh = get_column_letter(lhc)
    hi_dta = REG.get("HI.dta")
    hi_dtl = REG.get("HI.dtl")
    if hi_dta:
        ref_cell(ws, REG["TX.dta_open"], lhc, f"='{NAME['HI']}'!{cl_lh}${hi_dta}", FMT_MLN)
        ref_cell(ws, REG["TX.dta_close"], lhc, f"='{NAME['HI']}'!{cl_lh}${hi_dta}", FMT_MLN)
    if hi_dtl:
        ref_cell(ws, REG["TX.dtl_open"], lhc, f"='{NAME['HI']}'!{cl_lh}${hi_dtl}", FMT_MLN)
        ref_cell(ws, REG["TX.dtl_close"], lhc, f"='{NAME['HI']}'!{cl_lh}${hi_dtl}", FMT_MLN)

    # Tax formulas (forecast)
    for c_idx in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c_idx)
        prev = get_column_letter(c_idx - 1)

        # EBT from PL
        ref_cell(ws, REG["TX.ebt"], c_idx,
                 f"='{NAME['PL']}'!{cl}${REG['PL.ebt']}", FMT_MLN)
        # NOL open = prev close
        formula_cell(ws, REG["TX.nol_open"], c_idx, f"={prev}{REG['TX.nol_close']}", FMT_MLN)
        # NOL used = min(NOL_open, EBT × NOL_cap) — from CP
        cp_nol_cap = f"'Control_Panel'!$C${REG.get('CP.nol_cap', 82)}"
        formula_cell(ws, REG["TX.nol_used"], c_idx,
                     f"=MIN({cl}{REG['TX.nol_open']},MAX(0,{cl}{REG['TX.ebt']})*{cp_nol_cap})", FMT_MLN)
        # Taxable = EBT - NOL_used
        formula_cell(ws, REG["TX.taxable"], c_idx,
                     f"=MAX(0,{cl}{REG['TX.ebt']}-{cl}{REG['TX.nol_used']})", FMT_MLN)
        # Д7: Current tax = (taxable - timing_difference) × rate
        # Timing diff = tax_DA - book_DA = book_DA × 0.2 (Д7: 1.2 coefficient)
        cp_tax_rate = f"'Control_Panel'!$C${REG.get('CP.tax_rate', 80)}"
        book_da = f"'{NAME['PP']}'!{cl}${REG['PP.dep_charge']}"
        timing_diff = f"({book_da}*0.2)"  # tax DA is 20% higher than book
        formula_cell(ws, REG["TX.current"], c_idx,
                     f"=MAX(0,({cl}{REG['TX.taxable']}-{timing_diff}))*{cp_tax_rate}", FMT_MLN)
        # Total = current + deferred
        formula_cell(ws, REG["TX.total"], c_idx,
                     f"={cl}{REG['TX.current']}+{cl}{REG['TX.deferred']}", FMT_MLN, bold=True)
        # Effective rate
        formula_cell(ws, REG["TX.eff_rate"], c_idx,
                     f"=IFERROR({cl}{REG['TX.total']}/{cl}{REG['TX.ebt']},0)", FMT_PCT)
        # NOL close = open - used + new_losses (accumulate when EBT < 0)
        formula_cell(ws, REG["TX.nol_close"], c_idx,
                     f"={cl}{REG['TX.nol_open']}-{cl}{REG['TX.nol_used']}"
                     f"+MAX(0,-{cl}{REG['TX.ebt']})", FMT_MLN)

        # DTA/DTL: deferred tax from PPE timing difference
        # DTL grows when book depreciation < tax depreciation (accelerated)
        # Simplified: deferred_tax = (book_DA - tax_DA) × tax_rate
        # Tax DA ≈ book DA × 1.2 (accelerated as proxy)
        formula_cell(ws, REG["TX.dta_open"], c_idx, f"={prev}{REG['TX.dta_close']}", FMT_MLN)
        formula_cell(ws, REG["TX.dtl_open"], c_idx, f"={prev}{REG['TX.dtl_close']}", FMT_MLN)
        # Deferred tax expense = (tax_DA - book_DA) × tax_rate (DTL increasing)
        book_da = f"'{NAME['PP']}'!{cl}${REG['PP.dep_charge']}"
        formula_cell(ws, REG["TX.deferred"], c_idx,
                     f"=({book_da}*1.2-{book_da})*{cp_tax_rate}", FMT_MLN)
        # DTA_close = DTA_open (simplified — no new DTA sources)
        formula_cell(ws, REG["TX.dta_close"], c_idx, f"={cl}{REG['TX.dta_open']}", FMT_MLN)
        # DTL_close = DTL_open + deferred_tax_expense
        formula_cell(ws, REG["TX.dtl_close"], c_idx,
                     f"={cl}{REG['TX.dtl_open']}+{cl}{REG['TX.deferred']}", FMT_MLN)


def build_valuation(wb, cfg):
    """35_Valuation — DCF + SOTP + Sensitivity (full formulas)."""
    ws = wb["35_Valuation"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"35_Valuation — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "DCF (FCFF) + SOTP + Sensitivity Matrix").font = F_SUBTITLE

    fc = cfg["fc_years"]
    n_fc = len(fc)

    # ── A. WACC ──
    section_header(ws, 6, "A. WACC (Cost of Capital: CAPM)")
    # WACC params: reference Control_Panel (single source of truth)
    wacc_params = [
        ("rf", "Risk-free rate (Rf)", "CP.wacc_rf"),
        ("beta", "Beta (отрасль)", "CP.wacc_beta"),
        ("erp", "Equity Risk Premium (ERP)", "CP.wacc_erp"),
        ("crp", "Country Risk Premium (CRP)", "CP.wacc_crp"),
        ("scp", "Size/Company Premium (SCP)", "CP.wacc_scp"),
    ]
    for key, label, cp_key in wacc_params:
        r = REG[f"VL.{key}"]
        label_row(ws, r, label, "%" if key != "beta" else "x")
        cp_row = REG.get(cp_key)
        if cp_row:
            ref_cell(ws, r, 3, f"='Control_Panel'!$C${cp_row}",
                     FMT_PCT2 if key != "beta" else FMT_RATIO)
        else:
            # Fallback: local input
            defaults = {"rf": 0.10, "beta": 1.1, "erp": 0.07, "crp": 0.04, "scp": 0.01}
            input_cell(ws, r, 3, defaults[key], FMT_PCT2 if key != "beta" else FMT_RATIO)

    r_wacc = REG["VL.wacc"]
    # True WACC = Ke × we + Kd × (1-t) × wd
    # Ke = Rf + β×ERP + SCP (no CRP if Rf is local currency)
    # Kd = avg debt rate, wd = D/(D+E), we = 1-wd
    label_row(ws, r_wacc, "WACC = Ke×we + Kd×(1-t)×wd", "%", "True WACC for FCFF")
    ke = (f"$C${REG['VL.rf']}+$C${REG['VL.beta']}*$C${REG['VL.erp']}"
          f"+$C${REG['VL.scp']}")  # No CRP on top of local Rf
    cp_tax_vl = f"'Control_Panel'!$C${REG.get('CP.tax_rate', 80)}"
    n_hist_vl = len(cfg["hist_years"][-3:])
    lfc = get_column_letter(3 + n_hist_vl + len(fc) - 1)  # last forecast col
    kd = f"'{NAME['DT']}'!{lfc}${REG['DT.avg_rate']}"
    debt_ref = f"'{NAME['DT']}'!{lfc}${REG['DT.close']}"
    equity_ref = f"'{NAME['BS']}'!{lfc}${REG['BS.te']}"
    wd = f"IFERROR({debt_ref}/MAX(1,{debt_ref}+ABS({equity_ref})),0.5)"
    formula_cell(ws, r_wacc, 3,
                 f"=({ke})*(1-{wd})+{kd}*(1-{cp_tax_vl})*{wd}",
                 FMT_PCT2, bold=True)

    # ── B. TERMINAL VALUE ──
    section_header(ws, REG["VL.tg"] - 1, "B. TERMINAL VALUE PARAMETERS")
    # Terminal params: reference CP (single source of truth)
    cp_tg = REG.get("CP.terminal_g")
    cp_tm = REG.get("CP.terminal_mult")
    label_row(ws, REG["VL.tg"], "Terminal growth rate (g)", "%", "Долгосрочный рост ~ ном. ВВП")
    if cp_tg:
        ref_cell(ws, REG["VL.tg"], 3, f"='Control_Panel'!$C${cp_tg}", FMT_PCT)
    else:
        input_cell(ws, REG["VL.tg"], 3, 0.03, FMT_PCT)
    label_row(ws, REG["VL.tm"], "Terminal EV/EBITDA multiple", "x", "Peer median")
    if cp_tm:
        ref_cell(ws, REG["VL.tm"], 3, f"='Control_Panel'!$C${cp_tm}", FMT_MULT)
    else:
        input_cell(ws, REG["VL.tm"], 3, 6.0, FMT_MULT)

    # ── C. DCF — FCFF CALCULATION ──
    r = REG["VL.ev"] - 8  # space for FCFF rows
    section_header(ws, r, "C. DCF: FREE CASH FLOW TO FIRM (FCFF)")
    r += 1
    year_headers(ws, r, [], fc)
    r += 1

    # FCFF rows
    fcff_items = [
        ("EBIT", f"'{NAME['PL']}'!{{cl}}${REG['PL.ebit']}"),
        ("Tax rate", f"'{NAME['TX']}'!{{cl}}${REG['TX.eff_rate']}"),
        ("NOPAT = EBIT × (1 − tax)", None),
        ("D&A (add back)", f"'{NAME['PP']}'!{{cl}}${REG['PP.dep_charge']}"),
        ("CapEx", f"'{NAME['PP']}'!{{cl}}${REG['PP.capex']}"),
        ("ΔWC", f"'{NAME['WC']}'!{{cl}}${REG['WC.delta_nwc']}"),
        ("FCFF = NOPAT + D&A − CapEx − ΔWC", None),
        ("Discount factor: 1/(1+WACC)^t", None),
        ("PV of FCFF", None),
    ]

    fcff_start_r = r
    for label, _ in fcff_items:
        label_row(ws, r, label, "mln" if "rate" not in label.lower() and "factor" not in label.lower() else "")
        r += 1

    # FCFF formulas per forecast year — use SAME columns as model (F, G, H)
    n_hist_vl = len(cfg["hist_years"][-3:])
    for i, yr in enumerate(fc):
        c = 3 + n_hist_vl + i  # F=6, G=7, H=8 (matching model layout)
        cl = get_column_letter(c)
        t = i + 1  # discount period
        ebit_r = fcff_start_r
        tax_r = fcff_start_r + 1
        nopat_r = fcff_start_r + 2
        da_r = fcff_start_r + 3
        capex_r = fcff_start_r + 4
        dwc_r = fcff_start_r + 5
        fcff_r = fcff_start_r + 6
        df_r = fcff_start_r + 7
        pvfcff_r = fcff_start_r + 8

        ref_cell(ws, ebit_r, c, f"='{NAME['PL']}'!{cl}${REG['PL.ebit']}", FMT_MLN)
        # Tax rate: statutory (not effective — effective can be negative)
        cp_tax_vl = f"'Control_Panel'!$C${REG.get('CP.tax_rate', 80)}"
        ref_cell(ws, tax_r, c, f"={cp_tax_vl}", FMT_PCT)
        formula_cell(ws, nopat_r, c, f"={cl}{ebit_r}*(1-{cl}{tax_r})", FMT_MLN, bold=True)
        ref_cell(ws, da_r, c, f"='{NAME['PP']}'!{cl}${REG['PP.dep_charge']}", FMT_MLN)
        ref_cell(ws, capex_r, c, f"=ABS('{NAME['PP']}'!{cl}${REG['PP.capex']})", FMT_MLN)
        ref_cell(ws, dwc_r, c, f"='{NAME['WC']}'!{cl}${REG['WC.delta_nwc']}", FMT_MLN)
        formula_cell(ws, fcff_r, c,
                     f"={cl}{nopat_r}+{cl}{da_r}-{cl}{capex_r}-{cl}{dwc_r}", FMT_MLN, bold=True)
        formula_cell(ws, df_r, c, f"=1/(1+$C${r_wacc})^{t}", FMT_RATIO)
        formula_cell(ws, pvfcff_r, c, f"={cl}{fcff_r}*{cl}{df_r}", FMT_MLN)

    r = pvfcff_r + 2

    # Terminal value & DCF result
    section_header(ws, r, "D. DCF RESULT")
    r += 1
    tv_r = r
    label_row(ws, r, "Terminal Value (EV/EBITDA)", "mln", "EBITDA_last × multiple")
    last_fc_col = get_column_letter(3 + n_hist_vl + n_fc - 1)  # H (last forecast)
    formula_cell(ws, r, 3,
                 f"='{NAME['PL']}'!{last_fc_col}${REG['PL.ebitda']}*$C${REG['VL.tm']}", FMT_MLN)
    r += 1
    tv_perp_r = r
    label_row(ws, r, "Terminal Value (Perpetuity)", "mln", "FCFF_last × (1+g) / (WACC-g)")
    formula_cell(ws, r, 3,
                 f"=IFERROR({last_fc_col}{fcff_start_r + 6}*(1+$C${REG['VL.tg']})"
                 f"/($C${r_wacc}-$C${REG['VL.tg']}),0)", FMT_MLN)
    r += 1
    pv_tv_r = r
    label_row(ws, r, "PV of Terminal Value", "mln")
    formula_cell(ws, r, 3,
                 f"=($C${tv_r}+$C${tv_perp_r})/2/(1+$C${r_wacc})^{n_fc}", FMT_MLN)
    r += 1
    npv_r = r
    label_row(ws, r, "NPV of FCFF", "mln")
    pv_cols = [f"{get_column_letter(3+n_hist_vl+i)}{pvfcff_r}" for i in range(n_fc)]
    formula_cell(ws, r, 3, "=" + "+".join(pv_cols), FMT_MLN)
    r += 1

    # EV, ND, Equity
    r_ev = REG["VL.ev"]
    r_nd = REG["VL.nd"]
    r_eq = REG["VL.eq_value"]
    label_row(ws, r_ev, "Enterprise Value (MAX of DCF, SOTP)", "mln")
    formula_cell(ws, r_ev, 3,
                 f"=MAX($C${npv_r}+$C${pv_tv_r},$C${REG['VL.sotp_total']})",
                 FMT_MLN, bold=True)
    label_row(ws, r_nd, "Net Debt (последний прогнозный год)", "mln")
    ref_cell(ws, r_nd, 3, f"='{NAME['DT']}'!{last_fc_col}${REG['DT.nd']}", FMT_MLN)
    label_row(ws, r_eq, "Equity Value = EV − Net Debt", "mln")
    formula_cell(ws, r_eq, 3, f"=$C${r_ev}-$C${r_nd}", FMT_MLN, bold=True)

    # ── E. SOTP ──
    r_sotp = REG["VL.sotp_total"]
    section_header(ws, r_sotp - 2, "E. SOTP (Sum of the Parts)")
    label_row(ws, r_sotp - 1, "Сегмент | Revenue(last) × EV/Rev multiple", "mln")
    label_row(ws, r_sotp, "SOTP Enterprise Value (сумма)", "mln")
    # Per-segment SOTP (from Revenue sheet)
    for i, seg in enumerate(cfg["segments"]):
        sr = r_sotp + 1 + i
        label_row(ws, sr, seg["name"], "mln")
        rev_r = REG.get(f"RV.{seg['key']}_rev", 10)
        # Different multiples per segment (audit: 0.7 for all is wrong)
        seg_mults = {"seg1": 0.8, "seg2": 0.5, "seg3": 0.4}  # Al > Alumina > Other
        input_cell(ws, sr, 11, seg_mults.get(seg["key"], 0.7), FMT_MULT)
        ws.cell(sr, 12, "EV/Rev →").font = F_NOTE
        formula_cell(ws, sr, 3,
                     f"='{NAME['RV']}'!{last_fc_col}${rev_r}*$K${sr}", FMT_MLN)
    # Total SOTP
    seg_rows = [f"$C${r_sotp + 1 + i}" for i in range(len(cfg["segments"]))]
    formula_cell(ws, r_sotp, 3, "=" + "+".join(seg_rows), FMT_MLN, bold=True)

    # ── F. SENSITIVITY ──
    sens_r = REG["VL.sens_matrix"]
    section_header(ws, sens_r - 2, "F. SENSITIVITY: Equity Value = f(WACC, Terminal Growth)")
    label_row(ws, sens_r - 1, "WACC ↓ \\ g →", "")
    # 5×5 matrix: WACC from -4pp to +4pp, g from -2pp to +2pp
    wacc_offsets = [-0.04, -0.02, 0.0, 0.02, 0.04]
    g_offsets = [-0.02, -0.01, 0.0, 0.01, 0.02]

    # Header row (g values)
    for j, dg in enumerate(g_offsets):
        c = 3 + j
        formula_cell(ws, sens_r - 1, c, f"=$C${REG['VL.tg']}+{dg}", FMT_PCT)
        ws.cell(sens_r - 1, c).font = F_YEAR

    # Matrix body
    for i, dw in enumerate(wacc_offsets):
        rr = sens_r + i
        formula_cell(ws, rr, 2, f"=$C${r_wacc}+{dw}", FMT_PCT)  # WACC label in col B
        ws.cell(rr, 2).font = F_YEAR
        for j, dg in enumerate(g_offsets):
            c = 3 + j
            # EV = NPV_FCFF + FCFF_last*(1+g_adj)/(WACC_adj - g_adj) / (1+WACC_adj)^n - ND
            wacc_ref = f"($C${r_wacc}+{dw})"
            g_ref = f"($C${REG['VL.tg']}+{dg})"
            formula_cell(ws, rr, c,
                         f"=IFERROR($C${npv_r}+{last_fc_col}{fcff_start_r + 6}*(1+{g_ref})"
                         f"/({wacc_ref}-{g_ref})/(1+{wacc_ref})^{n_fc}-$C${r_nd},0)",
                         FMT_MLN0)
            # Highlight center cell
            if dw == 0 and dg == 0:
                ws.cell(rr, c).fill = FILL_RESULT


def build_score(wb, cfg):
    """31_Score — S&P 4-factor rating scorecard with formulas."""
    ws = wb["31_Score"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"31_Score — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "S&P-like 4-factor Credit Rating Scorecard").font = F_SUBTITLE
    n_hist = len(cfg["hist_years"][-3:])
    year_headers(ws, 4, cfg["hist_years"][-3:], cfg["fc_years"])

    section_header(ws, 6, "СКОРКАРТА: КОМПОНЕНТЫ (0-100 баллов)")
    # Leverage: ND/EBITDA → score via piecewise linear
    # <0.5x → 80, 1x → 72, 2x → 55, 3x → 40, 4.5x → 15, >6x → 5
    r_lev = REG["SC.leverage"]
    label_row(ws, r_lev, "Leverage Score (ND/EBITDA) [35%]", "балл",
              "<0.5→80, 2→55, 3.5→33, >6→5")
    for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c)
        nd_ebitda = f"'{NAME['RA']}'!{cl}${REG['RA.nd_ebitda']}"
        # Audit v7: linear scale 0-16x turnovers, monotonically decreasing
        # 0x→80, 4x→61, 8x→42, 12x→24, 16x→5
        # score = MAX(5, 80 - ND/EBITDA × 4.7)
        # IF EBITDA ≤ 0: floor score 5 (negative EBITDA = worst leverage, not best)
        formula_cell(ws, r_lev, c,
                     f"=IF('{NAME['PL']}'!{cl}${REG['PL.ebitda']}<=0,5,"
                     f"MAX(5,MIN(80,80-{nd_ebitda}*4.7)))", FMT_RATIO1)

    # Coverage: ICR → score
    r_cov = REG["SC.coverage"]
    label_row(ws, r_cov, "Coverage Score (EBITDA/Interest) [30%]", "балл",
              "1x→10, 3x→42, 5x→62, >10→88")
    for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c)
        icr = f"'{NAME['RA']}'!{cl}${REG['RA.icr']}"
        # Д9: recalibrated — more resolution at low ICR
        # 1x→12, 1.5x→20, 2x→30, 3x→42, 5x→60, 10x→80
        formula_cell(ws, r_cov, c,
                     f"=MAX(5,MIN(88,{icr}*12))", FMT_RATIO1)

    # Profitability: EBITDA margin → score (TTC-adjusted)
    r_prof = REG["SC.profit"]
    label_row(ws, r_prof, "Profitability Score (EBITDA margin TTC) [20%]", "балл",
              "Cycle avg from CP, cap 1.5×")
    cp_cycle = f"'Control_Panel'!$C${REG.get('CP.sc_cycle_margin', 103)}"
    for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c)
        margin = f"'{NAME['RA']}'!{cl}${REG['RA.ebitda_margin']}"
        formula_cell(ws, r_prof, c,
                     f"=MAX(5,MIN(82,MIN({margin},{cp_cycle}*1.5)*400))", FMT_RATIO1)

    # Liquidity: Current ratio + Cash/Debt
    r_liq = REG["SC.liquidity"]
    label_row(ws, r_liq, "Liquidity Score (CR + Cash metrics) [15%]", "балл")
    for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c)
        cr = f"'{NAME['RA']}'!{cl}${REG['RA.current']}"
        formula_cell(ws, r_liq, c,
                     f"=MAX(5,MIN(80,{cr}*40))", FMT_RATIO1)

    # Weighted score
    section_header(ws, REG["SC.base"] - 1, "ИТОГОВЫЙ РЕЙТИНГ")
    r_base = REG["SC.base"]
    label_row(ws, r_base, "Базовый балл (взвешенный)", "балл")
    # Weights from CP (not hardcoded)
    cp_wl = f"'Control_Panel'!$C${REG.get('CP.sc_w_lev', 98)}"
    cp_wc = f"'Control_Panel'!$C${REG.get('CP.sc_w_cov', 99)}"
    cp_wp = f"'Control_Panel'!$C${REG.get('CP.sc_w_prof', 100)}"
    cp_wq = f"'Control_Panel'!$C${REG.get('CP.sc_w_liq', 101)}"
    for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c)
        formula_cell(ws, r_base, c,
                     f"={cp_wl}*{cl}{r_lev}+{cp_wc}*{cl}{r_cov}+"
                     f"{cp_wp}*{cl}{r_prof}+{cp_wq}*{cl}{r_liq}",
                     FMT_RATIO1, bold=True)

    r_ind = REG["SC.ind_adj"]
    r_size = REG["SC.size_adj"]
    label_row(ws, r_ind, "Отраслевая корректировка", "балл")
    # From CP
    cp_ind = REG.get("CP.sc_ind_adj")
    if cp_ind:
        ref_cell(ws, r_ind, 3, f"='Control_Panel'!$C${cp_ind}", FMT_RATIO1)
    else:
        input_cell(ws, r_ind, 3, cfg.get("rating_ind_adj", -6), FMT_RATIO1)
    label_row(ws, r_size, "Размерная корректировка", "балл")
    cp_size = REG.get("CP.sc_size_adj")
    if cp_size:
        ref_cell(ws, r_size, 3, f"='Control_Panel'!$C${cp_size}", FMT_RATIO1)
    else:
        input_cell(ws, r_size, 3, cfg.get("rating_size_adj", 2), FMT_RATIO1)

    r_final = REG["SC.final"]
    label_row(ws, r_final, "Итоговый балл", "балл")
    for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c)
        formula_cell(ws, r_final, c,
                     f"=MAX(0,MIN(100,{cl}{r_base}+$C${r_ind}+$C${r_size}))", FMT_RATIO1, bold=True)

    r_rating = REG["SC.rating"]
    label_row(ws, r_rating, "Рейтинг (S&P эквивалент)", "")
    for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c)
        # Score → Rating lookup
        # Д9: recalibrated thresholds — Rusal B/CCC should score 15-30
        formula_cell(ws, r_rating, c,
                     f'=IF({cl}{r_final}>=85,"AAA",IF({cl}{r_final}>=75,"AA",'
                     f'IF({cl}{r_final}>=65,"A",IF({cl}{r_final}>=55,"BBB",'
                     f'IF({cl}{r_final}>=40,"BB",IF({cl}{r_final}>=25,"B",'
                     f'IF({cl}{r_final}>=12,"CCC","D")))))))',
                     FMT_TEXT)


def build_covenants(wb, cfg):
    """32_Covenants — covenant monitoring with actual vs threshold."""
    ws = wb["32_Covenants"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"32_Covenants — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "Мониторинг ковенантов: фактическое vs порог + headroom").font = F_SUBTITLE
    n_hist = len(cfg["hist_years"][-3:])
    year_headers(ws, 4, cfg["hist_years"][-3:], cfg["fc_years"])

    covs = cfg.get("covenants", {})

    # Structure: each covenant = 3 rows (actual, threshold, headroom/breach)
    section_header(ws, 6, "КОВЕНАНТЫ")
    r = 7
    cov_defs = [
        ("ND/EBITDA", covs.get("nd_ebitda_max", 4.5), "max", "RA", "nd_ebitda", FMT_MULT),
        ("Interest Coverage (ICR)", covs.get("icr_min", 2.0), "min", "RA", "icr", FMT_MULT),
        ("EBITDA Margin", covs.get("margin_min", 0.10), "min", "RA", "ebitda_margin", FMT_PCT),
        ("Current Ratio", covs.get("current_min", 1.0), "min", "RA", "current", FMT_MULT),
        ("Debt/Equity", covs.get("de_max", 4.0), "max", "RA", "debt_equity", FMT_MULT),
    ]

    for label, threshold, direction, code, key, fmt in cov_defs:
        subsection_header(ws, r, label); r += 1

        # Actual
        label_row(ws, r, "Фактическое значение")
        row_src = REG.get(f"{code}.{key}")
        if row_src:
            for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
                cl = get_column_letter(c)
                ref_cell(ws, r, c, f"='{NAME[code]}'!{cl}${row_src}", fmt)
        r += 1

        # Threshold — from CP if available
        label_row(ws, r, f"Порог ({'≤' if direction == 'max' else '≥'} {threshold})")
        # Map covenant labels to CP keys
        cov_cp = {"ND/EBITDA": "CP.cov_nd_ebitda", "Interest Coverage (ICR)": "CP.cov_icr"}
        cp_cov_row = REG.get(cov_cp.get(label, ""))
        for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
            if cp_cov_row:
                ref_cell(ws, r, c, f"='Control_Panel'!$C${cp_cov_row}", fmt)
            else:
                input_cell(ws, r, c, threshold, fmt)
        thresh_r = r
        r += 1

        # Headroom / Breach (protected from negative EBITDA)
        label_row(ws, r, "Headroom / BREACH", "", "Положительное = запас, отрицательное = нарушение")
        ebitda_ref = f"'{NAME['PL']}'!{get_column_letter(3+n_hist)}${REG['PL.ebitda']}"
        for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
            cl = get_column_letter(c)
            ebitda_c = f"'{NAME['PL']}'!{cl}${REG['PL.ebitda']}"
            if direction == "max" and "EBITDA" in label:
                # ND/EBITDA: if EBITDA ≤ 0, headroom = -99 (always breached)
                formula_cell(ws, r, c,
                             f"=IF({ebitda_c}<=0,-99,{cl}{thresh_r}-{cl}{r-2})", fmt)
            elif direction == "max":
                formula_cell(ws, r, c, f"={cl}{thresh_r}-{cl}{r-2}", fmt)
            else:
                formula_cell(ws, r, c, f"={cl}{r-2}-{cl}{thresh_r}", fmt)
        r += 2

    # Breach count
    section_header(ws, r, "ИТОГО НАРУШЕНИЙ")
    r += 1
    label_row(ws, r, "Количество нарушений", "", "0 = все ОК")
    for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
        cl = get_column_letter(c)
        # Count headroom rows < 0 (every 5th row starting from 10)
        parts = []
        for i, (_, _, _, _, _, _) in enumerate(cov_defs):
            headroom_r = 10 + i * 5
            parts.append(f"IF({cl}{headroom_r}<0,1,0)")
        formula_cell(ws, r, c, "=" + "+".join(parts), FMT_INT, bold=True)


def build_revstress(wb, cfg):
    """33_RevStress — reverse stress + tornado analysis."""
    ws = wb["33_RevStress"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"33_RevStress — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "Обратный стресс-тест + Tornado-анализ чувствительности").font = F_SUBTITLE

    section_header(ws, 6, "A. ОБРАТНЫЙ СТРЕСС-ТЕСТ (bisection)")
    label_row(ws, 7, "Какой шок Revenue приводит к нарушению ND/EBITDA?", "", "Результат: % снижения выручки")
    covs = cfg.get("covenants", {})
    nd_max = covs.get("nd_ebitda_max", 4.5)
    label_row(ws, 8, f"Порог ND/EBITDA: {nd_max}x")
    input_cell(ws, 8, 5, nd_max, FMT_MULT)  # E8 (not C8 — avoid self-ref from bisect_ebitda)

    label_row(ws, 10, "Breakeven Revenue shock (%)", "%", "Revenue(actual) × (1 + shock)")
    label_row(ws, 11, "Breakeven EBITDA shock (%)", "%")
    label_row(ws, 12, "Breakeven Interest rate shock (bp)", "bp")

    section_header(ws, 15, "B. TORNADO: ±1σ НА КЛЮЧЕВЫЕ ПЕРЕМЕННЫЕ")
    ws.cell(16, 1, "Переменная").font = F_LABEL_B
    ws.cell(16, 3, "Base").font = F_YEAR
    ws.cell(16, 4, "−1σ").font = F_YEAR
    ws.cell(16, 5, "+1σ").font = F_YEAR
    ws.cell(16, 6, "ΔNI (−1σ)").font = F_YEAR
    ws.cell(16, 7, "ΔNI (+1σ)").font = F_YEAR

    # Bisection formulas: what revenue shock → ND/EBITDA = threshold?
    # ND/EBITDA = (Debt - Cash) / EBITDA
    # If Revenue drops by x%: EBITDA_new ≈ EBITDA + Revenue × x × margin_sensitivity
    # Breakeven: ND / (EBITDA × (1+x)) = threshold → x = ND/(threshold×EBITDA) - 1
    n_hist = len(cfg["hist_years"][-3:])
    fc_start = 3 + n_hist
    last_fc = get_column_letter(fc_start)  # first forecast year for simplicity

    nd_ref = f"'{NAME['DT']}'!{last_fc}${REG['DT.nd']}"
    ebitda_ref = f"'{NAME['PL']}'!{last_fc}${REG['PL.ebitda']}"
    rev_ref = f"'{NAME['PL']}'!{last_fc}${REG['PL.revenue']}"
    int_ref = f"ABS('{NAME['DT']}'!{last_fc}${REG['DT.interest']})"
    # Revenue shock = ND/(threshold×EBITDA) - 1 (negative = drop)
    formula_cell(ws, REG["RS.bisect_rev"], 3,
                 f"=IFERROR({nd_ref}/($E$8*{ebitda_ref})-1,0)", FMT_PCT)
    # EBITDA shock (direct)
    formula_cell(ws, REG["RS.bisect_ebitda"], 3,
                 f"=IFERROR({nd_ref}/$E$8/{ebitda_ref}-1,0)", FMT_PCT)

    section_header(ws, 15, "B. TORNADO: ЧУВСТВИТЕЛЬНОСТЬ К ±1σ")
    ws.cell(16, 1, "Переменная").font = F_LABEL_B
    ws.cell(16, 3, "Шок").font = F_YEAR
    ws.cell(16, 4, "Δ EBITDA").font = F_YEAR
    ws.cell(16, 5, "Δ NI").font = F_YEAR
    ws.cell(16, 6, "Δ ND/EBITDA").font = F_YEAR

    # Tornado: analytical sensitivity (no macro recalc needed)
    # Rate shock: ΔInterest = Debt × Δrate → ΔNI = -ΔInterest × (1-tax)
    # Revenue shock: ΔEBITDA ≈ ΔRev × EBITDA_margin → ΔNI ≈ ΔEBITDA × (1-tax)
    # COGS shock: ΔEBITDA = -Revenue × Δratio → ΔNI = ΔEBITDA × (1-tax)
    cp_tax = f"'Control_Panel'!$C${REG.get('CP.tax_rate', 80)}"
    debt_ref = f"'{NAME['DT']}'!{last_fc}${REG['DT.close']}"
    margin_ref = f"'{NAME['RA']}'!{last_fc}${REG['RA.ebitda_margin']}"

    tornado_defs = [
        ("Interest rate +200bp", 0.02, "rate",
         f"=-{debt_ref}*0.02", f"=-{debt_ref}*0.02*(1-{cp_tax})"),
        ("Interest rate −200bp", -0.02, "rate",
         f"={debt_ref}*0.02", f"={debt_ref}*0.02*(1-{cp_tax})"),
        ("Revenue −20%", -0.20, "rev",
         f"={rev_ref}*(-0.2)*{margin_ref}", f"={rev_ref}*(-0.2)*{margin_ref}*(1-{cp_tax})"),
        ("Revenue +20%", 0.20, "rev",
         f"={rev_ref}*0.2*{margin_ref}", f"={rev_ref}*0.2*{margin_ref}*(1-{cp_tax})"),
        ("COGS +5pp", 0.05, "cogs",
         f"=-{rev_ref}*0.05", f"=-{rev_ref}*0.05*(1-{cp_tax})"),
        ("COGS −5pp", -0.05, "cogs",
         f"={rev_ref}*0.05", f"={rev_ref}*0.05*(1-{cp_tax})"),
        ("FX CNY +10%", -0.10, "fx",
         f"=0", f"=-'{NAME['DT']}'!{last_fc}${REG['DT.fx_reval']}"),
    ]
    for i, (var, shock, typ, d_ebitda, d_ni) in enumerate(tornado_defs):
        r = 17 + i
        label_row(ws, r, var)
        ws.cell(r, 3, shock).font = F_INPUT
        ws.cell(r, 3).number_format = FMT_PCT
        formula_cell(ws, r, 4, d_ebitda, FMT_MLN)
        formula_cell(ws, r, 5, d_ni, FMT_MLN)
        # Δ ND/EBITDA ≈ -ΔEBITDA × ND/EBITDA²
        formula_cell(ws, r, 6,
                     f"=IFERROR(-{get_column_letter(4)}{r}/{ebitda_ref}"
                     f"*{nd_ref}/{ebitda_ref},0)", FMT_MULT)


def build_scenarios(wb, cfg):
    """40_Scen — scenario comparison: base values from model + stress deltas."""
    ws = wb["40_Scen"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"40_Scen — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "Сравнение сценариев: базовый (из модели) + стресс-дельты").font = F_SUBTITLE

    n_hist = len(cfg["hist_years"][-3:])
    last_fc = get_column_letter(3 + n_hist)  # first forecast year

    section_header(ws, 4, "СЦЕНАРНОЕ СРАВНЕНИЕ (год 1)")
    headers = ["Revenue", "EBITDA", "NI", "ND/EBITDA", "ICR", "Cash", "FundGap"]
    ws.cell(5, 1, "Сценарий").font = F_LABEL_B
    for i, h in enumerate(headers):
        ws.cell(5, 3 + i, h).font = F_YEAR

    # Base row — formulas from model
    r = 6
    label_row(ws, r, "Base (из модели)")
    base_refs = [
        (f"='{NAME['PL']}'!{last_fc}${REG['PL.revenue']}", FMT_MLN),
        (f"='{NAME['PL']}'!{last_fc}${REG['PL.ebitda']}", FMT_MLN),
        (f"='{NAME['PL']}'!{last_fc}${REG['PL.ni']}", FMT_MLN),
        (f"='{NAME['RA']}'!{last_fc}${REG['RA.nd_ebitda']}", FMT_MULT),
        (f"='{NAME['RA']}'!{last_fc}${REG['RA.icr']}", FMT_MULT),
        (f"='{NAME['BS']}'!{last_fc}${REG['BS.cash']}", FMT_MLN),
        (f"='{NAME['DT']}'!{last_fc}${REG['DT.funding_gap']}", FMT_MLN),
    ]
    for i, (formula, fmt) in enumerate(base_refs):
        ref_cell(ws, r, 3 + i, formula, fmt)

    # ── Analytical stress rows ──
    # Each row applies a single-factor shock to base metrics using linear approx:
    #   Revenue shock x: ΔRev = Rev*x, ΔEBITDA = Rev*x*margin, ΔNI = ΔEBITDA*(1-t)
    #   Rate shock Δr: ΔInterest = Debt*Δr, ΔNI = -ΔInt*(1-t)
    #   Combined: sum of individual deltas
    cp_tax = f"'Control_Panel'!$C${REG.get('CP.tax_rate', 80)}"
    rev_base = f"C$6"       # base Revenue (row 6, col C)
    ebitda_base = f"D$6"    # base EBITDA
    ni_base = f"E$6"        # base NI
    nd_base = f"F$6"        # base ND/EBITDA
    icr_base = f"G$6"       # base ICR
    cash_base = f"H$6"      # base Cash
    gap_base = f"I$6"       # base FundGap
    margin_ref = f"'{NAME['RA']}'!{last_fc}${REG['RA.ebitda_margin']}"
    debt_ref = f"'{NAME['DT']}'!{last_fc}${REG['DT.close']}"
    ebitda_model = f"'{NAME['PL']}'!{last_fc}${REG['PL.ebitda']}"
    nd_ref = f"'{NAME['DT']}'!{last_fc}${REG['DT.nd']}"
    int_ref = f"ABS('{NAME['DT']}'!{last_fc}${REG['DT.interest']})"

    # Row 7: Revenue −20%
    r = 7
    label_row(ws, r, "Revenue −20%")
    d_rev = f"={rev_base}*(-0.2)"
    d_ebitda_rev = f"={rev_base}*(-0.2)*{margin_ref}"
    d_ni_rev = f"={rev_base}*(-0.2)*{margin_ref}*(1-{cp_tax})"
    ref_cell(ws, r, 3, f"={rev_base}+{rev_base}*(-0.2)", FMT_MLN)          # Revenue
    ref_cell(ws, r, 4, f"={ebitda_base}+{rev_base}*(-0.2)*{margin_ref}", FMT_MLN)  # EBITDA
    ref_cell(ws, r, 5, f"={ni_base}+{rev_base}*(-0.2)*{margin_ref}*(1-{cp_tax})", FMT_MLN)  # NI
    ref_cell(ws, r, 6, f"=IFERROR({nd_ref}/(D{r}),0)", FMT_MULT)           # ND/EBITDA
    ref_cell(ws, r, 7, f"=IFERROR(D{r}/{int_ref},0)", FMT_MULT)            # ICR
    ref_cell(ws, r, 8, f"={cash_base}", FMT_MLN)                           # Cash (unchanged)
    ref_cell(ws, r, 9, f"={gap_base}", FMT_MLN)                            # Gap (approx)

    # Row 8: Rate +200bp
    r = 8
    label_row(ws, r, "Rate +200bp")
    d_int = f"{debt_ref}*0.02"
    ref_cell(ws, r, 3, f"={rev_base}", FMT_MLN)
    ref_cell(ws, r, 4, f"={ebitda_base}", FMT_MLN)
    ref_cell(ws, r, 5, f"={ni_base}-{d_int}*(1-{cp_tax})", FMT_MLN)
    ref_cell(ws, r, 6, f"={nd_base}", FMT_MULT)
    ref_cell(ws, r, 7, f"=IFERROR({ebitda_base}/({int_ref}+{d_int}),0)", FMT_MULT)
    ref_cell(ws, r, 8, f"={cash_base}", FMT_MLN)
    ref_cell(ws, r, 9, f"={gap_base}", FMT_MLN)

    # Row 9: FX +10% (debt revaluation loss)
    r = 9
    label_row(ws, r, "FX +10%")
    fx_debt_share = 0.3  # approx share of FX-denominated debt
    ref_cell(ws, r, 3, f"={rev_base}", FMT_MLN)
    ref_cell(ws, r, 4, f"={ebitda_base}", FMT_MLN)
    ref_cell(ws, r, 5, f"={ni_base}-{debt_ref}*{fx_debt_share}*0.1*(1-{cp_tax})", FMT_MLN)
    ref_cell(ws, r, 6, f"=IFERROR(({nd_ref}+{debt_ref}*{fx_debt_share}*0.1)/{ebitda_model},0)", FMT_MULT)
    ref_cell(ws, r, 7, f"={icr_base}", FMT_MULT)
    ref_cell(ws, r, 8, f"={cash_base}", FMT_MLN)
    ref_cell(ws, r, 9, f"={gap_base}", FMT_MLN)

    # Row 10: Refi = 0% (no refinancing → mandatory is not rolled)
    r = 10
    label_row(ws, r, "Refi = 0%")
    mand_ref = f"'{NAME['DT']}'!{last_fc}${REG['DT.mandatory']}"
    ref_cell(ws, r, 3, f"={rev_base}", FMT_MLN)
    ref_cell(ws, r, 4, f"={ebitda_base}", FMT_MLN)
    ref_cell(ws, r, 5, f"={ni_base}", FMT_MLN)
    ref_cell(ws, r, 6, f"={nd_base}", FMT_MULT)
    ref_cell(ws, r, 7, f"={icr_base}", FMT_MULT)
    ref_cell(ws, r, 8, f"=MAX(0,{cash_base}-{mand_ref})", FMT_MLN)
    ref_cell(ws, r, 9, f"=MAX(0,{mand_ref}-{cash_base})", FMT_MLN)

    # Row 11: Combined stress (Rev−20% + Rate+200bp + FX+10%)
    r = 11
    label_row(ws, r, "Combined stress")
    ref_cell(ws, r, 3, f"=C7", FMT_MLN)  # same as Rev−20%
    ref_cell(ws, r, 4, f"=D7", FMT_MLN)  # EBITDA from rev shock
    ref_cell(ws, r, 5, f"=E7-{d_int}*(1-{cp_tax})-{debt_ref}*{fx_debt_share}*0.1*(1-{cp_tax})", FMT_MLN)
    ref_cell(ws, r, 6, f"=IFERROR(({nd_ref}+{debt_ref}*{fx_debt_share}*0.1)/D{r},0)", FMT_MULT)
    ref_cell(ws, r, 7, f"=IFERROR(D{r}/({int_ref}+{d_int}),0)", FMT_MULT)
    ref_cell(ws, r, 8, f"={cash_base}", FMT_MLN)
    ref_cell(ws, r, 9, f"=MAX(0,I7+I8+I9+I10-3*{gap_base})", FMT_MLN)

    # ── Summary section ──
    section_header(ws, 14, "КОВЕНАНТНЫЙ АНАЛИЗ")
    cov_nd = f"'Control_Panel'!$C${REG.get('CP.cov_nd', 80)}"
    # Count scenarios where ND/EBITDA > covenant
    label_row(ws, 15, "Сценариев с нарушением ND/EBITDA")
    ref_cell(ws, 15, 3,
             f"=COUNTIF(F7:F11,\">\"&{cov_nd})", "0")
    label_row(ws, 16, "Сценариев с Funding Gap > 0")
    ref_cell(ws, 16, 3, f"=COUNTIF(I7:I11,\">0\")", "0")
    label_row(ws, 17, "Обратный стресс: breakeven Revenue shock")
    ref_cell(ws, 17, 3, f"='33_RevStress'!$C${REG.get('RS.bisect_rev', 7)}", FMT_PCT)


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
    input_cell(ws, r, 3, 1, FMT_INT)
    REG["CP.rev_method"] = r; r += 1
    label_row(ws, r, "Эластичность Revenue к macro-фактору", "", "β × Δln(factor)")
    input_cell(ws, r, 3, 1.0, FMT_RATIO)
    REG["CP.rev_elasticity"] = r; r += 1
    label_row(ws, r, "R² (коэфф. детерминации)")
    ref_cell(ws, r, 3, f"='{NAME['MA']}'!$C${REG.get('MA.econ_r2', 53)}", FMT_PCT2); r += 2

    # ── D. СЕБЕСТОИМОСТЬ ──
    section_header(ws, r, "D. СЕБЕСТОИМОСТЬ"); r += 1
    cogs_method = 2 if cfg.get("cogs_mode") == "component" else 1
    label_row(ws, r, "COGS method (1=ratio, 2=component, 3=ppi_uplift)")
    input_cell(ws, r, 3, cogs_method, FMT_INT)
    REG["CP.cogs_method"] = r; r += 1
    # COGS ratio (used by both modes — main sensitivity lever)
    label_row(ws, r, "COGS ratio (калиброванный)", "%", "→ 12_COGS formula")
    input_cell(ws, r, 3, cfg.get("cogs_ratio_default", 0.83), FMT_PCT)
    REG["CP.cogs_ratio"] = r; r += 1
    if cfg.get("cogs_mode") == "component":
        for comp, share in cfg.get("cogs_components", {}).items():
            label_row(ws, r, f"Доля {comp.title()}", "%", "→ 12_COGS component")
            input_cell(ws, r, 3, share, FMT_PCT)
            REG[f"CP.cogs_{comp}"] = r; r += 1
    else:
        pass  # ratio mode uses CP.cogs_ratio directly
    label_row(ws, r, "PPI beta (COGS ~ PPI)")
    input_cell(ws, r, 3, 0.85, FMT_RATIO)
    REG["CP.ppi_beta"] = r; r += 1
    label_row(ws, r, "Mean reversion dampening")
    input_cell(ws, r, 3, 0.30, FMT_RATIO)
    REG["CP.mr_dampening"] = r; r += 2

    # ── E. SGA / ОПЕКС ──
    section_header(ws, r, "E. SGA / ОПЕРАЦИОННЫЕ РАСХОДЫ"); r += 1
    label_row(ws, r, "SGA ratio (EWA)", "%", "→ 13_SGA forecast = Revenue × ratio")
    input_cell(ws, r, 3, 0.08, FMT_PCT)
    REG["CP.sga_ratio"] = r; r += 1
    label_row(ws, r, "EWA halflife (лет)", "yr", "Информационно (preprocessing)")
    input_cell(ws, r, 3, 5, FMT_INT)
    REG["CP.ewa_halflife"] = r; r += 2

    # ── F. CAPEX / PP&E ──
    cp_da_rate_row = r + 1  # save for ref from PPE sheet
    section_header(ws, r, "F. КАПИТАЛЬНЫЕ ЗАТРАТЫ / PP&E"); r += 1
    label_row(ws, r, "DA rate (амортизация / ОС нетто)", "%")
    input_cell(ws, r, 3, 0.07, FMT_PCT)
    # Store this row for cross-ref — we'll update reg.json
    REG["CP.da_rate"] = r
    r += 1
    label_row(ws, r, "Sustaining CapEx / DA ratio")
    input_cell(ws, r, 3, 1.8, FMT_RATIO)
    REG["CP.sustaining_ratio"] = r; r += 1
    label_row(ws, r, "Expansion CapEx (% rev growth)")
    input_cell(ws, r, 3, 0.05, FMT_PCT)
    REG["CP.expansion_pct"] = r; r += 1
    label_row(ws, r, "Useful life (лет)", "yr", "→ DA = Gross / UL")
    input_cell(ws, r, 3, 16, FMT_INT)
    REG["CP.useful_life"] = r; r += 1
    label_row(ws, r, "Disposal % of CapEx", "%", "→ 15_PPE выбытия")
    input_cell(ws, r, 3, 0.0, FMT_PCT)  # 0 default — avoids BS imbalance unless proceeds connected
    REG["CP.disposal_pct"] = r; r += 2

    # ── G. ОБОРОТНЫЙ КАПИТАЛ ──
    section_header(ws, r, "G. ОБОРОТНЫЙ КАПИТАЛ"); r += 1
    label_row(ws, r, "WC method (1=days, 2=ratio)")
    input_cell(ws, r, 3, 1, FMT_INT)
    REG["CP.wc_method"] = r; r += 1
    for d, default, key in [("DSO (дни)", 30, "CP.wc_dso"),
                             ("DIH (дни)", 80, "CP.wc_dio"),
                             ("DPO (дни)", 40, "CP.wc_dpo")]:
        label_row(ws, r, d, "дни", "→ 16_WC forecast")
        input_cell(ws, r, 3, default, FMT_DAYS)
        REG[key] = r; r += 1
    r += 1

    # ── H. ДОЛГ ──
    section_header(ws, r, "H. ДОЛГ И ФИНАНСИРОВАНИЕ"); r += 1

    label_row(ws, r, "Min cash target", "mln")
    input_cell(ws, r, 3, cfg.get("min_cash", 500), FMT_MLN0)
    REG["CP.min_cash"] = r; r += 1

    label_row(ws, r, "RC лимит", "mln")
    input_cell(ws, r, 3, cfg.get("rc_limit", 2000), FMT_MLN0)
    REG["CP.rc_limit"] = r; r += 1

    label_row(ws, r, "RC ставка (база + спред)", "%")
    input_cell(ws, r, 3, cfg.get("rc_rate", 0.12), FMT_PCT)
    REG["CP.rc_rate"] = r; r += 1

    label_row(ws, r, "Commitment fee (% неисп. лимита)", "%")
    input_cell(ws, r, 3, cfg.get("commit_fee_rate", 0.005), FMT_PCT2)
    REG["CP.commit_fee_rate"] = r; r += 1

    label_row(ws, r, "Доля поддерж. CapEx (maint_share)", "%")
    input_cell(ws, r, 3, cfg.get("maint_share", 0.70), FMT_PCT)
    REG["CP.maint_share"] = r; r += 1

    label_row(ws, r, "Sweep % (добровольное погашение)", "%")
    input_cell(ws, r, 3, 0.30, FMT_PCT)
    REG["CP.sweep_pct"] = r; r += 1

    label_row(ws, r, "Target ND/EBITDA", "x")
    input_cell(ws, r, 3, cfg.get("debt_target_nd_ebitda", 2.0), FMT_MULT)
    REG["CP.target_leverage"] = r; r += 1

    label_row(ws, r, "Buffer сверх min cash", "mln")
    input_cell(ws, r, 3, cfg.get("cash_buffer", 200), FMT_MLN0)
    REG["CP.buffer"] = r; r += 1

    label_row(ws, r, "Refi % (облигации)", "%", "Сценарный параметр")
    input_cell(ws, r, 3, cfg.get("refi_pct_bonds", 1.0), FMT_PCT)
    REG["CP.refi_pct_bonds"] = r; r += 1

    label_row(ws, r, "Refi % (банковский долг)", "%", "Сценарный параметр")
    input_cell(ws, r, 3, cfg.get("refi_pct_bank", 1.0), FMT_PCT)
    REG["CP.refi_pct_bank"] = r; r += 1

    label_row(ws, r, "RC trigger (% лимита для нового транша)", "%")
    input_cell(ws, r, 3, 0.60, FMT_PCT)
    REG["CP.rc_trigger"] = r; r += 1

    label_row(ws, r, "Тенор refi транша (лет)", "yr", "Для рефинансирования")
    input_cell(ws, r, 3, cfg.get("term_tenor", 5), FMT_INT)
    REG["CP.term_tenor"] = r; r += 1

    label_row(ws, r, "Тенор capex транша (лет)", "yr", "Для проектного CapEx (5-7 лет)")
    input_cell(ws, r, 3, cfg.get("term_tenor_capex", 7), FMT_INT)
    REG["CP.term_tenor_capex"] = r; r += 1

    label_row(ws, r, "Spread base (новый долг)", "%")
    input_cell(ws, r, 3, cfg.get("spread_base", 0.03), FMT_PCT)
    REG["CP.spread_base"] = r; r += 1

    label_row(ws, r, "Spread step (за оборот ND/EBITDA)", "%")
    input_cell(ws, r, 3, cfg.get("spread_step", 0.005), FMT_PCT2)
    REG["CP.spread_step"] = r; r += 1

    label_row(ws, r, "Доступность нового долга (1=Да, 0=Нет)", "", "Сценарный")
    input_cell(ws, r, 3, 1, FMT_INT)
    REG["CP.new_debt_available"] = r; r += 1

    label_row(ws, r, "Премия за досрочное погашение LT", "%")
    input_cell(ws, r, 3, cfg.get("prepay_premium", 0.01), FMT_PCT)
    REG["CP.prepay_premium"] = r; r += 1

    label_row(ws, r, "Штрафная ставка (last resort)", "%", "Для финансирования при нарушении ковенантов")
    input_cell(ws, r, 3, 0.24, FMT_PCT)
    REG["CP.penalty_rate"] = r; r += 1

    label_row(ws, r, "Лимит штрафного привлечения", "mln", "0 = без лимита; >0 = потолок штрафного долга/год")
    input_cell(ws, r, 3, 0, FMT_MLN)  # 0 = unlimited (current behavior)
    REG["CP.penalty_limit"] = r; r += 1

    label_row(ws, r, "Covenant reclass LT→ST (1=Да, 0=Нет)", "", "IAS 1.74: opt-in (default=0, waiver assumed)")
    input_cell(ws, r, 3, 0, FMT_INT)  # Default 0: assume waiver. Analyst enables for stress
    REG["CP.cov_reclass"] = r; r += 1

    label_row(ws, r, "FX USDCNY change YoY", "%", "Input: no USD/CNY in macro yet")
    input_cell(ws, r, 3, 0.0, FMT_PCT)
    REG["CP.fx_usdcny_chg"] = r; r += 1

    label_row(ws, r, "FX USDRUB change YoY", "%", "Per-year from 05_Drivers")
    REG["CP.fx_usdrub_chg"] = r
    input_cell(ws, r, 3, 0.0, FMT_PCT)  # placeholder, PL uses per-year refs
    r += 1

    label_row(ws, r, "Доля выручки в CNY", "%", "Из МСФО Note 4: geography")
    input_cell(ws, r, 3, cfg.get("rev_cny_share", 0.0), FMT_PCT)
    REG["CP.rev_cny_share"] = r; r += 1

    label_row(ws, r, "Доля выручки в RUB", "%", "Из МСФО Note 4: geography")
    input_cell(ws, r, 3, cfg.get("rev_rub_share", 0.0), FMT_PCT)
    REG["CP.rev_rub_share"] = r; r += 1

    label_row(ws, r, "Доля затрат в RUB", "%", "Персонал + энергия + прочие внутр.")
    input_cell(ws, r, 3, cfg.get("cost_rub_share", 0.0), FMT_PCT)
    REG["CP.cost_rub_share"] = r; r += 2

    cov = cfg.get("covenants", {})
    label_row(ws, r, "Ковенант: ND/EBITDA max", "x", "При нарушении — блок дивидендов и новых выборок")
    input_cell(ws, r, 3, cov.get("nd_ebitda_max", 4.5), FMT_MULT)
    REG["CP.cov_nd_ebitda"] = r; r += 1

    label_row(ws, r, "Ковенант: ICR min", "x")
    input_cell(ws, r, 3, cov.get("icr_min", 1.5), FMT_MULT)
    REG["CP.cov_icr"] = r; r += 2

    # ── I. НАЛОГИ ──
    section_header(ws, r, "I. НАЛОГИ"); r += 1
    label_row(ws, r, "Statutory tax rate")
    input_cell(ws, r, 3, 0.25, FMT_PCT)
    REG["CP.tax_rate"] = r; r += 1
    label_row(ws, r, "NOL opening balance", "mln")
    input_cell(ws, r, 3, 0, FMT_MLN0)
    REG["CP.nol_open"] = r; r += 1
    label_row(ws, r, "NOL max utilization (%)")
    input_cell(ws, r, 3, 0.80, FMT_PCT)
    REG["CP.nol_cap"] = r; r += 2

    # ── J. ДИВИДЕНДЫ И КАПИТАЛ ──
    section_header(ws, r, "J. ДИВИДЕНДЫ И КАПИТАЛ"); r += 1
    payout = 0.0 if "RUSAL" in cfg["name"] else 0.60
    label_row(ws, r, "Dividend payout ratio")
    input_cell(ws, r, 3, payout, FMT_PCT)
    REG["CP.payout_ratio"] = r; r += 1
    label_row(ws, r, "Buyback (% FCF)", "%", "→ 24_Equity buyback = FCF × %")
    input_cell(ws, r, 3, 0.0, FMT_PCT)
    REG["CP.buyback_pct"] = r; r += 2

    # ── K. ОЦЕНКА (DCF) ──
    section_header(ws, r, "K. ОЦЕНКА (DCF)"); r += 1
    for param, val, fmt, key in [
        ("Risk-free rate (Rf)", 0.10, FMT_PCT, "CP.wacc_rf"),
        ("Beta", 1.1, FMT_RATIO, "CP.wacc_beta"),
        ("Equity Risk Premium", 0.07, FMT_PCT, "CP.wacc_erp"),
        ("Country Risk Premium", 0.04, FMT_PCT, "CP.wacc_crp"),
        ("Size Premium", 0.01, FMT_PCT, "CP.wacc_scp"),
        ("Terminal growth (g)", 0.03, FMT_PCT, "CP.terminal_g"),
        ("Terminal EV/EBITDA", 6.0, FMT_MULT, "CP.terminal_mult"),
    ]:
        label_row(ws, r, param)
        input_cell(ws, r, 3, val, fmt)
        REG[key] = r; r += 1
    r += 1

    # ── L. СКОРКАРТА ──
    section_header(ws, r, "L. СКОРКАРТА (S&P 4-FACTOR)"); r += 1
    for param, val, key in [
        ("Leverage weight", 0.35, "CP.sc_w_lev"),
        ("Coverage weight", 0.30, "CP.sc_w_cov"),
        ("Profitability weight", 0.20, "CP.sc_w_prof"),
        ("Liquidity weight", 0.15, "CP.sc_w_liq"),
        ("Industry adjustment", cfg.get("rating_ind_adj", -6), "CP.sc_ind_adj"),
        ("Size adjustment", cfg.get("rating_size_adj", 2), "CP.sc_size_adj"),
        ("Cycle avg EBITDA margin", cfg.get("rating_cycle_margin", 0.20), "CP.sc_cycle_margin"),
    ]:
        label_row(ws, r, param)
        fmt = FMT_PCT if "weight" in param or "margin" in param else FMT_RATIO1
        input_cell(ws, r, 3, val, fmt)
        REG[key] = r; r += 1

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
        ("ЭТАП 1: ВВОД ДАННЫХ (аналитик заполняет синие ячейки)", [
            ("02_Hist", "IS/BS/CF история (3 года). ВСЕ расчётные листы ссылаются сюда"),
            ("Raw_IFRS", "Долговой портфель: 20 инструментов + KeyRate forecast"),
            ("11_Segments", "Объёмы/цены/выручка по сегментам (10_Revenue ссылается)"),
            ("01_Macro", "Макро-факторы: 3 сценария (Base/Stress/Severe)"),
            ("05_Drivers", "Объёмы, удельные затраты, FX, ассоциированные"),
        ]),
        ("ЭТАП 2: НАСТРОЙКА МОДЕЛИ (Control Panel)", [
            ("Control_Panel", "47+ параметров: методы, ставки, ковенанты, оценка"),
        ]),
        ("ЭТАП 3: РАСЧЁТНЫЕ ЛИСТЫ (0 литералов, всё на формулах)", [
            ("10_Revenue", "Выручка = Σ(Vol × Price) + Reconciliation (из 02_Hist)"),
            ("12_COGS", "COGS: method switch (1=ratio, 2=component, 3=PPI)"),
            ("13_SGA", "SGA = Revenue × ratio (из CP)"),
            ("15_PPE", "PP&E corkscrew: Gross → CapEx → Dep → Net"),
            ("16_WC", "WC: DSO/DIH/DPO (формулы из 02_Hist, не литералы)"),
            ("17_Debt", "Долг: waterfall + penalty rate + history refs 02_Hist"),
            ("18_Lease", "IFRS 16: ROU + Liability"),
            ("19_Tax", "IAS 12: DTA/DTL refs 02_Hist, NOL carryforward"),
        ]),
        ("ЭТАП 4: ФИНАНСОВЫЕ ОТЧЁТЫ", [
            ("21_PL", "P&L: history = refs 02_Hist, other_opex/impairment = формулы"),
            ("20_BS", "Баланс: ABS() в TCL/TNCL, Other = plug → 02_Hist refs"),
            ("23_CF", "ОДДС: CFF включает new_term (always finances)"),
            ("24_Equity", "RE: дивиденды PREV year, buyback, covenant-gated"),
        ]),
        ("ЭТАП 5: АНАЛИТИКА И ПРОВЕРКИ", [
            ("30_Ratios", "25+ коэффициентов"),
            ("31_Score", "S&P 4-factor rating (EBITDA sign protection)"),
            ("32_Covenants", "5 ковенантов + breach tracking"),
            ("33_RevStress", "Reverse stress + Tornado"),
            ("40_Scen", "5 аналитических стресс-сценариев"),
            ("35_Valuation", "DCF (WACC) + SOTP + Sensitivity"),
            ("90_Checks", "15 проверок + 5 history checks = ДОЛЖНО БЫТЬ 0"),
            ("Model_Output", "Сводный дашборд (144 ссылки)"),
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

    n_hist = len(cfg["hist_years"][-3:])
    year_headers(ws, 4, cfg["hist_years"][-3:], cfg["fc_years"])

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


def build_debt_schedule(wb, cfg):
    """_Debt_Schedule — per-instrument schedule (technical, hidden later).

    Layout (per forecast year block):
      Row per instrument: Name | Kind | CCY | Balance | Rate | Type | Maturity
      Then columns per year: Open | Mandatory | Refi | Interest | Close

    Canonical kinds (from Python InstrumentKind):
      BOND_BULLET: bullet maturity, fixed rate
      BOND_FLOAT: bullet maturity, floating (KeyRate + spread)
      TERM_AMORT: scheduled amortization
      RC: revolving credit (draw/repay flexible)

    Interest = Balance × Rate (per instrument)
    Floating: Rate = KeyRate_forecast + Spread
    Mandatory = IF(maturity_year = forecast_year, opening_balance, 0)
    Refi = Mandatory (auto-rollover at market rate)
    """
    ws = wb["_Debt_Schedule"]
    apply_col_widths(ws)
    ws.cell(1, 1, "DEBT SCHEDULE — Per-Instrument (Technical)").font = F_TITLE
    ws.cell(2, 1, "Canonical instruments: BOND_BULLET / BOND_FLOAT / TERM_AMORT / RC").font = F_SUBTITLE

    fc = cfg["fc_years"]
    n_fc = len(fc)

    # Header: instrument info (cols A-G) + per-year blocks (H onwards)
    info_headers = ["№", "Instrument", "Kind", "CCY", "Balance (mln)", "Rate", "Maturity"]
    for i, h in enumerate(info_headers):
        ws.cell(4, i + 1, h).font = F_YEAR
        ws.cell(4, i + 1).alignment = A_CENTER

    # Per-year column blocks: Open | Mandatory | Refi | Interest | Close
    yr_cols_per = 5  # columns per year
    for yr_idx, yr in enumerate(fc):
        base_col = 8 + yr_idx * yr_cols_per
        for j, sub in enumerate(["Open", "Mandatory", "Refi", "Interest", "Close"]):
            ws.cell(3, base_col + j, f"{yr}E").font = F_YEAR
            ws.cell(4, base_col + j, sub).font = F_YEAR

    # Instruments will be filled by fill_data (rows 5+)
    # Row N+5 = TOTAL row with SUM formulas

    # Placeholder: 20 instrument rows + Other + total
    max_instruments = 20
    r_total = 5 + max_instruments + 1 + 1  # +1 Other row, +1 gap
    ws.cell(r_total, 1, "").font = F_LABEL_B
    ws.cell(r_total, 2, "ИТОГО").font = F_LABEL_B

    # Total formulas per year
    for yr_idx in range(n_fc):
        base_col = 8 + yr_idx * yr_cols_per
        for j in range(yr_cols_per):
            col = base_col + j
            col_letter = get_column_letter(col)
            formula_cell(ws, r_total, col,
                         f"=SUM({col_letter}5:{col_letter}{r_total - 1})", FMT_MLN, bold=True)

    # Store key row/col references for 17_Debt linkage
    REG["DS.total_row"] = r_total
    REG["DS.yr_start_col"] = 8
    REG["DS.cols_per_year"] = yr_cols_per
    REG["DS.max_instruments"] = max_instruments

    # Hide sheet (technical)
    ws.sheet_state = 'hidden'


def build_other_is(wb, cfg):
    """14_OtherIS — other income statement items (impairment, associates, etc.)."""
    ws = wb["14_OtherIS"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"14_OtherIS — {cfg['name']}").font = F_TITLE
    ws.cell(2, 1, "Прочие статьи PL: обесценение, ассоциированные, прочие финансовые").font = F_SUBTITLE
    n_hist = len(cfg["hist_years"][-3:])
    year_headers(ws, 4, cfg["hist_years"][-3:], cfg["fc_years"])

    section_header(ws, 6, "ПРОЧИЕ ДОХОДЫ И РАСХОДЫ")
    for key, label, unit in [
        ("associates", "Доля в ассоциированных и СП", "mln"),
        ("impairment", "Обесценение внеоборотных активов", "mln"),
        ("other_opex", "Прочие операционные расходы", "mln"),
        ("interest_income", "Процентный доход (по депозитам)", "mln"),
        ("other_fin", "Прочие финансовые доходы/расходы", "mln"),
    ]:
        r = REG[f"OI.{key}"]
        label_row(ws, r, label, unit)
        # History: input (fill_data fills)
        for c in range(3, 3 + n_hist):
            input_cell(ws, r, c, 0, FMT_MLN)
        # Forecast: carry forward from last history (not empty)
        for c in range(3 + n_hist, 3 + n_hist + len(cfg["fc_years"])):
            prev = get_column_letter(c - 1)
            formula_cell(ws, r, c, f"={prev}{r}", FMT_MLN)


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
        ("03_Assump",       build_assump),
        ("Raw_IFRS",        build_raw_ifrs),
        ("02_Hist",         build_hist),
        ("05_Drivers",      build_drivers),
        ("11_Segments",     build_segments),
        ("10_Revenue",      build_revenue),
        ("12_COGS",         build_cogs),
        ("13_SGA",          build_sga),
        ("14_OtherIS",      build_other_is),
        ("15_PPE",          build_ppe),
        ("16_WC",           build_wc),
        ("17_Debt",         build_debt),
        ("18_Lease",        build_lease),
        ("19_Tax",          build_tax),
        ("20_BS",           build_bs),
        ("21_PL",           build_pl),
        ("23_CF",           build_cf),
        ("24_Equity",       build_equity),
        ("30_Ratios",       build_ratios),
        ("31_Score",        build_score),
        ("32_Covenants",    build_covenants),
        ("33_RevStress",    build_revstress),
        ("35_Valuation",    build_valuation),
        ("40_Scen",         build_scenarios),
        ("90_Checks",       build_checks),
        ("Model_Output",    build_model_output),
        ("_Debt_Schedule",  build_debt_schedule),
        ("Changelog",       build_changelog),
    ]
    for name, builder in builders:
        print(f"  {name}...")
        builder(wb, cfg)

    # ── Save updated REG to reg.json (so fill_data sees runtime keys) ──
    reg_path = BASE_DIR / "reg.json"
    reg_path.write_text(json.dumps(REG, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── Post-processing: Excel settings ──
    print("  Post-processing...")

    # Enable Iterative Calculation (for circular: Debt ↔ Interest ↔ Cash)
    # openpyxl: wb.calculation.iterate = True, iterateCount, iterateDelta
    if wb.calculation is None:
        from openpyxl.workbook.properties import CalcProperties
        wb.calculation = CalcProperties()
    wb.calculation.iterate = True
    wb.calculation.iterateCount = 1000
    wb.calculation.iterateDelta = 0.000001  # 1e-6 like bank model
    # fullCalcOnLoad=True — recalc on open (audit requires cold start = warm start)
    wb.calculation.fullCalcOnLoad = True

    # Named ranges for circular solver (bank model pattern)
    # calc_reset: 0 = iterate (normal), 1 = seed (decouple circular refs)
    from openpyxl.workbook.defined_name import DefinedName
    # Add calc_reset cell in Control_Panel row 1 col K (hidden)
    ws_cp = wb["Control_Panel"]
    ws_cp.cell(1, 11, 0)  # K1 = 0 (iterate mode)
    ws_cp.cell(1, 11).font = F_NOTE
    ws_cp.cell(1, 12, "calc_reset: 0=iterate, 1=seed").font = F_NOTE
    ws_cp.cell(2, 11, "relax (демпфирование)").font = F_NOTE
    ws_cp.cell(2, 12, 1.0).font = F_INPUT
    ws_cp.cell(2, 12).number_format = FMT_RATIO
    dn = DefinedName("calc_reset", attr_text="'Control_Panel'!$K$1")
    wb.defined_names.add(dn)

    # ── Ergonomics ──

    # 1. Freeze panes on ALL sheets with data
    for sname in wb.sheetnames:
        ws = wb[sname]
        if ws.max_row > 5:
            ws.freeze_panes = "C5"

    # 2. Column widths for all sheets
    for sname in wb.sheetnames:
        ws = wb[sname]
        if ws.column_dimensions['A'].width is None or ws.column_dimensions['A'].width < 10:
            apply_col_widths(ws)

    # 3. Sheet protection (protect formula sheets, unlock input sheets)
    from openpyxl.worksheet.protection import SheetProtection
    input_sheets = {"00_Cover", "Control_Panel", "01_Macro", "02_Hist",
                    "05_Drivers", "Raw_IFRS", "10_Revenue", "11_Segments",
                    "14_OtherIS", "33_RevStress", "40_Scen", "Changelog"}
    for sname in wb.sheetnames:
        ws = wb[sname]
        if sname not in input_sheets:
            ws.protection = SheetProtection(sheet=True, password='vertex',
                                           formatCells=False, formatColumns=False,
                                           formatRows=False, sort=True, autoFilter=True)

    # 4. Number format fix: ensure no General format on data cells
    for sname in wb.sheetnames:
        ws = wb[sname]
        for row in ws.iter_rows(min_row=5, max_row=ws.max_row, min_col=3, max_col=11):
            for c in row:
                if isinstance(c.value, (int, float)) and c.number_format == 'General':
                    c.number_format = FMT_MLN

    # 5. Data validation on key switches (J1)
    from openpyxl.worksheet.datavalidation import DataValidation
    ws_cp = wb["Control_Panel"]
    # Scenario switch: 1-3
    dv_scen = DataValidation(type="whole", operator="between",
                             formula1="1", formula2="3",
                             errorTitle="Ошибка", error="Сценарий: 1, 2 или 3")
    dv_scen.add("C5")
    ws_cp.add_data_validation(dv_scen)
    # Method switches: 1-3
    for r_label in ["Revenue method", "COGS method", "WC method"]:
        for r in range(4, 100):
            if ws_cp.cell(r, 1).value and r_label in str(ws_cp.cell(r, 1).value):
                dv = DataValidation(type="whole", operator="between",
                                    formula1="1", formula2="3")
                dv.add(f"C{r}")
                ws_cp.add_data_validation(dv)
                break
    # new_debt_available: 0 or 1
    nd_row = REG.get("CP.new_debt_available")
    if nd_row:
        dv_nd = DataValidation(type="whole", operator="between",
                               formula1="0", formula2="1")
        dv_nd.add(f"C{nd_row}")
        ws_cp.add_data_validation(dv_nd)

    # 6. Unlock input cells on protected sheets (J2)
    from openpyxl.styles import Protection as CellProtection
    for sname in wb.sheetnames:
        ws = wb[sname]
        if sname not in input_sheets and ws.protection.sheet:
            # Unlock cells with F_INPUT font (blue = input)
            for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=15):
                for c in row:
                    if c.font and c.font.color and hasattr(c.font.color, 'rgb'):
                        if c.font.color.rgb and '0000FF' in str(c.font.color.rgb):
                            c.protection = CellProtection(locked=False)

    # 7. Back-navigation hyperlinks to 00_Guide (I7)
    for sname in wb.sheetnames:
        ws = wb[sname]
        if sname != "00_Guide" and ws.max_row > 2:
            link_cell = ws.cell(1, 10)  # J1
            link_cell.value = "← 00_Guide"
            link_cell.font = Font(color="3F5A73", size=9, underline="single")
            link_cell.hyperlink = f"#'00_Guide'!A1"

    # 8. Row grouping for detail sections (I4)
    # Group instrument details, Sources & Uses, calibration
    try:
        ws_dt = wb["17_Debt"]
        ws_dt.sheet_properties.outlinePr = openpyxl.worksheet.properties.Outline(
            summaryBelow=True)
        # Group S&U details (rows 7-21)
        ws_dt.row_dimensions.group(7, 21, outline_level=1, hidden=False)
        # Group calibration
        cal_start = REG.get("DT.cal_st_share", 79)
        cal_end = REG.get("DT.cal_st_flag", 84)
        if cal_start:
            ws_dt.row_dimensions.group(cal_start, cal_end, outline_level=1, hidden=True)
    except Exception:
        pass  # grouping is optional

    # Set metadata
    wb.properties.creator = "Vertex Corporate Model v4"
    wb.properties.title = f"Финансовая модель — {cfg['name']}"
    wb.properties.description = (
        f"3-Statement Excel-driven model for {cfg['name']}. "
        f"30 sheets, {len(cfg['fc_years'])} forecast years. "
        f"Generated by build_model.py (stressTest_v2 templates/excel_v4)."
    )

    # Count formulas for report
    total_f = sum(1 for s in wb.sheetnames
                  for row in wb[s].iter_rows()
                  for c in row
                  if isinstance(c.value, str) and c.value.startswith('='))

    # Save
    output_path = BASE_DIR / output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(output_path))

    # Post-process: strip empty <v></v> nodes (causes Excel repair dialog)
    import zipfile, re, shutil, tempfile
    tmp = tempfile.mktemp(suffix=".xlsx")
    with zipfile.ZipFile(str(output_path), 'r') as zin:
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
            empty_v_count = 0
            for item in zin.infolist():
                data = zin.read(item.filename)
                # Fix calcPr: add fullCalcOnLoad if missing
                if item.filename == "xl/workbook.xml":
                    text = data.decode("utf-8")
                    if "fullCalcOnLoad" not in text:
                        text = text.replace('iterate="1"', 'fullCalcOnLoad="1" iterate="1"')
                        data = text.encode("utf-8")
                if item.filename.startswith("xl/worksheets/"):
                    text = data.decode("utf-8")
                    cleaned = text.replace("<v></v>", "")
                    removed = (len(text) - len(cleaned)) // len("<v></v>") if "<v></v>" in text else 0
                    empty_v_count += removed
                    data = cleaned.encode("utf-8")
                zout.writestr(item, data)
    shutil.move(tmp, str(output_path))
    if empty_v_count:
        print(f"  Stripped {empty_v_count} empty <v></v> nodes")

    print(f"\n✓ Saved: {output_path}")
    print(f"  Sheets: {len(wb.sheetnames)}")
    print(f"  Formulas: {total_f}")
    print(f"  Company: {cfg['name']}")
    print(f"  Iterative Calc: ON (100 iter, 0.001 delta)")
    print(f"  Freeze panes: 12 sheets")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Corporate Financial Model v4")
    parser.add_argument("--company", required=True, choices=["rusal", "nornickel"])
    parser.add_argument("--output", default="model/model_v4.xlsx")
    args = parser.parse_args()
    build(args.company, args.output)
