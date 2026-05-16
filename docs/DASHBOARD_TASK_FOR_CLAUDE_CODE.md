# Задача: Доработка ноутбука `06_Financial_Dashboard.ipynb`

**Файл:** `companies/rusal/notebooks/06_Financial_Dashboard.ipynb`  
**Шаблон:** `templates/notebooks/06_Financial_Dashboard.ipynb`  
**Данные:** `data_mart_v2.db` + `companies/rusal/data/rusal_unified_complete.xlsx`

---

## Контекст

Ноутбук уже создан и запускается. Основа — plotly, данные из `Repository(DB_PATH)` и `build_model()`. Нужно расширить до профессионального аналитического отчёта по образцу credit research note (S&P / JPMorgan стиль): плотные таблицы, аналитические комментарии, исторические данные с 2019, макрораздел, сегментная выручка.

---

## Данные в БД и xlsb (что использовать)

### Производственные KPI (из `production_kpi` + `Заключение` листа xlsb)

| Год | Производство Al, kt | Продажи Al, kt | Cost/t ($) | Avg Price/t ($) | EBITDA/t ($) |
|-----|--------------------:|---------------:|-----------:|----------------:|-------------:|
| 2019 | 3,757 | 4,176 | 1,624 | 1,920 | 231 |
| 2020 | 3,755 | 3,926 | 1,508 | 1,805 | 222 |
| 2021 | 3,764 | 3,904 | 1,631 | 2,553 | 741 |
| 2022 | 3,835 | 3,896 | 2,183 | 2,976 | 521 |
| 2023 | 3,848 | 4,153 | 2,166 | 2,439 | 189 |
| 2024 | 3,992 | 3,859 | 2,017 | 2,520 | 386 |

Также: Бокситы (млн т): 16.0 / 14.8 / 15.0 / 12.3 / 13.4 / 15.9  
Глинозём (млн т): 7.9 / 8.2 / 8.3 / 5.9 / 5.1 / 6.4  
Загрузка мощностей: мощность 4,205 kt/год; efficiency 2019–2024 растёт

### Сегментная выручка (из `revenue_segments` + `Financial Statements` листа)

| Год | Al ($M) | Alumina ($M) | Foil ($M) | Other ($M) | Total ($M) |
|-----|--------:|-------------:|----------:|-----------:|-----------:|
| 2020 | 8,566 | — | — | — | 8,566 |
| 2021 | 9,966 | 610 | 515 | 903 | 11,994 |
| 2022 | 11,593 | 550 | 581 | 1,250 | 13,974 |
| 2023 | 10,129 | 340 | 550 | 1,194 | 12,213 |
| 2024 | ~10,291 | ~483 | ~531 | ~777 | 12,082 |

Объёмы: Al kt: 3,904 / 3,896 / 4,153 / 3,859; Alumina kt: 1,677 / 1,169 / 759 / 496; Foil kt: 1,250 / 1,194 / 1,146

### COGS breakdown (из `Raw Data_` листа xlsb)

Компоненты как % от выручки:
- Alumina costs: ~35–40% (commodity-linked, LME Alumina)
- Energy costs: ~25–30% (RUB-тариф)
- Personnel: ~12–16%
- Repairs & maintenance: ~5%
- Distribution expenses: ~6–7% (отдельная строка IS)
- Administrative expenses: ~5–6%
- D&A: ~4–5%

### Финансовые коэффициенты (из `_REPORT` листа xlsb — всё есть в БД)

**Рентабельность:**
| Коэффициент | 2020 | 2021 | 2022 | 2023 | 2024 |
|-------------|-----:|-----:|-----:|-----:|-----:|
| EBITDA margin | 10.2% | 24.1% | 14.5% | 6.4% | 12.3% |
| Net margin | 8.9% | 26.9% | 12.8% | 2.3% | 6.6% |
| Gross margin | 17.0% | 31.0% | 26.5% | 14.5% | 23.3% |
| ROA | 4.4% | 15.4% | 7.3% | 1.3% | 3.6% |
| ROE | — | 30.6% | 14.6% | 2.6% | 7.2% |

**Долговая нагрузка:**
| Коэффициент | 2020 | 2021 | 2022 | 2023 | 2024 |
|-------------|-----:|-----:|-----:|-----:|-----:|
| Debt/EBITDA | 2.3x | 4.7x | 10.0x | 5.3x | — |
| ND/EBITDA | — | 2.9x | 3.3x | 3.6x | 3.6x |
| Total Debt ($B) | 7.8 | 6.7 | 9.5 | 7.9 | 7.9 |

**Покрытие:**
| Коэффициент | 2020 | 2021 | 2022 | 2023 | 2024 |
|-------------|-----:|-----:|-----:|-----:|-----:|
| ICR (EBIT/Interest) | 0.5x | 2.8x | 1.9x | -0.2x | 4.9x |
| ICR incl. Associates | — | 6.4x | 3.5x | 2.8x | 2.8x |

