"""
Единая схема БД для финансовой модели v2.
Все таблицы создаются здесь. Единственный источник правды о структуре БД.
"""

from __future__ import annotations

# ─── DDL ───────────────────────────────────────────────────────────────────────

SCHEMA_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ═══════════════════════════════════════════════════════════════
-- СПРАВОЧНИКИ
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS companies (
    company_id          TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    industry            TEXT,
    currency            TEXT NOT NULL DEFAULT 'USD',
    accounting_standard TEXT NOT NULL DEFAULT 'US_GAAP',  -- US_GAAP | IFRS | RSBU
    db_unit             TEXT NOT NULL DEFAULT 'tUSD',      -- USD | tUSD | mUSD
    fiscal_year_end     TEXT DEFAULT '12-31',
    country             TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS periods (
    period_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id  TEXT NOT NULL REFERENCES companies(company_id),
    year        INTEGER NOT NULL,
    is_annual   INTEGER NOT NULL DEFAULT 1,
    is_forecast INTEGER NOT NULL DEFAULT 0,
    UNIQUE(company_id, year, is_annual)
);

CREATE TABLE IF NOT EXISTS scenarios (
    scenario_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id   TEXT NOT NULL REFERENCES companies(company_id),
    name         TEXT NOT NULL,
    type         TEXT NOT NULL DEFAULT 'base',  -- base | bull | bear | stress | custom
    description  TEXT,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_id, name)
);

CREATE TABLE IF NOT EXISTS model_versions (
    version_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id   TEXT NOT NULL REFERENCES companies(company_id),
    version      TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'draft',  -- draft | published | archived
    description  TEXT,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_id, version)
);

-- ═══════════════════════════════════════════════════════════════
-- RAW СЛОЙ — ИСТОРИЯ
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS history_is (
    company_id  TEXT    NOT NULL REFERENCES companies(company_id),
    period_id   INTEGER NOT NULL REFERENCES periods(period_id),
    metric      TEXT    NOT NULL,
    value       REAL    NOT NULL,
    source      TEXT,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, period_id, metric)
);

CREATE TABLE IF NOT EXISTS history_bs (
    company_id  TEXT    NOT NULL REFERENCES companies(company_id),
    period_id   INTEGER NOT NULL REFERENCES periods(period_id),
    metric      TEXT    NOT NULL,
    value       REAL    NOT NULL,
    source      TEXT,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, period_id, metric)
);

CREATE TABLE IF NOT EXISTS history_cf (
    company_id  TEXT    NOT NULL REFERENCES companies(company_id),
    period_id   INTEGER NOT NULL REFERENCES periods(period_id),
    metric      TEXT    NOT NULL,
    value       REAL    NOT NULL,
    source      TEXT,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, period_id, metric)
);

-- ═══════════════════════════════════════════════════════════════
-- RAW СЛОЙ — РАСПИСАНИЯ
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS debt_instruments (
    instrument_id        TEXT NOT NULL,
    company_id           TEXT NOT NULL REFERENCES companies(company_id),
    instrument_name      TEXT NOT NULL,
    db_type              TEXT NOT NULL,  -- revolving|term_amort|term_bullet|bond_fixed|bond_float|finance_lease|other
    currency             TEXT NOT NULL DEFAULT 'USD',
    opening_balance      REAL DEFAULT 0,
    committed_amount     REAL,           -- для revolving: лимит линии
    maturity_date        TEXT,
    interest_rate        REAL,           -- % (fixed rate или спред для float)
    rate_type            TEXT DEFAULT 'fixed',  -- fixed | floating
    base_rate_factor     TEXT,           -- макро-фактор базовой ставки: sofr, key_rate
    payment_frequency    TEXT DEFAULT 'semi_annual',
    amortization_profile TEXT DEFAULT 'bullet',
    callable_flag        INTEGER DEFAULT 0,
    covenant_package     TEXT,
    source               TEXT,
    updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (instrument_id, company_id)
);

CREATE TABLE IF NOT EXISTS debt_schedule (
    company_id       TEXT    NOT NULL REFERENCES companies(company_id),
    period_id        INTEGER NOT NULL REFERENCES periods(period_id),
    instrument_id    TEXT    NOT NULL,
    instrument_name  TEXT,
    opening_balance  REAL DEFAULT 0,
    draw             REAL DEFAULT 0,
    repay_mandatory  REAL DEFAULT 0,
    repay_voluntary  REAL DEFAULT 0,
    interest_expense REAL DEFAULT 0,
    interest_paid    REAL DEFAULT 0,
    closing_balance  REAL DEFAULT 0,
    interest_rate    REAL,
    classification   TEXT DEFAULT 'LT',  -- ST | LT | RC
    source           TEXT,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, period_id, instrument_id)
);

