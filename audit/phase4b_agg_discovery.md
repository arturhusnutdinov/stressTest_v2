# Phase 4b-ii-agg Discovery Report

**Date:** 2026-04-21
**Company:** Rusal (IFRS, mUSD)
**PDF:** RUSAL_consolidated_financial_statement_12m2024_ENG.pdf, page 11
**Years tested:** 2024, 2023

---

## 1. DB Aggregate Metrics (history_bs, 2024, mUSD)

| Metric | DB value | Type |
|--------|----------|------|
| other_ca | 883 | aggregate |
| other_ca_tax | 30 | separate |
| other_cl | 542 | aggregate |
| taxes_payable | 157 | separate |
| lease_liab_current | 5 | separate (Excel/Notes) |
| aoci | -11,205 | aggregate |
| nci | 2,856 | separate |
| other_ncl | 275 | aggregate |
| lease_liab_noncurrent | 42 | separate (Excel/Notes) |
| employee_benefits | 45 | separate (Excel/Notes) |
| investments_lt | 3,026 | different breakdown vs PDF |
| goodwill | 2,014 | separate (Excel/Notes) |
| rou_asset | 45 | separate (Excel/Notes) |

---

## 2. PDF Face Rows (unmatched, page 11)

### NCA (rows not currently parsed)
| Row | PDF line | 2024 | 2023 |
|-----|----------|------|------|
| 12 | Derivative financial assets | - | 13 |
| 13-14 | Investments in equity securities measured at fair value through profit and loss | 217 | 339 |

### CA (rows not currently parsed)
| Row | PDF line | 2024 | 2023 |
|-----|----------|------|------|
| 20 | Short-term investments | 112 | 125 |
| 22 | Prepayments and input VAT | 721 | 538 |
| 23 | Current income tax receivables | 30 | 8 |
| 24 | Dividends receivable | 29 | 412 |
| 25 | Derivative financial assets | 19 | 19 |

### Equity (rows not currently parsed)
| Row | PDF line | 2024 | 2023 |
|-----|----------|------|------|
| 35 | Other reserves | 2,856 | 2,689 |
| 36 | Currency translation reserve | (11,205) | (10,613) |

### NCL (rows not currently parsed)
| Row | PDF line | 2024 | 2023 |
|-----|----------|------|------|
| 42 | Provisions | 243 | 269 |
| 44 | Other non-current liabilities | 119 | 155 |

### CL (rows not currently parsed)
| Row | PDF line | 2024 | 2023 |
|-----|----------|------|------|
| 50 | Advances received | 420 | 218 |
| 51 | Other tax payable | 157 | 233 |
| 52 | Dividends payable | 5 | 5 |
| 54 | Derivative financial liabilities | 26 | - |
| 55 | Provisions | 96 | 114 |

---

## 3. Hypothesis Results

### aoci — DIRECT MAP

```
aoci = currency_translation_reserve
2024: -11,205 = -11,205  ✅ exact
```

**Action:** Add `aoci` row with pattern `^currencytranslationreserve`, sections: [equity].

---

### nci — DIRECT MAP

```
nci = other_reserves
2024: 2,856 = 2,856  ✅ exact
```

**Note:** DB calls this `nci` (non-controlling interests), PDF calls it "Other reserves". The Rusal "Other reserves" line is entirely NCI per IFRS Note 18.

**Action:** Add `nci` row with pattern `^otherreserves`, sections: [equity].

---

### other_ca — ADDITIVE (4 PDF lines)

```
other_ca = short_term_investments + prepayments_and_input_vat
         + dividends_receivable + derivative_financial_assets_ca

2024: 112 + 721 + 29 + 19 = 881  (DB=883, Δ=2, cash rounding)
2023: 125 + 538 + 412 + 19 = 1,094  (DB=1,094) ✅ exact
```

**Note:** 2024 Δ=2 due to cash rounding (parser=1503, DB=1501). From DB perspective: other_ca = total_ca - inventory - AR - cash - other_ca_tax = 8361 - 4477 - 1470 - 1501 - 30 = 883.

**Action:** Add `combine_from` support to parser. New rows:
- `_short_term_investments` (pattern: `^short-terminv`, sections: [current_assets])
- `_prepayments_vat` (pattern: `^prepaymentsa?ndinputvat`, sections: [current_assets])
- `_dividends_receivable` (pattern: `^dividendsrece`, sections: [current_assets])
- `_derivative_assets_ca` (pattern: `^derivativefina.*assets`, sections: [current_assets])

Then: `other_ca: combine_from: [_short_term_investments, _prepayments_vat, _dividends_receivable, _derivative_assets_ca]`

Separately: `other_ca_tax` → pattern `^currentincom.*taxreceivables`, sections: [current_assets]

---

### other_cl — ADDITIVE (3 PDF lines)

```
other_cl = advances_received + derivative_financial_liabilities + provisions_cl

2024: 420 + 26 + 96 = 542  ✅ exact match with DB
```

**Verification (residual):** total_cl - STD - AP - taxes_payable - dividends_payable = 6759 - 4520 - 1535 - 157 - 5 = 542 ✅

**Action:** New rows:
- `_advances_received` (pattern: `^advancesrece`, sections: [current_liab])
- `_derivative_liab_cl` (pattern: `^derivativefina.*liabilities`, sections: [current_liab])
- `_provisions_cl` (pattern: `^provisions`, sections: [current_liab])

