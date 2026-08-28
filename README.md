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
  us_steel/      ← US Steel (US GAAP, 2010-2024)
  rusal/         ← UC RUSAL (IFRS, 2011-2025, 69 debt instruments)
  nornickel/     ← Nornickel v1 (source data, Databook)
  nornickel_v2/  ← Nornickel v2 (template_v3, 38 ops drivers, 5 segments)
notebooks/       ← шаблонные ноутбуки
templates/       ← YAML и Excel шаблоны (template_UNIFIED_v3.xlsx)
tools/           ← init_company.py, ExcelExporter
docs/            ← документация (22 файла)
data_mart_v2.db  ← база данных (39 таблиц)
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

## Template v3

Стандартный формат загрузки данных (18 листов, канонические метрики):

```bash
# Загрузить Excel → DB
python3 tools/load_unified_excel.py --company nornickel_v2 \
    --excel companies/nornickel_v2/data/excel/nornickel_v2_template_v3.xlsx
```

Шаблон: `templates/excel_templates/template_UNIFIED_v3.xlsx`

Заполненные файлы:
- Nornickel: `companies/nornickel_v2/data/excel/nornickel_v2_template_v3.xlsx`
- Rusal: `companies/rusal/data/excel/rusal_template_v3.xlsx`
