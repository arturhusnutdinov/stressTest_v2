"""Smoke: Note 8 Tax reconciliation + DTA/DTL movement."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from parsers.pdf_parser import PDFParser

PDF = Path('/Users/arturhusnutdinov/Documents/IT Development/Docker/rusalFinStates/'
           'RUSAL_consolidated_financial_statement_12m2024_ENG.pdf')
ADAPTER = Path('parsers/adapters/rusal.yaml')
TOL = 0.02


def main():
    p = PDFParser(ADAPTER)
    ok = total = 0

    def check(label, got, exp):
        nonlocal ok, total
        total += 1
        if got is None:
            st = 'MISSING'
        elif abs(got - exp) / max(abs(exp), 1) <= TOL:
            st = 'ok'; ok += 1
        else:
            st = f'MISMATCH {got:.0f}'
        print(f'  {label:45} {st}')

    # ─── Reconciliation ──────────────────────────────────────
    print('=== Tax Reconciliation ===')
    r = p.parse_pivot_note(PDF, 'NOTE_8_TAX_RECONCILIATION')
    print(f'Page: {r.page_used}')

    def recon(cat, mv):
        return r.data.get(2024, {}).get(cat, {}).get(mv)

    check('profit_before_tax amount_2024', recon('profit_before_tax', 'amount_2024'), 858)
    check('profit_before_tax amount_2023', recon('profit_before_tax', 'amount_2023'), 244)
    check('tax_expense amount_2024', recon('tax_expense', 'amount_2024'), 55)
    check('tax_expense amount_2023', recon('tax_expense', 'amount_2023'), -38)
    check('tax_expense pct_2024', recon('tax_expense', 'pct_2024'), 6)
    check('statutory_rate pct_2024', recon('income_tax_statutory', 'pct_2024'), 20)

    # ─── DTA/DTL Movement ────────────────────────────────────
    print('\n=== DTA/DTL Movement ===')
    r2 = p.parse_pivot_note(PDF, 'NOTE_8_DTA_MOVEMENT')
    print(f'Page: {r2.page_used}')

    def dta(yr, cat, mv):
        return r2.data.get(yr, {}).get(cat, {}).get(mv)

    check('total closing 2024 (=dta-dtl=-138)', dta(2024, 'total', 'closing'), -138)
    check('total closing 2023', dta(2023, 'total', 'closing'), -176)
    check('ppe closing 2024', dta(2024, 'ppe', 'closing'), -602)
    check('ppe closing 2023', dta(2023, 'ppe', 'closing'), -503)
    check('total opening 2024 = closing 2023', dta(2024, 'total', 'opening'), -176)
    check('total P&L 2024', dta(2024, 'total', 'recognised_in_pl'), 65)

    rate = ok / total if total else 0
    print(f'\nSanity: {ok}/{total} ({rate:.0%})')

    Path('audit').mkdir(exist_ok=True)
    with open('audit/phase4c_note8_smoke_report.md', 'w') as f:
        f.write(f'# Note 8 Tax\n**Recon:** {r.page_used} | **DTA:** {r2.page_used}\n')
        f.write(f'**Sanity:** {ok}/{total} ({rate:.0%})\n')
        f.write(f'**Status:** {"PASS" if rate >= 0.75 else "FAIL"}\n')

    with open('audit/phase4c_tax_result.json', 'w') as f:
        json.dump({'recon': r.data, 'dta': r2.data}, f, indent=2, default=str)

    return 0 if rate >= 0.75 else 1

if __name__ == '__main__':
    sys.exit(main())
