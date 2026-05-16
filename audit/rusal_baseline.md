# Rusal Baseline Audit
**Generated:** 2026-04-21

## 1. Summary
- PDFs: 0 found
- xlsx template: companies/rusal/data/rusal_unified_complete.xlsx (88KB)
- xlsb prototype: 3-Statement Model (Template)_Rusal_1.xlsb (found)
- DB: data_mart_v2.db

## 2. Sanity Check
- us_steel BS=0.00 ✅
- rusal BS=0.00 ✅
- DB exists: True ✅

## 4. xlsx Template Status
| Sheet | Rows | Metrics | Years | Fill% |
|---|---|---|---|---|
| history_is | 39 | 36 | [2011, 2012, 2013]...[2025] | 58% |
| history_bs | 40 | 36 | [2011, 2012, 2013]...[2025] | 100% |
| history_cf | 82 | 79 | [2011, 2012, 2013]...[2025] | 57% |
| schedule_leases | 24 | 21 | [2010, 2011, 2012]...[2024] | 24% |
| schedule_ppe | 8 | 5 | [2010, 2011, 2012]...[2024] | 0% |
| schedule_tax | 8 | 5 | [2010, 2011, 2012]...[2024] | 0% |
| debt_instruments | 34 | 31 | []...[] | 0% |
| debt_cashflows | 7 | 3 | []...[] | 0% |
| segments_financial | 7 | 4 | [2011, 2012, 2013]...[2024] | 100% |
| segments_operational | 33 | 7 | [2011, 2012, 2013]...[2024] | 43% |
| revenue_segments | 78 | 5 | []...[] | 0% |
| dictionary_segments | 8 | 5 | []...[] | 0% |
| Production_KPI | 13 | 12 | [2011, 2012, 2013]...[2024] | 100% |
| macro_factors | 23 | 22 | [2011, 2012, 2013]...[2025] | 100% |

## 6. DB Status for Rusal

### history_is (21 metrics)
| Metric | Years | Range |
|---|---|---|
| amort_intangibles | 10 | 2011-2025 |
| asset_impairment | 14 | 2011-2025 |
| cogs | 15 | 2011-2025 |
| current_tax | 15 | 2011-2025 |
| deferred_tax | 15 | 2011-2025 |
| dep_ppe | 15 | 2011-2025 |
| distribution_expenses | 15 | 2011-2025 |
| earnings_from_investees | 15 | 2011-2025 |
| ebit | 15 | 2011-2025 |
| ebitda | 11 | 2015-2025 |
| ebt | 15 | 2011-2025 |
| expected_credit_losses | 1 | 2024-2024 |
| gross_profit | 15 | 2011-2025 |
| interest_expense | 15 | 2011-2025 |
| interest_income | 15 | 2011-2025 |
| net_income | 15 | 2011-2025 |
| other_operating_expenses | 2 | 2023-2024 |
| revenue | 15 | 2011-2025 |
| sga | 15 | 2011-2025 |
| tax_expense | 15 | 2011-2025 |
| total_da | 15 | 2011-2025 |

### history_bs (36 metrics)
| Metric | Years | Range |
|---|---|---|
| accounts_payable | 13 | 2013-2025 |
| accounts_receivable | 15 | 2011-2025 |
| aoci | 12 | 2013-2025 |
| apic | 13 | 2013-2025 |
| cash | 15 | 2011-2025 |
| dta | 15 | 2011-2025 |
| dtl | 13 | 2013-2025 |
| employee_benefits | 14 | 2011-2024 |
| goodwill | 7 | 2015-2024 |
| intangibles | 15 | 2011-2025 |
| inventory | 15 | 2011-2025 |
| investments_lt | 15 | 2011-2025 |
| lease_liab_current | 1 | 2024-2024 |
| lease_liab_noncurrent | 5 | 2019-2024 |
| long_term_debt | 13 | 2013-2025 |
| nci | 3 | 2017-2025 |
| other_ca | 15 | 2011-2025 |
| other_ca_tax | 3 | 2023-2025 |
| other_cl | 11 | 2014-2025 |
| other_nca | 15 | 2011-2025 |
| other_ncl | 11 | 2014-2025 |
| ppe_accum_dep | 15 | 2011-2025 |
| ppe_gross | 15 | 2011-2025 |
| ppe_net | 15 | 2011-2025 |
| retained_earnings | 13 | 2013-2025 |
| rou_asset | 5 | 2019-2024 |
| share_capital | 13 | 2013-2025 |
| short_term_debt | 13 | 2013-2025 |
| taxes_payable | 15 | 2011-2025 |
| total_assets | 15 | 2011-2025 |
| total_ca | 15 | 2011-2025 |
| total_cl | 11 | 2014-2025 |
| total_equity | 13 | 2013-2025 |
| total_liabilities | 13 | 2013-2025 |
| total_nca | 15 | 2011-2025 |
| total_ncl | 11 | 2014-2025 |