**Ликвидность:**
| Коэффициент | 2020 | 2021 | 2022 | 2023 | 2024 |
|-------------|-----:|-----:|-----:|-----:|-----:|
| Current Ratio | 2.1x | 1.8x | 2.2x | 2.1x | 1.2x |
| Quick Ratio | 1.3x | 1.0x | 1.2x | 1.2x | 0.6x |

**Оборачиваемость (Cash Conversion Cycle):**
| Показатель | 2021 | 2022 | 2023 | 2024 |
|------------|-----:|-----:|-----:|-----:|
| Inventory Days | 128 | 176 | 160 | 187 |
| AR Days | 50 | 31 | 34 | 44 |
| AP Days | 102 | 106 | 60 | 82 |
| Operating Cycle | 178 | 207 | 194 | 231 |
| CCC | 75 | 101 | 134 | 150 |

**CF показатели:**
| Показатель | 2021 | 2022 | 2023 | 2024 |
|------------|-----:|-----:|-----:|-----:|
| FFO ($M) | 4,282 | 2,824 | 1,302 | 1,752 |
| CFO ($M) | 1,146 | -412 | 1,760 | 483 |
| CapEx ($M) | -1,192 | -1,239 | -1,056 | -1,366 |
| FCF ($M) | -18 | -1,614 | 738 | -849 |
| Div. Nornickel ($M) | 620 | 1,639 | 0 | 416 |

### Отраслевые данные (из `Заключение` листа xlsb)

Мировое производство алюминия по странам:
- China: 55% / 38.5 mn t
- Russia: 6% / 4.2 mn t (Rusal — монопроизводитель)
- India: 5% / 3.5 mn t
- Canada: 4% / 2.8 mn t
- UAE: 3% / 2.1 mn t
- Others: 27% / 18.9 mn t

### Макро данные (из `Macro Data` листа xlsb + `macro_factors` БД)

LME Aluminium форвардная кривая (из xlsb, фактические данные):
- Cash: $2,712–2,713/t
- 3-month: $2,688–2,689/t
- Dec-26: $2,712–2,717/t
- Dec-27: $2,727–2,732/t
- Dec-28: $2,747–2,752/t

LME Alumina квартальные цены:
- Q3 2023: $336/t, Q4 2023: $334/t
- Q1 2024: $366/t, Q2 2024: $427/t
- Q3 2024: $504/t, Q4 2024: $695/t

История LME Al по годам (из `macro_factors` в БД): 2015–2024

### Долговые инструменты (из `Loans and Borrowings` + `Bonds` листов xlsb)

**Secured loans:**
| Инструмент | Баланс $M | Ставка | Погашения по годам ($M) |
|-----------|----------:|--------|------------------------|
| RUB KeyRate+2.2% | 98 | floating | 26/36/36/0/0 |
| RUB KeyRate+3.15% | 218 | floating | 4/4/5/10/13 |
| RUB KeyRate+5.95% | 133 | floating | 15/59/59/0/0 |
| CNY 4.75% | 1,564 | fixed | 522/521/521/0/0 |

**Unsecured bank loans:**
| Инструмент | Баланс $M | Ставка | Погашения по годам ($M) |
|-----------|----------:|--------|------------------------|
| CNY LPR1Y+3.1% | 333 | floating | 0/333/0/0/0 |
| RUB KeyRate+2% | 339 | floating | 339/0/0/0/0 |
| RUB KeyRate+2.45% | 492 | floating | 0/0/164/164/164 |
| RUB KeyRate+3% | 97 | floating | 6/19/0/72/0 |
| CNY 5.25% | 729 | fixed | 729/0/0/0/0 |
| RUB 13.5% | 25 | fixed | 25/0/0/0/0 |

**Bonds (ключевые серии 2024):**
| Серия | Номинал $M | Купон | Дата погашения |
|-------|----------:|-------|---------------|
| БО-001P-04 | 101 | 5.95% | 2025 |
| БО-001Р-01 | 792 | 3.75% | 2025 |
| БО-001Р-02 | 132 | 3.95% | 2025 |
| БО-001Р-03 | 396 | LPR1Y+0.2% | 2025 |
| 001РС-01–04 | 1,173 | 3.75% | 2025 |
| БО-05 / БО-06 | 78 | 8.5% | 2027 (оферта) |
| БО-001Р-05 | 79 | 6.7% | 2026 |
| БО-001Р-06 | 132 | 7.2% | 2026 |
| БО-001Р-07 | 119 | 7.9% | 2027 |
| БО-001Р-08 | 85 | 9.25% | 2027 |
| БО-001Р-09 | 295 | КС+2.2% | 2027 |
| БО-001Р-10 | 98 | КС+2.25% | 2027 |
| БО-001Р-11 | 98 | КС+2.5% | 2029 |

