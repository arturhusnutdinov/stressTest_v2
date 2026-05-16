"""
ThreeStatementModel — ядро 3-Statement модели v2.
Принцип: один метод = один блок. Каждый блок получает prev_state и возвращает обновлённый state.
Циклические зависимости (Debt ↔ Interest ↔ Cash) решаются joint iteration.
"""

from __future__ import annotations

import logging
import math
from copy import deepcopy
from dataclasses import replace
from typing import Dict, List, Optional, Tuple

from .inputs import (
    DebtSettings, ForecastMethod, HistoricState,
    ModelConfig, YearState,
)
from .schedules import (
    PPEBlock, DebtOptimizer, DebtInstrumentOpen, DebtSolveResult,
    InstrumentKind, infer_kind, DebtBlock,
    TaxBlock, LeaseBlock, EquityBlock, InterestPayableBlock,
    IntangiblesBlock, WCBlock,
)

logger = logging.getLogger(__name__)

# Толерантность BS Identity и CF Bridge
BS_TOL   = 1.0       # $1 (в единицах db_unit)
CF_TOL   = 1.0
ITER_MAX = 15        # максимум итераций joint solver


class ModelError(Exception):
    pass

class BSImbalanceError(ModelError):
    pass

class CFBridgeError(ModelError):
    pass


# ─── результат прогона ────────────────────────────────────────────────────────

class ModelResult:
    """Результат прогона модели — YearState по каждому прогнозному году."""

    def __init__(self) -> None:
        self.years: Dict[int, YearState] = {}
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.bs_diffs: Dict[int, float] = {}
        self.cf_diffs: Dict[int, float] = {}
        # Debt schedule lines per forecast year (instrument × year), for DB persistence
        self.debt_lines: Dict[int, list] = {}  # year → List[DebtYearLine]

    @property
    def success(self) -> bool:
        return not self.errors

    def to_flat(self, year: int) -> Dict[str, float]:
        """YearState → плоский словарь для записи в БД."""
        if year not in self.years:
            return {}
        return self.years[year].to_dict()

    def summary(self) -> str:
        lines = [f"Модель: {len(self.years)} лет прогноза"]
        if self.bs_diffs:
            max_bs = max(self.bs_diffs.values())
            lines.append(f"  BS max diff: {max_bs:.2f}")
        if self.cf_diffs:
            max_cf = max(self.cf_diffs.values())
            lines.append(f"  CF max diff: {max_cf:.2f}")
        if self.warnings:
            lines += [f"  ⚠ {w}" for w in self.warnings[:3]]
        if self.errors:
            lines += [f"  ✗ {e}" for e in self.errors[:3]]
        return "\n".join(lines)


# ─── главный класс ────────────────────────────────────────────────────────────