### history_cf (45 metrics)
| Metric | Years | Range |
|---|---|---|
| acquisitions | 2 | 2024-2025 |
| amortization | 15 | 2011-2025 |
| capex | 15 | 2011-2025 |
| capex_intangibles | 15 | 2011-2025 |
| cash_closing | 15 | 2011-2025 |
| cash_opening | 12 | 2014-2025 |
| cff_dividends | 15 | 2011-2025 |
| cff_lt_debt_issuance | 15 | 2011-2025 |
| cff_lt_debt_repayment | 15 | 2011-2025 |
| cff_total | 15 | 2011-2025 |
| cfi_other | 5 | 2021-2025 |
| cfi_total | 15 | 2011-2025 |
| cfo_before_tax | 12 | 2011-2025 |
| cfo_before_wc | 15 | 2011-2025 |
| cfo_da | 13 | 2011-2025 |
| cfo_income_tax_paid | 15 | 2011-2025 |
| cfo_interest_paid | 15 | 2011-2025 |
| cfo_interest_received | 4 | 2015-2024 |
| cfo_net_income | 2 | 2023-2024 |
| cfo_total | 15 | 2011-2025 |
| deferred_income_taxes | 15 | 2011-2025 |
| depreciation | 15 | 2011-2025 |
| dividends_from_associates | 11 | 2014-2025 |
| fin_lease_principal_cff | 6 | 2019-2024 |
| fx_effect_cash | 14 | 2011-2025 |
| fx_noncash | 8 | 2017-2025 |
| impairment_noncash | 13 | 2011-2025 |
| interest_income_noncash | 15 | 2011-2025 |
| interest_noncash | 15 | 2011-2025 |
| interest_paid | 15 | 2011-2025 |
| interest_received | 15 | 2011-2025 |
| net_change_cash | 15 | 2011-2025 |
| net_income | 14 | 2012-2025 |
| op_lease_cash_cfo | 6 | 2019-2024 |
| proceeds_borrowings | 15 | 2011-2025 |
| proceeds_ppe_disposal | 15 | 2011-2025 |
| refinancing_fees | 12 | 2013-2025 |
| repayments_borrowings | 15 | 2011-2025 |
| share_associates_noncash | 12 | 2014-2025 |
| tax_noncash | 15 | 2011-2025 |
| taxes_paid | 7 | 2019-2025 |
| wc_inventory | 9 | 2011-2025 |
| wc_payables | 3 | 2023-2025 |
| wc_provisions | 15 | 2011-2025 |
| wc_receivables | 3 | 2023-2025 |

### Debt Instruments
- Count: 31
- Total: $9.60B

### Canonical Metrics Table
- Exists in DB: False
- Note: canonical list lives in Python dataclasses (engine/model/inputs.py YearState)

### Alias Checks
- depreciation_owned: 0 rows ❌ missing
- deferred_tax: 15 rows ✅
- deferred_tax_expense: 0 rows ❌ missing

## 7. PDF Status

**Location:** `/Users/arturhusnutdinov/Documents/IT Development/Docker/rusalFinStates/`

| Year | FS (RU) | FS (EN) | Annual Report | 
|------|---------|---------|---------------|
| 2012 | ✅ | — | ✅ |
| 2013 | ✅ | — | ✅ |
| 2014 | ✅ | — | ✅ |
| 2015 | ✅ | — | ✅ |
| 2016 | ✅ | — | ✅ |
| 2017 | ✅ | — | ✅ |
| 2018 | ✅ | — | ✅ |
| 2019 | ✅ | — | ✅ |
| 2020 | ✅ | — | ✅ |
| 2021 | ✅ | — | ✅ |
| 2022 | ✅ | — | ✅ |
| 2023 | ✅ | ✅ | ✅ |
| 2024 | ✅ | ✅ | ✅ |
| 2025 | ✅ | ✅ | — |

**Total:** 31 PDFs, 14 years coverage (2012-2025), text-extractable.
**Best sources for parsing:** ENG FS (2023-2025) — cleaner structure.

## 8. Key Mismatches

### IS metrics in DB but NOT in xlsx (0)

### IS metrics in xlsx but NOT in DB (15)
- amortization
- dep_rou_finance
- dep_rou_operating
- depreciation_owned
- depreciation_rou
- eps_basic
- eps_diluted
- gain_loss_on_disposal
- lease_expense_operating
- lease_interest
- lease_interest_finance
- lease_interest_operating
- other_expense
- other_income
- rnd