CREATE TABLE IF NOT EXISTS ppe_components (
    company_id      TEXT    NOT NULL REFERENCES companies(company_id),
    period_id       INTEGER NOT NULL REFERENCES periods(period_id),
    component_id    TEXT    NOT NULL,
    component_name  TEXT,
    value_type      TEXT    NOT NULL,  -- gross | accumulated | net
    value           REAL,
    useful_life     REAL,
    source          TEXT,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, period_id, component_id, value_type)
);

CREATE TABLE IF NOT EXISTS lease_schedule (
    company_id      TEXT    NOT NULL REFERENCES companies(company_id),
    period_id       INTEGER NOT NULL REFERENCES periods(period_id),
    lease_id        TEXT    NOT NULL,
    lease_name      TEXT,
    lease_type      TEXT    NOT NULL,  -- finance | operating
    rou_open        REAL DEFAULT 0,
    rou_dep         REAL DEFAULT 0,
    rou_close       REAL DEFAULT 0,
    liab_open       REAL DEFAULT 0,
    interest_exp    REAL DEFAULT 0,
    payment         REAL DEFAULT 0,
    liab_close      REAL DEFAULT 0,
    discount_rate   REAL,
    source          TEXT,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, period_id, lease_id)
);

CREATE TABLE IF NOT EXISTS tax_schedule (
    company_id      TEXT    NOT NULL REFERENCES companies(company_id),
    period_id       INTEGER NOT NULL REFERENCES periods(period_id),
    ebt             REAL DEFAULT 0,
    current_tax     REAL DEFAULT 0,
    deferred_tax    REAL DEFAULT 0,
    effective_rate  REAL,
    dta_open        REAL DEFAULT 0,
    dta_additions   REAL DEFAULT 0,
    dta_used        REAL DEFAULT 0,
    dta_close       REAL DEFAULT 0,
    dtl_open        REAL DEFAULT 0,
    dtl_additions   REAL DEFAULT 0,
    dtl_reversal    REAL DEFAULT 0,
    dtl_close       REAL DEFAULT 0,
    nol_open        REAL DEFAULT 0,
    nol_additions   REAL DEFAULT 0,
    nol_used        REAL DEFAULT 0,
    nol_close       REAL DEFAULT 0,
    source          TEXT,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, period_id)
);

CREATE TABLE IF NOT EXISTS equity_schedule (
    company_id          TEXT    NOT NULL REFERENCES companies(company_id),
    period_id           INTEGER NOT NULL REFERENCES periods(period_id),
    re_open             REAL DEFAULT 0,
    net_income          REAL DEFAULT 0,
    dividends           REAL DEFAULT 0,
    buybacks            REAL DEFAULT 0,
    issuance            REAL DEFAULT 0,
    other_equity_changes REAL DEFAULT 0,
    re_close            REAL DEFAULT 0,
    source              TEXT,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, period_id)
);

CREATE TABLE IF NOT EXISTS segment_data (
    company_id    TEXT    NOT NULL REFERENCES companies(company_id),
    period_id     INTEGER NOT NULL REFERENCES periods(period_id),
    segment_id    TEXT    NOT NULL,
    segment_name  TEXT,
    metric        TEXT    NOT NULL,
    value         REAL,
    source        TEXT,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, period_id, segment_id, metric)
);

-- ═══════════════════════════════════════════════════════════════
-- МАКРО
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS macro_factors (
    factor_name  TEXT    NOT NULL,
    year         INTEGER NOT NULL,
    value        REAL    NOT NULL,
    unit         TEXT,
    scope        TEXT    NOT NULL DEFAULT 'global',  -- global | industry | company
    company_id   TEXT    NOT NULL DEFAULT '',
    source       TEXT,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (factor_name, year, scope, company_id)
);

CREATE TABLE IF NOT EXISTS macro_forecasts (
    company_id   TEXT    NOT NULL REFERENCES companies(company_id),
    factor_name  TEXT    NOT NULL,
    year         INTEGER NOT NULL,
    value        REAL    NOT NULL,
    method       TEXT,   -- vecm | arima | ets | rw_drift
    scenario_id  INTEGER NOT NULL DEFAULT 0,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, factor_name, year, scenario_id)
);

