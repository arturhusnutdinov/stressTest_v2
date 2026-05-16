# RUSAL — Следующая сессия Claude Code
**Дата:** 2026-04-04 | **Статус:** PRODUCTION READY (BS=0, CF=0, Stress 5/5)

---

## ОБЯЗАТЕЛЬНАЯ ПРОВЕРКА ПРИ СТАРТЕ

```python
import sys; sys.path.insert(0, '.')
from engine import ROOT, DB_PATH
assert str(ROOT).endswith('stressTest_v2'), f'ROOT={ROOT}'

from engine.orchestrator import build_model
for co in ['us_steel', 'rusal']:
    r = build_model(co, run_preprocessor=(co=='rusal'), run_model=True, run_stress=True)
    mr = r.model_result
    bs = max(mr.bs_diffs.values())
    n_s = sum(1 for sr in (r.stress_results or {}).values() if sr and sr.success)
    print(f'{co}: BS={bs:.6f} stress={n_s}/{len(r.stress_results or {})}')
assert bs < 1e6, f'Rusal BROKEN! BS={bs}'
print('OK')
```

---

## ТЕКУЩЕЕ СОСТОЯНИЕ

### US Steel — PRODUCTION READY
```
BS=0.000004  CF=0.000000  Stress 1/1
2025: Rev=$14.3B  EBITDA=14.7%  NI=$1,229M  ND/EB=1.1x  Rating=BBB
2029: Rev=$11.2B  EBITDA=14.3%  NI=$657M    ND/EB=-0.6x Rating=A-
```

### Rusal — PRODUCTION READY
```
BS=0.000004  CF=0.000000  Stress 5/5
Base year: 2025 (факт), Forecast: 2026-2030
2026: Rev=$15.6B  EBITDA=11.5%  NI=$945M   ND/EB=3.6x  Rating=B
2030: Rev=$16.8B  EBITDA=11.5%  NI=$984M   ND/EB=3.1x  Rating=B
Стресс: aluminium_downturn NI=-57%, energy_spike NI=-62%, covenant_breach NI=-76%
```

---

## ЧТО БЫЛО СДЕЛАНО В ЭТОЙ СЕССИИ

### Данные (Фаза 1)
| Что | Результат |
|-----|-----------|
| IS/BS/CF 2011-2025 | 1907 строк через ExcelLoader |
| Production KPI | 12 метрик, 14 лет |
| Macro | 22 фактора + прогноз 2026-2030 |
| Segments | 4 финансовых + 8 операционных |
| Debt instruments | 31 шт $9.6B, numeric rates в Excel |
| BS gaps closed | NCI, other_ca, other_cl, other_ncl — all from totals |
| investments_lt | Исправлен двойной счёт (PDF parsing error) |

### Движок (Фаза 2 — универсальные фиксы)
| Фикс | Файлы |
|------|-------|
| is_income_sign: natural/credit_negative | inputs.py, loader.py, project.yaml |
| investments_lt fallback names | loader.py (other_nca, other_ncl, other_cl) |
| Floating rate = spread + CBR key rate | debt.py, core.py, inputs.py |
| Refi fees через IS, не CFF | core.py, debt.py (closes BS identity) |
| opex_ratio = SGA + Distribution | preprocessor/core.py, core.py, loader.py |
| ExcelLoader: normalized IDs | excel.py (_load_debt_instruments) |
| ExcelLoader: Production_KPI handler | excel.py (_load_production_kpi) |
| ExcelLoader: unit-aware segments | excel.py (_load_segments) |
| Stress scenarios from YAML | orchestrator.py (reads company stress_scenarios.yaml) |

### Конфигурация (Фаза 3)
| Файл | Статус |
|------|--------|
| project.yaml | history 2011-2025, forecast 2026-2030, CBR forecast, covenants |
| excel_loader.yaml | Переписан под реальный формат Rusal Excel |
| stress_scenarios.yaml | 5 сценариев (aluminium, FX, energy, rate, covenant) |
| accounting_conventions.yaml | cash_only, is_income_sign=natural |
| 10 ноутбуков | Все us_steel→rusal, stale outputs cleared |
| Legacy CSV | Архивированы в history/_archive/ |

---

## АРХИТЕКТУРНЫЕ ПРИНЦИПЫ

```
YAML = ТОЛЬКО policy (target leverage, NOL, covenants, dividends)
Preprocessor → БД → Loader → ModelConfig (все числовые параметры)
Excel = единственный источник данных → ExcelLoader → DB

ЗАПРЕЩЕНО в YAML: cogs_pct, dep_rate, dso_days, avg_rate_pct, tax_rate
РАЗРЕШЕНО в YAML:
  target_net_debt_ebitda, max_voluntary_prepay_pct_fcf
  dividend_pct_ni, buyback_pct_fcf
  nol_opening_balance, is_income_sign
  cbr_key_rate_forecast
  covenants thresholds

Sign convention:
  is_income_sign: credit_negative (US GAAP / US Steel) — income stored as negative
  is_income_sign: natural (IFRS / Rusal) — income stored as positive

Reload идемпотентен:
  ExcelLoader normalizes instrument_id → lowercase + underscores
  upsert_debt_instrument uses ON CONFLICT → no duplicates
  Rates stored as numeric in Excel → preserved on reload
```

---

## ДАННЫЕ RUSAL В БД

```
data_mart_v2.db:
  history_is:        2011-2025  (278 строк, 19 метрик/год)
  history_bs:        2011-2025  (436 строк, 37 метрик/год)
  history_cf:        2011-2025  (543 строк, 79 метрик/год)
  preprocess_metrics: 910 метрик (14 групп + production_kpi)
  debt_instruments:  31 инструмент $9.60B (rates: 2-15%, floating+CBR)
  macro_factors:     22 фактора × 15 лет
  macro_forecasts:   8 факторов × 2026-2030
  segment_data:      168 строк (fin + operational)

Excel:
  companies/rusal/data/rusal_unified_complete.xlsx (32 листа)
```

---

## TODO СЛЕДУЮЩЕЙ СЕССИИ (Фаза 4)

### P1 — CogsBlock (компонентная себестоимость)
```
alumina_cost = volume_kt × alumina_price_usd_t (LME linked)
energy_cost  = volume_kt × power_cost (RUB tariff / USD/RUB)
labour_cost  = volume_kt × labour_cost (CPI RU indexed)
→ EBITDA margin станет динамическим (сейчас flat 11.5%)
```

### P2 — RevenueBlock (сегментная модель)
```
Al:      volume_kt × lme_aluminium × (1 + vap_premium)
Alumina: sales_kt × lme_alumina
→ Revenue по сегментам вместо единого OLS
```

### P3 — Backtesting
```
Прогноз 2023→2024: Revenue ±10%, EBITDA ±15%
Train on 2011-2022, test on 2023-2024
```

### P4 — Rating calibration
```
metals/mining (не steel)
industry_adjustment = -6
TTC margin = 12%
```

### P5 — Stress calibration
```
usd_rub_shock: добавить FX-linking в модель (revenue в USD, COGS частично в RUB)
energy_spike: power price → COGS (через CogsBlock)
```

---

*Документ обновлён автоматически 2026-04-04.*
