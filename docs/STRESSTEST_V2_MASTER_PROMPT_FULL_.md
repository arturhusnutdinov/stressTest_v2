# stressTest Engine v2 — Полный мастер-промпт

---
## UPDATE [2026-04-03] — ARCHITECTURAL FIX + RUSAL MODEL

### Parameter Loading Principle (FIXED)
```
YAML = policy only (targets, covenants, NOL, dividends)
Preprocessor → DB → Loader → ModelConfig (all numerical params)
Priority: YAML override → preprocess_recommended → ValueError
```

### Preprocessor Parameters
| Param | US Steel | Rusal |
|---|---|---|
| Avg rate | 0.0417 | 0.0933 |
| COGS ratio | 0.8550 | 0.7412 |
| DIH | 54.7384 | 138.0956 |
| DPO | 66.4406 | 60.2690 |
| DSO | 36.1700 | 38.1591 |
| Dep rate | 0.0993 | 0.0994 |
| Revenue beta | 1.6021 | 0.7227 |

### Model Results

**US Steel** (BS=0):
| Year | Rev$B | EBITDA% | NI$M | ND/EB |
|---|---|---|---|---|
| 2025 | 14.28 | 12.7% | 963 | 1.4x |
| 2026 | 13.22 | 12.6% | 705 | 1.0x |
| 2027 | 12.39 | 12.5% | 578 | 0.7x |
| 2028 | 11.72 | 12.4% | 520 | 0.3x |
| 2029 | 11.17 | 12.3% | 476 | -0.0x |

**Rusal** (BS=6137774):
| Year | Rev$B | EBITDA% | NI$M | ND/EB |
|---|---|---|---|---|
| 2025 | 13.88 | 17.5% | -23 | 2.3x |
| 2026 | 14.58 | 17.5% | 30 | 2.6x |
| 2027 | 15.17 | 17.5% | 106 | 2.8x |
| 2028 | 15.61 | 17.5% | 136 | 3.0x |
| 2029 | 15.66 | 17.5% | 97 | 3.2x |

### Changes This Session
- Removed 9 YAML hardcodes (tax_rate, WC days, avg_rate) → preprocessor only
- Revenue beta: lme_aluminium for Rusal (OLS β=0.78, R²=0.47)
- Macro forecasts: 8 factors × 5 years for Rusal
- Associates (Norilsk): EWA halflife=4 → ~$926M
- Debt rates: floating KeyRate separated from spread

### TODO
1. Dynamic EBITDA margin (cogs_macro_beta in core.py)
2. Floating rate = spread + CBR key rate
3. Segmented revenue (Volume × Price)
4. BS diff Rusal $6M (debt timing)

---

## КРИТИЧЕСКИ ВАЖНО: Рабочие папки

```
РАБОЧИЙ ПРОЕКТ:  /Users/arturhusnutdinov/Documents/IT Development/Docker/stressTest_v2
ПАПКА-ДОНОР:     /Users/arturhusnutdinov/Documents/IT Development/Docker/stressTest
```

**Все команды выполнять ТОЛЬКО в `stressTest_v2`. `stressTest` — источник для изучения, НИКОГДА не модифицировать.**

**Главная ошибка прошлых сессий:** Claude Code работал в `stressTest` вместо `stressTest_v2`. При старте ВСЕГДА проверять:
```python
from engine import ROOT, DB_PATH
assert str(ROOT).endswith('stressTest_v2'), f'WRONG ROOT: {ROOT}'
assert 'v3' not in str(DB_PATH), f'WRONG DB: {DB_PATH}'
```

---

## 1. Архитектура и структура проекта

### 1.1 Полная структура `stressTest_v2/`

