# 🔄 ДЕТАЛЬНАЯ ЛОГИКА ЦИКЛИЧНОСТИ МОДЕЛИ

## 📋 ОБЩАЯ СХЕМА ИТЕРАЦИОННОГО ЦИКЛА

### Входные параметры итерации:
- `iter_max`: Максимальное количество итераций (по умолчанию: 50)
- `tol`: Точность сходимости (по умолчанию: 1e-6)
- `prev_interest_sum`: Сумма Interest Expense с предыдущей итерации (для проверки сходимости)

### Критерий сходимости:
```python
if abs(new_interest_sum - prev_interest_sum) < tol:
    # Абсолютная сходимость
    converged = True
elif abs(new_interest_sum - prev_interest_sum) < tol * max(abs(new_interest_sum), 1.0):
    # Относительная сходимость
    converged = True
```

### Источники данных (ВСЕ ЧЕРЕЗ ВИТРИНУ):
- **Исторические данные:** `FinancialDataMart.get_history_income_statement()`, `get_history_balance_sheet()`, `get_history_cash_flow()`, `get_history_metric()`
- **Прогнозные данные:** `FinancialDataMart.get_model_forecast('IS'/'BS'/'CF')`
- **Сохранение данных:** `FinancialDataMart.save_model_forecast('IS'/'BS'/'CF')`
- **Corkscrew данные:** Прямое сохранение в БД (таблицы `debt_corkscrew`, `ppe_corkscrew`, `intangibles_corkscrew`, `equity_corkscrew`, `tax_schedule`)
- **Fallback:** CSV файлы используются только как резервный источник/дубликат

---

## 🔄 ПОРЯДОК РАСЧЕТА В КАЖДОЙ ИТЕРАЦИИ

### ИТЕРАЦИЯ #N (для каждого года прогноза последовательно)

#### ШАГ 1: Расчет Cash Flow (CFO, CFI, CFF)
**Входные данные:**
- `proj_ni[y]`: Net Income (из предыдущей итерации)
- `proj_dep[y]`: Depreciation
- `proj_intangibles_amortization[y]`: Amortization
- `wc["WC_delta"][y]`: Изменение Working Capital
- `proj_tax[y]`: Tax Expense (из предыдущей итерации)
- `capex[y]`: Capital Expenditures
- `debt["cff_borrowings"][y]`: Заимствования (из предыдущей итерации)
- `debt["cff_repayments"][y]`: Погашения (из предыдущей итерации)

**Расчет:**
```python
# ВАЖНО: CFO = NI + D&A - Gain/Loss - WC_Delta_incl_Tax_Int - Lease_Payments_CFO - Lease_Interest_CFO
# WC_Delta_incl_Tax_Int = WC_Delta_base + ΔTaxesPayable + ΔInterestPayable
# Это устраняет двойное вычитание Tax_Paid и Interest_Paid
# Timing differences отражаются через изменения payables
CFO = NI + D&A - Gain/Loss - WC_Delta_incl_Tax_Int - Lease_Payments_CFO - Lease_Interest_CFO
CFI = -CapEx + Disposal_Proceeds
CFF = Borrowings - Repayments - Lease_Principal_CFF  # Из Debt Solver (из предыдущей итерации)
NetChange = CFO + CFO_other + CFI + CFI_other + CFF + CFF_other
```

**Выходные данные:**
- `ncf[y]`: Net Cash Flow (NetChange)
- `cf_out`: DataFrame с CFO, CFI, CFF, NetChange

**Обновление:**
- Сохранение CF в БД через `mart.save_model_forecast('CF', cf_out)` (приоритет)
- Сохранение `3statement_CF.csv` (дубликат для совместимости)
- **Формат в БД:** Long format (year, metric, value) в таблице `model_forecasts`

---

#### ШАГ 2: Provisional Balance Sheet (Cash Roll)
**Входные данные:**
- `cash_last_year`: Cash на конец последнего исторического года
- `ncf[y]`: Net Cash Flow для каждого года

**Расчет:**
```python
cash_balance = cash_last_year
for y in years_frc:
    # ВАЖНО: НЕ клипуем cash до нуля здесь - debt solver должен увидеть реальный дефицит
    cash_balance = cash_balance + ncf[y]  # БЕЗ max(0.0, ...)
```

**Выходные данные:**
- `bs_out`: Provisional Balance Sheet с Cash, Debt, Equity, Intangibles, Lease Liability, ROU Asset

**Обновление:**
- Сохранение BS в БД через `mart.save_model_forecast('BS', bs_out)` (приоритет)
- Сохранение `3statement_BS.csv` (дубликат для совместимости)
- **Формат в БД:** Long format (year, metric, value) в таблице `model_forecasts`

---

