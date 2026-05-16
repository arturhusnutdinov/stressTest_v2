# stressTest Engine v2 — План доработок

> Составлен: 2026-05-16 на основе глубокого анализа кодовой базы.
> Приоритет: P0 (критично) → P1 (важно) → P2 (желательно) → P3 (косметика).

---

## P0 — КРИТИЧЕСКИЕ (влияют на стабильность и достоверность)

### 1. Покрытие модульными тестами (pytest)

**Текущее состояние:** Python-тесты отсутствуют полностью. Есть только 10 smoke-тестов PDF-парсера. Ядро движка (21 500+ строк) не покрыто.

**Шаги:**

#### 1a. Тестовая инфраструктура
```
Действие:      Создать pyproject.toml с [tool.pytest.ini_options] и conftest.py
Инструменты:   pytest, pytest-cov, pytest-mock
Результат:     pytest собирает тесты; testpaths = ["tests/"]
Файлы:         pyproject.toml, tests/conftest.py
```

#### 1b. Фикстуры БД
```
Действие:      Создать фикстуру tmp_sqlite_db с полной схемой и минимальными данными
Результат:     Каждый тест работает с изолированной in-memory SQLite БД
Файлы:         tests/conftest.py (db_session фикстура)
```

#### 1c. Тесты препроцессора (14 групп метрик)
```
Действие:      Для каждой группы метрик — отдельный TestCase с parametrize
Тесты:         test_margin_ratios, test_wc_days, test_capex, test_debt,
               test_interest, test_equity, test_extended, test_beta_coefficients,
               test_revenue_betas, test_lease, test_cogs_macro, 
               test_cf_reconciliation, test_is_reconciliation, test_unmodeled_items
Вход:          Фикстура с 5 годами синтетических данных (BS/IS/CF)
Проверки:      _recommended > 0, _ewa в [p10, p90], _last == последнее значение
Результат:     Покрытие preprocessor/core.py ≥ 80%
Файлы:         tests/unit/preprocessor/
```

#### 1d. Тесты ModelInputLoader
```
Действие:      Проверить загрузку HistoricState и ModelConfig из YAML + БД
Тесты:         test_load_historic, test_load_config, test_fill_drivers_from_preprocess,
               test_load_debt_instruments, test_load_macro_forecasts,
               test_build_base_year_state, test_detect_ppe_mode, test_detect_wc_mode
Результат:     Покрытие engine/model/loader.py ≥ 80%
Файлы:         tests/unit/model/test_loader.py
```

#### 1e. Тесты ядра модели (ThreeStatementModel)
```
Действие:      Для каждого блока _solve_* — unit-тесты с синтетическими входными данными
Тесты:         test_solve_revenue, test_solve_cogs, test_solve_sga, test_solve_ppe,
               test_solve_wc, test_solve_debt_parametric, test_solve_debt_optimizer,
               test_solve_tax_block, test_solve_equity, test_solve_lease,
               test_solve_cf, test_solve_bs_totals, test_bs_identity,
               test_cf_bridge, test_joint_convergence
Результат:     Покрытие engine/model/core.py ≥ 70%
Файлы:         tests/unit/model/test_core.py
```

#### 1f. Тесты corkscrew-блоков
```
Действие:      Изолированные тесты для каждого блока schedules/
Тесты:         test_ppe_block, test_debt_block, test_debt_optimizer,
               test_tax_block, test_lease_block, test_equity_block,
               test_wc_block, test_interest_payable_block, test_intangibles_block
Результат:     Покрытие engine/model/schedules/ ≥ 85%
Файлы:         tests/unit/model/schedules/
```

#### 1g. Интеграционные тесты
```
Действие:      Полный прогон build_model() для us_steel и rusal — base + все stress сценарии
Тесты:         test_full_pipeline_us_steel, test_full_pipeline_rusal,
               test_stress_scenarios, test_rating, test_covenants
Результат:     BS_diff = 0.0 и CF_diff = 0.0 для всех годов и сценариев
Файлы:         tests/integration/
```

---

### 2. Декомпозиция engine/model/core.py (2 044 строки)

**Текущее состояние:** Все блоки Revenue, COGS, SGA, PPE, WC, Debt, Lease, Tax, Equity, Interest Payable, BS Totals, CF, Covenant Acceleration находятся в одном файле.

