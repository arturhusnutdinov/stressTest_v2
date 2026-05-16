#!/usr/bin/env python3
"""Load schedule/Notes sheets from Excel into DB tables.

Handles: Intangibles, Tax, Provisions, Associates, Operational Drivers.
PPE and debt are loaded by ExcelLoader natively.

Usage:
    python3 tools/load_schedule_sheets.py --company rusal
    python3 tools/load_schedule_sheets.py --company rusal --dry-run
    python3 tools/load_schedule_sheets.py --company rusal --db tests/integration/test_data_mart.db
"""
from __future__ import annotations
import argparse, sqlite3, sys
from pathlib import Path
import pandas as pd

DEFAULT_DB = 'data_mart_v2.db'
DEFAULT_EXCEL = 'companies/rusal/data/rusal_complete_v4.xlsx'


def get_period_map(conn, company_id):
    return {yr: pid for pid, yr in conn.execute(
        "SELECT period_id, year FROM periods WHERE company_id=?", (company_id,))}


def load_intangibles(conn, df, company_id, period_map, dry_run):
    """Intangibles_Schedule → intangible_assets"""
    n = 0
    for _, row in df.iterrows():
        yr = int(row.get('year', 0))
        pid = period_map.get(yr)
        if not pid: continue
        cat = str(row.get('category', '')).strip()
        gross = row.get('gross_mUSD')
        accum = row.get('accum_amort_mUSD')
        net = row.get('net_mUSD')
        if not cat: continue
        if not dry_run:
            conn.execute(
                "INSERT OR REPLACE INTO intangible_assets "
                "(company_id, period_id, category, gross_amount, accumulated_amortization, "
                "net_amount, source, updated_at) VALUES (?,?,?,?,?,?,'excel_schedule',datetime('now'))",
                (company_id, pid, cat,
                 gross * 1e6 if pd.notna(gross) else None,
                 accum * 1e6 if pd.notna(accum) else None,
                 net * 1e6 if pd.notna(net) else None))
        n += 1
    return n


def load_tax(conn, df, company_id, period_map, dry_run):
    """Tax_Schedule → tax_schedule"""
    n = 0
    for _, row in df.iterrows():
        yr = int(row.get('year', 0))
        pid = period_map.get(yr)
        if not pid: continue
        if not dry_run:
            conn.execute(
                "INSERT OR REPLACE INTO tax_schedule "
                "(company_id, period_id, dta_open, dta_close, dtl_open, dtl_close, "
                "source, updated_at) VALUES (?,?,?,?,?,?,'excel_schedule',datetime('now'))",
                (company_id, pid,
                 row.get('dta_open'), row.get('dta_close'),
                 row.get('dtl_open'), row.get('dtl_close')))
        n += 1
    return n


def load_provisions(conn, df, company_id, period_map, dry_run):
    """Provisions_Detail → provisions_schedule"""
    n = 0
    for _, row in df.iterrows():
        yr = int(row.get('year', 0))
        pid = period_map.get(yr)
        if not pid: continue
        cat = str(row.get('category', '')).strip()
        closing = row.get('closing_mUSD')
        if not cat or pd.isna(closing): continue
        if not dry_run:
            conn.execute(
                "INSERT OR REPLACE INTO provisions_schedule "
                "(company_id, period_id, category, closing, source, updated_at) "
                "VALUES (?,?,?,?,'excel_schedule',datetime('now'))",
                (company_id, pid, cat, closing * 1e6))
        n += 1
    return n


def load_associates(conn, df, company_id, period_map, dry_run):
    """Associates_Detail → associates_schedule"""
    n = 0
    for _, row in df.iterrows():
        yr = int(row.get('year', 0))
        pid = period_map.get(yr)
        if not pid: continue
        cat = str(row.get('category', '')).strip()
        mv = str(row.get('movement', '')).strip()
        val = row.get('value_mUSD')
        if not cat or not mv or pd.isna(val): continue
        if not dry_run:
            conn.execute(
                "INSERT OR REPLACE INTO associates_schedule "
                "(company_id, period_id, category, movement, value, source) "
                "VALUES (?,?,?,?,?,'excel_schedule')",
                (company_id, pid, cat, mv, val * 1e6))
        n += 1
    return n


def load_operational(conn, df, company_id, dry_run):
    """Operational_Drivers → operational_drivers (uses company, not company_id)"""
    n = 0
    for _, row in df.iterrows():
        metric = str(row.get('metric', '')).strip()
        yr = int(row.get('year', 0))
        val = row.get('value')
        if not metric or pd.isna(val): continue
        if not dry_run:
            conn.execute(
                "INSERT OR REPLACE INTO operational_drivers "
                "(company, metric, year, value, source) VALUES (?,?,?,?,'excel_schedule')",
                (company_id, metric, yr, val))
        n += 1
    return n


SHEET_HANDLERS = {
    'Intangibles_Schedule': load_intangibles,
    'Tax_Schedule': load_tax,
    'Provisions_Detail': load_provisions,
    'Associates_Detail': load_associates,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--company', default='rusal')
    ap.add_argument('--excel', default=DEFAULT_EXCEL)
    ap.add_argument('--db', default=DEFAULT_DB)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    excel = Path(args.excel)
    db = Path(args.db)
    dry_run = args.dry_run

    print(f'Schedule Loader {"[DRY RUN]" if dry_run else "[LIVE]"}')
    print(f'  Excel: {excel.name}')
    print(f'  DB: {db}')
    print(f'  Company: {args.company}\n')

    xl = pd.ExcelFile(excel)
    conn = sqlite3.connect(db)
    period_map = get_period_map(conn, args.company)

    total = 0
    for sheet, handler in SHEET_HANDLERS.items():
        if sheet not in xl.sheet_names:
            print(f'  {sheet}: not in Excel — skip')
            continue
        df = pd.read_excel(excel, sheet_name=sheet, header=1)
        df = df.dropna(how='all')
        n = handler(conn, df, args.company, period_map, dry_run)
        total += n
        print(f'  {sheet}: {n} rows {"would load" if dry_run else "loaded"}')

    # Operational (different: uses 'company' not 'company_id')
    if 'Operational_Drivers' in xl.sheet_names:
        df = pd.read_excel(excel, sheet_name='Operational_Drivers', header=1)
        df = df.dropna(how='all')
        n = load_operational(conn, df, args.company, dry_run)
        total += n
        print(f'  Operational_Drivers: {n} rows {"would load" if dry_run else "loaded"}')

    if not dry_run:
        conn.commit()
    conn.close()

    print(f'\nTotal: {total} rows')
    return 0


if __name__ == '__main__':
    sys.exit(main())