---

## Структура ноутбука — что нужно добавить / переделать

### Секция 0: Шапка отчёта (ЗАМЕНИТЬ текущий overview)

Должна выглядеть как credit research note:

```python
# Шапка: компания, рейтинг, дата, аналитик
# Рейтинговые бейджи: Историч. B+ | Прогноз BB- | Стресс B
# Executive Summary: 3-4 предложения с выводом аналитика
```

HTML-блок (не plotly), стиль: заголовок компании 18px, подзаголовок отрасль/тикер, рейтинги в цветных бейджах (красный/жёлтый/зелёный), резюме с border-left.

### Секция 1: Макроэкономика (НОВАЯ — добавить перед Revenue)

**1a. LME форвардная кривая** — line chart:
- Исторические LME Al цены 2015–2024 из `macro_factors` (company_id='rusal', factor_name='lme_aluminium')
- LME Alumina 2015–2024 из `macro_factors` (factor_name='lme_alumina')
- Форвард 2025–2029 из `macro_forecasts`
- Правая ось: USD/RUB
- Вертикальная линия 2024/2025

**1b. Таблица макро-допущений** (HTML-таблица, не plotly):

| Фактор | Ед. | 2022A | 2023A | 2024A | 2025F | 2026F | 2027F | 2028F | 2029F |
|--------|-----|------:|------:|------:|------:|------:|------:|------:|------:|
| LME Al | $/t | 2,976 | 2,439 | 2,520 | 2,106 | 2,242 | 2,360 | 2,449 | 2,460 |
| LME Alumina | $/t | 339 | 337 | 456 | 316 | 333 | 350 | 363 | 369 |
| USD/RUB | — | 69 | 85 | 87 | 89 | 88 | 87 | 86 | 85 |
| CBR Key Rate | % | 7.5% | 16% | 21% | 19% | 14% | 11% | 9% | 8% |
| Power price | $/MWh | 43 | 41 | 43 | 46 | 48 | 51 | 53 | 55 |
| CPI Russia | % | 11.9% | 7.4% | 8.5% | 7.0% | 5.5% | 4.5% | 4.0% | 4.0% |

Источник данных: `macro_factors` + `macro_forecasts` из БД.

### Секция 2: Отраслевой анализ (НОВАЯ)

**2a. Мировое производство** — donut chart по странам (данные хардкодом из xlsb Заключение листа, выше)

**2b. Позиция Rusal** — небольшой HTML-блок с ключевыми фактами:
- #4 производитель в мире (3.9 млн т)
- Себестоимость 1-го квартиля ($2,017/t vs мировая ~$2,200+/t)
- Доля России в мировом производстве: 6%
- Загрузка мощностей: 94.9% (2024)

**2c. Производственные KPI** — таблица 2019–2024:

```python
# Данные из production_kpi в БД:
# SELECT metric, year, value FROM production_kpi WHERE company_id='rusal'
# Метрики: production_al_kt, sales_al_kt, avg_cost_usd_t, avg_price_usd_t, ebitda_per_tonne
# + bauxite_mt, alumina_mt из тех же данных
```

Таблица с цветовой кодировкой (зелёный = хорошо, красный = плохо):
- Cost/t > 2,100 → красный
- EBITDA/t < 200 → красный, > 500 → зелёный

### Секция 3: Структура выручки (ПЕРЕДЕЛАТЬ текущую)

**3a. Waterfal revenue bridge** — stacked bar chart по годам 2019–2029:
- Сегменты: Primary Al, Alumina, Foil & Other
- История из `revenue_segments`, прогноз из model_result
- Показывать доли % в подписях

**3b. Volume × Price анализ** — 4 мини-графика (make_subplots 2×2):
- Al volume (kt) история + прогноз
- Al price ($/t) vs LME Al
- Alumina volume + price
- Revenue growth decomposition (price effect vs volume effect)

```python
# Данные из revenue_segments + production_kpi + macro_factors
# Для каждого года: rev_delta = price_delta × vol_base + vol_delta × price_new
```

**3c. Таблица сегментной выручки** (HTML, плотная):

| Сегмент | 2021A | 2022A | 2023A | 2024A | 2025F | 2027F |
|---------|------:|------:|------:|------:|------:|------:|
| Primary Al $M | 9,966 | 11,593 | 10,129 | — | — | — |
| Al volume (kt) | 3,904 | 3,896 | 4,153 | 3,859 | 3,937 | 4,056 |
| Al price ($/t) | 2,553 | 2,976 | 2,439 | — | — | — |
| Alumina $M | 610 | 550 | 340 | — | — | — |
| Foil & Other $M | 1,418 | 1,831 | 1,744 | — | — | — |
| **Total $M** | **11,994** | **13,974** | **12,213** | **12,082** | **13,875** | **15,171** |