#### ШАГ 3: Расчет Interest Income (на основе Cash)
**Входные данные:**
- `cash_val`: Cash из provisional BS (загружается из БД через `mart.get_model_forecast('BS')`)
- `prev_cash_ii`: Cash с предыдущего года (для расчета среднего)
- `interest_income_rate`: Ставка процента по cash (из конфига)

**ВАЖНО:** Interest Income рассчитывается **ПОСЛЕ** debt solver, на основе closing cash после CFF.

**Расчет:**
```python
# Рассчитываем closing cash для каждого года: Opening + CFO + CFI + CFF
opening_cash_ii = cash_last_year if cash_last_year is not None else 0.0
for y in years_frc:
    # Получаем CFO с учетом ΔPayables (как в основном расчете)
    cfo_temp = proj_ni.get(y,0.0) + total_da - gain_loss - wc_delta_incl_tax_int - lease_payments_cfo - lease_interest_cfo
    cfi_temp = -capex.get(y,0.0)
    cff_temp = float(debt.get("cff_borrowings", {}).get(y, 0.0) - debt.get("cff_repayments", {}).get(y, 0.0))
    closing_cash_ii = opening_cash_ii + cfo_temp + cfi_temp + cff_temp
    
    # Interest Income на основе среднего cash (opening + closing) / 2
    avg_cash = (opening_cash_ii + closing_cash_ii) / 2.0
    proj_interest_income[y] = max(avg_cash, 0.0) * (interest_income_rate / 100.0)
    
    opening_cash_ii = closing_cash_ii  # Для следующего года
```

**Выходные данные:**
- `proj_interest_income[y]`: Interest Income для каждого года

**Обновление:**
- Добавление Interest Income в IS (используется в следующем шаге)
- IS сохраняется в БД через `mart.save_model_forecast('IS', is_out)`

**ВАЖНО:** Interest Income рассчитывается **ПОСЛЕ** debt solver, чтобы использовать актуальный closing cash после CFF.

---

#### ШАГ 4: Создание Provisional Income Statement
**Входные данные:**
- `proj_rev[y]`: Revenue
- `proj_cogs[y]`: COGS
- `proj_sga[y]`: SG&A
- `proj_dep[y]`: Depreciation
- `proj_tax[y]`: Tax Expense (из предыдущей итерации)
- `proj_ni[y]`: Net Income (из предыдущей итерации)

**Расчет:**
- Создание временного IS для debt solver

**Выходные данные:**
- `is_out`: Provisional Income Statement DataFrame

**Обновление:**
- Сохранение IS в БД через `mart.save_model_forecast('IS', is_out)` (приоритет)
- Сохранение `3statement_IS.csv` (дубликат для совместимости)
- **Формат в БД:** Long format (year, metric, value) в таблице `model_forecasts`

---

#### ШАГ 5: Debt/RC Solver (v2_solver)
**Входные данные:**
- `CFO`, `CFI`: Cash Flow Before Financing (CFB = CFO + CFI)
- `opening_cash`: Cash на начало года
- `min_cash`: Минимальный cash floor (из конфига)
- `instruments`: Список инструментов долга с параметрами:
  - `OpeningDebt`: Остаток долга на начало года
  - `Rate`: Процентная ставка
  - `Cap`: Лимит (для RC)
  - `Mandatory`: Обязательные платежи
  - `AmortType`: Тип погашения (bullet, level_payment, etc.)
  - `Priority`: Приоритет погашения
  - `Name`: Название инструмента

**Логика Debt Solver (v2_solver):**

**5.1. Расчет Cash Pre-Financing:**
```python
# ВАЖНО: CFB = CFO + CFI (без CFF)
Cash_PreFin = Opening_Cash + CFB
```

**5.2. Рефинансирование обязательных платежей (ДО расчета required_draw):**
**ВАЖНО:** Рефинансирование происходит **ДО** расчета `required_draw`, так как это парные проводки (net cash = 0, кроме комиссий).

**Режимы рефинансирования:**
- **Simple (Standard mode):** Продление существующего инструмента
  - Обновление `End` и `Rate` существующего инструмента
  - `Draw = Repay = Mandatory` (на том же инструменте)
  - Комиссии: `fees = mandatory * fees_pct` или `fees_abs`
- **Detailed (Custom mode):** Создание нового инструмента
  - Создание нового инструмента с новыми параметрами (tenor, rate)
  - `Draw` на новый инструмент = `Repay` на старый = `Mandatory`
  - Комиссии: `fees = mandatory * fees_pct` или `fees_abs`
  - Новый инструмент добавляется в список `instruments`

