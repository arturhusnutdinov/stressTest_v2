# Методология финансовой модели корпоративного эмитента (v4)

**Версия:** 4.1 (7 октября 2026)
**Компании:** UC RUSAL, PJSC MMC Norilsk Nickel
**Подход:** outside-in (публичная МСФО отчётность), 3-statement Excel-driven model
**Статус:** ALL 15 CHECKS = 0 · BS 0/0/0 · S&U 0/0/0 · Cash 500/500/500 · Err 0/0/0

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

## 9. Сценарии (верифицировано в Excel)

### Rusal
| Сценарий | LME Al | EBITDA | Rating | Penalty Debt | Cash |
|----------|--------|--------|--------|-------------|------|
| Base (2450) | 2,450 | +1,268 | B | 0 | 500 |
| Stress (2000) | 2,000 | +401 | D | 1,198 (Y2) | 500 |
| Severe (1700) | 1,700 | −137 | D | 3,068 (Y3) | 500 |

### Nornickel
| Сценарий | EBITDA | Rating | Cash |
|----------|--------|--------|------|
| Base | 4,280 | BBB | 1,494 |
| Stress | 3,238 | BBB | 1,454 |
| Severe | 2,404 | BB | 1,637 |

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
| S&U gap | = funding_need (CF-based, авторитетный) |
| penalty_rate | На accumulated gap при нарушении (% от долга по штрафной ставке) |