CREATE TABLE IF NOT EXISTS macro_anomalies (
    company_id   TEXT    NOT NULL REFERENCES companies(company_id),
    factor_name  TEXT    NOT NULL,
    year         INTEGER NOT NULL,
    value        REAL,
    z_score      REAL,
    delta        REAL,
    suggested_dummy INTEGER DEFAULT 0,
    PRIMARY KEY (company_id, factor_name, year)
);

-- ═══════════════════════════════════════════════════════════════
-- ПРЕПРОЦЕССОР
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS preprocess_metrics (
    company_id    TEXT    NOT NULL REFERENCES companies(company_id),
    metric_group  TEXT    NOT NULL,
    metric_name   TEXT    NOT NULL,
    year          INTEGER NOT NULL,  -- -1 = сводная метрика (ewa/mean/last/recommended)
    value         REAL,
    source        TEXT,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, metric_group, metric_name, year)
);

CREATE TABLE IF NOT EXISTS model_equations (
    company_id     TEXT    NOT NULL REFERENCES companies(company_id),
    equation_name  TEXT    NOT NULL,
    method         TEXT,
    coefficients   TEXT,  -- JSON
    r_squared      REAL,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, equation_name)
);

-- ═══════════════════════════════════════════════════════════════
-- РЕЗУЛЬТАТЫ МОДЕЛИ
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS forecast_is (
    company_id   TEXT    NOT NULL REFERENCES companies(company_id),
    period_id    INTEGER NOT NULL REFERENCES periods(period_id),
    scenario_id  INTEGER NOT NULL REFERENCES scenarios(scenario_id),
    version_id   INTEGER REFERENCES model_versions(version_id),
    metric       TEXT    NOT NULL,
    value        REAL    NOT NULL,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, period_id, scenario_id, metric)
);

CREATE TABLE IF NOT EXISTS forecast_bs (
    company_id   TEXT    NOT NULL REFERENCES companies(company_id),
    period_id    INTEGER NOT NULL REFERENCES periods(period_id),
    scenario_id  INTEGER NOT NULL REFERENCES scenarios(scenario_id),
    version_id   INTEGER REFERENCES model_versions(version_id),
    metric       TEXT    NOT NULL,
    value        REAL    NOT NULL,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, period_id, scenario_id, metric)
);

CREATE TABLE IF NOT EXISTS forecast_cf (
    company_id   TEXT    NOT NULL REFERENCES companies(company_id),
    period_id    INTEGER NOT NULL REFERENCES periods(period_id),
    scenario_id  INTEGER NOT NULL REFERENCES scenarios(scenario_id),
    version_id   INTEGER REFERENCES model_versions(version_id),
    metric       TEXT    NOT NULL,
    value        REAL    NOT NULL,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, period_id, scenario_id, metric)
);

CREATE TABLE IF NOT EXISTS stress_results (
    company_id        TEXT    NOT NULL REFERENCES companies(company_id),
    stress_scenario_id INTEGER NOT NULL REFERENCES scenarios(scenario_id),
    period_id         INTEGER NOT NULL REFERENCES periods(period_id),
    statement_type    TEXT    NOT NULL,  -- IS | BS | CF
    metric            TEXT    NOT NULL,
    value             REAL    NOT NULL,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, stress_scenario_id, period_id, statement_type, metric)
);

CREATE TABLE IF NOT EXISTS covenant_results (
    company_id     TEXT    NOT NULL REFERENCES companies(company_id),
    scenario_id    INTEGER NOT NULL REFERENCES scenarios(scenario_id),
    period_id      INTEGER NOT NULL REFERENCES periods(period_id),
    covenant_name  TEXT    NOT NULL,
    value          REAL,
    threshold      REAL,
    headroom_pct   REAL,
    breached       INTEGER DEFAULT 0,
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, scenario_id, period_id, covenant_name)
);

CREATE TABLE IF NOT EXISTS ratings (
    company_id   TEXT    NOT NULL REFERENCES companies(company_id),
    scenario_id  INTEGER NOT NULL REFERENCES scenarios(scenario_id),
    period_id    INTEGER NOT NULL REFERENCES periods(period_id),
    methodology  TEXT    NOT NULL,
    grade        TEXT,
    score        REAL,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, scenario_id, period_id, methodology)
);

CREATE TABLE IF NOT EXISTS rating_metrics (
    rating_id     INTEGER NOT NULL,
    factor_name   TEXT    NOT NULL,
    metric_name   TEXT    NOT NULL,
    value         REAL,
    score         REAL,
    weight        REAL,
    PRIMARY KEY (rating_id, factor_name, metric_name)
);