**Шаги:**

```
Шаг 1: Выделить блоки IS    → engine/model/blocks/revenue.py     (~120 строк)
Шаг 2: Выделить блок COGS   → engine/model/blocks/cogs.py        (~160 строк)
Шаг 3: Выделить блок SGA    → engine/model/blocks/sga.py         (~70 строк)
Шаг 4: Выделить блок PPE    → engine/model/blocks/ppe.py         (~110 строк)
Шаг 5: Выделить блок WC     → engine/model/blocks/wc.py          (~80 строк)
Шаг 6: Выделить блок Lease  → engine/model/blocks/lease.py       (~70 строк)
Шаг 7: Выделить блок Debt   → engine/model/blocks/debt.py        (~350 строк)
Шаг 8: Выделить блок Tax    → engine/model/blocks/tax.py         (~70 строк)
Шаг 9: Выделить блок Equity → engine/model/blocks/equity.py      (~60 строк)
Шаг 10: Выделить BS Totals   → engine/model/blocks/bs_totals.py  (~80 строк)
Шаг 11: Выделить CF         → engine/model/blocks/cf.py          (~100 строк)
Шаг 12: Выделить Covenant   → engine/model/blocks/covenant.py    (~40 строк)
```

**Контракт каждого блока:**
```python
# Каждый блок — чистая функция:
def solve_revenue(state: YearState, prev: YearState, config: ModelConfig, 
                  historic: HistoricState, dispatcher: ForecastDispatcher) -> YearState
```

**Результат:** `core.py` — только `run()`, `_solve_year()`, инициализация; каждый блок в отдельном файле.

---

## P1 — ВАЖНО (влияют на поддерживаемость и расширяемость)

### 3. Устранение прямых YAML/SQL-запросов из ядра

**Текущее состояние:** `core.py` напрямую читает `project.yaml` через `yaml.safe_load()` в методах:
- `_solve_revenue` (стр. 363-373)
- `_solve_cogs` (стр. 449-453)
- `_solve_is_subtotals` (стр. 779-785)
- `CogsBlock.__init__` — прямой `sqlite3.connect` (стр. 175-181)

**Шаги:**

```
Действие:      Перенести все YAML-чтения в ModelInputLoader._build_model_config
               Параметры передавать через ModelConfig поля:
               - revenue.revenue_factor
               - revenue.segment_modeling
               - cogs.revenue_factor, cogs.cost_factor, cogs.mode
               - accounting_conventions.da_in_cogs
Результат:     core.py не делает import yaml; 0 прямых sqlite3.connect
Файлы:         engine/model/loader.py (добавить поля), 
               engine/model/inputs.py (добавить поля в ModelConfig),
               engine/model/core.py (удалить yaml/sqlite3 вызовы)
```

### 4. Устранение hardcoded значений

**Текущие hardcoded значения:**

| Файл | Строка | Значение | Что должно быть |
|------|--------|----------|-----------------|
| `core.py` | 1110 | `209_000_000.0` | Finance lease liability US Steel → из препроцессора |
| `core.py` | 1753 | `0.10` | Payroll ratio to SGA → из препроцессора |
| `core.py` | 164 | `0.33` | Lease op_decay_rate default → LeaseParams default |
| `loader.py` | 586 | `0.0` | Lease amount defaults → константы в inputs.py |

**Шаги:**

```
Действие:      Создать engine/constants.py с именованными константами
               Все значения, где это возможно, вычислять в препроцессоре
Результат:     Ни одного "магического числа" в core.py без комментария
Файлы:         engine/constants.py, engine/model/core.py, engine/model/loader.py
```

### 5. CI/CD Pipeline

**Шаги:**

```
Действие:      Создать .github/workflows/ci.yml
Содержание:    - lint (ruff)
               - type-check (mypy)
               - test (pytest с coverage)
               - matrix: python-version [3.11, 3.12, 3.13]
Триггеры:      push на main, pull_request
Результат:     Каждый пул-реквест автоматически тестируется
Файлы:         .github/workflows/ci.yml
```

### 6. Типизация (mypy strict)

**Шаги:**

```
Действие:      Добавить mypy в dev-зависимости
               Постепенно активировать strict-режим:
               1. engine/model/inputs.py (уже с аннотациями)
               2. engine/model/schedules/
               3. engine/preprocessor/core.py
               4. engine/model/core.py
Результат:     mypy --strict проходит без ошибок
Файлы:         pyproject.toml ([tool.mypy]), все .py файлы
```

