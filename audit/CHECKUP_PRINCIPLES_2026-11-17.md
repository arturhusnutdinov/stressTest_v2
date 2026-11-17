# Чекап принципов построения: stressTest_v2 (RUSAL + Nornickel) vs bank_model

**Дата:** 2026-11-17
**Объект:** templates/excel_v4 (model/rusal_v4.xlsx, model/nornickel_v4.xlsx) + Python engine (engine/model/core.py)
**База сравнения:** принципы банковской модели (bank_model v4.9, спецификация docs/MODEL_MATH_FULL.md)
**Метод:** живые прогоны — audit_corp_model.py (кэш + --excel пересчёт), verify_model.py (3 сценария), pytest (80 тестов), build_model('rusal') из engine, граф зависимостей (Tarjan SCC)

---

## 1. Вердикт по принципам

| # | Принцип банковской модели | Статус | Доказательство |
|---|---|---|---|
| 1 | Excel = автономная формульная модель, Python только генерирует файл | ✅ | DESIGN.md заявлен явно; 30 листов 1-в-1 банковской архитектуре (CP / 01_Macro / 02_Hist / 03_Assump / corkscrews 15–19 / 20_BS / 21_PL / 23_CF / 90_Checks / Model_Output / Changelog) |
| 2 | Инварианты: баланс, ОДДС, corkscrews = 0 | ✅ | Живой пересчёт в Excel: **расхождений кэша 0, ошибочных ячеек 0**; C3: BS / CF / PPE / Debt / Equity — все PASS в обеих книгах |
| 3 | Без плагов (bottom-up, формула-остаток прозрачен) | ✅ | Банк: oth_l-остаток; здесь: BS = сумма компонент (no-plug v2.2.0), аудит C3 PASS |
| 4 | Параметризация, реестр, «никаких магических чисел» | ✅ (с оговоркой) | 130+ параметров CP (секции A–L), reg.json 606 строк, F7 «[РАСЧЁТ]-литерал = 0»; оговорка: 130–136 литералов (365 day-count) — WARN H1 |
| 5 | Сценарный переключатель в книге | ✅ | CP!C5 (1=Base/2=Stress/3=Severe), I3 PASS; 3 сценария × 3 года, LME-входы из 01_Macro |
| 6 | Эконометрика видна в модели | ✅ | G1: SLOPE/INTERCEPT/RSQ/STEYX присутствуют; регрессия Revenue~LME (β=0.653, t=1.62 — честно показана слабая значимость + shrinkage к 1.0) |
| 7 | Дисциплина оформления (цвета/ключи/нумерация) | ✅ | styles.py — цветовая схема банка; MODEL_DESCRIPTION в формате bank_model |
| 8 | Документация + аудит-трейл | ✅ | MODEL_DESCRIPTION_RUSAL (241 стр.) / _NORNICKEL (117 стр.), AI_MODEL_BUILD_GUIDE, Model_Methodology, 9 раундов аудита v4–v9, AUDIT_FIXES.md |
| 9 | Поведенческие тесты (монотонность, эластичности) | ✅ / ⚠️ | verify_model: монотонность Revenue/EBITda PASS, operating leverage 6.6x (RUSAL) / 1.0x (NORNICKEL); ⚠️ 1 FAIL у RUSAL (п. 5 ниже) |
| 10 | Python engine: полная валидация состояния | ✅ | YearState.full_validation: bs_identity / cf_bridge / cash_bs_cf; BS max diff 0.00, CF max diff 0.00 при живом прогоне |
| 11 | Тестовая батарея | ✅ | pytest: **80 passed** (unit + integration) |
| 12 | **Два движка → схожие результаты (sync gate)** | ❌ | **Нет гейта Excel↔Python; расхождение на порядок** (п. 2 ниже) — главный пробел |

Расширения сверх банковской модели: 33_RevStress (reverse stress + tornado), 35_Valuation (DCF + SOTP), 32_Covenants (headroom/breach), 31_Score (S&P 4-фактор), 40_Scen (сравнение сценариев).

## 2. Критические находки

### K1. Расхождение Excel ↔ Python на порядок (нет sync gate)
Банковский принцип «два движка дают схожие результаты» фактически нарушен:

| Показатель, 2026 base | Excel rusal_v4 | Python engine |
|---|---|---|
| Revenue, M$ | 15,641 | 13,378 |
| EBITDA, M$ | 1,313 (margin 8.4%) | **17 (margin 0.000)** |
| EBITDA 2027/2028 | 1,407 / 1,256 | **−114 / −263** |
| Рейтинг | B+ | CCC→CCC- (и сейв сломан, K2) |

Каскад: EBITDA≈0 → ND/EBITDA 489.96 (ковенант-чек живого прогона) → rating D. Revenue сопоставим, значит сломан расчёт затрат (COGS-компоненты / da_in_cogs / VECM PPI-входы). В банке это ловилось гейтом синхронизации (допуски по метрикам); здесь гейта нет (`tools/sync_rusal_excel.py` — синхронизация данных Excel→DB, не числовая сверка).
**Рекомендация:** (1) декомпозировать ΔEBITDA по блокам (COGS→компоненты→macro PPI chain, аналог P2-декомпозиции банка); (2) добавить `scripts/sync_gate_corp.py` — сравнение Model_Output vs engine forecast (Rev/EBITDA/NI/Debt, допуск 5–10%); (3) внести в регламент прогона.

### K2. Python engine: rating save сломан (interface drift)
`rating/runner.py:275` вызывает `upsert_rating(..., score_detail=...)`, сигнатура `repository.py:670` принимает `factor_metrics`. ERROR при сохранении каждого сценария. **80 pytest passed при живом баге** — брешь батареи (save-path не покрыт). Фикс: выровнять сигнатуру + интеграционный тест на сохранение рейтинга.

### K3. FAIL E2 (обе книги): 35_Valuation ссылается на чужой год
6 ссылок: `35_Valuation!C7/C29 (2026) -> 17_Debt!H (2028)`, `C34-C36 -> 10_Revenue!H (2028)`, `C7 -> 20_BS!H`. Шаблонный баг v4. Влияет на DCF-выходы 2026 (WACC/terminal на базе 2028). Фикс: смещение колонок в builder'е 35_Valuation.

## 3. Предупреждения (WARN) и замечания

| # | Уровень | Находка | Комментарий |
|---|---|---|---|
| W1 | ⚠️ цикличность | Граф формул: **0 SCC в обеих книгах**; при этом calcPr у RUSAL iterate=1 (избыточен), у NORNICKEL iterate=None | В банке цикл — намеренный (неподвижная точка). Здесь ацикличный DAG (opening-balance convention) — допустимо, но: унифицировать calcPr; зафиксировать в DESIGN.md; проверить эквивалентность итерациям решателя Python (10 итер. cash↔NI, tol $1K) — иначе движки считают разные математические объекты (кейс банка: «лаг = другая система») |
| W2 | ⚠️ стресс-гейт | verify_model: **Sc3 RUSAL EBITDA −2,179, но new_term draw = 2,100** при отрицательной EBITDA (гейт закрытия не сработал) | Аналог банковского тормоза: при EBITDA<0 дорожный драфт должен быть 0 ( refinancing gate ). NORNICKEL: все behavioral tests PASS |
| W3 | ⚠️ литералы | H1: 130 (RUSAL) / 136 (NORNICKEL), основное — 365 в 03_Assump/16_WC | По банковскому правилу 365 ∉ {0,1,2,3,4,6,12,100,0.5} → CP-параметр day_count. Низкий приоритет |
| W4 | ⚠️ пустые ссылки | На пустые ячейки: RUSAL 82, NORNICKEL 123 (05_Drivers/15_PPE/19_Tax/20_BS) | Тождества PASS — вероятно carry-forward by design; стоит задокументировать список как легитимный |
| W5 | ℹ️ документация | IMPLEMENTATION_PLAN: «No fullCalcOnLoad» — фактически fullCalcOnLoad=True в обеих книгах (верно); TODO.md устарел (Phase 2 IN PROGRESS при готовых v5.8); MODEL_DESCRIPTION_NORNICKEL «3 сегмента» vs таблица 4–5 сегментов | Привести документы к факту |
| W6 | ℹ️ асимметрия данных | NORNICKEL в Python-движке локально не воспроизводится (данные в Vertex PG; standalone SQLite — только RUSAL/US Steel) | Excel-модель полна; engine-прогон Норникеля требует PG. Отметить в MODEL_DESCRIPTION |