```
stressTest_v2/
├── engine/
│   ├── __init__.py               ← ROOT = динамический поиск (НЕ hardcode parents[N])
│   ├── orchestrator.py           ← build_model() — единая точка входа
│   ├── model/
│   │   ├── core.py               ← ThreeStatementModel
│   │   ├── inputs.py             ← YearState(108 полей), HistoricState, ModelConfig, LeaseParams
│   │   ├── loader.py             ← ModelInputLoader
│   │   ├── saver.py              ← ModelSaver
│   │   ├── revenue_models.py     ← ols_single_factor, ols_multi_factor, ewa_with_clamp
│   │   └── schedules/
│   │       ├── debt.py           ← DebtOptimizer + DebtBlock
│   │       ├── tax.py            ← TaxBlock (current + deferred + NOL + DTA/DTL)
│   │       ├── wc.py             ← WCBlock (6 параллельных corkscrew)
│   │       ├── ppe.py            ← PPEBlock (gross/accum/net)
│   │       ├── lease.py          ← FinanceLeaseBlock + OperatingLeaseUSGAAP + OperatingLeaseIFRS16
│   │       ├── equity.py         ← EquityBlock
│   │       ├── interest_payable.py ← InterestPayableBlock
│   │       └── intangibles.py    ← IntangiblesBlock
│   ├── preprocessor/core.py      ← ModelPreprocessor (13 групп)
│   ├── macro/
│   │   ├── runner.py             ← run_macro() — 3 потока (VECM + MR + EWA)
│   │   ├── vecm_bridge.py        ← подключение engine/ecm к Repository
│   │   ├── commodity_models.py   ← MeanReversion + RWDrift
│   │   └── db_adapter.py         ← MacroDBAdapter
│   ├── stress/
│   │   ├── core.py               ← ScenarioLoader, ShockSpec, StressScenario
│   │   └── runner.py             ← StressRunner
│   ├── rating/
│   │   ├── core.py               ← CreditMetrics, RatingEngine
│   │   └── runner.py             ← RatingRunner
│   ├── covenants/core.py         ← CovenantsChecker, CovenantSpec
│   ├── loader/
│   │   ├── base.py               ← BaseLoader, FormulaEngine, MappingConfig
│   │   └── excel.py              ← ExcelLoader
│   └── database/
│       ├── repository.py         ← Repository (единственный доступ к БД, UPSERT везде)
│       └── schema.py             ← 36 таблиц
├── companies/us_steel/
│   ├── configs/
│   │   ├── project.yaml
│   │   ├── macro_ecm.yaml
│   │   ├── stress_scenarios.yaml
│   │   └── covenants.yaml
│   ├── data/us_steel_data_export_v2.xlsx
│   └── notebooks/
├── notebooks/                    ← 00_Build_Model_Main.ipynb, 99_Configure_YAML.ipynb
├── templates/                    ← шаблоны для новых компаний
├── tools/
│   ├── init_company.py           ← создание структуры новой компании
│   └── migrate_from_v1.py
├── data_mart_v2.db               ← SQLite (НЕ v3!)
└── requirements.txt
```

### 1.2 engine/__init__.py — динамический ROOT

```python
def _find_root() -> Path:
    env_root = os.environ.get('STRESSTEST_ROOT')
    if env_root:
        return Path(env_root)
    current = Path(__file__).parent
    for _ in range(5):
        current = current.parent
        if (current / 'data_mart_v2.db').exists():
            return current
        if (current / 'README.md').exists() and (current / 'engine').exists():
            return current
    return Path(__file__).parent.parent

ROOT = _find_root()
DB_PATH = ROOT / 'data_mart_v2.db'
```

**ЗАПРЕЩЕНО:** `Path(__file__).parents[N]` с фиксированным N.

---

## 2. Ключевые принципы (нарушение = баг)

### 2.1 Нет plugов

- `cfo_other` НЕ должен быть > $50M
- `cash = prev_cash + CFO + CFI + CFF` — CF управляет cash, не BS plug
- BS балансирует через точные corkscrews

### 2.2 Балансовые тождества

```
BS Identity:   Total Assets = Total Liabilities + Total Equity  → diff = 0.000
CF Bridge:     Cash_open + CFO + CFI + CFF = Cash_close         → diff = 0.000
```

Допустимое отклонение: < $1 (floating point). Любое > $1 = баг.

### 2.3 Joint Iteration Solver (max_iter=10, tol=$1K)

```python
for iteration in range(max_iter):
    state = _solve_debt(state, prev)
    state = _solve_interest_payable(state, prev)
    state = _solve_is_subtotals(state)
    state = _solve_tax_block(state, prev)    # TaxBlock
    state = _solve_equity(state, prev)
    state = _solve_cf(state, prev)
    state = _solve_cash_from_cf(state, prev)  # cash из CF bridge
    state = _solve_bs_totals(state)
    if |cash_delta| < tol and |ni_delta| < tol:
        break
```

### 2.4 Standard vs Custom mode

**Standard mode** (упрощённые % методы):
- D&A = Revenue × dep_to_rev (~5.8%)
- WC = NWC/Revenue ratio (~8%)
- Tax = EBT × effective_rate
- Debt = parametric (target Net Debt/EBITDA)
- PPE = простой net corkscrew

**Custom mode** (полные corkscrew расписания):
- PPEBlock, WCBlock (DSO/DIH/DPO), TaxBlock (DTA/DTL/NOL)
- LeaseBlock (ASC 842 / IFRS 16), DebtOptimizer (per-instrument)

**Автодетект в Custom mode (graceful degradation):**
```python
use_ppe_corkscrew = ppe_gross + ppe_accum_dep за 3+ лет в БД
use_wc_days       = AR + Inv + AP за 3+ лет в БД
use_tax_corkscrew = DTA или DTL есть в БД
```

Приоритет: `features: в YAML` > `автодетект` > `mode-based дефолт`

---

## 3. IS → BS → CF маршрутизация

### 3.1 Income Statement

| Строка | YearState | Метод |
|---|---|---|
| Revenue | `revenue` | OLS: dln(Rev) ~ dln(HRC), beta=1.13, R²=0.858 |
| COGS (excl D&A) | `cogs` | DRIVER: cogs_pct × Rev (~0.845) |
| SG&A | `sga` | DRIVER: sga_pct × Rev |
| D&A | `total_da` | CORK: dep_ppe + dep_rou + amort |
| EBITDA | `ebitda` | CALC: gross_profit + sga + earnings_investees |
| EBIT | `ebit` | CALC: ebitda - total_da |
| Interest expense | `interest_expense` | CORK: Debt × rate (ПОСЛЕ cap-интереса) |
| EBT | `ebt` | CALC |
| Tax | `tax_expense` | CORK: TaxBlock |
| NI | `net_income` | CALC |

