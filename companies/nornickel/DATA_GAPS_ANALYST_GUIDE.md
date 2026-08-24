# Норникель — Инструкция по заполнению пробелов

**Дата:** 2026-05-19  
**Excel:** `nornickel_unified.xlsx` (14 листов `db_*` с сырыми данными)  
**Источники:** папки `data/annual_reports/`, `data/statements/`, `data/operational/`

---

## 🎯 Приоритет 1: Критично для модели

### 1. Выручка по металлам 2022-2025
**Листы:** `db_income_statement`, `db_revenue_breakdown`  
**Пробел:** строки Nickel, Copper, Palladium, Platinum, Other metals — 2022-2025  
**Где взять:**

| Год | Файл | Страницы |
|-----|------|----------|
| 2022 | `annual_reports/2022_Annual_Report_...eng.pdf` | Notes to FS, Note 7 Segment Information |
| 2023 | `annual_reports/2023-Annual-Report-...pdf` | Note 7 |
| 2024 | `annual_reports/2024_Annual_Report_ru.pdf` | стр. 57 (MD&A), Note 7 |
| 2025 | `statements/Databook_12m_25_Final.xlsx` | REVENUE BREAKDOWN → Metal Sales row 31 (total), доли из Annual Report |

**Что заполнять:**
```
db_income_statement rows 2-9 (металлы):
  Nickel 2, Copper 2, Palladium 2, Platinum 2, 
  Rhodium 2, Gold 2, Semiproducts 2, Other metals 2
  → сумма должна сойтись с Revenue from metal sales (row 10)

db_revenue_breakdown rows 15-30 (металлы + %):
  Те же металлы + including semi-products
  rows 32-40 (доли %) → сумма = 100%
```

---

## 🟡 Приоритет 2: Важно для полноты

### 2. Географическая разбивка выручки 2024-2025
**Лист:** `db_revenue_breakdown`  
**Пробел:** Europe, Asia, Americas, Russia/CIS — 2024-2025  
**Где взять:** Annual Report 2024, стр. 3 (диаграмма: Asia 47%, Europe 24%, Russia 15%, Americas 7%)  
**Формат:** строки 42-54 → % от metal sales

### 3. CAPEX 2011
**Лист:** `db_capex_breakdown`  
**Пробел:** все строки — только 2011 отсутствует (данные с 2012)  
**Где взять:** Databook FINANCIAL HIGHLIGHTS, строка Capital expenditures → $2,232M (2011). Детализация по дивизионам за 2011 — Annual Report 2011 (если есть) или оставить пустым.

### 4. Debt maturity schedule (актуализация)
**Лист:** `db_debt_liquidity`  
**Пробел:** строки 2014-2030+ (это НЕ годы, а сроки погашения!) заполнены данными только по 2021-2023.  
**Где взять:** Annual Report 2024, стр. 140 — таблица всех облигаций с датами погашения. Databook DEBT AND LIQUIDITY, строки "DEBT STRUCTURE".

### 5. Lease liabilities 2011-2013
**Лист:** `db_debt_liquidity`  
**Пробел:** Lease liabilities — 2011-2013  
**Где взять:** Databook BALANCE (Lease liabilities row, если есть за эти годы). IFRS 16 вступил в силу с 2019, до этого — finance leases.

---

## 🔵 Приоритет 3: Детализация (не блокирует модель)

### 6. EBITDA по сегментам (исторические)
**Лист:** `db_ebitda`  
**Пробел:** Kola division до 2020, KGMK Group/NN Harjavalta после 2020, GRK Bystrinskoye до 2016.  
**Причина:** сегменты менялись (KGMK + Harjavalta → Kola division с 2021, Bystrinsky с 2017).  
**Где взять:** Annual Reports за соответствующие годы, MD&A section.  
**Важность:** низкая — это историческая аналитика, не влияет на прогноз.

