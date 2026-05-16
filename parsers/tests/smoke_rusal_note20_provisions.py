"""Smoke: Rusal 2024 FS ENG, Note 20 Provisions pivot."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from parsers.pdf_parser import PDFParser

PDF = Path('/Users/arturhusnutdinov/Documents/IT Development/Docker/rusalFinStates/'
           'RUSAL_consolidated_financial_statement_12m2024_ENG.pdf')
ADAPTER = Path('parsers/adapters/rusal.yaml')

def get_total(mv):
    if not mv: return None
    for k, v in mv.items():
        if 'total' in k: return v
    return list(mv.values())[-1] if mv else None

def main():
    r = PDFParser(ADAPTER).parse_pivot_note(PDF, 'NOTE_20_PROVISIONS')
    print(f'Page: {r.page_used}, categories: {r.categories}')
    if r.warnings: print(f'Warnings: {r.warnings}')

    Path('audit').mkdir(exist_ok=True)
    with open('audit/phase4c_provisions_result.json', 'w') as f:
        json.dump({'page': r.page_used, 'cats': r.categories,
                   'data': r.data}, f, indent=2, default=str)

    ok = total_checks = 0
    EXPECTED = {2023: 383, 2024: 339}
    for year, exp_closing in EXPECTED.items():
        closing = get_total(r.data.get('provisions', {}).get(year, {}).get('closing', {}))
        total_checks += 1
        if closing and abs(closing - exp_closing) / exp_closing <= 0.02:
            ok += 1
            print(f'  {year} closing: {closing:.0f} = {exp_closing} ok')
        else:
            print(f'  {year} closing: {closing} vs {exp_closing} MISMATCH')

    rate = ok / total_checks if total_checks else 0
    print(f'Sanity: {ok}/{total_checks} ({rate:.0%})')
    with open('audit/phase4c_provisions_smoke_report.md', 'w') as f:
        f.write(f'# Note 20 Provisions\n**Page:** {r.page_used}\n**Sanity:** {ok}/{total_checks}\n')
        f.write(f'**Status:** {"PASS" if rate >= 0.5 else "FAIL"}\n')
    return 0 if rate >= 0.5 else 1

if __name__ == '__main__': sys.exit(main())
