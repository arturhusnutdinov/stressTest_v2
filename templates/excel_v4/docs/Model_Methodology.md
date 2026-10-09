# Методология финансовой модели корпоративного эмитента (v4)

**Версия:** 4.2 — AUDIT FINAL ACCEPTED (8 октября 2026)
**Компании:** UC RUSAL, PJSC MMC Norilsk Nickel
**Подход:** outside-in (публичная МСФО отчётность), 3-statement Excel-driven model
**Статус:** 54/54 тождеств = 0 · Cash=target always · OLS β=0.828 · 11_Segments live · reg.json auto-save

---

## 1. Цель и подход

Шаблон для кредитного анализа корпоративных эмитентов на основе публичной МСФО отчётности.
Модель строит прогноз IS/BS/CF на 3 года и рассчитывает: кредитные коэффициенты, рейтинг
(S&P 4-factor), ковенанты, стресс-тесты (3 сценария + tornado), оценку (DCF + SOTP).

- **Outside-in:** только публичные данные МСФО + макро-факторы (LME, CBR, VECM)
- **3-statement:** IS, BS, CF взаимосвязаны; NI → RE → Equity → BS; Cash из CF Bridge
- **Excel-driven:** ~1200 формул; Python генерирует (openpyxl), Excel считает
- **Zero-circular waterfall:** interest от OPENING → one-pass solution, no iterations needed
- **Gate = rate, not access:** модель ВСЕГДА финансирует компанию; при нарушении ковенантов — по штрафной ставке

---

## 2. Архитектура (31 лист)

| Тип | Листы |
|-----|-------|
| Навигация | 00_Guide, 00_Cover |
| Ввод | Control_Panel (130+ параметров), 01_Macro, 02_Hist, Raw_IFRS |
| Preprocessing | 03_Assump (EWA-калибровка) |
| Engine (IS) | 10_Revenue, 11_Segments, 12_COGS, 13_SGA, 14_OtherIS |
| Engine (BS) | 15_PPE, 16_WC, 17_Debt, 18_Lease, 19_Tax |
| Отчётность | 20_BS, 21_PL, 23_CF, 24_Equity |
| Аналитика | 30_Ratios, 31_Score, 32_Covenants, 33_RevStress, 35_Valuation |
| Стресс | 40_Scen (5 аналитических стресс-сценариев) |
| Контроль | 90_Checks (15 проверок), Model_Output |
| Справочно | _Debt_Schedule (per-instrument), Changelog |

### Цветовая конвенция
- **Синий** — ввод (данные)
- **Чёрный** — формулы
- **Зелёный** — ссылки на другие листы (read-only)
- **Жёлтая заливка** — ключевые допущения

---

## 3. Funding Waterfall (КЛЮЧЕВОЙ БЛОК)

### 3.1 Принцип: модель ВСЕГДА финансирует компанию
```
CFF_base = refi - mandatory - voluntary - lease - div    (детерминировано)
cash_before_RC = cash_open + CFO + CFI + CFF_base        (детерминировано)
need = MAX(0, min_cash - cash_before_RC)
RC_draw = MIN(free_limit, need)
new_term = MAX(0, need - RC_draw) + term_out              ← ВСЕГДА покрывает
CFF = CFF_base + new_term + RC_draw - RC_repay
Cash = cash_open + CFO + CFI + CFF = min_cash             (EXACT, one pass)
```

### 3.2 Gate = ставка, а не доступ
| Состояние ворот | Условие | new_term | Ставка | funding_gap |
|-----------------|---------|----------|--------|-------------|
| **OPEN** | Нет нарушения ковенантов | residual + term_out | Нормальная (spread_base + step × leverage) | 0 |
| **CLOSED** | EBITDA ≤ 0 OR ND/EBITDA > cov OR ICR < cov | residual + term_out | **Штрафная (penalty_rate, 24%)** | = new_term |

- **Компания всегда получает деньги** — cash = min_cash в любом сценарии
- **Штрафная ставка** = плата за риск при нарушении ковенантов
- **funding_gap** = сколько привлечено по штрафной ставке (НЕ непокрытый разрыв)
- **Процент:** term + RC + fee + penalty (penalty = prev_gap_accum × penalty_rate)

### 3.3 Почему нет цикличности
- Все проценты от OPENING balance (не avg)
- CFF_base исключает RC и new_term
- CFO зависит от NI → interest → но interest от opening → детерминировано
- One-pass solution, iterations не нужны

