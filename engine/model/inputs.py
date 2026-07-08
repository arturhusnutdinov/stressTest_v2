"""
Dataclasses для входных данных модели.
Принцип: чистые dataclasses, нет зависимостей от БД или YAML.
Все данные передаются уже загруженными — model не знает об источниках.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


# ─── forecast methods ─────────────────────────────────────────────────────────

class ForecastMethod(str, Enum):
    MACRO  = "macro"   # Elastic Net регрессия на макро-факторы
    DRIVER = "driver"  # % от base статьи (revenue, cogs, etc.)
    DAYS   = "days"    # WC оборачиваемость (DSO/DIH/DPO)
    CORK   = "cork"    # Corkscrew roll-forward
    EWA    = "ewa"     # Exponentially Weighted Average
    LAST   = "last"    # Carry forward последнего значения
    ZERO   = "zero"    # Обнуляется в прогнозе
    CALC   = "calc"    # Вычисляется из других статей
    PLUG   = "plug"    # Балансирующая статья
    LINK   = "link"    # Связь с другим отчётом


@dataclass
class ForecastMethodConfig:
    method: ForecastMethod
    # DRIVER
    driver_base: Optional[str] = None
    driver_ratio: Optional[float] = None
    driver_ratio_source: Optional[str] = None  # reserved for future use (history_ewa | fixed)
    # DAYS
    days_metric: Optional[str] = None   # dso | dih | dpo
    days_base: Optional[str] = None     # revenue | cogs
    days_floor: Optional[float] = None
    # CORK
    corkscrew_type: Optional[str] = None  # ppe | debt | lease | tax | equity
    corkscrew_field: Optional[str] = None
    # EWA
    ewa_halflife_years: float = 3.0
    # MACRO
    macro_factors: List[str] = field(default_factory=list)
    macro_model: str = "elastic_net"
    # PLUG
    plug_min_value: Optional[float] = None
    plug_absorbs_gap: bool = False
    # LINK
    link_source: Optional[str] = None   # IS | BS | CF
    link_field: Optional[str] = None
    # CALC
    calc_formula: Optional[str] = None
    # Общие
    sign: float = 1.0


# ─── debt ─────────────────────────────────────────────────────────────────────

@dataclass
class DebtInstrument:
    """Один долговой инструмент."""
    instrument_id: str
    instrument_name: str
    db_type: str                    # revolving | term_amort | term_bullet | bond_fixed | bond_float | other
    currency: str = "USD"
    opening_balance: float = 0.0
    committed_amount: Optional[float] = None
    maturity_date: Optional[str] = None
    interest_rate: Optional[float] = None    # % годовых
    rate_type: str = "fixed"
    base_rate_factor: Optional[str] = None  # макро-фактор для floating
    payment_frequency: str = "semi_annual"
    amortization_profile: str = "bullet"
    callable_flag: bool = False
    # Для schedule_based режима: готовый corkscrew по годам
    schedule: Optional[Dict[int, Dict[str, float]]] = None

    @property
    def is_revolving(self) -> bool:
        return self.db_type == "revolving"

    @property
    def is_bullet(self) -> bool:
        return self.amortization_profile == "bullet"


@dataclass
class RCSettings:
    """Настройки Revolving Credit Facility."""
    enabled: bool = True
    limit: float = 0.0
    min_cash: float = 0.0
    rate_spread: float = 0.03
    rate_delta_pct: float = 0.0


@dataclass
class RefinancingSettings:
    """Настройки рефинансирования."""
    enabled: bool = True
    mode: str = "simple"          # simple | detailed
    extend_years: int = 5
    rate_adjustment: float = 0.0
    fees_pct: float = 0.001


@dataclass
class DebtSettings:
    """Параметры долгового движка."""
    mode: str = "parametric"       # schedule_based | optimizer | parametric
    target_pct_revenue: float = 0.35
    avg_rate_pct: float = 0.05
    general_rate_delta_pct: float = 0.0
    iter_max: int = 15
    tol: float = 1e-6
    rc: RCSettings = field(default_factory=RCSettings)
    refinancing: RefinancingSettings = field(default_factory=RefinancingSettings)
    # LP-веса (только для optimizer)
    lp_w_cash_def: float = 1_000_000.0
    lp_w_icr: float = 600_000.0
    lp_w_lev: float = 600_000.0
    lp_w_draw: float = 0.1
    lp_w_end_debt: float = 0.02
    # Ковенанты для LP
    icr_min: float = 2.0
    lev_max: float = 3.5
    absorb_nonmodeled_st_debt: bool = True
    # CBR key rate forecast for floating instruments (year → rate, e.g. {2025: 0.19})
    cbr_key_rate_forecast: Dict[int, float] = field(default_factory=dict)


# ─── lease drivers ────────────────────────────────────────────────────────────

# NOTE: legacy dataclass — LeaseParams (EWA-calibrated) is the primary lease config;
# LeaseDrivers is retained for opening balances and backward compatibility with older YAML configs
@dataclass
class LeaseDrivers:
    enabled: bool = False
    default_discount_rate: float = 0.05
    rate_delta_pct: float = 0.0
    # Входящие балансы
    finance_rou_opening: float = 0.0
    finance_liab_opening: float = 0.0
    operating_rou_opening: float = 0.0
    operating_liab_opening: float = 0.0


@dataclass
class LeaseParams:
    """
    EWA-calibrated corkscrew parameters — computed by preprocessor from history.
    YAML can override any field; otherwise preprocessor recommended value is used.
    """
    # Operating lease (US GAAP ASC 842)
    op_decay_rate:    float = 0.33   # ROU amortisation / ROU_open  (~3yr avg life)
    op_new_leases:    float = 0.0    # new ROU additions per year ($)
    op_cash_payment:  float = 0.0    # operating lease cash outflow to CFO ($)
    # Finance lease
    fin_principal_rate: float = 0.25  # principal repayment / liab_open
    fin_amort_rate:     float = 0.28  # ROU dep / fin_asset_open
    fin_interest_rate:  float = 0.06  # interest expense / liab_open
    fin_new_leases:     float = 0.0   # new finance lease additions per year ($)


# ─── year state ───────────────────────────────────────────────────────────────

@dataclass
class YearState:
    """
    Полное состояние одного года модели.
    Заполняется инкрементально в _solve_year().
    Immutable после завершения года — следующий год читает из предыдущего.
    """
    year: int

    # IS
    revenue: float = 0.0
    cogs: float = 0.0
    gross_profit: float = 0.0
    sga: float = 0.0
    distribution_expenses: float = 0.0   # SGA split: distribution/selling
    admin_expenses: float = 0.0          # SGA split: administrative
    ecl_expenses: float = 0.0            # SGA split: expected credit losses
    other_opex: float = 0.0              # SGA split: other operating expenses
    dep_ppe: float = 0.0
    dep_rou: float = 0.0
    amort_intangibles: float = 0.0
    total_da: float = 0.0
    ebitda: float = 0.0
    asset_impairment: float = 0.0
    restructuring: float = 0.0
    other_losses_gains: float = 0.0
    earnings_from_investees: float = 0.0
    net_periodic_benefit: float = 0.0
    ebit: float = 0.0
    interest_expense_debt: float = 0.0
    interest_expense_leases: float = 0.0
    interest_expense: float = 0.0
    interest_income: float = 0.0
    loss_on_debt_extinguishment: float = 0.0
    other_financial_costs: float = 0.0
    ppe_disposal_gain: float = 0.0      # gain on PPE disposal → flows through EBT to balance BS
    ebt: float = 0.0
    tax_expense: float = 0.0
    net_income: float = 0.0
    eps_basic: float = 0.0
    eps_diluted: float = 0.0

    # BS — Current Assets
    cash: float = 0.0
    restricted_cash: float = 0.0
    accounts_receivable: float = 0.0
    receivables_related_parties: float = 0.0
    inventory: float = 0.0
    other_ca: float = 0.0
    total_ca: float = 0.0

    # BS — Non-Current Assets
    ppe_gross: float = 0.0
    ppe_accum_dep: float = 0.0
    ppe_net: float = 0.0
    ppe_net_ex_lease: float = 0.0
    finance_lease_asset: float = 0.0
    finance_lease_liab_current: float = 0.0
    finance_lease_liab_noncurrent: float = 0.0
    rou_asset: float = 0.0
    rou_finance: float = 0.0
    rou_operating: float = 0.0
    intangibles: float = 0.0
    goodwill: float = 0.0
    investments_lt: float = 0.0
    dta: float = 0.0
    other_nca: float = 0.0
    total_nca: float = 0.0
    total_assets: float = 0.0

    # BS — Current Liabilities
    short_term_debt: float = 0.0
    accounts_payable: float = 0.0
    accounts_payable_rp: float = 0.0
    payroll_payable: float = 0.0
    taxes_payable: float = 0.0
    interest_payable: float = 0.0
    lease_liab_current: float = 0.0
    lease_liab_cur_finance: float = 0.0
    lease_liab_cur_operating: float = 0.0
    other_cl: float = 0.0
    total_cl: float = 0.0

    # BS — Non-Current Liabilities
    long_term_debt: float = 0.0
    lease_liab_noncurrent: float = 0.0
    lease_liab_ncur_finance: float = 0.0
    lease_liab_ncur_operating: float = 0.0
    employee_benefits: float = 0.0
    dtl: float = 0.0
    other_ncl: float = 0.0
    total_ncl: float = 0.0
    total_liabilities: float = 0.0

    # BS — Equity
    share_capital: float = 0.0
    apic: float = 0.0
    treasury_stock: float = 0.0
    retained_earnings: float = 0.0
    aoci: float = 0.0
    nci: float = 0.0
    total_equity: float = 0.0
    total_liab_equity: float = 0.0

    # CF — CFO
    cfo_net_income: float = 0.0
    cfo_total_da: float = 0.0
    cfo_deferred_tax: float = 0.0
    cfo_change_ar: float = 0.0
    cfo_change_inv: float = 0.0
    cfo_change_ap: float = 0.0
    cfo_change_taxes_payable: float = 0.0
    cfo_change_interest_payable: float = 0.0
    cfo_change_other_wc: float = 0.0
    cfo_wc_delta: float = 0.0
    cfo_other: float = 0.0
    cfo_interest_paid: float = 0.0
    cfo_taxes_paid: float = 0.0
    cfo_lease_payments_operating: float = 0.0
    cfo_total: float = 0.0

    # CF — CFI
    cfi_capex: float = 0.0
    cfi_disposal_proceeds: float = 0.0
    cfi_acquisitions: float = 0.0
    cfi_other: float = 0.0
    cfi_total: float = 0.0

    # CF — CFF
    cff_debt_issuance: float = 0.0
    cff_debt_repayment: float = 0.0
    cff_revolver_draws: float = 0.0
    cff_revolver_repayments: float = 0.0
    cff_finance_lease_principal: float = 0.0
    cff_dividends: float = 0.0
    cff_buybacks: float = 0.0
    cff_share_buyback: float = 0.0   # alias for cff_buybacks (same value)
    cff_equity_issuance: float = 0.0
    cff_other: float = 0.0
    cff_total: float = 0.0

    # CF — Bridge
    cf_fx_effect: float = 0.0
    cf_net_change: float = 0.0
    cf_cash_opening: float = 0.0
    cf_cash_ending: float = 0.0

    # Internal: mutable state during solver iteration
    _cash_estimate: float = 0.0
    _actual_cfo_est: float = 0.0
    _fl_ncl_adj: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        """Конвертировать в плоский словарь для записи в БД."""
        from dataclasses import asdict
        return {k: v for k, v in asdict(self).items() if k != "year"}

    def bs_check(self) -> Tuple[float, float, float]:
        """
        Проверка BS Identity: Assets = Liabilities + Equity.
        Возвращает (total_assets, total_liab_equity, diff).
        """
        return self.total_assets, self.total_liab_equity, \
               abs(self.total_assets - self.total_liab_equity)

    def cf_bridge_check(self) -> Tuple[float, float, float]:
        """
        Проверка CF Bridge: cash_opening + net_change = cash_ending.
        Возвращает (expected, actual, diff).
        """
        expected = self.cf_cash_opening + self.cf_net_change
        return expected, self.cf_cash_ending, abs(expected - self.cf_cash_ending)


# ─── historic state ───────────────────────────────────────────────────────────

@dataclass
class HistoricState:
    """
    Исторические данные компании — всё что нужно ядру модели.
    Загружается из БД через ModelInputLoader.
    """
    company_id: str
    years: List[int]                        # все исторические годы
    base_year: int                          # последний исторический год

    # Исторические данные по годам {year: {metric: value}}
    is_data: Dict[int, Dict[str, float]] = field(default_factory=dict)
    bs_data: Dict[int, Dict[str, float]] = field(default_factory=dict)
    cf_data: Dict[int, Dict[str, float]] = field(default_factory=dict)

    # Препроцессор-метрики — драйверы прогноза
    preprocess: Dict[str, Dict] = field(default_factory=dict)
    # Структура: {group: {metric: value_or_{year:value}}}
    # Пример: preprocess["margin_ratios"]["cogs_ratio_recommended"] = 0.90

    # Долговые инструменты
    debt_instruments: List[DebtInstrument] = field(default_factory=list)
    debt_schedule: Dict[int, List[Dict]] = field(default_factory=dict)

    # Прогнозы макро-факторов {factor: {year: value}}
    macro_forecasts: Dict[str, Dict[int, float]] = field(default_factory=dict)

    # YearState базового года (последний исторический) — отправная точка
    base_year_state: Optional[YearState] = None

    def get_driver(self, group: str, metric: str, default=None):
        """Удобный доступ к рекомендованному значению драйвера."""
        return self.preprocess.get(group, {}).get(metric, default)

    def get_recommended(self, group: str, base_metric: str, default=None):
        """Получить _recommended значение для метрики."""
        return self.get_driver(group, f"{base_metric}_recommended", default)

    def is_val(self, year: int, metric: str) -> Optional[float]:
        return self.is_data.get(year, {}).get(metric)

    def bs_val(self, year: int, metric: str) -> Optional[float]:
        return self.bs_data.get(year, {}).get(metric)

    def cf_val(self, year: int, metric: str) -> Optional[float]:
        return self.cf_data.get(year, {}).get(metric)


# ─── model config ─────────────────────────────────────────────────────────────

@dataclass
class ModelConfig:
    """
    Конфигурация прогона модели.
    Загружается из project.yaml.
    """
    company_id: str
    scenario_name: str = "base"

    # Горизонт
    history_start_year: int = 2010
    history_end_year: int = 2024
    forecast_start_year: int = 2025
    forecast_end_year: int = 2029

    # Стандарт учёта
    accounting_standard: str = "US_GAAP"
    db_unit: str = "tUSD"

    # Drivers — переопределяют значения из препроцессора
    cogs_pct: Optional[float] = None          # если None — из preprocess
    sga_pct: Optional[float] = None
    capex_pct: Optional[float] = None
    capex_pct_by_year: Optional[Dict[int, float]] = None  # year-specific overrides
    min_capex_da_ratio: float = 0.90  # CapEx/DA floor — maintenance of existing asset base
    sustaining_capex_da_ratio: float = 0.0  # sustaining CapEx = ratio × DA (0=use min_capex_da_ratio)
    expansion_capex_pct_of_rev_growth: float = 0.0  # growth capex = pct × revenue growth
    additional_capex_schedule: Dict[int, float] = field(default_factory=dict)  # {year: $}
    dep_rate: Optional[float] = None
    accel_dep_excess_pct: float = 0.0  # % of book dep by which tax dep exceeds book dep (generates DTL)
    dep_to_rev: Optional[float] = None   # D&A как % от Revenue (альтернатива dep_rate)
    dso_days: Optional[float] = None
    dih_days: Optional[float] = None
    dpo_days: Optional[float] = None
    tax_rate: Optional[float] = None
    cash_rate: float = 0.02
    dividend_payout: float = 0.0
    buyback_pct_fcf: float = 0.0      # pct of prior-year FCF used for share buybacks
    buyback_leverage_max: float = 2.0  # buybacks only when ND/EBITDA < this threshold
    equity_additional_events: Dict[int, Dict[str, float]] = field(default_factory=dict)  # {year: {issuance/buyback/dividends: $}}
    min_cash: float = 0.0
    # Debt floor — компания не гасит долг ниже этого уровня
    target_net_debt_ebitda: float = 0.0     # 0 = no floor; e.g. 1.5 = keep ND >= 1.5×EBITDA
    max_voluntary_prepay_pct_fcf: float = 1.0  # cap on voluntary prepay as fraction of FCF (1.0 = no cap)
    # Growth capex: при росте Revenue компания инвестирует в capacity
    expansion_capex_pct_of_rev_growth: float = 0.0  # $ capex на $1 роста Revenue

    # Методы прогнозирования (из forecast_methods в project.yaml)
    forecast_methods: Dict[str, Dict[str, ForecastMethodConfig]] = \
        field(default_factory=dict)
    # Структура: {"IS": {"revenue": ForecastMethodConfig(method=MACRO, ...)}}

    # Долг
    debt: DebtSettings = field(default_factory=DebtSettings)

    # Лизинг — opening balances (legacy) + EWA-calibrated corkscrew params
    leases: LeaseDrivers = field(default_factory=LeaseDrivers)
    lease:  LeaseParams  = field(default_factory=LeaseParams)

    # Solver параметры (joint iteration, аналог Excel Iterative Calculation)
    max_iter: int   = 10      # максимум итераций joint solver
    tol:      float = 1000.0  # допуск сходимости ($1K)

    # Feature flags
    use_ppe_corkscrew: bool = True
    use_wc_days: bool = True
    use_debt_rc: bool = True
    use_intangibles_corkscrew: bool = True
    use_tax_corkscrew: bool = True
    use_interest_payable_cork: bool = True

    # Covenant acceleration (covenant breach → callable debt reclassified to ST)
    covenants_enabled: bool = False
    covenant_acceleration_triggers: List[str] = field(
        default_factory=lambda: ['interest_coverage', 'net_debt_ebitda']
    )
    # NOL / Tax config (used by TaxBlock)
    nol_opening_balance: float = 0.0
    nol_max_utilization_pct: float = 0.80
    tax_paid_timing: str = "next_year"  # "current_year" | "next_year"
    interest_payable_payment_timing: str = "next_year"  # "current_year" | "next_year"

    # Accounting conventions (from project.yaml accounting_conventions section)
    da_in_cogs: bool = True
    capitalize_interest: bool = False
    # Знаковая конвенция IS income items ниже EBIT
    #   "credit_negative" — доход как отрицательное (US GAAP / US Steel default)
    #   "natural"         — доход как положительное (IFRS / RUSAL)
    is_income_sign: str = "credit_negative"

    # Intangibles config (from YAML custom.intangibles)
    intang_amort_rate: Optional[float] = None       # Override for amortization rate
    intang_additions_pct_rev: float = 0.0            # Additions as % of revenue

    # SGA split config (from YAML custom.sga)
    sga_split_enabled: bool = False
    sga_distribution_pct_rev: Optional[float] = None
    sga_admin_pct_rev: Optional[float] = None
    sga_ecl_pct_rev: Optional[float] = None
    sga_other_opex_pct_rev: Optional[float] = None

    # Provisions corkscrew config
    provisions_corkscrew_enabled: bool = False

    # Deferred tax categories config
    deferred_tax_categories: Optional[Dict] = None

    # Finance lease initial liability (fallback for overlay in core.py)
    finance_lease_liab_initial: float = 0.0

    # Macro factor configuration (from YAML, used by blocks instead of re-reading YAML)
    revenue_macro_factor: Optional[str] = None
    cogs_revenue_factor: Optional[str] = None
    cogs_cost_factor: Optional[str] = None

    # Internal: populated by ModelInputLoader
    _segment_model: Optional[Dict[int, float]] = None

    @property
    def nol_enabled(self) -> bool:
        """True if NOL carryforward is active (opening balance > 0)."""
        return self.nol_opening_balance > 0

    @property
    def nol_limit_pct(self) -> float:
        """TCJA NOL limit as pct of taxable income (alias for nol_max_utilization_pct)."""
        return self.nol_max_utilization_pct

    @property
    def statutory_rate(self) -> float:
        """Statutory tax rate (alias for tax_rate with fallback from constants)."""
        from engine.constants import TAX_STATUTORY_RATE_DEFAULT
        return self.tax_rate or TAX_STATUTORY_RATE_DEFAULT

    @property
    def dividend_pct_ni(self) -> float:
        """Dividend payout as pct of NI (alias for dividend_payout)."""
        return self.dividend_payout

    @property
    def forecast_years(self) -> List[int]:
        return list(range(self.forecast_start_year, self.forecast_end_year + 1))

    @property
    def all_years(self) -> List[int]:
        return list(range(self.history_start_year, self.forecast_end_year + 1))

    def get_forecast_method(
        self, statement: str, metric: str
    ) -> Optional[ForecastMethodConfig]:
        return self.forecast_methods.get(statement.upper(), {}).get(metric)
