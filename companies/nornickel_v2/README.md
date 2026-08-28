# PJSC MMC Norilsk Nickel

**company_id**: `nornickel_v2`
**Отрасль**: metals
**Валюта**: USD
**Стандарт учёта**: IFRS
**История**: 2011-2025 (15 лет)
**Прогноз**: 2026-2028 (3 года)

## Данные (template_v3)

| Компонент | Количество | Источник |
|-----------|-----------|---------|
| IS метрики | 16 | Databook 12m 2025 |
| BS метрики | 26 | IFRS FS (USD consolidation) |
| CF метрики | 29 | IFRS FS |
| Операционные драйверы | 38 | Databook (production, prices, costs, capex) |
| Металлические сегменты | 5 | Ni, Cu, Pd, Pt, Other |
| Разбивка затрат | 14 | Databook COST BREAKDOWN |
| Долговые инструменты | 10 | FS notes |
| Макрофакторы | 4 | LME Ni/Cu/Pd/Pt |

## Сегменты выручки

| Сегмент | Доля ~2024 | Драйвер цены |
|---------|-----------|-------------|
| Nickel | ~21% | LME Nickel |
| Copper | ~22% | LME Copper |
| Palladium | ~38% | LME Palladium |
| Platinum | ~4% | LME Platinum |
| Other | ~5% | EWA |

## Структура
```
companies/nornickel_v2/
  configs/
    project.yaml              # 4 сегмента, 3yr forecast, LME-linked
    excel_loader.yaml         # Маппинг Excel → DB (metric_aliases)
    accounting_conventions.yaml
    forecast/macro_ecm.yaml   # VECM + MR для LME metals
    stress_scenarios.yaml
  data/
    excel/
      nornickel_v2_template_v3.xlsx   # Основной файл (18 листов, canonical)
      nornickel_v2_unified.xlsx       # Legacy format
    statements/               # МСФО отчётность
    annual_reports/           # Годовые отчёты
    macro/
    debt/
    operational/
  notebooks/
```

## Быстрый старт

```bash
# Загрузить template_v3 → DB
python3 tools/load_unified_excel.py --company nornickel_v2 \
    --excel companies/nornickel_v2/data/excel/nornickel_v2_template_v3.xlsx

# Полный прогон
python3 -m engine.orchestrator nornickel_v2 --stress --rating
```

## Ключевые особенности

- Revenue: Vol×Price по 4 металлам (LME-linked), other = EWA
- COGS: component-based (labour 30%, materials 17%, MET 15%, services 14%, energy 4%)
- CapEx: Polar Division + Kola + South + Bystrinsky + Environmental
- D&A: из EBITDA note (не split owned/RoU в Databook)
- BS: smart folding для non-standard items (social_liab, provisions, dividend_payable)