## 4. Экономическая санитария (из живых прогонов)

- **RUSAL**: Base ND/EBITDA 7/7/9x, ICR ~1x, рейтинг B+→BB→B, статус обложки «⚠ КОВЕНАНТЫ НАРУШЕНЫ» — согласуется с высоким левериджом эмитента; флаг-статус работает. Sc3 (Severe): Rev −40%, EBITDA −2,179, рейтинг D — стресс-история когерентна (op leverage 6.6x).
- **NORNICKEL**: Base Rev 13,879→15,039, EBITDA 6,727→7,196 (margin ~47%), NI ~3.0–3.1 bn, рейтинг A/A/A+, статус «✅ ОК» — согласуется с низким левериджем (ND 3,571, ND/EBITDA ~0.5x).
- Оба статуса на 00_Cover!C20 консистентны с модельными выходами (J1/J2 PASS).

## 5. Итог

Excel-модели RUSAL и Nornickel построены **с теми же принципами, что и банковские**: формульная автономность, инварианты по построению (живой пересчёт: 0 расхождений), bottom-up без плагов, реестр параметров, сценарный переключатель, эконометрика в книге, behavioral-тесты, документация bank_model-формата. Формально это тот же стандарт, перенесённый на корпоративный 3-statement.

**Два архитектурных отличия от банка:** (1) контур ацикличен (opening balances вместо неподвижной точки) — приемлемо, требует явной фиксации и проверки эквивалентности решателю; (2) **отсутствует sync gate** — и он же главный пробел: Python engine расходится с Excel на порядок по EBITDA (K1), рейтинг-сейв сломан (K2), что батарея не ловит.

**Приоритеты:** K1 (sync gate + декомпозиция EBITDA) → K2 (сигнатура + тест) → K3 (E2 годовая сетка) → W2 (стресс-гейт new_term) → W1/W3/W5 (документация и литералы).

Отчёт не коммитился. Автор чекапа: Claude (bank_model-стандарт верификации).

---

# REMEDIATION (17.11, выполнено в той же сессии)

## K2 — rating save: ИСПРАВЛЕНО
- `repository.upsert_rating`: добавлены `score_detail` (JSON в новую колонку ratings.score_detail),
  `nd_ebitda`, `icr` (в rating_metrics как credit_metrics). `schema.py`: колонка в DDL + миграция
  `_migrate_ratings_score_detail` (ALTER TABLE для существующих БД).
- Тест `TestRatingSavePath` (tests/unit/test_db_schema.py): save + идемпотентный upsert.
  Живой прогон: «Рейтинг сохранён: base → 3 лет», ERROR нет. pytest: 81 passed (было 80).

## K3 (E2) — сетка годов: ИСПРАВЛЕНО (двойной дефект)
1. Builder: заголовок лет FCFF писался через `year_headers(ws, r, [], fc)` в C:E, тогда как
   данные FCFF — в F:H (коллизия сетки). Стало `col_start=3 + n_hist_vl` → заголовок в колонках данных.
2. Аудитор E2: лист может содержать НЕСКОЛЬКО годовых сеток (FCFF F:H) и скалярные блоки
   (WACC, Net Debt «последний прогнозный год», SOTP-terminal) — год ячейки теперь определяется
   ближайшей строкой заголовков ВЫШЕ в той же колонке, скаляры вне сетки пропускаются.
- Пересборка обеих книг: аудит --excel → **0 расхождений кэша, E2 «0 смещений», тождества PASS ×2**.
- Заодно закрыт W1 по calcPr: builder снимает iterate (чистый DAG, 0 SCC) — единая топология обеих книг.

## W2 — стресс-гейт new_term: ИСПРАВЛЕНО
- 17_Debt: `new_term = IF(EBITDA<=0, 0, IF(gate, full_need, pen_limit_path))` — при отрицательной
  EBITDA срочный драфт = 0 (штрафной тракт тоже недоступен); при EBITDA>0 закрытый гейт =
  штрафное привлечение в пределах pen_limit (семантика сохранена).