**Логика рефинансирования:**
```python
# Для каждого инструмента с Mandatory > 0 и End == текущий год:
if refi_mode == "simple":
    # Продлеваем существующий инструмент
    inst["End"] = t + extend_years
    inst["Rate"] = inst_rate * (1.0 + rate_adjustment)
    refi_pairs.append((old_id, old_id, mandatory, fees, None))
else:
    # Создаем новый инструмент
    new_inst = {
        "Name": f"Refinanced_{inst_name}_{t}",
        "Rate": inst_rate + rate_spread,
        "OpeningDebt": 0.0,
        "End": t + new_tenor,
        "AmortType": amort_type,
        ...
    }
    refi_pairs.append((old_id, new_id, mandatory, fees, new_inst))
    new_instruments_to_add.append((new_id, new_inst, mandatory))
```

**5.3. Определение потребности в финансировании:**
```python
# ВАЖНО: Учитываем только non-refinanced mandatory платежи
# ВАЖНО: Также учитываем lease principal и refi fees (они уменьшают cash)
Mandatory_Cash = sum(mandatory for inst in instruments if not refinanced)
Lease_Principal_CFF = lease_payments_cff.get(y, 0.0)  # Principal платежи лизинга (CFF outflow)
Refi_Fees_Estimate = refi_fees_total  # Оценка комиссий за рефинансирование

Cash_Before_Vol = Cash_PreFin - Mandatory_Cash - Lease_Principal_CFF - Refi_Fees_Estimate

# ВАЖНО: required_draw всегда неотрицательное число "сколько надо привлечь"
# Теперь учитывает все обязательные платежи, включая lease principal и refi fees
Required_Draw = max(0.0, Min_Cash - Cash_Before_Vol)  # >= 0
Surplus = max(0.0, Cash_Before_Vol - Min_Cash)        # >= 0
```

**5.4. Выполнение рефинансирования (ПАРНЫЕ ПРОВОДКИ):**
```python
# ВАЖНО: Рефинансирование не влияет на cash (кроме комиссий)
for old_id, new_id, refi_amount, fees, new_inst_dict in refi_pairs:
    # Старый инструмент: Repay = refi_amount
    repays[old_id] += refi_amount
    
    # Новый инструмент: Draw = refi_amount (или продление старого)
    if refi_mode == "simple":
        draws[old_id] += refi_amount  # Продление того же инструмента
    else:
        # Добавляем новый инструмент в список
        instruments.append(new_inst_dict)
        draws[new_id] = refi_amount
    
    # Комиссии уменьшают cash
    refi_fees_total += fees
```

**5.5. Обработка дефицита (Required_Draw > 0):**
- **Приоритет 1:** RC Facilities (если доступны)
  - Draw из RC до лимита
  - `needed -= take` после каждого draw
  - Если `needed <= 1e-6`: выход
- **Приоритет 2:** Рефинансирование обязательных платежей (если дефицит не покрыт)
  - Для инструментов с `Mandatory > 0`:
    - Если `needed > mandatory`: рефинансируем `mandatory` + дополнительный draw на `(needed - mandatory)`
    - Если `needed <= mandatory`: рефинансируем только `mandatory`
    - `needed -= take` после каждого refinance
- **Приоритет 3:** Новые заимствования (если разрешено)
  - Создание новых draws из "New_Money_Facility"
  - `needed -= take` после каждого draw

**5.6. Обработка излишка (Surplus > 0):**
- **Приоритет 1:** Погашение RC (если есть draws)
- **Приоритет 2:** Обязательные платежи (Mandatory, которые не рефинансированы)
  - Bullet payments в год погашения
  - Amortizing payments по графику
- **Приоритет 3:** Добровольное погашение (Voluntary)
  - Погашение в порядке приоритета инструментов
  - Поддержание приблизительной пропорции ST/LT

**5.7. Расчет Interest Expense:**
```python
# Для каждого инструмента (включая новые, созданные при рефинансировании):
# ВАЖНО: Для рефинансированных инструментов используется piece-wise расчет (полугодовой вес)
# - До рефинансирования: Interest на старый инструмент (0.5 года)
# - После рефинансирования: Interest на новый инструмент (0.5 года)
# Это уменьшает дрожание итераций и расхождение NI/BS

for i, inst in enumerate(instruments):
    opening = inst["OpeningDebt"]
    drawing = draws.get(i, 0.0)
    repaying = repays.get(i, 0.0)  # Включает mandatory + voluntary
    ending = max(opening + drawing - repaying, 0.0)
    
    # Проверяем, было ли рефинансирование
    was_refinanced = check_if_refinanced(i, refi_pairs)
    
    if was_refinanced and refi_amount > 1e-6:
        # Piece-wise расчет: 0.5 года на старом + 0.5 года на новом
        old_balance_before_refi = opening
        old_balance_after_refi = opening - refi_amount
        new_balance_after_refi = refi_amount
        new_balance_end = ending
        
        interest_old = old_rate * 0.5 * (old_balance_before_refi + old_balance_after_refi)
        interest_new = new_rate * 0.5 * (new_balance_after_refi + new_balance_end)
        interests[i] = interest_old + interest_new
    else:
        # Обычный расчет: средний баланс × ставка
        avg_balance = 0.5 * (opening + ending)
        interests[i] = inst["Rate"] * avg_balance
```

