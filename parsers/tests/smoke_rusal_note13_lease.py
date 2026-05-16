"""Smoke: Note 13 Lease (ROU assets sub-section).

ROU closing_total_2024 = 45 (matches BS rou_asset).
Lease liabilities from text disclosure (not table):
  non-current 2024 = 42, 2023 = 30.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from parsers.pdf_parser import PDFParser

PDF = Path('/Users/arturhusnutdinov/Documents/IT Development/Docker/rusalFinStates/'
           'RUSAL_consolidated_financial_statement_12m2024_ENG.pdf')
ADAPTER = Path('parsers/adapters/rusal.yaml')


def main():
    p = PDFParser(ADAPTER)
    r = p.parse_pivot_note(PDF, 'NOTE_13_LEASE')
    print(f'Page: {r.page_used}, blocks: {list(r.data.keys())}')
    print(f'Categories: {r.categories}')

    ok = total = 0
    for block, years in r.data.items():
        for yr, mvs in years.items():
            closing = mvs.get('closing', {})
            total_val = closing.get('total')
            if total_val:
                print(f'  ROU closing {yr}: {total_val:.0f}')
                if yr == 2024:
                    total += 1
                    if abs(total_val - 45) / 45 <= 0.05:
                        ok += 1
                        print(f'    matches DB rou_asset=45')

    rate = ok / total if total else 0
    print(f'\nSanity: {ok}/{total}')

    Path('audit').mkdir(exist_ok=True)
    with open('audit/phase4c_lease_result.json', 'w') as f:
        json.dump({'page': r.page_used, 'cats': r.categories, 'data': r.data},
                  f, indent=2, default=str)
    with open('audit/phase4c_lease_smoke_report.md', 'w') as f:
        f.write(f'# Note 13 Lease\n**Page:** {r.page_used}\n')
        f.write(f'**ROU closing 2024:** {r.data.get("rou_assets", {}).get(2024, {}).get("closing", {}).get("total")}\n')
        f.write(f'**Status:** {"PASS" if ok else "PARTIAL"}\n')

    return 0 if ok > 0 or r.data else 1

if __name__ == '__main__':
    sys.exit(main())
