# Phase 1 Prep — Rusal
**Generated:** 2026-04-21

## Block 1 — excel_loader.yaml

**Path:** `companies/rusal/configs/excel_loader.yaml`

```yaml
# ═══════════════════════════════════════════════════════════════
# UC RUSAL — Excel Loader Configuration
# ═══════════════════════════════════════════════════════════════
# Source: companies/rusal/data/rusal_unified_complete.xlsx
# Format: Legacy wide (metric × years), unit = mUSD
#
# Usage:
#   from engine.loader.excel import ExcelLoader
#   from engine.database.repository import Repository
#   from engine import DB_PATH
#
#   with Repository(DB_PATH) as repo:
#       loader = ExcelLoader(
#           company_id="rusal", repo=repo,
#           db_unit="USD", input_default_unit="mUSD",
#       )
#       result = loader.load(Path("companies/rusal/data/rusal_unified_complete.xlsx"))

loader_settings:
  company_id: rusal
  db_unit: USD
  input_default_unit: mUSD      # Excel values in millions USD → ×1e6 → full USD in DB

# ─── Statement Sheets (legacy wide: metric | 2011 | 2012 | ... | unit) ──────

history:
  IS:
    sheet: history_is
    format: legacy
    required_metrics:
      - revenue
      - cogs
      - gross_profit
      - sga
      - ebitda
      - ebit
      - ebt
      - tax_expense
      - net_income
    key_optional:
      - dep_ppe
      - amort_intangibles
      - total_da
      - interest_expense
      - interest_income
      - earnings_from_investees
      - asset_impairment
      - distribution_expenses
      - current_tax
      - deferred_tax

  BS:
    sheet: history_bs
    format: legacy
    required_metrics:
      - cash
      - accounts_receivable
      - inventory
      - ppe_net
      - short_term_debt
      - long_term_debt
      - accounts_payable
      - retained_earnings
      - total_assets
      - total_equity
    key_optional:
      - ppe_gross
      - ppe_accum_dep
      - investments_lt
      - intangibles
      - goodwill
      - rou_asset
      - dta
      - dtl
      - share_capital
      - apic
      - aoci
      - nci
      - other_ca
      - other_cl
      - other_nca
      - other_ncl
      - total_liabilities

  CF:
    sheet: history_cf
    format: legacy
    required_metrics:
      - cfo_total
      - cfi_total
      - cff_total
    key_optional:
      - cfo_net_income
      - cfo_da
      - cfo_before_wc
      - cfo_interest_paid
      - cfo_income_tax_paid
      - capex
      - cff_lt_debt_issuance
      - cff_lt_debt_repayment
      - cff_dividends

# ─── Canonical Sheets ────────────────────────────────────────────────────────

canonical:
  debt_instruments:
    sheet: debt_instruments
    key: instrument_id
    # 31 instruments: CNY bonds, RUB bonds, floating KeyRate+spread

  macro_factors:
    sheet: macro_factors
    key: factor_name
    # 22 factors: LME Al/Alumina, USD/RUB, Brent, GDP, CPI/PPI RU, Power

  segments_financial:
    sheet: segments_financial
    keys: [segment_name, metric]
    # 4 segments: Primary Aluminium, Alumina, Foil & Other, Other

  segments_operational:
    sheet: segments_operational
    keys: [segment_name, metric]
    # Production/sales volumes, avg prices, segment costs

  Production_KPI:
    sheet: Production_KPI
    key: metric
    target: preprocess_metrics
    # 12 KPIs: production volumes, prices, segment revenues

# ─── Sign Convention ─────────────────────────────────────────────────────────
# IFRS "natural" signs: revenue/income = positive, expenses/costs = negative
# Configured in project.yaml → accounting_conventions.is_income_sign: natural

```

### Alias Analysis

| Section | Key | Type |
|---------|-----|------|
| loader_settings | company_id | str |
| loader_settings | db_unit | str |
| loader_settings | input_default_unit | str |
| history | IS | dict |
| history | BS | dict |
| history | CF | dict |
| canonical | debt_instruments | dict |
| canonical | macro_factors | dict |
| canonical | segments_financial | dict |
| canonical | segments_operational | dict |
| canonical | Production_KPI | dict |

**Note:** This yaml is descriptive (lists required/optional metrics), NOT a mapping yaml.
It does NOT contain alias resolution rules. Aliases live in the ExcelLoader code.
Total metric names listed: 58

## Block 2 — PPE Values Check

