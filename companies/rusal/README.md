# United Company RUSAL

**company_id**: `rusal`
**Отрасль**: metals
**Валюта**: USD
**Стандарт учёта**: IFRS
**Версия данных**: Excel v5 (rusal_complete_v5.xlsx)
**Статус**: BS diff = 0.000000, CF diff = 0.000000

## Структура
```
companies/rusal/
  configs/
    project.yaml              # Главный конфиг модели (2026-2030)
    excel_loader.yaml         # Маппинг Excel → canonical + BS conventions
    accounting_conventions.yaml
    forecast/macro_ecm.yaml   # Настройки макро-прогноза
    stress_scenarios.yaml     # Стресс-сценарии
  data/
    rusal_complete_v5.xlsx    # Единый Excel (IS/BS/CF + schedules)
    history/                  # Исторические данные (IS/BS/CF)
    macro/                    # Макро-факторы
  notebooks/
    00_Build_Model_Main.ipynb
    01_Data_Loading.ipynb
    02_Test_Model_Module.ipynb
    03_Stress_Testing.ipynb
    04_Rating.ipynb
    05_Covenants.ipynb
  outputs/                    # Результаты модели
```

## BS Data Conventions (IFRS)
- `ppe_net` = owned PPE only (EXCLUDES RoU asset 49M) — `rou_asset` stored separately
- `ppe_gross`/`ppe_accum_dep` = auto-reconciled in loader if includes RoU
- `intangibles` = other intangibles only (EXCLUDES goodwill) — `goodwill` stored separately
- `short_term_debt` = loans CL − `interest_payable` (from Note 19, within loans line)
- `accounts_payable` = pure trade payables — `lease_liab_current` extracted from notes separately
- All liabilities stored as positive magnitudes (abs)

## Быстрый старт

1. Настройте параметры в `configs/project.yaml`
2. Загрузите данные:
```python
from engine.loader.excel import ExcelLoader
from engine.database.repository import Repository
from engine import DB_PATH
from pathlib import Path

with Repository(DB_PATH) as repo:
    loader = ExcelLoader(company_id='rusal', repo=repo,
                         db_unit='USD', input_default_unit='mUSD')
    result = loader.load(Path('companies/rusal/data/rusal_complete_v5.xlsx'))
    print(f'Warnings: {len(result.warnings)}, Errors: {len(result.errors)}')
```
3. Запустите модель: `python3 -m engine.orchestrator rusal --stress --rating --covenants`

## Команды
```bash
# Модель (без препроцессора)
python3 -m engine.orchestrator rusal --no-preprocess

# Полный прогон
python3 -m engine.orchestrator rusal --stress --rating --covenants
```