### 3.4 fullCalcOnLoad = True
Холодный старт (raw XML) = тёплый (пересчитанный). Гарантировано тем, что:
- Проценты по новому траншу = 0 в году выдачи (начинаются со следующего)
- Дивиденды от прибыли ПРОШЛОГО года (не текущего)
- Все проценты от OPENING (не от (open+close)/2)

---

## 4. Debt Module (17_Debt + _Debt_Schedule)

### A. Sources & Uses (информационно)
```
USES: Maint_CapEx + Growth_CapEx + ΔNWC + Mandatory + Interest + Dividends
SOURCES: EBITDA - Tax + Refi + Excess_Cash
GAP = funding_need (CF-based, авторитетный расчёт)
```

### B. Term Debt corkscrew
```
Term_close = Term_open - Mandatory + Refi + New_term - Voluntary
Mandatory: из _Debt_Schedule (maturity dates)
Refi: Mandatory × refi_pct (bonds vs bank, сценарный параметр)
New_term: ВСЕГДА покрывает residual (при нарушении — по penalty_rate)
Voluntary: с premium, sweep_pct, covenant stops
```

### C. RC (Revolving Credit)
```
RC_draw = MIN(free_limit, need)
RC_repay = cash_sweep + term_out
RC_close = open + draw - repay
Interest_RC = opening × rc_rate (от OPENING, не avg)
Commit_fee = (limit - opening) × fee_rate
```

### D. Total Debt = Term + RC + FX revaluation

### E. Interest = Term + RC + Fee + Penalty
```
Penalty = prev_gap_accum × penalty_rate
```
Penalty_rate (C72, default 24%) — ставка для долга, привлечённого при нарушении ковенантов.

### F. ST / LT
```
ST = MIN(close, mandatory_NEXT_YEAR + RC_close)    ← IAS 1: next 12 months
LT = MAX(0, close - (mandatory_next + RC_close))   ← скобки обязательны!
```
Covenant reclass (IAS 1.74): CP.cov_reclass=1 AND breach → all debt becomes ST. Default=0 (waiver).

### G. EBITDA Sign Protection
```
Scorecard: IF(EBITDA ≤ 0, 5, formula)  — floor score (не max)
Covenant:  OR(EBITDA ≤ 0, ND/EBITDA > cov)  — всегда breach при отрицательной EBITDA
```

---

## 5. Revenue & COGS

### Revenue = Σ(Volume × Price) по сегментам
- Price = '01_Macro' active scenario row (Base/Stress/Severe)
- Volume = EWA carry-forward из истории

### Component COGS (Rusal)
```
Material (37%): Vol_Al × 1.93 × alumina_price / 1000
Energy (27%): фикс. на тонну × vol × power_index
Labour (12%): фикс. на тонну × vol × CPI_index
Other (24%): фикс. на тонну × vol × PPI_index
```
Операционный рычаг: Energy/Labour фиксированы на тонну → EBITDA эластичен к цене.
Rusal: 3.5x operating leverage (31% drop in price → 111% drop in EBITDA).

---

## 6. Corkscrews

| Corkscrew | Лист | Формула |
|-----------|------|---------|
| PPE | 15_PPE | Gross + CapEx - Disposal = Close; Net = Gross - AccDep |
| WC | 16_WC | DSO/DIH/DPO → AR/INV/AP; ΔNWC → CFO |
| Debt | 17_Debt | Term: Open - Mand + Refi + New - Vol = Close |
| Lease | 18_Lease | ROU: Open - Dep = Close; Liab: Open + Int - Pay = Close |
| Tax | 19_Tax | NOL: Open - Used = Close; DTA/DTL: carry |
| Equity | 24_Equity | RE: Open + NI - Div = Close |

---

## 7. Аналитика

### S&P 4-Factor Rating (31_Score)
| Компонент | Вес | Метрика | Защита EBITDA |
|-----------|-----|---------|---------------|
| Leverage (35%) | ND/EBITDA | IF(EBITDA≤0, 5, MAX(5, 80 - ND/EBITDA × 4.7)) |
| Coverage (30%) | ICR | MAX(5, MIN(88, ICR × 8.8)) |
| Profitability (20%) | EBITDA margin | MAX(5, MIN(82, margin × 400)) |
| Liquidity (15%) | Current ratio | MAX(5, MIN(80, CR × 40)) |