class ThreeStatementModel:
    """
    Строит 3-Statement прогноз год за годом.

    Использование:
        model = ThreeStatementModel(historic, config)
        result = model.run()
    """

    def __init__(self, historic: HistoricState, config: ModelConfig) -> None:
        self._h = historic
        self._c = config
        from .forecast_dispatcher import ForecastDispatcher
        self._dispatcher = ForecastDispatcher(historic, config)
        # Mutable debt state persisting across forecast years (Bug 1 & 2 fix)
        self._debt_instruments_state: List[DebtInstrumentOpen] = []
        # Finance lease liability tracking (simple overlay, not full corkscrew)
        self._fl_liab_remaining: float = 0.0
        # next-year mandatory hint for ST/LT split (Bug 3 fix)
        self._debt_next_mandatory_hint: Dict[str, float] = {}
        # Snapshot of instrument openings at start of each year (for iteration-safe re-runs)
        self._debt_year_snapshot: Dict[str, float] = {}
        self._debt_snapshot_year: int = -1
        self._last_debt_lines: list = []  # DebtYearLine for the last solved year
        self._nol_carryforward: float = getattr(config, 'nol_opening_balance', 0.0) or 0.0
        # Fixed year-opening NOL (set once per year, before iteration loop); used by _solve_tax_block
        # to avoid depleting the NOL pool across iterations of the same year.
        self._nol_year_open: float = self._nol_carryforward
        # Covenant acceleration: callable instruments in breach → reclassified ST
        # Reset at start of each year; populated mid-iteration after BS totals are known
        self._covenant_breach_instruments: set = set()
        # Cached covenant checker (created once; repo=None since we never save mid-model)
        self._covenant_checker = None
        if getattr(config, 'covenants_enabled', False):
            try:
                from pathlib import Path
                from engine.covenants.core import CovenantsChecker
                company_dir = Path("companies") / config.company_id
                self._covenant_checker = CovenantsChecker.from_project_yaml(
                    config.company_id, None, company_dir
                )
            except Exception:
                pass

        # CogsBlock: component-based COGS (if configured in YAML)
        self._cogs_block = None
        try:
            import yaml as _yaml
            from pathlib import Path as _Path
            _cfg_path = _Path("companies") / config.company_id / "configs" / "project.yaml"
            if _cfg_path.exists():
                with open(_cfg_path) as _fh:
                    _raw = _yaml.safe_load(_fh) or {}
                _mode = _raw.get('model', {}).get('mode', 'standard')
                _cogs_cfg = _raw.get('model', {}).get(_mode, {}).get('cogs', {})
                if _cogs_cfg.get('mode') == 'component':
                    from .cogs_block import CogsBlock, CogsBlockConfig
                    _base = historic.base_year_state
                    _base_cogs = abs(_base.cogs or 0)
                    _pp_kpi = historic.preprocess.get('production_kpi', {})
                    _base_prod = _pp_kpi.get('production_al_kt', {})
                    if isinstance(_base_prod, dict):
                        _base_prod = _base_prod.get(config.history_end_year) or \
                                     _base_prod.get(max(k for k in _base_prod if isinstance(k, int) and k > 0), 0)
                    # Get preprocessor cogs_ratio (EWA, stable anchor)
                    _pp_mr = historic.preprocess.get('margin_ratios', {})
                    _cogs_anchor = _pp_mr.get('cogs_ratio_ex_da_recommended') or \
                                   _pp_mr.get('cogs_ratio_recommended') or 0.0
                    if isinstance(_cogs_anchor, dict):
                        _cogs_anchor = _cogs_anchor.get(-1, 0.0)
                    cb_cfg = CogsBlockConfig(
                        alumina_share=float(_cogs_cfg.get('alumina_share', 0.37)),
                        energy_share=float(_cogs_cfg.get('energy_share', 0.27)),
                        labour_share=float(_cogs_cfg.get('labour_share', 0.12)),
                        other_share=float(_cogs_cfg.get('other_share', 0.24)),
                        alumina_intensity=float(_cogs_cfg.get('alumina_intensity', 1.93)),
                        energy_kwh_per_t=float(_cogs_cfg.get('energy_kwh_per_t', 15500.0)),
                        mean_reversion_dampening=float(_cogs_cfg.get('mean_reversion_dampening', 0.30)),
                        clamp_sigma=float(_cogs_cfg.get('clamp_sigma', 0.06)),
                        base_year=config.history_end_year,
                        base_cogs=_base_cogs,
                        base_revenue=abs(_base.revenue or 0),
                        base_production_kt=float(_base_prod or 0),
                        cogs_ratio_anchor=float(_cogs_anchor),
                    )
                    # macro_history: base year values from DB (never stressed)
                    _macro_hist = {}
                    try:
                        import sqlite3
                        from engine import DB_PATH as _db_path
                        _conn = sqlite3.connect(str(_db_path))
                        for _r in _conn.execute(
                            "SELECT factor_name, year, value FROM macro_factors WHERE year=?",
                            (config.history_end_year,)
                        ).fetchall():
                            _macro_hist.setdefault(_r[0], {})[_r[1]] = _r[2]
                        _conn.close()
                    except Exception:
                        pass
                    self._cogs_block = CogsBlock(cb_cfg, historic.macro_forecasts, _macro_hist)
                    logger.info(f"CogsBlock: base_cogs=${_base_cogs/1e9:.2f}B prod={cb_cfg.base_production_kt:.0f}kt")
        except Exception as _e:
            logger.debug(f"CogsBlock init failed: {_e}")

    # ── публичный API ──────────────────────────────────────────────────────────

    def run(self) -> ModelResult:
        result = ModelResult()
        prev = self._h.base_year_state
        if prev is None:
            result.errors.append("base_year_state не загружен")
            return result

        for year in self._c.forecast_years:
            try:
                state = self._solve_year(year, prev)
                # Верификация
                _, _, bs_diff = state.bs_check()
                _, _, cf_diff = state.cf_bridge_check()
                result.bs_diffs[year] = bs_diff
                result.cf_diffs[year] = cf_diff
                if bs_diff > BS_TOL:
                    result.warnings.append(f"{year}: BS diff={bs_diff:.0f}")
                if cf_diff > CF_TOL:
                    result.warnings.append(f"{year}: CF diff={cf_diff:.0f}")
                result.years[year] = state
                result.debt_lines[year] = list(self._last_debt_lines)
                prev = state
                logger.info(
                    f"  {year}: Revenue={state.revenue/1e6:.0f}M "
                    f"NetIncome={state.net_income/1e6:.0f}M "
                    f"BS_diff={bs_diff:.0f}"
                )
            except Exception as e:
                msg = f"{year}: {e}"
                result.errors.append(msg)
                logger.error(f"  ✗ {msg}", exc_info=True)
                break

        return result

    # ── _solve_year ───────────────────────────────────────────────────────────

    def _solve_year(self, year: int, prev: YearState) -> YearState:
        """
        Решает один прогнозный год через итерации (joint iteration).

        Круговые зависимости в 3-Statement модели:
        ┌─ RC draw → interest_expense → EBT → tax → NI ─┐
        │                                                  │
        └─ NI → RE → equity → BS → cash → RC draw ────────┘

        Аналог Excel "Iterative Calculation" (Tools → Options → Iterations).
        Сходимость: изменение cash и NI < tol между итерациями.

        Параметры:
            max_iter: максимум итераций (дефолт 10, обычно сходится за 3-4)
            tol:      допуск сходимости в абсолютных единицах (дефолт 1000 = $1K)
        """
        max_iter = getattr(self._c, 'max_iter', 10)
        tol      = getattr(self._c, 'tol', 1000.0)  # $1K допуск

        state = YearState(year=year)

        # ── Блоки не зависящие от итерации (вычисляются один раз) ──────
        state = self._solve_revenue(state, prev)
        state = self._solve_cogs(state, prev)
        state = self._solve_sga(state, prev)
        state = self._solve_ppe(state, prev)
        state = self._solve_other_is(state, prev)
        state = self._solve_wc(state, prev)
        state = self._solve_lease(state, prev)
        state = self._solve_bs_other(state, prev)

        # ── Итерационный цикл ─────────────────────────────────────
        # Reset covenant breach set: re-evaluated every iteration based on current state
        self._covenant_breach_instruments = set()
        # Freeze NOL opening for this year — prevents depletion across iterations
        self._nol_year_open = self._nol_carryforward

        prev_cash = prev.cash
        prev_ni   = 0.0

        for iteration in range(max_iter):
            # 1. Debt (RC draw зависит от prev_cash → cash estimate)
            # Always use prior-year cash as opening for the optimizer — using current-iter
            # cash would double-count CFO (state.cash already includes CFO effects).
            state._cash_estimate = prev.cash
            state = self._solve_debt(state, prev)

            # 2. Interest payable corkscrew
            state = self._solve_interest_payable(state, prev)

            # 3. IS subtotals: EBITDA → EBIT → EBT
            state = self._solve_is_subtotals(state)

            # 4. Tax: EBT → Tax → NI
            state = self._solve_tax_block(state, prev)

            # 5. Equity: NI → RE (BS)
            state = self._solve_equity(state, prev)

            # 6. CF: CFO + CFI + CFF
            state = self._solve_cf(state, prev)

            # Store actual CFO so next iteration's optimizer uses a better estimate
            state._actual_cfo_est = state.cfo_total

            # 7. Cash из CF Bridge (не из BS plug!)
            state = self._solve_cash_from_cf(state, prev)

            # 8. BS totals (использует cash из CF)
            state = self._solve_bs_totals(state)

            # 9. Covenant acceleration check (after BS totals — all metrics available)
            # Callable instruments breach → reclassified to ST next iteration
            if getattr(self._c, 'covenants_enabled', False):
                self._update_covenant_breach_instruments(state, year)

            # ── Сходимость ────────────────────────────────────────
            cash_delta = abs(state.cash - prev_cash)
            ni_delta   = abs(state.net_income - prev_ni)

            logger.debug(
                f"  {year} iter={iteration+1}: "
                f"cash_Δ={cash_delta/1e6:.2f}M ni_Δ={ni_delta/1e6:.2f}M"
            )

            if cash_delta < tol and ni_delta < tol:
                if iteration > 0:
                    logger.debug(
                        f"  {year}: сошлось за {iteration+1} итераций"
                    )
                break

            prev_cash = state.cash
            prev_ni   = state.net_income
        else:
            logger.warning(
                f"  {year}: НЕ сошлось за {max_iter} итераций"
            )

        return state

    # ── IS блоки ──────────────────────────────────────────────────────────────

    def _solve_revenue(self, state: YearState, prev: YearState) -> YearState:
        from .blocks.revenue import solve_revenue
        return solve_revenue(state, prev, self._h, self._c)

    def _solve_cogs(self, state: YearState, prev: YearState) -> YearState:
        """
        COGS = Revenue × ratio_cogs × (1 + macro_uplift)
        OR (if cogs.mode=component): COGS = CogsBlock(alumina + energy + labour + other)
        """
        # ── CogsBlock mode: component-based COGS ──────────────────────────────
        if self._cogs_block is not None:
            cogs_val = self._cogs_block.compute(state.year, revenue=abs(state.revenue))
            state.cogs = -abs(cogs_val)
            state.gross_profit = state.revenue + state.cogs
            return state

        # ── Standard mode: ratio × macro uplift ──────────────────────────────
        # cogs_pct: YAML config → preprocessor recommended → last historical → None (clamped below)
        cogs_pct = self._c.cogs_pct
        if not cogs_pct:
            pp_mr = self._h.preprocess.get('margin_ratios', {})
            rec = pp_mr.get('cogs_ratio_recommended')
            if isinstance(rec, dict):
                rec = rec.get(-1)
            if not rec:
                rec = pp_mr.get('cogs_ratio_last')
                if isinstance(rec, dict):
                    rec = rec.get(-1)
            cogs_pct = float(rec) if rec else None

        # Читаем конфиг YAML для COGS и accounting_conventions
        mode_cfg = {}
        da_in_cogs = True  # default: DA embedded in COGS (conservative)
        try:
            import yaml
            from engine import ROOT as _root
            cfg_path = _root / "companies" / self._h.company_id / "configs" / "project.yaml"
            if cfg_path.exists():
                with open(cfg_path) as f:
                    raw = yaml.safe_load(f) or {}
                mode = raw.get('model', {}).get('mode', 'standard')
                mode_cfg = raw.get('model', {}).get(mode, {}).get('cogs', {})
                da_in_cogs = raw.get('accounting_conventions', {}).get('da_in_cogs', True)
        except Exception:
            pass

        revenue_factor = mode_cfg.get('revenue_factor', 'steel_price_hrc')
        cost_factor    = mode_cfg.get('cost_factor', 'steel_ppi_iron_steel')

        # If still None after preprocessor lookup, derive from history median
        if cogs_pct is None:
            hist_cogs_raw = self._h.preprocess.get('margin_ratios', {}).get('cogs_ratio', {})
            hist_vals_raw = [v for k, v in (hist_cogs_raw.items() if isinstance(hist_cogs_raw, dict) else [])
                             if isinstance(k, int) and k > 0 and v is not None]
            cogs_pct = sorted(hist_vals_raw)[len(hist_vals_raw) // 2] if hist_vals_raw else 0.75

        # da_in_cogs=False: DB/history stores COGS including D&A, but model computes
        # ebit = ebitda - total_da separately → strip DA from cogs_pct to avoid double-count.
        # dep_to_rev is computed by preprocessor as DA / Revenue per year.
        if not da_in_cogs:
            _capex_pp_cogs = self._h.preprocess.get('capex', {})
            dep_summary = _capex_pp_cogs.get('dep_to_rev', {})
            # Try '_recommended' key inside dict, then fall back to top-level 'dep_to_rev_recommended'
            dep_to_rev_rec = (
                dep_summary.get('_recommended') if isinstance(dep_summary, dict) else None
            ) or _capex_pp_cogs.get('dep_to_rev_recommended')
            if dep_to_rev_rec:
                cogs_pct = max(0.40, cogs_pct - dep_to_rev_rec)
                logger.debug(
                    f"  {state.year} da_in_cogs=False: "
                    f"strip dep_to_rev={dep_to_rev_rec:.4f} → cogs_pct={cogs_pct:.4f}"
                )

        betas = {**self._h.preprocess.get('beta_coefficients', {}),
                 **self._h.preprocess.get('revenue_betas', {}),
                 **self._h.preprocess.get('cogs_macro', {})}

        def _apply_factor(factor_name: str, default_beta: float) -> float:
            nonlocal cogs_pct
            factor_series = self._h.macro_forecasts.get(factor_name, {})
            if not factor_series:
                return cogs_pct
            f_curr = factor_series.get(state.year)
            f_prev = factor_series.get(state.year - 1)
            if not f_curr or not f_prev or f_prev <= 0:
                return cogs_pct
            beta_key = factor_name.replace('-', '_') + '_beta'
            beta = betas.get(beta_key) or betas.get(f'cogs_beta_{factor_name}') or default_beta
            if beta is None:
                beta = default_beta
            factor_growth = math.log(f_curr / f_prev)
            uplift = factor_growth * beta
            # Clamp: не более ±2pp к cogs_pct в год
            max_uplift = 0.02 / max(abs(cogs_pct), 0.01)
            uplift = max(-max_uplift, min(max_uplift, uplift))
            logger.debug(
                f"  {state.year} COGS {factor_name}: "
                f"growth={factor_growth:.3f} beta={beta:.3f} uplift={uplift:.4f}"
            )
            return cogs_pct * (1.0 + uplift)

        # Применяем revenue factor (обратная связь: beta < 0)
        if revenue_factor:
            # Берём beta из препроцессора (rev_beta_<factor>); без него — без корректировки
            rev_beta_key = f"rev_beta_{revenue_factor}"
            beta_val = betas.get(rev_beta_key)
            if isinstance(beta_val, dict):
                beta_val = beta_val.get(-1)
            beta_default = float(beta_val) if beta_val is not None else 0.0
            cogs_pct = _apply_factor(revenue_factor, beta_default)

        # Применяем cost factor (прямая связь: beta > 0)
        if cost_factor:
            cost_beta_key = f"rev_beta_{cost_factor}"
            cost_beta_val = betas.get(cost_beta_key)
            if isinstance(cost_beta_val, dict):
                cost_beta_val = cost_beta_val.get(-1)
            cost_beta_default = float(cost_beta_val) if cost_beta_val is not None else 0.0
            cogs_pct = _apply_factor(cost_factor, cost_beta_default)

        # Clamp в исторический диапазон [P10, P90] из препроцессора
        hist_cogs = self._h.preprocess.get('margin_ratios', {}).get('cogs_ratio', {})
        if isinstance(hist_cogs, dict):
            hist_vals_raw = {k: v for k, v in hist_cogs.items()
                             if isinstance(k, int) and k > 0 and v is not None}
            if not da_in_cogs:
                # Strip per-year dep_to_rev from historical cogs_ratio before clamping
                dep_summary = self._h.preprocess.get('capex', {}).get('dep_to_rev', {})
                dep_by_yr = {k: v for k, v in dep_summary.items()
                             if isinstance(k, int)} if isinstance(dep_summary, dict) else {}
                dep_rec = dep_summary.get('_recommended', 0.0) if isinstance(dep_summary, dict) else 0.0
                hist_vals = [v - dep_by_yr.get(k, dep_rec) for k, v in hist_vals_raw.items()]
            else:
                hist_vals = list(hist_vals_raw.values())
            if len(hist_vals) >= 5:
                hist_sorted = sorted(hist_vals)
                n = len(hist_sorted)
                p10 = hist_sorted[max(0, int(n * 0.10))]
                p90 = hist_sorted[min(n-1, int(n * 0.90))]
                cogs_pct = max(p10 * 0.95, min(p90 * 1.05, cogs_pct))
            elif hist_vals:
                cogs_pct = max(min(hist_vals) * 0.90, min(max(hist_vals) * 1.10, cogs_pct))
        else:
            cogs_pct = max(0.40, min(1.05, cogs_pct))

        state.cogs = -abs(state.revenue * cogs_pct)
        state.gross_profit = state.revenue + state.cogs
        return state

    def _solve_sga(self, state: YearState, prev: YearState) -> YearState:
        from .blocks.sga import solve_sga
        return solve_sga(state, prev, self._h, self._c)

    def _solve_ppe(self, state: YearState, prev: YearState) -> YearState:
        # Standard mode: простой % от Revenue без PPE corkscrew
        if not getattr(self._c, 'use_ppe_corkscrew', True):
            pp_cap = self._h.preprocess.get('capex', {})
            dep_to_rev = self._c.dep_to_rev
            if not dep_to_rev:
                rec = pp_cap.get('dep_to_rev_recommended')
                if isinstance(rec, dict): rec = rec.get(-1)
                dep_to_rev = float(rec) if rec else None
            dep_to_rev = dep_to_rev or capex_pct  # last-resort: dep ≈ capex (maintenance equilibrium)
            capex_pct = self._c.capex_pct
            if not capex_pct:
                rec = pp_cap.get('capex_to_rev_recommended')
                if isinstance(rec, dict): rec = rec.get(-1)
                capex_pct = float(rec) if rec else None
            capex_pct = capex_pct or dep_to_rev  # capex ≈ dep (maintenance) as last-resort
            dep_charge = state.revenue * dep_to_rev
            capex      = abs(state.revenue * capex_pct)
            # PP&E net: простой corkscrew без gross/accum разбивки
            state.ppe_net       = max(0.0, prev.ppe_net + capex - dep_charge)
            state.ppe_gross     = state.ppe_net  # упрощённо
            state.ppe_accum_dep = 0.0
            state.dep_ppe       = dep_charge
            state.cfi_capex     = -capex
            state.cfi_disposal_proceeds = 0.0
            # Intangibles: amort rate from preprocessor or last-resort 10%
            _intang_rec = self._h.preprocess.get('capex', {}).get('intang_amort_rate_recommended')
            if isinstance(_intang_rec, dict): _intang_rec = _intang_rec.get(-1)
            intang_rate = float(_intang_rec) if _intang_rec else 0.10
            state.intangibles       = max(0.0, prev.intangibles * (1 - intang_rate))
            state.amort_intangibles = prev.intangibles * intang_rate
            state.total_da = dep_charge + state.amort_intangibles
            return state

        # Year-specific override takes precedence over ratio_default
        capex_pct = (
            (self._c.capex_pct_by_year or {}).get(state.year)
            or self._c.capex_pct
        )
        if not capex_pct:
            _pp_cap = self._h.preprocess.get('capex', {})
            _rec = _pp_cap.get('capex_to_rev_recommended')
            if isinstance(_rec, dict): _rec = _rec.get(-1)
            if not _rec:
                _rec = _pp_cap.get('dep_to_rev_recommended')
                if isinstance(_rec, dict): _rec = _rec.get(-1)
            capex_pct = float(_rec) if _rec else 0.05
        raw_capex = abs(state.revenue * capex_pct)
        # Economic floor: CapEx >= min_capex_da_ratio × DA (maintenance of asset base)
        _prev_da = prev.dep_ppe or 0.0
        _min_ratio = getattr(self._c, 'min_capex_da_ratio', 0.90)
        capex = max(raw_capex, _prev_da * _min_ratio)
        # Growth capex: при росте выручки нужен expansion capex
        _expansion_pct = getattr(self._c, 'expansion_capex_pct_of_rev_growth', 0.0) or 0.0
        if _expansion_pct > 0:
            _rev_growth = max(0.0, state.revenue - prev.revenue)
            capex += _rev_growth * _expansion_pct
        # Additive project capex: one-off or scheduled investments on top of base model
        _add_capex_sched = getattr(self._c, 'additional_capex_schedule', {}) or {}
        capex += _add_capex_sched.get(state.year, 0.0)
        # dep_rate: из препроцессора; если нет — вычисляем из dep_to_rev / (ppe_net/rev)
        dep_rate = self._c.dep_rate
        if not dep_rate and self._c.dep_to_rev and prev.ppe_net and state.revenue:
            dep_rate = self._c.dep_to_rev / max(prev.ppe_net / max(state.revenue, 1), 0.01)
        dep_rate = dep_rate or capex_pct  # крайний fallback — = capex_pct (нейтрально)
        # Если только ppe_net в БД (нет gross) — предпочесть dep_to_rev
        if prev.ppe_gross == 0 and self._c.dep_to_rev:
            dep_rate = self._c.dep_to_rev / max(
                (prev.ppe_net / max(state.revenue, 1)),
                0.01
            )
        disposal_ratio = 0.0  # No disposals modeled — avoids unbooked gain/loss complexity
        block = PPEBlock.from_prev_state(
            prev, dep_rate=dep_rate, capex=capex,
            disposal_proceeds=capex * disposal_ratio,
            disposal_pct_of_capex=disposal_ratio,
        )
        ok, issues = block.validate()
        if not ok:
            logger.warning(f"  {state.year} PPE: {issues}")
        state.ppe_gross     = block.gross_close or 0.0
        state.ppe_accum_dep = block.accdep_close or 0.0
        state.ppe_net       = block.net_close or 0.0
        state.dep_ppe       = block.dep_charge
        state.cfi_capex     = -capex
        state.cfi_disposal_proceeds = block.disposal_proceeds
        # Disposal gain → ppe_disposal_gain → included in EBT → flows to NI/RE.
        # Without this, the gain stays in cash (CFI) but not in equity, causing BS drift.
        state.ppe_disposal_gain = block.gain_loss or 0.0
        # Intangibles corkscrew — amort_rate только если IS историчеcки показывает амортизацию
        hist_amort = float(
            self._h.is_data.get(self._h.base_year, {}).get("amortization") or 0.0
        )
        amort_rate = (hist_amort / max(prev.intangibles, 1.0)) if hist_amort > 0 else 0.0
        intang_block = IntangiblesBlock.from_prev_state(
            prev, amort_rate=amort_rate, revenue=state.revenue,
            additions_pct_revenue=0.0,
        )
        state.intangibles       = intang_block.intang_close or 0.0
        state.amort_intangibles = intang_block.amort_is
        state.total_da = block.dep_charge + state.amort_intangibles
        return state

    def _solve_other_is(self, state: YearState, prev: YearState) -> YearState:
        """
        Прочие статьи IS через ForecastDispatcher.
        Метод из YAML перекрывает дефолтную EWA логику.
        """
        # One-time items → ZERO (всегда, если не переопределено)
        for metric in ['asset_impairment', 'restructuring',
                       'loss_on_debt_extinguishment', 'other_losses_gains']:
            fm = self._c.get_forecast_method('is', metric)
            if fm is None:
                setattr(state, metric, 0.0)
            else:
                val = self._dispatcher.apply('is', metric, state, prev)
                if val is not None:
                    setattr(state, metric, val)

        # Recurring non-operating → EWA или метод из YAML
        recurring = [
            ('earnings_from_investees', 'extended', 'earnings_from_investees'),
            ('net_periodic_benefit',    'extended', 'net_periodic_benefit_income'),
            ('other_financial_costs',   'extended', 'other_financial_costs'),
            ('interest_income',         'extended', 'interest_income'),
        ]

        for attr, pp_group, pp_key in recurring:
            # Dispatcher использует pp_key (ключ в БД) для поиска истории
            # YAML forecast_methods тоже должен быть keyed by pp_key
            dispatch_key = pp_key  # совпадает с attr кроме net_periodic_benefit
            val = self._dispatcher.apply('is', dispatch_key, state, prev)
            if val is not None:
                setattr(state, attr, val)
                continue

            # Дефолт: EWA из препроцессора (сырое значение из БД — знак как в DB)
            pp = self._h.preprocess.get(pp_group, {})
            rec = pp.get(f"{pp_key}_recommended") or pp.get(f"{pp_key}_last")
            if isinstance(rec, dict):
                rec = rec.get(-1)
            if rec is not None:
                # Preprocessor хранит в конвенции источника (может быть + или -).
                # Модель ожидает доход как ПОЛОЖИТЕЛЬНЫЙ → abs() гарантирует это.
                setattr(state, attr, abs(float(rec)))
            else:
                prev_val = getattr(prev, attr, 0.0)
                setattr(state, attr, prev_val * 0.95)

        return state

    def _solve_is_subtotals(self, state: YearState) -> YearState:
        from .blocks.is_subtotals import solve_is_subtotals
        return solve_is_subtotals(state, self._h)

    def _solve_tax_block(self, state: YearState, prev: YearState) -> YearState:
        """Tax через TaxBlock: NOL, DTA/DTL, taxes_payable, taxes_paid_cf."""
        # Standard mode: effective rate без DTA/DTL
        if not getattr(self._c, 'use_tax_corkscrew', True):
            # Effective rate из препроцессора или statutory
            pp_m = self._h.preprocess.get('margin_ratios', {})
            eff_rate = pp_m.get('effective_tax_rate_recommended')
            if isinstance(eff_rate, dict):
                eff_rate = eff_rate.get(-1)
            if not eff_rate:
                eff_rate = self._c.tax_rate
            if not eff_rate:
                # Derive from history median effective rate
                hist_tax = self._h.preprocess.get('margin_ratios', {}).get('effective_tax_rate', {})
                hist_vals_tx = [v for k, v in (hist_tax.items() if isinstance(hist_tax, dict) else [])
                                if isinstance(k, int) and k > 0 and v is not None and 0 < v < 1]
                eff_rate = sorted(hist_vals_tx)[len(hist_vals_tx) // 2] if hist_vals_tx else 0.21
            eff_rate = max(0.05, min(0.45, float(eff_rate)))

            state.tax_expense      = -max(0.0, state.ebt * eff_rate) if state.ebt > 0 else 0.0
            state.net_income       = state.ebt + state.tax_expense
            state.dta              = prev.dta    # carry
            state.dtl              = prev.dtl    # carry
            state.taxes_payable    = prev.taxes_payable  # carry
            state.cfo_taxes_paid   = abs(state.tax_expense)
            state.cfo_deferred_tax = 0.0
            return state

        accel_pct = getattr(self._c, 'accel_dep_excess_pct', 0.0) or 0.0
        accel_dep_excess = (state.dep_ppe or 0.0) * accel_pct

        # Pension DTA: employee_benefits reduction → DTA grows
        pension_dta_delta = max(0.0, (prev.employee_benefits or 0.0) - (state.employee_benefits or 0.0))

        # Use year-opening NOL (frozen before iteration loop) so multi-iteration convergence
        # doesn't deplete the pool mid-year. _nol_carryforward persists the close to next year.
        _nol_open = self._nol_year_open
        block = TaxBlock(
            ebt=state.ebt,
            statutory_rate=self._c.tax_rate or 0.21,
            nol_open=_nol_open,
            nol_enabled=_nol_open > 0,
            nol_limit_pct=getattr(self._c, 'nol_max_utilization_pct', 0.80) or 0.80,
            dta_open=prev.dta or 0.0,
            dtl_open=prev.dtl or 0.0,
            taxes_payable_open=prev.taxes_payable or 0.0,
            accel_dep_excess=accel_dep_excess,
            pension_dta_delta=pension_dta_delta,
            payment_lag=1,  # next_year: US Steel pays prior-year taxes in current year
        ).solve()
        ok, issues = block.validate()
        if not ok:
            logger.warning(f"  {state.year} Tax: {issues}")

        # IS routing: current tax only (statutory × taxable_income)
        state.tax_expense   = block.total_tax_expense or 0.0
        state.net_income    = state.ebt + state.tax_expense
        # BS routing: positive magnitudes
        state.dta           = block.dta_close or 0.0
        state.dtl           = block.dtl_close or 0.0
        state.taxes_payable = block.taxes_payable_close or 0.0
        # CFO routing
        state.cfo_deferred_tax = block.cfo_deferred_tax or 0.0
        state.cfo_taxes_paid   = -(block.tax_paid_cf or 0.0)  # negative = cash outflow (supplemental)
        # NOL persistence across years
        self._nol_carryforward = block.nol_close or 0.0

        return state

    # ── Covenant acceleration ─────────────────────────────────────────────────

    def _update_covenant_breach_instruments(self, state: YearState, year: int) -> None:
        """
        Проверяет ковенанты по текущему YearState и обновляет
        self._covenant_breach_instruments. Callable instruments с нарушением
        acceleration_triggers будут переклассифицированы в ST на следующей
        итерации debt solve.
        """
        if self._covenant_checker is None:
            return
        try:
            triggers = set(getattr(self._c, 'covenant_acceleration_triggers',
                                   ['interest_coverage', 'net_debt_ebitda']))
            cov_by_metric = self._covenant_checker.check_year(state, year)

            breached_metrics = {
                metric for metric, res in cov_by_metric.items()
                if res.status == 'breach' and metric in triggers
            }

            if breached_metrics:
                for inst in self._debt_instruments_state:
                    if getattr(inst, 'callable_flag', False):
                        self._covenant_breach_instruments.add(inst.instrument_id)
                logger.debug(
                    f"  {year}: covenant breach {breached_metrics} → "
                    f"{len(self._covenant_breach_instruments)} callable instruments → ST"
                )
            else:
                self._covenant_breach_instruments = set()

        except Exception as e:
            logger.debug(f"  {year}: covenant acceleration check skipped: {e}")

    # ── WC блок ───────────────────────────────────────────────────────────────

    def _solve_wc(self, state: YearState, prev: YearState) -> YearState:
        """Working Capital через WCBlock (DSO/DIH/DPO с полным corkscrew)."""
        # Standard mode: NWC как % от Revenue
        if not getattr(self._c, 'use_wc_days', True):
            # NWC/Revenue ratio из препроцессора или дефолт 8%
            pp_wc = self._h.preprocess.get('wc_days', {})
            nwc_ratio = pp_wc.get('nwc_to_revenue_recommended')
            if isinstance(nwc_ratio, dict):
                nwc_ratio = nwc_ratio.get(-1)
            nwc_ratio = float(nwc_ratio) if nwc_ratio else 0.08
            nwc_ratio = max(0.02, min(0.25, nwc_ratio))

            target_nwc = state.revenue * nwc_ratio
            prev_nwc   = (prev.accounts_receivable + prev.inventory
                         + prev.other_ca - abs(prev.accounts_payable)
                         - abs(getattr(prev, 'accrued_liabilities', 0))
                         - abs(prev.other_cl))
            delta_nwc  = target_nwc - prev_nwc

            # Простое разбиение NWC
            state.accounts_receivable = target_nwc * 0.45
            state.inventory           = target_nwc * 0.40
            state.other_ca            = target_nwc * 0.15
            state.accounts_payable    = -target_nwc * 0.35
            state.other_cl            = -target_nwc * 0.10
            state.cfo_change_ar       = -(state.accounts_receivable - prev.accounts_receivable)
            state.cfo_change_inv      = -(state.inventory - prev.inventory)
            state.cfo_change_ap       = -(state.accounts_payable - prev.accounts_payable)
            state.cfo_wc_delta        = -delta_nwc
            return state

        _pp_wc = self._h.preprocess.get('wc_days', {})
        def _wc_days(cfg_val, pp_key):
            if cfg_val:
                return float(cfg_val)
            rec = _pp_wc.get(pp_key)
            if isinstance(rec, dict): rec = rec.get(-1)
            return float(rec) if rec else None

        _dso = _wc_days(self._c.dso_days, 'dso_recommended')
        _dih = _wc_days(self._c.dih_days, 'dih_recommended')
        _dpo = _wc_days(self._c.dpo_days, 'dpo_recommended')
        _wc_kwargs: dict = {}
        if _dso is not None: _wc_kwargs['dso'] = _dso
        if _dih is not None: _wc_kwargs['dih'] = _dih
        if _dpo is not None: _wc_kwargs['dpo'] = _dpo

        # Cyclical WC sensitivity: pass revenue growth rate so WC days respond
        # to macro cycle (declining revenue → longer DSO/DIH, shorter DPO)
        prev_rev = prev.revenue if (prev.revenue or 0) > 0 else (state.revenue or 1)
        rev_growth = (state.revenue - prev_rev) / prev_rev if prev_rev > 0 else 0.0

        block = WCBlock.from_days(
            prev=prev,
            revenue=state.revenue,
            cogs=state.cogs,
            sga=state.sga,
            revenue_growth_rate=rev_growth,
            **_wc_kwargs,
        )
        ok, issues = block.validate()
        if not ok:
            logger.warning(f"  {state.year} WC: {issues}")

        state.accounts_receivable = block.ar_close
        state.inventory           = block.inventory_close
        state.accounts_payable    = -block.ap_close   # знак: liability в BS
        state.other_ca            = block.other_ca_close
        state.other_cl            = block.other_cl_close + block.accrued_close

        # CF WC changes
        state.cfo_change_ar  = -(block.ar_close - block.ar_open)
        state.cfo_change_inv = -(block.inventory_close - block.inventory_open)
        state.cfo_change_ap  =   (block.ap_close - block.ap_open)
        state.cfo_wc_delta   = block.get_wc_delta()
        return state

    # ── Equity corkscrew ──────────────────────────────────────────────────────

    def _solve_equity(self, state: YearState, prev: YearState) -> YearState:
        """Retained Earnings corkscrew через EquityBlock."""
        # Leverage gate: use current debt (just solved) vs prev cash (not yet updated)
        _total_debt = abs(state.long_term_debt or 0) + abs(state.short_term_debt or 0)
        _ebitda = state.ebitda or 0
        _nd_ebitda = (_total_debt - (prev.cash or 0)) / _ebitda if _ebitda > 1e-6 else 999.0
        # FCF basis: prior year actuals (companies decide buybacks on known trailing FCF)
        _fcf_prev = (prev.cfo_total or 0) + (prev.cfi_total or 0)
        # Equity additional events for this year (one-off issuances/buybacks/dividends)
        _eq_events = (self._c.equity_additional_events or {}).get(state.year)
        block = EquityBlock.from_prev_state(
            prev=prev,
            net_income=state.net_income,
            dividend_pct_ni=self._c.dividend_pct_ni,
            buyback_pct_fcf=getattr(self._c, 'buyback_pct_fcf', 0.0),
            buyback_leverage_max=getattr(self._c, 'buyback_leverage_max', 2.0),
            net_debt_ebitda=_nd_ebitda,
            fcf_for_buyback=_fcf_prev,
            equity_additional_events=_eq_events,
        )
        ok, issues = block.validate()
        if not ok:
            logger.warning(f"  {state.year} Equity: {issues}")

        state.retained_earnings = block.re_close or 0.0
        state.share_capital     = block.share_cap_close or 0.0
        state.apic              = block.apic_close or 0.0
        state.treasury_stock    = block.treasury_close or 0.0
        state.aoci              = block.aoci_close or 0.0
        state.nci               = block.nci_close or 0.0

        state.cff_dividends    = -block.dividends
        state.cff_buybacks     = -block.buybacks
        state.cff_share_buyback = -block.buybacks   # alias

        # Additive scheduled equity events (SPO, extra buyback, special dividend)
        _eq_events = getattr(self._c, 'equity_additional_events', {}) or {}
        _yr_events = _eq_events.get(state.year, {})
        if _yr_events:
            _add_buyback  = float(_yr_events.get('buyback',   0.0))
            _add_issuance = float(_yr_events.get('issuance',  0.0))
            _add_divs     = float(_yr_events.get('dividends', 0.0))
            # CFF flows (outflows negative, inflows positive)
            state.cff_share_buyback  = (state.cff_share_buyback or 0.0) - _add_buyback
            state.cff_buybacks       = (state.cff_buybacks or 0.0)      - _add_buyback
            state.cff_equity_issuance = (state.cff_equity_issuance or 0.0) + _add_issuance
            state.cff_dividends      = (state.cff_dividends or 0.0)     - _add_divs
            # BS: issuance increases share_capital; buyback increases treasury (reduces equity)
            state.share_capital    = (state.share_capital or 0.0)    + _add_issuance
            state.treasury_stock   = (state.treasury_stock or 0.0)   + _add_buyback
            # RE: special dividend reduces retained earnings (already reduced by model divs)
            state.retained_earnings = (state.retained_earnings or 0.0) - _add_divs

        return state

    def _solve_lease(self, state: YearState, prev: YearState) -> YearState:
        """Lease corkscrew через LeaseBlock (Finance + Operating).
        Uses from_config (EWA-calibrated rates) when preprocessor data is available,
        falls back to from_prev_state (dep_rate approach) otherwise."""
        _has_lease_params = (
            self._h.preprocess.get("lease", {}).get("op_lease_decay_rate_recommended") is not None
            or self._c.lease.op_cash_payment > 0
            or self._c.lease.fin_principal_rate != 0.25  # non-default → explicitly loaded
        )
        if _has_lease_params:
            block = LeaseBlock.from_config(prev=prev, config=self._c)
        else:
            _lease_dep_rec = self._h.preprocess.get('capex', {}).get('lease_dep_rate_recommended')
            if isinstance(_lease_dep_rec, dict): _lease_dep_rec = _lease_dep_rec.get(-1)
            _lease_dep_rate = float(_lease_dep_rec) if _lease_dep_rec else 0.15
            block = LeaseBlock.from_prev_state(
                prev=prev,
                accounting_standard=self._c.accounting_standard,
                finance_discount_rate=self._c.leases.default_discount_rate,
                operating_discount_rate=self._c.leases.default_discount_rate,
                dep_rate=_lease_dep_rate,
            )
        ok, issues = block.validate()
        if not ok:
            logger.warning(f"  {state.year} Lease: {issues}")

        # BS
        state.rou_asset             = block.rou_total_close
        state.rou_finance           = block.rou_finance_close
        state.rou_operating         = block.rou_operating_close
        state.lease_liab_current    = block.liab_current_total
        state.lease_liab_noncurrent = block.liab_noncurrent_total
        state.lease_liab_cur_finance   = block.liab_finance_current
        state.lease_liab_cur_operating = block.liab_operating_current
        state.lease_liab_ncur_finance   = block.liab_finance_noncurrent
        state.lease_liab_ncur_operating = block.liab_operating_noncurrent

        # IS
        state.dep_rou                 = block.dep_rou
        state.interest_expense_leases = block.interest_expense_leases
        # US GAAP operating: dep_rou excludes operating ROU amort (lease_expense not in D&A).
        # NI already embeds the cash lease expense via SGA; do NOT add rou_amort_operating to
        # total_da — it is NOT a non-cash add-back (the payment IS the cash outflow).
        state.total_da += block.dep_rou  # finance + IFRS operating only

        # CF
        # op_lease_pmt is NOT added to cfo_total — operating lease expense is already in NI via SGA.
        # Adding it would double-count the cash outflow. Instead, dep_rou_op (above) and delta_lease_lia
        # (in cfo_change_other_wc) together reconcile the non-cash items correctly.
        state.cfo_lease_payments_operating = -block.payments_cfo  # stored for reference only
        state.cff_finance_lease_principal   = -block.payments_cff

        # ── Simple finance lease CFF overlay ─────────────────────────────
        # Finance lease principal is INSIDE ppe_net (dep handled by PPE solver).
        # Only the CFF payment and matching other_ncl liability reduction needed.
        # Uses fin_principal_rate from config × prev other_ncl finance portion.
        _fl_rate = getattr(self._c.lease, 'fin_principal_rate', 0) or 0
        if _fl_rate > 0 and block.payments_cff == 0:
            # Estimate remaining finance lease liability from running balance
            _fl_liab_est = self._fl_liab_remaining
            if _fl_liab_est == 0:
                _fl_liab_est = 209_000_000.0  # 10-K 2024: $209M total fin lease liab
            _fl_principal = _fl_liab_est * _fl_rate
            # Update running balance (new leases flow through capex→ppe_net, not here)
            self._fl_liab_remaining = max(0, _fl_liab_est - _fl_principal)
            # CFF: principal outflow
            state.cff_finance_lease_principal = -_fl_principal
            # BS: reduce other_ncl to match (applied in _solve_bs_other)
            state._fl_ncl_adj = -_fl_principal

        return state

    def _solve_interest_payable(self, state: YearState, prev: YearState) -> YearState:
        """Interest Payable corkscrew → interest_payable BS + cfo_interest_paid."""
        block = InterestPayableBlock(
            interest_payable_open=prev.interest_payable or 0.0,
            interest_accrued=state.interest_expense,
            payment_timing="next_year",
        ).solve()
        ok, issues = block.validate()
        if not ok:
            logger.warning(f"  {state.year} InterestPayable: {issues}")

        state.interest_payable = block.interest_payable_close or 0.0
        state.cfo_interest_paid = -(block.interest_paid_cf or 0.0)
        return state

    # ── Joint Debt ↔ Interest solver ──────────────────────────────────────────

    def _joint_solve(self, state: YearState, prev: YearState) -> YearState:
        """
        Итеративно решает циклическую зависимость:
        Debt → Interest → CFO → Cash → RC draw/sweep → Debt
        """
        cfg = self._c.debt

        for iteration in range(ITER_MAX):
            prev_interest = state.interest_expense

            # 1. Решаем долг (в зависимости от режима)
            state = self._solve_debt(state, prev)

            # 2. Interest income от cash
            state.interest_income = prev.cash * self._c.cash_rate

            # 3. Пересчитываем IS subtotals (нужны для ICR в LP)
            state = self._solve_is_subtotals(state)

            # 4. Проверка сходимости
            diff = abs(state.interest_expense - prev_interest)
            if diff < cfg.tol:
                logger.debug(f"  Joint iter={iteration+1} diff={diff:.2f} — OK")
                break
        else:
            logger.warning(
                f"  {state.year}: joint solver не сошёлся за {ITER_MAX} итераций"
            )

        return state

    def _solve_debt(self, state: YearState, prev: YearState) -> YearState:
        """Диспетчер режимов долга."""
        mode = self._c.debt.mode
        if mode == "schedule_based":
            return self._solve_debt_schedule(state, prev)
        elif mode == "optimizer":
            return self._solve_debt_optimizer(state, prev)
        else:
            return self._solve_debt_parametric(state, prev)

    def _solve_debt_parametric(self, state: YearState, prev: YearState) -> YearState:
        """
        Standard mode debt — упрощённая но экономически корректная модель.

        Логика:
        1. Определяем целевой общий долг (Net Debt / EBITDA target или % Revenue)
        2. ST debt = обязательная амортизация + RC остаток
        3. LT debt = total - ST
        4. RC: draw если cash < min_cash, repay если cash > min_cash + buffer
        5. Рефинанс: если ST > FCF → сигнал риска (не блокирует модель)

        ST/LT разделение важно для:
        - Оценки рефинанс риска (ST > FCF → нужен рефинанс)
        - Ковенант расчётов (Net Debt/EBITDA)
        - Interest coverage (EBIT / interest_expense)
        """
        cfg = self._c.debt

        # ── 1. Определяем целевой общий долг ──────────────────────────────
        prev_total = prev.short_term_debt + prev.long_term_debt

        # Приоритет: net_debt_ebitda_target > target_pct_revenue > carry
        target_total = None

        # Net Debt/EBITDA target (лучшая практика)
        nd_ebitda_target = getattr(cfg, 'net_debt_ebitda_target', None)
        if nd_ebitda_target and state.ebitda > 0:
            target_net_debt = nd_ebitda_target * state.ebitda
            target_total = target_net_debt + state.cash  # cash пока предыдущий

        # % от Revenue fallback
        if target_total is None:
            pct_rev = getattr(cfg, 'target_pct_revenue', None) or 0.0
            if pct_rev > 0:
                target_total = state.revenue * pct_rev
            else:
                target_total = prev_total  # carry forward

        # Ограничиваем изменение: не более 20% total debt в год (реализм)
        max_change = prev_total * 0.20 if prev_total > 0 else abs(target_total) * 0.20
        if abs(target_total - prev_total) > max_change:
            target_total = prev_total + max_change * (1 if target_total > prev_total else -1)

        target_total = max(0.0, target_total)

        # ── 2. ST debt = обязательная амортизация + RC ────────────────────
        # Обязательная амортизация из истории (EWA ratio ST/Total)
        hist_st_ratio = self._h.preprocess.get("debt", {}).get("st_debt_ratio_recommended")
        if isinstance(hist_st_ratio, dict):
            hist_st_ratio = hist_st_ratio.get(-1) or hist_st_ratio.get(max(hist_st_ratio.keys()))

        # Если нет из препроцессора — используем исторический ST/Total
        if not hist_st_ratio:
            prev_hist_total = prev.short_term_debt + prev.long_term_debt
            hist_st_ratio = (prev.short_term_debt / prev_hist_total
                            if prev_hist_total > 0 else 0.15)

        # Clamp: ST ratio 5%-40% (реалистичный диапазон)
        hist_st_ratio = max(0.05, min(0.40, hist_st_ratio or 0.15))

        # Обязательная ST амортизация (текущая порция LT долга)
        mandatory_st = prev.long_term_debt * hist_st_ratio * 0.5  # ~50% ST ratio = амортизация

        # RC остаток — draw/repay в зависимости от cash gap
        min_cash = getattr(cfg.rc, 'min_cash', 0) if hasattr(cfg, 'rc') else 0
        rc_limit  = getattr(cfg.rc, 'limit',    0) if hasattr(cfg, 'rc') else 0

        # Приблизительные CFO/CFI — нужны ниже для refinancing risk диагностики
        approx_cfo = (state.net_income + state.total_da + state.cfo_wc_delta
                     - state.cfo_interest_paid - state.cfo_taxes_paid)
        approx_cfi = state.cfi_capex + state.cfi_disposal_proceeds

        # Используем предварительную оценку cash если доступна (joint iteration)
        if hasattr(state, '_cash_estimate') and state._cash_estimate is not None:
            cash_before_debt = state._cash_estimate
        else:
            cash_before_debt = prev.cash + approx_cfo + approx_cfi

        # RC draw/repay
        rc_draw = 0.0
        rc_repay = 0.0
        if cash_before_debt < min_cash:
            # Нужен draw
            rc_draw = min(min_cash - cash_before_debt, rc_limit)
        elif cash_before_debt > min_cash * 2 and prev.short_term_debt > mandatory_st:
            # Избыточный cash — гасим RC
            rc_repay = min(cash_before_debt - min_cash * 2,
                          prev.short_term_debt - mandatory_st)

        # Итоговый ST debt
        st_debt = mandatory_st + rc_draw - rc_repay
        st_debt = max(0.0, st_debt)

        # ── 3. LT debt = total - ST ───────────────────────────────────────
        lt_debt = max(0.0, target_total - st_debt)

        # ── 4. Cash flows от долговых операций ───────────────────────────
        new_total = st_debt + lt_debt
        delta = new_total - prev_total

        state.short_term_debt = st_debt
        state.long_term_debt  = lt_debt

        if delta > 0:
            state.cff_debt_issuance  = delta
            state.cff_debt_repayment = 0.0
        else:
            state.cff_debt_issuance  = 0.0
            state.cff_debt_repayment = delta  # отрицательное

        # ── 5. Interest expense ───────────────────────────────────────────
        avg_rate = getattr(cfg, 'avg_rate_pct', None)
        if not avg_rate:
            _debt_pp = self._h.preprocess.get('debt', {})
            _rate_rec = _debt_pp.get('avg_interest_rate_recommended')
            if isinstance(_rate_rec, dict): _rate_rec = _rate_rec.get(-1)
            avg_rate = float(_rate_rec) if _rate_rec else None
        avg_rate = avg_rate or 0.05  # last-resort: 5% neutral rate
        avg_debt = (prev_total + new_total) / 2.0
        gross_interest = avg_debt * avg_rate

        # Капитализированные проценты (убывают по мере завершения стройки)
        # Приоритет: year-specific исторические значения, затем decay от EWA recommended
        _capex_pp = self._h.preprocess.get("capex", {})
        _cap_series = _capex_pp.get("capitalized_interest_pct", {})
        _cap_rec    = _capex_pp.get("capitalized_interest_pct_recommended") or 0.0
        if isinstance(_cap_rec, dict):
            _cap_rec = _cap_rec.get(-1, 0.0) or 0.0
        years_from_base = state.year - self._h.base_year
        if isinstance(_cap_series, dict) and state.year in _cap_series:
            cap_pct = float(_cap_series[state.year])          # фактическое значение для года
        else:
            cap_pct = max(0.0, float(_cap_rec) - 0.15 * years_from_base)

        state.interest_expense_debt = gross_interest * (1.0 - cap_pct)
        state.interest_expense      = state.interest_expense_debt + abs(state.interest_expense_leases or 0)

        # ── 6. Рефинанс риск (диагностика, не блокирует) ─────────────────
        fcf = approx_cfo + approx_cfi
        if st_debt > 0 and fcf < st_debt * 0.5:
            logger.debug(
                f"  {state.year} REFIN RISK: ST={st_debt/1e6:.0f}M FCF={fcf/1e6:.0f}M "
                f"(FCF/ST={fcf/st_debt:.1f}x)"
            )

        return state

    def _solve_debt_schedule(self, state: YearState, prev: YearState) -> YearState:
        """
        Schedule-based debt: читаем corkscrew из debt_instruments.schedule.
        Если schedule для данного года не найден (прогнозные годы) —
        переносим долг из предыдущего года и считаем проценты параметрически.
        """
        year = state.year
        total_interest  = 0.0
        total_st        = 0.0
        total_lt        = 0.0
        total_issuance  = 0.0
        total_repayment = 0.0

        scheduled_instruments = [
            inst for inst in self._h.debt_instruments
            if inst.schedule and year in inst.schedule
        ]

        if scheduled_instruments:
            for inst in scheduled_instruments:
                row = inst.schedule[year]
                interest   = float(row.get("interest_expense", 0))
                closing    = float(row.get("closing_balance", 0))
                draw       = float(row.get("draw", 0))
                repay      = float(row.get("repay_mandatory", 0) or 0) + \
                             float(row.get("repay_voluntary", 0) or 0)
                classif    = str(row.get("classification", "LT")).upper()

                total_interest  += interest
                total_issuance  += draw
                total_repayment += repay

                if classif == "ST" or inst.is_revolving:
                    total_st += closing
                else:
                    total_lt += closing
        else:
            # Нет schedule для прогнозного года — переносим долг и считаем проценты
            total_st = prev.short_term_debt
            total_lt = prev.long_term_debt
            # Используем incurred rate (gross, до капитализации) если доступен из препроцессора
            int_pp = self._h.preprocess.get("interest", {})
            incurred_series = int_pp.get("interest_incurred", {})
            base_yr = self._h.base_year
            incurred_base = float(incurred_series.get(base_yr, 0)) if isinstance(incurred_series, dict) else 0.0
            total_debt_base = (prev.short_term_debt + prev.long_term_debt) or 1.0
            if incurred_base > 0:
                # Incurred rate из истории — но config.avg_rate_pct может быть выше (стресс-шок)
                historical_rate = incurred_base / total_debt_base
                gross_rate = max(historical_rate, self._c.debt.avg_rate_pct)
            else:
                gross_rate = self._c.debt.avg_rate_pct + self._c.debt.general_rate_delta_pct
            gross_interest = (total_st + total_lt) * gross_rate
            # Применяем cap_pct: year-specific из препроцессора, затем decay
            _capex_pp2  = self._h.preprocess.get("capex", {})
            _cap_series2 = _capex_pp2.get("capitalized_interest_pct", {})
            _cap_rec2    = _capex_pp2.get("capitalized_interest_pct_recommended") or 0.0
            if isinstance(_cap_rec2, dict):
                _cap_rec2 = _cap_rec2.get(-1, 0.0) or 0.0
            years_elapsed = year - base_yr
            if isinstance(_cap_series2, dict) and year in _cap_series2:
                cap_pct = float(_cap_series2[year])
            else:
                cap_pct = max(0.0, float(_cap_rec2) - 0.15 * years_elapsed)
            capitalized = gross_interest * cap_pct
            total_interest = max(0.0, gross_interest - capitalized)
            logger.debug(
                f"  {year}: debt carry-forward STD={total_st:.0f} LTD={total_lt:.0f} "
                f"gross_rate={gross_rate:.3f} cap_pct={cap_pct:.2f} int={total_interest:.0f}"
            )

        # RC: absorb cash gap если нужно
        if self._c.debt.rc.enabled and self._c.debt.rc.limit > 0:
            state, rc_draw, rc_repay = self._apply_rc(state, prev, total_st, total_lt)
            total_st       += rc_draw - rc_repay
            total_issuance += rc_draw
            total_repayment += rc_repay
            rc_rate = self._c.debt.rc.rate_spread + self._c.debt.avg_rate_pct
            total_interest += rc_draw * rc_rate

        state.short_term_debt       = total_st
        state.long_term_debt        = total_lt
        state.interest_expense_debt = total_interest
        state.interest_expense      = total_interest + abs(state.interest_expense_leases or 0)

        # CFF: явные движения долга (delta-based, как в модели Русала)
        delta_st    = state.short_term_debt - prev.short_term_debt
        delta_lt    = state.long_term_debt  - prev.long_term_debt
        delta_total = delta_st + delta_lt

        if delta_total >= 0:
            state.cff_debt_issuance  = delta_total
            state.cff_debt_repayment = 0.0
        else:
            state.cff_debt_issuance  = 0.0
            state.cff_debt_repayment = delta_total

        return state

    def _build_instruments_open_from_raw(self) -> List[DebtInstrumentOpen]:
        """
        First-year initialisation: convert DebtInstrument → DebtInstrumentOpen.
        Called once; subsequent years use self._debt_instruments_state directly.
        """
        cfg = self._c.debt
        forecast_years = sorted(self._c.forecast_years)
        result: List[DebtInstrumentOpen] = []

        for inst in self._h.debt_instruments:
            opening = inst.opening_balance or 0.0

            raw_rate = inst.interest_rate or 0.0
            rate = raw_rate / 100.0 if raw_rate > 1.0 else raw_rate
            if rate == 0.0:
                rate = cfg.avg_rate_pct
            # Floating-rate instruments: store spread only; base rate added per-year in solver
            if getattr(inst, "rate_type", "fixed") == "floating":
                rate = max(0.001, rate + getattr(cfg, "general_rate_delta_pct", 0.0))

            # Determine kind: db_type first, fallback to name matching
            db_type_lower = (inst.db_type or "").lower()
            if "lease" in db_type_lower or "lease" in inst.instrument_name.lower():
                kind = InstrumentKind.LEASE
            elif db_type_lower in ("revolving",) or inst.is_revolving:
                kind = InstrumentKind.RC
            elif db_type_lower in ("bond_fixed", "bond_float"):
                kind = InstrumentKind.BOND_BULLET
            elif db_type_lower in ("term_bullet",):
                kind = InstrumentKind.BULLET
            elif db_type_lower in ("term_amort",):
                kind = InstrumentKind.TERM_AMORT
            else:
                kind = infer_kind(inst.instrument_name, inst.db_type)

            # Parse maturity_date "YYYY-MM-DD" / "YYYY-MM" → int year
            maturity: Optional[int] = None
            if inst.maturity_date:
                try:
                    maturity = int(str(inst.maturity_date)[:4])
                except (ValueError, TypeError):
                    maturity = None

            # Build amort_schedule
            amort_schedule: Dict[int, float] = {}
            if inst.schedule:
                for yr, row in inst.schedule.items():
                    amt = float(row.get('repay_mandatory', 0) or 0)
                    if amt > 0:
                        amort_schedule[int(yr)] = amt

            if not amort_schedule and opening > 0 and maturity is not None:
                amort_profile = (inst.amortization_profile or "bullet").lower()
                if amort_profile == "bullet":
                    amort_schedule = {maturity: opening}
                elif amort_profile == "amort":
                    remaining_yrs = [y for y in forecast_years if y <= maturity]
                    if remaining_yrs:
                        annual_pay = opening / len(remaining_yrs)
                        amort_schedule = {y: annual_pay for y in remaining_yrs}

            result.append(DebtInstrumentOpen(
                instrument_id=inst.instrument_id,
                name=inst.instrument_name,
                kind=kind,
                opening=opening,
                rate=rate,
                limit=inst.committed_amount or 0.0,
                maturity=maturity,
                amort_schedule=amort_schedule,
                priority=0,
                classification="LT" if kind not in (InstrumentKind.RC,) else "ST",
                callable_flag=bool(getattr(inst, 'callable_flag', False)),
            ))

        # ── Reconciliation instrument ─────────────────────────────────────────
        # The debt_schedule may not track every instrument (e.g. near-maturity STD,
        # partially-repaid bonds).  Sum non-lease openings vs historical BS debt;
        # any gap would silently drop from the BS without a CFF entry, causing a
        # permanent BS imbalance.  A residual instrument absorbs the gap so the
        # optimizer starts from the correct total debt level.
        base_state = self._h.base_year_state
        if base_state is not None:
            hist_total = (base_state.long_term_debt or 0) + (base_state.short_term_debt or 0)
            non_lease_total = sum(
                inst_obj.opening for inst_obj in result
                if inst_obj.kind not in (InstrumentKind.LEASE,)
            )
            gap = hist_total - non_lease_total
            if gap > 1e3:  # > $1K — real gap, not floating-point noise
                lt_rates = [i.rate for i in result
                            if i.kind not in (InstrumentKind.LEASE,) and i.rate > 0]
                avg_r = sum(lt_rates) / len(lt_rates) if lt_rates else cfg.avg_rate_pct
                last_yr = max(forecast_years) if forecast_years else self._h.base_year + 5
                result.append(DebtInstrumentOpen(
                    instrument_id="_debt_residual",
                    name="DebtResidual",
                    kind=InstrumentKind.BOND_BULLET,
                    opening=gap,
                    rate=avg_r,
                    maturity=last_yr,
                    amort_schedule={last_yr: gap},
                    priority=2,          # repaid last (after scheduled instruments)
                    classification="LT",
                ))
                logger.debug(
                    f"  Debt reconciliation: hist={hist_total/1e6:.0f}M  "
                    f"instruments={non_lease_total/1e6:.0f}M  residual={gap/1e6:.0f}M"
                )

        return result

    def _solve_debt_optimizer(self, state: YearState, prev: YearState) -> YearState:
        """
        Optimizer: DebtOptimizer.solve_year — full 7-step algorithm.
        Instruments state persists between forecast years so refi mutations
        (maturity rollover, rate adjustment) and new instruments survive.
        Fallback to parametric if no instruments.
        """
        if not self._h.debt_instruments:
            logger.debug(f"  {state.year}: optimizer — нет инструментов, fallback to parametric")
            return self._solve_debt_parametric(state, prev)

        cfg = self._c.debt

        # Initialise persistent state on very first year
        if not self._debt_instruments_state:
            self._debt_instruments_state = self._build_instruments_open_from_raw()

        # Snapshot-restore: the iterative year loop calls _solve_debt multiple times
        # (for interest/NI/tax convergence).  Without a restore, each iteration
        # accumulates state mutations (new-money appends, opening updates), producing
        # ballooning debt and BS diffs.  Solution:
        #  • First call for a new year  → snapshot current openings
        #  • Subsequent calls same year → restore to snapshot, drop transient instruments
        if self._debt_snapshot_year != state.year:
            # New year: take snapshot before any mutation
            self._debt_year_snapshot = {
                inst.instrument_id: inst.opening
                for inst in self._debt_instruments_state
            }
            self._debt_snapshot_year = state.year
        else:
            # Re-iteration: restore openings and remove instruments added this year
            snap_ids = set(self._debt_year_snapshot.keys())
            self._debt_instruments_state = [
                inst for inst in self._debt_instruments_state
                if inst.instrument_id in snap_ids
            ]
            for inst in self._debt_instruments_state:
                inst.opening = self._debt_year_snapshot[inst.instrument_id]

        instruments_open = self._debt_instruments_state

        # Передаём estimated cash в optimizer для корректного RC решения
        if hasattr(state, '_cash_estimate') and state._cash_estimate is not None:
            state_cash_for_solver = state._cash_estimate
        else:
            state_cash_for_solver = prev.cash

        # Приближённые CFO/CFI для определения cash needs
        # Use actual CFO from prior iteration if available (much more accurate than NI+DA+WC approx)
        if hasattr(state, '_actual_cfo_est') and state._actual_cfo_est is not None:
            approx_cfo = state._actual_cfo_est
        else:
            approx_cfo = (
                state.net_income
                + state.total_da
                + state.cfo_wc_delta
            )
        approx_cfi = state.cfi_capex + state.cfi_disposal_proceeds

        # ST/LT split: covenant breach acceleration instruments (populated by covenants module)
        covenant_breached = getattr(self, '_covenant_breach_instruments', set())

        # ── Voluntary prepay cap ─────────────────────────────────────────
        # Two independent caps (the SMALLER one binds):
        # 1. FCF cap: max voluntary_prepay = max_pct × max(0, FCF)
        # 2. Debt floor: don't reduce net_debt below target × EBITDA
        _vol_cap = None
        _max_prepay_pct = getattr(self._c, 'max_voluntary_prepay_pct_fcf', 1.0) or 1.0
        _target_nd_eb = getattr(self._c, 'target_net_debt_ebitda', 0.0) or 0.0

        _fcf_est = approx_cfo + approx_cfi
        # Cap 1: FCF-based limit
        if _max_prepay_pct < 1.0 and _fcf_est > 0:
            _vol_cap = _fcf_est * _max_prepay_pct
        # Cap 2: debt floor — net debt must stay above target
        if _target_nd_eb > 0 and state.ebitda > 0:
            _total_debt_now = sum(inst.opening for inst in instruments_open if not inst.is_lease)
            _current_nd = _total_debt_now - (prev.cash or 0)
            _min_nd = _target_nd_eb * state.ebitda
            _floor_cap = max(0.0, _current_nd - _min_nd)
            _vol_cap = min(_vol_cap, _floor_cap) if _vol_cap is not None else _floor_cap

        solve_result: DebtSolveResult = DebtOptimizer.solve_year(
            year=state.year,
            opening_cash=state_cash_for_solver,
            cfo=approx_cfo,
            cfi=approx_cfi,
            instruments_open=instruments_open,
            min_cash=self._c.min_cash or cfg.rc.min_cash,
            refi_mode=cfg.refinancing.mode if cfg.refinancing.enabled else "none",
            refi_extend_years=cfg.refinancing.extend_years,
            refi_rate_adj_pct=cfg.refinancing.rate_adjustment,
            refi_fees_bps=cfg.refinancing.fees_pct * 10_000.0,
            allow_new_money=True,
            covenant_breach_instruments=covenant_breached,
            max_voluntary_repay=_vol_cap,
            cbr_key_rate=(cfg.cbr_key_rate_forecast or {}).get(
                state.year, list((cfg.cbr_key_rate_forecast or {}).values())[-1]
                if cfg.cbr_key_rate_forecast else 0.0
            ),
        )

        # Bug 1 fix: update opening balances for next year from this year's closings
        closing_by_id: Dict[str, float] = {
            ln.instrument_id: ln.closing for ln in solve_result.lines
        }
        for inst in instruments_open:
            inst.opening = closing_by_id.get(inst.instrument_id, inst.opening)

        # Bug 2 fix: persist new instruments from refi mode="new"
        for new_inst in solve_result.new_instruments:
            # Set opening = refi draw amount (already carried in refi_draw on the line)
            matching_line = next(
                (ln for ln in solve_result.lines if ln.instrument_id == new_inst.instrument_id),
                None,
            )
            if matching_line is not None:
                new_inst.opening = matching_line.closing
            self._debt_instruments_state.append(new_inst)

        # Build next-year mandatory hint (informational; ST/LT split now uses
        # instrument maturity/amort_schedule directly in DebtOptimizer Step 6)
        next_year = state.year + 1
        hint: Dict[str, float] = {}
        for inst in self._debt_instruments_state:
            nxt = inst.amort_schedule.get(next_year, 0.0)
            if inst.maturity == next_year and inst.kind in (
                InstrumentKind.BOND_BULLET, InstrumentKind.BULLET
            ):
                nxt = inst.opening
            if nxt > 0:
                hint[inst.instrument_id] = nxt
        self._debt_next_mandatory_hint = hint

        # Сохраняем строки за этот год (для записи в debt_schedule после схождения)
        self._last_debt_lines = solve_result.lines

        # Применяем результат в state
        state.short_term_debt       = solve_result.st_debt
        state.long_term_debt        = solve_result.lt_debt
        # Capitalized interest (ASC 835-20): reduce IS interest by cap_pct
        _capex_pp = self._h.preprocess.get('capex', {})
        _cap_rec = _capex_pp.get('capitalized_interest_pct_recommended') or 0.0
        if isinstance(_cap_rec, dict): _cap_rec = _cap_rec.get(-1, 0.0)
        _cap_pct = max(0.0, float(_cap_rec or 0))
        _gross_debt_interest = solve_result.interest_expense_total
        _net_debt_interest = _gross_debt_interest * (1.0 - _cap_pct)
        state.interest_expense_debt = _net_debt_interest
        # Total interest = debt (net of cap) + finance lease interest (ASC 842)
        state.interest_expense      = _net_debt_interest + abs(state.interest_expense_leases or 0)

        # CFF: debt flows — fees excluded (they flow through IS as loss_on_debt_ext)
        total_draw  = sum(ln.draw + ln.refi_draw for ln in solve_result.lines)
        total_repay = sum(ln.repay for ln in solve_result.lines)
        state.cff_debt_issuance  = total_draw
        state.cff_debt_repayment = -total_repay

        # Refi fees → P&L as loss_on_debt_extinguishment
        # Cash path: fees reduce CFO (via lower NI), NOT CFF — avoids double-count
        total_refi_fees = sum(ln.refi_fees for ln in solve_result.lines)
        state.loss_on_debt_extinguishment = total_refi_fees

        return state

    def _apply_rc(
        self, state: YearState, prev: YearState,
        current_st: float, current_lt: float
    ) -> Tuple[YearState, float, float]:
        """RC draw/sweep для поддержания min_cash."""
        min_cash = self._c.debt.rc.min_cash
        rc_limit = self._c.debt.rc.limit

        # Приблизительный CFO без RC
        approx_cfo = (
            state.net_income
            + state.total_da
            + state.cfo_wc_delta
        )
        approx_cash = (
            prev.cash
            + approx_cfo
            + state.cfi_capex
            + state.cfi_disposal_proceeds
        )

        rc_draw   = 0.0
        rc_repay  = 0.0

        if approx_cash < min_cash:
            # Нужно занять
            rc_draw = min(min_cash - approx_cash, rc_limit)
        elif approx_cash > min_cash * 1.5 and prev.short_term_debt > 0:
            # Есть лишний кеш → погасить RC
            rc_repay = min(approx_cash - min_cash, prev.short_term_debt)

        state.cff_revolver_draws      = rc_draw
        state.cff_revolver_repayments = -rc_repay
        return state, rc_draw, rc_repay

    # ── BS другие статьи ──────────────────────────────────────────────────────

    def _solve_bs_other(self, state: YearState, prev: YearState) -> YearState:
        from .blocks.bs_other import solve_bs_other
        return solve_bs_other(state, prev)

    def _solve_cash_from_cf(self, state: YearState, prev: YearState) -> YearState:
        from .blocks.cash import solve_cash_from_cf
        return solve_cash_from_cf(state, prev, self._c)

    def _solve_bs_totals(self, state: YearState) -> YearState:
        from .blocks.bs_totals import solve_bs_totals
        return solve_bs_totals(state)

    def _solve_cf(self, state: YearState, prev: YearState) -> YearState:
        """
        Строит полный CF Statement (indirect method, US GAAP / IFRS).

        Структура:
        ── CFO (Operating) ──────────────────────────────────────────
        Net Income
        + D&A (non-cash add-back)
        + Deferred Tax (non-cash)
        + Δ Working Capital (AR, Inv, AP, taxes payable, interest payable, other)
        + Operating Lease Payments (ASC 842 / IFRS 16)
        + Other CFO
        = CFO Total

        ── CFI (Investing) ──────────────────────────────────────────
        - CapEx
        + Disposal Proceeds
        ± Acquisitions / Divestitures
        + Other CFI
        = CFI Total

        ── CFF (Financing) ──────────────────────────────────────────
        + Debt Issuance
        - Debt Repayment
        + Revolver Draws
        - Revolver Repayments
        - Finance Lease Principal
        - Dividends Paid
        - Share Buybacks
        + Share Issuance
        + Other CFF
        = CFF Total

        ── Bridge ───────────────────────────────────────────────────
        Cash Opening + CFO + CFI + CFF = Cash Ending
        """
        # ── CFO ──────────────────────────────────────────────────────
        # 1. Net Income (link из IS)
        state.cfo_net_income = state.net_income

        # 2. D&A add-back (non-cash)
        state.cfo_total_da = state.total_da

        # 3. Deferred Tax (non-cash) — приближение через Δ(DTA - DTL)
        if state.cfo_deferred_tax == 0.0:
            delta_dta = (state.dta or 0) - (prev.dta or 0)
            delta_dtl = (state.dtl or 0) - (prev.dtl or 0)
            state.cfo_deferred_tax = -delta_dta + delta_dtl

        # 4. Δ Working Capital — cfo_change_ar/inv/ap уже заполнены в _solve_wc
        # Use abs() for liability items: DB stores historical liabilities as negative,
        # while corkscrews output positive values. abs() normalises the sign convention
        # so that delta = actual BS change regardless of which year is base vs forecast.
        state.cfo_change_taxes_payable = (
            abs(state.taxes_payable or 0) - abs(prev.taxes_payable or 0)
        )
        state.cfo_change_interest_payable = (
            abs(state.interest_payable or 0) - abs(prev.interest_payable or 0)
        )
        delta_payroll      = abs(state.payroll_payable or 0) - abs(prev.payroll_payable or 0)
        delta_other_cl     = abs(state.other_cl or 0) - abs(prev.other_cl or 0)
        delta_other_ca     = (state.other_ca or 0) - (prev.other_ca or 0)
        # Lease liability changes (principal repayments) must be in CF to keep BS balanced.
        # dep_rou is in total_da (non-cash add-back); op_lease_pmt captures total cash out;
        # Only FINANCE lease LL changes belong in CFO WC adjustments.
        # Operating lease cash flows are already embedded in NI via SGA (no separate CFO line);
        # adding ΔOp_LL here would double-count the cash impact.
        delta_lease_lia    = (
            abs(state.lease_liab_cur_finance or 0) - abs(prev.lease_liab_cur_finance or 0) +
            abs(state.lease_liab_ncur_finance or 0) - abs(prev.lease_liab_ncur_finance or 0)
        )
        state.cfo_change_other_wc = -delta_other_ca + delta_other_cl + delta_payroll + delta_lease_lia

        state.cfo_wc_delta = (
            (state.cfo_change_ar or 0) +
            (state.cfo_change_inv or 0) +
            (state.cfo_change_ap or 0) +
            state.cfo_change_taxes_payable +
            state.cfo_change_interest_payable +
            state.cfo_change_other_wc
        )

        # 5. Operating Lease Payments: NOT added to cfo_total — full payment already in NI via SGA.
        # rou_amort_operating is NOT in total_da to avoid IS double-count; delta_lease_lia in other_wc
        # captures the principal repayment on the liability side for BS balance.
        op_lease_pmt = 0.0  # set to 0; cfo_lease_payments_operating stored on state for reference

        # 6. Other CFO — EWA от исторических прочих CFO позиций
        pp_ext = self._h.preprocess.get('extended', {})
        other_cfo_hist = pp_ext.get('other_cfo_recommended')
        if isinstance(other_cfo_hist, dict):
            other_cfo_hist = other_cfo_hist.get(-1, 0.0)
        state.cfo_other = float(other_cfo_hist or 0.0)

        # 7. CFO Total (indirect method)
        # Disposal gains in NI are investing-activity cash flows → subtract from CFO.
        # Full proceeds remain in CFI; gain × (1-t) is in NI (RE); tax on gain is in WC via taxes_payable.
        disposal_gain_adj = -(state.ppe_disposal_gain or 0.0)
        state.cfo_total = (
            state.cfo_net_income +
            state.cfo_total_da +
            state.cfo_deferred_tax +
            state.cfo_wc_delta +
            disposal_gain_adj +
            op_lease_pmt +
            state.cfo_other
        )

        # Supplemental disclosures (не входят в cfo_total по indirect method)
        # cfo_interest_paid и cfo_taxes_paid задаются в _solve_interest_payable / _solve_tax_block

        # ── CFI ──────────────────────────────────────────────────────
        # cfi_acquisitions: zeroed in forecast — one-off historical acquisitions
        # (e.g. Big River Steel) inflate the EWA without a corresponding BS asset
        # being modeled, causing permanent BS drift (assets ≠ liabilities+equity).
        # If explicit acquisition modeling is needed, add a corresponding asset update.
        state.cfi_acquisitions = 0.0

        state.cfi_total = (
            (state.cfi_capex or 0.0) +
            (state.cfi_disposal_proceeds or 0.0) +
            state.cfi_acquisitions +
            (state.cfi_other or 0.0)
        )

        # ── CFF ──────────────────────────────────────────────────────
        state.cff_total = (
            (state.cff_debt_issuance or 0.0) +
            (state.cff_debt_repayment or 0.0) +
            (state.cff_revolver_draws or 0.0) +
            (state.cff_revolver_repayments or 0.0) +
            (state.cff_finance_lease_principal or 0.0) +  # FIX: было пропущено
            (state.cff_dividends or 0.0) +
            (state.cff_buybacks or 0.0) +
            (state.cff_equity_issuance or 0.0) +
            (state.cff_other or 0.0)
        )

        # ── Bridge ───────────────────────────────────────────────────
        state.cf_cash_opening = prev.cash
        state.cf_net_change   = state.cfo_total + state.cfi_total + state.cff_total
        state.cf_cash_ending  = state.cf_cash_opening + state.cf_net_change

        # CF управляет cash — нет plug reconciliation.
        # state.cash будет установлен в _solve_cash_plug из cf_cash_ending.

        return state
