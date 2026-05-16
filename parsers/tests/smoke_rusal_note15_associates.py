"""Smoke: Rusal 2024 FS ENG, Note 15 Associates/JV roll-forward (wide-table)."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from parsers.pdf_parser import PDFParser

PDF = Path('/Users/arturhusnutdinov/Documents/IT Development/Docker/rusalFinStates/'
           'RUSAL_consolidated_financial_statement_12m2024_ENG.pdf')
ADAPTER = Path('parsers/adapters/rusal.yaml')


def main():
    r = PDFParser(ADAPTER).parse_pivot_note(PDF, 'NOTE_15_ASSOCIATES')
    print(f'Page: {r.page_used}, blocks: {list(r.data.keys())}')
    print(f'Categories: {r.categories}')
    if r.warnings:
        print(f'Warnings: {r.warnings}')

    Path('audit').mkdir(exist_ok=True)
    with open('audit/phase4c_associates_result.json', 'w') as f:
        json.dump({'page': r.page_used, 'cats': r.categories,
                   'data': r.data}, f, indent=2, default=str)

    ok = total_checks = 0

    def check(label, got, exp):
        nonlocal ok, total_checks
        total_checks += 1
        if got is None:
            st = 'MISSING'
        elif abs(got - exp) / max(abs(exp), 1) <= 0.05:
            st = 'ok'
            ok += 1
        else:
            st = f'MISMATCH {got:.0f}'
        print(f'  {label:45} {st}')

    for block, years in r.data.items():
        for year in sorted(years, reverse=True):
            mvs = years[year]
            closing = mvs.get('closing', {})
            total = closing.get('total')
            if total:
                print(f'\n{block}/{year}: closing_total = {total:.0f}')

    # Sanity checks
    for block in r.data:
        y2024 = r.data[block].get(2024, {})
        y2023 = r.data[block].get(2023, {})
        check('closing_total_2024 = 4868 (BS)',
              y2024.get('closing', {}).get('total'), 4868)
        check('share_of_profits_total_2024 = 564 (IS)',
              y2024.get('share_of_profits', {}).get('total'), 564)
        check('closing_total_2023 = 4521',
              y2023.get('closing', {}).get('total'), 4521)
        check('opening_total_2024 = 4521',
              y2024.get('opening', {}).get('total'), 4521)
        break  # only first block

    rate = ok / total_checks if total_checks else 0
    print(f'\nSanity: {ok}/{total_checks} ({rate:.0%})')

    with open('audit/phase4c_associates_smoke_report.md', 'w') as f:
        f.write(f'# Note 15 Associates\n**Page:** {r.page_used}\n')
        f.write(f'**Sanity:** {ok}/{total_checks} ({rate:.0%})\n')
        f.write(f'**Status:** {"PASS" if rate >= 0.75 else "FAIL"}\n')

    return 0 if rate >= 0.75 else 1


if __name__ == '__main__':
    sys.exit(main())