**5.8. Расчет Closing Cash:**
```python
# ВАЖНО: Closing Cash = Opening Cash + CFO + CFI + CFF
# Interest уже учтен в CFO (через NI), НЕ вычитаем здесь
# Mandatory уже включен в repays, НЕ вычитаем отдельно
# Lease principal и refi fees уменьшают CFF (cash outflow)
CFF = Total_Draws - Total_Repays - Refi_Fees - Lease_Principal_CFF
Closing_Cash = Opening_Cash + CFB + CFF  # где CFB = CFO + CFI

# ========== АССЕРТ: Min-cash guard с лизингом и fee ==========
# Контроль: денег достаточно для min_cash (с учетом всех обязательных платежей)
if Closing_Cash + 1e-6 < Min_Cash:
    print(f"[Debt Solver Assert] ⚠️  Min cash violated: Closing=${Closing_Cash:,.0f}, Min=${Min_Cash:,.0f}")
    # Не используем assert, чтобы не останавливать выполнение, но выводим предупреждение
```

**Выходные данные:**
- `debt_new["interest_expense"][y]`: Interest Expense для каждого года
- `debt_new["debt_total"][y]`: Total Debt для каждого года
- `debt_new["cff_borrowings"][y]`: Заимствования (CFF) = Total Draws
- `debt_new["cff_repayments"][y]`: Погашения (CFF) = Total Repays (mandatory + voluntary)
- `debt_new["debt_split"][y]`: Разделение на ST/LT/RC
  - `ST`: Short-Term Debt (maturing <= 1 year)
  - `LT`: Long-Term Debt (maturing > 1 year)
  - `RC`: Revolving Credit draws
- `debt_new["NewInstruments"]`: Список новых инструментов, созданных при рефинансировании
  - Формат: `[(temp_new_id, new_inst_dict, refi_amount), ...]`

**Обновление:**
- `debt = debt_new`: Обновление словаря debt для следующей итерации
- Добавление новых инструментов в `instrument_states` для сохранения в corkscrew
- Сохранение debt corkscrew в БД (таблица `debt_corkscrew`)
  - Формат: `(company, year, instrument, metric, value, classification)`
  - Метрики: `OpeningDebt`, `Draw`, `Repay`, `Mandatory`, `Voluntary`, `Interest`, `EndDebt`
  - **ВАЖНО:** Включает все инструменты, включая новые, созданные при рефинансировании

---

#### ШАГ 6: Пересчет Income Statement (EBT, Tax, NI)
**Входные данные:**
- `proj_rev[y]`: Revenue
- `proj_cogs[y]`: COGS
- `proj_sga[y]`: SG&A
- `proj_dep[y]`: Depreciation
- `proj_interest_income[y]`: Interest Income (из ШАГ 3)
- `debt["interest_expense"][y]`: Interest Expense (из ШАГ 5)
- `proj_leases["finance_lease_interest"][y]`: Lease Interest
- `gain_loss_on_disposal[y]`: Gain/Loss on Disposal

**Расчет:**
```python
EBIT = Revenue - COGS - SG&A - Depreciation
EBT = EBIT + Gain/Loss + Interest_Income - Interest_Expense - Lease_Interest
```

**Tax Calculation (Standard или Custom):**

**Standard Model:**
```python
if EBT < 0:
    NOL_Balance += abs(EBT)
    Taxable_Income = 0.0
    Tax_Expense = 0.0
elif EBT > 0 and NOL_Balance > 0:
    NOL_Used = min(EBT, NOL_Balance)
    Taxable_Income = EBT - NOL_Used
    Tax_Expense = Taxable_Income * Tax_Rate
    NOL_Balance -= NOL_Used
else:
    Taxable_Income = EBT
    Tax_Expense = Taxable_Income * Tax_Rate

Net_Income = EBT - Tax_Expense
```

**Custom Model (Tax Schedule):**
```python
# Используется build_tax_schedule с:
# - Current Tax (EBT × Tax_Rate с учетом NOL)
# - Deferred Tax (из временных разниц)
# - Taxes Payable (timing differences)
# - DTA/DTL corkscrew

Total_Tax_Expense = Current_Tax + Deferred_Tax_Expense
Net_Income = EBT - Total_Tax_Expense
```