### 40_Scen: 5 аналитических стресс-сценариев
| Сценарий | Шок |
|----------|-----|
| Revenue −20% | Rev × 0.8, EBITDA = base + Rev × (−0.2) × margin |
| Rate +200bp | ΔInterest = Debt × 0.02, ΔNI = −ΔInt × (1−t) |
| FX +10% | Debt reval = Debt × FX_share × 0.1 |
| Refi = 0% | Cash = MAX(0, cash − mandatory), Gap = mandatory − cash |
| Combined | Rev−20% + Rate+200bp + FX+10% |

### DCF Valuation
```
WACC = Ke × we + Kd × (1−t) × wd     (настоящий WACC, без двойного счёта CRP)
FCFF = NOPAT + D&A − CapEx − ΔWC
EV = NPV(FCFF) + PV(TV)
Equity = EV − Net Debt
```

---

## 8. Проверки (15 checks в 90_Checks)

| # | Проверка | Тип |
|---|----------|-----|
| 1 | BS: TA − TL − TE = 0 | Тождество |
| 2 | CF: ΔCash = CFO+CFI+CFF | Тождество |
| 3 | PPE rollforward | Тождество |
| 4 | Debt rollforward | Тождество |
| 5 | Equity rollforward | Тождество |
| 6 | RC ≤ limit | Флаг |
| 7 | Penalty debt (0 = no breach) | Информационно |
| 8 | S&U: need = RC + new_term | Тождество |
| 9 | ST + LT = DT.close | Тождество |
| 10 | DT.close = Term + RC + FX | Тождество |
| 11 | Cash ≥ min_cash | Флаг |
| 12 | Maint capex not debt-financed | Флаг |
| 13 | Int = Term + RC + Fee + Penalty | Тождество |
| 14 | Невязка кольца | Тождество |
| 15 | ОШИБОК ВСЕГО | Сумма |

**Статус: ALL = 0 для обеих компаний во всех 3 сценариях (Base/Stress/Severe)**

---

## 9. Сценарии (верифицировано в Excel, 09.10.2026)

Scenario design:
- **Base**: web consensus (Al 2800, Alumina 450, USD/RUB 85→99)
- **Stress**: commodity −20%, FX +15% devaluation, CPI/PPI +2pp
- **Severe**: commodity −40%, FX = Base (pure price shock, shows true leverage)

### Rusal (all identities = 0)
| Сценарий | EBITDA Y1/Y2/Y3 | Rating Y1/Y2/Y3 | Cash |
|----------|-----------------|-----------------|------|
| Base (Al 2800) | 2,967 / 3,494 / 3,499 | BB / BBB / BBB | 2,245→3,431 |
| Stress (Al 2240+FX) | 980 / 395 / −90 | CCC / D / D | 694→500 |
| Severe (Al 1680) | 941 / 337 / −222 | CCC / D / D | 840→500 |

WAC: **9.6%→9.0%** | COGS FX: ÷(1+ΔUSD/RUB) | Dividends: 50% payout
Severe < Stress in Y3 (−222 vs −90) — pure price shock shows true operating leverage

### Nornickel (all identities = 0)
| Сценарий | EBITDA Y1/Y2/Y3 | Rating Y1/Y2/Y3 | Cash |
|----------|-----------------|-----------------|------|
| Base | 4,179 / 4,354 / 4,529 | BBB / BBB / BBB | 1,483→500 |
| Stress | 3,559 / 3,384 / 3,209 | BBB / BB / BB | 1,324→500 |
| Severe | 2,950 / 2,776 / 2,643 | BB / BB / BB | 1,336→500 |

Nornickel: 0 flags even in Severe (strong credit profile)

---

## 10. Пайплайн сборки

```bash
cd stressTest_v2/templates/excel_v4

# 1. Сборка (ОБЯЗАТЕЛЬНО -B или rm __pycache__)
python3 -B scripts/build_model.py --company rusal
python3 -B scripts/fill_data.py --company rusal --model model/model_v4.xlsx

# 2. Пересчёт в Excel (AppleScript)
osascript -e 'tell application "Microsoft Excel" to calculate'
# × 25 раз

# 3. Верификация
python3 -B scripts/verify_model.py model/model_rusal.xlsx

# ЗАПРЕЩЕНО: открывать пересчитанный файл в openpyxl (стирает cache)
```

---

## 11. Ключевые паттерны (для разработки)

