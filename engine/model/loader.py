"""
ModelInputLoader — загружает данные из БД в HistoricState + ModelConfig.
Единственная точка где модель обращается к Repository.
После load() ядро модели работает только с dataclasses.
"""

from __future__ import annotations

import logging
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..database.repository import Repository
from .inputs import (
    DebtInstrument, DebtSettings, ForecastMethod, ForecastMethodConfig,
    HistoricState, LeaseDrivers, LeaseParams, ModelConfig, RCSettings,
    RefinancingSettings, YearState,
)

logger = logging.getLogger(__name__)


class ModelInputLoader:
    """
    Загружает все входные данные для модели из БД + project.yaml.

    Использование:
        with Repository() as repo:
            loader = ModelInputLoader("us_steel", repo, config_path)
            historic, config = loader.load()
    """

    def __init__(
        self,
        company_id: str,
        repo: Repository,
        config_path: Optional[Path] = None,
        scenario_name: str = "base",
    ) -> None:
        self.company_id = company_id
        self._repo = repo
        self._config_path = config_path
        self._scenario_name = scenario_name

    def load(self) -> tuple[HistoricState, ModelConfig]:
        """Главный метод — возвращает (HistoricState, ModelConfig)."""
        # 1. Загрузить YAML-конфиг
        cfg = self._load_yaml_config()

        # 2. Построить ModelConfig
        model_config = self._build_model_config(cfg)

        # 3. Загрузить историю из БД
        historic = self._load_historic_state(model_config)

        # 4. Загрузить препроцессор-метрики
        self._load_preprocess(historic, model_config)

        # 5. Заполнить драйверы из препроцессора (если не переопределены в YAML)
        self._fill_drivers_from_preprocess(model_config, historic)

        # 6. Загрузить долговые инструменты
        self._load_debt_instruments(historic, model_config)

        # 7. Загрузить макро-прогнозы
        self._load_macro_forecasts(historic, model_config)

        # 8. Построить base_year_state из последнего исторического года
        self._is_income_sign = model_config.is_income_sign
        historic.base_year_state = self._build_base_year_state(
            historic, model_config.history_end_year
        )

        # 9. Загружаем сегментную модель если настроена
        model_config._segment_model = None
        try:
            cfg = self._load_yaml_config()
            mode = cfg.get("model", {}).get("mode", "custom")
            mode_cfg = cfg.get("model", {}).get(mode, {})
            rev_cfg = mode_cfg.get("revenue", {})
            if rev_cfg.get("segment_modeling", False):
                from .segment_revenue import SegmentRevenueModel
                # Build combined macro (history + forecasts) for OLS chain-link
                _factors_needed = set(
                    f for sc in rev_cfg.get("segments", {}).values()
                    for f in sc.get("price_factors", []) + sc.get("volume_factors", [])
                )
                _combined_macro = dict(historic.macro_forecasts)
                for _fn in _factors_needed:
                    _hist = self._repo.get_macro_factor(_fn)
                    if _hist:
                        _combined = {**_hist, **_combined_macro.get(_fn, {})}
                        _combined_macro[_fn] = _combined
                seg_model = SegmentRevenueModel.from_yaml_config(
                    rev_cfg, _combined_macro,
                )
                if seg_model:
                    forecast_years = list(range(
                        model_config.forecast_start_year,
                        model_config.forecast_end_year + 1,
                    ))
                    seg_forecasts = seg_model.forecast(forecast_years)
                    model_config._segment_model = seg_model.total_revenue(seg_forecasts)
                    logger.info(
                        f"  Сегментная Revenue модель: {len(seg_model.segments)} сегментов"
                    )
        except Exception as e:
            logger.debug(f"  Сегментная модель: {e}")

        logger.info(
            f"Входные данные загружены: {self.company_id} "
            f"история={historic.years[0]}–{historic.base_year} "
            f"прогноз={model_config.forecast_start_year}–{model_config.forecast_end_year}"
        )
        return historic, model_config

    # ── YAML конфиг ───────────────────────────────────────────────────────────

    def _load_yaml_config(self) -> Dict[str, Any]:
        if self._config_path and self._config_path.exists():
            with open(self._config_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    def _build_model_config(self, cfg: Dict[str, Any]) -> ModelConfig:
        model_cfg = cfg.get("model", {})
        mode = model_cfg.get("mode", "standard")
        std_cfg = model_cfg.get("standard", {})
        custom_cfg = model_cfg.get(mode, {}) if mode != "standard" else {}
        # Merge: standard is the base, custom overrides at the section level
        # Any section (debt, ppe, wc, ...) not present in custom falls back to standard
        mode_cfg = {**std_cfg, **custom_cfg}
        periods_custom = custom_cfg.get("periods", std_cfg.get("periods", {}))
        periods = periods_custom
        company_cfg = cfg.get("company", {})

        # Debt settings: prefer custom section if present, else standard
        debt_raw = custom_cfg.get("debt", std_cfg.get("debt", {}))
        rc_raw = debt_raw.get("rc", {})
        _refi_cfg = debt_raw.get("refinancing", {})
        ref_raw = _refi_cfg.get("simple", _refi_cfg)  # flat or nested under "simple"

        debt_mode = debt_raw.get("mode", "auto")
        # "full" is a YAML alias for "optimizer" (v2_solver)
        if debt_mode == "full":
            debt_mode = "optimizer"
        if debt_mode == "auto":
            # Определяем автоматически ниже после загрузки БД
            debt_mode = self._detect_debt_mode()

        # min_cash: YAML → препроцессор → дефолт 0
        yaml_min_cash = rc_raw.get("min_cash", 0)
        if yaml_min_cash and float(yaml_min_cash) > 0:
            min_cash_final = float(yaml_min_cash)
        else:
            pp_debt = self._repo.get_preprocess(self.company_id, "debt")
            pp_min_cash = pp_debt.get("min_cash_recommended")
            if isinstance(pp_min_cash, dict):
                pp_min_cash = pp_min_cash.get(-1)
            min_cash_final = float(pp_min_cash) if pp_min_cash else 0.0

        rc = RCSettings(
            enabled=rc_raw.get("enable", True),
            limit=rc_raw.get("limit", 0.0),
            min_cash=min_cash_final,
            rate_spread=rc_raw.get("rate_spread", 0.03),
        )
        ref = RefinancingSettings(
            enabled=debt_raw.get("refinancing", {}).get("enable", True),
            mode=debt_raw.get("refinancing", {}).get("mode", "simple"),
            extend_years=ref_raw.get("extend_years", 5),
            rate_adjustment=ref_raw.get("rate_adjustment", 0.0),
            fees_pct=ref_raw.get("fees_pct", 0.001),
        )
        def _pct(v, default):
            """YAML может хранить ставки как 5.0 (%) или 0.05 (доли). Нормализуем."""
            if v is None:
                return default
            v = float(v)
            return v / 100.0 if v > 1.0 else v

        debt_settings = DebtSettings(
            mode=debt_mode,
            target_pct_revenue=debt_raw.get("target_pct_revenue", 0.35),
            avg_rate_pct=_pct(debt_raw.get("avg_rate_pct"), 0.05),
            iter_max=debt_raw.get("iter_max", 15),
            tol=float(debt_raw.get("tol", 1e-6)),
            rc=rc,
            refinancing=ref,
            icr_min=debt_raw.get("covenants", {}).get("icr_min", 2.0),
            lev_max=debt_raw.get("covenants", {}).get("lev_max", 3.5),
            cbr_key_rate_forecast={
                int(k): float(v)
                for k, v in (debt_raw.get("cbr_key_rate_forecast") or {}).items()
            },
        )

        # Lease settings — opening balances (legacy)
        lease_raw = mode_cfg.get("leases", {})
        leases = LeaseDrivers(
            enabled=lease_raw.get("enabled", False),
            default_discount_rate=lease_raw.get("default_discount_rate", 0.05),
        )

        # Lease corkscrew params — YAML overrides only at config-build time.
        # Preprocessor-based filling happens later in _fill_drivers_from_preprocess.
        _lease_yaml = mode_cfg.get("lease", {})
        _lease_params = LeaseParams(
            # Rates (dimensionless) — YAML value as-is, else class default used implicitly
            op_decay_rate      = float(_lease_yaml.get("op_decay_rate",      0.33)),
            fin_principal_rate = float(_lease_yaml.get("fin_principal_rate", 0.25)),
            fin_amort_rate     = float(_lease_yaml.get("fin_amort_rate",     0.28)),
            fin_interest_rate  = float(_lease_yaml.get("fin_interest_rate",  0.06)),
            # Dollar amounts: YAML values in millions → *1e6; preprocessor fills later
            op_new_leases   = float(_lease_yaml["op_new_leases"])  * 1e6 if "op_new_leases"  in _lease_yaml else 0.0,
            op_cash_payment = float(_lease_yaml["op_cash_payment"]) * 1e6 if "op_cash_payment" in _lease_yaml else 0.0,
            fin_new_leases  = float(_lease_yaml["fin_new_leases"])  * 1e6 if "fin_new_leases"  in _lease_yaml else 0.0,
        )

        # Forecast methods
        fm = self._parse_forecast_methods(cfg.get("forecast_methods", {}))

        # Feature flags
        features = cfg.get("features", {})

        # Автодетект для custom mode — graceful degradation
        # Если явно задано в features → берём оттуда
        # Если custom mode → автодетект по наличию данных
        # Если standard mode → упрощённые методы
        _auto_ppe = self._detect_ppe_mode() if mode == "custom" else False
        _auto_wc  = self._detect_wc_mode()  if mode == "custom" else False
        _auto_tax = self._detect_tax_mode() if mode == "custom" else False

        # tax_rate_statutory: mode-specific margins take priority, then standard.margins fallback.
        # Never read from preprocessor here — preprocess tax_rate EWA is distorted by near-zero
        # EBT years (e.g. 2011=2.96x, 2012=21.8x) and gets clamped to 0.50 even with max clamp.
        _std_margins = cfg.get("model", {}).get("standard", {}).get("margins", {})
        _tax_rate_yaml = (
            _safe_float(mode_cfg.get("margins", {}).get("tax_rate_statutory"))
            or _safe_float(_std_margins.get("tax_rate_statutory"))
        )

        mc = ModelConfig(
            company_id=self.company_id,
            scenario_name=self._scenario_name,
            history_start_year=periods.get("history_start_year", 2010),
            history_end_year=periods.get("history_end_year", 2024),
            forecast_start_year=periods.get("forecast_start_year", 2025),
            forecast_end_year=periods.get("forecast_end_year", 2029),
            accounting_standard=company_cfg.get("accounting_standard", "US_GAAP"),
            db_unit=company_cfg.get("db_unit", "tUSD"),
            # Drivers (могут быть переопределены в YAML)
            cogs_pct=_safe_float(mode_cfg.get("margins", {}).get("cogs_pct")),
            tax_rate=_tax_rate_yaml,
            min_cash=float(features.get("min_cash", 0.0)),
            target_net_debt_ebitda=float(
                mode_cfg.get("debt", {}).get("target_net_debt_ebitda", 0.0)),
            max_voluntary_prepay_pct_fcf=float(
                mode_cfg.get("debt", {}).get("max_voluntary_prepay_pct_fcf", 1.0)),
            expansion_capex_pct_of_rev_growth=float(
                mode_cfg.get("ppe", {}).get("expansion_capex_pct_of_rev_growth", 0.0)),
            dividend_payout=float(mode_cfg.get("equity", {}).get("dividend_payout_ratio", 0.0)),
            buyback_pct_fcf=float(mode_cfg.get("equity", {}).get("buyback_pct_fcf", 0.0)),
            buyback_leverage_max=float(mode_cfg.get("equity", {}).get("buyback_leverage_max", 2.0)),
            equity_additional_events={
                int(yr): {k: float(v) * 1e6 for k, v in events.items()}
                for yr, events in mode_cfg.get("equity", {}).get("additional_events", {}).items()
            },
            # WC days
            dso_days=_safe_float(mode_cfg.get("wc", {}).get("dso_days")),
            dih_days=_safe_float(mode_cfg.get("wc", {}).get("dio_days")),
            dpo_days=_safe_float(mode_cfg.get("wc", {}).get("dpo_days")),
            # CapEx
            capex_pct=_safe_float(mode_cfg.get("capex_policy", {}).get("ratio_default")),
            capex_pct_by_year={
                int(k): float(v)
                for k, v in mode_cfg.get("capex_policy", {}).get("capex_pct_by_year", {}).items()
            } or None,
            dep_rate=_safe_float(mode_cfg.get("ppe", {}).get("depreciation_rate")),
            min_capex_da_ratio=float(mode_cfg.get("ppe", {}).get("min_capex_da_ratio", 0.90)),
            additional_capex_schedule={
                int(yr): float(amt) * 1e6
                for yr, amt in mode_cfg.get("ppe", {}).get("additional_capex", {}).items()
            },
            accel_dep_excess_pct=float(
                cfg.get("model", {}).get("standard", {}).get("taxes", {}).get("accel_dep_excess_pct", 0.0)
                or cfg.get("model", {}).get("custom", {}).get("taxes", {}).get("accel_dep_excess_pct", 0.0)
                or 0.0
            ),
            debt=debt_settings,
            leases=leases,
            lease=_lease_params,
            forecast_methods=fm,
            # Feature flags
            use_ppe_corkscrew=features.get("use_ppe_corkscrew", _auto_ppe),
            use_wc_days=features.get("use_wc_days", _auto_wc),
            use_debt_rc=features.get("use_debt_rc",
                False if mode == "standard" else True),
            use_intangibles_corkscrew=features.get("use_intangibles_corkscrew",
                False if mode == "standard" else _auto_ppe),
            use_tax_corkscrew=features.get("use_tax_corkscrew", _auto_tax),
            use_interest_payable_cork=features.get("use_interest_payable_cork",
                False if mode == "standard" else _auto_tax),
            # Covenant acceleration wiring
            covenants_enabled=bool(cfg.get("covenants", {}).get("enabled", False)),
            covenant_acceleration_triggers=list(
                cfg.get("covenants", {}).get("acceleration_triggers",
                    ['interest_coverage', 'net_debt_ebitda'])
            ),
            # NOL config — YAML stores $M amounts; convert to absolute dollars
            nol_opening_balance=float(
                (mode_cfg.get("taxes") or {}).get("nol_opening_balance", 0.0) or 0.0
            ) * 1e6,
            nol_max_utilization_pct=float(
                (mode_cfg.get("taxes") or {}).get("nol_max_utilization_pct", 0.80) or 0.80
            ),
            # Accounting conventions (drive COGS/interest treatment in core.py)
            da_in_cogs=bool(cfg.get("accounting_conventions", {}).get("da_in_cogs", True)),
            capitalize_interest=bool(
                cfg.get("accounting_conventions", {}).get("capitalize_interest", False)
            ),
            is_income_sign=str(
                cfg.get("accounting_conventions", {}).get("is_income_sign", "credit_negative")
            ),
            # Macro factor config (from YAML → passed to blocks, no re-read)
            revenue_macro_factor=(
                mode_cfg.get("revenue", {}).get("macro_factor") or
                (mode_cfg.get("revenue", {}).get("macro_factors") or [None])[0]
            ),
            cogs_revenue_factor=mode_cfg.get("cogs", {}).get("revenue_factor"),
            cogs_cost_factor=mode_cfg.get("cogs", {}).get("cost_factor"),
            # Solver параметры
            max_iter=int(cfg.get("solver", {}).get("max_iter", 10)),
            tol=float(cfg.get("solver", {}).get("tol", 1000.0)),
        )
        return mc

    def _parse_forecast_methods(
        self, raw: Dict[str, Any]
    ) -> Dict[str, Dict[str, ForecastMethodConfig]]:
        """Парсит секцию forecast_methods из project.yaml."""
        result: Dict[str, Dict[str, ForecastMethodConfig]] = {}
        for statement, metrics in raw.items():
            statement_upper = statement.upper()
            result[statement_upper] = {}
            if not isinstance(metrics, dict):
                continue
            for metric, spec in metrics.items():
                if not isinstance(spec, dict):
                    continue
                try:
                    method = ForecastMethod(spec.get("method", "ewa"))
                    fmc = ForecastMethodConfig(
                        method=method,
                        driver_base=spec.get("driver_base"),
                        driver_ratio=_safe_float(spec.get("driver_ratio")),
                        driver_ratio_source=spec.get("driver_ratio_source"),
                        days_metric=spec.get("days_metric"),
                        days_base=spec.get("days_base"),
                        days_floor=_safe_float(spec.get("days_floor")),
                        corkscrew_type=spec.get("corkscrew_type"),
                        corkscrew_field=spec.get("corkscrew_field"),
                        ewa_halflife_years=float(spec.get("ewa_halflife_years", 3.0)),
                        macro_factors=spec.get("macro_factors", []),
                        macro_model=spec.get("macro_model", "elastic_net"),
                        plug_min_value=_safe_float(spec.get("plug_min_value")),
                        plug_absorbs_gap=bool(spec.get("plug_absorbs_gap", False)),
                        link_source=spec.get("link_source"),
                        link_field=spec.get("link_field"),
                        calc_formula=spec.get("calc_formula"),
                        sign=_parse_sign(spec.get("sign", 1.0)),
                    )
                    result[statement_upper][metric] = fmc
                except (ValueError, KeyError) as e:
                    logger.warning(f"Ошибка парсинга forecast_method {statement}.{metric}: {e}")
        return result

    def _detect_debt_mode(self) -> str:
        """Автоопределение режима долга по наличию данных в БД."""
        # Проверяем наличие debt_schedule — используем history_end_year из конфига
        cfg = self._load_yaml_config()
        hist_end = cfg.get("model", {}).get("standard", {}).get("periods", {}).get("history_end_year", 0)
        schedule = self._repo.get_debt_schedule(self.company_id, hist_end) if hist_end else None
        if schedule:
            return "schedule_based"
        # Проверяем наличие debt_instruments
        instruments = self._repo.get_debt_instruments(self.company_id)
        if instruments:
            return "optimizer"
        return "parametric"

    def _detect_ppe_mode(self) -> bool:
        """
        Автодетект: использовать PPE corkscrew или упрощённый % метод.

        Corkscrew (True) если:
        - ppe_gross И ppe_accum_dep есть в истории за 3+ лет

        Простой метод (False) если:
        - Только ppe_net без разбивки gross/accum
        - Или данных < 3 лет
        """
        try:
            gross_data = self._repo.get_metric_series(self.company_id, "BS", "ppe_gross")
            accum_data = self._repo.get_metric_series(self.company_id, "BS", "ppe_accum_dep")

            # Нужно минимум 3 года с обеими метриками и ненулевыми значениями
            common = {y for y in set(gross_data) & set(accum_data)
                     if gross_data.get(y, 0) > 0 and accum_data.get(y, 0) > 0}

            if len(common) >= 3:
                logger.info(f"  PPE mode: corkscrew (gross+accum данные за {len(common)} лет)")
                return True
            else:
                logger.info(f"  PPE mode: simple (нет gross/accum разбивки, лет={len(common)})")
                return False
        except Exception:
            return False

    def _detect_wc_mode(self) -> bool:
        """
        Автодетект: использовать DSO/DIH/DPO или NWC ratio.

        Days mode (True) если:
        - AR, Inventory, AP есть в истории за 3+ лет
        - DSO разумный (10-120 дней)

        Ratio mode (False) если:
        - Нет детальных WC данных
        """
        try:
            ar_data  = self._repo.get_metric_series(self.company_id, "BS", "accounts_receivable")
            inv_data = self._repo.get_metric_series(self.company_id, "BS", "inventory")
            ap_data  = self._repo.get_metric_series(self.company_id, "BS", "accounts_payable")

            common = set(ar_data) & set(inv_data) & set(ap_data)
            valid  = {y for y in common
                     if ar_data.get(y, 0) > 0 and inv_data.get(y, 0) > 0}

            if len(valid) >= 3:
                logger.info(f"  WC mode: days (AR/Inv/AP данные за {len(valid)} лет)")
                return True
            else:
                logger.info(f"  WC mode: ratio (нет детальных WC данных, лет={len(valid)})")
                return False
        except Exception:
            return False

    def _detect_tax_mode(self) -> bool:
        """
        Автодетект: использовать TaxBlock (DTA/DTL) или effective rate.

        TaxBlock (True) если:
        - DTA или DTL есть в истории

        Effective rate (False) если:
        - Нет DTA/DTL данных
        """
        try:
            dta_data = self._repo.get_metric_series(self.company_id, "BS", "dta")
            dtl_data = self._repo.get_metric_series(self.company_id, "BS", "dtl")

            has_dta = any(v > 0 for v in dta_data.values()) if dta_data else False
            has_dtl = any(v > 0 for v in dtl_data.values()) if dtl_data else False

            if has_dta or has_dtl:
                logger.info(f"  Tax mode: corkscrew (DTA={has_dta} DTL={has_dtl})")
                return True
            else:
                logger.info(f"  Tax mode: effective rate (нет DTA/DTL данных)")
                return False
        except Exception:
            return False

    # ── история ───────────────────────────────────────────────────────────────

    def _load_historic_state(self, cfg: ModelConfig) -> HistoricState:
        years = self._repo.get_years(self.company_id, is_forecast=0)
        if not years:
            raise ValueError(f"Нет исторических данных для {self.company_id}")

        # Ограничиваем по config
        years = [y for y in years if cfg.history_start_year <= y <= cfg.history_end_year]
        if not years:
            raise ValueError(
                f"Нет данных в диапазоне {cfg.history_start_year}–{cfg.history_end_year}"
            )

        is_data = self._repo.get_history(self.company_id, "IS", years)
        bs_data = self._repo.get_history(self.company_id, "BS", years)
        cf_data = self._repo.get_history(self.company_id, "CF", years)

        return HistoricState(
            company_id=self.company_id,
            years=years,
            base_year=max(years),
            is_data=is_data,
            bs_data=bs_data,
            cf_data=cf_data,
        )

    # ── препроцессор ──────────────────────────────────────────────────────────

    def _load_preprocess(self, historic: HistoricState, cfg: ModelConfig) -> None:
        groups = [
            "margin_ratios", "wc_days", "capex", "debt", "interest",
            "equity", "extended", "beta_coefficients", "revenue_betas",
            "cf_reconciliation_adjustment", "is_reconciliation_adjustment",
            "unmodeled_items_adjustment", "lease",
            "production_kpi",
        ]
        for group in groups:
            data = self._repo.get_preprocess(self.company_id, group)
            if data:
                historic.preprocess[group] = data

    def _fill_drivers_from_preprocess(
        self, cfg: ModelConfig, historic: HistoricState
    ) -> None:
        """
        Если driver не задан явно в YAML — берём из препроцессора.
        Приоритет: YAML explicit > preprocess_recommended > hardcoded default.
        """
        def _from_pp(group: str, metric: str, default: Optional[float] = None) -> Optional[float]:
            val = historic.get_recommended(group, metric)
            return val if val is not None else default

        if cfg.cogs_pct is None:
            cfg.cogs_pct = _from_pp("margin_ratios", "cogs_ratio", 0.85)
        if cfg.sga_pct is None:
            # Prefer opex_ratio (sga + distribution) when available
            cfg.sga_pct = _from_pp("margin_ratios", "opex_ratio", None) or \
                          _from_pp("margin_ratios", "sga_ratio", 0.05)
        if cfg.capex_pct is None:
            # capex_pct_revenue — от старого препроцессора (корректные данные)
            # capex_to_rev — от нового (может иметь ошибки в 2024 CF данных)
            # Берём лучшее из двух: capex_pct_revenue если есть
            v = _from_pp("capex", "capex_pct_revenue", None)
            if v is None:
                v = _from_pp("capex", "capex_to_rev", 0.05)
            cfg.capex_pct = v
        if cfg.dep_rate is None:
            dep_last = historic.preprocess.get("capex", {}).get("dep_rate_last")
            dep_ewa  = historic.get_recommended("capex", "dep_rate")
            # Используем последнее наблюдение — наиболее актуально для текущего PPE base
            cfg.dep_rate = dep_last if dep_last else dep_ewa  # None → core fallback to dep_to_rev
        if cfg.dep_to_rev is None:
            dep_to_rev_last = historic.preprocess.get("capex", {}).get("dep_to_rev_last")
            dep_to_rev_ewa  = historic.get_recommended("capex", "dep_to_rev")
            # Предпочитаем последнее (более актуально для текущего размера активов)
            cfg.dep_to_rev = dep_to_rev_last if dep_to_rev_last else dep_to_rev_ewa
        if cfg.dso_days is None:
            cfg.dso_days = _from_pp("wc_days", "dso", 45.0)
        if cfg.dih_days is None:
            cfg.dih_days = _from_pp("wc_days", "dih", 60.0)
        if cfg.dpo_days is None:
            cfg.dpo_days = _from_pp("wc_days", "dpo", 50.0)
        if cfg.tax_rate is None:
            # Use tax_effective_rate (not tax_rate) — tax_rate EWA blows up when EBT ≈ 0.
            rate = _from_pp("margin_ratios", "tax_effective_rate", 0.25)
            cfg.tax_rate = max(0.05, min(0.45, rate))
        # Обновляем avg_rate_pct из препроцессора если YAML не задал явно нестандартное значение
        rate_from_pp = _from_pp("debt", "avg_interest_rate", None)
        if rate_from_pp is not None and abs(cfg.debt.avg_rate_pct - 0.05) < 0.001:
            cfg.debt.avg_rate_pct = max(0.01, min(0.20, rate_from_pp))
        # cash_rate: используем last наблюдение interest_income_rate (год высоких ставок актуален)
        # Приоритет: interest.interest_income_rate_last > extended.interest_income_rate_last > default 2%
        rate_income_last = (
            historic.preprocess.get("interest", {}).get("interest_income_rate_last")
            or historic.preprocess.get("extended", {}).get("interest_income_rate_last")
        )
        if rate_income_last is not None and rate_income_last > 0.005:
            cfg.cash_rate = min(0.10, float(rate_income_last))

        # Lease corkscrew params: fill from preprocessor where YAML left defaults (0.0 for amounts)
        _pp_l = historic.preprocess.get("lease", {})

        def _lrec(pp_key: str, default: float) -> float:
            v = _pp_l.get(pp_key + "_recommended")
            return float(v) if v is not None else default

        # Rates: only update if still at hardcoded default (YAML override wins)
        if cfg.lease.op_decay_rate == 0.33:
            cfg.lease.op_decay_rate = _lrec("op_lease_decay_rate", 0.33)
        if cfg.lease.fin_principal_rate == 0.25:
            cfg.lease.fin_principal_rate = _lrec("fin_lease_principal_rate", 0.25)
        if cfg.lease.fin_amort_rate == 0.28:
            cfg.lease.fin_amort_rate = _lrec("fin_lease_amort_rate", 0.28)
        if cfg.lease.fin_interest_rate == 0.06:
            cfg.lease.fin_interest_rate = _lrec("fin_lease_interest_rate", 0.06)
        # Dollar amounts: fill from preprocessor if YAML left them at 0
        if cfg.lease.op_new_leases == 0.0:
            cfg.lease.op_new_leases = _lrec("op_lease_new_leases", 0.0)
        if cfg.lease.op_cash_payment == 0.0:
            cfg.lease.op_cash_payment = _lrec("op_lease_cash_payment", 0.0)
        if cfg.lease.fin_new_leases == 0.0:
            cfg.lease.fin_new_leases = _lrec("fin_lease_new_leases", 0.0)

    # ── долг ──────────────────────────────────────────────────────────────────

    def _load_debt_instruments(
        self, historic: HistoricState, cfg: ModelConfig
    ) -> None:
        raw_instruments = self._repo.get_debt_instruments(self.company_id)

        # Always load base-year schedule to get closing balances as opening for forecast
        base_year_schedule_rows = self._repo.get_debt_schedule(
            self.company_id, historic.base_year
        )
        base_year_close: dict = {
            row["instrument_id"]: float(row.get("closing_balance") or 0)
            for row in base_year_schedule_rows
        }

        for r in raw_instruments:
            instrument_id = r["instrument_id"]
            # Prefer base-year closing balance over the static opening_balance column
            opening = base_year_close.get(
                instrument_id, float(r.get("opening_balance") or 0)
            )
            instrument = DebtInstrument(
                instrument_id=instrument_id,
                instrument_name=r.get("instrument_name", instrument_id),
                db_type=r.get("db_type", "other"),
                currency=r.get("currency", "USD"),
                opening_balance=opening,
                committed_amount=_safe_float(r.get("committed_amount")),
                maturity_date=r.get("maturity_date"),
                interest_rate=_safe_float(r.get("interest_rate")),
                rate_type=r.get("rate_type", "fixed"),
                base_rate_factor=r.get("base_rate_factor"),
                payment_frequency=r.get("payment_frequency", "semi_annual"),
                amortization_profile=r.get("amortization_profile", "bullet"),
                callable_flag=bool(r.get("callable_flag", False)),
            )

            # Загружаем corkscrew если есть
            if cfg.debt.mode == "schedule_based":
                schedule = {}
                for year in historic.years:
                    yr_schedule = self._repo.get_debt_schedule(self.company_id, year)
                    for row in yr_schedule:
                        if row["instrument_id"] == instrument.instrument_id:
                            schedule[year] = row
                            break
                if schedule:
                    instrument.schedule = schedule
            else:
                # For v2_solver / full mode: load mandatory repayments for forecast years
                # so the optimizer can build amort_schedule with known obligations
                schedule = {}
                for year in cfg.forecast_years:
                    yr_schedule = self._repo.get_debt_schedule(self.company_id, year)
                    for row in yr_schedule:
                        if row["instrument_id"] == instrument.instrument_id:
                            mand = float(row.get("repay_mandatory") or 0)
                            if mand > 0:
                                schedule[year] = row
                            break
                if schedule:
                    instrument.schedule = schedule

            historic.debt_instruments.append(instrument)

        logger.info(f"Долговых инструментов: {len(historic.debt_instruments)}")

    # ── макро-прогнозы ────────────────────────────────────────────────────────

    def _load_macro_forecasts(
        self, historic: HistoricState, cfg: ModelConfig
    ) -> None:
        try:
            scenario_id = self._repo.get_scenario_id(
                self.company_id, self._scenario_name
            )
            forecasts = self._repo.get_macro_forecasts(
                self.company_id, scenario_id
            )
            # Prepend last historical observation for each factor so that
            # PPI/CPI beta adjustments in year-1 of the forecast can look up
            # the prior-year actuals (e.g. ppi_series.get(base_year)).
            for factor_name, series in forecasts.items():
                hist = self._repo.get_macro_factor(factor_name)
                for yr, val in hist.items():
                    if yr not in series:
                        series[yr] = val
            historic.macro_forecasts = forecasts
            logger.info(f"Макро-прогнозов: {len(forecasts)} факторов")
        except ValueError:
            logger.warning(
                f"Сценарий '{self._scenario_name}' не найден, макро-прогнозы не загружены"
            )

    # ── base year state ───────────────────────────────────────────────────────

    def _build_base_year_state(
        self, historic: HistoricState, year: int
    ) -> YearState:
        """
        Строит YearState для базового (последнего исторического) года.
        Это отправная точка для первого прогнозного года.
        """
        is_y = historic.is_data.get(year, {})
        bs_y = historic.bs_data.get(year, {})
        cf_y = historic.cf_data.get(year, {})

        def _g(d: dict, k: str, default: float = 0.0) -> float:
            v = d.get(k)
            return float(v) if v is not None else default

        state = YearState(year=year)

        # IS
        state.revenue              = _g(is_y, "revenue")
        state.cogs                 = _g(is_y, "cogs")
        state.gross_profit         = _g(is_y, "gross_profit")
        state.sga                  = _g(is_y, "sga")
        state.dep_ppe              = _g(is_y, "depreciation_owned")
        state.dep_rou              = _g(is_y, "depreciation_rou")
        state.amort_intangibles    = _g(is_y, "amortization")
        state.total_da             = _g(is_y, "total_da")
        state.ebitda               = _g(is_y, "ebitda")
        state.ebit                 = _g(is_y, "ebit")
        state.interest_expense     = _g(is_y, "interest_expense")
        state.ebt                  = _g(is_y, "ebt")
        state.tax_expense          = _g(is_y, "tax_expense")
        state.net_income           = _g(is_y, "net_income")
        # Income items ниже EBIT: модель ожидает ПОЛОЖИТЕЛЬНЫЙ знак для дохода.
        # Конвенция "credit_negative": DB хранит доход как отрицательное → инвертируем.
        # Конвенция "natural": DB хранит доход как положительное → берём как есть.
        _sign = -1.0 if self._is_income_sign == "credit_negative" else 1.0
        state.earnings_from_investees = _sign * (_g(is_y, "earnings_from_investees") or 0.0)
        state.net_periodic_benefit    = _sign * (_g(is_y, "net_periodic_benefit_income") or 0.0)
        state.interest_income         = _sign * (_g(is_y, "interest_income") or 0.0)

        # BS
        state.cash                 = _g(bs_y, "cash")
        state.restricted_cash      = _g(bs_y, "restricted_cash")
        state.accounts_receivable  = _g(bs_y, "accounts_receivable")
        state.inventory            = _g(bs_y, "inventory")
        state.other_ca             = _g(bs_y, "other_ca") or _g(bs_y, "other_current_assets")
        state.accounts_payable     = _g(bs_y, "accounts_payable")
        state.ppe_gross            = _g(bs_y, "ppe_gross")
        state.ppe_accum_dep        = _g(bs_y, "ppe_accum_dep")
        state.ppe_net              = _g(bs_y, "ppe_net")
        state.rou_asset            = _g(bs_y, "rou_asset")
        state.intangibles          = _g(bs_y, "intangibles")
        state.goodwill             = _g(bs_y, "goodwill")
        state.investments_lt       = _g(bs_y, "investments_and_long_term_receivables") or _g(bs_y, "investments_lt")
        state.dta                  = _g(bs_y, "dta")
        state.dtl                  = _g(bs_y, "dtl")
        state.other_nca            = _g(bs_y, "other_nca") or _g(bs_y, "other_non_current_assets")
        state.short_term_debt      = _g(bs_y, "short_term_debt")
        state.long_term_debt       = _g(bs_y, "long_term_debt")
        state.lease_liab_current   = _g(bs_y, "lease_liab_current")
        state.lease_liab_noncurrent = _g(bs_y, "lease_liab_noncurrent")
        state.employee_benefits    = _g(bs_y, "employee_benefits")
        state.other_ncl            = _g(bs_y, "other_non_current_liabilities") or _g(bs_y, "other_ncl")
        state.other_cl             = _g(bs_y, "other_cl") or _g(bs_y, "other_current_liabilities")
        state.taxes_payable        = _g(bs_y, "taxes_payable") or _g(bs_y, "accrued_taxes")
        state.interest_payable     = _g(bs_y, "interest_payable") or _g(bs_y, "accrued_interest")
        state.payroll_payable      = _g(bs_y, "payroll_payable") or _g(bs_y, "payroll_and_benefits_payable")
        state.share_capital        = _g(bs_y, "share_capital")
        state.apic                 = _g(bs_y, "apic")
        state.treasury_stock       = _g(bs_y, "treasury_stock")
        state.retained_earnings    = _g(bs_y, "retained_earnings")
        state.aoci                 = _g(bs_y, "aoci")
        state.nci                  = _g(bs_y, "nci")
        state.total_assets         = _g(bs_y, "total_assets")
        state.total_equity         = _g(bs_y, "total_equity")
        state.total_liab_equity    = _g(bs_y, "total_liab_equity")

        # CF
        state.cfi_capex            = _g(cf_y, "capex")
        state.cfo_total            = _g(cf_y, "cfo_total")
        state.cfi_total            = _g(cf_y, "cfi_total")
        state.cff_total            = _g(cf_y, "cff_total")
        state.cf_cash_ending       = _g(cf_y, "cash_ending")

        # Force BS balance in base year by adjusting other_nca as a plug.
        # Historical data may have small imbalances (missing items, rounding).
        # This plug is a one-time correction; forecast years are balanced by corkscrews.
        _ca = (state.cash or 0) + (state.restricted_cash or 0) + (state.accounts_receivable or 0) + (state.inventory or 0) + (state.other_ca or 0)
        _nca = (state.ppe_net or 0) + (state.rou_asset or 0) + (state.intangibles or 0) + (state.goodwill or 0) + (state.dta or 0) + (state.investments_lt or 0) + (state.other_nca or 0)
        _cl = (state.short_term_debt or 0) + abs(state.accounts_payable or 0) + abs(state.taxes_payable or 0) + abs(state.interest_payable or 0) + abs(state.payroll_payable or 0) + abs(state.lease_liab_current or 0) + abs(state.other_cl or 0)
        _ncl = (state.long_term_debt or 0) + abs(state.dtl or 0) + abs(state.employee_benefits or 0) + abs(state.lease_liab_noncurrent or 0) + abs(state.other_ncl or 0)
        _eq = (state.share_capital or 0) + (state.apic or 0) + (state.retained_earnings or 0) - abs(state.treasury_stock or 0) + (state.aoci or 0) + (state.nci or 0)
        _assets = _ca + _nca
        _le = _cl + _ncl + _eq
        _plug = _le - _assets  # positive = L+E > Assets → add to NCA
        if abs(_plug) > 1.0:
            state.other_nca = (state.other_nca or 0) + _plug

        return state


# ── helpers ────────────────────────────────────────────────────────────────────

def _parse_sign(val) -> float:
    """Парсит знак: 'negative' → -1.0, 'positive' → 1.0, число → float."""
    if isinstance(val, str):
        s = val.strip().lower()
        if s in ("negative", "neg", "-1", "-"):
            return -1.0
        if s in ("positive", "pos", "1", "+"):
            return 1.0
        try:
            return float(s)
        except ValueError:
            return 1.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return 1.0


def _safe_float(val) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