**Выходные данные:**
- `proj_ebit[y]`: EBIT
- `proj_ebt[y]`: EBT
- `proj_tax[y]`: Tax Expense
- `proj_ni[y]`: Net Income

**Обновление:**
- Обновление IS для следующей итерации
- Обновление NOL balance (если используется)

---

#### ШАГ 7: Пересчет Cash Flow с обновленным NI
**Входные данные:**
- `proj_ni[y]`: Net Income (обновленный из ШАГ 6)
- Остальные компоненты как в ШАГ 1

**Расчет:**
- Повторный расчет CFO, CFI, CFF с новым NI
- Обновление NetChange

**Выходные данные:**
- Обновленный `ncf[y]`

**Обновление:**
- Обновление CF в БД через `mart.save_model_forecast('CF', cf_out)` (приоритет)
- Обновление `3statement_CF.csv` (дубликат для совместимости)
- **ВАЖНО:** CF перезагружается из БД после обновления для использования актуальных значений

---

#### ШАГ 8: Проверка сходимости
**Входные данные:**
- `new_interest_sum`: Сумма Interest Expense по всем годам (из ШАГ 5)
- `prev_interest_sum`: Сумма Interest Expense с предыдущей итерации

**Расчет:**
```python
interest_diff = abs(new_interest_sum - prev_interest_sum)
if interest_diff < tol:
    # Абсолютная сходимость
    converged = True
elif interest_diff < tol * max(abs(new_interest_sum), 1.0):
    # Относительная сходимость
    converged = True
```

**Выходные данные:**
- `converged`: Флаг сходимости

**Обновление:**
- Если `converged == True`: выход из цикла
- Если `converged == False`: `prev_interest_sum = new_interest_sum`, переход к следующей итерации

---

## 🔗 ЦИКЛИЧЕСКИЕ ЗАВИСИМОСТИ

### Цикл 1: Cash → CFF → Interest Income → NI → CFO → Cash
```
Cash (BS) 
  → Debt Solver (RC draws/repays) 
    → CFF = Draws - Repays 
      → Closing Cash = Opening Cash + CFO + CFI + CFF 
        → Interest Income (IS, на основе avg cash) 
          → EBT = EBIT + Interest Income - Interest Expense 
            → Tax Expense 
              → Net Income 
                → CFO = NI + D&A - WC_Delta_incl_Tax_Int 
                  → NetChange = CFO + CFI + CFF 
                    → Cash (BS)
```

**ВАЖНО:** Interest Income рассчитывается **ПОСЛЕ** debt solver, на основе closing cash после CFF.

### Цикл 2: Debt → Interest Expense → NI → CFO → Cash → Debt
```
Debt (BS) 
  → Interest Expense (IS, на основе avg debt balance) 
    → EBT = EBIT + Interest Income - Interest Expense 
      → Tax Expense 
        → Net Income 
          → CFO = NI + D&A - WC_Delta_incl_Tax_Int 
            → NetChange = CFO + CFI + CFF 
              → Cash (BS) 
                → Debt Solver (RC draws/repays, refinancing) 
                  → Debt (BS)
```

**ВАЖНО:** Debt Solver использует Cash для определения required_draw и surplus, что влияет на draws/repays и, следовательно, на Interest Expense следующей итерации.

### Цикл 3: NI → Retained Earnings → Equity → Balance Sheet
```
Net Income 
  → Retained Earnings = Prior RE + NI - Dividends 
    → Total Equity = Share Capital + APIC + RE + AOCI + NCI 
      → Balance Sheet (Liab + Equity)
```

---

## 📊 DEBT SCHEDULE - ДЕТАЛЬНАЯ СТРУКТУРА

### Входные данные для Debt Solver:

#### 1. Инструменты долга (instruments):
```python
{
    "Name": "Term_Loan_2027",
    "OpeningDebt": 1600.0,      # Остаток на начало года
    "Rate": 0.05,                # Процентная ставка (5%)
    "Cap": None,                 # Лимит (для RC)
    "Mandatory": 167.0,          # Обязательные платежи
    "AmortType": "level_payment", # Тип погашения
    "Priority": 1,                # Приоритет погашения
    "end_year": 2027,            # Год погашения
    "payment_frequency": "annual" # Частота платежей
}
```

#### 2. Cash Flow Before Financing:
```python
CFB = CFO + CFI  # Cash Flow до финансирования
```

#### 3. Параметры:
- `opening_cash`: Cash на начало года
- `min_cash`: Минимальный cash floor
- `years`: Список лет прогноза

### Выходные данные Debt Solver:

#### 1. Результаты для каждого инструмента:
```python
{
    "Draw": 0.0,           # Новые заимствования
    "Repay": 1433.0,       # Погашения (mandatory + voluntary)
    "Mandatory": 167.0,    # Обязательные платежи
    "Voluntary": 1266.0,   # Добровольные платежи
    "Interest": 40.0,      # Проценты
    "EndDebt": 167.0       # Остаток на конец года
}
```