**US GAAP: da_in_cogs = False** — D&A отдельная строка, НЕ в COGS.

### 3.2 Правило знаков для liabilities в CF

```python
# НЕВЕРНО:
delta = taxes_payable - prev.taxes_payable

# ВЕРНО (liability хранится отрицательной):
delta = abs(taxes_payable) - abs(prev.taxes_payable)
```

---

## 4. Моделирование долга

### 4.1 Типы инструментов

| db_type | Логика | CF |
|---|---|---|
| `revolving` | RC: draw/repay, always ST | cff_revolver |
| `term_amort` | равномерная амортизация | cff_debt_repayment |
| `bond_fixed/float` | bullet при maturity | cff_debt_repayment |
| `finance_lease` | исключается из DebtOptimizer | cff_finance_lease_principal |

### 4.2 DebtOptimizer — 7 шагов

```
ШАГ 0: Mandatory = amort_schedule[year] или full при maturity
ШАГ 1: Рефинансирование (simple: продлить maturity +5л / new: новый инструмент)
ШАГ 2: pre-fin cash = opening_cash + cfo + cfi - mandatory - fees
ШАГ 3: Draw (RC первым, потом LT по priority/rate)
ШАГ 4: Repay surplus (RC первым)
ШАГ 5: Interest = avg(open_after_refi, closing) × rate
ШАГ 6: ST/LT split (4 правила ниже)
ШАГ 7: CFF = draws - repays - fees
```

**4 правила ST/LT:**
```python
if inst.is_revolving: is_st = True                        # Rule 1: RC всегда ST
elif inst.maturity == year + 1: is_st = True              # Rule 2: погашается в след году
elif inst.amort_schedule.get(year+1, 0) > 0: split ST/LT  # Rule 3: amortization
elif inst.callable + covenant_breach: is_st = True         # Rule 4: acceleration
```

### 4.3 Capitalized interest (ASC 835-20)

```python
cap_pct = preprocessor['cap_interest_pct_recommended']  # EWA = 37.75% для US Steel
gross_interest = avg_debt × avg_gross_rate
state.interest_expense = gross_interest × (1 - cap_pct)  # в IS
capitalized = gross_interest × cap_pct                    # в PPE gross
# US Steel 2024 факт: gross=$237M, cap=$213M (91%), net_IS=$24M
```

### 4.4 Parametric mode (Standard) — ST/LT

```python
# Целевой долг:
target_total = net_debt_ebitda_target × ebitda  # приоритет
           или target_pct_revenue × revenue     # fallback

# ST = mandatory amortization + RC
hist_st_ratio = EWA(st_debt / total_debt)  # clamp 5%-40%
mandatory_st = long_term_debt × hist_st_ratio × 0.5
st_debt = mandatory_st + rc_draw - rc_repay
lt_debt = target_total - st_debt

# Рефинанс риск:
if short_term_debt > 0 and fcf < short_term_debt × 0.5:
    logger.warning("REFIN RISK: FCF/ST < 0.5x")
```

---

## 5. TaxBlock — полная реализация

```python
@dataclass
class TaxBlock:
    ebt:                float = 0.0
    statutory_rate:     float = 0.21
    nol_open:           float = 0.0        # US Steel: $1,014M federal
    nol_max_util_pct:   float = 0.80       # TCJA 2017
    dta_open:           float = 0.0
    dtl_open:           float = 0.0
    temp_diff_delta:    float = 0.0        # Δtemp diff
    taxes_payable_open: float = 0.0
    tax_paid_timing:    str = "current_year"

    def solve(self) -> "TaxBlock":
        # 1. NOL utilization (до 80% taxable, indefinite carryforward)
        nol_used = min(self.nol_open * self.nol_max_util_pct, max(self.ebt, 0))
        self.nol_used = nol_used
        self.nol_close = self.nol_open - nol_used + max(0, -self.ebt)

        # 2. Taxable income
        self.taxable_income = max(0.0, self.ebt - nol_used)

        # 3. Current tax
        self.current_tax = -self.taxable_income * self.statutory_rate

        # 4. Deferred tax
        # ФОРМУЛА: deferred_tax = ΔDTL - ΔDTA → CFO add-back
        self.deferred_tax = -self.temp_diff_delta * self.statutory_rate

        # 5. Total
        self.total_tax = self.current_tax + self.deferred_tax
        self.effective_rate = abs(self.total_tax) / self.ebt if self.ebt > 0 else 0

        # 6. DTA/DTL closing corkscrews
        self.dta_close = max(0.0, self.dta_open + self.temp_diff_delta)
        self.dtl_close = max(0.0, self.dtl_open - self.temp_diff_delta)

        # 7. Taxes payable corkscrew
        if self.tax_paid_timing == "current_year":
            self.taxes_payable_close = 0.0
            self.taxes_paid_cf = abs(self.current_tax)
        else:  # next_year
            self.taxes_payable_close = abs(self.current_tax)
            self.taxes_paid_cf = self.taxes_payable_open
        return self
```

