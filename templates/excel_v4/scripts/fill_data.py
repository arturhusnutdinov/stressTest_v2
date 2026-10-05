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
    """Fill 02_Hist with IS/BS/CF data."""
    ws = wb["02_Hist"]
    src = SOURCES[company]
    hist_years = src["hist_years"]

    # Determine year columns (C onwards)
    # Write year headers
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
    """Fill 11_Segments with operational data."""
    ws = wb["11_Segments"]
    apply_col_widths(ws)
    ws.cell(1, 1, f"11_Segments — Operational Data").font = F_TITLE

    src = SOURCES[company]
    hist_years = src["hist_years"][-8:]  # Last 8 years for segments
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
    """Fill 10_Revenue with historical segment volumes & prices."""
    ws = wb["10_Revenue"]
    segments_data = data.get("segments", [])

    # Extract volume and price history per segment
    seg_vp: Dict[str, Dict[str, Dict[int, float]]] = {}
    for item in segments_data:
        seg = item["segment"]
        met = item["metric"]
        if met in ("sales_kt", "production_kt", "avg_price_usd_t", "revenue"):
            seg_vp.setdefault(seg, {}).setdefault(met, {})[item["year"]] = item["value"]

    src = SOURCES[company]
    hist_years = src["hist_years"][-5:]

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