#### 2. Агрегированные результаты:
```python
debt_new = {
    "interest_expense": {2025: 1122.0, ...},  # Interest Expense по годам
    "debt_total": {2025: 623.0, ...},          # Total Debt по годам
    "cff_borrowings": {2025: 0.0, ...},        # Заимствования (CFF)
    "cff_repayments": {2025: 14857.0, ...},   # Погашения (CFF)
    "debt_split": {                            # Разделение на ST/LT/RC
        2025: {
            "ST": 623.0,   # Short-Term Debt
            "LT": 0.0,     # Long-Term Debt
            "RC": 0.0      # Revolving Credit
        },
        ...
    }
}
```

---

## 🔄 ЧТО ОБНОВЛЯЕТСЯ ПРИ КАЖДОЙ ИТЕРАЦИИ

### 1. Income Statement:
- ✅ Interest Income (на основе Cash)
- ✅ Interest Expense (из Debt Solver)
- ✅ EBT (с учетом Interest Income/Expense)
- ✅ Tax Expense (Standard или Custom)
- ✅ Net Income

### 2. Cash Flow Statement:
- ✅ CFO (с обновленным NI, включая Tax_Paid и Interest_Paid)
- ✅ CFI (с обновленным CapEx и Disposal Proceeds)
- ✅ CFF (с обновленными Borrowings/Repayments из Debt Solver)
- ✅ NetChange (CFO + CFO_other + CFI + CFI_other + CFF + CFF_other)
- ✅ Сохранение в БД (приоритет) и CSV (для совместимости)

### 3. Balance Sheet:
- ✅ Cash (из NetChange: Opening_Cash + NetChange = Closing_Cash)
- ✅ Debt (из Debt Solver: ST/LT/RC split)
- ✅ Equity (из Retained Earnings corkscrew)
- ✅ Taxes Payable (corkscrew: open + Tax_Expense - Tax_Paid = close)
- ✅ Interest Payable (corkscrew: open + Interest_Expense - Interest_Paid = close)
- ✅ Сохранение в БД (приоритет) и CSV (для совместимости)

### 4. Debt Schedule:
- ✅ Opening Debt (из предыдущего года или истории)
- ✅ Draws (новые заимствования из RC/refinance/new money)
- ✅ Repayments (mandatory + voluntary)
- ✅ Interest Expense (на основе среднего баланса)
- ✅ Ending Debt (Opening + Draws - Repayments)
- ✅ Сохранение в БД (таблица `debt_corkscrew`)

### 5. Проверка сходимости:
- ✅ `prev_interest_sum` = `new_interest_sum`
- ✅ Если `abs(new_interest_sum - prev_interest_sum) < tol`: выход из цикла

---

## 📈 ПОСЛЕДОВАТЕЛЬНОСТЬ ОБРАБОТКИ ЛЕТ

### Важно:
Годы обрабатываются **последовательно**, начиная с первого года прогноза:

```python
for y in sorted(years_frc):  # 2025, 2026, 2027, ...
    # 1. Расчет CF для года y
    # 2. Расчет Cash для года y
    # 3. Расчет Interest Income для года y
    # 4. Debt Solver для года y (использует Cash и CF)
    # 5. Расчет EBT/Tax/NI для года y
    # 6. Обновление Retained Earnings для года y
    # 7. Переход к году y+1
```

**Зависимости между годами:**
- Cash года y используется как `opening_cash` для года y+1
- Ending Debt года y используется как `OpeningDebt` для года y+1
- Retained Earnings года y используется как `opening_RE` для года y+1

---

## 🎯 КРИТЕРИИ СХОДИМОСТИ

### Абсолютная сходимость:
```python
if abs(new_interest_sum - prev_interest_sum) < tol:
    converged = True
```

### Относительная сходимость:
```python
if abs(new_interest_sum - prev_interest_sum) < tol * max(abs(new_interest_sum), 1.0):
    converged = True
```

### Максимальное количество итераций:
```python
if _it >= iter_max - 1:
    print("Warning: Maximum iterations reached")
    break
```

---

## 📝 ПРИМЕР ИТЕРАЦИИ

### Итерация 1:
- Interest Expense = $1,077
- Cash = $500
- Debt Total = $0

### Итерация 2:
- Interest Expense = $1,122 (изменение: +$45)
- Cash = $500
- Debt Total = $0

### Итерация 3:
- Interest Expense = $1,122 (изменение: $0)
- **Сходимость достигнута!** (изменение < tol)

---

## 🔍 ОТЛАДКА

