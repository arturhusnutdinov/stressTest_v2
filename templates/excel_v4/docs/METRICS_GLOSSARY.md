# Словарь определений метрик (excel_v4 + engine)

**Назначение** (AUDIT_ADEQUACY §3.5): единый словарь определений для backtest,
sync-гейта и сверки Excel ↔ Python ↔ БД. Ключевая ловушка — EBITDA: у книги,
engine и БД разные ряды.

## EBITDA — три определения

| Определение | Значение 2025 (rusal) | Формула | Где используется |
|---|---|---|---|
| **EBITDA (книга, 21_PL!F12)** | 1 053 | `Выручка − COGS − SGA ± прочие опер.` = `gross_profit + sga + other` + доля в ассоциатах (факт = МСФО EBITDA reported) | 21_PL r12, 30_Ratios (ND/EBITDA, ICR), 31_Score, ковенанты, 17_Debt r56 |
| **EBITDA (БД, history_is.ebitda)** | 597 | `ebit + total_da` — узкое, post-associates | не использовать для сверки с книгой |
| **EBITDA (БД, history_is.ebitda_reported)** | 1 053 | МСФО reported | **эталон для backtest/гейта vs книга** |

Правило: любая сверка книги с БД по EBITDA обязана использовать
`ebitda_reported`. Ключ `ebitda` — исторический ряд препроцессора.

## Основные метрики

| Метрика | Книга (лист!строка) | Engine (YearState) | БД-ключ(и) | Примечание |
|---|---|---|---|---|
| Revenue | 21_PL!r7 = '10_Revenue'!F$20 | `state.revenue` | `revenue` (history_is) | сегментная модель Vol×Price |
| Gross profit | 21_PL!r9 = F7+F8 | `revenue + cogs` | `gross_profit` | COGS отрицателен в БД |
| EBITDA (книга) | 21_PL!r12 = F9+F10+F11 | `state.ebitda` | **`ebitda_reported`** | см. таблицу выше |
| D&A | 21_PL!r13 | `state.total_da` | `total_da` | PPE dep + ΔROU |
| EBIT | 21_PL!r15 = F12−F13−F14 | `state.ebit` | `ebit` | |
| Процентные расходы | 21_PL!r16 = −'17_Debt'!F$48 | `state.interest_expense` | `interest_expense` | знак: книга −, БД модуль |
| Чистая прибыль | 21_PL!r22 = F20+F21 | `state.net_income` | `net_income` | налог ABS() |
| Итого долг | 17_Debt!r42 = term_close+RC_close+FX | `state.total_debt` (STD+LTD) | `short_term_debt` + `long_term_debt` | ND = долг − cash |
| ND/EBITDA | 30_Ratios!r7 | `_nd_ebitda` | — (расчётное) | ковенант 4.5x |
| ICR | 30_Ratios!r8 = EBITDA/проценты | `_icr` | — (расчётное) | ковенант ≥1.5–2.0 |
| CapEx | 23_CF!r15 ← '15_PPE'!F8 | `state.cfi_capex` | `capex` (history_cf) | MAX(поддерж., рост.) |

## Единицы

- Excel-книга: **млн USD** (mln).
- БД `data_mart_v2.db`: **доллары США** (история из ExcelLoader ×1e6; engine
  хранит raw $ — при сравнении делить БД на 1e6). Backtest-скрипт учитывает.

## Проверка полноты фактов (2024)

Замечание AUDIT_ADEQUACY §3.5 «2024-й факт в БД не найден по ключу 'revenue'»
**не воспроизводится** (проверено 18.11): `revenue` 2024 присутствует для
rusal и us_steel во всех трёх таблицах (history_is/bs/cf: 30/47/46 и
43/70/82 строк). Замечание снимается.

## Ссылки

- Методология: `docs/Model_Methodology.md`, `docs/MODEL_DESCRIPTION_RUSAL.md`
- Sync-гейт: `scripts/sync_gate_corp.py` — сверка Excel ↔ engine
- Backtest: `scripts/backtest.py` (engine) + `--backtest` флаги сборки/заполнения
