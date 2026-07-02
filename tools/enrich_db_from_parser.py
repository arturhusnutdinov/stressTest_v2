#!/usr/bin/env python3
"""Phase 4d: Enrich data_mart_v2.db from PDF parser output.

Principle: INSERT only (no overwrite of existing values).
Parser returns mUSD; DB stores full USD — multiply by 1e6.

Usage:
    python tools/enrich_db_from_parser.py --dry-run
    python tools/enrich_db_from_parser.py
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parsers.pdf_parser import PDFParser

DEFAULT_PDF = None  # must be provided via --pdf argument
ADAPTER = Path('parsers/adapters/rusal.yaml')
DB_PATH = 'data_mart_v2.db'
COMPANY = 'rusal'
TOLERANCE = 0.02
MUSD_TO_USD = 1e6

# Globals set by main()
PDF_PATH = None
TARGET_YEAR = 2024


def get_period_id(conn, company_id, year):
    row = conn.execute(
        "SELECT period_id FROM periods WHERE company_id=? AND year=?",
        (company_id, year)).fetchone()
    return row[0] if row else None


def get_db_value(conn, table, company_id, period_id, metric):
    row = conn.execute(
        f"SELECT value FROM {table} WHERE company_id=? AND period_id=? AND metric=?",
        (company_id, period_id, metric)).fetchone()
    return row[0] if row else None


def enrich_debt_instruments(conn, clause_col, clause_val, dry_run=False):
    """Parse Note 19 and INSERT new loan instruments into debt_instruments."""
    pdf_parser = PDFParser(ADAPTER)
    result = pdf_parser.parse_instrument_list(PDF_PATH, 'NOTE_19_DEBT_LOANS')

    print(f'Parsed: {len(result.instruments)} instruments, '
          f'schedule_year={result.schedule_year}')

    # Ensure required columns exist
    existing_cols = [r[1] for r in conn.execute('PRAGMA table_info(debt_instruments)')]
    new_cols = [
        ('schedule_year', 'INTEGER'), ('instrument_class', 'TEXT'),
        ('rate_description', 'TEXT'), ('total', 'REAL'),
        ('yr1', 'REAL'), ('yr2', 'REAL'), ('yr3', 'REAL'),
        ('yr4', 'REAL'), ('yr5', 'REAL'), ('yr6_plus', 'REAL'),
    ]
    for col_name, col_type in new_cols:
        if col_name not in existing_cols:
            conn.execute(f'ALTER TABLE debt_instruments ADD COLUMN {col_name} {col_type}')
            print(f'  + Column: {col_name} {col_type}')

    inserted = skipped = 0
    for inst in result.instruments:
        sched_year = inst.get('schedule_year')
        inst_class = inst.get('instrument_class')
        rate_tp = inst.get('rate_type')
        rate_desc = inst.get('rate_description', '')

        if not inst_class or not rate_tp:
            continue

        existing = conn.execute(
            f"SELECT COUNT(*) FROM debt_instruments WHERE "
            f"{clause_col}=? AND schedule_year=? AND instrument_class=? "
            f"AND rate_type=? AND rate_description=?",
            (clause_val, sched_year, inst_class, rate_tp, rate_desc)
        ).fetchone()[0]

        if existing > 0:
            skipped += 1
            continue

        # Generate required fields
        import re as _re
        inst_id = 'pdf_' + _re.sub(r'[^a-z0-9]+', '_',
                          f'{inst_class}_{rate_desc}'.lower()).strip('_') + f'_{sched_year}'
        inst_name = rate_desc
        # Derive currency from description
        ccy = 'USD'
        if 'RUB' in rate_desc or 'KeyRate' in rate_desc:
            ccy = 'RUB'
        elif 'CNY' in rate_desc or 'LPR' in rate_desc:
            ccy = 'CNY'
        elif 'EUR' in rate_desc or 'Euribor' in rate_desc:
            ccy = 'EUR'
        elif 'KZT' in rate_desc:
            ccy = 'KZT'

        if not dry_run:
            conn.execute(
                f"INSERT INTO debt_instruments "
                f"(instrument_id, {clause_col}, instrument_name, db_type, currency, "
                f"rate_type, schedule_year, instrument_class, "
                f"rate_description, total, yr1, yr2, yr3, yr4, yr5, "
                f"yr6_plus, source, updated_at) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                f"'pdf_parser', datetime('now'))",
                (inst_id, clause_val, inst_name, inst_class or 'loan', ccy,
                 rate_tp, sched_year, inst_class, rate_desc,
                 inst.get('total', 0), inst.get('yr1', 0), inst.get('yr2', 0),
                 inst.get('yr3', 0), inst.get('yr4', 0), inst.get('yr5', 0),
                 inst.get('yr6_plus', 0)))
        inserted += 1
        print(f'  {"would" if dry_run else "INSERT"}: [{sched_year}] [{inst_class}] '
              f'{rate_desc[:35]:35} total={inst.get("total", 0):>8,.0f}')

    print(f'\nDebt instruments: inserted={inserted}, skipped={skipped}')
    return inserted


def main():
    global PDF_PATH, TARGET_YEAR

    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--pdf', type=str, required=True,
                    help='Path to PDF financial statement (required)')
    args = ap.parse_args()
    dry_run = args.dry_run

    PDF_PATH = Path(args.pdf)
    if not PDF_PATH.exists():
        print(f'ERROR: PDF not found: {PDF_PATH}')
        return 1

    # Auto-detect target year from filename
    import re as _re
    yr_match = _re.search(r'(20\d{2})', PDF_PATH.stem)
    if yr_match:
        TARGET_YEAR = int(yr_match.group(1))

    print(f'Phase 4d Enrich {"[DRY RUN]" if dry_run else "[LIVE]"}')
    print(f'PDF: {PDF_PATH.name}, Year: {TARGET_YEAR}')
    print(f'DB:  {DB_PATH}, Company: {COMPANY}\n')

    # Parse all sections
    pdf_parser = PDFParser(ADAPTER)

    sections = {
        'IS': pdf_parser.parse_section(PDF_PATH, 'IS'),
        'BS': pdf_parser.parse_section(PDF_PATH, 'BS'),
        'CF': pdf_parser.parse_section(PDF_PATH, 'CF'),
        'NOTE_16': pdf_parser.parse_section(PDF_PATH, 'NOTE_16_INVENTORY'),
    }
    for name, res in sections.items():
        print(f'  {name}: {len(res.metrics)} metrics, page {res.page_used}')

    res_ppe = pdf_parser.parse_pivot_note(PDF_PATH, 'NOTE_13_PPE')
    print(f'  PPE: blocks={list(res_ppe.data.keys())}, page {res_ppe.page_used}')
    print()

    # Connect
    conn = sqlite3.connect(DB_PATH)
    period_id = get_period_id(conn, COMPANY, TARGET_YEAR)
    if period_id is None:
        print(f'ERROR: no period_id for {COMPANY}/{TARGET_YEAR}')
        return 1
    print(f'Period ID for {TARGET_YEAR}: {period_id}')

    stats = {'matched': 0, 'inserted': 0, 'mismatch': 0, 'skipped': 0}
    mismatches = []

    # Map sections to DB tables
    TABLE_MAP = [
        ('IS', 'history_is', sections['IS'].metrics),
        ('BS', 'history_bs', sections['BS'].metrics),
        ('CF', 'history_cf', sections['CF'].metrics),
        ('NOTE_16', 'history_bs', sections['NOTE_16'].metrics),
    ]

    for sec_label, table, parsed in TABLE_MAP:
        print(f'\n--- {sec_label} -> {table} ---')
        for canonical, year_vals in sorted(parsed.items()):
            # Process ALL years found by parser (not just TARGET_YEAR)
            for yr, val_musd in year_vals.items():
                yr_int = int(yr)
                if val_musd is None:
                    continue
                pid = get_period_id(conn, COMPANY, yr_int)
                if pid is None:
                    continue
                val_usd = val_musd * MUSD_TO_USD

                db_val = get_db_value(conn, table, COMPANY, pid, canonical)

                if db_val is None:
                    if not dry_run:
                        conn.execute(
                            f"INSERT INTO {table} (company_id, period_id, metric, value, source, updated_at) "
                            "VALUES (?, ?, ?, ?, 'pdf_parser', datetime('now'))",
                            (COMPANY, pid, canonical, val_usd))
                    stats['inserted'] += 1
                    print(f'  INSERT  {canonical:35} {yr_int} = {val_musd:>12,.1f} mUSD')
                else:
                    db_musd = db_val / MUSD_TO_USD
                    rel = abs(val_musd - db_musd) / max(abs(db_musd), 1.0)
                    if rel <= TOLERANCE:
                        stats['matched'] += 1
                    else:
                        stats['mismatch'] += 1
                        mismatches.append({
                            'section': sec_label,
                            'metric': canonical,
                            'parser_musd': val_musd,
                            'db_musd': db_musd,
                            'delta_pct': rel,
                        })

    # PPE components
    print(f'\n--- NOTE_13_PPE -> ppe_components ---')
    ppe_inserted = 0
    for block, years_data in res_ppe.data.items():
        for year, movements_data in years_data.items():
            year_int = int(year)
            pid = get_period_id(conn, COMPANY, year_int)
            if pid is None:
                continue
            for movement, cat_vals in movements_data.items():
                for category, val_musd in cat_vals.items():
                    if val_musd is None:
                        continue
                    val_usd = val_musd * MUSD_TO_USD
                    # value_type = '{block}_{movement}'
                    vtype = f'{block}_{movement}'
                    component_id = category
                    component_name = category.replace('_', ' ').title()

                    existing = conn.execute(
                        "SELECT value FROM ppe_components "
                        "WHERE company_id=? AND period_id=? AND component_id=? AND value_type=?",
                        (COMPANY, pid, component_id, vtype)).fetchone()

                    if existing is None:
                        if not dry_run:
                            conn.execute(
                                "INSERT INTO ppe_components "
                                "(company_id, period_id, component_id, component_name, "
                                "value_type, value, source, updated_at) "
                                "VALUES (?, ?, ?, ?, ?, ?, 'pdf_parser', datetime('now'))",
                                (COMPANY, pid, component_id, component_name,
                                 vtype, val_usd))
                        ppe_inserted += 1

    # Also insert standard snapshot types (gross/accumulated/net)
    for year_int in [2023, 2024]:
        pid = get_period_id(conn, COMPANY, year_int)
        if pid is None:
            continue
        cost_closing = res_ppe.data.get('cost', {}).get(year_int, {}).get('closing', {})
        dep_closing = res_ppe.data.get('accum_dep', {}).get(year_int, {}).get('closing', {})
        for cat in cost_closing:
            gross = cost_closing.get(cat)
            accum = dep_closing.get(cat)
            if gross is not None:
                existing = conn.execute(
                    "SELECT value FROM ppe_components "
                    "WHERE company_id=? AND period_id=? AND component_id=? AND value_type='gross'",
                    (COMPANY, pid, cat)).fetchone()
                if existing is None:
                    if not dry_run:
                        conn.execute(
                            "INSERT INTO ppe_components "
                            "(company_id, period_id, component_id, component_name, "
                            "value_type, value, source, updated_at) "
                            "VALUES (?, ?, ?, ?, 'gross', ?, 'pdf_parser', datetime('now'))",
                            (COMPANY, pid, cat, cat.replace('_', ' ').title(),
                             gross * MUSD_TO_USD))
                    ppe_inserted += 1
            if accum is not None:
                existing = conn.execute(
                    "SELECT value FROM ppe_components "
                    "WHERE company_id=? AND period_id=? AND component_id=? AND value_type='accumulated'",
                    (COMPANY, pid, cat)).fetchone()
                if existing is None:
                    if not dry_run:
                        conn.execute(
                            "INSERT INTO ppe_components "
                            "(company_id, period_id, component_id, component_name, "
                            "value_type, value, source, updated_at) "
                            "VALUES (?, ?, ?, ?, 'accumulated', ?, 'pdf_parser', datetime('now'))",
                            (COMPANY, pid, cat, cat.replace('_', ' ').title(),
                             accum * MUSD_TO_USD))
                    ppe_inserted += 1
            if gross is not None and accum is not None:
                existing = conn.execute(
                    "SELECT value FROM ppe_components "
                    "WHERE company_id=? AND period_id=? AND component_id=? AND value_type='net'",
                    (COMPANY, pid, cat)).fetchone()
                if existing is None:
                    if not dry_run:
                        conn.execute(
                            "INSERT INTO ppe_components "
                            "(company_id, period_id, component_id, component_name, "
                            "value_type, value, source, updated_at) "
                            "VALUES (?, ?, ?, ?, 'net', ?, 'pdf_parser', datetime('now'))",
                            (COMPANY, pid, cat, cat.replace('_', ' ').title(),
                             (gross - accum) * MUSD_TO_USD))
                    ppe_inserted += 1

    print(f'  {"Would insert" if dry_run else "Inserted"}: {ppe_inserted} rows')

    # ─── Debt instruments ────────────────────────────────────────
    print(f'\n--- NOTE_19_DEBT_LOANS -> debt_instruments ---')
    debt_inserted = enrich_debt_instruments(conn, 'company_id', COMPANY, dry_run)

    if not dry_run:
        conn.commit()

    # Summary
    print(f'\n{"="*60}')
    print(f'ENRICH SUMMARY {"[DRY RUN]" if dry_run else ""}')
    print(f'{"="*60}')
    print(f'  Matched ({TOLERANCE:.0%} tol): {stats["matched"]}')
    print(f'  Inserted:              {stats["inserted"]}')
    print(f'  MISMATCHES:            {stats["mismatch"]}')
    print(f'  PPE components:        {ppe_inserted}')
    print(f'  Debt instruments:      {debt_inserted}')

    if mismatches:
        print(f'\n--- MISMATCHES ---')
        for m in sorted(mismatches, key=lambda x: -x['delta_pct']):
            print(f'  {m["section"]:6} {m["metric"]:35} '
                  f'parser={m["parser_musd"]:>10,.1f} db={m["db_musd"]:>10,.1f} '
                  f'delta={m["delta_pct"]:.1%}')

    conn.close()

    Path('audit').mkdir(exist_ok=True)
    with open('audit/phase4d_enrich_report.json', 'w') as f:
        json.dump({
            'dry_run': dry_run, 'stats': stats,
            'ppe_inserted': ppe_inserted, 'mismatches': mismatches,
        }, f, indent=2, default=str)
    print(f'\nSaved: audit/phase4d_enrich_report.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