### 7. Ore output для Trans-Baikal до 2018
**Лист:** `db_ore_output`  
**Пробел:** строки Trans-Baikal Division, Bystrinskoye field — до 2018  
**Причина:** Bystrinsky GOK запущен в коммерческую эксплуатацию в 2019.  
**Заполнять:** нулями или "—" (не было добычи).

### 8. Средние содержания металлов в руде (grades)
**Лист:** `db_ore_output`  
**Пробел:** строки AVERAGE MINED METAL GRADES, Ni%, Cu%, PGM g/t — полностью пусто  
**Где взять:** Databook лист ORE OUTPUT — эти данные могут быть в других колонках. Или Factsheet (стр. 8): Ni 0.52-1.15%, Cu 0.21-1.87%, PGMs 0.08-6.28 g/t.  
**Важность:** средняя — для понимания тренда качества руды.

### 9. Recovery rates — smelting breakdown
**Лист:** `db_recovery_rates`  
**Пробел:** секции METALS RECOVERY IN SMELTING (Ni, Cu, PGM) — пусто  
**Где взять:** Databook RECOVERY RATES, строки 14-24 (smelting rows). Возможно, не скопировались из-за формата заголовков.  
**Статус:** ⚠️ возможно баг зеркалирования — перепроверить.

---

## ⬜ Приоритет 4: Опционально / Для справки

### 10. Section headers (не данные)
**Листы:** `db_balance_sheet`, `db_cash_flow`, `db_cost_breakdown`, `db_working_capital`  
**Пробел:** строки-заголовки типа "ASSETS", "EQUITY AND LIABILITIES", "OPERATING ACTIVITIES"  
**Действие:** ⚠️ не заполнять — это структурные метки Databook.

### 11. Финансовые коэффициенты (Credit Ratios)
**Лист:** `db_financial_ratios`  
**Пробел:** секция Credit Ratios — пусто  
**Где взять:** Databook SELECTED FINANCIAL RATIOS, строки 9-22. Возможно, не скопировались.

### 12. Долговые инструменты (как отдельные записи)
**Лист:** `debt_instruments` (в оригинальной секции)  
**Пробел:** полностью пуст  
**Где взять:** Annual Report 2024, стр. 140 — таблица 10 выпусков облигаций с ISIN, купоном, датой погашения.

---

## 📁 Доступные файлы для заполнения

| Папка | Годы | Что содержит |
|-------|------|-------------|
| `annual_reports/` | 2014, 2016-2024 | Годовые отчёты (MD&A + Notes + FS) |
| `annual_reports/*Factsheet*` | 2020-2022, 2024 | Factsheets (операционные + фин. показатели) |
| `statements/Databook_12m_25_Final.xlsx` | 2009-2025 | Все финансовые и операционные данные |
| `statements/ifrs_*.pdf` | 2013-2025 | IFRS financial statements |
| `operational/` | 2009, 2014-2025 | Пресс-релизы с производственными результатами |
| `analytics/` | Dec 2025 | Обзоры рынка Ni, Cu, PGM (цены, балансы) |

---

## 📊 Сводка: сколько строк заполнять

| Лист | Всего строк | С пробелами | На заполнение |
|------|------------|-------------|---------------|
| `db_income_statement` | 54 | 9 | **9 строк × 4 года (2022-2025)** |
| `db_revenue_breakdown` | 64 | 50 | ~10 строк металлов + ~10 строк географии |
| `db_capex_breakdown` | 45 | 26 | 1 год (2011) × 26 строк |
| `db_debt_liquidity` | 45 | 22 | Maturity schedule + lease 2011-2013 |
| `db_ebitda` | 33 | 12 | Сегменты (исторические, опционально) |
| `db_ore_output` | 65 | 14 | Grades + Trans-Baikal до 2018 |
| `db_recovery_rates` | 24 | 8 | Smelting rows (проверить) |
| **Итого реально заполнять** | | | **~40-50 ячеек вручную** |

> ⚠️ Большинство «пробелов» — это section headers (не данные), изменившаяся сегментация, или периоды до запуска активов. Реальных дыр для ручного заполнения ~40-50 значений.

---
