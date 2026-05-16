# US STEEL — Модель финансового прогнозирования

## Структура данных

### Витрина данных (FinancialDataMart)

- Все исторические данные, макро-факторы и результаты модели хранятся в централизованной БД `data_mart.db` в корне проекта.
- Основные таблицы для US Steel:
  - `history_is` / `history_bs` / `history_cf` — история отчетности (wide → canonical form)
  - `segment_metrics` — выручка по сегментам и операционные драйверы (2010-2024)
  - `macro_factors`, `macro_forecasts` — макроистория и прогнозы
  - `model_results`, `model_parameters`, `outputs` — результаты моделей, параметры, дополнительные таблицы (стресс, ковенанты и т.д.)
- Доступ к данным: `from engine.database.data_mart import get_data_mart` и метод `mart = get_data_mart(ROOT, "us_steel")`.

```python
from pathlib import Path
from engine.database.data_mart import get_data_mart

root = Path('.')
with get_data_mart(root, 'us_steel') as mart:
    hist_is = mart.get_history_income_statement(canonical=True)
    latest_version = mart.get_existing_versions()[0]['version']
    cf_forecast = mart.get_model_results(latest_version, 'CF', canonical=True)
```

> ℹ️ CSV-файлы в `companies/us_steel/history` и `companies/us_steel/data` остаются источником для первичной загрузки/контроля качества, но движок читает данные исключительно из витрины.

### Финансовая история (2010-2024)
- **IS**: таблица `history_is` (CSV-шаблон: `history/is_history_us_steel.csv`)
- **BS**: таблица `history_bs` (CSV-шаблон: `history/bs_history_us_steel.csv`)
- **CF**: таблица `history_cf` (CSV-шаблон: `history/cf_history_us_steel.csv`)

**Train/Test Split:**
- **Обучающая выборка**: 2010-2022 (13 лет)
- **Тестовая выборка**: 2023-2024 (2 лет для валидации)


### Макро-факторы

**Макро-факторы (8 шт.) в `macro_factors` / `macro_forecasts`:**
- `gdp_us` — US GDP (CSV-шаблон: `macro/gdp_us.csv`)
- `industrial_production_us` — Industrial Production (CSV-шаблон: `macro/industrial_production_us.csv`)
- `dxy` — Dollar Index
- `steel_price_hrc_usd` — Steel Price HRC
- `iron_ore_price_usd` — Iron Ore Price
- `cpi_us` — Consumer Price Index
- `ppi_us` — Producer Price Index
- `world_gdp` — Global GDP


### Структура долга

- Расписание долга загружается в `outputs` (тип `DEBT_WATERFALL`) и `model_parameters`.
- CSV-шаблон (для редактирования/импорта): `data/debt/debt_schedule.csv`
- **Лизинг (IFRS16)**: `history_bs` содержит `rou_asset`, `history_cf` — `lease_payments_cff`, `history_is` — `lease_interest` (загружено из EDGAR schedules).

Количество инструментов: 9

- **RC_Facility_A**: ставка 8.00%, 2010-2029, тип: revolver, лимит: $2,000, min cash: $500
- **RC_Facility_B**: ставка 7.50%, 2015-2029, тип: revolver, лимит: $1,500, min cash: $300
- **Term_Loan_2018**: ставка 4.20%, 2010-2018, тип: amortizing
- **Term_Loan_2023**: ставка 4.80%, 2015-2023, тип: amortizing
- **Term_Loan_2027**: ставка 5.10%, 2020-2027, тип: amortizing
- **Bond_2025_Bullet**: ставка 4.50%, 2010-2025, тип: bullet
- **Bond_2028_Bullet**: ставка 5.20%, 2017-2028, тип: bullet
- **Bond_2030_Callable**: ставка 5.50%, 2020-2030, тип: bullet
- **Variable_Rate_Note**: ставка 4.00%, 2021-2026, тип: amortizing


### Конфигурация

