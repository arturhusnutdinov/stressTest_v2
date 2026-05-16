"""Smoke test: parse Rusal 2024 FS ENG, Note 13 PPE pivot table.

Phase 4c-ppe: validates parse_pivot_note() capability.
Sanity checks vs discovery values and DB cross-reference.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from parsers.pdf_parser import PDFParser

PDF_PATH = Path(
    '/Users/arturhusnutdinov/Documents/IT Development/Docker/rusalFinStates/'
    'RUSAL_consolidated_financial_statement_12m2024_ENG.pdf'
)
ADAPTER = Path('parsers/adapters/rusal.yaml')
DB_PATH = 'data_mart_v2.db'
TOLERANCE_PCT = 0.02

EXPECTED = {
    'cost': {
        2024: {'closing_total': 17341, 'additions_total': 1503, 'disposals_total': -290},
        2023: {'closing_total': 16514, 'additions_total': 1121},
    },
    'accum_dep': {
        2024: {'closing_total': 11336, 'depreciation_charge_total': 556},
        2023: {'closing_total': 10708, 'depreciation_charge_total': 542},
    },
}


def db_metric(table, metric, year):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        f"SELECT h.value FROM {table} h "
        "JOIN periods p ON h.period_id=p.period_id "
        "WHERE h.company_id='rusal' AND h.metric=? AND p.year=? LIMIT 1",
        (metric, year)).fetchone()
    conn.close()
    return row[0] / 1e6 if row else None


def get_total(movement_dict):
    if not movement_dict:
        return None
    for k, v in movement_dict.items():
        if 'total' in k or 'tot' in k:
            return v
    return sum(movement_dict.values())


def main():
    parser = PDFParser(ADAPTER)
    print(f'Parsing: {PDF_PATH.name}')
    result = parser.parse_pivot_note(PDF_PATH, 'NOTE_13_PPE')

    print(f'\nSection: {result.section}')
    print(f'Page used: {result.page_used}')
    print(f'Categories: {result.categories}')
    print(f'Blocks: {list(result.data.keys())}')
    if result.warnings:
        print(f'Warnings: {result.warnings}')

    # Show structure
    for block, years in result.data.items():
        for year, movements in years.items():
            print(f'  {block}/{year}: {list(movements.keys())}')

    Path('audit').mkdir(exist_ok=True)
    with open('audit/phase4c_ppe_parse_result.json', 'w') as f:
        json.dump({
            'section': result.section,
            'page_used': result.page_used,
            'categories': result.categories,
            'blocks': list(result.data.keys()),
            'data': result.data,
            'warnings': result.warnings,
        }, f, indent=2, default=str)

    print(f'\n{"-"*70}')
    print(f'{"check":45} {"parsed":>10} {"expected":>10} {"st":>6}')
    print(f'{"-"*70}')

    ok = total_checks = 0

    def check(label, parsed_val, expected_val):
        nonlocal ok, total_checks
        total_checks += 1
        if parsed_val is None:
            st = 'MISS'
        elif expected_val is None:
            st = 'N/A'
        else:
            rel = abs(parsed_val - expected_val) / max(abs(expected_val), 1)
            if rel <= TOLERANCE_PCT:
                st = 'ok'
                ok += 1
            else:
                st = f'{rel:.0%}'
        ps = f'{parsed_val:,.0f}' if parsed_val is not None else '--'
        es = f'{expected_val:,.0f}' if expected_val is not None else '--'
        print(f'  {label:43} {ps:>10} {es:>10} {st:>6}')

    # Expected checks
    for block in ['cost', 'accum_dep']:
        for year in [2024, 2023]:
            bdata = result.data.get(block, {}).get(year, {})
            exp = EXPECTED.get(block, {}).get(year, {})
            for key, exp_val in exp.items():
                movement = key.replace('_total', '')
                check(f'{block}/{year}/{movement}',
                      get_total(bdata.get(movement)), exp_val)

    # DB cross-checks
    print(f'\n{"-"*70}')
    print(f'DB cross-checks')
    print(f'{"-"*70}')

    cost_close = get_total(result.data.get('cost', {}).get(2024, {}).get('closing'))
    dep_close = get_total(result.data.get('accum_dep', {}).get(2024, {}).get('closing'))

    check('ppe_gross vs DB', cost_close, db_metric('history_bs', 'ppe_gross', 2024))
    check('ppe_accum_dep vs DB', dep_close,
          abs(db_metric('history_bs', 'ppe_accum_dep', 2024) or 0))
    if cost_close and dep_close:
        check('ppe_net vs DB', cost_close - dep_close,
              db_metric('history_bs', 'ppe_net', 2024))

    print(f'{"-"*70}')
    rate = ok / total_checks if total_checks else 0
    print(f'Result: {ok}/{total_checks} ({rate:.0%})')

    with open('audit/phase4c_ppe_smoke_report.md', 'w') as f:
        f.write(f'# Phase 4c-ppe Smoke Report\n\n')
        f.write(f'**Page:** {result.page_used}\n')
        f.write(f'**Categories:** {result.categories}\n')
        f.write(f'**Blocks:** {list(result.data.keys())}\n')
        f.write(f'**Checks:** {ok}/{total_checks} ({rate:.0%})\n')
        f.write(f'**Status:** {"PASS" if rate >= 0.80 else "FAIL"}\n')

    return 0 if rate >= 0.80 else 1


if __name__ == '__main__':
    sys.exit(main())