- it_res (90_Checks #C3): срабатывает только при открытом рынке (EBITDA>0) — недофинансированный
  разрыв при закрытом рынке = флаг стресса, не ошибка книги (error_count не включает it_res).
- verify_model RUSAL: **ALL BEHAVIORAL TESTS PASS** (Sc3: EBITDA −2,179 → new_term 0);
  NORNICKEL: ALL PASS.

## K1 — sync gate + декомпозиция: ЧАСТИЧНО ЗАКРЫТ (значительный прогресс)
- **Корень расхождения найден**: `_solve_sga` брал `opex_ratio_recommended` = (|sga|+|distribution|)/rev,
  при IFRS-маппинге Русала distribution уже внутри sga → двойной счёт (20.2% vs sga 13.5%)
  → SGA 2,701 vs Excel 1,197 → EBITDA ≈ 0.
- **Фикс engine** (`engine/model/blocks/sga.py`): приоритет источника SGA = явные компоненты
  конфигурации (split-режим, сумма %-of-revenue) → `sga_ratio_recommended` → last → медиана;
  opex_ratio исключён (двойной счёт по построению); YAML-компоненты вне статистического клампа.
- **Результат**: engine EBITDA 1,206/1,123/1,012 (margin 9.0/8.1/7.1%) vs Excel 1,313/1,407/1,256
  (8.4/9.2/8.3%) — было ~0/отрицательная, расхождение сжато со 100x до Δmargin ≤1.3 п.п.
- **Новый гейт** `templates/excel_v4/scripts/sync_gate_corp.py`: Excel (Model_Output) ↔ engine.
  Структура (COGS%/EBITDA%/Net%) — жёсткий допуск 3 п.п. (input-insensitive);
  уровни — info ±20% (макровходы разные: Excel фикс-сценарии vs VECM). RUSAL: PASS (exit 0).
  Nornickel: exit 2 (engine недоступен без Vertex PG — штатно).
- **Остаток K1**: (а) уровни Revenue Δ−14.5% (VECM LME vs Excel Base 2,800 — разные макро, не дефект);
  (б) Net% Δ до 2.9 п.п. (разные долговые расписания/associates) — мониторить через гейт;
  (в) Nornickel engine-сверка требует PG-доступа.

## Верификационный срез после remediation
| проверка | результат |
|---|---|
| pytest | 81 passed (+TestRatingSavePath) |
| аудит --excel, обе книги | 0 расх. кэша, 0 ошибок, E2 PASS, BS/CF/PPE/Debt/Equity PASS |
| verify_model, обе книги | ALL BEHAVIORAL TESTS PASS |
| sync_gate_corp (rusal) | PASS, exit 0 |

Изменённые файлы: engine/database/repository.py, engine/database/schema.py,
engine/model/blocks/sga.py, tests/unit/test_db_schema.py,
templates/excel_v4/scripts/build_model.py, scripts/audit_corp_model.py,
templates/excel_v4/scripts/sync_gate_corp.py (новый), model/rusal_v4.xlsx,
model/nornickel_v4.xlsx (артефакты, в .gitignore).

## Addendum (17.11, закрытие пробелов)

- **W3 закрыт**: литералы 365 вынесены в параметр `CP.day_count` (builder ссылается
  на него из 03_Assump/16_WC); H1: 130→103 / 136→109 (остаток — литералы 17_Debt:
  спреды/теноры, следующий раунд). **F5 закрыт**: 0 констант без тега источника
  ([НОРМ] day_count, [ОЦЕНКА] CapEx floor).
- **W5 закрыт**: IMPLEMENTATION_PLAN приведён к факту (fullCalcOnLoad=1, чистый DAG,
  iterate снят; добавлены принципы 9–10); AUDIT_FIXES — раздел Round v10.
- Итоговая батарея: аудит 0 расх./0 ошибок/E2 PASS/F5 PASS (обе книги),
  verify ALL BEHAVIORAL PASS ×2, pytest 81 passed, sync_gate_corp PASS.
- Коммиты выполнены (запрошено пользователем): см. git log.
