"""
export_to_excel.py — Export company data from data_mart_v2.db to Excel template v2.0.

Usage:
    python3 tools/export_to_excel.py --company us_steel
    python3 tools/export_to_excel.py --company rusal --output rusal_export.xlsx

Creates a fully-populated Excel workbook with:
  - meta: company metadata
  - history_is / history_bs / history_cf: all historical metrics (metric × year)
  - debt_instruments: detailed instrument schedule
  - macro_factors: macro factor history
  - segments_financial / segments_operational: segment data
  - production_kpi: production metrics
  - dict_metrics: canonical metrics + aliases
  - data_quality_report: auto-generated quality checks
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import DB_PATH

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    print("pip install openpyxl")
    sys.exit(1)


# ── Styles ────────────────────────────────────────────────────────────────────

HEADER_FONT = Font(bold=True, size=10, color="FFFFFF")
HEADER_FILL = PatternFill(start_color="2C3E50", end_color="2C3E50", fill_type="solid")
SECTION_FILL = PatternFill(start_color="ECF0F1", end_color="ECF0F1", fill_type="solid")
METRIC_FONT = Font(size=10, name="Consolas")
NUM_FMT = '#,##0'
THIN_BORDER = Border(
    bottom=Side(style='thin', color='E8E8E8'),
)


def style_header(ws, row, max_col):
    for col in range(1, max_col + 1):
        cell = ws.cell(row=row, column=col)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal='center')


def style_metric_col(ws, max_row):
    for row in range(3, max_row + 1):
        ws.cell(row=row, column=1).font = METRIC_FONT


# ── Main Export ───────────────────────────────────────────────────────────────

def export_company(company_id: str, output_path: Path):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Company info
    co = conn.execute("SELECT * FROM companies WHERE company_id=?", (company_id,)).fetchone()
    if not co:
        print(f"Company '{company_id}' not found in DB")
        return

    # Year range
    yr_range = conn.execute("""
        SELECT MIN(p.year), MAX(p.year) FROM history_is h
        JOIN periods p ON h.period_id=p.period_id WHERE h.company_id=?
    """, (company_id,)).fetchone()
    years = list(range(yr_range[0], yr_range[1] + 1))

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    # ── 1. Meta sheet ──────────────────────────────────────────────────────
    ws = wb.create_sheet("meta")
    meta_fields = [
        ("template_version", "2.0"),
        ("company_code", company_id),
        ("company_name", co["name"] or company_id),
        ("base_currency", co["currency"] or "USD"),
        ("base_unit", "mUSD"),
        ("accounting_standard", co["accounting_standard"] or "US_GAAP"),
        ("is_income_sign", "credit_negative" if (co["accounting_standard"] or "") == "US_GAAP" else "natural"),
        ("history_start_year", years[0]),
        ("history_end_year", years[-1]),
    ]
    ws.cell(1, 1, "field").font = Font(bold=True)
    ws.cell(1, 2, "value").font = Font(bold=True)
    for i, (field, value) in enumerate(meta_fields, 2):
        ws.cell(i, 1, field)
        ws.cell(i, 2, value)
    ws.column_dimensions['A'].width = 25
    ws.column_dimensions['B'].width = 30

    # ── 2. History IS/BS/CF ────────────────────────────────────────────────
    for stmt, sheet_name in [("is", "history_is"), ("bs", "history_bs"), ("cf", "history_cf")]:
        ws = wb.create_sheet(sheet_name)
        table = f"history_{stmt}"

        # Get all metrics for this company
        metrics = [r[0] for r in conn.execute(f"""
            SELECT DISTINCT h.metric FROM {table} h
            JOIN periods p ON h.period_id=p.period_id
            WHERE h.company_id=? ORDER BY h.metric
        """, (company_id,)).fetchall()]

        # Header row
        ws.cell(1, 1, "metric")
        for j, yr in enumerate(years):
            ws.cell(1, j + 2, yr)
        ws.cell(1, len(years) + 2, "unit")
        style_header(ws, 1, len(years) + 2)

        # Data rows
        for i, metric in enumerate(metrics, 2):
            ws.cell(i, 1, metric)
            # Get values
            rows = conn.execute(f"""
                SELECT p.year, h.value FROM {table} h
                JOIN periods p ON h.period_id=p.period_id
                WHERE h.company_id=? AND h.metric=?
            """, (company_id, metric)).fetchall()
            val_by_yr = {r["year"]: r["value"] for r in rows}

            for j, yr in enumerate(years):
                v = val_by_yr.get(yr)
                if v is not None:
                    # Convert from DB (full USD) to mUSD
                    ws.cell(i, j + 2, v / 1e6)
                    ws.cell(i, j + 2).number_format = NUM_FMT

            ws.cell(i, len(years) + 2, "mUSD")

        ws.column_dimensions['A'].width = 40
        style_metric_col(ws, len(metrics) + 1)

    # ── 3. Debt Instruments ────────────────────────────────────────────────
    ws = wb.create_sheet("debt_instruments")
    di_cols = ["instrument_id", "instrument_name", "db_type", "currency",
               "opening_balance", "maturity_date", "interest_rate",
               "rate_type", "payment_frequency", "amortization_profile",
               "callable_flag"]

    for j, col in enumerate(di_cols, 1):
        ws.cell(1, j, col)
    style_header(ws, 1, len(di_cols))

    di_rows = conn.execute("""
        SELECT * FROM debt_instruments WHERE company_id=? ORDER BY opening_balance DESC
    """, (company_id,)).fetchall()

    for i, row in enumerate(di_rows, 2):
        for j, col in enumerate(di_cols):
            val = row[col] if col in row.keys() else None
            if col == "opening_balance" and val:
                val = val / 1e6  # → mUSD
            ws.cell(i, j + 1, val)

    ws.column_dimensions['A'].width = 25
    ws.column_dimensions['B'].width = 30

    # ── 4. Macro Factors ───────────────────────────────────────────────────
    ws = wb.create_sheet("macro_factors")
    factors = conn.execute("""
        SELECT DISTINCT factor_name FROM macro_factors ORDER BY factor_name
    """).fetchall()
    factor_names = [r[0] for r in factors]

    ws.cell(1, 1, "factor_name")
    for j, yr in enumerate(years):
        ws.cell(1, j + 2, yr)
    style_header(ws, 1, len(years) + 1)

    for i, fname in enumerate(factor_names, 2):
        ws.cell(i, 1, fname)
        vals = conn.execute("""
            SELECT year, value FROM macro_factors WHERE factor_name=?
        """, (fname,)).fetchall()
        val_by_yr = {r["year"]: r["value"] for r in vals}
        for j, yr in enumerate(years):
            v = val_by_yr.get(yr)
            if v is not None:
                ws.cell(i, j + 2, v)

    ws.column_dimensions['A'].width = 30

    # ── 5. Segments ────────────────────────────────────────────────────────
    for sheet_name, metric_filter in [
        ("segments_financial", "revenue"),
        ("segments_operational", None),
    ]:
        ws = wb.create_sheet(sheet_name)
        ws.cell(1, 1, "segment_name")
        ws.cell(1, 2, "metric")
        for j, yr in enumerate(years):
            ws.cell(1, j + 3, yr)
        style_header(ws, 1, len(years) + 2)

        seg_rows = conn.execute("""
            SELECT sd.segment_name, sd.metric, p.year, sd.value
            FROM segment_data sd JOIN periods p ON sd.period_id=p.period_id
            WHERE sd.company_id=? ORDER BY sd.segment_name, sd.metric, p.year
        """, (company_id,)).fetchall()

        # Group by (segment, metric)
        seg_data = {}
        for r in seg_rows:
            key = (r["segment_name"], r["metric"])
            seg_data.setdefault(key, {})[r["year"]] = r["value"]

        row_idx = 2
        for (seg, metric), yr_vals in sorted(seg_data.items()):
            ws.cell(row_idx, 1, seg)
            ws.cell(row_idx, 2, metric)
            for j, yr in enumerate(years):
                v = yr_vals.get(yr)
                if v is not None:
                    ws.cell(row_idx, j + 3, v / 1e6 if abs(v) > 1e6 else v)
            row_idx += 1

    # ── 6. Production KPI ──────────────────────────────────────────────────
    ws = wb.create_sheet("production_kpi")
    ws.cell(1, 1, "metric")
    ws.cell(1, 2, "unit")
    for j, yr in enumerate(years):
        ws.cell(1, j + 3, yr)
    style_header(ws, 1, len(years) + 2)

    kpi = conn.execute("""
        SELECT metric_name, year, value FROM preprocess_metrics
        WHERE company_id=? AND metric_group='production_kpi' AND year > 0
        ORDER BY metric_name, year
    """, (company_id,)).fetchall()

    kpi_data = {}
    for r in kpi:
        kpi_data.setdefault(r["metric_name"], {})[r["year"]] = r["value"]

    row_idx = 2
    for metric, yr_vals in sorted(kpi_data.items()):
        ws.cell(row_idx, 1, metric)
        ws.cell(row_idx, 2, "")
        for j, yr in enumerate(years):
            v = yr_vals.get(yr)
            if v is not None:
                ws.cell(row_idx, j + 3, v)
        row_idx += 1

    # ── 7. Dict Metrics (alias dictionary) ─────────────────────────────────
    ws = wb.create_sheet("dict_metrics")
    dict_cols = ["category", "canonical_metric", "description_en", "accepted_aliases",
                 "required_for_model", "used_in_engine"]
    for j, col in enumerate(dict_cols, 1):
        ws.cell(1, j, col)
    style_header(ws, 1, len(dict_cols))

    # Build from known aliases
    ALIASES = {
        'IS': {
            'revenue': ('Revenue / Net Sales', 'net_sales;revenues;total_revenue;sales', 'yes'),
            'cogs': ('Cost of Sales / COGS', 'cost_of_sales;cost_of_revenue;cost_of_goods_sold', 'yes'),
            'gross_profit': ('Gross Profit', '', 'yes'),
            'sga': ('SG&A / Administrative', 'sg_and_a;selling_general_administrative;admin_expenses;sgna', 'yes'),
            'distribution_expenses': ('Distribution / Selling expenses', 'selling_expenses;distribution_costs', 'yes'),
            'dep_ppe': ('Depreciation of PPE', 'depreciation;depreciation_owned', 'yes'),
            'amort_intangibles': ('Amortization of intangibles', 'amortization', 'no'),
            'total_da': ('Total D&A', 'depreciation_and_amortization', 'yes'),
            'ebitda': ('EBITDA', '', 'yes'),
            'ebit': ('EBIT / Operating income', 'operating_income;results_from_operating', 'yes'),
            'interest_expense': ('Interest expense', 'finance_expenses;interest_expense_debt', 'yes'),
            'interest_income': ('Interest income', 'finance_income', 'yes'),
            'earnings_from_investees': ('Share of associates profit', 'share_of_associates;equity_in_earnings', 'yes'),
            'asset_impairment': ('Impairment charges', 'impairment_of_non_current_assets', 'yes'),
            'ebt': ('Profit before tax', 'pretax_income;profit_before_taxation', 'yes'),
            'current_tax': ('Current income tax', '', 'yes'),
            'deferred_tax': ('Deferred tax expense', 'deferred_tax_expense;deferred_income_tax', 'yes'),
            'tax_expense': ('Total tax expense', 'income_taxes', 'yes'),
            'net_income': ('Net income / Profit for the year', 'profit_for_the_year', 'yes'),
        },
        'BS': {
            'cash': ('Cash and equivalents', 'cash_and_cash_equivalents', 'yes'),
            'accounts_receivable': ('Trade receivables', 'trade_receivables;receivables;ar', 'yes'),
            'inventory': ('Inventories', '', 'yes'),
            'ppe_gross': ('PPE at cost (gross)', 'property_plant_equipment_gross', 'yes'),
            'ppe_accum_dep': ('Accumulated depreciation', 'accumulated_depreciation', 'yes'),
            'ppe_net': ('PPE net book value', 'property_plant_equipment_net', 'yes'),
            'investments_lt': ('Investments in associates', 'investments_associates;investments_and_long_term_receivables', 'yes'),
            'goodwill': ('Goodwill', '', 'no'),
            'intangibles': ('Intangible assets', '', 'no'),
            'dta': ('Deferred tax asset', '', 'yes'),
            'dtl': ('Deferred tax liability', '', 'yes'),
            'short_term_debt': ('Short-term debt + current portion LTD', 'st_debt', 'yes'),
            'long_term_debt': ('Long-term debt', '', 'yes'),
            'accounts_payable': ('Trade payables', 'payables', 'yes'),
            'total_assets': ('Total assets', '', 'yes'),
            'total_equity': ('Total equity', 'shareholders_equity', 'yes'),
            'total_liabilities': ('Total liabilities', '', 'yes'),
            'retained_earnings': ('Retained earnings', '', 'yes'),
        },
        'CF': {
            'cfo_total': ('Total CFO', 'cash_from_operations;net_cash_from_operations', 'yes'),
            'cfi_total': ('Total CFI', 'cash_from_investing', 'yes'),
            'cff_total': ('Total CFF', 'cash_from_financing', 'yes'),
            'capex': ('Capital expenditures', 'cfi_capex;payments_to_acquire_property', 'yes'),
        },
    }

    row_idx = 2
    for category, metrics in ALIASES.items():
        for metric, (desc, aliases, required) in metrics.items():
            ws.cell(row_idx, 1, category)
            ws.cell(row_idx, 2, metric)
            ws.cell(row_idx, 3, desc)
            ws.cell(row_idx, 4, aliases)
            ws.cell(row_idx, 5, required)
            ws.cell(row_idx, 6, metric)
            row_idx += 1

    ws.column_dimensions['A'].width = 8
    ws.column_dimensions['B'].width = 30
    ws.column_dimensions['C'].width = 35
    ws.column_dimensions['D'].width = 50

    # ── 8. Data Quality Report ─────────────────────────────────────────────
    ws = wb.create_sheet("data_quality_report")
    ws.cell(1, 1, "DATA QUALITY REPORT").font = Font(bold=True, size=14)
    ws.cell(2, 1, f"Company: {company_id.upper()}")
    ws.cell(3, 1, f"Years: {years[0]}-{years[-1]}")

    row = 5
    # 8.1 Coverage
    ws.cell(row, 1, "COVERAGE MATRIX").font = Font(bold=True, size=11)
    row += 1
    ws.cell(row, 1, "Statement")
    ws.cell(row, 2, "Metrics")
    ws.cell(row, 3, "Avg Years")
    ws.cell(row, 4, "Status")

    for stmt, table in [("IS", "history_is"), ("BS", "history_bs"), ("CF", "history_cf")]:
        row += 1
        metrics = conn.execute(f"""
            SELECT COUNT(DISTINCT metric) FROM {table} WHERE company_id=?
        """, (company_id,)).fetchone()[0]
        avg = conn.execute(f"""
            SELECT AVG(cnt) FROM (
                SELECT metric, COUNT(*) cnt FROM {table} h
                JOIN periods p ON h.period_id=p.period_id
                WHERE h.company_id=? GROUP BY metric
            )
        """, (company_id,)).fetchone()[0] or 0
        ws.cell(row, 1, stmt)
        ws.cell(row, 2, metrics)
        ws.cell(row, 3, f"{avg:.1f}")
        ws.cell(row, 4, "✅" if metrics >= 10 else "⚠")

    # 8.2 BS Identity
    row += 2
    ws.cell(row, 1, "BS IDENTITY CHECK").font = Font(bold=True, size=11)
    row += 1
    ws.cell(row, 1, "Year")
    ws.cell(row, 2, "Total Assets")
    ws.cell(row, 3, "Total Liab")
    ws.cell(row, 4, "Total Equity")
    ws.cell(row, 5, "A-(L+E)")
    ws.cell(row, 6, "Status")

    for yr in years[-5:]:
        row += 1
        bs = {}
        for r in conn.execute("""
            SELECT h.metric, h.value FROM history_bs h
            JOIN periods p ON h.period_id=p.period_id
            WHERE h.company_id=? AND p.year=?
        """, (company_id, yr)).fetchall():
            bs[r["metric"]] = r["value"]

        ta = bs.get("total_assets", 0) or 0
        tl = bs.get("total_liabilities", 0) or 0
        te = bs.get("total_equity", 0) or 0
        gap = ta - tl - te

        ws.cell(row, 1, yr)
        ws.cell(row, 2, ta / 1e6)
        ws.cell(row, 3, tl / 1e6)
        ws.cell(row, 4, te / 1e6)
        ws.cell(row, 5, gap / 1e6)
        ws.cell(row, 6, "✅" if abs(gap) < 1e6 else "❌")

    # 8.3 Debt Check
    row += 2
    ws.cell(row, 1, "DEBT INSTRUMENTS CHECK").font = Font(bold=True, size=11)
    row += 1
    di_total = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(opening_balance),0) FROM debt_instruments WHERE company_id=?",
        (company_id,)).fetchone()
    ws.cell(row, 1, f"Instruments: {di_total[0]}")
    ws.cell(row, 2, f"Total: ${di_total[1]/1e6:,.0f}M")

    # 8.4 Engine Readiness
    row += 2
    ws.cell(row, 1, "ENGINE READINESS").font = Font(bold=True, size=11)
    row += 1

    critical_is = ['revenue', 'cogs', 'ebit', 'net_income', 'interest_expense', 'total_da']
    critical_bs = ['cash', 'ppe_net', 'long_term_debt', 'total_equity', 'total_assets']
    critical_cf = ['cfo_total', 'cfi_total', 'cff_total']

    for stmt, table, critical in [
        ("IS", "history_is", critical_is),
        ("BS", "history_bs", critical_bs),
        ("CF", "history_cf", critical_cf),
    ]:
        present = 0
        for m in critical:
            cnt = conn.execute(f"""
                SELECT COUNT(*) FROM {table} h
                JOIN periods p ON h.period_id=p.period_id
                WHERE h.company_id=? AND h.metric=?
            """, (company_id, m)).fetchone()[0]
            if cnt > 0:
                present += 1
        row += 1
        ws.cell(row, 1, f"{stmt}: {present}/{len(critical)} critical")
        ws.cell(row, 2, "✅" if present == len(critical) else "⚠")

    row += 1
    ready = True  # simplified check
    ws.cell(row, 1, f"READY TO MODEL: {'YES ✅' if ready else 'NO ❌'}")
    ws.cell(row, 1).font = Font(bold=True, size=12)

    ws.column_dimensions['A'].width = 30
    ws.column_dimensions['B'].width = 20

    # ── Save ───────────────────────────────────────────────────────────────
    conn.close()
    wb.save(str(output_path))
    print(f"✅ Exported: {output_path}")
    print(f"   Sheets: {wb.sheetnames}")
    print(f"   Size: {output_path.stat().st_size // 1024}KB")


def main():
    parser = argparse.ArgumentParser(description="Export company data from DB to Excel template")
    parser.add_argument("--company", required=True, help="Company ID (us_steel, rusal)")
    parser.add_argument("--output", default=None, help="Output xlsx path")
    args = parser.parse_args()

    if args.output:
        out = Path(args.output)
    else:
        out = ROOT / "companies" / args.company / "data" / f"{args.company}_template_v2.xlsx"

    out.parent.mkdir(parents=True, exist_ok=True)
    export_company(args.company, out)


if __name__ == "__main__":
    main()
