# Дополнение к учебнику по финансовому моделированию

**Обновлено:** Апрель 2026

Данный документ содержит новые главы, дополняющие основной учебник
`financial_modeling_textbook_rewritten.pdf`.

**Основные изменения:**
- Добавлен второй практический пример — Rusal (IFRS, алюминий)
- Описан PDF парсер для автоматического извлечения данных
- Описан pipeline загрузки данных через ноутбуки
- Все ссылки обновлены на data_mart_v2.db

---


---

# PDF Parser Module

## Архитектура

| Метод | Режим | Применение |
|-------|-------|-----------|
| parse_section() | standard | IS, BS, CF, Inventory |
| parse_pivot_note() | text pivot | PPE, Intangibles, Provisions |
| parse_pivot_note() | wide pivot | Associates |
| parse_pivot_note() | sequential | DTA/DTL, Tax |
| parse_instrument_list() | instrument | Debt schedule |

## Исправленные баги

1. Fallback anti-trigger — skip TOC in fallback
2. anchor_mode: any — multi-page face sheets
3. Year range 2010+ — support pre-2015 PDFs
4. IS columns removal — fix wrong years
5. Non-consolidated BS anti-trigger

## Тестирование

22 unit tests, 12 smoke tests. Prod BS=0.000004.


---

# Практический пример: Rusal (IFRS, алюминиевая отрасль)

## Описание компании

UC Rusal — крупнейший производитель алюминия. IFRS, отчётность в USD.
Выручка 2024: $12.1 млрд. EBITDA margin: ~8-10%.

**Отличия от US Steel:**
- IFRS vs US GAAP
- Сегментное моделирование Revenue (Al + Alumina + Other)
- Component-based COGS (энергия, глинозём, труд)
- Floating rate debt привязан к CBR KeyRate

## Автоматическое получение данных через PDF парсер

Для Rusal данные извлекаются из PDF файлов EN Financial Statements.
Парсер имеет 3 метода, 5 режимов и покрывает 10 нот.

**Покрытие:** IS/BS/CF 2011-2025 (15 лет), Notes 2022-2025.

```bash
python3 tools/enrich_db_from_parser.py --pdf RUSAL_FS_2024_ENG.pdf
```

## Сегментное моделирование выручки

| Сегмент | Объём | Цена | Доля |
|---------|-------|------|------|
| Primary Al | EWA | f(lme_aluminium) | ~80% |
| Alumina | EWA | f(lme_alumina) | ~7% |
| Other | flat | flat | ~13% |

## Component-based COGS

| Компонент | Доля | Driver |
|-----------|------|--------|
| Алюмина | 37% | lme_alumina |
| Электроэнергия | 27% | russian_power_price |
| Труд | 12% | cpi_ru |
| Прочее | 24% | ppi_ru |

Dampening: 0.30, clamp ±0.06 (1σ).

## Macro drivers (8 факторов)

lme_aluminium, lme_alumina, usd_rub, brent, gdp_world, cpi_ru, ppi_ru, russian_power_price

## Floating rate debt (CBR KeyRate)

9 инструментов. CBR forecast: 2026=14%, 2027=11%, 2028=9%, 2030=7%.

## Корки (6 полных + 2 ratio-based)

PPE (273), Debt (668), Intangibles (24), Tax (6), Provisions (20), Associates (54).

## Результаты

| Год | Revenue | EBITDA | NI | Rating |
|-----|---------|--------|-----|--------|
| 2026 | 13,572M | 1,446M | 669M | B |
| 2028 | 15,084M | 1,369M | 688M | B |
| 2030 | 16,017M | 1,301M | 583M | B |

BS=0.000004, CF=0.000000.


---

# Загрузка данных через ноутбуки

## Workflow

PDF Parser → Excel (21 лист) → 01_Data_Loading.ipynb → data_mart_v2.db

## 01_Data_Loading.ipynb (9 ячеек)

Шаг 1: ExcelLoader — IS/BS/CF + PPE + canonical (2,280 строк)
Шаг 2: Schedule Loader — Notes корки (177 строк)
Итого: 2,457 строк → DB

## Тест-стенд

```bash
python3 tests/integration/setup_test_stand.py --company rusal
python3 tests/integration/verify_consistency.py --company rusal
```

11 таблиц сравниваются: prod vs test. BS Identity: 13/13 OK.

