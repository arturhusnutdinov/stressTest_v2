# Норникель — Аудит полноты данных

**Дата:** 2026-05-19  
**Excel:** `data/excel/nornickel_unified.xlsx` (22 листа)

---

## 📊 Сводка по листам

| Лист | Заполнено | Статус | Где взять недостающее |
|------|-----------|--------|----------------------|
| `history_is` | 97% (305/315) | 🟢 | sga = G&A + S&D из Databook IS |
| `history_bs` | 94% (605/645) | 🟢 | Lease/Social liabilities — Databook BS |
| `history_cf` | 68% (398/585) | 🟡 | WC-строки — Databook CASH FLOW (детализация) |
| `segments` | **0% (0/225)** | 🔴 | Databook IS (выручка) + PRODUCTION (объём) — **баг в скрипте** |
| `macro_factors` | 29% (44/150) | 🔴 | LME 2022-2025 + USD/RUB, Brent, CPI — внешние источники |
| `operational_drivers` | 90% (175/195) | 🟢 | Revenue по металлам — Databook IS 2022-2025 (NA в Databook → нужен Annual Report) |
| `cost_breakdown` | 92% (165/180) | 🟢 | Total Cash OpCosts — вычислить сумму компонентов |
| `capex_breakdown` | 57% (43/75) | 🟡 | Trans-Baikal, Energy — Databook CAPEX BREAKDOWN |
| `production_data` | **100%** (60/60) | 🟢 | — |
| `production_metrics` | **100%** (150/150) | 🟢 | — |
| `ore_output` | **100%** (210/210) | 🟢 | — |
| `recovery_rates` | 97% (218/225) | 🟢 | Trans-Baikal Cu до 2018 — не было дивизиона |
| `realized_prices` | 73% (44/60) | 🟡 | 2022-2025 — Databook IS не даёт разбивку, нужен Annual Report |
| `mineral_reserves` | 6% (6/105) | 🔵 | Статический лист (reserves as of 01.01.2026) |
| `debt_instruments` | **0%** | 🔴 | Annual Report 2024 стр. 140 + Databook DEBT |
| `ppe_components` | частично | 🔴 | Databook BALANCE Note 14 (нужен парсинг) |
| `dict_metrics` | **0%** | 🔴 | Ручное заполнение по методологии |
| `Tax_DTA_DTL` | частично (2021-2025) | 🟡 | Databook BALANCE DTA/DTL rows |
| `Lease_Schedule` | частично (2021-2025) | 🟡 | Databook BS lease rows |
| `Provisions_Detail` | частично (2021-2025) | 🟡 | Databook BS provisions rows |
| `Equity_Schedule` | частично (2021-2025) | 🟡 | Databook SOCIE / BS equity rows |

---

## 🔴 Критические проблемы

### 1. `segments` — полностью пуст (баг скрипта)
**Причина:** имена метрик в Excel (`revenue_musd`, `volume_kt`, `avg_price_usd_t`) не совпадают с теми, что ожидал скрипт populate_nornickel_excel.py.
**Решение:** исправить скрипт. Данные есть в Databook IS (revenue by metal) и PRODUCTION DATA (volume).
**Источник:** Databook, листы INCOME STATEMENT + PRODUCTION DATA.

### 2. `debt_instruments` — полностью пуст
**Решение:** Annual Report 2024 стр. 140 содержит таблицу всех 10 выпусков облигаций (купон, дата погашения, объём, валюта). Также Databook DEBT AND LIQUIDITY.
**Источник:** Annual Report 2024 стр. 140 + Databook.

### 3. `macro_factors` — USD/RUB, Brent, CPI, PPI, GDP пусты
**Решение:** загрузка из внешних макро-источников (FRED, World Bank, MOEX).
**Источник:** `macro/global/drivers/` или внешние CSV.

---

## 🟡 Умеренные проблемы

### 4. `history_cf` — 68%, не хватает рабочего капитала за 2011-2020
Databook CF имеет полные данные, скрипт не распарсил все строки WC.
**Источник:** Databook CASH FLOW STATEMENT.

### 5. `realized_prices` / revenue by metal — 2022-2025
Databook IS даёт разбивку выручки по металлам только до 2021. С 2022 — NA.
**Источник:** Annual Report, Note 7 (Segment Information). Нужен ручной ввод.