**CF routing:**
```python
state.tax_expense      = block.total_tax          # IS
state.dta              = block.dta_close           # BS asset (+)
state.dtl              = -block.dtl_close          # BS liability (-)!
state.taxes_payable    = block.taxes_payable_close
state.cfo_taxes_paid   = block.taxes_paid_cf       # CF supplemental
state.cfo_deferred_tax = block.deferred_tax        # CFO add-back
```

**NOL US Steel:** $1,014M federal (indefinite) → 2025 eff rate = 4.2% вместо 21%.

---

## 6. LeaseBlock — полная реализация (ASC 842 / IFRS 16)

### 6.1 Ключевые различия

| | US GAAP (ASC 842) | IFRS 16 |
|---|---|---|
| Operating IS | `lease_expense` единая строка (в SGA!) | dep + interest раздельно |
| Operating CF | ВЕСЬ платёж → CFO | interest → CFO, principal → CFF |
| Finance IS | dep + interest раздельно | dep + interest раздельно |
| Finance CF | interest → CFO, principal → CFF | то же |

### 6.2 FinanceLeaseBlock (одинаково для обоих стандартов)

```python
@dataclass
class FinanceLeaseBlock:
    rou_open: float = 0.0
    liab_open: float = 0.0
    dep_rate: float = 0.15      # ~6-7 лет
    discount_rate: float = 0.05

    def solve(self):
        self.rou_dep = self.rou_open * self.dep_rate
        self.interest_exp = self.liab_open * self.discount_rate
        self.total_payment = self.liab_open * (self.dep_rate + self.discount_rate)
        self.principal_pmt = max(0, self.total_payment - self.interest_exp)
        self.rou_close = max(0, self.rou_open + self.rou_additions - self.rou_dep)
        self.liab_close = max(0, self.liab_open + self.liab_additions - self.principal_pmt)
        # Текущая / долгосрочная части
        next_yr_principal = self.liab_close * self.dep_rate
        self.liab_current = min(next_yr_principal, self.liab_close)
        self.liab_noncurrent = max(0, self.liab_close - self.liab_current)
```

### 6.3 OperatingLeaseUSGAAP (ASC 842)

```python
@dataclass
class OperatingLeaseUSGAAP:
    """
    IS:  lease_expense единая строка (уже в SGA — НЕ добавлять в total_da!)
    BS:  ROU asset + lease liability
    CF:  ВЕСЬ платёж → CFO (не разделяется!)
    """
    def solve(self):
        # Единая строка lease_expense = interest + dep (неразличимые)
        self.lease_expense = self.liab_open * (self.dep_rate + self.discount_rate)
        self.interest_component = self.liab_open * self.discount_rate
        self.rou_amort = max(0, self.lease_expense - self.interest_component)
        
        # ВЕСЬ платёж в CFO
        self.payment_cfo = self.lease_expense
        
        principal = max(0, self.lease_expense - self.interest_component)
        self.liab_close = max(0, self.liab_open + self.liab_additions - principal)
        self.rou_close = max(0, self.rou_open + self.rou_additions - self.rou_amort)
        # Текущая / долгосрочная части
        next_yr_principal = self.liab_close * self.dep_rate
        self.liab_current = min(next_yr_principal, self.liab_close)
        self.liab_noncurrent = max(0, self.liab_close - self.liab_current)
```

### 6.4 OperatingLeaseIFRS16

```python
@dataclass
class OperatingLeaseIFRS16:
    """
    IFRS 16: ВСЕ договоры как finance-подобные.
    IS:  dep_charge (в total_da!) + interest_exp (отдельно)
    CF:  interest → CFO, principal → CFF (не как US GAAP!)
    Исключения short-term/low-value: lease_expense → IS, payment → CFO.
    """
    exemption_pct: float = 0.0

    def solve(self):
        rou_main = self.rou_open * (1 - self.exemption_pct)
        liab_main = self.liab_open * (1 - self.exemption_pct)
        
        self.dep_charge = rou_main * self.dep_rate      # В total_da!
        self.interest_exp = liab_main * self.discount_rate  # В IS отдельно!
        
        total_pmt = liab_main * (self.dep_rate + self.discount_rate)
        self.principal_pmt = max(0, total_pmt - self.interest_exp)
        
        self.interest_paid_cfo = self.interest_exp    # → CFO
        # principal_pmt → CFF (отличие от US GAAP!)
        
        self.exemption_expense = (
            self.liab_open * self.exemption_pct * (self.dep_rate + self.discount_rate)
        )
        self.rou_close = max(0, self.rou_open + self.rou_additions - self.dep_charge)
        self.liab_close = max(0, self.liab_open + self.liab_additions - self.principal_pmt)
```

