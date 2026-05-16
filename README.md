# stressTest Engine v2

Универсальный движок финансового моделирования (3-Statement Model).

## Быстрый старт

```python
from engine.orchestrator import build_model

result = build_model(
    company_id="us_steel",
    run_preprocessor=True,
    run_macro=True,
    run_model=True,
    run_stress=True,
    run_rating=True,
    run_covenants=True,
)
print(result.summary())
```

## Структура

```
engine/          ← движок (model, macro, stress, rating, covenants)
companies/       ← данные компаний
  us_steel/      ← пример: US Steel
    configs/     ← project.yaml, covenants.yaml
    data/        ← Excel файлы
    notebooks/   ← ноутбуки анализа
notebooks/       ← шаблонные ноутбуки
templates/       ← YAML и Excel шаблоны
tools/           ← init_company.py, ExcelExporter
docs/            ← документация
data_mart_v2.db  ← база данных
```

## Документация

- [docs/00_PROJECT_OVERVIEW.md](docs/00_PROJECT_OVERVIEW.md)
- [docs/01_MODELING_SCHEMA.md](docs/01_MODELING_SCHEMA.md)
- [docs/07_US_STEEL_EXAMPLE.md](docs/07_US_STEEL_EXAMPLE.md)

## Новая компания

```bash
python3 tools/init_company.py rusal \
    --name "United Company RUSAL" \
    --industry metals \
    --currency USD \
    --standard IFRS
```