### Секция 4: P&L (РАСШИРИТЬ)

**4a. Полная IS таблица** (HTML, не plotly) с данными 2020–2029:

| Строка IS | 2020A | 2021A | 2022A | 2023A | 2024A | 2025F | 2026F | 2027F |
|-----------|------:|------:|------:|------:|------:|------:|------:|------:|
| Выручка | 8,566 | 11,994 | 13,974 | 12,213 | 12,082 | 13,875 | 14,578 | 15,171 |
| COGS | -7,112 | -8,273 | -10,770 | -10,445 | -9,261 | — | — | — |
| Gross Profit | 1,454 | 3,721 | 3,204 | 1,768 | 2,821 | — | — | — |
| Gross margin % | 17.0% | 31.0% | 22.9% | 14.5% | 23.3% | — | — | — |
| Distribution exp. | -469 | -617 | -697 | -755 | -848 | — | — | — |
| Admin exp. | -553 | -603 | -769 | -603 | -695 | — | — | — |
| Impairment | -9 | -209 | -196 | -321 | -580 | — | — | — |
| **EBITDA adj.** | **871** | **2,893** | **2,028** | **786** | **1,490** | **1,625** | **1,750** | **1,896** |
| EBITDA margin % | 10.2% | 24.1% | 14.5% | 6.4% | 12.3% | 11.7% | 12.0% | 12.5% |
| D&A | -570 | -596 | -503 | -540 | -538 | -530 | -548 | -562 |
| EBIT | 279 | 2,079 | 1,316 | -79 | 368 | 1,095 | 1,202 | 1,334 |
| Finance income | 151 | 63 | 133 | 144 | 457 | — | — | — |
| Finance expense | -690 | -800 | -838 | -573 | -531 | -736 | -706 | -640 |
| Share of Nornickel | 976 | 1,807 | 1,555 | 752 | 564 | 926 | 926 | 926 |
| Pretax income | 716 | 3,641 | 2,166 | 244 | 858 | — | — | — |
| Tax | 43 | -416 | -373 | 38 | -55 | -203 | -193 | -196 |
| **Net Income** | **759** | **3,225** | **1,793** | **282** | **803** | **1,082** | **1,229** | **1,424** |

Цветовая кодировка: прогноз — другой фон столбцов. Отрицательные — красный, NI положительный — зелёный.

**4b. COGS waterfall chart** — как изменился COGS 2022→2024:
- Alumina: -$X (снижение цены)
- Energy: -$X
- Personnel: +$X
- FX effect: +$X / -$X

### Секция 5: Баланс (ОСТАВИТЬ, ДОПОЛНИТЬ)

Добавить **Common-size BS** (% от Total Assets):
```
PPE: 28% → 27% → 26%
Associates: 24% → 23% → 22%
...
```

### Секция 6: Cash Flow (РАСШИРИТЬ)

**6a. FFO bridge** — горизонтальный waterfall:
FFO = NI + D&A + Finance exp. + Impairment + Tax (non-cash)
→ CFO = FFO + ΔWC
→ FCF = CFO - CapEx

Данные из _REPORT / Заключение листа xlsb (и из БД):

| | 2021A | 2022A | 2023A | 2024A | 2025F |
|---|------:|------:|------:|------:|------:|
| Net Income | 3,225 | 1,793 | 282 | 803 | 1,082 |
| D&A | 596 | 503 | 540 | 538 | 530 |
| Finance exp. (add-back) | 800 | 838 | 573 | 531 | 736 |
| Other non-cash | 269+445 | 359+286 | 322+166 | 624-65 | — |
| **FFO** | **4,282** | **2,824** | **1,302** | **1,752** | **—** |
| ΔWC | -1,537 | -2,422 | +1,104 | -923 | — |
| **CFO** | **1,146** | **-412** | **1,760** | **483** | **1,210** |
| CapEx | -1,192 | -1,239 | -1,056 | -1,366 | -1,249 |
| **FCF** | **-18** | **-1,614** | **+738** | **-849** | **-39** |
| Div. from Nornickel | 620 | 1,639 | 0 | 416 | 603 |
| **FCF adj.** | **602** | **25** | **738** | **-433** | **564** |

**6b. Cash conversion cycle** — line chart 2021–2029:
- Inventory Days (прогноз: 187 → 180 дней)
- AR Days (44 → 38 дней)
- AP Days (82 → 60 дней)
- CCC = Inv + AR - AP (2024: 150 дней — аномально высоко, комментарий)

### Секция 7: Долговой анализ (РАСШИРИТЬ)

**7a. Детальная таблица долговых инструментов** (HTML, не plotly):

Разделить на группы: Secured loans / Unsecured bank loans / Bonds  
Показывать: инструмент, баланс $M, ставка, тип (fixed/float), валюта, погашения по годам 2025–2029+