### 6.5 LeaseBlock — агрегатор (выбор стандарта)

```python
@dataclass
class LeaseBlock:
    accounting_standard: str = "US_GAAP"   # US_GAAP | IFRS
    finance: FinanceLeaseBlock = None
    operating_gaap: OperatingLeaseUSGAAP = None
    operating_ifrs: OperatingLeaseIFRS16 = None

    @property
    def dep_rou(self) -> float:
        """Амортизация ROU в total_da."""
        total = 0.0
        if self.finance:
            total += self.finance.rou_dep or 0
        # US GAAP operating: НЕ в dep (в SGA!)
        # IFRS operating: В dep!
        if self.operating_ifrs:
            total += self.operating_ifrs.dep_charge or 0
        return total

    @property
    def interest_expense_leases(self) -> float:
        """Процентные расходы в IS."""
        total = 0.0
        if self.finance:
            total += self.finance.interest_exp or 0
        # US GAAP operating: нет отдельной строки (в lease_expense)
        # IFRS operating: отдельная строка!
        if self.operating_ifrs:
            total += self.operating_ifrs.interest_exp or 0
        return total

    @property
    def payments_cfo(self) -> float:
        """Платежи в CFO."""
        total = 0.0
        if self.finance:
            total += self.finance.interest_exp or 0      # только interest
        if self.operating_gaap:
            total += self.operating_gaap.payment_cfo or 0  # ВЕСЬ платёж!
        if self.operating_ifrs:
            total += self.operating_ifrs.interest_paid_cfo or 0  # только interest
        return total

    @property
    def payments_cff(self) -> float:
        """Платежи в CFF."""
        total = 0.0
        if self.finance:
            total += self.finance.principal_pmt or 0
        # US GAAP operating: НИЧЕГО в CFF
        if self.operating_ifrs:
            total += self.operating_ifrs.principal_pmt or 0  # IFRS: principal в CFF!
        return total
```

### 6.6 CF routing из LeaseBlock

```python
state.dep_rou                     = block.dep_rou
state.total_da                    = state.dep_ppe + state.dep_rou + state.amort_intangibles
state.interest_expense_leases     = block.interest_expense_leases
state.cfo_lease_payments_operating = -block.payments_cfo   # CFO outflow
state.cff_finance_lease_principal  = -block.payments_cff   # CFF outflow
```

### 6.7 КРИТИЧНО для US GAAP Operating Lease

```
✗ НЕ добавлять ROU op amortization в total_da add-back!
   (она уже включена в SGA/lease_expense, которая снижает NI)
✗ НЕ включать ΔLL в CFO WC delta!
✓ lease_expense уже в SGA → автоматически в NI → CFO
```

### 6.8 Параметры из препроцессора

```python
# _process_lease() через EWA из истории:
op_decay_rate = (ROU_open + new_op - ROU_close) / ROU_open
op_new_leases = CF.rou_assets_from_op_leases    # EWA
fin_principal_rate = principal / LL_open         # EWA
fin_amort_rate = amort / asset_open              # EWA
fin_interest_rate = interest / LL_avg            # EWA
```

### 6.9 Данные US Steel 2024

```
Operating lease: ROU=$72M, liab_curr=$35M, liab_NC=$44M, cash_cfo=$47M
Finance lease:   asset_net=$198M, liab_curr=$58M, liab_NC=$151M, principal_cff=$49M
```

---

## 7. WCBlock — 6 параллельных corkscrew

```python
@dataclass
class WCBlock:
    # AR: ar_open, ar_additions=revenue, ar_collections, ar_close
    # Inv: inventory_open, inv_purchases, inv_cogs, inventory_close
    # AP: ap_open, ap_purchases, ap_payments, ap_close
    # OtherCA: other_ca_open ... other_ca_close
    # Accrued: accrued_open ... accrued_close
    # OtherCL: other_cl_open ... other_cl_close

    def get_wc_delta(self) -> float:
        """Рост актива = отток кэша (−), рост пассива = приток (+)."""
        return (
            -(self.ar_close       - self.ar_open)
            -(self.inventory_close - self.inventory_open)
            +(self.ap_close        - self.ap_open)
            -(self.other_ca_close  - self.other_ca_open)
            +(self.accrued_close   - self.accrued_open)
            +(self.other_cl_close  - self.other_cl_open)
        )
```

**Dynamic WC days (цикличность):**
```python
adj_dso = max(0.80, min(1.20, 1.0 + 0.3 × (-rev_growth)))  # спад → DSO растёт
adj_dih = max(0.80, min(1.20, 1.0 + 0.4 × (-rev_growth)))
adj_dpo = max(0.80, min(1.20, 1.0 + 0.2 ×  rev_growth))   # спад → DPO снижается
```

**US Steel 2024:** DSO=32.6д, DIH=56.3д, DPO=71.3д.

---

## 8. PPEBlock

