# ГМК Норильский Никель — Дневник построения модели

**Начало:** 2026-05-18
**Статус:** Этап 0 — Инициализация

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
- **Тикер:** MOEX: GMKN, LSE: MNOD (ADR)

### Ожидаемая структура
```
companies/nornickel/
├── configs/project.yaml
├── configs/stress_scenarios.yaml
├── configs/forecast/macro_ecm.yaml
├── data/excel/
├── notebooks/
└── outputs/
```

### Результат
- ✅ `init_company.py` отработал: 13 директорий, 5 YAML конфигов, 10 notebooks, Excel шаблон, README.md
- ✅ Доработан `init_company.py`: +data/statements/, +data/annual_reports/, +Excel шаблон автогенерация
- ✅ project.yaml с шаблонными значениями (IFRS, USD, metals)
- ✅ stress_scenarios.yaml — пустой шаблон
- ✅ 10 Jupyter notebooks скопированы с company_id=nornickel

### Решения
- ✅ **Источник данных:** ручной ввод в Excel (без парсера)
- ✅ **Горизонт истории:** с 2011 года (15 лет: 2011-2025)
- ✅ **Макро-факторы:** определить ПОСЛЕ анализа структуры выручки (→ Этап 2)

### Открытые вопросы (требуют решения)
- [ ] Сегменты выручки: Nickel, Palladium, Copper, Platinum + Other? → после анализа отчётности
- [ ] Макро-факторы: LME Ni, LME Pd, LME Cu, LME Pt, USD/RUB + что ещё? → после анализа сегментов
- [ ] Debt: есть ли детальный Note аналог для debt instruments?
- [ ] COGS: component-based (как Rusal) или standard PPI?
- [ ] Дивидендная политика: НорНикель исторически платит высокие дивиденды (50-100% FCF)

---

---

## Этап 1: Сбор и ввод данных

**Дата:** 2026-05-18
**Статус:** В ожидании — ручной ввод пользователем

### План
- ✅ XBRL парсинг: 2 файла (2023, 2025) → 162 серии, 5 лет данных (2021-2025)
- ✅ Excel v2 с корками и schedule sheets: `nornickel_unified.xlsx` (14 листов, 500/1545 ячеек = 32%)
- ✅ IS: 22 метрики (revenue, cogs_metal/other, gross_profit, g&a, ebit, finance, ebt, tax, ni)
- ✅ BS: 42 метрики (full IFRS structure с NN-specific: social liabilities, provisions)
- ✅ CF: 38 метрик (indirect method, full WC breakdown, investing, financing)
- ✅ XBRL данные синим шрифтом, 2011-2020 пустые для ручного ввода
- Пользователь заполняет 2011-2020 из МСФО отчётности (10 лет)

### Что есть из XBRL, что нет
**Есть (автозаполнено):**
- IS/BS/CF face statements: 2021-2025 (из двух iXBRL файлов)
- Equity Schedule (SOCIE): 2021-2025 по компонентам (SC, SP, RE, AOCI, NCI)
- Tax DTA/DTL: 2023-2025
- Lease liabilities: 2021-2025 (current + noncurrent)
- Provisions: 2023-2025 (current + noncurrent)
- Dividends paid по компонентам: 2021-2025

**Нет в iXBRL (нужен ручной ввод из Notes):**
- PPE components (Note): gross/accum_dep по категориям — нужен ввод
- Debt instruments (Note): отдельные инструменты с rates/maturity — нужен ввод
- Intangibles breakdown (Note) — нужен ввод
- Segments revenue (Ni/Pd/Cu/Pt) — нужен ввод из Annual Report
- Данные: IS / BS / CF за 2011-2025 (15 лет)
- По образцу `companies/rusal/data/rusal_complete_v4.xlsx` (21 лист)
- Минимум: листы `history_is`, `history_bs`, `history_cf`
- Желательно: `debt_instruments`, `ppe_components`, `segments`, `operational_drivers`

### Порядок действий после заполнения Excel
1. Загрузка через `01_Data_Loading.ipynb` → data_mart_v2.db
2. Анализ структуры выручки (сегменты, commodity drivers)
3. Определение макро-факторов на основе сегментов
4. Настройка project.yaml

### Долг: определить макро-факторы после анализа выручки
Логика: сначала понимаем из чего состоит выручка (Ni/Pd/Cu/Pt/Other), потом определяем какие LME цены нужны как макро-факторы. Это влияет на:
- revenue.macro_factors в project.yaml
- cogs.components (если component-based)
- stress_scenarios.yaml (какие шоки применять)

---

## Методология (по нашему workflow)

1. ✅ **Init** — `init_company.py` → структура + шаблоны (2026-05-18)
2. 🔄 **Data Collection** — ручной ввод IS/BS/CF 2011-2025 в Excel (ожидание)
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