Данные: из `debt_instruments` в БД (31 инструмент, $7.9B)

**7b. Maturity schedule waterfall** — stacked bar по типу инструмента:
- Secured loans (CNY, RUB)
- Unsecured bank loans
- Bonds (RUB фиксированные)
- Bonds (плавающие КС+)
- Итого линия накопленным итогом

**7c. Структура по валюте** — donut + таблица:
- CNY: ~45% ($3.6B)
- RUB: ~38% ($3.0B)
- USD: ~13% ($1.0B)
- EUR/Other: ~4% ($0.3B)

**7d. Процентная нагрузка** — расчёт по CBR прогнозу:
- Floating rate debt (~$1.5B) — ставка = спред + CBR
- При CBR 2025=19% → all-in ~21-23% на RUB floating
- При CBR 2027=11% → all-in ~13-14% на RUB floating
- Таблица: year, total_interest_expense, implied_rate, floating_portion

### Секция 8: Кредитные метрики и ковенанты (НОВАЯ — КРИТИЧНО)

**8a. Полная таблица кредитных метрик** (HTML):

| Метрика | Ковенант | 2021A | 2022A | 2023A | 2024A | 2025F | 2026F | 2027F |
|---------|----------|------:|------:|------:|------:|------:|------:|------:|
| **Долговая нагрузка** |
| ND/EBITDA | ≤ 4.5x | 2.9x | 3.3x | 3.6x | 3.6x | 3.1x | 2.7x | 2.2x |
| Total Debt/EBITDA | — | 4.7x | 10.0x | 5.3x | — | — | — | — |
| Долг / Капитал | ≤ 60% | 39% | 43% | 42% | 41% | 39% | 37% | 36% |
| **Покрытие** |
| EBIT / Int. exp. (ICR) | ≥ 2.0x | 2.8x | 1.9x | -0.2x | 0.7x | 1.5x | 1.7x | 2.1x |
| EBITDA / Int. exp. | — | 4.2x | 3.1x | 1.6x | 2.6x | 2.2x | 2.5x | 3.0x |
| EBITDA+Assoc / Int. exp. | — | 6.4x | 3.5x | 2.8x | 3.6x | 3.5x | 3.8x | 4.5x |
| CFO / Int. exp. | — | 1.4x | -0.5x | 2.1x | 0.9x | 1.6x | 1.9x | 2.3x |
| FFO / Total Debt | — | 63.6% | 29.9% | 16.5% | 22.1% | — | — | — |
| **Ликвидность** |
| Current Ratio | — | 1.8x | 2.2x | 2.1x | 1.2x | — | — | — |
| Quick Ratio | — | 1.0x | 1.2x | 1.2x | 0.6x | — | — | — |
| Cash / STD | — | 1.0x | 1.3x | 1.1x | 0.3x | 0.6x | — | — |
| Min Cash ($M) | ≥ 1,984 | ✓ | ✓ | ✓ | ⚠ 1,503 | — | — | — |
| **Рентабельность** |
| EBITDA margin | — | 24.1% | 14.5% | 6.4% | 12.3% | 11.7% | 12.0% | 12.5% |
| Gross margin | — | 31.0% | 22.9% | 14.5% | 23.3% | — | — | — |
| ROA | — | 15.4% | 7.3% | 1.3% | 3.6% | — | — | — |
| ROE | — | 30.6% | 14.6% | 2.6% | 7.2% | — | — | — |
| **Оборачиваемость** |
| Inventory Days | — | 128 | 176 | 160 | 187 | 180 | 175 | 170 |
| AR Days | — | 50 | 31 | 34 | 44 | 38 | 38 | 38 |
| AP Days | — | 102 | 106 | 60 | 82 | 60 | 60 | 60 |
| CCC | — | 75 | 101 | 134 | 150 | 158 | 153 | 148 |

Цветовая кодировка:
- ND/EBITDA: ≤3x = зелёный, 3-4x = жёлтый, >4x = красный
- ICR: ≥3x = зелёный, 2-3x = жёлтый, <2x = красный
- Ковенант нарушен → красная ячейка + ⚠

**8b. Ковенант heatmap** — визуальный светофор по годам:

```
Ковенант          | 2021 | 2022 | 2023 | 2024 | 2025F | 2026F | 2027F
ND/EBITDA ≤4.5x  |  🟢  |  🟢  |  🟢  |  🟢  |  🟢   |  🟢   |  🟢
ICR ≥2.0x         |  🟢  |  🟡  |  🔴  |  🔴  |  🔴   |  🟡   |  🟢
Cash ≥$1.98B      |  🟢  |  🟢  |  🟢  |  🔴  |  🟢   |  🟢   |  🟢
Debt/Cap ≤60%     |  🟢  |  🟢  |  🟢  |  🟢  |  🟢   |  🟢   |  🟢
```