| Паттерн | Правило |
|---------|---------|
| __pycache__ | `python3 -B` или `rm -rf __pycache__` перед КАЖДОЙ сборкой |
| Проценты | ВСЕ от OPENING balance (instruments + RC + synthetics) |
| Новый транш | Проценты = 0 в году выдачи (со следующего года) |
| Дивиденды | От прибыли ПРОШЛОГО года: `MAX(0, E_ni) × payout` |
| CFF_base | Исключает RC AND new_term |
| Revenue | Цены = '01_Macro' active row (не литералы) |
| Material COGS | Vol × 1.93 × alumina_price (не от выручки) |
| fill_data | НЕ перезаписывает: forecast prices, SGA total formula |
| EBITDA ≤ 0 | Floor score 5, covenant breach, penalty rate |
| LT формула | `MAX(0, close-(mandatory+RC))` — скобки обязательны! |
| ST | Next year mandatory (IAS 1), не текущий год |
| BS.cash | = CF cash_close (модель всегда финансирует) |
| S&U gap | = rc_draw + new_term (включает term_out, check = 0 всегда) |
| penalty_rate | На accumulated gap при нарушении (% от долга по штрафной ставке) |
| funding_gap | = penalty-financed portion (подмножество new_term, не отдельный источник) |

---

## 12. CP параметры: 43/44 LIVE

### Method Switches (из Control_Panel)
| Switch | Значения | Default | Лист |
|--------|----------|---------|------|
| Revenue method | 1=segment, 2=macro_ols (β×Δln), 3=ewa | 1 | 10_Revenue |
| COGS method | 1=ratio, 2=component, 3=ppi_uplift | 2 (Rusal) | 12_COGS |
| WC method | 1=days (DSO/DIH/DPO), 2=ratio (NWC/Rev) | 1 | 16_WC |
| SGA ratio | CP.sga_ratio → Revenue × ratio | 8% | 13_SGA |

### Все CP секции
| Секция | Параметры | Статус |
|--------|-----------|--------|
| A. Макросценарий | Сценарий (1/2/3) + 6 macro factors | LIVE |
| B. Операционные | Volume + price growth per segment | LIVE |
| C. Выручка | Method, elasticity β, R² | LIVE |
| D. Себестоимость | Method, ratio, components, PPI beta, dampening | LIVE |
| E. SGA | SGA ratio, EWA halflife | LIVE (halflife = info) |
| F. CapEx/PPE | DA rate, sustaining ratio, expansion%, useful life, disposal% | LIVE |
| G. Оборотный капитал | Method, DSO/DIH/DPO | LIVE |
| H. Долг | 18 params (min_cash..penalty_rate) | LIVE |
| I. FX | USDCNY/USDRUB change, rev/cost shares | LIVE |
| J. Ковенанты | ND/EBITDA max, ICR min | LIVE |
| K. Налоги | Tax rate, NOL open/cap | LIVE |
| L. Дивиденды/WACC | Payout, Rf/β/ERP/CRP/SCP, TV growth | LIVE |

### Единственный информационный
- `CP.ewa_halflife` — настройка Python preprocessing (не Excel формула)

---

## 13. Финальный статус (AUDIT FINAL ACCEPTED)

| Метрика | Значение |
|---------|---------|
| Версия | v4.2 (AUDIT FINAL accepted 08.10.2026) |
| Листов | 31 (включая 11_Segments с формулами) |
| Формул | ~1,270 |
| CP параметров | ~47 LIVE (1 informational: ewa_halflife) |
| Method switches | 4 (Revenue: segment/OLS/EWA, COGS: ratio/component/PPI, WC: days/ratio, SGA: ratio) |
| Проверок | 15, все = 0 в обоих компаниях × 3 сценария |
| Компании | 2 (Rusal, Nornickel) |
| Сценарии | 3 × verified (Base/Stress/Severe) |
| Cash | = min_cash ВСЕГДА (модель всегда финансирует) |
| Gate | = rate (penalty 24%, penalty_limit configurable) |
| 11_Segments | Подключён: vol/price/rev с формулами, 10_Revenue → refs |
| OLS β | 0.828 (Rusal, 14 obs, lme_aluminium) → CP.rev_elasticity |
| ST last year | avg ST share fallback (нет 2029 столбца) |
| Buyback | CP.buyback_pct → 24_Equity (covenant-gated) |
| Terminal params | CP.terminal_g/mult → 35_Valuation |
| Op leverage | Rusal 3.5x, Nornickel 1.0x |
| Behavioral tests | verify_model.py — ALL PASS обе компании |
| Документация | Methodology + AI Build Guide |
| Оставшийся долг | ~150 литералов истории (layout rework, non-blocking) |
