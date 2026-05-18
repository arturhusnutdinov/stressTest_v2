# Norilsk Nickel (PJSC MMC Norilsk Nickel)

**company_id**: `nornickel`
**Отрасль**: metals
**Валюта**: USD
**Стандарт учёта**: IFRS

## Структура
```
companies/nornickel/
  configs/
    project.yaml              # Главный конфиг модели
    excel_loader.yaml         # Маппинг Excel → DB
    accounting_conventions.yaml
    forecast/macro_ecm.yaml   # Настройки макро-прогноза
    stress_scenarios.yaml     # Стресс-сценарии
  data/
    excel/                    # UNIFIED Excel с данными (IS/BS/CF/debt/macro)
    macro/                    # Макро-факторы (CSV)
    debt/                     # Долговые расписания
    operational/              # Операционные KPI
  notebooks/
    00_Build_Model_Main.ipynb # Главный pipeline
    01_Data_Loading.ipynb     # Загрузка данных
    02_Test_Model_Module.ipynb # Тестирование модели
    03_Stress_Testing.ipynb   # Стресс-тесты
    04_Rating.ipynb           # Кредитный рейтинг
    05_Covenants.ipynb        # Ковенанты
  outputs/                    # Результаты модели
```

## Быстрый старт

1. Заполните Excel: `data/excel/nornickel_unified.xlsx`
2. Настройте: `configs/project.yaml`
3. Загрузите данные: `notebooks/01_Data_Loading.ipynb`
4. Запустите модель: `notebooks/00_Build_Model_Main.ipynb`

## CLI
```bash
# Полный прогон
python3 -m engine.orchestrator nornickel --stress --rating

# Только модель
python3 -m engine.orchestrator nornickel --no-preprocess
```