Данные: рассчитываются из model_result + hist_is + hist_bs

**8c. Covenant headroom** — bar chart:
- Для каждого ковенанта: фактическое значение vs лимит
- Headroom = (лимит - факт) / лимит × 100%

### Секция 9: Рейтинговый анализ (ПЕРЕДЕЛАТЬ)

**9a. Рейтинговая шкала с позицией** — горизонтальная полоска:
```
D | CCC | B- | B | B+ | BB- | BB | BB+ | BBB- | BBB | A | AA | AAA
                    ↑ 2024A        ↑ 2027F
```

**9b. Факторный анализ** — radar chart (6 факторов):
- Scale/Diversification (Business Position): 61/100 (сила)
- Profitability: 52/100
- Leverage: 38/100 (слабость)
- Coverage: 45/100 (слабость)
- Liquidity: 44/100
- Associates (Nornickel): 68/100 (сила)

**9c. Рейтинг-матрица Base / Stress** — таблица:

| | 2025F | 2026F | 2027F | 2028F | 2029F |
|---|:-----:|:-----:|:-----:|:-----:|:-----:|
| Base | BB− | BB− | BB | BB | BB+ |
| Al −25% | B | B | B+ | B+ | BB− |
| USD/RUB +30% | B+ | BB− | BB− | BB− | BB |
| Rate +300bp | B+ | BB− | BB− | BB | BB |
| Combined | CCC+ | B− | B | B+ | BB− |

### Секция 10: Стресс-тестирование (РАСШИРИТЬ)

**10a. Чувствительность EBITDA** — heatmap/table:

| Шок | NI base | ΔNI | ΔND/EBITDA | Ков.breach? |
|-----|--------:|----:|-----------:|:-----------:|
| Base | $1,082M | — | 3.1x | Нет |
| LME Al −10% | $813M | −$269M | +0.3x | Нет |
| LME Al −25% | $544M | −$538M | 5.2x | **ND/EBITDA ⚠** |
| LME Alumina +20% | $749M | −$333M | +0.4x | Нет |
| USD/RUB +30% | $932M | −$150M | 3.4x | Нет |
| CBR +300bp | $832M | −$250M | 3.3x | Нет |
| Combined shock | $162M | −$920M | 6.8x | **ND/EBITDA + ICR ⚠** |

**10b. Tornado chart** (горизонтальный bar, 2 цвета):
- Факторы отсортированы по |влиянию на NI|
- Левая сторона = downside шок, правая = upside

**10c. Scenario comparison** — line charts (Revenue, EBITDA, ND/EBITDA, Rating) по сценариям

### Секция 11: Коэффициентный анализ (ПОЛНАЯ ТАБЛИЦА — НОВАЯ)

Аналог листа `_REPORT` из xlsb — полная таблица за все годы.

Структура HTML-таблицы (не plotly):

```html
<table>
  <thead>История / Прогноз</thead>
  <tr class="section-header">РЕНТАБЕЛЬНОСТЬ</tr>
  <tr>EBITDA margin % ...</tr>
  <tr>EBIT margin % ...</tr>
  <tr>Net margin % ...</tr>
  <tr>Gross margin % ...</tr>
  <tr>ROA % ...</tr>
  <tr>ROE % ...</tr>
  <tr class="section-header">ДОЛГОВАЯ НАГРУЗКА</tr>
  <tr>ND/EBITDA x ...</tr>
  <tr>Total Debt/EBITDA x ...</tr>
  <tr>Debt/Equity x ...</tr>
  <tr>Debt/Total Capital % ...</tr>
  <tr class="section-header">ПОКРЫТИЕ</tr>
  <tr>EBITDA/Interest x ...</tr>
  <tr>EBIT/Interest (ICR) x ...</tr>
  <tr>EBITDA+Associates/Interest x ...</tr>
  <tr>CFO/Interest x ...</tr>
  <tr>FFO/Total Debt % ...</tr>
  <tr>FCF/Total Debt % ...</tr>
  <tr class="section-header">ЛИКВИДНОСТЬ</tr>
  <tr>Current Ratio x ...</tr>
  <tr>Quick Ratio x ...</tr>
  <tr>Cash/STD x ...</tr>
  <tr class="section-header">ОБОРАЧИВАЕМОСТЬ (дни)</tr>
  <tr>Inventory Days ...</tr>
  <tr>AR Days ...</tr>
  <tr>AP Days ...</tr>
  <tr>Operating Cycle ...</tr>
  <tr>Cash Conversion Cycle ...</tr>
  <tr class="section-header">CASH FLOW</tr>
  <tr>CFO $M ...</tr>
  <tr>FFO $M ...</tr>
  <tr>CapEx $M ...</tr>
  <tr>FCF $M ...</tr>
  <tr>FCF + Div.Nornickel $M ...</tr>
  <tr>CapEx/Revenue % ...</tr>
  <tr>CapEx/D&A x ...</tr>
  <tr class="section-header">ПРОИЗВОДСТВЕННЫЕ KPI</tr>
  <tr>Al production (kt) ...</tr>
  <tr>Al sales (kt) ...</tr>
  <tr>Cost per tonne ($/t) ...</tr>
  <tr>Avg price ($/t) ...</tr>
  <tr>EBITDA per tonne ($/t) ...</tr>
  <tr>Capacity utilization % ...</tr>
</table>
```

