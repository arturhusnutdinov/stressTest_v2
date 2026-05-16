# Спецификация модели — RUSAL

**Дата генерации:** 2025-11-03

## Обзор модели

**Тип модели:** STANDARD

**Периоды:**
- История: 2010 - 2024
- Прогноз: 2025 - 2029

---

## 1. Методы моделирования статей

### Revenue

- **Метод:** Regression on macro factors
- **Fallback:** EWA growth rates

### COGS

- **Метод:** Ratio to Revenue (calculated from history)
- **Fallback:** 80% of Revenue

### SG&A

- **Метод:** EWA with half-life
- **Fallback:** 5% of Revenue

### Depreciation

- **Метод:** Ratio to Revenue or PP&E
- **Fallback:** 4% of Revenue

### CapEx

- **Метод:** Ratio to Revenue (calculated from history)
- **Fallback:** 8% of Revenue

### Working Capital

- **Метод:** Days method (DSO, DIO, DPO)
- **Fallback:** Constant days

### Debt

- **Метод:** From debt_schedule.csv or BS history
- **Fallback:** No debt

### Taxes

- **Метод:** Statutory rate with floor
- **Fallback:** 20% of EBT

---

## 2. Расчетные параметры из истории

| Параметр | Mean | Median | Last | Min | Max | Years |
|----------|------|--------|------|-----|-----|-------|
| cogs_margin | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 5 |
| sga_margin | 0.1130 | 0.1112 | 0.1277 | 0.1017 | 0.1277 | 5 |
| dep_margin | 0.0470 | 0.0427 | 0.0424 | 0.0351 | 0.0658 | 5 |
| net_income_margin | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 5 |
| ebitda_margin | 0.8870 | 0.8888 | 0.8723 | 0.8723 | 0.8983 | 5 |
---

## 3. Допущения моделирования

### Параметры берутся равными последнему значению

- **WC_days (DSO, DIO, DPO)**: EWA (Exponentially Weighted Average) (fallback: last_value)
- **SG&A**: EWA with CPI growth (fallback: last_value)
- **Margins (EBITDA, EBIT)**: EWA or constant if stable (fallback: last_value)

### Параметры равны нулю

- **Other Operating Income (if not specified)**: 0 (Assumed zero if not in history)
- **R&D (if not specified)**: 0 (Assumed zero if not in history)
- **Amortization (if not specified)**: 0 (Assumed zero if only Depreciation)
---

## 4. Трансформации данных

### Revenue (target)

- **Трансформация:** dln
- **Anchor:** history_last
- **Статус:** OK

### Revenue (features)

- **Трансформация:** dln
- **Anchor:** nan
- **Статус:** OK

### SG&A

- **Трансформация:** dln
- **Anchor:** history_last
- **Статус:** OK

### CPI (for SG&A)

- **Трансформация:** dln
- **Anchor:** nan
- **Статус:** OK

### Revenue (chainlink check)

- **Трансформация:** dln -> levels
- **Anchor:** nan
- **Статус:** WARN

---

## 5. Параметры из истории по годам

### cogs_margin

| Год | Значение |
|-----|----------|
| 2020 | 0.0000 |
| 2021 | 0.0000 |
| 2022 | 0.0000 |
| 2023 | 0.0000 |
| 2024 | 0.0000 |

### sga_margin

| Год | Значение |
|-----|----------|
| 2020 | 0.1193 |
| 2021 | 0.1017 |
| 2022 | 0.1049 |
| 2023 | 0.1112 |
| 2024 | 0.1277 |

### dep_margin

| Год | Значение |
|-----|----------|
| 2020 | 0.0658 |
| 2021 | 0.0491 |
| 2022 | 0.0351 |
| 2023 | 0.0427 |
| 2024 | 0.0424 |

### net_income_margin

| Год | Значение |
|-----|----------|
| 2020 | 0.0000 |
| 2021 | 0.0000 |
| 2022 | 0.0000 |
| 2023 | 0.0000 |
| 2024 | 0.0000 |

### ebitda_margin

| Год | Значение |
|-----|----------|
| 2020 | 0.8807 |
| 2021 | 0.8983 |
| 2022 | 0.8951 |
| 2023 | 0.8888 |
| 2024 | 0.8723 |