```python
@dataclass
class PPEBlock:
    gross_open, gross_capex, gross_disposals = 0, 0, 0
    accdep_open, dep_charge, dep_on_disposals = 0, 0, 0

    def solve(self):
        self.gross_close = gross_open + gross_capex - gross_disposals
        self.accdep_close = accdep_open + dep_charge - dep_on_disposals
        self.net_close = gross_close - accdep_close
        self.gain_loss = disposal_proceeds - (gross_disposals - dep_on_disposals)

    @classmethod
    def from_prev_state(cls, prev, dep_rate, capex, ...):
        # dep_rate × avg(net_PPE) — правильная практика
        avg_net = (prev.ppe_net + ...) / 2
        dep_charge = dep_rate * avg_net
```

**CapEx логика:**
```python
base_capex    = revenue × capex_pct
floor_capex   = dep_ppe × min_capex_da_ratio   # floor = 0.90 × DA
project_capex = additional_capex_schedule.get(year, 0)
total_capex   = max(base_capex, floor_capex) + project_capex
```

---

## 9. EquityBlock

```python
@dataclass
class EquityBlock:
    def solve(self):
        self.re_close = re_open + net_income + dividends  # dividends < 0
        self.treasury_close = treasury_open + buybacks    # buybacks < 0
        self.total_equity_close = (
            share_cap_close + apic_close
            - abs(treasury_close)   # treasury_stock NEGATIVE
            + re_close + aoci_close
        )
```

---

## 10. Препроцессор (13 групп)

| Группа | Ключевые метрики |
|---|---|
| margin_ratios | cogs_ratio_ex_da=0.845, sga_ratio, ebitda_margin, tax_rate |
| wc_days | dso=32.6д, dih=56.3д, dpo=71.3д, nwc_to_revenue |
| capex | capex_to_rev, dep_to_rev, cap_interest_pct=37.75% |
| debt | avg_interest_rate, nd_ebitda, icr, st_debt_ratio=2.5% |
| interest | interest_income_rate, accrual_ratio |
| equity | dividend_payout, buyback_ratio, roe |
| extended | earnings_investees EWA, net_periodic_benefit EWA |
| beta_coefficients | steel_hrc_beta=-0.471 (R²=0.923) |
| revenue_betas | rev_beta_hrc=1.13 (R²=0.858) |
| lease | op_decay_rate, fin_principal_rate EWA |

**EWA:**
```python
alpha = 1.0 - math.exp(-math.log(2) / halflife_years)
result = series[0]
for v in series[1:]:
    result = alpha * v + (1-alpha) * result
```

---

## 11. Макро-модуль — три потока

### 11.1 Архитектура по типу фактора

```
Поток 1: VECM (statsmodels) → GDP, CPI, industrial_production
         Группы по 3 фактора (Йохансен max ~12)
         
Поток 2: Mean Reversion → commodity (HRC, SPPI, brent, coal, iron_ore)
         kappa зависит от сценария:
           base = 0.15  (медленная нормализация)
           bear = 0.5   (быстрый возврат к медиане)
           bull = RWDrift P50-P95

Поток 3: EWA (halflife=5) → прочие факторы
```

### 11.2 Mean Reversion (O-U)

```python
def mean_reversion_forecast(history, forecast_years=5, long_run_mean=None, kappa=0.15):
    """
    ln P(t+1) = ln P(t) + kappa × (ln mu - ln P(t))
    
    US Steel HRC: медиана $698 (2010-2024), последнее $923 (2024)
    kappa=0.15: base, kappa=0.5: bear, RWDrift: bull
    """
```

### 11.3 Двухфакторная модель COGS

```
Revenue factor (HRC): ОБРАТНАЯ связь, beta=-0.471 (R²=0.923)
  Рост HRC → Revenue растёт быстрее затрат → COGS% ПАДАЕТ

Cost factor (SPPI): ПРЯМАЯ связь, beta=+0.202
  Рост SPPI → затраты → COGS% РАСТЁТ

2-факторный R²=0.932
```

### 11.4 Revenue-COGS консистентность

```python
# Revenue OLS: dln(Revenue) = alpha + 1.13 × dln(HRC)
# Revenue и COGS используют ОДИН фактор HRC → автоматически консистентно!

state.revenue = prev.revenue × exp(alpha + beta × dln(HRC))
# COGS = Revenue × ratio → следует за Revenue
```

---

## 12. Стресс-тестирование

### 12.1 Типы шоков

```python
class ShockSpec:
    shock_type: str
    # "percentage": base × (1 + value/100)
    # "absolute":   base + value
    # "basis_points": base + value/10000   (100bp = 1%)
    # "pp":           base + value/100     (2pp = +0.02)
```

### 12.2 Встроенные сценарии

```python
BUILTINS = {
    "steel_downturn":  HRC -25%, SPPI -15%, brent -20%, capex -30%,
    "rate_spike":      avg_rate +2pp (200bp),
    "wc_stress":       DSO +30%, DIH +20%, DPO -15%, avg_rate +2pp,
    "combined_stress": steel_downturn + wc_stress,
}
# + extends + sector_packs
```

### 12.3 Применение шоков

