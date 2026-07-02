#!/usr/bin/env python3
"""Load schedule/Notes sheets from Excel into DB tables.

Handles: Intangibles, Tax, Provisions, Associates, Operational Drivers,
         Equity, Leases, WC Corkscrew, Interest Split, Tax Corkscrew.
PPE and debt are loaded by ExcelLoader natively.

Usage:
    python3 tools/load_schedule_sheets.py --company rusal
    python3 tools/load_schedule_sheets.py --company rusal --dry-run
    python3 tools/load_schedule_sheets.py --company nornickel --excel companies/nornickel/data/excel/nornickel_unified.xlsx
"""
from __future__ import annotations
import argparse, sqlite3, sys
from pathlib import Path
import pandas as pd

DEFAULT_DB = 'data_mart_v2.db'


def _find_excel(company_id: str) -> str:
    """Auto-detect unified Excel file for a company."""
    candidates = [
        f'companies/{company_id}/data/excel/{company_id}_unified.xlsx',
        f'companies/{company_id}/data/{company_id}_unified.xlsx',
        f'companies/{company_id}/data/excel/{company_id}_input.xlsx',
        f'companies/{company_id}/data/{company_id}_complete_v4.xlsx',
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return candidates[0]


def get_period_map(conn, company_id):
    return {yr: pid for pid, yr in conn.execute(
        "SELECT period_id, year FROM periods WHERE company_id=?", (company_id,))}


# ── mUSD suffix columns → multiply by 1e6 ──────────────────────────────

def _val(row, col, scale=True):
    """Get value from row, optionally scale mUSD→USD (×1e6)."""
    v = row.get(col)
    if pd.isna(v) or v is None:
        return None
    if scale:
        return float(v) * 1e6
    return float(v)


# ── Handlers ────────────────────────────────────────────────────────────

def load_intangibles(conn, df, company_id, period_map, dry_run):
    """intangible_assets sheet → intangible_assets table"""
    n = 0
    for _, row in df.iterrows():
        yr = int(row.get('year', 0))
        pid = period_map.get(yr)
        if not pid:
            continue
        cat = str(row.get('category', '')).strip()
        if not cat:
            continue
        gross = _val(row, 'gross_amount_mUSD') or _val(row, 'gross_mUSD')
        accum = _val(row, 'accumulated_amortization_mUSD') or _val(row, 'accum_amort_mUSD')
        net = _val(row, 'net_amount_mUSD') or _val(row, 'net_mUSD')
        ul = row.get('useful_life')
        if not dry_run:
            conn.execute(
                "INSERT OR REPLACE INTO intangible_assets "
                "(company_id, period_id, category, gross_amount, accumulated_amortization, "
                "net_amount, useful_life, source, updated_at) "
                "VALUES (?,?,?,?,?,?,?,'excel_schedule',datetime('now'))",
                (company_id, pid, cat, gross, accum, net,
                 str(ul) if pd.notna(ul) else None))
        n += 1
    return n


def load_tax(conn, df, company_id, period_map, dry_run):
    """schedule_tax sheet → tax_schedule table"""
    n = 0
    for _, row in df.iterrows():
        yr = int(row.get('year', 0))
        pid = period_map.get(yr)
        if not pid:
            continue
        if not dry_run:
            conn.execute(
                "INSERT OR REPLACE INTO tax_schedule "
                "(company_id, period_id, ebt, current_tax, deferred_tax, effective_rate, "
                "dta_open, dta_additions, dta_used, dta_close, "
                "dtl_open, dtl_additions, dtl_reversal, dtl_close, "
                "nol_open, nol_additions, nol_used, nol_close, "
                "source, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'excel_schedule',datetime('now'))",
                (company_id, pid,
                 _val(row, 'ebt_mUSD'),
                 _val(row, 'current_tax_mUSD'),
                 _val(row, 'deferred_tax_mUSD'),
                 _val(row, 'effective_rate', scale=False),
                 _val(row, 'dta_open_mUSD') or _val(row, 'dta_open'),
                 _val(row, 'dta_additions_mUSD'),
                 _val(row, 'dta_used_mUSD'),
                 _val(row, 'dta_close_mUSD') or _val(row, 'dta_close'),
                 _val(row, 'dtl_open_mUSD') or _val(row, 'dtl_open'),
                 _val(row, 'dtl_additions_mUSD'),
                 _val(row, 'dtl_reversal_mUSD'),
                 _val(row, 'dtl_close_mUSD') or _val(row, 'dtl_close'),
                 _val(row, 'nol_open_mUSD'),
                 _val(row, 'nol_additions_mUSD'),
                 _val(row, 'nol_used_mUSD'),
                 _val(row, 'nol_close_mUSD')))
        n += 1
    return n


def load_provisions(conn, df, company_id, period_map, dry_run):
    """provisions sheet → provisions_schedule table"""
    n = 0
    for _, row in df.iterrows():
        yr = int(row.get('year', 0))
        pid = period_map.get(yr)
        if not pid:
            continue
        cat = str(row.get('category', '')).strip()
        closing = _val(row, 'closing_mUSD')
        if not cat or closing is None:
            continue
        if not dry_run:
            conn.execute(
                "INSERT OR REPLACE INTO provisions_schedule "
                "(company_id, period_id, category, closing, source, updated_at) "
                "VALUES (?,?,?,?,'excel_schedule',datetime('now'))",
                (company_id, pid, cat, closing))
        n += 1
    return n


def load_associates(conn, df, company_id, period_map, dry_run):
    """associates sheet → associates_schedule table"""
    n = 0
    for _, row in df.iterrows():
        yr = int(row.get('year', 0))
        pid = period_map.get(yr)
        if not pid:
            continue
        cat = str(row.get('category', '')).strip()
        mv = str(row.get('movement', '')).strip()
        val = _val(row, 'value_mUSD')
        if not cat or not mv or val is None:
            continue
        if not dry_run:
            conn.execute(
                "INSERT OR REPLACE INTO associates_schedule "
                "(company_id, period_id, category, movement, value, source, updated_at) "
                "VALUES (?,?,?,?,?,'excel_schedule',datetime('now'))",
                (company_id, pid, cat, mv, val))
        n += 1
    return n


def load_operational(conn, df, company_id, dry_run):
    """operational_drivers (wide format: driver, unit, year1, year2, ...) → operational_drivers table"""
    n = 0
    # Detect format: wide (driver, unit, 2011, 2012, ...) vs long (metric, year, value)
    cols = [str(c) for c in df.columns]
    if 'year' in cols and 'value' in cols:
        # Long format
        for _, row in df.iterrows():
            metric = str(row.get('metric', row.get('driver', ''))).strip()
            yr = int(row.get('year', 0))
            val = row.get('value')
            unit = row.get('unit')
            if not metric or pd.isna(val):
                continue
            if not dry_run:
                conn.execute(
                    "INSERT OR REPLACE INTO operational_drivers "
                    "(company_id, metric, year, value, unit, source, updated_at) "
                    "VALUES (?,?,?,?,?,'excel_schedule',datetime('now'))",
                    (company_id, metric, yr, float(val),
                     str(unit) if pd.notna(unit) else None))
            n += 1
    else:
        # Wide format: driver | unit | 2011 | 2012 | ...
        year_cols = [c for c in df.columns if isinstance(c, (int, float)) or
                     (isinstance(c, str) and c.isdigit())]
        for _, row in df.iterrows():
            driver = str(row.get('driver', row.get('metric', ''))).strip()
            unit = row.get('unit')
            if not driver:
                continue
            for yc in year_cols:
                yr = int(yc)
                val = row.get(yc)
                if pd.isna(val) or val is None:
                    continue
                if not dry_run:
                    conn.execute(
                        "INSERT OR REPLACE INTO operational_drivers "
                        "(company_id, metric, year, value, unit, source, updated_at) "
                        "VALUES (?,?,?,?,?,'excel_schedule',datetime('now'))",
                        (company_id, driver, yr, float(val),
                         str(unit) if pd.notna(unit) else None))
                n += 1
    return n


def load_equity(conn, df, company_id, period_map, dry_run):
    """schedule_equity sheet → equity_schedule table"""
    n = 0
    for _, row in df.iterrows():
        yr = int(row.get('year', 0))
        pid = period_map.get(yr)
        if not pid:
            continue
        if not dry_run:
            conn.execute(
                "INSERT OR REPLACE INTO equity_schedule "
                "(company_id, period_id, re_open, net_income, dividends, buybacks, "
                "issuance, other_equity_changes, re_close, source, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,'excel_schedule',datetime('now'))",
                (company_id, pid,
                 _val(row, 're_open_mUSD'),
                 _val(row, 'net_income_mUSD'),
                 _val(row, 'dividends_mUSD'),
                 _val(row, 'buybacks_mUSD'),
                 _val(row, 'issuance_mUSD'),
                 _val(row, 'other_equity_changes_mUSD'),
                 _val(row, 're_close_mUSD')))
        n += 1
    return n


def load_leases(conn, df, company_id, period_map, dry_run):
    """schedule_leases sheet → lease_schedule table"""
    n = 0
    for _, row in df.iterrows():
        yr = int(row.get('year', 0))
        pid = period_map.get(yr)
        if not pid:
            continue
        lid = str(row.get('lease_id', '')).strip()
        lt = str(row.get('lease_type', '')).strip()
        if not lid or not lt:
            continue
        if not dry_run:
            conn.execute(
                "INSERT OR REPLACE INTO lease_schedule "
                "(company_id, period_id, lease_id, lease_name, lease_type, "
                "rou_open, rou_dep, rou_close, liab_open, interest_exp, payment, "
                "liab_close, discount_rate, source, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'excel_schedule',datetime('now'))",
                (company_id, pid, lid,
                 row.get('lease_name'),
                 lt,
                 _val(row, 'rou_open_mUSD'),
                 _val(row, 'rou_dep_mUSD'),
                 _val(row, 'rou_close_mUSD'),
                 _val(row, 'liab_open_mUSD'),
                 _val(row, 'interest_exp_mUSD'),
                 _val(row, 'payment_mUSD'),
                 _val(row, 'liab_close_mUSD'),
                 _val(row, 'discount_rate', scale=False)))
        n += 1
    return n


def load_wc_corkscrew(conn, df, company_id, period_map, dry_run):
    """schedule_working_capital / sched_wc_corkscrew → sched_wc_corkscrew table"""
    n = 0
    for _, row in df.iterrows():
        yr = int(row.get('year', 0))
        pid = period_map.get(yr)
        if not pid:
            continue
        comp = str(row.get('component', '')).strip()
        if not comp:
            continue
        if not dry_run:
            conn.execute(
                "INSERT OR REPLACE INTO sched_wc_corkscrew "
                "(company_id, period_id, component, opening_balance, closing_balance, "
                "delta, driver_value, driver_metric, source, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,'excel_schedule',datetime('now'))",
                (company_id, pid, comp,
                 _val(row, 'opening_balance_mUSD'),
                 _val(row, 'closing_balance_mUSD'),
                 _val(row, 'delta_mUSD'),
                 _val(row, 'driver_value', scale=False),
                 row.get('driver_metric')))
        n += 1
    return n


def load_interest_split(conn, df, company_id, period_map, dry_run):
    """interest_paid_split / schedule_interest → interest_paid_split table"""
    n = 0
    for _, row in df.iterrows():
        yr = int(row.get('year', 0))
        pid = period_map.get(yr)
        if not pid:
            continue
        if not dry_run:
            conn.execute(
                "INSERT OR REPLACE INTO interest_paid_split "
                "(company_id, period_id, interest_paid_debt, interest_paid_leases, "
                "interest_paid_total, interest_payable_debt_open, interest_payable_debt_close, "
                "interest_payable_leases_open, interest_payable_leases_close, "
                "change_debt, change_leases, source, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,'excel_schedule',datetime('now'))",
                (company_id, pid,
                 _val(row, 'interest_paid_debt_mUSD'),
                 _val(row, 'interest_paid_leases_mUSD'),
                 _val(row, 'interest_paid_total_mUSD'),
                 _val(row, 'interest_payable_debt_open_mUSD'),
                 _val(row, 'interest_payable_debt_close_mUSD'),
                 _val(row, 'interest_payable_leases_open_mUSD'),
                 _val(row, 'interest_payable_leases_close_mUSD'),
                 _val(row, 'change_debt_mUSD'),
                 _val(row, 'change_leases_mUSD')))
        n += 1
    return n


def load_tax_corkscrew(conn, df, company_id, period_map, dry_run):
    """sched_tax_corkscrew → sched_tax_corkscrew table"""
    n = 0
    for _, row in df.iterrows():
        yr = int(row.get('year', 0))
        pid = period_map.get(yr)
        if not pid:
            continue
        tdt = str(row.get('temp_diff_type', '')).strip()
        if not tdt:
            continue
        if not dry_run:
            conn.execute(
                "INSERT OR REPLACE INTO sched_tax_corkscrew "
                "(company_id, period_id, temp_diff_type, "
                "dta_opening, dta_created, dta_utilized, dta_closing, "
                "dtl_opening, dtl_created, dtl_reversed, dtl_closing, "
                "source, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,'excel_schedule',datetime('now'))",
                (company_id, pid, tdt,
                 _val(row, 'dta_opening_mUSD'),
                 _val(row, 'dta_created_mUSD'),
                 _val(row, 'dta_utilized_mUSD'),
                 _val(row, 'dta_closing_mUSD'),
                 _val(row, 'dtl_opening_mUSD'),
                 _val(row, 'dtl_created_mUSD'),
                 _val(row, 'dtl_reversed_mUSD'),
                 _val(row, 'dtl_closing_mUSD')))
        n += 1
    return n


# ── Sheet → Handler mapping ────────────────────────────────────────────

# Sheets that need period_map (year → period_id)
PERIOD_HANDLERS = {
    # New template names
    'intangible_assets':          load_intangibles,
    'schedule_tax':               load_tax,
    'provisions':                 load_provisions,
    'associates':                 load_associates,
    'schedule_equity':            load_equity,
    'schedule_leases':            load_leases,
    'schedule_working_capital':   load_wc_corkscrew,
    'schedule_interest':          load_interest_split,
    'interest_paid_split':        load_interest_split,
    'sched_tax_corkscrew':        load_tax_corkscrew,
    'sched_wc_corkscrew':         load_wc_corkscrew,
    # Legacy names (backward compat)
    'Intangibles_Schedule':       load_intangibles,
    'Tax_Schedule':               load_tax,
    'Provisions_Detail':          load_provisions,
    'Associates_Detail':          load_associates,
    'Tax_DTA_DTL':                load_tax,
    'Lease_Schedule':             load_leases,
    'Equity_Schedule':            load_equity,
}

# Sheets without period_map
DIRECT_HANDLERS = {
    'operational_drivers':        load_operational,
    'Operational_Drivers':        load_operational,
}


def main():
    ap = argparse.ArgumentParser(description="Load schedule sheets from Excel into DB")
    ap.add_argument('--company', required=True, help="Company ID")
    ap.add_argument('--excel', default=None, help="Path to Excel file (auto-detect if omitted)")
    ap.add_argument('--db', default=DEFAULT_DB, help="Path to SQLite DB")
    ap.add_argument('--dry-run', action='store_true', help="Don't write to DB")
    args = ap.parse_args()

    excel = Path(args.excel) if args.excel else Path(_find_excel(args.company))
    db = Path(args.db)
    dry_run = args.dry_run

    if not excel.exists():
        print(f'ERROR: Excel file not found: {excel}')
        return 1

    print(f'Schedule Loader {"[DRY RUN]" if dry_run else "[LIVE]"}')
    print(f'  Excel: {excel}')
    print(f'  DB:    {db}')
    print(f'  Company: {args.company}\n')

    xl = pd.ExcelFile(excel)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    period_map = get_period_map(conn, args.company)

    if not period_map:
        print(f'WARNING: No periods found for company "{args.company}" — '
              f'load history first (history_is/bs/cf)')

    total = 0

    # Period-based handlers
    for sheet, handler in PERIOD_HANDLERS.items():
        if sheet not in xl.sheet_names:
            continue
        df = pd.read_excel(excel, sheet_name=sheet)
        df = df.dropna(how='all')
        if df.empty:
            print(f'  {sheet}: empty — skip')
            continue
        n = handler(conn, df, args.company, period_map, dry_run)
        total += n
        print(f'  {sheet}: {n} rows {"would load" if dry_run else "loaded"}')

    # Direct handlers (no period_map)
    for sheet, handler in DIRECT_HANDLERS.items():
        if sheet not in xl.sheet_names:
            continue
        df = pd.read_excel(excel, sheet_name=sheet)
        df = df.dropna(how='all')
        if df.empty:
            print(f'  {sheet}: empty — skip')
            continue
        n = handler(conn, df, args.company, dry_run)
        total += n
        print(f'  {sheet}: {n} rows {"would load" if dry_run else "loaded"}')

    if not dry_run:
        conn.commit()
    conn.close()

    print(f'\nTotal: {total} rows')
    return 0


if __name__ == '__main__':
    sys.exit(main())
