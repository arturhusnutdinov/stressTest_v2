"""Smoke test: parse Rusal 2024 FS ENG, Note 19 Loans repayment schedule.

Phase 4c-debt: validates parse_instrument_list() capability.
Expected: 2024 schedule has 14 loan instruments, total = 4,241 mUSD.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from parsers.pdf_parser import PDFParser

PDF_PATH = Path(
    '/Users/arturhusnutdinov/Documents/IT Development/Docker/rusalFinStates/'
    'RUSAL_consolidated_financial_statement_12m2024_ENG.pdf'
)
ADAPTER = Path('parsers/adapters/rusal.yaml')
TOLERANCE = 0.02

EXPECTED_2024 = {
    'instrument_count': 14,
    'total_sum': 4241,
    'yr1_sum': 1750,
    'yr2_sum': 997,
    'yr3_sum': 840,
    'yr4_sum': 262,
    'yr5_sum': 182,
    'yr6_plus_sum': 210,
}


def main():
    parser = PDFParser(ADAPTER)
    print(f'Parsing: {PDF_PATH.name}')
    result = parser.parse_instrument_list(PDF_PATH, 'NOTE_19_DEBT_LOANS')

    print(f'\nPages used: {result.page_used}')
    print(f'Schedule year: {result.schedule_year}')
    print(f'Total instruments: {len(result.instruments)}')
    if result.warnings:
        print(f'Warnings: {result.warnings}')

    by_year = {}
    for inst in result.instruments:
        by_year.setdefault(inst.get('schedule_year'), []).append(inst)

    for yr in sorted(by_year, reverse=True):
        insts = by_year[yr]
        print(f'\n  {yr}: {len(insts)} instruments')
        for i in insts:
            print(f'    [{(i["instrument_class"] or "?"):25}] [{(i["rate_type"] or "?"):8}] '
                  f'{i["rate_description"]:35} total={i["total"]:>8,.0f}')

    Path('audit').mkdir(exist_ok=True)
    with open('audit/phase4c_debt_parse_result.json', 'w') as f:
        json.dump({
            'pages': result.page_used,
            'schedule_year': result.schedule_year,
            'by_year': {str(yr): len(insts) for yr, insts in by_year.items()},
            'instruments': result.instruments,
        }, f, indent=2, default=str)

    # Sanity checks
    insts_2024 = [i for i in by_year.get(2024, [])
                  if i.get('instrument_class') and i.get('rate_type')]

    print(f'\n{"-"*70}')
    print(f'SANITY CHECKS 2024')
    print(f'{"-"*70}')

    ok = total_checks = 0

    def check(label, got, expected):
        nonlocal ok, total_checks
        total_checks += 1
        rel = abs(got - expected) / max(abs(expected), 1)
        st = 'ok' if rel <= TOLERANCE else f'{rel:.0%}'
        if rel <= TOLERANCE:
            ok += 1
        print(f'  {label:35} {got:>10,.0f} exp={expected:>10,} {st:>6}')

    check('instrument count', len(insts_2024), EXPECTED_2024['instrument_count'])
    check('total sum', sum(i['total'] for i in insts_2024), EXPECTED_2024['total_sum'])
    check('yr1 sum', sum(i['yr1'] for i in insts_2024), EXPECTED_2024['yr1_sum'])
    check('yr2 sum', sum(i['yr2'] for i in insts_2024), EXPECTED_2024['yr2_sum'])
    check('yr3 sum', sum(i['yr3'] for i in insts_2024), EXPECTED_2024['yr3_sum'])
    check('yr4 sum', sum(i['yr4'] for i in insts_2024), EXPECTED_2024['yr4_sum'])
    check('yr5 sum', sum(i['yr5'] for i in insts_2024), EXPECTED_2024['yr5_sum'])
    check('yr6_plus sum', sum(i['yr6_plus'] for i in insts_2024), EXPECTED_2024['yr6_plus_sum'])

    rate = ok / total_checks if total_checks else 0
    print(f'{"-"*70}')
    print(f'Result: {ok}/{total_checks} ({rate:.0%})')

    with open('audit/phase4c_debt_smoke_report.md', 'w') as f:
        f.write(f'# Phase 4c-debt Smoke Report\n\n')
        f.write(f'**Pages:** {result.page_used}\n')
        f.write(f'**Instruments:** {len(result.instruments)}\n')
        f.write(f'**Sanity 2024:** {ok}/{total_checks} ({rate:.0%})\n')
        f.write(f'**Status:** {"PASS" if rate >= 0.85 else "FAIL"}\n')

    return 0 if rate >= 0.85 else 1


if __name__ == '__main__':
    sys.exit(main())
