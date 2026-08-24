# ГМК Норильский Никель — Дневник построения модели

**Начало:** 2026-05-18
**Статус:** Этап 1 — Сбор данных ✅ (Excel заполнен 2011-2025 из Databook)

---

## Этап 0: Инициализация проекта

**Дата:** 2026-05-18
**Действие:** Создание структуры проекта через `tools/init_company.py`

### Параметры компании
- **Company ID:** `nornickel`
- **Название:** ПАО ГМК «Норильский никель»
- **Отрасль:** metals / mining (никель, палладий, медь, платина)
- **Валюта отчётности:** USD
- **Стандарт:** IFRS
- **Тикер:** MOEX: GMKN

### Результат
- ✅ `init_company.py` отработал: 13 директорий, 5 YAML конфигов, 10 notebooks, Excel шаблон, README.md
- ✅ Доработан `init_company.py`: +data/statements/, +data/annual_reports/, +Excel шаблон автогенерация
- ✅ project.yaml с шаблонными значениями (IFRS, USD, metals)
- ✅ stress_scenarios.yaml — пустой шаблон
- ✅ 10 Jupyter notebooks скопированы с company_id=nornickel

### Решения
- ✅ **Источник данных:** Databook Норникеля (2009-2025 IFRS) + XBRL (2023, 2025)
- ✅ **Горизонт истории:** 2011-2025 (15 лет)
- ✅ **Макро-факторы:** LME Ni, Pd, Cu, Pt, Brent, USD/RUB, CPI, PPI → после анализа выручки

---

## Этап 1: Сбор и ввод данных

**Дата:** 2026-05-18
**Статус:** ✅ Завершён — Excel заполнен из Databook + XBRL

### Источники данных
1. **Databook_12m_25_Final.xlsx** (скачан с nornickel.ru/investors) — основной источник
   - 17 листов: IS, BS, CF, Costs, CAPEX, Debt, Production, Ore, Recovery Rates, Reserves
   - Период: 2009-2025 (полугодовые + годовые)
   - Валюта: USD млн (IFRS)
   
2. **XBRL iXBRL** (2023 + 2025 отчёты) — 162 серии, 5 лет (2021-2025)

3. **Годовой отчёт 2024** (182 стр.) — выверка, MD&A, сегменты, риски

4. **Factsheet 2024** (21 стр.) — операционные показатели, производство

5. **Операционные результаты 2025** (PDF, 3 стр.) — production 2025 + guidance 2026

### Что заполнено в `nornickel_unified.xlsx`

| Лист | Строк | Источник | Период | Статус |
|------|-------|----------|--------|--------|
| `history_is` | 22 метрики | Databook IS + EBITDA Calc | 2011-2025 | ✅ |
| `history_bs` | 44 метрики | Databook BALANCE | 2011-2025 | ✅ |
| `history_cf` | 40 метрик | Databook CF | 2011-2025 | ✅ |
| `segments` | 16 (5 металлов × 3 метрики) | Databook IS + Production | 2011-2025 | ✅ |
| `macro_factors` | 10 факторов | Calculated realised prices | 2011-2025 | 🟡 цены реализации |
| `operational_drivers` | 8 драйверов | Databook Production + Ore | 2011-2025 | ✅ |
| `cost_breakdown` | 12 статей | Databook COST BREAKDOWN | 2011-2025 | ✅ новый лист |
| `capex_breakdown` | 5 статей | Databook CAPEX + CF | 2011-2025 | ✅ новый лист |
| `production_data` | 4 металла | Databook PRODUCTION + PDF 2025 | 2011-2025 | ✅ новый лист |

### Валидация (2024 данные vs Годовой отчёт)
- ✅ Revenue: 12,535 (100%)
- ✅ Metal sales: 11,848 (100%)
- ✅ EBITDA: считается из OpProfit + D&A + Impairment
- ✅ Net Income: 1,815 (100%)
- ✅ Total Assets: 23,170 (100%)
- ✅ ST Debt: 2,834 / LT Debt: 7,112 (100%)
- ✅ Total Equity: 8,097 (100%)
- ✅ CFO: 4,433 / CAPEX: -2,386 / CFF: -2,042 (100%)
- ⚠️ COGS: -6,221 vs AR -6,232 (Δ 11M, классиф. разница)

### Загруженные файлы
```
data/
├── excel/nornickel_unified.xlsx          ← заполнен (17 листов)
├── statements/
│   ├── Databook_12m_25_Final.xlsx        ← основной источник
│   ├── nn_ifrs_*.pdf (2014-2025)         ← 9 PDF отчётов
│   └── EngUSD/xbrl_extracted/             ← iXBRL (2023, 2025)
├── annual_reports/
│   ├── 2024_annual_report_*.pdf          ← 182 стр.
│   └── Nornickel-Factsheet-2024.pdf      ← 21 стр.
├── operational/
│   └── nornickel_production_results_2025_rus_full.pdf
└── analytics/                             ← создана, файлы требуют анкету
```

### Открытые вопросы → Этап 2
- [ ] Сегменты выручки: Ni/Pd/Cu/Pt/Other — данные есть, нужно проанализировать доли
- [ ] Макро-факторы: LME Ni, Pd, Cu, Pt + USD/RUB + Brent — загрузить историю цен
- [ ] COGS: component-based (энергия, материалы, труд) или PPI-indexed?
- [ ] Debt instruments: детальный список из Annual Report (10 выпусков)
- [ ] Дивидендная политика: за 2024 не платили, за 2025 — решение 27.06.2025

---

## Методология (по нашему workflow)

1. ✅ **Init** — `init_company.py` → структура + шаблоны (2026-05-18)
2. ✅ **Data Collection** — Databook + XBRL → Excel 2011-2025 (2026-05-18)
3. ⬜ **Data Loading** — `01_Data_Loading.ipynb` → data_mart_v2.db
4. ⬜ **Revenue Analysis** — анализ сегментов → определение макро-факторов
5. ⬜ **Macro Data** — загрузка LME Ni/Pd/Cu/Pt + USD/RUB + прочие факторы
6. ⬜ **YAML Config** — настроить project.yaml (revenue, cogs, debt, macro)
7. ⬜ **Macro Forecast** — VECM/ARIMA для макро-факторов
8. ⬜ **Model Run** — `build_model('nornickel')` → BS check
9. ⬜ **Stress Scenarios** — stress_scenarios.yaml (Ni/Pd price shocks, FX, rates)
10. ⬜ **Rating & Covenants** — настроить rating/covenants секции
11. ⬜ **Validation** — train/test split, regression tests

---
