"""Smoke test: parse Rusal 2024 FS ENG, IS section, compare to DB.

Phase 4b-i FIX: file-based smoke test (no more inline heredoc).
Strict sign compare, notes_only metrics skipped.
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


def db_values_for_year(year, metrics):
    conn = sqlite3.connect(DB_PATH)
    result = {}
    for m in metrics:
        row = conn.execute(
            "SELECT h.value FROM history_is h "
            "JOIN periods p ON h.period_id=p.period_id "
            "WHERE h.company_id='rusal' AND h.metric=? AND p.year=? LIMIT 1",
            (m, year)).fetchone()
        # DB stores in full USD, parser returns mUSD → convert
        result[m] = row[0] / 1e6 if row else None
    conn.close()
    return result


def main():
    with open(ADAPTER) as f:
        adapter = yaml.safe_load(f)
    is_cfg = adapter['sections']['IS']
    expected_canonicals = set(is_cfg['rows'].keys())
    notes_only = set(is_cfg.get('notes_only', []))

    parser = PDFParser(ADAPTER)
    print(f'Parsing: {PDF_PATH.name}')
    result = parser.parse_section(PDF_PATH, 'IS')

    print(f'\nSection: {result.section}')
    print(f'Page used: {result.page_used}')
    print(f'Years detected: {result.years_detected}')
    print(f'Metrics extracted: {len(result.metrics)}')
    print(f'Unmatched rows: {len(result.unmatched_rows)}')
    if result.warnings:
        print(f'Warnings: {result.warnings}')

    Path('audit').mkdir(exist_ok=True)
    with open('audit/phase4a_v2_parse_result.json', 'w') as f:
        json.dump({
            'section': result.section,
            'pdf': Path(result.pdf_path).name,
            'page_used': result.page_used,
            'years_detected': result.years_detected,
            'metrics': result.metrics,
            'unmatched_rows': result.unmatched_rows,
            'warnings': result.warnings,
        }, f, indent=2, default=str)

    parsed_target = {m: v.get(TARGET_YEAR) for m, v in result.metrics.items()}
    compare_keys = sorted(set(parsed_target.keys()) - notes_only)
    db_target = db_values_for_year(TARGET_YEAR, compare_keys)

    print(f'\n{"metric":26} {"parsed":>14} {"db":>14} {"status":>14}')
    print('-' * 70)

    matches = 0
    total = 0

    for m in compare_keys:
        p = parsed_target.get(m)
        d = db_target.get(m)
        total += 1
        if p is None or d is None:
            status = 'N/A'
        else:
            denom = max(abs(d), 1.0)
            rel = abs(p - d) / denom
            if rel <= TOLERANCE_PCT:
                status = 'ok'
                matches += 1
            else:
                status = f'MISMATCH {rel:.1%}'
        p_s = f'{p:,.0f}' if p is not None else '--'
        d_s = f'{d:,.0f}' if d is not None else '--'
        print(f'{m:26} {p_s:>14} {d_s:>14} {status:>14}')

    print('-' * 70)
    match_rate = matches / total if total else 0
    non_notes = len(expected_canonicals) - len(notes_only)
    coverage = len(result.metrics) / non_notes if non_notes else 0
    print(f'Match rate: {matches}/{total} ({match_rate:.0%})')
    print(f'Coverage:   {len(result.metrics)}/{non_notes} ({coverage:.0%})')
    if notes_only:
        print(f'Skipped (notes_only): {sorted(notes_only)}')

    with open('audit/phase4a_v2_smoke_report.md', 'w') as f:
        f.write(f'# IS Smoke Test (file-based)\n\n')
        f.write(f'**PDF:** {Path(result.pdf_path).name}\n')
        f.write(f'**Page:** {result.page_used}\n')
        f.write(f'**Years:** {result.years_detected}\n')
        f.write(f'**Match:** {matches}/{total} ({match_rate:.0%})\n')
        f.write(f'**Coverage:** {len(result.metrics)}/{non_notes} ({coverage:.0%})\n')
        passed = match_rate >= 0.95 and coverage >= 0.90
        f.write(f'**Status:** {"PASS" if passed else "FAIL"}\n')

    return 0 if (match_rate >= 0.95 and coverage >= 0.90) else 1


if __name__ == '__main__':
    sys.exit(main())