### 6. Schedules (Tax, Lease, Provisions, Equity) — только 2021-2025
XBRL дал 2021-2025. Databook BS содержит эти строки за все годы, нужно распарсить.
**Источник:** Databook BALANCE.

---

## 📁 Новые файлы от пользователя (19 мая)

### annual_reports/ (14 файлов)
| Файл | Год | Размер |
|------|-----|--------|
| `2024_Annual_Report_ru.pdf` | 2024 | 42 MB |
| `2024_Factsheet.pdf` | 2024 | 36 MB |
| `2023-Annual-Report-of-PJSC-MMC-Norilsk-Nickel.pdf` | 2023 | 24 MB |
| `2022_Annual_Report_of_PJSC_MMC_Norilsk_Nickel_eng.pdf` | 2022 | 117 MB |
| `AR_2021_en.pdf` | 2021 | 22 MB |
| `2020.pdf` | 2020 | 15 MB |
| `2019.pdf` | 2019 | 32 MB |
| `2018en_.pdf` | 2018 | 10 MB |
| `2017en_.pdf` | 2017 | 7 MB |
| `2016en.pdf` | 2016 | 17 MB |
| `2014en.pdf` | 2014 | 13 MB |
| `Nornickel_Factsheet_2022_eng.pdf` | 2022 | 23 MB |
| `Nornickel_Factsheet_2021.pdf` | 2021 | 6 MB |
| `Nornickel_Factsheet_2020.pdf` | 2020 | 5 MB |

**Нет:** Annual Reports 2013, 2015; Factsheets 2016-2019, 2023.

### operational/ (12 файлов)
| Файл | Год |
|------|-----|
| `file2009_full.pdf` | 2009 |
| `production_fy2014_2c_eng_1_full.pdf` | 2014 |
| `proizvodstvennij_press_reliz_za_4kv_i_2015_g_eng_final_1_full.pdf` | 2015 |
| `press_release_4q_and_2016_eng_9_full.pdf` | 2016 |
| `press_release_4q-and-2017_eng_final_full.pdf` | 2017 |
| `Press_release_4Q_and_2018_ENG_Final_full.pdf` | 2018 |
| `Press_release_FY2019_ENG_Final_FULL.pdf` | 2019 |
| `NORNICKEL_PRODUCTION_RESULTS_FOR_FY2020_full.pdf` | 2020 |
| `NORNICKEL_PRODUCTION_RESULTS_FY2021_ENG_full.pdf` | 2021 |
| `NORNICKEL_PRODUCTION_RESULTS_FY2022_full.pdf` | 2022 |
| `nornickel_production_results_fy2023_eng_full.pdf` | 2023 |
| `nornickel_production_results_2024_eng_full.pdf` | 2024 |
| `nornickel_production_results_2025_rus_full.pdf` | 2025 |

✅ **Полный комплект 2009, 2014-2025!** Не хватает 2010-2013.

### statements/ (новые)
| Файл | Год |
|------|-----|
| `file2016.pdf` | 2016 |
| `2200_nn_ifrs_consolidated_fs_2013_eng_usd_04_04_2014_final.pdf` | 2013 |

✅ IFRS coverage: 2013-2025.

---

## 🎯 План действий

### Срочно (сегодня):
1. **Починить `segments`** — исправить скрипт под `revenue_musd`/`volume_kt`/`avg_price_usd_t`
2. **Дозаполнить `history_cf`** — WC-строки из Databook CF
3. **`debt_instruments`** — распарсить Annual Report 2024 стр. 140

### Средний приоритет:
4. **Schedules** (Tax/Lease/Provisions/Equity) — дозаполнить из Databook BALANCE за 2011-2020
5. **`realized_prices` 2022-2025** — вытащить из Annual Reports выручку по металлам
6. **`macro_factors`** — загрузить LME/USD-RUB/Brent из готовых CSV (если есть в `macro/global/drivers/`)

### Низкий приоритет (не блокирует модель):
7. `dict_metrics` — ручное заполнение
8. `ppe_components` — парсинг Note 14 из Annual Report
9. `mineral_reserves` — статические данные, не влияют на прогноз

---