Цветовая кодировка ячеек:
- Прогнозные годы: светло-синий фон
- Ковенантные метрики в нарушении: красный фон
- Улучшение год/год: стрелка вверх ▲ зелёная
- Ухудшение год/год: стрелка вниз ▼ красная

---

## Технические требования

### Источники данных (приоритет)

```python
# 1. История IS/BS/CF — из БД
with Repository(DB_PATH) as repo:
    for yr in range(2019, 2025):
        is_d = repo.get_history_year(COMPANY_ID, 'IS', yr)
        bs_d = repo.get_history_year(COMPANY_ID, 'BS', yr)
        cf_d = repo.get_history_year(COMPANY_ID, 'CF', yr)

# 2. Production KPI — из production_kpi таблицы
    kpi = repo.query("""
        SELECT pk.metric, p.year, pk.value
        FROM production_kpi pk JOIN periods p ON pk.period_id=p.period_id
        WHERE pk.company_id='rusal' ORDER BY pk.metric, p.year
    """)

# 3. Сегменты — из revenue_segments таблицы
    segs = repo.query("""
        SELECT year, segment_name, revenue
        FROM revenue_segments WHERE company_id='rusal' ORDER BY year
    """)

# 4. Macro — из macro_factors + macro_forecasts
    macro_h = repo.query("SELECT factor_name, year, value FROM macro_factors WHERE year<=2024")
    macro_f = repo.query("SELECT factor_name, year, value FROM macro_forecasts WHERE company_id='rusal'")

# 5. Прогноз — из build_model()
result = build_model(COMPANY_ID, run_preprocessor=False, run_model=True,
    run_stress=True, run_rating=True, stress_scenarios=STRESS_SCENARIOS)
forecast = result.model_result.years
stress_results = result.stress_results

# 6. Debt instruments — из debt_instruments таблицы
    di = repo.query("SELECT * FROM debt_instruments WHERE company_id='rusal'")
```

### Вычисление коэффициентов

```python
def calc_ratios(yr, hist_is, hist_bs, hist_cf, forecast):
    """Считает все кредитные метрики для года."""
    if yr <= 2024:
        is_d = hist_is[yr]; bs_d = hist_bs[yr]; cf_d = hist_cf.get(yr, {})
        rev    = is_d.get('revenue', 0)
        ebitda = is_d.get('ebitda', 0) or (is_d.get('ebit',0) + abs(is_d.get('total_da',0)))
        ebit   = is_d.get('ebit', 0)
        ni     = is_d.get('net_income', 0)
        int_e  = abs(is_d.get('interest_expense', 0))
        cogs   = abs(is_d.get('cogs', 0))
        da     = abs(is_d.get('total_da', 0))
        assoc  = is_d.get('earnings_from_investees', 0) or 0
        cash   = bs_d.get('cash', 0)
        ar     = bs_d.get('accounts_receivable', 0)
        inv    = bs_d.get('inventory', 0)
        ap     = abs(bs_d.get('accounts_payable', 0))
        ta     = bs_d.get('total_assets', 0)
        te     = bs_d.get('total_equity', 0)
        ltd    = abs(bs_d.get('long_term_debt', 0))
        std    = abs(bs_d.get('short_term_debt', 0))
        td     = ltd + std; nd = td - cash
        cfo    = cf_d.get('cfo_total', 0)
        capex  = abs(cf_d.get('capex', 0))
        # FFO = NI + DA + interest_paid + impairment + current_tax (non-cash add-back)
        ffo = ni + da + abs(is_d.get('interest_expense',0)) + abs(is_d.get('asset_impairment',0) or 0)
        fcf = (cfo or 0) - capex
    else:
        s = forecast[yr]
        # ... из атрибутов YearState

    return {
        'nd_ebitda':  nd/ebitda if ebitda else None,
        'icr_ebit':   ebit/int_e if int_e else None,
        'icr_ebitda': ebitda/int_e if int_e else None,
        'icr_assoc':  (ebitda+assoc)/int_e if int_e else None,
        'cfo_int':    cfo/int_e if int_e else None,
        'ffo_debt':   ffo/td if td else None,
        'fcf_debt':   fcf/td if td else None,
        'current':    (bs_d.get('total_ca',0)) / (abs(bs_d.get('total_cl',0)) or 1),
        'quick':      (cash+ar) / (abs(bs_d.get('total_cl',0)) or 1),
        'cash_std':   cash/std if std else None,
        'inv_days':   inv/(cogs/365) if cogs else None,
        'ar_days':    ar/(rev/365) if rev else None,
        'ap_days':    ap/(cogs/365) if cogs else None,
        'ebitda_m':   ebitda/rev if rev else None,
        'ni_m':       ni/rev if rev else None,
        'roa':        ni/ta if ta else None,
        'roe':        ni/te if te else None,
        'capex_rev':  capex/rev if rev else None,
        'capex_da':   capex/da if da else None,
    }
```