-- ═══════════════════════════════════════════════════════════════
-- АУДИТ
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operation   TEXT    NOT NULL,  -- INSERT | UPDATE | DELETE | LOAD | RUN
    table_name  TEXT,
    company_id  TEXT,
    record_id   TEXT,
    details     TEXT,  -- JSON
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ═══════════════════════════════════════════════════════════════
-- ДЕТАЛИЗИРОВАННЫЕ CORKSCREW-РАСПИСАНИЯ
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS sched_lease_finance (
    company_id          TEXT    NOT NULL REFERENCES companies(company_id),
    period_id           INTEGER NOT NULL REFERENCES periods(period_id),
    lease_id            TEXT    NOT NULL,
    opening             REAL DEFAULT 0,
    additions           REAL DEFAULT 0,
    payments_principal  REAL DEFAULT 0,
    payments_interest   REAL DEFAULT 0,
    depreciation_is     REAL DEFAULT 0,
    interest_expense_is REAL DEFAULT 0,
    closing             REAL DEFAULT 0,
    rou_asset_open      REAL DEFAULT 0,
    rou_asset_dep       REAL DEFAULT 0,
    rou_asset_close     REAL DEFAULT 0,
    liab_current        REAL DEFAULT 0,
    liab_noncurrent     REAL DEFAULT 0,
    mode                TEXT DEFAULT 'actual',
    source              TEXT,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, period_id, lease_id)
);

CREATE TABLE IF NOT EXISTS sched_lease_operating (
    company_id          TEXT    NOT NULL REFERENCES companies(company_id),
    period_id           INTEGER NOT NULL REFERENCES periods(period_id),
    lease_id            TEXT    NOT NULL,
    opening             REAL DEFAULT 0,
    additions           REAL DEFAULT 0,
    payments            REAL DEFAULT 0,
    lease_expense_is    REAL DEFAULT 0,
    closing             REAL DEFAULT 0,
    rou_asset_open      REAL DEFAULT 0,
    rou_asset_dep       REAL DEFAULT 0,
    rou_asset_close     REAL DEFAULT 0,
    liab_current        REAL DEFAULT 0,
    liab_noncurrent     REAL DEFAULT 0,
    mode                TEXT DEFAULT 'actual',
    source              TEXT,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, period_id, lease_id)
);

CREATE TABLE IF NOT EXISTS sched_tax_corkscrew (
    company_id      TEXT    NOT NULL REFERENCES companies(company_id),
    period_id       INTEGER NOT NULL REFERENCES periods(period_id),
    temp_diff_type  TEXT    NOT NULL,  -- depreciation | inventory | leases | other
    dta_opening     REAL DEFAULT 0,
    dta_created     REAL DEFAULT 0,
    dta_utilized    REAL DEFAULT 0,
    dta_closing     REAL DEFAULT 0,
    dtl_opening     REAL DEFAULT 0,
    dtl_created     REAL DEFAULT 0,
    dtl_reversed    REAL DEFAULT 0,
    dtl_closing     REAL DEFAULT 0,
    source          TEXT,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, period_id, temp_diff_type)
);

CREATE TABLE IF NOT EXISTS sched_wc_corkscrew (
    company_id      TEXT    NOT NULL REFERENCES companies(company_id),
    period_id       INTEGER NOT NULL REFERENCES periods(period_id),
    component       TEXT    NOT NULL,  -- ar | inventory | ap | other_ca | other_cl
    opening_balance REAL DEFAULT 0,
    closing_balance REAL DEFAULT 0,
    delta           REAL DEFAULT 0,
    driver_value    REAL,
    driver_metric   TEXT,
    source          TEXT,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, period_id, component)
);

CREATE TABLE IF NOT EXISTS interest_paid_split (
    company_id                    TEXT    NOT NULL REFERENCES companies(company_id),
    period_id                     INTEGER NOT NULL REFERENCES periods(period_id),
    interest_paid_debt            REAL DEFAULT 0,
    interest_paid_leases          REAL DEFAULT 0,
    interest_paid_total           REAL DEFAULT 0,
    interest_payable_debt_open    REAL DEFAULT 0,
    interest_payable_debt_close   REAL DEFAULT 0,
    interest_payable_leases_open  REAL DEFAULT 0,
    interest_payable_leases_close REAL DEFAULT 0,
    change_debt                   REAL DEFAULT 0,
    change_leases                 REAL DEFAULT 0,
    source                        TEXT,
    updated_at                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, period_id)
);