- `configs/project.yaml` — настроен под отрасль:
  - Основной драйвер выручки: `steel_price_hrc`
  - Макро-факторы: 8 факторов
  - RC включен: `limit: 2,000`, `min_cash: 500`
  - Train/test split: `train_end_year: 2022`
  - **Tax Loss Carryforward (NOL)**:
    - `nol_opening_balance: 0` — входящий остаток убытков
    - `nol_max_utilization_pct: 80` — макс % использования за год
    - `nol_expiration_years: 20` — срок действия NOL
- `configs/edgar_loader.yaml` — правила загрузки EDGAR (история, сегменты, шедулы lease/PPE/tax, debt instruments & cashflows).


## Запуск модели

```bash
# 1. Запуск макро-прогноза
python3 tools/run_vecm.py --config configs/forecast/macro_ecm.yaml --company us_steel

# 2. Запуск модели
python3 -c "
from pathlib import Path
from engine.model.core import build_model
root = Path('.')
build_model(root, 'us_steel')
"
```

## Тестирование модели

### Через Jupyter Notebooks

**Рекомендуемый способ для детального анализа:**

1. **02_Test_Model_Module.ipynb** — комплексный тестовый ноутбук (полностью переработанная версия):
   ```bash
   cd companies/us_steel/notebooks
   jupyter notebook 02_Test_Model_Module.ipynb
   ```
   
   Включает (14 разделов):
   - Сводную таблицу 3-Statement (история + прогноз)
   - Детальный анализ всех статей
   - Debt corkscrew по инструментам
   - Валидацию финансовых связей
   - Графики Actual vs Fitted

2. **01_Test_Macro_Module.ipynb** — тестирование макропрогноза
3. **00_Build_Model_Main.ipynb** — главный ноутбук построения модели
4. **99_Configure_YAML.ipynb** — интерактивная настройка конфигурации

Подробные инструкции: см. `notebooks/README_TESTS.md`

---

## 🎬 Демонстрация полного цикла построения модели

Для имитации построения модели с нуля (от загрузки данных до построения модели):

### Шаг 1: Подготовка Excel файлов

Уже подготовлены файлы с историческими данными US STEEL в директории `data_input/`:

```bash
ls companies/us_steel/data_input/
```

**Структура:**
- `Income_Statement_US_STEEL.xlsx` - IS данные
- `Balance_Sheet_US_STEEL.xlsx` - BS данные
- `Cash_Flow_US_STEEL.xlsx` - CF данные
- `Debt_Schedule_US_STEEL.xlsx` - Расписание долга
- `macro_factors/` - 8 макро-факторов в формате Excel
- `operational/` - Операционные данные

### Шаг 2: Загрузка данных в Data Mart

- **Из EDGAR:** `tools/load_edgar_to_data_mart.py` (история, сегменты, tax schedule, debt) — см. `docs/EDGAR_LOADER.md`.
- **Из Excel шаблона:** `tools/load_excel_to_data_mart.py` (история, шедулы, сегменты, драйверы, долг) — см. `docs/EXCEL_DATA_LOADER.md`.
- **Макро:** `tools/load_macro_excel.py`.

Все загрузчики пишут напрямую в `data_mart.db`; CSV/Excel оставляем как артефакт для ревью.

### Шаг 3: Настройка конфигурации через ноутбук

Откройте интерактивный редактор конфигурации:

```bash
jupyter notebook companies/us_steel/notebooks/99_Configure_YAML.ipynb
```

### Шаг 4: Построение модели

```bash
jupyter notebook companies/us_steel/notebooks/00_Build_Model_Main.ipynb
```

---

## 📋 Чек-лист демо-пайплайна

- [ ] 1. Excel файлы созданы в `data_input/`
- [ ] 2. Данные загружены через `tools/load_edgar_to_data_mart.py` или `tools/load_excel_to_data_mart.py`
- [ ] 3. Конфигурация настроена через `99_Configure_YAML.ipynb`
- [ ] 4. Валидация данных пройдена
- [ ] 5. Модель построена (через ноутбук или Python)
- [ ] 6. Результаты проанализированы в `02_Test_Model_Module.ipynb`

**Готово! Модель работает от загрузки данных до построения прогноза.**

