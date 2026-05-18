# PDF Parser Guide — Rusal Financial Statements

**Updated:** May 2026 | **Version:** 2.1.0 | **Status:** Production ready

## Overview

Automated extraction from EN Financial Statements PDFs (IFRS, pdfplumber).

**Code:** `parsers/pdf_parser.py` (~1000 lines)
**Adapter:** `parsers/adapters/rusal.yaml` (~600 lines)

## Architecture

| Method | Mode | Use case |
|--------|------|----------|
| `parse_section()` | standard | IS, BS, CF, Inventory |
| `parse_pivot_note()` | text pivot | PPE, Intangibles, Provisions |
| `parse_pivot_note()` | wide pivot | Associates (years in columns) |
| `parse_pivot_note()` | sequential | DTA/DTL, Tax reconciliation |
| `parse_instrument_list()` | instrument | Debt schedule |

## Notes Coverage

| Note | Method | Sanity |
|------|--------|--------|
| IS/BS/CF face | parse_section | IS 16/16, BS 25/27, CF 34/34 |
| Note 8 Tax | sequential | 12/12 |
| Note 13 PPE | text pivot | 12/12 |
| Note 13 Lease ROU | text pivot | 1/1 |
| Note 14 Intangibles | text pivot | NBV verified |
| Note 15 Associates | wide pivot | 4/4 |
| Note 16 Inventory | parse_section | 6/6 |
| Note 19 Debt | instrument_list | 17/17 exact |
| Note 20 Provisions | text pivot | 2/2 |

## Year Coverage (after all fixes)

| Statement | Years | Count |
|-----------|-------|-------|
| IS | 2011-2025 | 15 |
| BS | 2012-2025 | 14 |
| CF | 2011-2025 | 15 |

## Parser Fixes Applied

1. **Fallback anti-trigger** — skip TOC pages in fallback loop
2. **anchor_mode: any** — handle multi-page face sheets (CF/BS)
3. **Year range 2010+** — support pre-2015 PDFs
4. **IS columns removal** — removed stale `year_cols_from: 4`
5. **Non-consolidated BS anti-trigger** — skip entity-level BS in 2013/2014

## Annual Report Parser

Extracts operational KPIs from Russian Annual Reports:

| Data | Years | DB Table |
|------|-------|----------|
| Al/Alumina sales (kt, mUSD, USD/t) | 2021-2024 | operational_drivers |
| Geographic revenue (mUSD) | 2015-2024 | operational_drivers |

## Testing

- **Unit tests:** 22/22 (`parsers/tests/test_parser_helpers.py`)
- **Smoke tests:** 12 files (`parsers/tests/smoke_rusal_*.py`)
- **Regression:** prod BS=0.000004 after any change
