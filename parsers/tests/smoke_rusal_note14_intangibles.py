"""Smoke: Rusal 2024 FS ENG, Note 14 Intangible Assets pivot."""
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
    r = PDFParser(ADAPTER).parse_pivot_note(PDF, 'NOTE_14_INTANGIBLES')
    print(f'Page: {r.page_used}, blocks: {list(r.data.keys())}')
    if r.warnings: print(f'Warnings: {r.warnings}')

    Path('audit').mkdir(exist_ok=True)
    with open('audit/phase4c_intangibles_result.json', 'w') as f:
        json.dump({'page': r.page_used, 'cats': r.categories,
                   'data': r.data}, f, indent=2, default=str)

    cost_2024 = get_total(r.data.get('cost', {}).get(2024, {}).get('closing', {}))
    amort_2024 = get_total(r.data.get('accum_amort', {}).get(2024, {}).get('closing', {}))
    print(f'Cost closing 2024: {cost_2024}')
    print(f'AccumAmort closing 2024: {amort_2024}')
    ok = False
    if cost_2024 and amort_2024:
        nbv = cost_2024 - abs(amort_2024)
        print(f'NBV = {nbv:.0f} (expected ~2,201)')
        ok = abs(nbv - 2201) / 2201 <= 0.05
        print(f'NBV check: {"ok" if ok else "FAIL"}')
    with open('audit/phase4c_intangibles_smoke_report.md', 'w') as f:
        f.write(f'# Note 14 Intangibles\n**Page:** {r.page_used}\n**Status:** {"PASS" if ok else "FAIL"}\n')
    return 0 if ok else 1

if __name__ == '__main__': sys.exit(main())