CREATE TABLE IF NOT EXISTS lease_maturity_ladder (
    company_id       TEXT    NOT NULL REFERENCES companies(company_id),
    period_id        INTEGER NOT NULL REFERENCES periods(period_id),
    lease_id         TEXT    NOT NULL,
    lease_type       TEXT    NOT NULL,  -- finance | operating
    maturity_year    INTEGER NOT NULL,
    principal_amount REAL DEFAULT 0,
    interest_amount  REAL DEFAULT 0,
    total_payment    REAL DEFAULT 0,
    currency_code    TEXT DEFAULT 'USD',
    source           TEXT,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, period_id, lease_id, maturity_year)
);

CREATE TABLE IF NOT EXISTS balancing_adjustments (
    company_id          TEXT    NOT NULL REFERENCES companies(company_id),
    period_id           INTEGER NOT NULL REFERENCES periods(period_id),
    statement_type      TEXT    NOT NULL,  -- IS | BS | CF
    metric              TEXT    NOT NULL,
    adjustment_value    REAL    NOT NULL,
    is_balancing        INTEGER DEFAULT 0,
    balancing_reason    TEXT,
    balancing_category  TEXT,
    lineage_pointers    TEXT,  -- JSON
    original_value      REAL,
    source              TEXT,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, period_id, statement_type, metric)
);

CREATE TABLE IF NOT EXISTS intangible_assets (
    company_id               TEXT    NOT NULL REFERENCES companies(company_id),
    period_id                INTEGER NOT NULL REFERENCES periods(period_id),
    category                 TEXT    NOT NULL,
    gross_amount             REAL DEFAULT 0,
    accumulated_amortization REAL DEFAULT 0,
    net_amount               REAL DEFAULT 0,
    useful_life              TEXT,
    source                   TEXT,
    updated_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, period_id, category)
);

CREATE TABLE IF NOT EXISTS debt_cashflows (
    company_id     TEXT    NOT NULL REFERENCES companies(company_id),
    instrument_id  TEXT    NOT NULL,
    year           INTEGER NOT NULL,
    period         TEXT,
    cashflow_type  TEXT    NOT NULL,  -- interest | principal | drawdown | fee
    amount         REAL    NOT NULL,
    currency       TEXT    DEFAULT 'USD',
    note           TEXT,
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, instrument_id, year, cashflow_type)
);

-- ═══════════════════════════════════════════════════════════════
-- ИНДЕКСЫ
-- ═══════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_history_is_company_year ON history_is(company_id, period_id);
CREATE INDEX IF NOT EXISTS idx_history_bs_company_year ON history_bs(company_id, period_id);
CREATE INDEX IF NOT EXISTS idx_history_cf_company_year ON history_cf(company_id, period_id);
CREATE INDEX IF NOT EXISTS idx_forecast_is_scenario    ON forecast_is(company_id, scenario_id);
CREATE INDEX IF NOT EXISTS idx_forecast_bs_scenario    ON forecast_bs(company_id, scenario_id);
CREATE INDEX IF NOT EXISTS idx_forecast_cf_scenario    ON forecast_cf(company_id, scenario_id);
CREATE INDEX IF NOT EXISTS idx_preprocess_company      ON preprocess_metrics(company_id, metric_group);
CREATE INDEX IF NOT EXISTS idx_debt_schedule_company   ON debt_schedule(company_id, period_id);
CREATE INDEX IF NOT EXISTS idx_macro_factors_name      ON macro_factors(factor_name, year);
CREATE INDEX IF NOT EXISTS idx_macro_forecasts_company ON macro_forecasts(company_id, factor_name);
CREATE INDEX IF NOT EXISTS idx_audit_log_company       ON audit_log(company_id, created_at);
CREATE INDEX IF NOT EXISTS idx_sched_lease_fin_company  ON sched_lease_finance(company_id, period_id);
CREATE INDEX IF NOT EXISTS idx_sched_lease_oper_company ON sched_lease_operating(company_id, period_id);
CREATE INDEX IF NOT EXISTS idx_debt_cashflows_company   ON debt_cashflows(company_id, instrument_id);
CREATE INDEX IF NOT EXISTS idx_balancing_company        ON balancing_adjustments(company_id, period_id);
CREATE INDEX IF NOT EXISTS idx_intangibles_company      ON intangible_assets(company_id, period_id);
"""


def create_schema(conn) -> None:
    """Применить DDL к существующему соединению."""
    conn.executescript(SCHEMA_DDL)
    conn.commit()


def get_table_names() -> list[str]:
    """Список всех таблиц для валидации и тестов."""
    import re
    return re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", SCHEMA_DDL)