```python
# macro_shocks → модифицируем macro_forecasts в deepcopy(historic)
# driver_shocks → модифицируем ModelConfig deepcopy
# rate шоки → обновляем inst.interest_rate для schedule-based долга!
```

---

## 13. Рейтинговый модуль

```python
# Скоринг 0-100 → SP шкала
weights = {leverage: 0.30, coverage: 0.30, profitability: 0.25, liquidity: 0.15}

# Пороги leverage:
# Net Debt/EBITDA < 0 → 95  |  < 1.5 → 78  |  < 3 → 62  |  < 4.5 → 30  |  > 6 → 5

# Из project.yaml:
rating:
  methodology: sp   # sp | moodys | fitch | internal
  weights: ...
```

---

## 14. Ковенанты

### 14.1 STEEL_COVENANTS

| Ковенант | Лимит | Буфер |
|---|---|---|
| Net Debt/EBITDA | ≤ 3.5x | 10% |
| ICR (EBIT/Int) | ≥ 2.5x | 15% |
| EBITDA Margin | ≥ 5% | 20% |
| Current Ratio | ≥ 1.0x | 10% |
| FCF/Debt | ≥ -10% | 0% |

### 14.2 Из project.yaml

```yaml
covenants:
  enabled: true
  methodology: steel    # steel → 5 стальных ковенантов
  warning_buffer: 0.10
  thresholds:
    net_debt_ebitda_max: 3.5
    interest_coverage_min: 2.5
    ebitda_margin_min: 0.05
    current_ratio_min: 1.0

# CovenantsChecker.from_project_yaml(company_id, repo, company_dir) — читает автоматически
```

---

## 15. База данных (data_mart_v2.db, 36 таблиц)

```python
# Единый Repository:
with Repository(db_path='data_mart_v2.db') as repo:
    repo.upsert_history(company_id, 'IS', year, {metric: value})
    repo.upsert_preprocess(company_id, group, {metric: value_or_series})
    repo.upsert_macro_factors({factor: {year: value}})
    repo.upsert_forecast(company_id, 'IS', year, scenario_id, metrics)
```

### 15.1 Данные US Steel в БД

```
history_is: interest_incurred, interest_capitalized (Note 7)
            finance_lease_interest, finance_lease_amort (Note 24)
history_bs: ppe_gross, ppe_accum_dep
            rou_asset, lease_liab_current/noncurrent
            finance_lease_asset_net, fin_lease_liab_curr/noncurrent
            dta (dta_federal_nol=$213M, valuation_allowance=$149M)
            dtl (dtl_ppe=$589M, dtl_investments=$557M)
history_cf: capex=-$2,287M (2024!), op_lease_cash_cfo=$47M
            fin_lease_principal_cff=$49M, deferred_income_taxes=$113M
debt_instruments: ~15 инструментов, callable_flag, rate_type
lease_schedule 2025-2029: operating=[39,24,15,7,1]$M; finance=[78,70,50,29,7]$M
preprocess: steel_hrc_beta=-0.471, rev_best_beta=1.13, cap_interest_pct=37.75%
            st_debt_ratio=2.5%
```

### 15.2 Ключевые метрики US Steel 2024 (факт 10-K)

```
Revenue:      $15,640M   COGS (excl D&A): $14,060M  D&A: $913M
Interest IS:  $24M (net) Cap.interest: $213M (91%)  EBT: $438M
Tax:          $54M (12.3% — NOL!)   NI: $384M
Cash: $1,367M  PPE net: $11,973M  LTD: $4,078M  STD: $95M
CFO: $919M  CapEx: -$2,287M (14.6% revenue!)  CFF: -$199M
DTL: -$657M  Total assets: $20,235M  Total equity: $11,440M
```

---

## 16. project.yaml — полная структура

```yaml
company:
  name: "United States Steel Corporation"
  company_id: "us_steel"
  industry: "metals"
  currency: "USD"
  accounting_standard: "US_GAAP"
  db_unit: "USD"

model:
  mode: custom

  custom:
    periods:
      history_end_year: 2024
      forecast_start_year: 2025
      forecast_end_year: 2029

    revenue:
      macro_factor: steel_price_hrc

    cogs:
      macro_factor: steel_price_hrc      # revenue-side, beta=-0.471
      cost_factor: steel_ppi_iron_steel   # cost-side, beta=+0.202

    margins:
      tax_rate_statutory: 0.21

    ppe:
      min_capex_da_ratio: 0.90

    debt:
      mode: auto
      target_pct_revenue: 0.27
      avg_rate_pct: 0.0609
      rc:
        enable: true
      refinancing:
        mode: simple
        extend_years: 5

    taxes:
      nol_opening_balance: 1014   # $M federal, indefinite

    equity:
      dividend_payout_ratio: 0.03

    leases:
      enabled: true
      default_discount_rate: 0.05

features:
  min_cash: 0.0
  # use_ppe_corkscrew/use_wc_days/use_tax_corkscrew — автодетект!

covenants:
  enabled: true
  methodology: steel
  warning_buffer: 0.10
  thresholds:
    net_debt_ebitda_max: 3.5
    interest_coverage_min: 2.5
    ebitda_margin_min: 0.05
    current_ratio_min: 1.0

rating:
  methodology: sp
  weights:
    leverage: 0.30
    coverage: 0.30
    profitability: 0.25
    liquidity: 0.15
```

