#!/usr/bin/env python3
"""
Fill corporate model v4 with historical data from multiple sources:
  1. stressTest_v2 Excel templates (rusal_complete_v4.xlsx, nornickel unified)
  2. stressTest_v2 SQLite database (data_mart_v2.db)
  3. Vertex PostgreSQL (stress_v2.*, market_data.*)

Usage:
    python scripts/fill_data.py --company rusal --model model/rusal_v4.xlsx
    python scripts/fill_data.py --company nornickel --model model/nornickel_v4.xlsx
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

import openpyxl
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from styles import *

BASE_DIR = Path(__file__).resolve().parent.parent
SV2_ROOT = BASE_DIR.parent.parent  # stressTest_v2 root
REG = json.loads((BASE_DIR / "reg.json").read_text(encoding="utf-8"))


def discover_cp_rows(wb):
    """Find Control_Panel parameter rows by label search.
    CP.* keys are set at runtime by build_model, not in reg.json.
    This function discovers them from the built workbook."""
    ws = wb["Control_Panel"]
    label_map = {
        "min cash": "CP.min_cash",
        "rc лимит": "CP.rc_limit",
        "rc ставка": "CP.rc_rate",
        "commitment fee": "CP.commit_fee_rate",
        "maint_share": "CP.maint_share",
        "sweep": "CP.sweep_pct",
        "target nd": "CP.target_leverage",
        "buffer": "CP.buffer",
        "refi % (облигации": "CP.refi_pct_bonds",
        "refi % (банковский": "CP.refi_pct_bank",
        "rc trigger": "CP.rc_trigger",
        "тенор нового": "CP.term_tenor",
        "spread base": "CP.spread_base",
        "spread step": "CP.spread_step",
        "доступность нового": "CP.new_debt_available",
        "премия за досрочное": "CP.prepay_premium",
        "ковенант: nd": "CP.cov_nd_ebitda",
        "ковенант: icr": "CP.cov_icr",
        "fx usdcny": "CP.fx_usdcny_chg",
        "fx usdrub": "CP.fx_usdrub_chg",
        "доля выручки в cny": "CP.rev_cny_share",
        "доля выручки в rub": "CP.rev_rub_share",
        "доля затрат в rub": "CP.cost_rub_share",
        "statutory tax": "CP.tax_rate",
        "nol opening": "CP.nol_open",
        "nol max": "CP.nol_cap",
        "risk-free": "CP.wacc_rf",
        "beta": "CP.wacc_beta",
        "equity risk": "CP.wacc_erp",
        "country risk": "CP.wacc_crp",
        "size premium": "CP.wacc_scp",
        "terminal growth": "CP.terminal_g",
        "terminal ev": "CP.terminal_mult",
        "leverage weight": "CP.sc_w_lev",
        "coverage weight": "CP.sc_w_cov",
        "profitability weight": "CP.sc_w_prof",
        "liquidity weight": "CP.sc_w_liq",
        "industry adj": "CP.sc_ind_adj",
        "size adj": "CP.sc_size_adj",
        "cycle avg": "CP.sc_cycle_margin",
        "cogs ratio": "CP.cogs_ratio",
        "доля material": "CP.cogs_material",
        "доля energy": "CP.cogs_energy",
        "доля labour": "CP.cogs_labour",
        "доля other": "CP.cogs_other",
        "useful life": "CP.useful_life",
        "тенор refi": "CP.term_tenor",
        "тенор capex": "CP.term_tenor_capex",
        "штрафная ставка": "CP.penalty_rate",
        "covenant reclass": "CP.cov_reclass",
        "disposal %": "CP.disposal_pct",
        "dso (дни": "CP.wc_dso",
        "dih (дни": "CP.wc_dio",
        "dpo (дни": "CP.wc_dpo",
    }
    for r in range(4, 100):
        val = ws.cell(r, 1).value
        if not val:
            continue
        val_lower = str(val).lower()
        for pattern, key in label_map.items():
            if pattern in val_lower and key not in REG:
                REG[key] = r
    found = sum(1 for k in label_map.values() if k in REG)
    if found > 0:
        print(f"    CP rows discovered: {found}/{len(label_map)}")

# ── Unified column layout (must match build_model.py) ────────────────────────
# ALL sheets: C-E = 3 hist years (2023-2025), F-H = 3 forecast years (2026E-2028E)
N_HIST_DISPLAY = 3   # last 3 years shown in model sheets
COL_START = 3        # col C = first year

# ── Source data paths ────────────────────────────────────────────────────────

SOURCES = {
    "rusal": {
        "excel": SV2_ROOT / "companies/rusal/data/rusal_complete_v4.xlsx",
        "sqlite": SV2_ROOT / "companies/rusal/data/data_mart_v2.db",
        "hist_years": list(range(2011, 2026)),
        "fc_years": [2026, 2027, 2028],
    },
    "nornickel": {
        "excel": SV2_ROOT / "companies/nornickel/data/excel/nornickel_unified.xlsx",
        "excel_alt": SV2_ROOT / "companies/nornickel_v2/data/excel/nornickel_v2_template_v3.xlsx",
        "sqlite": SV2_ROOT / "companies/nornickel_v2/data/data_mart_v2.db",
        "hist_years": list(range(2010, 2026)),
        "fc_years": [2026, 2027, 2028],
    },
}

# IS metric mapping: source_metric → (display_label, reg_key, sign_flip)
IS_MAP = {
    "revenue": ("Выручка", "revenue", False),
    "cogs": ("Себестоимость", "cogs", False),
    "gross_profit": ("Валовая прибыль", "gp", False),
    "sga": ("SGA (комм.+адм.)", "sga", False),
    "total_da": ("D&A", "da", True),  # stored positive in source
    "ebitda": ("EBITDA", "ebitda", False),
    "ebit": ("EBIT", "ebit", False),
    "interest_expense": ("Процентные расходы", "interest", False),
    "finance_cost_net": ("Фин. расходы (нетто)", "interest", False),  # Nornickel alias
    "interest_income": ("Процентные доходы", None, False),
    "other_operating_expenses": ("Прочие опер. расходы", None, False),
    "ebt": ("Прибыль до налога", "ebt", False),
    "tax_expense": ("Налог на прибыль", "tax", False),
    "net_income": ("Чистая прибыль", "ni", False),
    "earnings_from_investees": ("Доля в ассоциированных", None, False),
    "distribution_expenses": ("Коммерческие расходы", None, False),
    "asset_impairment": ("Обесценение активов", None, False),
    "dep_ppe": ("Амортизация ОС", None, True),
    "amort_intangibles": ("Амортизация НМА", None, True),
    "current_tax": ("Текущий налог", None, False),
    "deferred_tax": ("Отложенный налог", None, False),
    "expected_credit_losses": ("Расходы по ECL", None, False),
}

BS_MAP = {
    "cash": ("Денежные средства", "cash"),
    "accounts_receivable": ("Дебиторская задолженность", "ar"),
    "inventory": ("Запасы", "inv"),
    "ppe_net": ("ОС (нетто)", "ppe_net"),
    "ppe_gross": ("ОС (валовая стоимость)", "ppe_gross"),
    "ppe_accum_dep": ("Накопленная амортизация", "accdep"),
    "goodwill": ("Гудвилл", "goodwill"),
    "intangibles": ("Нематериальные активы", "intang"),
    "rou_asset": ("Активы ПИ (ROU)", "rou"),
    "dta": ("Отложенный нал. актив", "dta"),
    "short_term_debt": ("Краткосрочный долг", "st_debt"),
    "long_term_debt": ("Долгосрочный долг", "lt_debt"),
    "accounts_payable": ("Кредиторская задолженность", "ap"),
    "lease_liab_current": ("Аренда (кратк.)", "lease_cl"),
    "lease_liab_noncurrent": ("Аренда (долг.)", "lease_ncl"),
    "provisions": ("Резервы", "prov"),
    "dtl": ("Отложенное нал. обяз.", "dtl"),
    "total_assets": ("Итого активы", "ta"),
    "total_liabilities": ("Итого обязательства", "tl"),
    "total_equity": ("Собственный капитал", "equity"),
    "retained_earnings": ("Нераспр. прибыль", "re"),
}

CF_MAP = {
    "cfo_total": ("Операционный CF", "cfo"),
    "cfi_total": ("Инвестиционный CF", "cfi"),
    "cff_total": ("Финансовый CF", "cff"),
    "net_change": ("Чистое изменение ДС", "net_change"),
    "capex": ("Капитальные затраты", "capex"),
}


def load_source_data(company: str) -> Dict[str, Any]:
    """Load data from Excel source file."""
    src = SOURCES[company]
    excel_path = src["excel"]
    if not excel_path.exists():
        excel_path = src.get("excel_alt", excel_path)
    if not excel_path.exists():
        print(f"  ⚠ Source Excel not found: {excel_path}")
        return {}

    print(f"  Reading: {excel_path.name}")
    wb = openpyxl.load_workbook(str(excel_path), data_only=True)
    data = {"is": {}, "bs": {}, "cf": {}, "segments": [], "macro": [], "debt": []}

    # ── IS ──
    if "history_is" in wb.sheetnames:
        ws = wb["history_is"]
        headers = [c.value for c in ws[1]]
        year_cols = {int(h): i for i, h in enumerate(headers) if isinstance(h, (int, float)) and h > 2000}
        for row in ws.iter_rows(min_row=2, values_only=True):
            metric = str(row[0] or "").strip()
            if not metric:
                continue
            for year, col_idx in year_cols.items():
                val = row[col_idx] if col_idx < len(row) else None
                if val is not None and isinstance(val, (int, float)):
                    data["is"].setdefault(metric, {})[year] = float(val)

    # ── BS ──
    if "history_bs" in wb.sheetnames:
        ws = wb["history_bs"]
        headers = [c.value for c in ws[1]]
        year_cols = {int(h): i for i, h in enumerate(headers) if isinstance(h, (int, float)) and h > 2000}
        for row in ws.iter_rows(min_row=2, values_only=True):
            metric = str(row[0] or "").strip()
            if not metric:
                continue
            for year, col_idx in year_cols.items():
                val = row[col_idx] if col_idx < len(row) else None
                if val is not None and isinstance(val, (int, float)):
                    data["bs"].setdefault(metric, {})[year] = float(val)

    # ── CF ──
    if "history_cf" in wb.sheetnames:
        ws = wb["history_cf"]
        headers = [c.value for c in ws[1]]
        # CF may have different first column name
        year_cols = {}
        for i, h in enumerate(headers):
            if isinstance(h, (int, float)) and h > 2000:
                year_cols[int(h)] = i
        for row in ws.iter_rows(min_row=2, values_only=True):
            # CF uses different column layout: could be col 0 or col 2 for metric name
            metric = None
            for ci in [0, 1, 2]:
                if ci < len(row) and isinstance(row[ci], str) and row[ci].strip():
                    metric = row[ci].strip()
                    break
            if not metric:
                continue
            for year, col_idx in year_cols.items():
                val = row[col_idx] if col_idx < len(row) else None
                if val is not None and isinstance(val, (int, float)):
                    data["cf"].setdefault(metric, {})[year] = float(val)

    # ── Segments ──
    for sheet_name in ["segments_operational", "segments_financial", "Production_KPI"]:
        if sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            headers = [c.value for c in ws[1]]
            year_cols = {int(h): i for i, h in enumerate(headers) if isinstance(h, (int, float)) and h > 2000}
            for row in ws.iter_rows(min_row=2, values_only=True):
                seg_name = str(row[0] or "").strip()
                metric = str(row[1] or "").strip() if len(row) > 1 else ""
                if not seg_name:
                    continue
                for year, col_idx in year_cols.items():
                    val = row[col_idx] if col_idx < len(row) else None
                    if val is not None and isinstance(val, (int, float)):
                        data["segments"].append({
                            "segment": seg_name, "metric": metric,
                            "year": year, "value": float(val),
                        })

    # ── Macro ──
    if "macro_factors" in wb.sheetnames:
        ws = wb["macro_factors"]
        headers = [c.value for c in ws[1]]
        year_cols = {int(h): i for i, h in enumerate(headers) if isinstance(h, (int, float)) and h > 2000}
        for row in ws.iter_rows(min_row=2, values_only=True):
            factor = str(row[0] or "").strip()
            if not factor:
                continue
            for year, col_idx in year_cols.items():
                val = row[col_idx] if col_idx < len(row) else None
                if val is not None and isinstance(val, (int, float)):
                    data["macro"].append({"factor": factor, "year": year, "value": float(val)})

    # ── Debt ──
    if "debt_instruments" in wb.sheetnames:
        ws = wb["debt_instruments"]
        headers = [str(c.value or "").strip() for c in ws[1]]
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[0] is None:
                continue
            inst = {}
            for i, h in enumerate(headers):
                if i < len(row) and row[i] is not None:
                    inst[h] = row[i]
            if inst:
                data["debt"].append(inst)

    wb.close()

    # Try supplementary file for segments/operational if primary had none
    if not data["segments"] and src.get("excel_alt"):
        alt = src["excel_alt"]
        if alt.exists():
            print(f"  Reading supplementary: {alt.name}")
            wb2 = openpyxl.load_workbook(str(alt), data_only=True)
            for sheet_name in ["segments_operational", "segments_financial", "Production_KPI",
                               "operational_drivers", "segments"]:
                if sheet_name in wb2.sheetnames:
                    ws2 = wb2[sheet_name]
                    headers = [c.value for c in ws2[1]]
                    year_cols = {int(h): i for i, h in enumerate(headers)
                                 if isinstance(h, (int, float)) and h > 2000}
                    for row in ws2.iter_rows(min_row=2, values_only=True):
                        seg_name = str(row[0] or "").strip()
                        metric = str(row[1] or "").strip() if len(row) > 1 else ""
                        if not seg_name:
                            continue
                        for year, col_idx in year_cols.items():
                            val = row[col_idx] if col_idx < len(row) else None
                            if val is not None and isinstance(val, (int, float)):
                                data["segments"].append({
                                    "segment": seg_name, "metric": metric,
                                    "year": year, "value": float(val),
                                })
            # Also get macro from alt
            if "macro_factors" in wb2.sheetnames and not data["macro"]:
                ws2 = wb2["macro_factors"]
                headers = [c.value for c in ws2[1]]
                year_cols = {int(h): i for i, h in enumerate(headers)
                             if isinstance(h, (int, float)) and h > 2000}
                for row in ws2.iter_rows(min_row=2, values_only=True):
                    factor = str(row[0] or "").strip()
                    if not factor:
                        continue
                    for year, col_idx in year_cols.items():
                        val = row[col_idx] if col_idx < len(row) else None
                        if val is not None and isinstance(val, (int, float)):
                            data["macro"].append({"factor": factor, "year": year, "value": float(val)})
            # Also load debt_instruments from supplementary
            if "debt_instruments" in wb2.sheetnames and not data["debt"]:
                ws_di = wb2["debt_instruments"]
                for row in ws_di.iter_rows(min_row=2, values_only=True):
                    if row[0] is None:
                        continue
                    # Explicit column mapping (template_v3 format):
                    # 0=id, 1=name, 2=db_type, 3=ccy, 4=balance_mUSD, 5=maturity/rate_shifted,
                    # 6=rate_type_shifted, 7=rate_type, 8=base_rate
                    bal_raw = row[4] if len(row) > 4 else 0
                    # Detect shifted columns: if col 5 is float < 1 → it's rate, not maturity
                    col5 = row[5] if len(row) > 5 else None
                    col6 = row[6] if len(row) > 6 else None
                    col7 = row[7] if len(row) > 7 else None

                    if isinstance(col5, (int, float)) and col5 < 1:
                        # Shifted: col5=rate, col6=rate_type
                        rate = float(col5)
                        rate_type = str(col6 or "fixed")
                        maturity = ""
                    else:
                        maturity = str(col5 or "")
                        rate = float(col6 or 0)
                        rate_type = str(col7 or "fixed")

                    # Infer maturity from instrument name (1yr → 2026, 3yr → 2028)
                    name = str(row[1] or "")
                    if not maturity:
                        if "1y" in name.lower():
                            maturity = "2026"
                        elif "3y" in name.lower():
                            maturity = "2028"
                        elif "5y" in name.lower():
                            maturity = "2030"

                    inst = {
                        "instrument_id": str(row[0] or ""),
                        "instrument_name": name,
                        "db_type": str(row[2] or ""),
                        "currency": str(row[3] or "USD"),
                        "opening_balance": float(bal_raw or 0) * 1e6,
                        "interest_rate": rate,
                        "rate_type": rate_type.lower(),
                        "maturity_date": maturity,
                    }
                    data["debt"].append(inst)
                print(f"    Supplementary debt: {len(data['debt'])} instruments loaded")

            wb2.close()
            print(f"    Supplementary segments: {len(data['segments'])} rows")

    return data


def fill_hist_sheet(wb, data: dict, company: str):
    """Fill 02_Hist with IS/BS/CF data.

    02_Hist uses FULL history (all years, cols C onwards).
    Other sheets use only last 3 years.
    """
    ws = wb["02_Hist"]
    src = SOURCES[company]
    hist_years = src["hist_years"]  # FULL history for 02_Hist

    # Write year headers for full history
    year_headers(ws, 4, hist_years, [])

    # Fill IS
    print(f"    IS: {len(data.get('is', {}))} metrics")
    for metric, years_data in sorted(data.get("is", {}).items()):
        map_entry = IS_MAP.get(metric)
        if not map_entry:
            continue
        label, reg_key, sign_flip = map_entry
        if reg_key is None:
            continue
        r = REG.get(f"HI.{reg_key}")
        if r is None:
            continue
        label_row(ws, r, label, "mln")
        for year, val in years_data.items():
            if year in hist_years:
                col = 3 + hist_years.index(year)
                v = abs(val) if sign_flip else val
                cell = ws.cell(r, col, round(v, 1))
                cell.font = F_INPUT
                cell.number_format = FMT_MLN

    # Fill BS
    print(f"    BS: {len(data.get('bs', {}))} metrics")
    for metric, years_data in sorted(data.get("bs", {}).items()):
        map_entry = BS_MAP.get(metric)
        if not map_entry:
            continue
        label, reg_key = map_entry
        r = REG.get(f"HI.{reg_key}")
        if r is None:
            continue
        label_row(ws, r, label, "mln")
        for year, val in years_data.items():
            if year in hist_years:
                col = 3 + hist_years.index(year)
                cell = ws.cell(r, col, round(val, 1))
                cell.font = F_INPUT
                cell.number_format = FMT_MLN

    # Compute EBITDA where missing: EBITDA = GP - SGA + DA (all absolute)
    is_d = data.get("is", {})
    ebitda_hist = is_d.get("ebitda", {})
    gp_hist = is_d.get("gross_profit", {})
    sga_hist = is_d.get("sga", {})
    da_hist = is_d.get("total_da", is_d.get("dep_ppe", {}))
    dist_hist = is_d.get("distribution_expenses", {})
    r_ebitda = REG.get("HI.ebitda")
    if r_ebitda:
        computed = 0
        for year in hist_years:
            col = 3 + hist_years.index(year)
            existing = ws.cell(r_ebitda, col).value
            if (existing is None or existing == 0) and year in gp_hist:
                gp = gp_hist.get(year, 0)
                sga = sga_hist.get(year, 0)
                da = da_hist.get(year, 0)
                dist = dist_hist.get(year, 0)
                ebitda = abs(gp) + sga + dist + abs(da)  # SGA/dist are negative
                if ebitda != 0:
                    cell = ws.cell(r_ebitda, col, round(ebitda, 1))
                    cell.font = F_INPUT
                    cell.number_format = FMT_MLN
                    computed += 1
        if computed > 0:
            print(f"    EBITDA: computed {computed} missing years (GP+SGA+DA)")

    # Fill CF
    print(f"    CF: {len(data.get('cf', {}))} metrics")
    for metric, years_data in sorted(data.get("cf", {}).items()):
        map_entry = CF_MAP.get(metric)
        if not map_entry:
            continue
        label, reg_key = map_entry
        r = REG.get(f"HI.{reg_key}")
        if r is None:
            continue
        label_row(ws, r, label, "mln")
        for year, val in years_data.items():
            if year in hist_years:
                col = 3 + hist_years.index(year)
                cell = ws.cell(r, col, round(val, 1))
                cell.font = F_INPUT
                cell.number_format = FMT_MLN


def fill_segments(wb, data: dict, company: str):
    """Fill 11_Segments with operational data (uses wider history for context)."""
    ws = wb["11_Segments"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"11_Segments — Operational Data").font = F_TITLE

    src = SOURCES[company]
    hist_years = src["hist_years"][-8:]  # 8 years for segments (wider view)
    year_headers(ws, 4, hist_years, src["fc_years"])

    segments_data = data.get("segments", [])
    if not segments_data:
        ws.cell(6, 1, "Нет данных по сегментам").font = F_NOTE
        return

    # Group by segment → metric
    grouped: Dict[str, Dict[str, Dict[int, float]]] = {}
    for item in segments_data:
        seg = item["segment"]
        met = item["metric"]
        yr = item["year"]
        val = item["value"]
        grouped.setdefault(seg, {}).setdefault(met, {})[yr] = val

    r = 6
    print(f"    Segments: {len(grouped)} segments")
    for seg_name, metrics in sorted(grouped.items()):
        section_header(ws, r, seg_name)
        r += 1
        for met_name, years_data in sorted(metrics.items()):
            label_row(ws, r, met_name)
            for year, val in years_data.items():
                if year in hist_years:
                    col = 3 + hist_years.index(year)
                    cell = ws.cell(r, col, round(val, 2))
                    cell.font = F_INPUT
                    cell.number_format = FMT_MLN if abs(val) > 100 else FMT_RATIO1
            r += 1
        r += 1  # gap between segments


def fill_macro(wb, data: dict, company: str):
    """Fill 01_Macro with historical macro factors."""
    ws = wb["01_Macro"]
    macro_data = data.get("macro", [])
    if not macro_data:
        return

    src = SOURCES[company]
    hist_years = src["hist_years"][-8:]

    # Group by factor
    factors: Dict[str, Dict[int, float]] = {}
    for item in macro_data:
        factors.setdefault(item["factor"], {})[item["year"]] = item["value"]

    # Find empty rows after existing content to add historical macro
    r = 55  # After scenario sections
    section_header(ws, r, "ИСТОРИЧЕСКИЕ МАКРО-ФАКТОРЫ")
    r += 1
    year_headers(ws, r, hist_years, [])
    r += 1

    print(f"    Macro: {len(factors)} factors")
    for factor_name, years_data in sorted(factors.items()):
        label_row(ws, r, factor_name)
        for year, val in years_data.items():
            if year in hist_years:
                col = 3 + hist_years.index(year)
                cell = ws.cell(r, col, round(val, 4))
                cell.font = F_INPUT
                cell.number_format = FMT_RATIO if abs(val) < 100 else FMT_MLN0
        r += 1


def fill_revenue(wb, data: dict, company: str):
    """Fill 10_Revenue with historical segment volumes & prices.

    Sources: segments_operational from Excel + project.yaml for missing years.
    """
    ws = wb["10_Revenue"]
    segments_data = data.get("segments", [])

    seg_vp: Dict[str, Dict[str, Dict[int, float]]] = {}
    for item in segments_data:
        seg = item["segment"]
        met = item["metric"]
        if met in ("sales_kt", "production_kt", "avg_price_usd_t", "revenue"):
            seg_vp.setdefault(seg, {}).setdefault(met, {})[item["year"]] = item["value"]

    # Supplement from project.yaml (has volume_history and price_history with 2025)
    yaml_path = SV2_ROOT / f"companies/{company}/configs/project.yaml"
    if yaml_path.exists():
        import yaml
        proj = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        custom_segs = proj.get("model", {}).get("custom", {}).get("revenue", {}).get("segments", {})
        for seg_key, seg_cfg in custom_segs.items():
            # Map yaml segment name to display name
            name_map = {
                "primary_al": "Primary Aluminium",
                "alumina": "Alumina",
                "other": "Other",
                "nickel": "Nickel",
                "copper": "Copper",
                "pgm": "PGM",
                "palladium": "PGM",  # palladium maps to PGM segment
                "platinum": "Platinum",
            }
            display_name = name_map.get(seg_key, seg_key.title())
            vol_hist = seg_cfg.get("volume_history", {})
            price_hist = seg_cfg.get("price_history", {})

            for yr, vol in vol_hist.items():
                yr = int(yr)
                seg_vp.setdefault(display_name, {}).setdefault("sales_kt", {})[yr] = float(vol)
            for yr, price in price_hist.items():
                yr = int(yr)
                # YAML prices may be in tUSD (×1000) — normalize to $/t
                p = float(price)
                if p > 100000:  # likely in tUSD units (e.g., 2652000 = $2652/t × 1000)
                    p = p / 1000
                seg_vp.setdefault(display_name, {}).setdefault("avg_price_usd_t", {})[yr] = p

    src = SOURCES[company]
    hist_years = src["hist_years"][-N_HIST_DISPLAY:]  # 3 years (match model layout)

    print(f"    Revenue segments: {len(seg_vp)} with volume/price data")
    # Fill into existing revenue rows (seg1, seg2, seg3)
    seg_configs = {
        "rusal": [("Primary Aluminium", "seg1"), ("Alumina", "seg2"), ("Other", "seg3")],
        "nornickel": [("Nickel", "seg1"), ("Copper", "seg2"), ("PGM", "seg3")],
    }

    for seg_label, key in seg_configs.get(company, []):
        # Find matching segment data
        matching = None
        for seg_name in seg_vp:
            if seg_label.lower() in seg_name.lower():
                matching = seg_vp[seg_name]
                break

        if not matching:
            continue

        # Fill into 11_Segments (single source); 10_Revenue refs 11_Segments
        sg_vol_r = REG.get(f"SG.{key}_vol")
        sg_price_r = REG.get(f"SG.{key}_price")
        ws_sg = wb["11_Segments"]

        vol_data = matching.get("sales_kt", matching.get("production_kt", {}))
        price_data = matching.get("avg_price_usd_t", {})
        rev_data = matching.get("revenue", {})

        for year in hist_years:
            if year not in vol_data and year not in rev_data:
                continue
            col = 3 + hist_years.index(year)

            if year in vol_data and sg_vol_r:
                ws_sg.cell(sg_vol_r, col, round(vol_data[year], 0)).font = F_INPUT
                ws_sg.cell(sg_vol_r, col).number_format = FMT_INT
                print(f"      11_Seg: {seg_label} vol {year}={vol_data[year]:.0f} → r{sg_vol_r} c{col}")
            if year in price_data and sg_price_r:
                ws_sg.cell(sg_price_r, col, round(price_data[year], 0)).font = F_INPUT
                ws_sg.cell(sg_price_r, col).number_format = FMT_INT
                print(f"      11_Seg: {seg_label} price {year}={price_data[year]:.0f} → r{sg_price_r} c{col}")

        # Forecast: macro-driven price via OLS chain-link or EWA carry-forward
        fc_years = src["fc_years"]
        fc_start_col = COL_START + N_HIST_DISPLAY

        # Volume: EWA growth from last 3 years
        last_vol = vol_data.get(hist_years[-1], vol_data.get(hist_years[-2], 0))
        vol_vals = [vol_data.get(yr, 0) for yr in hist_years if vol_data.get(yr, 0) > 0]
        if len(vol_vals) >= 2:
            import math
            growth_rates = [math.log(vol_vals[i] / vol_vals[i-1])
                           for i in range(1, len(vol_vals)) if vol_vals[i-1] > 0]
            avg_growth = sum(growth_rates) / len(growth_rates) if growth_rates else 0
        else:
            avg_growth = 0

        # Price: macro-driven (OLS β × Δln(factor)) or EWA
        last_price = price_data.get(hist_years[-1], price_data.get(hist_years[-2], 0))

        # Find macro factor data for OLS
        factor_name = None
        seg_cfg_yaml = {}
        yaml_path = SV2_ROOT / f"companies/{company}/configs/project.yaml"
        if yaml_path.exists():
            import yaml
            proj = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            custom_segs = proj.get("model", {}).get("custom", {}).get("revenue", {}).get("segments", {})
            for sk, sc in custom_segs.items():
                name_map = {"primary_al": "Primary Aluminium", "alumina": "Alumina",
                           "other": "Other", "nickel": "Nickel", "copper": "Copper", "pgm": "PGM"}
                if name_map.get(sk, sk.title()).lower() in seg_label.lower():
                    seg_cfg_yaml = sc
                    pf = sc.get("price_factors", [])
                    if pf:
                        factor_name = pf[0]
                    break

        # Compute OLS β from historical Δln(price) ~ Δln(factor)
        beta_price = 1.0  # default elasticity
        if factor_name:
            macro_data = data.get("macro", [])
            factor_series = {}
            for item in macro_data:
                if item["factor"] == factor_name:
                    factor_series[item["year"]] = item["value"]

            if len(factor_series) >= 3 and len(price_data) >= 3:
                common_yrs = sorted(set(price_data.keys()) & set(factor_series.keys()))
                if len(common_yrs) >= 4:
                    import math
                    dy, dx = [], []
                    for i in range(1, len(common_yrs)):
                        y0, y1 = common_yrs[i-1], common_yrs[i]
                        p0, p1 = price_data.get(y0, 0), price_data.get(y1, 0)
                        f0, f1 = factor_series.get(y0, 0), factor_series.get(y1, 0)
                        if p0 > 0 and p1 > 0 and f0 > 0 and f1 > 0:
                            dy.append(math.log(p1 / p0))
                            dx.append(math.log(f1 / f0))
                    if dx:
                        n = len(dx)
                        mx = sum(dx) / n
                        my = sum(dy) / n
                        cov = sum((dx[i]-mx)*(dy[i]-my) for i in range(n))
                        var = sum((dx[i]-mx)**2 for i in range(n))
                        if abs(var) > 1e-12:
                            beta_price = cov / var
                            alpha_price = my - beta_price * mx
                            print(f"    {seg_label} OLS: β={beta_price:.3f} α={alpha_price:.4f} "
                                  f"({len(dx)} obs, factor={factor_name})")

        # Forecast: DON'T override — build_model creates formulas in 11_Segments
        # Write OLS β to CP.rev_elasticity (for Revenue method 2)
        if factor_name and beta_price != 1.0:
            cp_elast_row = REG.get("CP.rev_elasticity")
            if cp_elast_row:
                ws_cp = wb["Control_Panel"]
                ws_cp.cell(cp_elast_row, 3, round(beta_price, 3)).font = F_INPUT
                ws_cp.cell(cp_elast_row, 3).number_format = FMT_RATIO
            print(f"    {seg_label} OLS β={beta_price:.3f} → CP.rev_elasticity")


def fill_debt_schedule(wb, data: dict, company: str):
    """Fill _Debt_Schedule with per-instrument formulas.

    For each instrument:
    - Map to canonical kind (BOND_BULLET, BOND_FLOAT, TERM_AMORT, RC)
    - Per year: Open → Mandatory (if maturity) → Refi → Interest → Close
    - Floating rate: KeyRate + spread from 01_Macro
    """
    if "_Debt_Schedule" not in wb.sheetnames:
        return

    ws = wb["_Debt_Schedule"]
    src = SOURCES[company]
    fc_years = src["fc_years"]
    debt_instruments = data.get("debt", [])

    if not debt_instruments:
        print("    Debt schedule: no instruments")
        return

    # Load KeyRate forecast from YAML for floating rate repricing
    import yaml as _yaml
    yaml_path = SV2_ROOT / f"companies/{company}/configs/project.yaml"
    kr_forecast = {}
    target_nd_ebitda = 3.5
    if yaml_path.exists():
        _proj = _yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        kr_forecast = _proj.get("model", {}).get("custom", {}).get("debt", {}).get("cbr_key_rate_forecast", {})
        target_nd_ebitda = _proj.get("model", {}).get("custom", {}).get("debt", {}).get("target_net_debt_ebitda",
                           _proj.get("model", {}).get("standard", {}).get("debt", {}).get("target_net_debt_ebitda", 3.5))

    # Write KeyRate forecast to Raw_IFRS (RI.kr_row)
    # _Debt_Schedule reads from Raw_IFRS via formulas (build_model sets refs)
    ri_kr_row = REG.get("RI.kr_row")
    ws_ri = wb["Raw_IFRS"]
    if ri_kr_row:
        for yr_idx, yr in enumerate(fc_years):
            kr_val = kr_forecast.get(yr, kr_forecast.get(int(yr), 0.12))
            ws_ri.cell(ri_kr_row, 7 + yr_idx, kr_val).font = F_INPUT
            ws_ri.cell(ri_kr_row, 7 + yr_idx).number_format = FMT_PCT

    yr_start = 8
    cols_per = 5

    # Sort by balance descending
    instruments = sorted(debt_instruments,
                         key=lambda x: -abs(float(x.get("opening_balance", 0) or 0)))
    max_inst = min(20, len(instruments))

    # Canonical kind mapping
    def infer_kind(name, db_type, rate_type):
        rt = (rate_type or "").lower()
        dt = (db_type or "").lower()
        if "revolv" in dt or "rc" in dt:
            return "RC"
        if "float" in rt or "keyrate" in name.lower():
            return "BOND_FLOAT"
        if "amort" in dt or "term" in dt:
            return "TERM_AMORT"
        return "BOND_BULLET"

    # KeyRate forecast row in 01_Macro (for floating rate)
    # Scenario base key rate is in row 8 of 01_Macro
    macro_kr_row = 8  # LME Aluminium... actually we need KeyRate
    # For now: use avg_rate from DT for floating (simplified)

    yr_start = 8  # col H
    cols_per = 5  # Open, Mandatory, Refi, Interest, Close

    other_balance = 0
    other_interest = 0
    top_n_balance = 0  # track top-N for reconciliation

    for i, inst in enumerate(instruments):
        if i >= max_inst:
            bal = abs(float(inst.get("opening_balance", 0) or 0)) / 1e6
            rate = float(inst.get("interest_rate", 0) or 0)
            other_balance += bal
            other_interest += bal * rate
            continue

        # Track rounded top-N balance for reconciliation with BS
        top_n_balance += round(abs(float(inst.get("opening_balance", 0) or 0)) / 1e6, 1)

        r = 5 + i
        name = str(inst.get("instrument_name", f"Inst_{i+1}"))[:35]
        db_type = str(inst.get("db_type", ""))
        ccy = str(inst.get("currency", "USD"))
        bal_mln = abs(float(inst.get("opening_balance", 0) or 0)) / 1e6
        rate = float(inst.get("interest_rate", 0) or 0)
        rate_type = str(inst.get("rate_type", "fixed"))
        maturity = str(inst.get("maturity_date", ""))
        kind = infer_kind(name, db_type, rate_type)

        # Parse maturity year
        mat_year = None
        for y in range(2025, 2035):
            if str(y) in maturity:
                mat_year = y
                break

        # Write instrument info to Raw_IFRS (single source)
        # _Debt_Schedule reads from Raw_IFRS via formulas
        ws_ri = wb["Raw_IFRS"]
        ri_start = REG.get("RI.debt_start_row", 70)
        ri_r = ri_start + i
        ws_ri.cell(ri_r, 1, name).font = F_INPUT           # A: Name
        ws_ri.cell(ri_r, 2, kind).font = F_INPUT            # B: Kind
        ws_ri.cell(ri_r, 3, ccy).font = F_INPUT             # C: CCY
        ws_ri.cell(ri_r, 4, round(bal_mln, 1)).font = F_INPUT  # D: Balance
        ws_ri.cell(ri_r, 4).number_format = FMT_MLN
        ws_ri.cell(ri_r, 5, rate).font = F_INPUT            # E: Rate
        ws_ri.cell(ri_r, 5).number_format = FMT_PCT2
        ws_ri.cell(ri_r, 6, maturity).font = F_INPUT         # F: Maturity

        # Per-year schedule formulas already in build_model (refs to Raw_IFRS)
        # No fill_data override needed

    # Other bucket: write to Raw_IFRS "Other" row
    bs_d = data.get("bs", {})
    last_yr = SOURCES[company]["hist_years"][-1]
    st_bs = abs(bs_d.get("short_term_debt", {}).get(last_yr, 0))
    lt_bs = abs(bs_d.get("long_term_debt", {}).get(last_yr, 0))
    bs_total_mln = st_bs + lt_bs
    reconciled_other = bs_total_mln - top_n_balance
    if reconciled_other < 0:
        reconciled_other = other_balance
    ws_ri = wb["Raw_IFRS"]
    ri_other = REG.get("RI.debt_other_row")
    if ri_other and (other_balance > 0 or reconciled_other > 0):
        ws_ri.cell(ri_other, 1, f"Other ({len(instruments) - max_inst} instruments)").font = F_INPUT
        ws_ri.cell(ri_other, 4, round(reconciled_other, 1)).font = F_INPUT
        ws_ri.cell(ri_other, 4).number_format = FMT_MLN
        avg_other_rate = other_interest / other_balance if other_balance > 0 else 0.08
        ws_ri.cell(ri_other, 5, round(avg_other_rate, 4)).font = F_INPUT
        ws_ri.cell(ri_other, 5).number_format = FMT_PCT2

    print(f"    Debt schedule: {max_inst} instruments + Other, per-year formulas")

    # Now link 17_Debt totals FROM _Debt_Schedule
    ws_dt = wb["17_Debt"]
    # Find total row by searching for "ИТОГО" in column B
    total_r = 27  # default from build (5 + 20 + 2)
    for r in range(5, 30):
        if ws.cell(r, 2).value == "ИТОГО":
            total_r = r
            break

    NAME_PL = "21_PL"
    NAME_PPE = "15_PPE"

    # ── ST/LT split from instrument maturities ──
    # Add ST/LT computation rows after total in _Debt_Schedule
    r_st_label = total_r + 2
    r_lt_label = total_r + 3
    ws.cell(r_st_label, 2, "ST (maturity ≤ t+1)").font = F_LABEL_B
    ws.cell(r_lt_label, 2, "LT (maturity > t+1)").font = F_LABEL_B

    for yr_idx, yr in enumerate(fc_years):
        bc = yr_start + yr_idx * cols_per
        close_col = get_column_letter(bc + 4)  # Close column

        # ST: SUMPRODUCT of Close × (maturity_year ≤ yr+1)
        # For each instrument: IF maturity_year ≤ yr+1 → Close, else 0
        st_parts = []
        lt_parts = []
        for i_row in range(5, 5 + max_inst + (1 if other_balance > 0 else 0)):
            mat_cell = f"$G${i_row}"  # maturity column
            close_cell = f"{close_col}{i_row}"
            # ST: instrument matures within 1 year of THIS forecast year
            # Check if maturity text contains year ≤ yr+1
            st_conditions = []
            for check_yr in range(yr, yr + 2):  # this year or next
                st_conditions.append(f'ISNUMBER(SEARCH("{check_yr}",{mat_cell}))')
            st_formula = f"IF(OR({','.join(st_conditions)}),{close_cell},0)"
            st_parts.append(st_formula)
            lt_parts.append(f"{close_cell}-{st_formula}")

        # Simplified: ST = SUM of instruments with maturity matching yr or yr+1
        # Use simpler approach: count instruments per maturity year
        formula_cell(ws, r_st_label, bc + 4,
                     f"=SUMPRODUCT(({close_col}5:{close_col}{5+max_inst})*"
                     f"((ISNUMBER(SEARCH(\"{yr}\",G5:G{5+max_inst})))"
                     f"+(ISNUMBER(SEARCH(\"{yr+1}\",G5:G{5+max_inst})))))",
                     FMT_MLN)
        formula_cell(ws, r_lt_label, bc + 4,
                     f"={close_col}{total_r}-{close_col}{r_st_label}",
                     FMT_MLN)

    # ── Synthetic "New Term" rows per forecast year ──
    # Rate = base_rate + spread_base + spread_step × MAX(0, ND/EBITDA - target)
    r_synth_start = r_lt_label + 2
    ws.cell(r_synth_start - 1, 2, "СИНТЕТИЧЕСКИЕ ТРАНШИ").font = F_LABEL_B
    cp_spread_base = REG.get("CP.spread_base")
    cp_spread_step = REG.get("CP.spread_step")
    cp_target_lev = REG.get("CP.target_leverage")
    cp_term_tenor = REG.get("CP.term_tenor")

    for yr_idx, yr in enumerate(fc_years):
        r_synth = r_synth_start + yr_idx
        bc = yr_start + yr_idx * cols_per
        c_dt = COL_START + N_HIST_DISPLAY + yr_idx
        cl_dt = get_column_letter(c_dt)

        ws.cell(r_synth, 2, f"New Term {yr}").font = F_LABEL
        # Maturity = yr + tenor
        tenor = 5
        if cp_term_tenor:
            tenor_ref = f"'Control_Panel'!$C${cp_term_tenor}"
        else:
            tenor_ref = str(tenor)
        # Maturity = yr + capex_tenor (longer for project capex)
        cp_capex_tenor = REG.get("CP.term_tenor_capex")
        capex_tenor = 7
        if cp_capex_tenor:
            # Read from CP for the formula
            capex_tenor = 7  # default, CP overrides at runtime
        ws.cell(r_synth, 7, f"{yr + capex_tenor}").font = F_LABEL

        # Rate = leverage-dependent: avg_rate + spread_base + spread_step × MAX(0, ND/EBITDA - target)
        if cp_spread_base and cp_spread_step and cp_target_lev:
            rate_formula = (f"='17_Debt'!{cl_dt}${REG['DT.avg_rate']}"
                           f"+'Control_Panel'!$C${cp_spread_base}"
                           f"+'Control_Panel'!$C${cp_spread_step}"
                           f"*MAX(0,IFERROR('17_Debt'!{cl_dt}${REG['DT.nd_ebitda']},0)"
                           f"-'Control_Panel'!$C${cp_target_lev})")
            ws.cell(r_synth, 6).value = rate_formula
            ws.cell(r_synth, 6).font = F_FORMULA
            ws.cell(r_synth, 6).number_format = FMT_PCT2
        else:
            ws.cell(r_synth, 6, 0.12).font = F_INPUT
            ws.cell(r_synth, 6).number_format = FMT_PCT2

        # Opening = DT.new_term from 17_Debt for THIS year (0 for prior years)
        for prior_idx in range(yr_idx):
            prior_bc = yr_start + prior_idx * cols_per
            ws.cell(r_synth, prior_bc, 0).font = F_INPUT  # 0 before issuance
            ws.cell(r_synth, prior_bc + 4, 0).font = F_INPUT  # close = 0

        # Issuance year: Open = DT.new_term
        formula_cell(ws, r_synth, bc,
                     f"='17_Debt'!{cl_dt}${REG['DT.new_term']}", FMT_MLN)
        formula_cell(ws, r_synth, bc + 1, "=0", FMT_MLN)  # no mandatory in year of issuance
        formula_cell(ws, r_synth, bc + 2, "=0", FMT_MLN)  # no refi
        cl_open_s = get_column_letter(bc)
        cl_close_s = get_column_letter(bc + 4)
        # Interest = 0 in year of issuance (breaks circular: new_term → interest → NI → CF → need)
        # Interest starts NEXT year from opening balance (= closing of issuance year)
        formula_cell(ws, r_synth, bc + 3, "=0", FMT_MLN)
        formula_cell(ws, r_synth, bc + 4,
                     f"={cl_open_s}{r_synth}", FMT_MLN)  # bullet: close = open

        # Subsequent years: carry forward
        for fut_idx in range(yr_idx + 1, len(fc_years)):
            fut_bc = yr_start + fut_idx * cols_per
            prev_close_col = get_column_letter(fut_bc - 1)
            cl_open_f = get_column_letter(fut_bc)
            cl_close_f = get_column_letter(fut_bc + 4)
            formula_cell(ws, r_synth, fut_bc, f"={prev_close_col}{r_synth}", FMT_MLN)
            formula_cell(ws, r_synth, fut_bc + 1, "=0", FMT_MLN)  # no maturity within horizon
            formula_cell(ws, r_synth, fut_bc + 2, "=0", FMT_MLN)
            # Interest from opening only (no circular)
            formula_cell(ws, r_synth, fut_bc + 3,
                         f"={cl_open_f}{r_synth}*$F${r_synth}",
                         FMT_MLN)
            formula_cell(ws, r_synth, fut_bc + 4,
                         f"={cl_open_f}{r_synth}", FMT_MLN)

    # Update total row: SUM(instruments) + SUM(synthetics) — non-contiguous to skip ST/LT rows
    n_synth = len(fc_years)
    r_synth_end = r_synth_start + n_synth - 1
    # Instrument rows: 5 to total_r-1 (before ИТОГО)
    r_inst_end = total_r - 1
    for yr_idx in range(len(fc_years)):
        bc = yr_start + yr_idx * cols_per
        for j in range(cols_per):
            col = bc + j
            cl = get_column_letter(col)
            formula_cell(ws, total_r, col,
                         f"=SUM({cl}5:{cl}{r_inst_end})+SUM({cl}{r_synth_start}:{cl}{r_synth_end})",
                         FMT_MLN, bold=True)

    print(f"    Synthetic terms: {n_synth} rows ({r_synth_start}-{r_synth_end}), "
          f"leverage-dependent rate")

    for yr_idx, yr in enumerate(fc_years):
        c_dt = COL_START + N_HIST_DISPLAY + yr_idx
        bc = yr_start + yr_idx * cols_per
        cl = get_column_letter(c_dt)
        close_col = get_column_letter(bc + 4)

        # 17_Debt ← _Debt_Schedule totals (mandatory, refi, interest)
        mand_col = get_column_letter(bc + 1)
        refi_col = get_column_letter(bc + 2)
        int_col = get_column_letter(bc + 3)
        # Mandatory from schedule (includes synthetics via extended SUM)
        formula_cell(ws_dt, REG["DT.mandatory"], c_dt,
                     f"='_Debt_Schedule'!{mand_col}${total_r}", FMT_MLN)
        # Refi from schedule
        formula_cell(ws_dt, REG["DT.refi"], c_dt,
                     f"='_Debt_Schedule'!{refi_col}${total_r}", FMT_MLN)
        # Interest (term only)
        formula_cell(ws_dt, REG["DT.interest_term"], c_dt,
                     f"='_Debt_Schedule'!{int_col}${total_r}", FMT_MLN)

        # ST/LT: DON'T override — build_model computes from mandatory + RC + reclass
        # (SUMPRODUCT text search on static maturity was wrong — audit defect 3)

    # ── FX Revaluation from currency exposure ──
    # FX effect = Σ(instrument_close × (FX_old/FX_new - 1)) per currency
    # Simplified: FX_effect ≈ -balance × pct_change_in_rate
    # CNY instruments: -close × USDCNY_change; RUB: -close × USDRUB_change
    cp_fx_cny = REG.get("CP.fx_usdcny_chg")
    cp_fx_rub = REG.get("CP.fx_usdrub_chg")

    if cp_fx_cny or cp_fx_rub:
        r_fx_label = r_synth_end + 2
        ws.cell(r_fx_label - 1, 2, "ВАЛЮТНАЯ ПЕРЕОЦЕНКА").font = F_LABEL_B
        ws.cell(r_fx_label, 2, "FX Reval (CNY)").font = F_LABEL
        ws.cell(r_fx_label + 1, 2, "FX Reval (RUB)").font = F_LABEL
        ws.cell(r_fx_label + 2, 2, "FX Reval (ИТОГО)").font = F_LABEL_B

        for yr_idx, yr in enumerate(fc_years):
            bc = yr_start + yr_idx * cols_per
            close_col = get_column_letter(bc + 4)
            c_dt = COL_START + N_HIST_DISPLAY + yr_idx
            cl_dt = get_column_letter(c_dt)

            # Sum Close balances per currency using SUMPRODUCT + SEARCH
            # CNY: SUMPRODUCT(Close × (currency = "CNY"))
            cny_sum = (f"SUMPRODUCT(({close_col}5:{close_col}{r_inst_end})"
                       f"*(ISNUMBER(SEARCH(\"CNY\",$D$5:$D${r_inst_end}))))")
            rub_sum = (f"SUMPRODUCT(({close_col}5:{close_col}{r_inst_end})"
                       f"*(ISNUMBER(SEARCH(\"RUB\",$D$5:$D${r_inst_end}))))")

            # FX effect = -balance × pct_change (positive change = USD strengthens = gain on debt)
            # Sign: positive FX reval = gain (debt decreases), negative = loss
            cny_ref = f"'Control_Panel'!$C${cp_fx_cny}" if cp_fx_cny else "0"
            rub_ref = f"'Control_Panel'!$C${cp_fx_rub}" if cp_fx_rub else "0"

            formula_cell(ws, r_fx_label, bc + 4,
                         f"=-({cny_sum})*{cny_ref}", FMT_MLN)
            formula_cell(ws, r_fx_label + 1, bc + 4,
                         f"=-({rub_sum})*{rub_ref}", FMT_MLN)
            formula_cell(ws, r_fx_label + 2, bc + 4,
                         f"={close_col}{r_fx_label}+{close_col}{r_fx_label+1}",
                         FMT_MLN, bold=True)

            # Link to 17_Debt FX reval
            fx_total_col = get_column_letter(bc + 4)
            formula_cell(ws_dt, REG["DT.fx_reval"], c_dt,
                         f"='_Debt_Schedule'!{fx_total_col}${r_fx_label+2}", FMT_MLN)

        print(f"    FX revaluation: CNY + RUB exposure, linked to CP FX assumptions")

    # Voluntary_term: already set by build_model with proper waterfall
    ws_cp = wb["Control_Panel"]
    cp_target_row = REG.get("CP.target_leverage")
    if cp_target_row is None:
        for r in range(50, 80):
            val = ws_cp.cell(r, 1).value
            if val and "target" in str(val).lower() and "nd" in str(val).lower():
                cp_target_row = r
                break
    if cp_target_row is None:
        cp_target_row = 60  # safe fallback
        ws_cp.cell(cp_target_row, 1, "Target ND/EBITDA").font = F_LABEL
        ws_cp.cell(cp_target_row, 3, target_nd_ebitda).font = F_INPUT
        ws_cp.cell(cp_target_row, 3).number_format = FMT_MULT

    # Voluntary_term: formula already set by build_model with proper S&U integration
    # No override needed — build_model references CP rows correctly via REG

    # ── Historical Calibration (Section 4 of TASK_debt_module.md) ──
    # Write informational metrics to DT.cal_* rows in last hist column
    last_yr = src["hist_years"][-1]
    hc = COL_START + N_HIST_DISPLAY - 1
    bs_d = data.get("bs", {})
    st_val = abs(bs_d.get("short_term_debt", {}).get(last_yr, 0))
    lt_val = abs(bs_d.get("long_term_debt", {}).get(last_yr, 0))
    total_debt = st_val + lt_val
    if total_debt > 0:
        # 1. ST share: build_model sets formula = ST/(ST+LT) from 02_Hist
        # 2. Maint share: build_model sets formula = DA/CapEx from 02_Hist
        ws_dt = wb["17_Debt"]
        st_share = st_val / total_debt
        da_last = abs(data.get("is", {}).get("total_da", {}).get(last_yr, 0))
        capex_last = abs(data.get("cf", {}).get("capex", {}).get(last_yr, 0))
        maint_share_hist = da_last / capex_last if capex_last > 0 else 0
        print(f"    Calibration: ST={st_share:.1%} maint={maint_share_hist:.1%} (formulas from build_model)")

        # 3. Spread to base = weighted avg rate - KeyRate (approx)
        # Read avg_rate from the workbook (already filled by fill_debt_hist)
        avg_rate_cell = ws_dt.cell(REG["DT.avg_rate"], hc).value
        avg_rate_val = float(avg_rate_cell) if isinstance(avg_rate_cell, (int, float)) else 0.08
        base_rate = 0.10  # approximate KeyRate level
        spread_hist = avg_rate_val - base_rate if avg_rate_val > base_rate else 0
        ws_dt.cell(REG["DT.cal_spread"], hc, round(spread_hist, 4)).font = F_INPUT
        ws_dt.cell(REG["DT.cal_spread"], hc).number_format = FMT_PCT2

        # 4. Average tenor (weighted by balance)
        if debt_instruments:
            w_tenor = w_bal_t = 0
            for inst in debt_instruments:
                b = abs(float(inst.get("opening_balance", 0) or 0))
                mat = str(inst.get("maturity_date", ""))
                for y in range(last_yr, last_yr + 20):
                    if str(y) in mat:
                        tenor = y - last_yr
                        w_tenor += b * tenor
                        w_bal_t += b
                        break
            if w_bal_t > 0:
                avg_tenor = w_tenor / w_bal_t
                ws_dt.cell(REG["DT.cal_tenor"], hc, round(avg_tenor, 1)).font = F_INPUT
                ws_dt.cell(REG["DT.cal_tenor"], hc).number_format = FMT_RATIO

        # 5. Debt-financed capex = (ΔDebt - refi) / CapEx — needs prev year, skip if unavailable
        # 6. ST flag: for forecast years, compare model ST% vs hist median
        for yr_idx, yr in enumerate(fc_years):
            c_dt = COL_START + N_HIST_DISPLAY + yr_idx
            cl_dt = get_column_letter(c_dt)
            # Model ST share vs historical — flag if deviation > 15 p.p.
            formula_cell(ws_dt, REG["DT.cal_st_flag"], c_dt,
                         f"=IF(ABS({cl_dt}{REG['DT.st']}/MAX(1,{cl_dt}{REG['DT.close']})"
                         f"-{get_column_letter(hc)}{REG['DT.cal_st_share']})>0.15,"
                         f"\"⚠ ST ±15pp\",\"OK\")",
                         "")

        maint_str = f"{maint_share_hist*100:.1f}%" if capex_last > 0 else "n/a"
        print(f"    Calibration: ST={st_share*100:.1f}%, maint={maint_str}, "
              f"spread={spread_hist*100:.2f}%")

    print(f"    17_Debt: mandatory + refi + interest + ST/LT + FX linked to _Debt_Schedule")
    print(f"    Floating rate: KeyRate from Raw_IFRS row {ri_kr_row} + spread per instrument")
    print(f"    Target ND/EBITDA: {target_nd_ebitda}x (CP row {cp_target_row})")


def fill_revenue_reconciliation(wb, data: dict, company: str):
    """Fill reconciliation row: Reported Revenue - Σ segments for history years."""
    ws = wb["10_Revenue"]
    src = SOURCES[company]
    hist_years = src["hist_years"][-N_HIST_DISPLAY:]
    is_d = data.get("is", {})

    r_recon = REG.get("RV.recon", 19)
    r_total = REG.get("RV.total_rev", 20)

    # Compute segment revenue from Python data (not Excel cells — can't eval formulas)
    segments_data = data.get("segments", [])
    seg_vp: Dict[str, Dict[str, Dict[int, float]]] = {}
    for item in segments_data:
        seg = item["segment"]
        met = item["metric"]
        seg_vp.setdefault(seg, {}).setdefault(met, {})[item["year"]] = item["value"]

    # Supplement from YAML
    yaml_path = SV2_ROOT / f"companies/{company}/configs/project.yaml"
    if yaml_path.exists():
        import yaml
        proj = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        custom_segs = proj.get("model", {}).get("custom", {}).get("revenue", {}).get("segments", {})
        name_map = {"primary_al": "Primary Aluminium", "alumina": "Alumina",
                     "other": "Other", "nickel": "Nickel", "copper": "Copper", "pgm": "PGM"}
        for sk, sc in custom_segs.items():
            dn = name_map.get(sk, sk.title())
            for yr, vol in sc.get("volume_history", {}).items():
                seg_vp.setdefault(dn, {}).setdefault("sales_kt", {})[int(yr)] = float(vol)
            for yr, p in sc.get("price_history", {}).items():
                pv = float(p)
                if pv > 100000:
                    pv = pv / 1000
                seg_vp.setdefault(dn, {}).setdefault("avg_price_usd_t", {})[int(yr)] = pv

    filled = 0
    for yr_idx, yr in enumerate(hist_years):
        col = COL_START + yr_idx
        reported_rev = abs(is_d.get("revenue", {}).get(yr, 0))
        # Compute segment sum from Python data (only MODEL segments, not all)
        seg_configs_local = {
            "rusal": [("Primary Aluminium", "seg1"), ("Alumina", "seg2")],
            "nornickel": [("Nickel", "seg1"), ("Copper", "seg2"), ("PGM", "seg3")],
        }
        model_segs = seg_configs_local.get(company, [])
        seg_sum = 0
        for seg_label_r, _ in model_segs:
            for seg_name, metrics in seg_vp.items():
                if seg_label_r.lower() in seg_name.lower():
                    vol_d = metrics.get("sales_kt", metrics.get("production_kt", {}))
                    price_d = metrics.get("avg_price_usd_t", {})
                    if yr in vol_d and yr in price_d:
                        seg_sum += vol_d[yr] * price_d[yr] / 1000
                    break

        if reported_rev > 0:
            recon = reported_rev - seg_sum
            ws.cell(r_recon, col, round(recon, 1)).font = F_INPUT
            ws.cell(r_recon, col).number_format = FMT_MLN
            filled += 1

    if filled > 0:
        print(f"    Revenue reconciliation: {filled} years, last gap = {recon:,.0f}M "
              f"({recon/reported_rev*100:.0f}% of revenue)")


def fill_debt_hist(wb, data: dict, company: str):
    """Fill 17_Debt with opening balances from BS history."""
    ws = wb["17_Debt"]
    src = SOURCES[company]
    hist_years = src["hist_years"]
    last_yr = hist_years[-1]
    fc_years = src["fc_years"]
    # History last column = 3 + len(hist_years[-3:]) - 1
    hc = 3 + len(hist_years[-3:]) - 1  # col index for last hist year

    bs = data.get("bs", {})
    st = bs.get("short_term_debt", {}).get(last_yr, 0)
    lt = bs.get("long_term_debt", {}).get(last_yr, 0)
    total_bs = abs(st) + abs(lt)
    cash = abs(bs.get("cash", {}).get(last_yr, 0))

    total = total_bs  # must match BS (ST+LT) for balance identity

    # Debt history: build_model sets formulas from 02_Hist (no literals needed)
    if total > 0:
        print(f"    Debt opening: ST={abs(st):.0f} LT={abs(lt):.0f} Total={total:.0f} (refs from build_model)")

    # Avg rate: compute weighted average from instrument table (not implied)
    is_data = data.get("is", {})
    debt_instruments = data.get("debt", [])
    if debt_instruments:
        w_bal = w_int = 0
        for inst in debt_instruments:
            b = abs(float(inst.get("opening_balance", 0) or 0))
            r = float(inst.get("interest_rate", 0) or 0)
            if b > 0 and r > 0:
                w_bal += b
                w_int += b * r
        if w_bal > 0:
            avg_rate = w_int / w_bal
        else:
            avg_rate = 0.08  # fallback
    else:
        # Fallback: implied from IS interest / debt
        interest = abs(is_data.get("interest_expense", {}).get(last_yr, 0))
        if interest == 0:
            interest = abs(is_data.get("finance_cost_net", {}).get(last_yr, 0))
        avg_rate = interest / total if total > 0 and interest > 0 else 0.08

    # Avg rate: build_model computes from 02_Hist (interest/debt)
    # Still fill forecast cols for avg_rate (fill_data overrides build_model default)
    fc_start_col = hc + 1
    for c in range(fc_start_col, fc_start_col + len(fc_years)):
        ws.cell(REG["DT.avg_rate"], c, round(avg_rate, 4)).font = F_INPUT
        ws.cell(REG["DT.avg_rate"], c).number_format = FMT_PCT
    print(f"    Avg rate (weighted from instruments): {avg_rate*100:.2f}%")
    # Interest history: build_model sets ref to 02_Hist

    # Fill mandatory repay from instrument maturities
    fc_years = src["fc_years"]
    debt_instruments = data.get("debt", [])
    if debt_instruments:
        from collections import defaultdict
        repay_by_year = defaultdict(float)
        for inst in debt_instruments:
            bal = abs(float(inst.get("opening_balance", 0) or 0))
            mat = str(inst.get("maturity_date", ""))
            for y in fc_years:
                if str(y) in mat:
                    repay_by_year[y] += bal
                    break

        fc_start_col = hc + 1
        for i, yr in enumerate(fc_years):
            c = fc_start_col + i
            repay = repay_by_year.get(yr, 0) / 1e6  # convert to mln
            if repay > 0:
                ws.cell(REG["DT.mandatory"], c, round(repay, 1)).font = F_INPUT
                ws.cell(REG["DT.mandatory"], c).number_format = FMT_MLN
                # Refi: linked to _Debt_Schedule total refi (which uses per-instrument refi_pct)
                # Will be overridden below when linking DT to _Debt_Schedule

        if repay_by_year:
            print(f"    Mandatory repay: " + ", ".join(f"{yr}={repay_by_year[yr]/1e6:,.0f}M" for yr in sorted(repay_by_year)))

    # ND, instrument summary: build_model sets formulas
    # ── INSTRUMENT SUMMARY → refs to Raw_IFRS ──
    ri_start = REG.get("RI.debt_start_row", 69)
    ri_count = REG.get("RI.debt_count", 20)
    r_start = 88
    section_header(ws, r_start - 1, "ИНСТРУМЕНТЫ (из Raw_IFRS)")
    ws.cell(r_start, 1, "Инструмент").font = F_YEAR
    ws.cell(r_start, 3, "Баланс").font = F_YEAR
    ws.cell(r_start, 4, "Ставка").font = F_YEAR
    ws.cell(r_start, 6, "Погашение").font = F_YEAR
    for i in range(min(15, ri_count + 1)):
        r = r_start + 1 + i
        ri_r = ri_start + i
        formula_cell(ws, r, 1, f"='Raw_IFRS'!A{ri_r}", "General")
        formula_cell(ws, r, 3, f"='Raw_IFRS'!D{ri_r}", FMT_MLN)
        formula_cell(ws, r, 4, f"='Raw_IFRS'!E{ri_r}", FMT_PCT2)
        formula_cell(ws, r, 6, f"='Raw_IFRS'!F{ri_r}", "General")

        # Total row
        r_total_inst = r_start + 1 + min(15, ri_count + 1)
        ws.cell(r_total_inst, 1, "ИТОГО").font = F_LABEL_B
        formula_cell(ws, r_total_inst, 3,
                     f"=SUM(C{r_start+1}:C{r_total_inst-1})", FMT_MLN, bold=True)

        print(f"    Instruments: refs to Raw_IFRS rows {ri_start}-{ri_start+ri_count}")

    # Tax DTA/DTL: build_model sets refs to 02_Hist (no fill needed)
    dta = abs(bs.get("dta", {}).get(last_yr, 0))
    dtl = abs(bs.get("dtl", {}).get(last_yr, 0))
    if dta or dtl:
        print(f"    Tax: DTA={dta:.0f} DTL={dtl:.0f} (refs from build_model)")

    # Fill lease opening from BS (Д10: load actual lease data)
    if "18_Lease" in wb.sheetnames:
        ws_l = wb["18_Lease"]
        # Only load if last year has separate disclosure (avoids double-count with PPE/Loans)
        rou = abs(bs.get("rou_asset", {}).get(last_yr, 0))
        lease_cl = abs(bs.get("lease_liab_current", {}).get(last_yr, 0))
        lease_ncl = abs(bs.get("lease_liab_noncurrent", {}).get(last_yr, 0))
        if rou == 0 and lease_cl == 0 and lease_ncl == 0:
            print(f"    Lease: not separately disclosed in {last_yr} BS → skipped (in PPE/Loans)")
            rou = 0
            lease_cl = 0
            lease_ncl = 0
        lease_total = lease_cl + lease_ncl
        if rou > 0 or lease_total > 0:
            ws_l.cell(REG["LS.rou_open"], hc, round(rou, 1)).font = F_INPUT
            ws_l.cell(REG["LS.rou_close"], hc, round(rou, 1)).font = F_INPUT
            ws_l.cell(REG["LS.liab_open"], hc, round(lease_total, 1)).font = F_INPUT
            ws_l.cell(REG["LS.liab_close"], hc, round(lease_total, 1)).font = F_INPUT
            # ROU dep ≈ ROU / 5 years (typical lease term)
            rou_dep = round(rou / 5, 1)
            ws_l.cell(REG["LS.rou_dep"], hc, rou_dep).font = F_INPUT
            ws_l.cell(REG["LS.rou_dep"], hc).number_format = FMT_MLN
            # Lease payment ≈ lease_total / 4 (typical)
            liab_pay = round(lease_total / 4, 1)
            ws_l.cell(REG["LS.liab_pay"], hc, liab_pay).font = F_INPUT
            ws_l.cell(REG["LS.liab_pay"], hc).number_format = FMT_MLN
            # Forecast: dep and pay carry forward
            for fc_i in range(len(src["fc_years"])):
                fc_c = hc + 1 + fc_i
                ws_l.cell(REG["LS.rou_dep"], fc_c, rou_dep).font = F_INPUT
                ws_l.cell(REG["LS.liab_pay"], fc_c, liab_pay).font = F_INPUT
            # BS history: ROU/lease NOT set separately (already in PPE/Loans per IFRS)
            # Forecast: BS.rou ← LS.rou_close, BS.lease ← LS.liab
            # History totals (TA/TL) from МСФО already include them
            # Setting them separately would double-count
            ws_bs = wb["20_BS"]
            print(f"    Lease (Д10): ROU={rou:.0f} Liab={lease_total:.0f} (CL={lease_cl:.0f} NCL={lease_ncl:.0f})")
            print(f"    Lease forecast: dep={rou_dep:.0f}/yr, pay={liab_pay:.0f}/yr")

    # Fill lease for ALL history years — ONLY if last year has separate disclosure
    # Rusal 2025: ROU/lease in PPE/Loans (not separate) → don't load → avoids double-count
    if "18_Lease" in wb.sheetnames:
        ws_l = wb["18_Lease"]
        rou_last = abs(bs.get("rou_asset", {}).get(last_yr, 0))
        lcl_last = abs(bs.get("lease_liab_current", {}).get(last_yr, 0))
        lncl_last = abs(bs.get("lease_liab_noncurrent", {}).get(last_yr, 0))
        # Only fill if last year has separate disclosure
        if rou_last > 0 or lcl_last > 0 or lncl_last > 0:
            for yr_idx, yr in enumerate(hist_years[-N_HIST_DISPLAY:]):
                col_l = COL_START + yr_idx
                rou_yr = abs(bs.get("rou_asset", {}).get(yr, 0))
                lcl_yr = abs(bs.get("lease_liab_current", {}).get(yr, 0))
                lncl_yr = abs(bs.get("lease_liab_noncurrent", {}).get(yr, 0))
                ltot_yr = lcl_yr + lncl_yr
                if rou_yr > 0:
                    ws_l.cell(REG["LS.rou_open"], col_l, round(rou_yr, 1)).font = F_INPUT
                    ws_l.cell(REG["LS.rou_close"], col_l, round(rou_yr, 1)).font = F_INPUT
                if ltot_yr > 0:
                    ws_l.cell(REG["LS.liab_open"], col_l, round(ltot_yr, 1)).font = F_INPUT
                    ws_l.cell(REG["LS.liab_close"], col_l, round(ltot_yr, 1)).font = F_INPUT

    # Fill 14_OtherIS — interest income, associates, impairment (Д10)
    if "14_OtherIS" in wb.sheetnames:
        ws_oi = wb["14_OtherIS"]
        is_d = data.get("is", {})
        oi_map = {
            "interest_income": "interest_income",
            "earnings_from_investees": "associates",
            "asset_impairment": "impairment",
            "other_operating_expenses": "other_opex",
        }
        oi_filled = 0
        for src_key, oi_key in oi_map.items():
            vals = is_d.get(src_key, {})
            r_oi = REG.get(f"OI.{oi_key}")
            if not r_oi:
                continue
            for yr in hist_years[-N_HIST_DISPLAY:]:
                col = COL_START + hist_years[-N_HIST_DISPLAY:].index(yr)
                val = vals.get(yr)
                if val is not None:
                    ws_oi.cell(r_oi, col, round(val, 1)).font = F_INPUT
                    ws_oi.cell(r_oi, col).number_format = FMT_MLN
                    oi_filled += 1
            # Forecast: carry forward last year for interest_income
            if oi_key == "interest_income":
                last_val = vals.get(last_yr, 0)
                if last_val:
                    for fc_i in range(len(src["fc_years"])):
                        fc_c = COL_START + N_HIST_DISPLAY + fc_i
                        ws_oi.cell(r_oi, fc_c, round(last_val, 1)).font = F_INPUT
                        ws_oi.cell(r_oi, fc_c).number_format = FMT_MLN
        if oi_filled:
            print(f"    14_OtherIS (Д10): {oi_filled} cells filled (int_income, associates, impairment)")

    # Fill PPE opening from BS
    if "15_PPE" in wb.sheetnames:
        ws_p = wb["15_PPE"]
        ppe_gross = abs(bs.get("ppe_gross", {}).get(last_yr, 0))
        accdep = abs(bs.get("ppe_accum_dep", {}).get(last_yr, 0))
        ppe_net = abs(bs.get("ppe_net", {}).get(last_yr, 0))
        if ppe_net > 0:
            ws_hi = wb["02_Hist"] if "02_Hist" in wb.sheetnames else None
            cl_h = get_column_letter(hc)
            gross_val = round(ppe_gross or ppe_net * 2, 1)
            dep_val = round(accdep or ppe_net, 1)
            net_val = round(ppe_net, 1)
            # Write to 02_Hist and create refs
            if ws_hi:
                ws_hi.cell(REG["HI.ppe_gross"], hc, gross_val).font = F_INPUT
                ws_hi.cell(REG["HI.accdep"], hc, dep_val).font = F_INPUT
                ws_hi.cell(REG["HI.ppe_net"], hc, net_val).font = F_INPUT
                ws_p.cell(REG["PP.gross_open"], hc).value = f"='02_Hist'!{cl_h}${REG['HI.ppe_gross']}"
                ws_p.cell(REG["PP.gross_open"], hc).font = F_REF
                ws_p.cell(REG["PP.gross_close"], hc).value = f"='02_Hist'!{cl_h}${REG['HI.ppe_gross']}"
                ws_p.cell(REG["PP.gross_close"], hc).font = F_REF
                ws_p.cell(REG["PP.dep_open"], hc).value = f"='02_Hist'!{cl_h}${REG['HI.accdep']}"
                ws_p.cell(REG["PP.dep_open"], hc).font = F_REF
                ws_p.cell(REG["PP.dep_close"], hc).value = f"='02_Hist'!{cl_h}${REG['HI.accdep']}"
                ws_p.cell(REG["PP.dep_close"], hc).font = F_REF
                ws_p.cell(REG["PP.net_open"], hc).value = f"='02_Hist'!{cl_h}${REG['HI.ppe_net']}"
                ws_p.cell(REG["PP.net_open"], hc).font = F_REF
                ws_p.cell(REG["PP.net_close"], hc).value = f"='02_Hist'!{cl_h}${REG['HI.ppe_net']}"
                ws_p.cell(REG["PP.net_close"], hc).font = F_REF
            else:
                ws_p.cell(REG["PP.gross_open"], hc, gross_val).font = F_INPUT
                ws_p.cell(REG["PP.gross_close"], hc, gross_val).font = F_INPUT
                ws_p.cell(REG["PP.dep_open"], hc, dep_val).font = F_INPUT
                ws_p.cell(REG["PP.dep_close"], hc, dep_val).font = F_INPUT
                ws_p.cell(REG["PP.net_open"], hc, net_val).font = F_INPUT
                ws_p.cell(REG["PP.net_close"], hc, net_val).font = F_INPUT
            # DA history → 02_Hist refs
            da_hist = is_data.get("total_da", is_data.get("dep_ppe", {}))
            for yr_offset, yr in enumerate(hist_years[-N_HIST_DISPLAY:]):
                da_val = da_hist.get(yr, 0)
                if da_val:
                    col_pp = COL_START + yr_offset
                    cl_pp = get_column_letter(col_pp)
                    abs_da = round(abs(da_val), 1)
                    if ws_hi:
                        ws_hi.cell(REG["HI.da"], col_pp, abs_da).font = F_INPUT
                        ws_p.cell(REG["PP.dep_charge"], col_pp).value = f"='02_Hist'!{cl_pp}${REG['HI.da']}"
                        ws_p.cell(REG["PP.dep_charge"], col_pp).font = F_REF
                    else:
                        ws_p.cell(REG["PP.dep_charge"], col_pp, abs_da).font = F_INPUT
                    ws_p.cell(REG["PP.dep_charge"], col_pp).number_format = FMT_MLN
            # Calibrate useful life = Gross / DA (write to CP)
            da_last = abs(is_data.get("total_da", is_data.get("dep_ppe", {})).get(last_yr, 0))
            if da_last > 0 and (ppe_gross or ppe_net * 2) > 0:
                cal_ul = round((ppe_gross or ppe_net * 2) / da_last, 0)
                cp_ul_row = REG.get("CP.useful_life")
                if cp_ul_row:
                    ws_cp = wb["Control_Panel"]
                    ws_cp.cell(cp_ul_row, 3, int(cal_ul)).font = F_INPUT
                    ws_cp.cell(cp_ul_row, 3).number_format = FMT_INT
                    print(f"    PPE: Gross={ppe_gross:.0f} Net={ppe_net:.0f} DA={da_last:.0f} → UL={cal_ul:.0f}yr (calibrated)")
                else:
                    print(f"    PPE: Gross={ppe_gross:.0f} Net={ppe_net:.0f} (CP.useful_life not found)")
            else:
                print(f"    PPE: Gross={ppe_gross:.0f} AccDep={accdep:.0f} Net={ppe_net:.0f}")

    # Fill Equity opening → 02_Hist ref
    if "24_Equity" in wb.sheetnames:
        ws_e = wb["24_Equity"]
        re = bs.get("retained_earnings", {}).get(last_yr, 0)
        if re != 0:
            hi_re = REG.get("HI.re")
            cl_h = get_column_letter(hc)
            ws_hi = wb["02_Hist"] if "02_Hist" in wb.sheetnames else None
            if hi_re and ws_hi:
                ws_hi.cell(hi_re, hc, round(re, 1)).font = F_INPUT
                ws_e.cell(REG["EQ.re_open"], hc).value = f"='02_Hist'!{cl_h}${hi_re}"
                ws_e.cell(REG["EQ.re_open"], hc).font = F_REF
                ws_e.cell(REG["EQ.re_close"], hc).value = f"='02_Hist'!{cl_h}${hi_re}"
                ws_e.cell(REG["EQ.re_close"], hc).font = F_REF
            else:
                ws_e.cell(REG["EQ.re_open"], hc, round(re, 1)).font = F_INPUT
                ws_e.cell(REG["EQ.re_close"], hc, round(re, 1)).font = F_INPUT
            print(f"    Retained earnings opening: {re:.0f} (→ 02_Hist)")

    # Fill BS last hist year (static items) → 02_Hist refs where possible
    if "20_BS" in wb.sheetnames:
        ws_bs = wb["20_BS"]
        ws_hi = wb["02_Hist"] if "02_Hist" in wb.sheetnames else None
        # Map: BS key → (source BS keys, HI row key)
        static_keys = {
            "other_ca": (["other_current_assets"], None),
            "goodwill": (["goodwill"], "goodwill"),
            "intang": (["intangibles"], "intang"),
            "other_nca": (["other_non_current_assets", "investments_lt"], "other_nca"),
            "other_cl": (["other_current_liabilities"], "other_cl"),
            "other_ncl": (["other_non_current_liabilities"], "other_ncl"),
            "sc": (["share_capital"], None),
            "apic": (["additional_paid_in_capital", "apic"], None),
            "aoci": (["aoci", "other_comprehensive_income"], None),
            "prov": (["provisions"], "prov"),
        }
        cl_h = get_column_letter(hc)
        for bs_key, (source_keys, hi_key) in static_keys.items():
            val = 0
            for sk in source_keys:
                v = bs.get(sk, {}).get(last_yr, 0)
                if v:
                    val = v
                    break
            if val:
                hi_row = REG.get(f"HI.{hi_key}") if hi_key else None
                if hi_row and ws_hi:
                    ws_hi.cell(hi_row, hc, round(val, 1)).font = F_INPUT
                    ws_bs.cell(REG[f"BS.{bs_key}"], hc).value = f"='02_Hist'!{cl_h}${hi_row}"
                    ws_bs.cell(REG[f"BS.{bs_key}"], hc).font = F_REF
                else:
                    ws_bs.cell(REG[f"BS.{bs_key}"], hc, round(val, 1)).font = F_INPUT


def fill_statement_history(wb, data: dict, company: str):
    """Fill 21_PL and 23_CF history columns (E=2025) for forecast continuity."""
    src = SOURCES[company]
    last_yr = src["hist_years"][-1]
    hc = COL_START + N_HIST_DISPLAY - 1  # col E = 5

    is_d = data.get("is", {})
    cf_d = data.get("cf", {})

    # Fill CF history (last year) → 02_Hist refs
    ws_cf = wb["23_CF"]
    ws_hi = wb["02_Hist"] if "02_Hist" in wb.sheetnames else None
    cf_map = {
        "cfo_total": ("cfo", "cfo"),
        "cfi_total": ("cfi", "cfi"),
        "cff_total": ("cff", "cff"),
        "capex": ("capex", "capex"),
        "net_change": ("net_change", "net_change"),
    }
    filled = 0
    cl_h = get_column_letter(hc)
    for src_key, (reg_suffix, hi_key) in cf_map.items():
        val = cf_d.get(src_key, {}).get(last_yr)
        if val is not None:
            r = REG.get(f"CF.{reg_suffix}")
            hi_row = REG.get(f"HI.{hi_key}")
            if r:
                if hi_row and ws_hi:
                    ws_hi.cell(hi_row, hc, round(val, 1)).font = F_INPUT
                    ws_cf.cell(r, hc).value = f"='02_Hist'!{cl_h}${hi_row}"
                    ws_cf.cell(r, hc).font = F_REF
                else:
                    ws_cf.cell(r, hc, round(val, 1)).font = F_INPUT
                ws_cf.cell(r, hc).number_format = FMT_MLN
                filled += 1

    # Cash opening/closing → 02_Hist refs
    bs_d = data.get("bs", {})
    cash_open = bs_d.get("cash", {}).get(last_yr - 1, 0)
    cash_close = bs_d.get("cash", {}).get(last_yr, 0)
    hi_cash = REG.get("HI.cash")
    if cash_close:
        if hi_cash and ws_hi:
            ws_hi.cell(hi_cash, hc, round(cash_close, 1)).font = F_INPUT
            ws_cf.cell(REG["CF.cash_close"], hc).value = f"='02_Hist'!{cl_h}${hi_cash}"
            ws_cf.cell(REG["CF.cash_close"], hc).font = F_REF
        else:
            ws_cf.cell(REG["CF.cash_close"], hc, round(cash_close, 1)).font = F_INPUT
        ws_cf.cell(REG["CF.cash_close"], hc).number_format = FMT_MLN
    if cash_open:
        prev_cl = get_column_letter(hc - 1)
        if hi_cash and ws_hi:
            ws_hi.cell(hi_cash, hc - 1, round(cash_open, 1)).font = F_INPUT
            ws_cf.cell(REG["CF.cash_open"], hc).value = f"='02_Hist'!{prev_cl}${hi_cash}"
            ws_cf.cell(REG["CF.cash_open"], hc).font = F_REF
        else:
            ws_cf.cell(REG["CF.cash_open"], hc, round(cash_open, 1)).font = F_INPUT

    # Fill PL history (last 3 years)
    ws_pl = wb["21_PL"]
    pl_map = {
        "revenue": "revenue", "cogs": "cogs", "gross_profit": "gp",
        "sga": "sga", "ebitda": "ebitda", "ebit": "ebit",
        "interest_expense": "interest", "other_financial": "other_fin",
        "ebt": "ebt", "tax_expense": "tax", "net_income": "ni",
        "total_da": "da",
        "other_operating_expenses": "other_opex", "asset_impairment": "impairment",
        "other_opex": "other_opex", "impairment": "impairment",
    }
    # PL ← 02_Hist reference mapping
    pl_to_hi = {
        "revenue": "revenue", "cogs": "cogs", "gp": "gp",
        "sga": "sga", "ebitda": "ebitda", "ebit": "ebit",
        "interest": "interest", "other_fin": "other_fin",
        "ebt": "ebt", "tax": "tax", "ni": "ni", "da": "da",
        "other_opex": "other_opex", "impairment": "impairment",
    }
    ws_hi = wb["02_Hist"] if "02_Hist" in wb.sheetnames else None
    hist_3 = src["hist_years"][-N_HIST_DISPLAY:]
    pl_refs = 0
    for yr in hist_3:
        col = COL_START + hist_3.index(yr)
        cl = get_column_letter(col)
        for src_key, reg_suffix in pl_map.items():
            val = is_d.get(src_key, {}).get(yr)
            if val is not None:
                r = REG.get(f"PL.{reg_suffix}")
                if r:
                    # Write to 02_Hist and create ref
                    hi_key = pl_to_hi.get(reg_suffix)
                    hi_row = REG.get(f"HI.{hi_key}") if hi_key else None
                    if hi_row and ws_hi:
                        ws_hi.cell(hi_row, col, round(val, 1)).font = F_INPUT
                        ws_hi.cell(hi_row, col).number_format = FMT_MLN
                        ws_pl.cell(r, col).value = f"='02_Hist'!{cl}${hi_row}"
                        ws_pl.cell(r, col).font = F_REF
                        ws_pl.cell(r, col).number_format = FMT_MLN
                        pl_refs += 1
                    else:
                        ws_pl.cell(r, col, round(val, 1)).font = F_INPUT
                        ws_pl.cell(r, col).number_format = FMT_MLN

    # Д1: Fill missing PL items as residuals so history satisfies its own formulas
    # other_opex = EBITDA - GP - SGA (makes Валовая + SGA + other = EBITDA)
    # other_opex and impairment as FORMULAS (computed from other PL items)
    # other_opex = EBITDA - GP - SGA (residual)
    # impairment = EBITDA - DA - EBIT (residual)
    r_oo = REG.get("PL.other_opex")
    r_imp = REG.get("PL.impairment")
    for yr in hist_3:
        col = COL_START + hist_3.index(yr)
        cl = get_column_letter(col)
        if r_oo:
            formula_cell(ws_pl, r_oo, col,
                         f"={cl}{REG['PL.ebitda']}-{cl}{REG['PL.gp']}-{cl}{REG['PL.sga']}",
                         FMT_MLN)
        if r_imp:
            formula_cell(ws_pl, r_imp, col,
                         f"={cl}{REG['PL.ebitda']}-ABS({cl}{REG['PL.da']})-{cl}{REG['PL.ebit']}",
                         FMT_MLN)

    print(f"    CF history: {filled} metrics for {last_yr}, cash={cash_close}")
    print(f"    PL history: {len(pl_map)} metrics × {len(hist_3)} years ({pl_refs} refs to 02_Hist)")
    print(f"    PL reconciliation: other_opex + impairment filled from residuals (Д1)")


def fill_bs_history(wb, data: dict, company: str):
    """Fill 20_BS column C (last hist year) from BS history data."""
    ws = wb["20_BS"]
    src = SOURCES[company]
    last_yr = src["hist_years"][-1]
    bs = data.get("bs", {})

    # Map BS metrics to 20_BS rows (comprehensive)
    bs_map = {
        "cash": "cash", "accounts_receivable": "ar", "inventory": "inv",
        "other_ca": "other_ca",
        "ppe_net": "ppe", "rou_asset": "rou", "goodwill": "goodwill",
        "intangibles": "intang", "dta": "dta", "other_nca": "other_nca",
        "accounts_payable": "ap", "short_term_debt": "st_debt",
        "taxes_payable": "tax_pay", "other_cl": "other_cl",
        "long_term_debt": "lt_debt", "lease_liab_current": "lease_cl",
        "lease_liab_noncurrent": "lease_ncl", "provisions": "prov",
        "dtl": "dtl", "other_ncl": "other_ncl",
        "total_assets": "ta", "total_liabilities": "tl",
        "total_equity": "te", "retained_earnings": "re",
        "share_capital": "sc", "apic": "apic", "aoci": "aoci",
        "nci": "aoci",  # NCI included in AOCI row for simplicity
        "investments_lt": "other_nca",  # included in other NCA
        "total_ca": "tca", "total_nca": "tnca",
        "total_cl": "tcl", "total_ncl": "tncl",
    }

    # Fill BS for ALL 3 history years (C=2023, D=2024, E=2025)
    # Accumulate values for keys that map to same BS row (e.g., investments_lt + other_nca → other_nca)
    hist_3 = src["hist_years"][-N_HIST_DISPLAY:]

    # BS → HI mapping for reference formulas (20_BS ← 02_Hist)
    bs_to_hi = {
        "cash": "cash", "ar": "ar", "inv": "inv", "other_ca": "other_ca",
        "ppe": "ppe_net", "rou": "rou", "goodwill": "goodwill", "intang": "intang",
        "dta": "dta", "other_nca": "other_nca",
        "ap": "ap", "st_debt": "st_debt", "tax_pay": "tax_pay", "other_cl": "other_cl",
        "lt_debt": "lt_debt", "lease_cl": "lease_cl", "lease_ncl": "lease_ncl",
        "prov": "prov", "dtl": "dtl", "other_ncl": "other_ncl",
        "sc": "sc", "apic": "apic", "re": "re", "aoci": "aoci",
        "equity": "te",
    }

    filled = 0
    for yr_idx, yr in enumerate(hist_3):
        col = COL_START + yr_idx
        cl = get_column_letter(col)
        # First: write values to 02_Hist (if not already there)
        ws_hi = wb["02_Hist"] if "02_Hist" in wb.sheetnames else None

        # Accumulate per-row
        row_accum: Dict[int, float] = {}
        for src_key, bs_key in bs_map.items():
            val = bs.get(src_key, {}).get(yr)
            if val is not None and isinstance(val, (int, float)):
                r = REG.get(f"BS.{bs_key}")
                if r:
                    row_accum[r] = row_accum.get(r, 0) + val

        # Skip total rows (build_model sets formulas for these)
        total_rows = {REG.get(f"BS.{k}") for k in
                      ["tca", "tnca", "ta", "tcl", "tncl", "tl", "te", "check"]}
        for r, val in row_accum.items():
            if r in total_rows:
                # Write to 02_Hist only (BS cell has formula from build_model)
                for bk, hk in bs_to_hi.items():
                    if REG.get(f"BS.{bk}") == r:
                        hi_row = REG.get(f"HI.{hk}")
                        if hi_row and ws_hi:
                            ws_hi.cell(hi_row, col, round(val, 1)).font = F_INPUT
                            ws_hi.cell(hi_row, col).number_format = FMT_MLN
                        break
                continue
            # Try to create reference to 02_Hist instead of literal
            # Find corresponding HI row
            bs_key_name = None
            for bk, hk in bs_to_hi.items():
                if REG.get(f"BS.{bk}") == r:
                    hi_row = REG.get(f"HI.{hk}")
                    if hi_row and ws_hi:
                        # Write value to 02_Hist
                        ws_hi.cell(hi_row, col, round(val, 1)).font = F_INPUT
                        ws_hi.cell(hi_row, col).number_format = FMT_MLN
                        # 20_BS references 02_Hist
                        ws.cell(r, col).value = f"='02_Hist'!{cl}${hi_row}"
                        ws.cell(r, col).font = F_REF
                        ws.cell(r, col).number_format = FMT_MLN
                        bs_key_name = bk
                        break
            if not bs_key_name:
                # Fallback: write literal directly
                ws.cell(r, col, round(val, 1)).font = F_INPUT
                ws.cell(r, col).number_format = FMT_MLN
            filled += 1

    # Also compute missing totals
    # Other CA = TCA - cash - ar - inv (if available)
    tca = bs.get("total_current_assets", {}).get(last_yr, 0)
    cash = abs(bs.get("cash", {}).get(last_yr, 0))
    ar = abs(bs.get("accounts_receivable", {}).get(last_yr, 0))
    inv = abs(bs.get("inventory", {}).get(last_yr, 0))
    if tca and (cash or ar or inv):
        other_ca = abs(tca) - cash - ar - inv
        if other_ca > 0:
            ws.cell(REG["BS.other_ca"], 3, round(other_ca, 1)).font = F_INPUT

    # Other CL
    tcl = bs.get("total_current_liabilities", {}).get(last_yr, 0)
    ap = abs(bs.get("accounts_payable", {}).get(last_yr, 0))
    st_d = abs(bs.get("short_term_debt", {}).get(last_yr, 0))
    if tcl and (ap or st_d):
        other_cl = abs(tcl) - ap - st_d
        if other_cl > 0:
            ws.cell(REG["BS.other_cl"], 3, round(other_cl, 1)).font = F_INPUT

    # Other NCL
    tncl = bs.get("total_non_current_liabilities", {}).get(last_yr, 0)
    lt_d = abs(bs.get("long_term_debt", {}).get(last_yr, 0))
    prov = abs(bs.get("provisions", {}).get(last_yr, 0))
    if tncl:
        other_ncl = abs(tncl) - lt_d - prov
        if other_ncl > 0:
            ws.cell(REG["BS.other_ncl"], 3, round(other_ncl, 1)).font = F_INPUT

    # Other NCA
    tnca = bs.get("total_non_current_assets", {}).get(last_yr, 0)
    ppe = abs(bs.get("ppe_net", {}).get(last_yr, 0))
    if tnca and ppe:
        gw = abs(bs.get("goodwill", {}).get(last_yr, 0))
        intang = abs(bs.get("intangibles", {}).get(last_yr, 0))
        other_nca = abs(tnca) - ppe - gw - intang
        if other_nca > 0 and REG.get("BS.other_nca"):
            ws.cell(REG["BS.other_nca"], 3, round(other_nca, 1)).font = F_INPUT

    # Compute Other_CL and Other_NCL from totals (not source line items)
    # Other_CL = TCL - (AP + STD + Lease_CL + Tax_Pay) — absorbs unmapped CL items
    # Other_NCL = TNCL - (LTD + Lease_NCL + Provisions + DTL) — absorbs unmapped NCL items
    # Other_CA = TCA - (Cash + AR + INV) — absorbs unmapped CA items
    # Other items: compute as plug, write to 02_Hist, 20_BS refs 02_Hist
    ws_hi = wb["02_Hist"] if "02_Hist" in wb.sheetnames else None
    for yr_idx, yr in enumerate(hist_3):
        col = COL_START + yr_idx
        cl = get_column_letter(col)

        plugs = [
            ("other_ca", ["cash", "accounts_receivable", "inventory"],
             "total_ca", "total_current_assets"),
            ("other_nca", ["ppe_net", "intangibles", "dta", "rou_asset", "goodwill"],
             "total_nca", "total_non_current_assets"),
            ("other_cl", ["accounts_payable", "short_term_debt", "lease_liab_current", "taxes_payable"],
             "total_cl", "total_current_liabilities"),
            ("other_ncl", ["long_term_debt", "dtl", "lease_liab_noncurrent", "provisions"],
             "total_ncl", "total_non_current_liabilities"),
        ]
        for other_key, known_keys, total_key, alt_total_key in plugs:
            total_v = abs((bs.get(total_key) or bs.get(alt_total_key) or {}).get(yr, 0))
            if total_v > 0:
                known = sum(abs(bs.get(k, {}).get(yr, 0)) for k in known_keys)
                plug_val = total_v - known
                # Write to 02_Hist
                hi_row = REG.get(f"HI.{other_key}")
                if hi_row and ws_hi:
                    ws_hi.cell(hi_row, col, round(plug_val, 1)).font = F_INPUT
                    ws_hi.cell(hi_row, col).number_format = FMT_MLN
                # 20_BS: ref to 02_Hist
                bs_row = REG.get(f"BS.{other_key}")
                if bs_row and hi_row:
                    ws.cell(bs_row, col).value = f"='02_Hist'!{cl}${hi_row}"
                    ws.cell(bs_row, col).font = F_REF
                    ws.cell(bs_row, col).number_format = FMT_MLN

    print(f"    BS history: {filled} metrics filled, Other as plugs → 02_Hist refs")


def fill_wc_days(wb, data: dict, company: str):
    """Compute DSO/DIO/DPO from historical AR/INV/AP/Rev/COGS + fill WC balances."""
    ws = wb["16_WC"]
    src = SOURCES[company]
    hist_years = src["hist_years"][-N_HIST_DISPLAY:]

    is_d = data.get("is", {})
    bs_d = data.get("bs", {})

    rev_hist = is_d.get("revenue", {})
    cogs_hist = is_d.get("cogs", {})
    ar_hist = bs_d.get("accounts_receivable", {})
    inv_hist = bs_d.get("inventory", {})
    ap_hist = bs_d.get("accounts_payable", {})

    # WC days history: build_model sets formulas (AR/Rev×365 from 02_Hist)
    # Compute values in Python for CP calibration (don't write to cells)
    computed_days = {"dso": [], "dio": [], "dpo": []}
    for year in hist_years:
        rev = abs(rev_hist.get(year, 0))
        cogs = abs(cogs_hist.get(year, 0))
        ar = abs(ar_hist.get(year, 0))
        inv_ = abs(inv_hist.get(year, 0))
        ap = abs(ap_hist.get(year, 0))
        if rev > 0:
            computed_days["dso"].append(ar / rev * 365)
        if cogs > 0:
            computed_days["dio"].append(inv_ / cogs * 365)
            computed_days["dpo"].append(ap / cogs * 365)

    # Forecast: WC days from Control_Panel (build_model sets formula =CP.wc_dso etc.)
    # Calibrate CP values from EWA of history (03_Assump rows 13-15)
    fc_years = src["fc_years"]
    ws_cp = wb["Control_Panel"]
    assump_rows = {"dso": 13, "dio": 14, "dpo": 15}
    cp_keys = {"dso": REG.get("CP.wc_dso"), "dio": REG.get("CP.wc_dio"),
               "dpo": REG.get("CP.wc_dpo")}
    # Compute EWA average from Python data for CP calibration
    for metric_key, assump_row in assump_rows.items():
        vals = computed_days.get(metric_key, [])
        if vals:
            ewa_avg = sum(vals) / len(vals)  # simple average
            cp_row = cp_keys.get(metric_key)
            if cp_row:
                ws_cp.cell(cp_row, 3, round(ewa_avg, 0)).font = F_INPUT
                ws_cp.cell(cp_row, 3).number_format = FMT_DAYS
                print(f"    CP.wc_{metric_key} = {ewa_avg:.0f} (EWA from {len(vals)} years)")
    # Note: build_model already set forecast WC days = CP ref, no override needed

    # Fill WC balances (AR, INV, AP) for history years
    bs_d = data.get("bs", {})
    for yr_idx, year in enumerate(hist_years):
        col = COL_START + yr_idx
        ar_v = abs(bs_d.get("accounts_receivable", {}).get(year, 0))
        inv_v = abs(bs_d.get("inventory", {}).get(year, 0))
        ap_v = abs(bs_d.get("accounts_payable", {}).get(year, 0))
        # WC balances → 02_Hist refs where available
        ws_hi_wc = wb["02_Hist"] if "02_Hist" in wb.sheetnames else None
        cl_wc = get_column_letter(col)
        wc_hi_map = {"ar": "ar", "inv": "inv"}
        if ar_v:
            hi_r = REG.get("HI.ar")
            if hi_r and ws_hi_wc:
                ws_hi_wc.cell(hi_r, col, round(ar_v, 1)).font = F_INPUT
                ws.cell(REG["WC.ar"], col).value = f"='02_Hist'!{cl_wc}${hi_r}"
                ws.cell(REG["WC.ar"], col).font = F_REF
            else:
                ws.cell(REG["WC.ar"], col, round(ar_v, 1)).font = F_INPUT
            ws.cell(REG["WC.ar"], col).number_format = FMT_MLN
        if inv_v:
            hi_r = REG.get("HI.inv")
            if hi_r and ws_hi_wc:
                ws_hi_wc.cell(hi_r, col, round(inv_v, 1)).font = F_INPUT
                ws.cell(REG["WC.inv"], col).value = f"='02_Hist'!{cl_wc}${hi_r}"
                ws.cell(REG["WC.inv"], col).font = F_REF
            else:
                ws.cell(REG["WC.inv"], col, round(inv_v, 1)).font = F_INPUT
            ws.cell(REG["WC.inv"], col).number_format = FMT_MLN
        if ap_v:
            hi_r = REG.get("HI.ap")
            if hi_r and ws_hi_wc:
                ws_hi_wc.cell(hi_r, col, round(ap_v, 1)).font = F_INPUT
                ws.cell(REG["WC.ap"], col).value = f"=-ABS('02_Hist'!{cl_wc}${hi_r})"
                ws.cell(REG["WC.ap"], col).font = F_REF
            else:
                ws.cell(REG["WC.ap"], col, round(-ap_v, 1)).font = F_INPUT
            ws.cell(REG["WC.ap"], col).number_format = FMT_MLN

    print(f"    WC days: {len(computed_days.get('dso',[]))} historical years computed, forecast carry-forwarded")
    print(f"    WC balances: AR/INV/AP filled for {len(hist_years)} hist years")


def fill_cogs_sga_from_history(wb, data: dict, company: str):
    """Fill 12_COGS and 13_SGA with historical ratios from IS data."""
    src = SOURCES[company]
    hist_years = src["hist_years"][-N_HIST_DISPLAY:]  # 3 years (match model layout)
    fc_years = src["fc_years"]

    is_d = data.get("is", {})
    rev_hist = is_d.get("revenue", {})
    cogs_hist = is_d.get("cogs", {})
    sga_hist = is_d.get("sga", {})
    dist_hist = is_d.get("distribution_expenses", {})

    # Fill COGS: component mode fills individual components, ratio mode fills total
    ws_cg = wb["12_COGS"]

    # Check if component mode
    import yaml
    yaml_path = SV2_ROOT / f"companies/{company}/configs/project.yaml"
    cogs_mode = "ratio"
    cogs_components = {}
    if yaml_path.exists():
        proj = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        custom_cogs = proj.get("model", {}).get("custom", {}).get("cogs", {})
        if custom_cogs.get("mode") == "component":
            cogs_mode = "component"
            cogs_components = {
                "material": custom_cogs.get("alumina_share", 0.37),
                "energy": custom_cogs.get("energy_share", 0.27),
                "labour": custom_cogs.get("labour_share", 0.12),
                "other": custom_cogs.get("other_share", 0.24),
            }

    if cogs_mode == "component" and cogs_components:
        # Fill each component as FORMULA = ABS(PL.COGS) × share (not literal)
        for year in hist_years:
            col = COL_START + hist_years.index(year)
            cl = get_column_letter(col)
            for comp, share in cogs_components.items():
                r = REG.get(f"CG.{comp}", 8)
                pl_title = "21_PL"
                formula_cell(ws_cg, r, col,
                             f"=ABS('{pl_title}'!{cl}${REG['PL.cogs']})*{share}",
                             FMT_MLN)
        print(f"    COGS: component mode, {len(cogs_components)} components as formulas")
    else:
        # Ratio mode: fill total COGS
        for year in hist_years:
            col = COL_START + hist_years.index(year)
            cogs = cogs_hist.get(year, 0)
            if cogs != 0:
                ws_cg.cell(REG["CG.total"], col, round(cogs, 1)).font = F_INPUT
                ws_cg.cell(REG["CG.total"], col).number_format = FMT_MLN

    last_cogs = abs(cogs_hist.get(hist_years[-1], 0))
    last_rev = abs(rev_hist.get(hist_years[-1], 1))
    cogs_ratio = last_cogs / last_rev if last_rev else 0.80

    # Write calibrated COGS ratio to Control_Panel row 20
    ws_cp = wb["Control_Panel"]
    ws_cp.cell(20, 3, round(cogs_ratio, 4)).font = F_INPUT
    ws_cp.cell(20, 3).number_format = FMT_PCT
    ws_cp.cell(20, 1, "COGS ratio (калиброванный)").font = F_LABEL

    # Ensure min_cash is set (row 55)
    # Min cash already set by build_control_panel via REG["CP.min_cash"]
    # No hardcoded fallback needed

    print(f"    COGS: ratio={cogs_ratio:.1%} → CP!C20")

    # Fill SGA
    ws_sa = wb["13_SGA"]
    for year in hist_years:
        col = 3 + hist_years.index(year)
        sga = sga_hist.get(year, 0)
        dist = dist_hist.get(year, 0)
        total_sga = sga + dist  # both negative
        # SGA total: DON'T overwrite — build_model sets =ref('21_PL')
        # (was overwriting formula with literal — audit Д4)
        pass

    # Forecast SGA: ratio × Revenue
    last_sga = (sga_hist.get(hist_years[-1], 0) + dist_hist.get(hist_years[-1], 0))
    sga_ratio = abs(last_sga) / abs(last_rev) if last_rev else 0.08
    # SGA forecast: use ratio from 03_Assump (EWA calibrated, row 8)
    for i, yr in enumerate(fc_years):
        c = 3 + len(hist_years) + i
        cl = get_column_letter(c)
        rev_ref = f"'{wb['10_Revenue'].title}'!{cl}${REG['RV.total_rev']}"
        sga_ref = f"'03_Assump'!{cl}$8"  # SGA/Revenue from preprocessing
        formula_cell(ws_sa, REG["SA.sga_total"], c,
                     f"=-ABS({rev_ref})*{sga_ref}", FMT_MLN)

    print(f"    SGA: history filled, forecast linked to 03_Assump EWA")


def validate_data(wb, data: dict, company: str):
    """Cross-check key metrics for consistency."""
    issues = []
    src = SOURCES[company]
    last_yr = src["hist_years"][-1]

    is_data = data.get("is", {})
    bs_data = data.get("bs", {})

    # Check Revenue
    rev = is_data.get("revenue", {}).get(last_yr)
    if rev:
        print(f"    Revenue ({last_yr}): {rev:,.0f}")

    # Check NI
    ni = is_data.get("net_income", {}).get(last_yr)
    if ni:
        print(f"    Net Income ({last_yr}): {ni:,.0f}")

    # Check BS balance
    ta = bs_data.get("total_assets", {}).get(last_yr, 0)
    tl = bs_data.get("total_liabilities", {}).get(last_yr, 0)
    te = bs_data.get("total_equity", {}).get(last_yr, 0)
    if ta and (tl or te):
        diff = abs(ta) - abs(tl) - abs(te)
        if abs(diff) > 1:
            issues.append(f"BS imbalance ({last_yr}): TA={ta:.0f} - TL={tl:.0f} - TE={te:.0f} = {diff:.0f}")
        else:
            print(f"    BS check ({last_yr}): TA={ta:,.0f} TL={tl:,.0f} TE={te:,.0f} ✓")

    # Check EBITDA consistency
    ebitda = is_data.get("ebitda", {}).get(last_yr, 0)
    rev_val = is_data.get("revenue", {}).get(last_yr, 0)
    if ebitda and rev_val:
        margin = ebitda / rev_val
        print(f"    EBITDA margin ({last_yr}): {margin*100:.1f}%")

    if issues:
        print(f"\n  ⚠ VALIDATION ISSUES ({len(issues)}):")
        for iss in issues:
            print(f"    ⚠ {iss}")
    else:
        print(f"    All checks passed ✓")


def fill_macro_scenarios(wb, company: str):
    """Fill 01_Macro 3 scenarios with consensus-based forecasts."""
    ws = wb["01_Macro"]
    src = SOURCES[company]
    fc_years = src["fc_years"]
    n_hist = N_HIST_DISPLAY
    fc_start = COL_START + n_hist

    # Consensus-based scenarios (LME Al $/t, LME Alumina, USD/RUB, Brent, CPI%, PPI%)
    # Factors match cfg["macro_factors"] order
    scenarios = {
        "rusal": {
            # Scenario 1: Base (consensus mean-reversion)
            1: {
                "LME Aluminium": [2450, 2500, 2550],     # gradual recovery
                "LME Alumina": [540, 520, 500],           # normalizing
                "USD/RUB": [95, 92, 90],                  # RUB strengthening
                "Brent": [75, 72, 70],                    # stable
                "CPI RU": [0.06, 0.05, 0.04],             # declining
                "PPI RU": [0.05, 0.04, 0.03],
            },
            # Scenario 2: Stress (commodity down, RUB weak)
            2: {
                "LME Aluminium": [2000, 1900, 1850],     # -20%
                "LME Alumina": [400, 380, 370],           # down
                "USD/RUB": [110, 115, 120],               # RUB weakening
                "Brent": [60, 55, 50],
                "CPI RU": [0.08, 0.09, 0.10],
                "PPI RU": [0.07, 0.08, 0.09],
            },
            # Scenario 3: Severe (deep recession)
            3: {
                "LME Aluminium": [1700, 1600, 1550],     # -35%
                "LME Alumina": [300, 280, 270],
                "USD/RUB": [130, 140, 150],
                "Brent": [45, 40, 38],
                "CPI RU": [0.12, 0.14, 0.15],
                "PPI RU": [0.10, 0.12, 0.14],
            },
        },
        "nornickel": {
            1: {
                "LME Nickel": [18000, 19000, 20000],
                "LME Copper": [9000, 9200, 9500],
                "LME Palladium": [1000, 1050, 1100],
                "LME Platinum": [950, 980, 1000],
                "USD/RUB": [95, 92, 90],
                "Brent": [75, 72, 70],
                "GDP World": [0.027, 0.029, 0.030],
            },
            2: {
                "LME Nickel": [14000, 13000, 12000],
                "LME Copper": [7000, 6500, 6000],
                "LME Palladium": [700, 650, 600],
                "LME Platinum": [750, 700, 680],
                "USD/RUB": [110, 115, 120],
                "Brent": [55, 50, 45],
                "GDP World": [0.015, 0.010, 0.005],
            },
            3: {
                "LME Nickel": [10000, 9000, 8500],
                "LME Copper": [5500, 5000, 4500],
                "LME Palladium": [500, 450, 400],
                "LME Platinum": [600, 550, 500],
                "USD/RUB": [140, 150, 160],
                "Brent": [40, 35, 30],
                "GDP World": [0.005, -0.010, -0.020],
            },
        },
    }

    company_scenarios = scenarios.get(company, {})
    if not company_scenarios:
        return

    from build_model import COMPANY_CONFIGS
    cfg = COMPANY_CONFIGS.get(company, {})
    factors = cfg.get("macro_factors", [])

    # Scenario row blocks: S1 starts at row 8, gap = len(factors)+3
    n_f = len(factors)
    filled = 0
    for s_idx in [1, 2, 3]:
        s_data = company_scenarios.get(s_idx, {})
        s_base = 6 + (s_idx - 1) * (n_f + 3)  # matches build_macro layout
        for i, factor in enumerate(factors):
            r = s_base + 2 + i
            vals = s_data.get(factor, [0] * len(fc_years))
            for j, val in enumerate(vals):
                c = fc_start + j
                ws.cell(r, c, val).font = F_INPUT
                if isinstance(val, float) and val < 1:
                    ws.cell(r, c).number_format = FMT_PCT
                else:
                    ws.cell(r, c).number_format = FMT_RATIO1
                filled += 1

    print(f"    Macro scenarios: 3 × {n_f} factors × {len(fc_years)} years = {filled} cells")


def fill_macro_forecasts(wb, data: dict, company: str):
    """Fill 01_Macro forecast columns with simple mean-reversion forecasts.

    For commodity prices: mean reversion towards historical median.
    For FX/rates: carry forward or from YAML key_rate_forecast.
    """
    ws = wb["01_Macro"]
    src = SOURCES[company]
    hist_years = src["hist_years"][-3:]
    fc_years = src["fc_years"]
    fc_start_col = COL_START + N_HIST_DISPLAY

    macro_data = data.get("macro", [])
    if not macro_data:
        return

    # Group by factor
    factors: Dict[str, Dict[int, float]] = {}
    for item in macro_data:
        factors.setdefault(item["factor"], {})[item["year"]] = item["value"]

    # Load key rate forecast from YAML
    import yaml
    yaml_path = SV2_ROOT / f"companies/{company}/configs/project.yaml"
    kr_forecast = {}
    if yaml_path.exists():
        proj = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        kr_forecast = proj.get("model", {}).get("custom", {}).get("debt", {}).get("cbr_key_rate_forecast", {})

    # Find row for each factor in 01_Macro (historical section)
    # Scan rows 55+ (where historical macro was written by fill_macro)
    factor_rows = {}
    for r in range(55, 80):
        label = ws.cell(r, 1).value
        if label and isinstance(label, str):
            factor_rows[label.strip()] = r

    filled = 0
    for factor_name, row in factor_rows.items():
        series = factors.get(factor_name, {})
        if not series:
            continue

        # Get last 5 years for mean calculation
        recent = sorted(series.items())[-5:]
        if not recent:
            continue

        # Mean reversion forecast: value converges to 5-year median
        vals = [v for _, v in recent]
        median_val = sorted(vals)[len(vals) // 2]
        last_val = recent[-1][1]

        # Reversion speed: 30% per year towards median
        reversion = 0.3
        forecast_val = last_val
        for i, yr in enumerate(fc_years):
            c = fc_start_col + i
            forecast_val = forecast_val + reversion * (median_val - forecast_val)
            ws.cell(row, c, round(forecast_val, 2)).font = F_INPUT
            ws.cell(row, c).number_format = '#,##0.00' if abs(forecast_val) < 1000 else '#,##0'
            filled += 1

    # Also fill SCENARIO section (rows 8-13) with base scenario forecasts
    # Map factor names to scenario rows
    factor_row_map = {}
    for r in range(8, 20):
        label = ws.cell(r, 1).value
        if label and isinstance(label, str):
            factor_row_map[label.strip()] = r

    scenario_filled = 0
    for factor_name, row in factor_row_map.items():
        series = factors.get(factor_name, {})
        if not series:
            continue
        recent = sorted(series.items())[-5:]
        if not recent:
            continue
        vals = [v for _, v in recent]
        median_val = sorted(vals)[len(vals) // 2]
        last_val = recent[-1][1]
        reversion = 0.3
        forecast_val = last_val
        for i, yr in enumerate(fc_years):
            c = fc_start_col + i
            forecast_val = forecast_val + reversion * (median_val - forecast_val)
            ws.cell(row, c, round(forecast_val, 2)).font = F_INPUT
            ws.cell(row, c).number_format = '#,##0.00' if abs(forecast_val) < 1000 else '#,##0'
            scenario_filled += 1

    print(f"    Macro forecasts: {filled} historical + {scenario_filled} scenario cells")


def fill_all(company: str, model_path: str):
    """Main entry: load data and fill model."""
    print(f"\n{'='*60}")
    print(f"Filling data for: {company}")
    print(f"{'='*60}")

    # Load source data
    print("\n1. Loading source data...")
    data = load_source_data(company)
    if not data:
        print("  ✗ No data loaded!")
        return

    stats = {
        "IS metrics": len(data.get("is", {})),
        "BS metrics": len(data.get("bs", {})),
        "CF metrics": len(data.get("cf", {})),
        "Segment rows": len(data.get("segments", [])),
        "Macro rows": len(data.get("macro", [])),
        "Debt instruments": len(data.get("debt", [])),
    }
    for k, v in stats.items():
        print(f"    {k}: {v}")

    # Open model
    model_file = BASE_DIR / model_path
    if not model_file.exists():
        print(f"  ✗ Model file not found: {model_file}")
        return

    print(f"\n2. Opening model: {model_file.name}")
    wb = openpyxl.load_workbook(str(model_file))

    # Discover CP parameter rows from built workbook
    discover_cp_rows(wb)

    # Fill sheets
    print("\n3. Filling 02_Hist (IS/BS/CF)...")
    fill_hist_sheet(wb, data, company)

    # 11_Segments: data now filled via fill_revenue → SG.{key}_vol/price rows
    # Old fill_segments created dynamic layout that conflicted with build_segments
    print("\n4. 11_Segments: filled via fill_revenue (REG-registered rows)")

    print("\n5. Filling 01_Macro (factors + scenarios)...")
    fill_macro(wb, data, company)
    fill_macro_scenarios(wb, company)

    print("\n6. Filling 10_Revenue (volumes & prices)...")
    fill_revenue(wb, data, company)

    print("\n7. Filling 17_Debt (opening balances)...")
    fill_debt_hist(wb, data, company)

    print("\n5b. Filling _Debt_Schedule (per-instrument)...")
    fill_debt_schedule(wb, data, company)

    print("\n6a. Filling revenue reconciliation...")
    # Revenue reconciliation: build_model sets formula = '02_Hist'!revenue - Σ segments
    print("    Revenue reconciliation: formula from build_model (not fill_data)")

    print("\n6b. Filling macro factor forecasts...")
    fill_macro_forecasts(wb, data, company)

    print("\n7a. Filling statement sheets history (PL/CF col E)...")
    fill_statement_history(wb, data, company)

    # 7b. BS history: build_model sets refs for mapped items; fill remaining
    print("\n7b. Filling 20_BS residual history (Other items, tax_pay, equity)...")
    fill_bs_history(wb, data, company)

    print("\n8. Computing WC days + filling COGS/SGA from history...")
    fill_wc_days(wb, data, company)
    fill_cogs_sga_from_history(wb, data, company)

    print("\n9. Validating data consistency...")
    validate_data(wb, data, company)

    # Save
    wb.save(str(model_file))
    print(f"\n✓ Saved: {model_file}")

    # Count filled cells
    total_filled = 0
    for s in wb.sheetnames:
        ws = wb[s]
        filled = sum(1 for row in ws.iter_rows() for c in row
                     if c.value is not None and not isinstance(c.value, str))
        if filled > 0:
            total_filled += filled
    print(f"  Total data cells: {total_filled}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fill Corporate Model v4 with data")
    parser.add_argument("--company", required=True, choices=["rusal", "nornickel"])
    parser.add_argument("--model", required=True, help="Path to model xlsx (relative to v4 root)")
    args = parser.parse_args()
    fill_all(args.company, args.model)