### Логирование:
```python
print(f"[DEBT] Iteration {_it + 1}: Interest expense = ${new_interest_sum:,.0f} (prev: ${prev_interest_sum:,.0f})")
```

### Проверка баланса:
```python
if abs(total_assets - total_liab_equity) > 0.01:
    print(f"[BS Balance Warning] Year {y}: Assets=${total_assets:,.0f}, Liab+Equity=${total_liab_equity:,.0f}, Diff=${diff:,.0f}")
```

---

## ✅ ИТОГОВЫЕ ВЫХОДНЫЕ ДАННЫЕ

После сходимости итерационного цикла:

1. **Income Statement:**
   - Revenue, COGS, SG&A, Depreciation, Amortization
   - Interest Income, Interest Expense
   - Tax Expense, Net Income
   - **Хранилище:** БД (таблица `model_forecasts`, `statement_type='IS'`) + CSV (дубликат)
   - **Формат в БД:** Long format (company, statement_type, metric, year, value)

2. **Balance Sheet:**
   - Cash, AR, Inventory, PP&E, Intangibles
   - AP, Debt (ST/LT), Lease Liability
   - Taxes Payable, Interest Payable (corkscrews)
   - Equity (Share Capital, APIC, RE, AOCI, NCI)
   - **Хранилище:** БД (таблица `model_forecasts`, `statement_type='BS'`) + CSV (дубликат)
   - **Формат в БД:** Long format (company, statement_type, metric, year, value)

3. **Cash Flow Statement:**
   - CFO, CFI, CFF, NetChange
   - **Хранилище:** БД (таблица `model_forecasts`, `statement_type='CF'`) + CSV (дубликат)
   - **Формат в БД:** Long format (company, statement_type, metric, year, value)

4. **Corkscrew Schedules:**
   - **Debt corkscrew:** БД (таблица `debt_corkscrew`)
     - Метрики: OpeningDebt, Draw, Repay, Mandatory, Voluntary, Interest, EndDebt
     - Формат: `(company, year, instrument, metric, value, classification)`
     - **ВАЖНО:** Включает все инструменты, включая новые, созданные при рефинансировании
   - **PP&E corkscrew:** БД (таблица `ppe_corkscrew`)
     - Метрики: Opening_Gross, Opening_AccumDep, Opening_Net, CapEx, Disposals, Depreciation, Ending_Gross, Ending_AccumDep, Ending_Net
     - Формат: `(company, year, metric, value)`
   - **Intangibles corkscrew:** БД (таблица `intangibles_corkscrew`)
     - Метрики: Opening, Additions, Amortization, Ending
     - Формат: `(company, year, metric, value)`
   - **Equity corkscrew:** БД (таблица `equity_corkscrew`)
     - Метрики: Share_Capital, APIC, AOCI, NCI, Retained_Earnings, Total_Equity
     - Формат: `(company, year, metric, value)`
   - **Tax schedule:** БД (таблица `tax_schedule`, если Custom)
     - Метрики: Taxable_Income, Current_Tax, Deferred_Tax, Tax_Expense, Tax_Paid, Taxes_Payable
     - Формат: `(company, year, metric, value)`
   - **CSV файлы:** Сохраняются как дубликат для совместимости, но БД является основным хранилищем

5. **Проверки:**
   - Balance Sheet Identity (Assets = Liab + Equity)
   - Cash Bridge (Opening Cash + CFO + CFI + CFF = Closing Cash)
   - Retained Earnings (Opening RE + NI - Div = Closing RE)
   - Taxes Payable (Opening + Tax_Expense - Tax_Paid = Closing)
   - Interest Payable (Opening + Interest_Expense - Interest_Paid = Closing)

---

## 🔧 ВАЖНЫЕ ИСПРАВЛЕНИЯ (после перехода на витрину данных)

### 1. Переход на FinancialDataMart (витрину данных):
- **Все исторические данные:** Загружаются через `mart.get_history_income_statement()`, `get_history_balance_sheet()`, `get_history_cash_flow()`, `get_history_metric()`
- **Все прогнозные данные:** Загружаются через `mart.get_model_forecast('IS'/'BS'/'CF')`
- **Все сохранения:** Через `mart.save_model_forecast('IS'/'BS'/'CF')`
- **Приоритет:** БД (через витрину) → CSV (fallback только для чтения)
- **Сохранение:** БД (основное) + CSV (дубликат для совместимости)

### 2. Формат имен метрик:
- Поддержка обоих форматов: PascalCase (`CFO`, `CFI`, `CFF`) и snake_case (`cfo`, `cfi`, `cff`)
- БД использует snake_case, CSV может использовать PascalCase
- Витрина автоматически нормализует метрики к канонической форме

