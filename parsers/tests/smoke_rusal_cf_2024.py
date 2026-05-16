"""Smoke test: parse Rusal 2024 FS ENG, CF section, compare to DB.

Phase 4b-iii: mapping only (no aggregation).
Coverage formula fix: denominator = non-helper, non-notes_only rows.
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
SECTION = 'CF'


def db_values_for_year(year, metrics):
    conn = sqlite3.connect(DB_PATH)
    result = {}
    for m in metrics:
        row = conn.execute(
            "SELECT h.value FROM history_cf h "
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
    all_rows = sec_cfg['rows']
    # Non-helper canonicals = expected metrics
    expected_canonicals = {k for k in all_rows if not k.startswith('_')}
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
    with open('audit/phase4b_iii_parse_result.json', 'w') as f:
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

    yaml_not_found = expected_canonicals - notes_only - set(parsed_target.keys())

    print(f'\n{"metric":35} {"parsed":>12} {"db":>12} {"status":>10}')
    print('-' * 72)

    matches = total = 0
    for m in compare_keys:
        p = parsed_target.get(m)
        d = db_target.get(m)
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
        print(f'{m:35} {ps:>12} {ds:>12} {status:>10}')

    if yaml_not_found:
        print(f'\nYaml canonicals NOT found ({len(yaml_not_found)}):')
        for m in sorted(yaml_not_found):
            print(f'  {m}')

    print('-' * 72)
    match_rate = matches / total if total else 0
    # Fixed coverage: intersection of extracted with expected canonicals
    extracted = set(result.metrics.keys()) & expected_canonicals
    non_notes = len(expected_canonicals) - len(notes_only)
    coverage = len(extracted) / non_notes if non_notes else 0
    print(f'Match rate: {matches}/{total} ({match_rate:.0%})')
    print(f'Coverage:   {len(extracted)}/{non_notes} ({coverage:.0%})')

    with open('audit/phase4b_iii_smoke_report.md', 'w') as f:
        f.write(f'# CF Smoke Test\n\n')
        f.write(f'**Page:** {result.page_used}\n**Years:** {result.years_detected}\n')
        f.write(f'**Match:** {matches}/{total} ({match_rate:.0%})\n')
        f.write(f'**Coverage:** {len(extracted)}/{non_notes} ({coverage:.0%})\n')
        passed = match_rate >= 0.85 and coverage >= 0.70
        f.write(f'**Status:** {"PASS" if passed else "FAIL"}\n')

    return 0 if (match_rate >= 0.85 and coverage >= 0.70) else 1


if __name__ == '__main__':
    sys.exit(main())