Then: `other_cl: combine_from: [_advances_received, _derivative_liab_cl, _provisions_cl]`

Separately:
- `taxes_payable` → pattern `^othertaxpaya`, sections: [current_liab]
- `dividends_payable` → pattern `^dividendspay`, sections: [current_liab]

---

### other_ncl — CANNOT match DB from PDF face

```
PDF face: provisions_ncl(243) + other_ncl_line(119) = 362
DB:       other_ncl(275) + lease_liab_noncurrent(42) + employee_benefits(45) = 362  ✅

DB "other_ncl" is a sub-split of the face total:
  362 - 42 (lease) - 45 (employee benefits) = 275
```

The DB has Notes-level detail (lease_liab_noncurrent, employee_benefits) that is embedded within Provisions and Other NCL on the PDF face. **Cannot reconstruct DB's exact other_ncl from face alone.**

**Action — two options:**
1. **Use residual:** `other_ncl = total_ncl - LTD - DTL` = 362. Accept mismatch (362 vs 275) — the parser captures ALL NCL residual items.
2. **Combine PDF lines:** provisions_ncl + other_ncl_line = 362. Same result, explicit.

**Recommendation:** Option 2 (additive), with a note that parser's `other_ncl` includes lease_liab_noncurrent and employee_benefits that the DB tracks separately. The model loader should handle the mapping.

---

### investments_in_associates — DIFFERENT BREAKDOWN

```
PDF face:  investments_in_associates(4,868) + investments_equity_fvpl(217) = 5,085
DB (Excel): investments_lt(3,026) + goodwill(2,014) + rou_asset(45) = 5,085  ✅
```

The DB uses Notes-level breakdown. The PDF face shows consolidated line items that don't decompose the same way.

**Action:** Parser correctly extracts `investments_in_associates = 4,868`. The loader maps this to `investments_lt` in the DB but the values differ because the DB splits goodwill and ROU out. This is a **loader mapping issue**, not a parser issue. Two options:
1. Leave as-is — parser provides face value; Excel/DB has Notes detail.
2. Add `investments_equity_fvpl` pattern and let the model decide.

**Recommendation:** Add `_investments_fvpl` as a helper row for completeness, but do not try to split investments_in_associates to match DB's investments_lt + goodwill + rou_asset. That data only exists in Notes.

---

## 4. Contract for Phase 4b-ii-agg Implementation

### Parser changes (pdf_parser.py)
1. Add `combine_from` support to `_map_rows()`:
   - After individual row matching, compute aggregate metrics by summing component rows
   - Components prefixed with `_` are helper rows (not emitted in final metrics unless combine_from references them)

### YAML changes (rusal.yaml BS section)

**New direct rows:**
| canonical | pattern | section |
|-----------|---------|---------|
| aoci | `^currencytranslationreserve` | equity |
| nci | `^otherreserves` | equity |
| other_ca_tax | `^currentincom.*taxreceivables` | current_assets |
| taxes_payable | `^othertaxpaya` | current_liab |
| dividends_payable | `^dividendspay` | current_liab |

**New helper rows (prefixed _):**
| helper | pattern | section |
|--------|---------|---------|
| _short_term_investments | `^short-?terminv` | current_assets |
| _prepayments_vat | `^prepayments` | current_assets |
| _dividends_receivable | `^dividendsrece` | current_assets |
| _derivative_assets_ca | `^derivativefina.*assets` | current_assets |
| _advances_received | `^advancesrece` | current_liab |
| _derivative_liab_cl | `^derivativefina.*liabilities` | current_liab |
| _provisions_cl | `^provisions` | current_liab |
| _provisions_ncl | `^provisions` | non_current_liab |
| _other_ncl_line | `^othernon-?currentliabilities` | non_current_liab |
| _investments_fvpl | `^investmentsinequity` | non_current_assets |

**New combine_from:**
| aggregate | components |
|-----------|------------|
| other_ca | _short_term_investments + _prepayments_vat + _dividends_receivable + _derivative_assets_ca |
| other_cl | _advances_received + _derivative_liab_cl + _provisions_cl |
| other_ncl | _provisions_ncl + _other_ncl_line |

### Expected smoke test results after implementation
| metric | parser | DB | status |
|--------|--------|-----|--------|
| aoci | -11,205 | -11,205 | ok |
| nci | 2,856 | 2,856 | ok |
| other_ca | 881 | 883 | ~ok (Δ=2, cash rounding) |
| other_ca_tax | 30 | 30 | ok |
| other_cl | 542 | 542 | ok |
| other_ncl | 362 | 275 | EXPECTED MISMATCH (+87, lease+empl_ben) |
| taxes_payable | 157 | 157 | ok |
| investments_in_associates | 4,868 | N/A (DB=investments_lt=3,026) | N/A |

### Known limitations
1. **other_ncl:** Parser will return 362 (provisions+other), DB has 275. Gap = lease_liab_noncurrent(42) + employee_benefits(45). These are Notes-level items not visible on BS face.
2. **investments_in_associates vs investments_lt:** Different granularity. PDF=4,868 includes goodwill(2,014)+ROU(45) that DB tracks separately.
3. **cash rounding:** Parser reads 1,503 from PDF, DB has 1,501 from Excel. Causes 2 mUSD variance in other_ca residual check.

---

**Status: DISCOVERY COMPLETE**
Ready for Phase 4b-ii-agg implementation.