### 3. Исправление расчета CFO:
- **Вариант A (текущий):** `CFO = NI + D&A - Gain/Loss - WC_Delta_incl_Tax_Int`
  - `WC_Delta_incl_Tax_Int = WC_Delta_base + ΔTaxesPayable + ΔInterestPayable`
  - Это устраняет двойное вычитание Tax_Paid и Interest_Paid
  - Timing differences отражаются через изменения payables

### 4. Исправление Closing Cash:
- Удалено двойное вычитание `- Total_Interest - Total_Mandatory`
- Формула: `Closing_Cash = Opening_Cash + CFB + CFF`
- Где `CFB = CFO + CFI` (без CFF)

### 5. Исправление Cash Pre-Financing:
- Удалено клиппирование cash до нуля в provisional BS
- Debt solver должен видеть реальный дефицит для правильного финансирования

### 6. Добавлены Payables Corkscrews:
- **Taxes Payable:** `open + Tax_Expense - Tax_Paid = close`
- **Interest Payable:** `open + Interest_Expense - Interest_Paid = close`
- Обеспечивают баланс при timing differences между expense и paid
- Сохраняются в `bs_final` и учитываются в `total_current_liabilities`

### 7. Исправление Required Draw:
- **ВАЖНО:** `Required_Draw` рассчитывается **ПОСЛЕ** учета non-refinanced mandatory платежей
- Формула: `Cash_Before_Vol = Cash_PreFin - Mandatory_Cash (non-refi)`
- `Required_Draw = max(0.0, Min_Cash - Cash_Before_Vol)`

### 8. Рефинансирование долга:
- **Simple mode (Standard):** Продление существующего инструмента (обновление `End` и `Rate`)
- **Detailed mode (Custom):** Создание нового инструмента с новыми параметрами
- Рефинансирование = парные проводки (net cash = 0, кроме комиссий)
- Новые инструменты добавляются в `instrument_states` и сохраняются в `debt_corkscrew`

### 9. Исправление Interest Income Timing:
- **ВАЖНО:** Interest Income рассчитывается **ПОСЛЕ** debt solver
- На основе closing cash после CFF (не provisional cash)
- Это обеспечивает правильную циклическую зависимость: Cash → CFF → Interest Income → NI → CFO → Cash

### 10. Итерационная сходимость RC draws:
- В начале каждой итерации `draws_iter` и `repays_iter` сбрасываются
- `draws` и `repays` обновляются значениями из текущей итерации
- `draws_prev` и `repays_prev` используются для проверки сходимости
- Это предотвращает накопление draws между итерациями

### 11. Required Draw с учетом lease principal и refi fees:
- **ВАЖНО:** `Required_Draw` рассчитывается **ПОСЛЕ** учета:
  - Non-refinanced mandatory платежей
  - Lease principal payments (CFF outflow)
  - Refi fees (оценка комиссий за рефинансирование)
- Формула: `Cash_Before_Vol = Cash_PreFin - Mandatory_Cash - Lease_Principal - Refi_Fees`
- `Required_Draw = max(0.0, Min_Cash - Cash_Before_Vol)`
- Это предотвращает ситуацию "прошли min_cash, а потом упали ниже из-за lease/fees"

### 12. Piece-wise расчет процентов при рефинансировании:
- **ВАЖНО:** Для рефинансированных инструментов используется piece-wise расчет (полугодовой вес)
- До рефинансирования: Interest на старый инструмент (0.5 года)
- После рефинансирования: Interest на новый инструмент (0.5 года)
- Это уменьшает дрожание итераций и расхождение NI/BS при крупных mid-year операциях

### 13. Расширенный Total Assets:
- **ВАЖНО:** `Total Assets` включает все компоненты:
  - Cash + Restricted Cash + ST Investments
  - AR + Inventory + Prepaid Expenses + Other CA
  - PP&E + Intangibles + Goodwill
  - DTA + Other NCA + ROU Asset
- Это обеспечивает правильный баланс с Total Liabilities + Equity

### 14. Ассерты-ловушки (инварианты):
- **BS Identity:** `abs(Total_Assets - (Total_Liabilities + Total_Equity)) < eps`
- **Cash Bridge:** `abs(Opening_Cash + CFO + CFI + CFF - Closing_Cash) < eps`
- **Payables Corkscrews:**
  - `abs(Tax_Open + Tax_Expense - Tax_Paid - Tax_Close) < eps`
  - `abs(Int_Open + Int_Expense - Int_Paid - Int_Close) < eps`
- **Equity Recon:** `abs(RE_Close - (RE_Open + NI - Dividends)) < eps`
- **Min-cash Guard:** `Closing_Cash + eps >= Min_Cash` (с учетом lease/fees)
- Все ассерты выводят предупреждения, но не останавливают выполнение

