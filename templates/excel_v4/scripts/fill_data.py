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

        vol_r = REG.get(f"RV.{key}_vol")
        price_r = REG.get(f"RV.{key}_price")
        if not vol_r:
            continue

        vol_data = matching.get("sales_kt", matching.get("production_kt", {}))
        price_data = matching.get("avg_price_usd_t", {})
        rev_data = matching.get("revenue", {})

        for year in hist_years:
            if year not in vol_data and year not in rev_data:
                continue
            col = 3 + hist_years.index(year)

            if year in vol_data:
                cell = ws.cell(vol_r, col, round(vol_data[year], 0))
                cell.font = F_INPUT
                cell.number_format = FMT_INT
            if year in price_data and price_r:
                cell = ws.cell(price_r, col, round(price_data[year], 0))
                cell.font = F_INPUT
                cell.number_format = FMT_INT

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

        # Write forecasts
        forecast_vol = last_vol
        forecast_price = last_price
        for i, yr in enumerate(fc_years):
            c = fc_start_col + i
            # Volume: EWA growth
            if avg_growth != 0:
                import math
                forecast_vol = forecast_vol * math.exp(avg_growth)
            # Overwrite formula cell with calculated value
            ws.cell(vol_r, c, round(forecast_vol, 0)).font = F_FORMULA
            ws.cell(vol_r, c).number_format = FMT_INT

            # Price: if macro-driven, use factor growth × β
            if factor_name and factor_series:
                # Use mean-reversion forecast of factor (already in 01_Macro)
                # For now: simple chain-link using last known growth
                last_factor = factor_series.get(hist_years[-1], factor_series.get(hist_years[-2], 0))
                # Price mean-reverts like factor
                if last_factor > 0 and last_price > 0:
                    # Price grows at β × factor growth rate
                    # Simple: median reversion at 30% per year
                    median_price = sorted(price_data.values())[len(price_data) // 2] if price_data else last_price
                    forecast_price = forecast_price + 0.3 * (median_price - forecast_price)

            if price_r and forecast_price > 0:
                ws.cell(price_r, c, round(forecast_price, 0)).font = F_FORMULA
                ws.cell(price_r, c).number_format = FMT_INT


def fill_revenue_reconciliation(wb, data: dict, company: str):
    """Fill reconciliation row: Reported Revenue - Σ segments for history years."""
    ws = wb["10_Revenue"]
    src = SOURCES[company]
    hist_years = src["hist_years"][-N_HIST_DISPLAY:]
    is_d = data.get("is", {})

    r_recon = REG.get("RV.recon", 19)
    r_total = REG.get("RV.total_rev", 20)

    filled = 0
    for yr_idx, yr in enumerate(hist_years):
        col = COL_START + yr_idx
        reported_rev = abs(is_d.get("revenue", {}).get(yr, 0))
        # Σ segments = total formula evaluates to... but we can't read formula result
        # Instead: compute segment sum from data
        seg_sum = 0
        for seg_key in ["seg1", "seg2", "seg3"]:
            rev_r = REG.get(f"RV.{seg_key}_rev")
            if rev_r:
                cell_val = ws.cell(rev_r, col).value
                if isinstance(cell_val, (int, float)):
                    seg_sum += abs(cell_val)
                elif isinstance(cell_val, str) and cell_val.startswith("="):
                    # Formula — can't evaluate, estimate from vol × price
                    vol_r = REG.get(f"RV.{seg_key}_vol")
                    price_r = REG.get(f"RV.{seg_key}_price")
                    if vol_r and price_r:
                        v = ws.cell(vol_r, col).value
                        p = ws.cell(price_r, col).value
                        if isinstance(v, (int, float)) and isinstance(p, (int, float)):
                            seg_sum += v * p / 1000

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
    total = abs(st) + abs(lt)
    cash = abs(bs.get("cash", {}).get(last_yr, 0))

    if total > 0:
        ws.cell(REG["DT.open"], hc, round(total, 1)).font = F_INPUT
        ws.cell(REG["DT.open"], hc).number_format = FMT_MLN
        ws.cell(REG["DT.close"], hc, round(total, 1)).font = F_INPUT
        ws.cell(REG["DT.close"], hc).number_format = FMT_MLN
        ws.cell(REG["DT.st"], hc, round(abs(st), 1)).font = F_INPUT
        ws.cell(REG["DT.st"], hc).number_format = FMT_MLN
        ws.cell(REG["DT.lt"], hc, round(abs(lt), 1)).font = F_INPUT
        ws.cell(REG["DT.lt"], hc).number_format = FMT_MLN
        print(f"    Debt opening: ST={abs(st):.0f} LT={abs(lt):.0f} Total={total:.0f}")

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

    fc_start_col = hc + 1
    for c in range(fc_start_col, fc_start_col + len(fc_years)):
        ws.cell(REG["DT.avg_rate"], c, round(avg_rate, 4)).font = F_INPUT
        ws.cell(REG["DT.avg_rate"], c).number_format = FMT_PCT
    # Also fill history col
    ws.cell(REG["DT.avg_rate"], hc, round(avg_rate, 4)).font = F_INPUT
    print(f"    Avg rate (weighted from instruments): {avg_rate*100:.2f}%")

    # Fill interest in history col (from IS data)
    interest = abs(is_data.get("interest_expense", {}).get(last_yr, 0))
    if interest == 0:
        interest = abs(is_data.get("finance_cost_net", {}).get(last_yr, 0))
    if total > 0 and interest > 0:
        ws.cell(REG["DT.interest"], hc, round(interest, 1)).font = F_INPUT
        ws.cell(REG["DT.interest"], hc).number_format = FMT_MLN

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
                # Refinancing = mandatory (assumed full refi)
                ws.cell(REG["DT.refi"], c).value = f"={get_column_letter(c)}{REG['DT.mandatory']}"
                ws.cell(REG["DT.refi"], c).font = F_FORMULA
                ws.cell(REG["DT.refi"], c).number_format = FMT_MLN

        if repay_by_year:
            print(f"    Mandatory repay: " + ", ".join(f"{yr}={repay_by_year[yr]/1e6:,.0f}M" for yr in sorted(repay_by_year)))

    # Also fill ND in history col
    nd = total - cash
    ws.cell(REG["DT.nd"], hc, round(nd, 1)).font = F_FORMULA
    ws.cell(REG["DT.nd"], hc).number_format = FMT_MLN

    # ── INSTRUMENT SCHEDULE ──
    # Fill top instruments below aggregate corkscrew (row 25+)
    debt_instruments = data.get("debt", [])
    if debt_instruments:
        # Sort by balance descending
        instruments = sorted(debt_instruments, key=lambda x: -abs(float(x.get("opening_balance", 0) or 0)))
        top_n = min(15, len(instruments))

        r_start = 25
        section_header(ws, r_start - 1, f"ИНСТРУМЕНТЫ ({len(instruments)} всего, top {top_n})")

        # Headers
        ws.cell(r_start, 1, "Инструмент").font = F_YEAR
        ws.cell(r_start, 2, "Валюта").font = F_YEAR
        ws.cell(r_start, 3, "Баланс").font = F_YEAR
        ws.cell(r_start, 4, "Ставка").font = F_YEAR
        ws.cell(r_start, 5, "Тип").font = F_YEAR
        ws.cell(r_start, 6, "Погашение").font = F_YEAR

        other_balance = 0
        other_interest = 0
        for i, inst in enumerate(instruments):
            bal = abs(float(inst.get("opening_balance", 0) or 0))
            rate = float(inst.get("interest_rate", 0) or 0)
            name = str(inst.get("instrument_name", f"Instrument_{i+1}"))[:35]
            ccy = str(inst.get("currency", "USD"))
            rtype = str(inst.get("rate_type", "fixed"))
            maturity = str(inst.get("maturity_date", ""))

            if i < top_n:
                r = r_start + 1 + i
                ws.cell(r, 1, name).font = F_LABEL
                ws.cell(r, 2, ccy).font = F_LABEL
                ws.cell(r, 3, round(bal / 1e6, 1)).font = F_INPUT  # mln
                ws.cell(r, 3).number_format = FMT_MLN
                ws.cell(r, 4, rate).font = F_INPUT
                ws.cell(r, 4).number_format = FMT_PCT2
                ws.cell(r, 5, rtype).font = F_LABEL
                ws.cell(r, 6, maturity).font = F_LABEL
            else:
                other_balance += bal
                other_interest += bal * rate

        # Other bucket
        r_other = r_start + 1 + top_n
        ws.cell(r_other, 1, f"Other ({len(instruments) - top_n} instruments)").font = F_LABEL_B
        ws.cell(r_other, 3, round(other_balance / 1e6, 1)).font = F_INPUT
        ws.cell(r_other, 3).number_format = FMT_MLN
        if other_balance > 0:
            ws.cell(r_other, 4, round(other_interest / other_balance, 4)).font = F_INPUT
            ws.cell(r_other, 4).number_format = FMT_PCT2

        # Total row
        r_total_inst = r_other + 1
        ws.cell(r_total_inst, 1, "ИТОГО").font = F_LABEL_B
        total_col = get_column_letter(3)
        formula_cell(ws, r_total_inst, 3,
                     f"=SUM({total_col}{r_start+1}:{total_col}{r_other})", FMT_MLN, bold=True)

        print(f"    Instruments: {top_n} top + Other ({len(instruments)-top_n}), total={total/1e6:.0f}M")

    # Fill Tax DTA/DTL history
    if "19_Tax" in wb.sheetnames:
        ws_tx = wb["19_Tax"]
        dta = abs(bs.get("dta", {}).get(last_yr, 0))
        dtl = abs(bs.get("dtl", {}).get(last_yr, 0))
        if dta:
            ws_tx.cell(REG["TX.dta_open"], hc, round(dta, 1)).font = F_INPUT
            ws_tx.cell(REG["TX.dta_close"], hc, round(dta, 1)).font = F_INPUT
        if dtl:
            ws_tx.cell(REG["TX.dtl_open"], hc, round(dtl, 1)).font = F_INPUT
            ws_tx.cell(REG["TX.dtl_close"], hc, round(dtl, 1)).font = F_INPUT
        if dta or dtl:
            print(f"    Tax: DTA={dta:.0f} DTL={dtl:.0f}")

    # Fill lease opening from BS
    if "18_Lease" in wb.sheetnames:
        ws_l = wb["18_Lease"]
        rou = abs(bs.get("rou_asset", {}).get(last_yr, 0))
        lease_cl = abs(bs.get("lease_liab_current", {}).get(last_yr, 0))
        lease_ncl = abs(bs.get("lease_liab_noncurrent", {}).get(last_yr, 0))
        lease_total = lease_cl + lease_ncl
        if rou > 0 or lease_total > 0:
            ws_l.cell(REG["LS.rou_open"], hc, round(rou, 1)).font = F_INPUT
            ws_l.cell(REG["LS.rou_close"], hc, round(rou, 1)).font = F_INPUT
            ws_l.cell(REG["LS.liab_open"], hc, round(lease_total, 1)).font = F_INPUT
            ws_l.cell(REG["LS.liab_close"], hc, round(lease_total, 1)).font = F_INPUT
            print(f"    Lease: ROU={rou:.0f} Liability={lease_total:.0f}")

    # Fill PPE opening from BS
    if "15_PPE" in wb.sheetnames:
        ws_p = wb["15_PPE"]
        ppe_gross = abs(bs.get("ppe_gross", {}).get(last_yr, 0))
        accdep = abs(bs.get("ppe_accum_dep", {}).get(last_yr, 0))
        ppe_net = abs(bs.get("ppe_net", {}).get(last_yr, 0))
        if ppe_net > 0:
            ws_p.cell(REG["PP.gross_open"], hc, round(ppe_gross or ppe_net * 2, 1)).font = F_INPUT
            ws_p.cell(REG["PP.gross_open"], hc).number_format = FMT_MLN
            ws_p.cell(REG["PP.gross_close"], hc, round(ppe_gross or ppe_net * 2, 1)).font = F_INPUT
            ws_p.cell(REG["PP.dep_open"], hc, round(accdep or ppe_net, 1)).font = F_INPUT
            ws_p.cell(REG["PP.dep_close"], hc, round(accdep or ppe_net, 1)).font = F_INPUT
            ws_p.cell(REG["PP.net_open"], hc, round(ppe_net, 1)).font = F_INPUT
            ws_p.cell(REG["PP.net_close"], hc, round(ppe_net, 1)).font = F_INPUT
            # Fill DA history for sustaining CapEx calculation
            da_hist = is_data.get("total_da", is_data.get("dep_ppe", {}))
            for yr_offset, yr in enumerate(hist_years[-N_HIST_DISPLAY:]):
                da_val = da_hist.get(yr, 0)
                if da_val:
                    col_pp = COL_START + yr_offset
                    ws_p.cell(REG["PP.dep_charge"], col_pp, round(abs(da_val), 1)).font = F_INPUT
                    ws_p.cell(REG["PP.dep_charge"], col_pp).number_format = FMT_MLN
            print(f"    PPE: Gross={ppe_gross:.0f} AccDep={accdep:.0f} Net={ppe_net:.0f}")

    # Fill Equity opening
    if "24_Equity" in wb.sheetnames:
        ws_e = wb["24_Equity"]
        re = bs.get("retained_earnings", {}).get(last_yr, 0)
        if re != 0:
            ws_e.cell(REG["EQ.re_open"], hc, round(re, 1)).font = F_INPUT
            ws_e.cell(REG["EQ.re_close"], hc, round(re, 1)).font = F_INPUT
            print(f"    Retained earnings opening: {re:.0f}")

    # Fill BS last hist year (static items for carry-forward)
    if "20_BS" in wb.sheetnames:
        ws_bs = wb["20_BS"]
        static_keys = {
            "other_ca": ["other_current_assets"],
            "goodwill": ["goodwill"],
            "intang": ["intangibles"],
            "other_nca": ["other_non_current_assets", "investments_lt"],
            "other_cl": ["other_current_liabilities"],
            "other_ncl": ["other_non_current_liabilities"],
            "sc": ["share_capital"],
            "apic": ["additional_paid_in_capital", "apic"],
            "aoci": ["aoci", "other_comprehensive_income"],
        }
        for bs_key, source_keys in static_keys.items():
            val = 0
            for sk in source_keys:
                v = bs.get(sk, {}).get(last_yr, 0)
                if v:
                    val = v
                    break
            if val:
                ws_bs.cell(REG[f"BS.{bs_key}"], 3, round(val, 1)).font = F_INPUT


def fill_statement_history(wb, data: dict, company: str):
    """Fill 21_PL and 23_CF history columns (E=2025) for forecast continuity."""
    src = SOURCES[company]
    last_yr = src["hist_years"][-1]
    hc = COL_START + N_HIST_DISPLAY - 1  # col E = 5

    is_d = data.get("is", {})
    cf_d = data.get("cf", {})

    # Fill CF history (last year) for cash opening
    ws_cf = wb["23_CF"]
    cf_map = {
        "cfo_total": "cfo", "cfi_total": "cfi", "cff_total": "cff",
        "capex": "capex", "net_change": "net_change",
    }
    filled = 0
    for src_key, reg_suffix in cf_map.items():
        val = cf_d.get(src_key, {}).get(last_yr)
        if val is not None:
            r = REG.get(f"CF.{reg_suffix}")
            if r:
                ws_cf.cell(r, hc, round(val, 1)).font = F_INPUT
                ws_cf.cell(r, hc).number_format = FMT_MLN
                filled += 1

    # Cash opening = previous year closing cash from BS
    bs_d = data.get("bs", {})
    cash_open = bs_d.get("cash", {}).get(last_yr - 1, 0)
    cash_close = bs_d.get("cash", {}).get(last_yr, 0)
    if cash_close:
        ws_cf.cell(REG["CF.cash_close"], hc, round(cash_close, 1)).font = F_INPUT
        ws_cf.cell(REG["CF.cash_close"], hc).number_format = FMT_MLN
    if cash_open:
        ws_cf.cell(REG["CF.cash_open"], hc, round(cash_open, 1)).font = F_INPUT

    # Fill PL history (last 3 years)
    ws_pl = wb["21_PL"]
    pl_map = {
        "revenue": "revenue", "cogs": "cogs", "gross_profit": "gp",
        "sga": "sga", "ebitda": "ebitda", "ebit": "ebit",
        "interest_expense": "interest", "ebt": "ebt",
        "tax_expense": "tax", "net_income": "ni",
        "total_da": "da",
    }
    hist_3 = src["hist_years"][-N_HIST_DISPLAY:]
    for yr in hist_3:
        col = COL_START + hist_3.index(yr)
        for src_key, reg_suffix in pl_map.items():
            val = is_d.get(src_key, {}).get(yr)
            if val is not None:
                r = REG.get(f"PL.{reg_suffix}")
                if r:
                    ws_pl.cell(r, col, round(val, 1)).font = F_INPUT
                    ws_pl.cell(r, col).number_format = FMT_MLN

    print(f"    CF history: {filled} metrics for {last_yr}, cash={cash_close}")
    print(f"    PL history: {len(pl_map)} metrics × {len(hist_3)} years")


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

    filled = 0
    for yr_idx, yr in enumerate(hist_3):
        col = COL_START + yr_idx
        # Accumulate per-row
        row_accum: Dict[int, float] = {}
        for src_key, bs_key in bs_map.items():
            val = bs.get(src_key, {}).get(yr)
            if val is not None and isinstance(val, (int, float)):
                r = REG.get(f"BS.{bs_key}")
                if r:
                    row_accum[r] = row_accum.get(r, 0) + val
        for r, val in row_accum.items():
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
    for yr_idx, yr in enumerate(hist_3):
        col = COL_START + yr_idx
        tca = abs(bs.get("total_ca", bs.get("total_current_assets", {})).get(yr, 0))
        tcl = abs(bs.get("total_cl", bs.get("total_current_liabilities", {})).get(yr, 0))
        tncl_src = abs(bs.get("total_ncl", bs.get("total_non_current_liabilities", {})).get(yr, 0))

        if tca > 0:
            known_ca = sum(abs(bs.get(k, {}).get(yr, 0)) for k in
                          ["cash", "accounts_receivable", "inventory"])
            other_ca = tca - known_ca
            if other_ca > 0:
                ws.cell(REG["BS.other_ca"], col, round(other_ca, 1)).font = F_INPUT
                ws.cell(REG["BS.other_ca"], col).number_format = FMT_MLN

        # Also compute Other_NCA from TNCA
        tnca_src = abs(bs.get("total_nca", bs.get("total_non_current_assets", {})).get(yr, 0))
        if tnca_src > 0:
            known_nca = sum(abs(bs.get(k, {}).get(yr, 0)) for k in
                           ["ppe_net", "intangibles", "dta", "rou_asset", "goodwill"])
            other_nca = tnca_src - known_nca
            if other_nca > 0:
                ws.cell(REG["BS.other_nca"], col, round(other_nca, 1)).font = F_INPUT

        if tcl > 0:
            known_cl = sum(abs(bs.get(k, {}).get(yr, 0)) for k in
                          ["accounts_payable", "short_term_debt", "lease_liab_current"
                          ]) + bs.get("taxes_payable", {}).get(yr, 0)
            other_cl = tcl - known_cl
            if other_cl > 0:
                ws.cell(REG["BS.other_cl"], col, round(other_cl, 1)).font = F_INPUT

        if tncl_src > 0:
            known_ncl = sum(abs(bs.get(k, {}).get(yr, 0)) for k in
                           ["long_term_debt", "dtl", "lease_liab_noncurrent"])
            other_ncl = tncl_src - known_ncl
            if other_ncl > 0:
                ws.cell(REG["BS.other_ncl"], col, round(other_ncl, 1)).font = F_INPUT

    print(f"    BS history: {filled} metrics filled, Other CL/NCL/CA from totals")


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

    computed = 0
    for year in hist_years:
        col = 3 + hist_years.index(year)
        rev = abs(rev_hist.get(year, 0))
        cogs = abs(cogs_hist.get(year, 0))
        ar = abs(ar_hist.get(year, 0))
        inv_ = abs(inv_hist.get(year, 0))
        ap = abs(ap_hist.get(year, 0))

        if rev > 0:
            dso = ar / rev * 365
            ws.cell(REG["WC.dso"], col, round(dso, 0)).font = F_INPUT
            ws.cell(REG["WC.dso"], col).number_format = FMT_DAYS
        if cogs > 0:
            dio = inv_ / cogs * 365
            dpo = ap / cogs * 365
            ws.cell(REG["WC.dio"], col, round(dio, 0)).font = F_INPUT
            ws.cell(REG["WC.dio"], col).number_format = FMT_DAYS
            ws.cell(REG["WC.dpo"], col, round(dpo, 0)).font = F_INPUT
            ws.cell(REG["WC.dpo"], col).number_format = FMT_DAYS
        computed += 1

    # Forecast: link to 03_Assump EWA-calibrated days (rows 13/14/15)
    fc_years = src["fc_years"]
    assump_rows = {"dso": 13, "dio": 14, "dpo": 15}
    for metric_key, assump_row in assump_rows.items():
        for i, yr in enumerate(fc_years):
            c = COL_START + N_HIST_DISPLAY + i
            cl = get_column_letter(c)
            formula_cell(ws, REG[f"WC.{metric_key}"], c,
                         f"='03_Assump'!{cl}${assump_row}", FMT_DAYS)

    # Fill WC balances (AR, INV, AP) for history years
    bs_d = data.get("bs", {})
    for yr_idx, year in enumerate(hist_years):
        col = COL_START + yr_idx
        ar_v = abs(bs_d.get("accounts_receivable", {}).get(year, 0))
        inv_v = abs(bs_d.get("inventory", {}).get(year, 0))
        ap_v = abs(bs_d.get("accounts_payable", {}).get(year, 0))
        if ar_v:
            ws.cell(REG["WC.ar"], col, round(ar_v, 1)).font = F_INPUT
            ws.cell(REG["WC.ar"], col).number_format = FMT_MLN
        if inv_v:
            ws.cell(REG["WC.inv"], col, round(inv_v, 1)).font = F_INPUT
            ws.cell(REG["WC.inv"], col).number_format = FMT_MLN
        if ap_v:
            ws.cell(REG["WC.ap"], col, round(-ap_v, 1)).font = F_INPUT
            ws.cell(REG["WC.ap"], col).number_format = FMT_MLN

    print(f"    WC days: {computed} historical years computed, forecast carry-forwarded")
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
        # Fill each component for history years
        for year in hist_years:
            col = COL_START + hist_years.index(year)
            total_cogs = abs(cogs_hist.get(year, 0))
            if total_cogs > 0:
                for comp, share in cogs_components.items():
                    r = REG.get(f"CG.{comp}", 8)
                    ws_cg.cell(r, col, round(total_cogs * share, 1)).font = F_INPUT
                    ws_cg.cell(r, col).number_format = FMT_MLN
        print(f"    COGS: component mode, {len(cogs_components)} components filled")
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
    if ws_cp.cell(55, 3).value is None:
        ws_cp.cell(55, 3, 500).font = F_INPUT
        ws_cp.cell(55, 3).number_format = FMT_MLN0
        ws_cp.cell(55, 1, "Min cash target").font = F_LABEL

    print(f"    COGS: ratio={cogs_ratio:.1%} → CP!C20")

    # Fill SGA
    ws_sa = wb["13_SGA"]
    for year in hist_years:
        col = 3 + hist_years.index(year)
        sga = sga_hist.get(year, 0)
        dist = dist_hist.get(year, 0)
        total_sga = sga + dist  # both negative
        if total_sga != 0:
            ws_sa.cell(REG["SA.sga_total"], col, round(total_sga, 1)).font = F_INPUT
            ws_sa.cell(REG["SA.sga_total"], col).number_format = FMT_MLN

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

    # Fill sheets
    print("\n3. Filling 02_Hist (IS/BS/CF)...")
    fill_hist_sheet(wb, data, company)

    print("\n4. Filling 11_Segments (operational)...")
    fill_segments(wb, data, company)

    print("\n5. Filling 01_Macro (factors)...")
    fill_macro(wb, data, company)

    print("\n6. Filling 10_Revenue (volumes & prices)...")
    fill_revenue(wb, data, company)

    print("\n7. Filling 17_Debt (opening balances)...")
    fill_debt_hist(wb, data, company)

    print("\n6a. Filling revenue reconciliation...")
    fill_revenue_reconciliation(wb, data, company)

    print("\n6b. Filling macro factor forecasts...")
    fill_macro_forecasts(wb, data, company)

    print("\n7a. Filling statement sheets history (PL/CF col E)...")
    fill_statement_history(wb, data, company)

    print("\n7b. Filling 20_BS history column from 02_Hist...")
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