### Ковенанты

```python
COVENANTS = {
    'nd_ebitda': {'limit': 4.5, 'direction': 'max', 'label': 'ND/EBITDA ≤ 4.5x'},
    'icr_ebit':  {'limit': 2.0, 'direction': 'min', 'label': 'ICR ≥ 2.0x'},
    'debt_cap':  {'limit': 0.60,'direction': 'max', 'label': 'Долг/Капитал ≤ 60%'},
    'min_cash':  {'limit': 1984,'direction': 'min', 'label': 'Min Cash ≥ $1,984M'},
}

def check_covenant(metric_value, covenant):
    if metric_value is None: return 'na'
    if covenant['direction'] == 'max':
        if metric_value <= covenant['limit'] * 0.8: return 'ok'      # зелёный
        if metric_value <= covenant['limit']:        return 'warn'    # жёлтый
        return 'breach'                                               # красный
    else:  # min
        if metric_value >= covenant['limit'] * 1.2: return 'ok'
        if metric_value >= covenant['limit']:        return 'warn'
        return 'breach'

def covenant_color(status):
    return {'ok': '#eaf3de', 'warn': '#faeeda', 'breach': '#fcebeb', 'na': '#f5f5f5'}[status]
```

### HTML-таблицы (стиль)

```python
def html_ratio_table(data_dict, years, ratios_config):
    """
    data_dict: {yr: {metric: value}}
    years: список лет
    ratios_config: [{'key':'nd_ebitda','label':'ND/EBITDA','fmt':'{:.2f}x','covenant':4.5,'dir':'max'}, ...]
    """
    # Шапка: история серого цвета, прогноз синего
    # Строки секций: тёмный фон, uppercase
    # Ковенантные нарушения: красный фон + ⚠
    # YoY изменение: ▲ зелёный / ▼ красный
```

### Экспорт в HTML

```python
if EXPORT_HTML:
    # Сохранить все figures как plotly HTML
    # Сохранить HTML-таблицы
    # Объединить в один standalone HTML файл
    html_path = Path(f'companies/{COMPANY_ID}/outputs/{COMPANY_ID}_dashboard.html')
    # plotly.io.write_html или pio.to_html(fig, include_plotlyjs='cdn')
```

---

## Порядок выполнения для Claude Code

1. **Проверь что ноутбук работает:**
   ```bash
   cd "/Users/arturhusnutdinov/Documents/IT Development/Docker/stressTest_v2"
   python3 -c "from engine.orchestrator import build_model; r=build_model('rusal',run_preprocessor=False,run_model=True); print('OK BS=',max(r.model_result.bs_diffs.values()))"
   ```

2. **Читай текущий ноутбук:**
   ```python
   import json; nb=json.loads(open('companies/rusal/notebooks/06_Financial_Dashboard.ipynb').read())
   print(f"{len(nb['cells'])} ячеек")
   ```

3. **Добавляй секции поверх существующих** (не удаляй рабочие секции):
   - Вставляй новые ячейки `cells.insert(idx, cell(src))`
   - Или перезаписывай существующие если они покрывают ту же секцию

4. **Тест каждой секции отдельно** перед добавлением в ноутбук:
   ```bash
   jupyter nbconvert --to notebook --execute --ExecutePreprocessor.timeout=180 \
     companies/rusal/notebooks/06_Financial_Dashboard.ipynb \
     --output companies/rusal/outputs/06_dashboard_executed.ipynb
   ```

5. **Финальный HTML экспорт:**
   ```bash
   ls -la companies/rusal/outputs/
   ```

---

## Чего не нужно делать

- Не менять код движка (`engine/`)
- Не запускать препроцессор (`run_preprocessor=False` в build_model)
- Не хардкодить данные если они есть в БД — брать из БД
- Не использовать `localStorage` в HTML
- Не создавать новые таблицы в БД — только читать существующие

---

*Документ создан по анализу: `3-Statement_Model__Template__Rusal_1.xlsb` (23 листа) + текущего состояния `06_Financial_Dashboard.ipynb` (14 ячеек). Версия: апрель 2026.*