| Year | ppe_gross | ppe_accum_dep | ppe_net | computed (gross+accum) | diff | flags |
|------|----------|--------------|---------|----------------------|------|-------|
| 2011 | 20,257 | 14,511 | 5,746 | 5,746 | 0 | ✅ |
| 2012 | 19,224 | 13,771 | 5,453 | 5,453 | 0 | ✅ |
| 2013 | 14,690 | 10,523 | 4,167 | 4,167 | 0 | ✅ |
| 2014 | 13,936 | 9,983 | 3,953 | 3,953 | 0 | ✅ |
| 2015 | 13,587 | -9,733 | 3,854 | 3,854 | 0 | ✅ |
| 2016 | 13,653 | -9,588 | 4,065 | 4,065 | 0 | ✅ |
| 2017 | 14,520 | 10,197 | 4,323 | 4,323 | 0 | ✅ |
| 2018 | 14,857 | -10,436 | 4,421 | 4,421 | 0 | ✅ |
| 2019 | 15,728 | -11,229 | 4,499 | 4,499 | 0 | ✅ |
| 2020 | 16,973 | 12,118 | 4,855 | 4,855 | 0 | ✅ |
| 2021 | 17,093 | 11,743 | 5,350 | 5,350 | 0 | ✅ |
| 2022 | 18,623 | -12,794 | 5,829 | 5,829 | 0 | ✅ |
| 2023 | 16,514 | -10,708 | 5,806 | 5,806 | 0 | ✅ |
| 2024 | 17,341 | 11,336 | 6,005 | 6,005 | 0 | ✅ |
| 2025 | 20,304 | 13,273 | 7,031 | 7,031 | 0 | ✅ |

**PPE values: OK**

## Block 3 — Hidden Metrics Search

### BS: investments/associates
- `investments_lt` (15 years)

### IS: ebitda/adjusted
- `ebitda` (11 years)

### CF: revolving/wc/working
- `cfo_before_wc` (15 years)
- `wc_inventory` (9 years)
- `wc_provisions` (15 years)
- `wc_payables` (3 years)
- `wc_receivables` (3 years)

### CF: dividends
- `cff_dividends` (15 years)
- `dividends_from_associates` (11 years)

### CF: debt/borrowing
- `cff_lt_debt_issuance` (15 years)
- `cff_lt_debt_repayment` (15 years)
- `proceeds_borrowings` (15 years)
- `repayments_borrowings` (15 years)

### CF: interest/tax paid
- `cfo_income_tax_paid` (15 years)
- `cfo_interest_paid` (15 years)
- `interest_paid` (15 years)
- `taxes_paid` (7 years)

### CF: lease
- `fin_lease_principal_cff` (6 years)
- `op_lease_cash_cfo` (6 years)

### IS: deferred_tax variants
- `deferred_tax` (15 years)

### IS: depreciation variants
- `dep_ppe` (15 years)

## Block 4 — Sheet Coverage: xlsx vs loader

| Sheet | Data in xlsx | In loader | Status |
|-------|-------------|-----------|--------|
| Production_KPI | 12/12 (100%) | Y | Y/Y ✅ |
| balancing_adjustments | 0/0 (0%) | N | N/N — |
| debt_cashflows | 0/3 (0%) | Y | N/Y — loader expects empty sheet |
| debt_instruments | 0/31 (0%) | Y | N/Y — loader expects empty sheet |
| dictionary_debt_types | 0/0 (0%) | N | N/N — |
| dictionary_metrics | 0/0 (0%) | N | N/N — |
| dictionary_segments | 0/5 (0%) | N | N/N — |
| dictionary_units | 0/0 (0%) | N | N/N — |
| history_bs | 36/36 (100%) | Y | Y/Y ✅ |
| history_cf | 45/79 (57%) | Y | Y/Y ✅ |
| history_is | 21/36 (58%) | Y | Y/Y ✅ |
| intangible_assets | 0/0 (0%) | Y | N/Y — loader expects empty sheet |
| interest_paid_split | 0/0 (0%) | N | N/N — |
| lease_maturity_ladder | 0/0 (0%) | N | N/N — |
| lease_schedule | — | Y | N/Y — loader expects empty sheet |
| macro_factors | 22/22 (100%) | Y | Y/Y ✅ |
| meta | 0/0 (0%) | N | N/N — |
| operational_drivers | 0/0 (0%) | N | N/N — |
| ppe_components | 0/0 (0%) | Y | N/Y — loader expects empty sheet |
| revenue_segments | 0/5 (0%) | N | N/N — |
| sched_lease_finance | 0/0 (0%) | Y | N/Y — loader expects empty sheet |
| sched_lease_operating | 0/0 (0%) | Y | N/Y — loader expects empty sheet |
| sched_tax_corkscrew | 0/0 (0%) | N | N/N — |
| sched_wc_corkscrew | 0/0 (0%) | N | N/N — |
| schedule_equity | 0/0 (0%) | Y | N/Y — loader expects empty sheet |
| schedule_interest | 0/0 (0%) | N | N/N — |
| schedule_leases | 5/21 (24%) | N | Y/N ⚠ data not loaded! |
| schedule_ppe | 0/5 (0%) | N | N/N — |
| schedule_tax | 0/5 (0%) | Y | N/Y — loader expects empty sheet |
| schedule_working_capital | 0/0 (0%) | N | N/N — |
| segments_financial | 4/4 (100%) | Y | Y/Y ✅ |
| segments_mdna | 0/0 (0%) | N | N/N — |
| segments_operational | 3/7 (43%) | Y | Y/Y ✅ |

---
## Summary

- **loader yaml:** descriptive format (no alias mapping), lists ~58 metric names
- **PPE values:** OK
- **Sheet coverage mismatches:** 10