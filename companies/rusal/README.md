# United Company RUSAL

**company_id**: `rusal`
**Отрасль**: metals
**Валюта**: USD
**Стандарт учёта**: IFRS

## Структура
```
companies/rusal/
  configs/
    project.yaml              # Главный конфиг модели
    excel_loader.yaml         # Маппинг Excel → canonical
    accounting_conventions.yaml
    forecast/macro_ecm.yaml   # Настройки макро-прогноза
    stress_scenarios.yaml     # Стресс-сценарии
  data/
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

## Быстрый старт

1. Настройте параметры в `configs/project.yaml`
2. Загрузите исторические данные через `notebooks/00_Build_Model_Main.ipynb`
3. Запустите модель: `notebooks/00_Build_Model_Main.ipynb`
4. Анализируйте результаты: `notebooks/02_Test_Model_Module.ipynb`

## Команды
```bash
# Инициализация/обновление модели
cd /path/to/project
python3 -m engine.orchestrator rusal --no-preprocess

# Полный прогон
python3 -m engine.orchestrator rusal --stress --rating --covenants
```
