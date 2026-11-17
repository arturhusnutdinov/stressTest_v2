# Audit Fixes Tracker (from AUDIT_RUSAL.md)

## Priority 1 — BLOCKING

### 1.1 Revenue: segments cover 74% not 100%
- "Other (VAP, foil)" segment has 0 volume/price → missing ~25% of revenue
- Fix: Reconciliation row = Reported - Σ segments (carries forward to forecast)
- Status: **FIXED** ✅ — Rev $14,321M (was $10,546M)

### 1.2 Cash goes negative in 2027-2028
- Revolver doesn't work for years 2/3 (only year 1 uses prev_cash)
- Mandatory repay = 0 (despite 15 instruments maturing 2026-2027)
- Fix: implement maturity schedule from instrument table
- Interest_paid = 0 in CFF (should be non-zero for IFRS CFF presentation)
- Status: **FIXED** ✅

## Priority 2 — STRUCTURAL

### 2.1 Valuation broken (14 #VALUE!)
- WACC formula references text cell ("2026E" instead of number)
- EV references sensitivity matrix instead of NPV
- Net Debt references col I (beyond horizon)
- Fix: rebuild valuation with separate WACC block, clear row layout
- Status: **FIXED** ✅

### 2.2 Checks don't catch #VALUE!
- COUNTIF(ABS>1) doesn't detect errors
- Need: SUMPRODUCT(--ISERROR()) pattern from bank model
- Add: convergence residual, traffic light on cover
- Status: **FIXED** ✅

### 2.3 Interest sign convention
- History: -573 / -531 / -1155 (negative = expense)
- Forecast: +1155 (positive, but PL formula subtracts)
- Fix: ensure consistent sign (always negative for expense)
- Status: **FIXED** ✅

## Priority 3 — DATA

### 3.1 NOL doesn't accumulate losses
- When NI < 0: NOL should increase by |NI|
- Current: NOL only decreases (used) or stays flat
- Fix: NOL_close = NOL_open - used + MAX(0, -EBT)
- Status: **FIXED** ✅

### 3.2 Avg rate should be from instruments
- Currently: hardcoded 12.03%
- Should: weighted average from instrument table (CNY 4.75-8.5%, RUB 14-15%)
- Status: **FIXED** ✅

### 3.3 BS history gaps
- Goodwill: 2156 → 0 (not carried properly)
- ROU: 31 → empty
- Other NCA: 2963 → 7177 (inconsistent)
- Tax payable: -222 (negative liability)
- Status: **PARTIALLY FIXED** (Other CL/NCA from totals)

## Priority 4 — POLISH

### 4.1 Macro scenario = 0
- All LME/FX/GDP forecast values = 0 in scenario rows
- Only historical section filled
- Fix: link scenario values to macro forecasts
- Status: **FIXED** ✅

### 4.2 03_Assump not connected
- 142 formulas but no incoming references from engine sheets
- Preprocessing computes ratios but nothing uses them
- Status: **FIXED** ✅

### 4.3 Ergonomics
- No sheet protection (bank model: 24/26)
- No data validation (bank model: 7)
- No row grouping (bank model: 428)
- 129 cells with General format
- Status: **FIXED** ✅

### 4.4 calcPr settings
- Missing: iterateCount, iterateDelta
- Need: 1000 / 1e-6 like bank model
- fullCalcOnLoad: controversial (bank model avoids it)
- Status: **FIXED** ✅

## Round v10 (17.11) — чекап против принципов bank_model
Источник: audit/CHECKUP_PRINCIPLES_2026-11-17.md (полный чекап + remediation).

1. **[FAIL→PASS] E2 годовая сетка** — двойной дефект: (а) builder писал заголовок
   лет FCFF в C:E при данных в F:H (стало col_start=3+n_hist); (б) аудитор E2
   брал год по одной сетке на лист — стал ближайший заголовок ВЫШЕ ячейки,
   скаляры вне сетки (WACC, «Net Debt последний прогнозный год», SOTP-terminal)
   пропускаются. Итог: «0 смещений» в обеих книгах.
2. **[BEHAVIORAL] new_term-гейт** — при EBITDA≤0 срочный драфт закрыт полностью
   (включая штрафной тракт); it_res (90_Checks #C3) срабатывает только при
   открытом рынке (недофинансированный разрыв = флаг стресса, не ошибка книги).
   verify_model: ALL BEHAVIORAL TESTS PASS ×2.
3. **[PARAM] CP.day_count** — литералы 365 в 03_Assump/16_WC заменены ссылкой
   на параметр Control_Panel (H1: 130→103 и 136→109 оставшихся литералов —
   остаток в 17_Debt: спреды/теноры, следующий раунд).
4. **[F5] Метки источников** — 0 констант без [ДАННЫЕ/РАСЧЁТ/ОЦЕНКА/НОРМ]-тега
   (day_count, CapEx floor).
5. **[TOPOLOGY] calcPr** — iterate снят обеими книгами (чистый DAG, 0 SCC),
   единая топология согласно DESIGN.md.

Остаток (WARN, задокументировано): D8 ABS-в-суммах (57/42), H1 литералы 17_Debt,
82/123 ссылок на пустые ячейки (carry-forward по дизайну, тождества = 0).
