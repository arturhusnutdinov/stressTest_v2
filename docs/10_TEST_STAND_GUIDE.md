# Test Stand Guide

**Updated:** May 2026 | **Version:** 2.1.0

## Overview

Integration test infrastructure for verifying Excel → DB loading and data consistency.

**Location:** `tests/integration/`

**Full test suite:** `python3 -m pytest tests/ -v` — 45 tests (unit + integration)

## Usage

```bash
# 1. Setup test DB (copy prod, clear company data)
python3 tests/integration/setup_test_stand.py --company rusal

# 2. Load Excel into test DB
# ExcelLoader (face + canonical):
python3 -c "
from engine.loader.excel import ExcelLoader
from engine.database.repository import Repository
with Repository('tests/integration/test_data_mart.db') as repo:
    ExcelLoader(company_id='rusal', repo=repo, db_unit='USD',
                input_default_unit='mUSD').load(
        'companies/rusal/data/rusal_complete_v4.xlsx')
"
# Schedule sheets (Notes data):
python3 tools/load_schedule_sheets.py --company rusal \
    --db tests/integration/test_data_mart.db

# 3. Verify consistency
python3 tests/integration/verify_consistency.py --company rusal
```

## What verify_consistency checks

1. **Table comparison** — row counts: prod vs test (11 tables)
2. **Corkscrew verification** — closing balance = BS face value
3. **BS Identity** — total_assets = total_liabilities + total_equity

## Expected output

```
history_is:          336 = 336  ✓
history_bs:          458 ≈ 446  ≈ (parser-only extras)
history_cf:          544 = 544  ✓
ppe_components:      273 = 273  ✓
intangible_assets:    24 =  24  ✓
tax_schedule:          6 =   6  ✓
provisions_schedule:  20 =  20  ✓
associates_schedule:  54 =  54  ✓
operational_drivers:  73 =  73  ✓
debt_instruments:     69 =  69  ✓
lease_schedule:        4 =   4  ✓
equity_schedule:      15 =  15  ✓
BS Identity: 13/13 years OK
overall: PASS
```
