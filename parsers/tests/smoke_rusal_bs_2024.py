"""Smoke test: parse Rusal 2024 FS ENG, BS section, compare to DB.

Phase 4b-ii: mapping only (no aggregation).
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
SECTION = 'BS'


def db_values_for_year(year, metrics):
    conn = sqlite3.connect(DB_PATH)
    result = {}
    for m in metrics:
        row = conn.execute(
            "SELECT h.value FROM history_bs h "
            "JOIN periods p ON h.period_id=p.period_id "
            "WHERE h.company_id='rusal' AND h.metric=? AND p.year=? LIMIT 1",
            (m, year)).fetchone()
        # DB stores in full USD, parser returns mUSD
        result[m] = row[0] / 1e6 if row else None
    conn.close()
    return result


def main():
    with open(ADAPTER) as f:
        adapter = yaml.safe_load(f)
    sec_cfg = adapter['sections'][SECTION]
    expected = set(sec_cfg['rows'].keys())
    notes_only = set(sec_cfg.get('notes_only', []))

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
    with open('audit/phase4b_ii_parse_result.json', 'w') as f:
        json.dump({
            'section': result.section,
            'pdf': Path(result.pdf_path).name,
            'page_used': result.page_used,
            'years_detected': result.years_detected,
            'metrics': result.metrics,
            'unmatched_rows': result.unmatched_rows,
            'warnings': result.warnings,
        }, f, indent=2, default=str)

    parsed = {m: v.get(TARGET_YEAR) for m, v in result.metrics.items()}
    compare = sorted(set(parsed.keys()) - notes_only)
    db = db_values_for_year(TARGET_YEAR, compare)

    print(f'\n{"metric":30} {"parsed":>12} {"db":>12} {"status":>10}')
    print('-' * 68)

    matches = total = 0
    for m in compare:
        p = parsed.get(m)
        d = db.get(m)
        total += 1
        if p is None or d is None:
            status = 'N/A'
        else:
            rel = abs(p - d) / max(abs(d), 1.0)
            if rel <= TOLERANCE_PCT:
                status = 'ok'
                matches += 1
            else:
                status = f'MISMATCH {rel:.1%}'
        ps = f'{p:,.0f}' if p is not None else '--'
        ds = f'{d:,.0f}' if d is not None else '--'
        print(f'{m:30} {ps:>12} {ds:>12} {status:>10}')

    # Show yaml canonicals not found
    not_found = expected - notes_only - set(parsed.keys())
    if not_found:
        print(f'\nYaml canonicals NOT found ({len(not_found)}):')
        for m in sorted(not_found):
            print(f'  {m}')

    print('-' * 68)
    rate = matches / total if total else 0
    non_notes = len(expected) - len(notes_only)
    cov = len(result.metrics) / non_notes if non_notes else 0
    print(f'Match: {matches}/{total} ({rate:.0%})')
    print(f'Coverage: {len(result.metrics)}/{non_notes} ({cov:.0%})')

    with open('audit/phase4b_ii_smoke_report.md', 'w') as f:
        f.write(f'# BS Smoke Test\n\n')
        f.write(f'**Page:** {result.page_used}\n**Years:** {result.years_detected}\n')
        f.write(f'**Match:** {matches}/{total} ({rate:.0%})\n')
        f.write(f'**Coverage:** {len(result.metrics)}/{non_notes} ({cov:.0%})\n')
        passed = rate >= 0.90 and cov >= 0.70
        f.write(f'**Status:** {"PASS" if passed else "FAIL"}\n')

    return 0 if (rate >= 0.90 and cov >= 0.70) else 1


if __name__ == '__main__':
    sys.exit(main())
