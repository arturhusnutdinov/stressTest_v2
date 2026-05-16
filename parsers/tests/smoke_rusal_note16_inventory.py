"""Smoke test: parse Rusal 2024 FS ENG, Note 16 (Inventory), compare breakdown.

Phase 4c-inventory: proves parse_section() works for Notes-level tables.
New canonicals (inventory_raw_materials, inventory_wip, inventory_fg) are
NOT in DB yet — compared against expected values from discovery dump.
Sanity check: RM + WIP + FG = 4,477 (= DB inventory for 2024).
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from parsers.pdf_parser import PDFParser

PDF_PATH = Path(
    '/Users/arturhusnutdinov/Documents/IT Development/Docker/rusalFinStates/'
    'RUSAL_consolidated_financial_statement_12m2024_ENG.pdf'
)
ADAPTER = Path('parsers/adapters/rusal.yaml')
DB_PATH = 'data_mart_v2.db'
TOLERANCE_PCT = 0.02
TARGET_YEAR = 2024
SECTION = 'NOTE_16_INVENTORY'

EXPECTED = {
    'inventory_raw_materials': {2024: 1447, 2023: 1333},
    'inventory_wip':           {2024: 848,  2023: 766},
    'inventory_fg':            {2024: 2182, 2023: 1500},
}


def db_inventory_total(year):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT h.value FROM history_bs h "
        "JOIN periods p ON h.period_id=p.period_id "
        "WHERE h.company_id='rusal' AND h.metric='inventory' AND p.year=?",
        (year,)).fetchone()
    conn.close()
    return row[0] / 1e6 if row else None


def main():
    parser = PDFParser(ADAPTER)
    print(f'Parsing: {PDF_PATH.name}')
    result = parser.parse_section(PDF_PATH, SECTION)

    print(f'\nSection: {result.section}')
    print(f'Page used: {result.page_used}')
    print(f'Years detected: {result.years_detected}')
    print(f'Metrics extracted: {len(result.metrics)}')
    print(f'Unmatched rows: {len(result.unmatched_rows)}')
    if result.warnings:
        print(f'Warnings: {result.warnings}')

    Path('audit').mkdir(exist_ok=True)
    with open('audit/phase4c_inv_parse_result.json', 'w') as f:
        json.dump({
            'section': result.section,
            'pdf': Path(result.pdf_path).name,
            'page_used': result.page_used,
            'years_detected': result.years_detected,
            'metrics': result.metrics,
            'unmatched_rows': result.unmatched_rows,
            'warnings': result.warnings,
        }, f, indent=2, default=str)

    print(f'\n{"canonical":30} {"year":>6} {"parsed":>10} {"expected":>10} {"status":>8}')
    print('-' * 68)

    match_exp = total_exp = 0
    for canonical, years in EXPECTED.items():
        for year, expected_val in years.items():
            total_exp += 1
            parsed_val = result.metrics.get(canonical, {}).get(year)
            if parsed_val is None:
                status = 'MISSING'
            elif abs(parsed_val - expected_val) <= max(1, abs(expected_val) * TOLERANCE_PCT):
                status = 'ok'
                match_exp += 1
            else:
                status = f'MISMATCH {parsed_val:.0f}'
            ps = f'{parsed_val:,.0f}' if parsed_val is not None else '--'
            print(f'{canonical:30} {year:>6} {ps:>10} {expected_val:>10,} {status:>8}')

    rate = match_exp / total_exp if total_exp else 0
    print(f'\nExpected match: {match_exp}/{total_exp} ({rate:.0%})')

    print(f'\nSum sanity (RM + WIP + FG vs DB.inventory):')
    for y in [2024, 2023]:
        rm = result.metrics.get('inventory_raw_materials', {}).get(y)
        wip = result.metrics.get('inventory_wip', {}).get(y)
        fg = result.metrics.get('inventory_fg', {}).get(y)
        db_total = db_inventory_total(y)
        parsed_total = (rm + wip + fg) if all(v is not None for v in [rm, wip, fg]) else None
        ps = f'{parsed_total:,.0f}' if parsed_total is not None else '--'
        ds = f'{db_total:,.0f}' if db_total is not None else '--'
        if parsed_total is not None and db_total is not None:
            delta = abs(parsed_total - db_total)
            st = 'ok' if delta <= max(1, abs(db_total) * TOLERANCE_PCT) else f'delta={parsed_total - db_total:+.0f}'
        else:
            st = 'N/A'
        print(f'  {y}: sum={ps}, db={ds}, {st}')

    with open('audit/phase4c_inv_smoke_report.md', 'w') as f:
        f.write(f'# Phase 4c-inventory Smoke Test\n\n')
        f.write(f'**Page:** {result.page_used}\n**Years:** {result.years_detected}\n')
        f.write(f'**Match:** {match_exp}/{total_exp} ({rate:.0%})\n')
        passed = rate >= 0.90
        f.write(f'**Status:** {"PASS" if passed else "FAIL"}\n')

    return 0 if rate >= 0.90 else 1


if __name__ == '__main__':
    sys.exit(main())