---

## P2 — ЖЕЛАТЕЛЬНО (повышают качество кода)

### 7. Линтинг и форматирование

```
Действие:      Добавить ruff в CI; настроить правила
Правила:       line-length=100, docstring-convention=google
               Запретить: unused-import, bare-except, broad-except
Результат:     ruff check --select ALL проходит с 0 ошибок
Файлы:         pyproject.toml ([tool.ruff]), все .py файлы
```

### 8. Документирование API (docstrings)

```
Действие:      Добавить Google-style docstrings ко всем публичным методам
               Особенно: ModelInputLoader, ThreeStatementModel, 
               ModelPreprocessor, Repository, все Corkscrew-блоки
Результат:     pdoc / sphinx генерирует документацию API без варнингов
Файлы:         Все engine/**/*.py
```

### 9. Унификация языка документации

```
Действие:      Перевести ВСЕ docstrings на английский
               Документацию в docs/ — на английский
               Комментарии в коде — английский (уже смешанно)
Результат:     Единый язык во всей кодовой базе
```

### 10. Пакетирование

```
Действие:      Создать pyproject.toml с:
               - [project] (name, version, description, dependencies)
               - [project.scripts] (stresstest = engine.orchestrator:main)
               - [build-system] (setuptools)
Результат:     pip install -e . работает; stresstest --company us_steel из CLI
Файлы:         pyproject.toml
```

---

## P3 — КОСМЕТИКА (nice-to-have)

### 11. Performance-оптимизации

```
Действие:      Профилирование cProfile, выявление узких мест
Ожидаемые:     Предзагрузка всех YAML-конфигов один раз при старте
               Кеширование preprocess_metrics в памяти
               Ленивая загрузка schedule-данных
Результат:     Полный прогон build_model() < 5 секунд (сейчас ~10-15с)
```

### 12. Docker-образ

```
Действие:      Dockerfile с Python 3.12 + зависимостями
               docker-compose.yml для разработки
Результат:     docker compose up запускает Jupyter + API
Файлы:         Dockerfile, docker-compose.yml
```

### 13. Changelog и версионирование

```
Действие:      CHANGELOG.md, версионирование Semantic Versioning
               Git tags для релизов
Результат:     git tag v2.1.0; CHANGELOG.md с описанием изменений
```

---

## Дорожная карта (Roadmap)

| Фаза | Задачи | Ожидаемый срок |
|------|--------|---------------|
| **Sprint 1** | P0.1a-b (тестовая инфраструктура, фикстуры) | 2-3 дня |
| **Sprint 2** | P0.1c-d (тесты препроцессора и лоадера) | 3-4 дня |
| **Sprint 3** | P0.1e-f (тесты ядра и corkscrews) | 4-5 дней |
| **Sprint 4** | P0.1g (интеграционные тесты), P0.2 (декомпозиция core.py) | 4-5 дней |
| **Sprint 5** | P1.3 (убрать YAML из ядра), P1.4 (hardcoded → constants) | 2-3 дня |
| **Sprint 6** | P1.5 (CI/CD), P1.6 (mypy), P2.7 (ruff) | 2-3 дня |
| **Sprint 7** | P2.8-9 (документирование), P2.10 (пакетирование) | 2-3 дня |
| **Sprint 8** | P3.11-13 (perf, docker, changelog) | 3-4 дня |

**Всего: ~8 спринтов, ~24-30 рабочих дней.**

---

## Критерии приёмки (Definition of Done)

- [ ] `pytest` проходит 100% тестов
- [ ] Coverage ≥ 70% (ядро), ≥ 85% (corkscrews)
- [ ] `mypy --strict` без ошибок
- [ ] `ruff check` без ошибок
- [ ] CI/CD зелёный на push
- [ ] `core.py` < 400 строк (только run + _solve_year + инициализация)
- [ ] 0 прямых `yaml.safe_load()` и `sqlite3.connect()` в core.py
- [ ] 0 недокументированных «магических чисел»
- [ ] Все docstrings на английском
- [ ] `pip install -e .` работает
- [ ] BS_diff = 0.0 и CF_diff = 0.0 для всех компаний/сценариев