---

## 17. Типичные ошибки

| Ошибка | Симптом | Исправление |
|---|---|---|
| Работа в stressTest вместо _v2 | ROOT не содержит 'stressTest_v2' | Проверить ROOT при старте |
| Использует data_mart_v2.db | Данные из старой схемы | `assert 'v3' not in str(DB_PATH)` |
| D&A double-count | EBITDA завышена ~$900M | `da_in_cogs = False` |
| cash из BS plug | CF не управляет cash | `_solve_cash_from_cf` — единственный метод |
| Liability знаки в CF | WC delta неверный | `abs()` для taxes_payable, IP, AP в delta |
| parents[N] hardcode | ломается при переносе | `_find_root()` в `__init__.py` |
| NOL не активирован | eff rate = 21% | `nol_opening_balance: 1014` |
| Op lease в D&A add-back | CFO завышен | НЕ добавлять ROU op в total_da |
| capex = 0 в 2024 | Backtesting fail | Загрузить `-$2,287M` в history_cf |
| rate_spike не работает | NI не меняется | `type: pp` + обновить inst.interest_rate |
| Revenue и COGS от разных факторов | Rev растёт, COGS падает | Оба через HRC → chain-link |
| VECM rank overflow | нестабильные прогнозы | Группы ≤3 факторов, commodity → MR |

---

## 18. Скрипт полной верификации

```bash
cd "/Users/arturhusnutdinov/Documents/IT Development/Docker/stressTest_v2" && python3 << 'EOF'
import sys, logging, warnings
sys.path.insert(0, '.')
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)

from engine import ROOT, DB_PATH
assert str(ROOT).endswith('stressTest_v2'), f'WRONG ROOT: {ROOT}'
assert 'v3' not in str(DB_PATH), f'WRONG DB: {DB_PATH}'
print(f'ROOT: {ROOT} ✅')

from engine.orchestrator import build_model
result = build_model('us_steel',
    run_preprocessor=False, run_macro=False,
    run_model=True, run_stress=True, run_rating=True, run_covenants=True,
    stress_scenarios=['steel_downturn', 'rate_spike', 'wc_stress'])

mr = result.model_result
assert max(mr.bs_diffs.values()) < 1e6
assert max(mr.cf_diffs.values()) < 1e6
print(f'BS max: {max(mr.bs_diffs.values()):.6f} ✅')
print(f'CF max: {max(mr.cf_diffs.values()):.6f} ✅')

# NOL
s25 = mr.years[2025]
eff = s25.tax_expense / s25.ebt if s25.ebt else 0
assert abs(eff) < 0.10, f'NOL не работает: {eff:.1%}'
print(f'NOL eff rate 2025: {eff:.1%} ✅')

# Lease
assert (s25.rou_asset or 0) > 0, 'Lease не работает'
print(f'Lease ROU: ${(s25.rou_asset or 0)/1e6:.0f}M ✅')

# DTA/DTL
assert abs(s25.dta or 0) > 0 or abs(s25.dtl or 0) > 0
print(f'DTA/DTL: ok ✅')

# Stress
for sc, sr in result.stress_results.items():
    assert sr and sr.success
    print(f'Stress {sc}: OK ✅')

print()
print('=== ВСЕ ПРОВЕРКИ ПРОШЛИ ✅ ===')
print()
print(f'{"Год":<6} {"Rev$B":>7} {"EBITDA%":>8} {"NI$M":>7} {"BS":>6} {"CF":>6}')
for yr, s in sorted(mr.years.items()):
    _, _, bs = s.bs_check()
    _, _, cf = s.cf_bridge_check()
    print(f'{yr:<6} {s.revenue/1e9:>7.2f} {s.ebitda/s.revenue*100:>7.1f}% {s.net_income/1e6:>7.0f} {bs:>6.2f} {cf:>6.2f}')
EOF
```

---

## 19. Создание новой компании

```bash
python3 refactoring_v2/tools/init_company.py rusal \
    --name "United Company RUSAL" \
    --industry metals --currency USD --standard IFRS

# Создаёт полную структуру с ноутбуками и конфигами из шаблонов.
# Все ноутбуки универсальны — работают с любым COMPANY_ID.
```

**Порядок работы с новой компанией:**
1. Настроить `configs/project.yaml`
2. Загрузить данные через ExcelLoader
3. `build_model(company_id, run_preprocessor=True, run_macro=True, run_model=True)`
4. Анализировать в ноутбуках

---

*Этот документ — полный источник правды для stressTest Engine v2, включая все модули: LeaseBlock (ASC 842/IFRS 16), TaxBlock (NOL/DTA/DTL), DebtOptimizer (7 шагов), WCBlock (6 corkscrew), PPEBlock, Macro (VECM+MR+EWA), Standard/Custom mode, Stress, Rating, Covenants.*
