# Corporate Model v4 — Detailed Implementation Plan

## Architecture: Python generates, Excel calculates (bank model pattern)

### Phase 1: Skeleton ✅ DONE (30 sheets, 712 formulas)
### Phase 2: Data fill ✅ DONE (Rusal 1337, Nornickel 1214 data cells)
### Phase 3: Cross-sheet linking ✅ DONE (BS←corkscrews, PL←engines, CF←sources)
### Phase 3.5: BS Balance ✅ DONE (Check=-516, was -17503)

---

## Phase 4: Preprocessing Layer (CURRENT)

### 4.1 EWA Calibration in Excel
Python preprocessor computes EWA ratios from history → stored in preprocess_metrics.
In Excel: compute directly from 02_Hist data using SUMPRODUCT formulas.

**03_Assump sheet** becomes the preprocessing engine:
- Section 1: Margin ratios (COGS/Rev, SGA/Rev, EBITDA margin)
  - Formula: SUMPRODUCT with exponential weights over history years
  - EWA halflife = 3 years (configurable in Control_Panel)
  - Winsorized: clip at historical P10/P90

- Section 2: WC Days (DSO, DIH, DPO)
  - DSO = AR/Rev × 365 per year → EWA of DSO series
  - DIH = INV/COGS × 365 per year → EWA
  - DPO = AP/COGS × 365 per year → EWA

- Section 3: CapEx / DA
  - CapEx/Rev ratio → EWA
  - DA/PPE_net ratio (dep_rate) → EWA
  - Sustaining ratio = CapEx/DA → EWA

- Section 4: Debt
  - Avg interest rate = Interest/AvgDebt → EWA
  - ND/EBITDA history

- Section 5: Tax
  - Effective tax rate = Tax/EBT → EWA
  - Current/deferred split

- Section 6: Equity
  - Payout ratio = Dividends/NI → EWA

### 4.2 Macro Factor Model in Excel
**01_Macro** enhanced with econometric display:
- Revenue beta: OLS β from Δln(Rev) ~ Δln(Factor)
  - Computed in 03_Assump using SLOPE/INTERCEPT formulas on historical dln series
  - Displayed in 01_Macro for transparency
- COGS factor: PPI beta from Δln(COGS/Rev) ~ Δln(PPI)
- Revenue forecast: Rev_t = Rev_{t-1} × (1 + β × Δln(Factor_t))

### 4.3 Revenue Segment Model
**10_Revenue** uses EWA-calibrated growth rates:
- Volume: EWA of historical growth → carry forward or macro-driven
- Price: β × Δln(LME_factor) or EWA
- Revenue = Volume × Price (already implemented)

---

## Phase 5: Debt Circular Optimizer

### 5.1 Python Logic (from core.py _solve_debt)
```
for each forecast year:
    1. mandatory_repay = scheduled amortization
    2. pre_cash = cash_opening + CFO + CFI - mandatory
    3. if pre_cash < min_cash: draw = min_cash - pre_cash
    4. if pre_cash > 1.5 × min_cash: voluntary_repay = surplus
    5. interest = avg(open, close) × rate
    6. close = open + draw - mandatory - voluntary
```

### 5.2 Excel Implementation
**17_Debt** formulas:
- Mandatory: input or percentage of opening balance
- Draw: =MAX(0, min_cash - pre_financing_cash)
- Voluntary: =MAX(0, post_draw_cash - 1.5 × min_cash)
- This creates circular ref (draw → interest → NI → CFO → cash → draw)
- Solved by Excel Iterative Calculation (already enabled)

### 5.3 Circular Chain
```
17_Debt.draw → 17_Debt.interest → 21_PL.interest → 21_PL.NI
  → 23_CF.NI → 23_CF.CFO → 23_CF.cash_close → 20_BS.cash
  → 17_Debt.draw (circular!)
```

---

## Phase 6: Complete Corkscrews

### 6.1 Intangibles (from Python)
- Additions = 0.3% of Revenue
- Amortization = 5% of balance
- Close = Open + Additions - Amort

### 6.2 Provisions (from Python)
- Pension: charge 12%, utilization 8%
- Site restoration: accretion 2%
- Legal: charge 30%, utilization 20%

### 6.3 Lease (IFRS 16)
- ROU: Open - Dep = Close
- Liability: Open + Interest - Payment = Close
- Discount rate from Control_Panel

---

## Phase 7: Validation & Polish

### 7.1 90_Checks Enhanced
- BS Identity: TA - TL - TE = 0 (per year)
- CF Bridge: ΔCash(BS) = CFO + CFI + CFF
- PPE Rollforward: net_close = gross_close - dep_close
- Debt Rollforward: close = open + draw - repay
- Equity Rollforward: re_close = re_open + NI - div
- Error count: COUNTIF(checks <> 0)

### 7.2 Model_Output Enhanced
- Compare history vs forecast (trend arrows)
- Key ratio traffic lights (green/yellow/red)

### 7.3 Nornickel Build
- Same structure, different parameters
- 5 segments (Ni/Cu/Pd/Pt/Other)

---

## Key Principles (from bank model)
1. openpyxl writes formulas, Excel calculates
2. AppleScript for recalc (10 iterations) and reading values
3. No fullCalcOnLoad — preserve cached values
4. NORMSDIST not NORM.S.DIST
5. Notes must NOT start with '='
6. Column alignment: ALL sheets use same C-E=hist, F-H=fc layout
7. Data fills AFTER build, before Excel recalc
8. reg.json = single source of truth for row numbers
