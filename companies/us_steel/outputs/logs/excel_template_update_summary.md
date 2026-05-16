# Обновление Excel шаблона для US Steel

## Дата: 2025-01-XX

## Выполненные задачи

### 1. Анализ используемых метрик

Проведен анализ метрик, используемых в:
- **HistoricState** (базовый год модели)
- **Drivers** (параметры модели)
- **Corkscrews** (PP&E, Debt, Lease, Tax, Equity, WC)
- **Canonical Forms** (канонические формы отчетности)

### 2. Определение перечня необходимых метрик

**Income Statement (IS):**
- Всего необходимых: **28 метрик**
- В БД: **32 метрики**
- Required из YAML: **10 метрик**

**Balance Sheet (BS):**
- Всего необходимых: **47 метрик**
- В БД: **53 метрики**
- Required из YAML: **9 метрик**

**Cash Flow (CF):**
- Всего необходимых: **36 метрик**
- В БД: **53 метрики**
- Required из YAML: **9 метрик**

### 3. Анализ избыточных метрик

**IS - избыточные метрики (13):**
- asset_impairment_charges
- earnings_from_investees
- eps_basic, eps_diluted
- gain_loss_on_disposal
- gross_profit
- net_periodic_benefit_income
- net_sales_to_related_parties
- other_expenses, other_income
- other_losses_gains_net
- restructuring_and_other_charges
- rnd

**BS - избыточные метрики (15):**
- accounts_payable_related_parties, ap_related_parties
- accrued_interest, accrued_taxes
- common_stock_par
- current_lease_liability, long_term_lease_liability
- deferred_credits
- employee_benefits
- investments_and_long_term_receivables
- payroll_and_benefits_payable
- receivables_related_parties
- restricted_cash
- short_term_investments
- st_debt

**CF - избыточные метрики (42):**
- Множество детализированных метрик, которые не используются напрямую в модели

### 4. Анализ отсутствующих метрик

**IS - отсутствующие метрики (9):**
- dep_rou_finance, dep_rou_operating
- interest_expense_debt, interest_expense_lease
- lease_expense_operating
- lease_interest_finance, lease_interest_operating
- net_interest_and_other_financial_costs
- net_periodic_benefit_cost_other_than_service_cost

**BS - отсутствующие метрики (9):**
- current_finance_lease_liability
- current_operating_lease_liability
- interest_payable
- lease_liab_current_total, lease_liab_noncurrent_total
- noncurrent_finance_lease_liability
- noncurrent_operating_lease_liability
- rou_finance_asset, rou_operating_asset

**CF - отсутствующие метрики (25):**
- Множество метрик для детализации CF (change_ar, change_inventory, change_ap, и т.д.)
- Метрики для combine_from (cfo_total, cfi_total, cff_total)
- Метрики для детализации операций (acquisitions, divestitures, и т.д.)

### 5. Экспорт данных из БД в Excel шаблон

**Результаты экспорта:**

**IS:**
- Заполнено: **32 существующих метрик**
- Добавлено: **3 новых метрик**
- Экспортировано из БД: **19 метрик** (из необходимых 28)
- Отсутствует в БД: **9 метрик**

**BS:**
- Заполнено: **51 существующих метрик**
- Добавлено: **2 новых метрик**
- Экспортировано из БД: **38 метрик** (из необходимых 47)
- Отсутствует в БД: **9 метрик**

**CF:**
- Заполнено: **52 существующих метрик**
- Добавлено: **0 новых метрик**
- Экспортировано из БД: **11 метрик** (из необходимых 36)
- Отсутствует в БД: **25 метрик**

## Выводы и рекомендации

### 1. Избыточные метрики

Многие метрики в БД не используются напрямую в модели. Они могут быть полезны для:
- Анализа и отчетности
- Детализации для кастом моделей
- Валидации данных

**Рекомендация:** Оставить избыточные метрики в шаблоне, но пометить их как опциональные в `dictionary_metrics`.

### 2. Отсутствующие метрики

Большинство отсутствующих метрик являются:
- **Вычисляемыми** (combine_from) - они могут быть рассчитаны автоматически
- **Детализацией** (finance/operating lease breakdown) - они могут быть добавлены аналитиком при необходимости
- **Компонентами CF** (change_ar, change_inventory, и т.д.) - они рассчитываются автоматически из BS

**Рекомендация:** 
- Для вычисляемых метрик: добавить в шаблон с пометкой `source: calculated`
- Для детализации: добавить в шаблон как опциональные метрики
- Для компонентов CF: оставить как вычисляемые

### 3. Следующие шаги

1. **Обновить dictionary_metrics** в шаблоне:
   - Добавить все необходимые метрики
   - Пометить опциональные метрики
   - Добавить метрики с `source: calculated`

2. **Обновить excel_loader.yaml**:
   - Добавить отсутствующие метрики в required_metrics
   - Настроить combine_from для вычисляемых метрик

3. **Доработать шаблон**:
   - Добавить визуальные подсказки для опциональных метрик
   - Добавить формулы для вычисляемых метрик (где возможно)

## Файлы

- **Анализ метрик:** `companies/us_steel/outputs/logs/required_metrics_analysis.txt`
- **Экспортированный Excel:** `companies/us_steel/data/excel/us_steel_input.xlsx`
- **Скрипт анализа:** `tools/analyze_required_metrics_for_excel.py`
- **Скрипт экспорта:** `tools/export_us_steel_to_excel.py`

