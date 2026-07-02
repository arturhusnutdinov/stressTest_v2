from __future__ import annotations
import json
import warnings
from itertools import combinations
import numpy as np, pandas as pd, yaml
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from statsmodels.tsa.vector_ar.vecm import select_coint_rank, VECM
from statsmodels.tsa.api import VAR
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.seasonal import STL
from statsmodels.stats.diagnostic import acorr_ljungbox
from .io import read_one_row_annual
from .cointegration_test import select_forecast_method, check_forecast_stability, test_cointegration_with_dummies
from .preprocess import preprocess_macro_history, FactorAnomaly, FactorMetrics

try:
    from pmdarima import auto_arima as _auto_arima_model
    PMDARIMA_AVAILABLE = True
except ImportError:
    PMDARIMA_AVAILABLE = False

# DB adapter — set by caller (vecm_bridge/runner) before running VECM
_db_adapter = None


def set_db_adapter(adapter) -> None:
    """Set module-level DB adapter for saving results."""
    global _db_adapter
    _db_adapter = adapter


def _save_forecast(db, company: str, factor_name: str, data: Dict[int, float], method: str) -> None:
    """Save forecast via adapter. db parameter kept for backward compat but _db_adapter preferred."""
    target = db or _db_adapter
    if target is None or not data:
        return
    try:
        target.save_macro_forecast(factor_name, data, method=method)
    except Exception:
        pass


def _save_diagnostics(db, company: str, factor_name: str, method: str, block_name: str,
                      p: int = None, rank: int = None, span_start: int = None, span_end: int = None,
                      lb_pvalue: float = None, note: str = None, cv_smape: float = None) -> None:
    target = db or _db_adapter
    if target is None:
        return
    try:
        target.save_ecm_diagnostics(company, factor_name, method, block_name, p, rank, span_start, span_end, lb_pvalue, note, cv_smape)
    except Exception:
        pass


def _save_actual_vs_fitted(db, company: str, factor_name: str, actual: Dict[int, float], fitted: Dict[int, float]) -> None:
    target = db or _db_adapter
    if target is None:
        return
    try:
        target.save_actual_vs_fitted(company, factor_name, actual, fitted)
    except Exception:
        pass


def _save_forecast_diag(db, company: str, factor_name: str, slope: float, flat_flag: bool) -> None:
    target = db or _db_adapter
    if target is None:
        return
    try:
        target.save_ecm_forecast_diag(company, factor_name, slope, flat_flag)
    except Exception:
        pass
DEFAULT_FALLBACK_ORDER = ["arima011", "rw_drift"]
def _read_yaml(p: Path) -> dict:
    try:
        text = Path(p).read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except Exception:
        try:
            text = Path(p).read_text()
        except Exception:
            return {}
    try:
        data = yaml.safe_load(text)
    except Exception:
        return {}
    return data or {}


def _load_company_project(root: Path, company: str) -> dict:
    proj_path = Path(root) / "companies" / company / "configs" / "project.yaml"
    return _read_yaml(proj_path)


def _load_project_factors(root: Path, company: str) -> List[str]:
    proj = _load_company_project(root, company)
    macro_cfg = proj.get("macro_forecast", {}) if isinstance(proj, dict) else {}
    factors = macro_cfg.get("factors") or []
    if not factors:
        fmap = macro_cfg.get("file_map", {})
        if isinstance(fmap, dict):
            factors = list(fmap.keys())
    return [str(f).strip() for f in factors if f]
def _to_ln_series(levels: Dict[int, float]) -> pd.Series:
    eps=1e-9; return pd.Series({y: (np.log(max(v, eps)) if pd.notna(v) else np.nan) for y, v in levels.items()})
def _stack_block_ln(
    root: Path,
    company: str,
    facs: List[str],
    file_map: dict,
    search_paths: list,
    cleaned_overrides: Optional[Dict[str, Dict[int, float]]] = None,
) -> pd.DataFrame:
    """
    Загружает историю макро-факторов и преобразует в ln формат для VECM.
    ЗАГРУЗКА ТОЛЬКО ИЗ БД (CSV fallback удален из основного кода, но может оставаться в read_one_row_annual для совместимости)
    """
    cols={}

    for f in facs:
        if cleaned_overrides and f in cleaned_overrides:
            override_series = pd.Series(cleaned_overrides[f], dtype=float).dropna().sort_index()
            if not override_series.empty:
                cols[f'ln_{f}'] = override_series
                continue
        # Load factor history via io.read_one_row_annual (uses adapter or DB fallback)
        history_data = {}
        try:
            lv, _ = read_one_row_annual(root, company, f, file_map, search_paths)
            if lv:
                # Filter to positive values only (levels, not ln)
                history_data = {k: v for k, v in lv.items() if pd.notna(v) and v > 0}
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Не удалось загрузить макро-фактор {f}: {e}")
        
        # Преобразуем уровни в ln формат для VECM
        if history_data:
            cols[f'ln_{f}']=_to_ln_series(history_data)
    
    Y=pd.DataFrame(cols).sort_index().dropna(how='any'); return Y
def _choose_rank(Y: pd.DataFrame, det: str, alpha: float, k_ar_diff: int=1) -> int:
    det_order=0 if det in ('nc','none') else 1
    res=select_coint_rank(Y.values, det_order=det_order, method='trace', signif=alpha, k_ar_diff=k_ar_diff)
    return int(res.rank)
def _fit_vecm(Y: pd.DataFrame, det: str, p_min: int, p_max: int, alpha: float, 
               use_dummies: bool = False, shock_years: List[int] = None, max_dummies: int = None, 
               dummy_aic_penalty: float = 10.0):
    best=None
    for p in range(p_min, p_max+1):
        try:
            if use_dummies:
                # Используем тестирование с dummy переменными
                m, aic, n_dummies, selected_shocks = test_cointegration_with_dummies(Y, p, det, alpha, shock_years, max_dummies, dummy_aic_penalty)
                if m is not None and aic < float('inf'):
                    r = m.coint_rank
                    if (best is None) or (aic<best['aic']): 
                        best={'p':p,'rank':r,'model':m,'aic':aic,'n_dummies':n_dummies,'selected_shocks':selected_shocks}
            else:
                # Стандартный подход без dummy
                r=_choose_rank(Y, det, alpha, k_ar_diff=p-1); m=VECM(Y, k_ar_diff=p-1, coint_rank=r, deterministic=det).fit()
                # Вычисляем AIC вручную, т.к. VECMResults не имеет атрибута aic
                # AIC = -2*loglikelihood + 2*number_of_parameters
                # Для VECM: k = k_endog*k_ar_diff + k_endog*rank + det_order (для простоты берем приблизительную оценку)
                n_params = Y.shape[1] * p + Y.shape[1] * r + (1 if det in ('ci','li') else 0)
                aic = -2 * m.llf + 2 * n_params
                if (best is None) or (aic<best['aic']): best={'p':p,'rank':r,'model':m,'aic':aic,'n_dummies':0,'selected_shocks':None}
        except Exception: continue
    return best
def _apply_residual_ar1_if_needed(resid: pd.DataFrame, alpha: float) -> Dict[str, float]:
    phi={}
    for c in resid.columns:
        try:
            pval=acorr_ljungbox(resid[c], lags=[1], return_df=True)['lb_pvalue'].iloc[0]
            phi[c]=0.0 if pval>=alpha else float(np.corrcoef(resid[c][1:], resid[c][:-1])[0,1])
        except Exception: phi[c]=0.0
    return phi

def _apply_residual_arma_if_needed(resid: pd.DataFrame, alpha: float) -> Dict[str, tuple]:
    """
    Применяет ARMA(1,1) к остаткам VECM, если обнаружена автокорреляция.
    Возвращает словарь {column: (phi, theta)} где phi - AR1 коэффициент, theta - MA1 коэффициент.
    """
    phis_thetas = {}
    for c in resid.columns:
        try:
            pval = acorr_ljungbox(resid[c], lags=[1], return_df=True)['lb_pvalue'].iloc[0]
            if pval < alpha:
                # Есть автокорреляция - оцениваем ARMA(1,1)
                try:
                    arma_model = ARIMA(resid[c], order=(1, 0, 1)).fit(method_kwargs={"warn_convergence": False})
                    phi_val = float(arma_model.arparams[0]) if len(arma_model.arparams) > 0 else 0.0
                    theta_val = float(arma_model.maparams[0]) if len(arma_model.maparams) > 0 else 0.0
                    phis_thetas[c] = (phi_val, theta_val)
                except Exception:
                    # Fallback to AR1
                    phis_thetas[c] = (float(np.corrcoef(resid[c][1:], resid[c][:-1])[0,1]), 0.0)
            else:
                phis_thetas[c] = (0.0, 0.0)
        except Exception:
            phis_thetas[c] = (0.0, 0.0)
    return phis_thetas
def _rolling_cv_smape(y: pd.Series, horizon: int=1) -> float:
    # простой rolling origin: one-step ahead sMAPE, начиная с половины ряда
    y=y.dropna()
    if len(y)<8: return float('inf')
    start=max(4, len(y)//2)
    errs=[]
    for t in range(start, len(y)-horizon+1):
        train=y.iloc[:t]
        true=y.iloc[t:t+horizon]
        # модель 1: RW-drift на ln-уровнях (средняя Δ)
        d=train.diff().dropna()
        drift=d.mean() if not d.empty else 0.0
        fc=[train.iloc[-1]+drift]
        # sMAPE
        num=abs(true.values[0]-fc[0])
        den=(abs(true.values[0])+abs(fc[0]))/2 if (abs(true.values[0])+abs(fc[0]))!=0 else 1.0
        errs.append(num/den)
    return float(np.mean(errs)) if errs else float('inf')
def _forecast_rw_drift_ln(y: pd.Series, steps: int) -> pd.Series:
    y=y.dropna()
    if y.empty:
        return pd.Series([np.nan]*steps)
    d=y.diff().dropna(); drift=float(d.mean()) if not d.empty else 0.0
    out=[y.iloc[-1]+drift]
    for _ in range(1,steps): out.append(out[-1]+drift)
    idx_start = int(y.index.max()) + 1 if len(y.index) else 0
    idx = np.arange(idx_start, idx_start + steps)
    return pd.Series(np.asarray(out, dtype=float), index=idx)
def _forecast_arima011_ln(y: pd.Series, steps: int) -> pd.Series:
    y=y.dropna()
    if len(y)<6:
        return _forecast_rw_drift_ln(y, steps)
    try:
        m=ARIMA(y, order=(0,1,1)).fit(method_kwargs={"warn_convergence":False})
        f=m.forecast(steps=steps)
        idx_start = int(y.index.max()) + 1 if len(y.index) else 0
        idx = np.arange(idx_start, idx_start + steps)
        return pd.Series(np.asarray(f, dtype=float), index=idx)
    except Exception:
        return _forecast_rw_drift_ln(y, steps)
def _fitted_rw_drift_ln(y: pd.Series) -> pd.Series:
    y = y.dropna()
    if len(y) < 2:
        return pd.Series(index=y.index, dtype=float)
    d = y.diff().dropna(); drift = float(d.mean()) if not d.empty else 0.0
    fitted = []
    idx = y.index.tolist()
    for i in range(len(y)):
        if i == 0:
            fitted.append(np.nan)
        else:
            fitted.append(float(y.iloc[i-1] + drift))
    return pd.Series(fitted, index=y.index)
def _fitted_arima011_ln(y: pd.Series) -> pd.Series:
    y = y.dropna()
    if len(y) < 6:
        return _fitted_rw_drift_ln(y)
    try:
        m = ARIMA(y, order=(0,1,1)).fit(method_kwargs={"warn_convergence":False})
        # one-step ahead in-sample predictions
        pred = m.predict()
        return pd.Series(pred, index=y.index)
    except Exception:
        return _fitted_rw_drift_ln(y)


def _forecast_auto_arima_ln(y: pd.Series, steps: int, cfg: dict) -> Optional[pd.Series]:
    if not PMDARIMA_AVAILABLE:
        return None
    params = cfg or {}
    y = y.dropna()
    if y.empty:
        return None
    min_points = int(params.get("min_points", 8))
    if len(y) < max(6, min_points):
        return None
    try:
        model = _auto_arima_model(
            y,
            seasonal=params.get("seasonal", False),
            m=int(params.get("seasonal_periods", 1) or 1),
            suppress_warnings=True,
            error_action="ignore",
            max_p=params.get("max_p", 3),
            max_q=params.get("max_q", 3),
            max_d=params.get("max_d", 2),
            stepwise=True,
            n_jobs=params.get("n_jobs", 1),
        )
        forecast = model.predict(n_periods=steps)
        idx_start = int(y.index.max()) + 1 if len(y.index) else 0
        idx = np.arange(idx_start, idx_start + steps)
        return pd.Series(np.asarray(forecast, dtype=float), index=idx)
    except Exception:
        return None


def _forecast_ets_ln(y: pd.Series, steps: int, cfg: dict) -> Optional[pd.Series]:
    params = cfg or {}
    y = y.dropna()
    if len(y) < int(params.get("min_points", 6)):
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = ExponentialSmoothing(
                y,
                trend=params.get("trend", "add"),
                damped_trend=params.get("damped_trend", False),
                seasonal=params.get("seasonal", None),
                seasonal_periods=params.get("seasonal_periods"),
                initialization_method="estimated",
            ).fit(optimized=True)
        forecast = model.forecast(steps)
        idx_start = int(y.index.max()) + 1 if len(y.index) else 0
        idx = np.arange(idx_start, idx_start + steps)
        return pd.Series(np.asarray(forecast, dtype=float), index=idx)
    except Exception:
        return None


def _forecast_stl_arima_ln(y: pd.Series, steps: int, cfg: dict) -> Optional[pd.Series]:
    params = cfg or {}
    y = y.dropna()
    seasonal_periods = int(params.get("seasonal_periods", 0) or 0)
    if seasonal_periods < 2:
        return None
    min_points = int(params.get("min_points", seasonal_periods * 3))
    if len(y) < max(min_points, seasonal_periods * 2):
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            stl = STL(y, period=seasonal_periods, robust=True)
            res = stl.fit()
        remainder = res.trend + res.resid
        fc = None
        arima_params = params.get("auto_arima", {})
        if PMDARIMA_AVAILABLE:
            auto_cfg = {
                "enabled": True,
                "min_points": arima_params.get("min_points", 8),
                "max_p": arima_params.get("max_p", 3),
                "max_q": arima_params.get("max_q", 3),
                "max_d": arima_params.get("max_d", 2),
                "seasonal": arima_params.get("seasonal", False),
                "n_jobs": arima_params.get("n_jobs", 1),
            }
            auto_cfg["seasonal_periods"] = seasonal_periods
            auto_cfg.setdefault("seasonal", True)
            fc = _forecast_auto_arima_ln(remainder, steps, auto_cfg)
        if fc is None or fc.isna().all():
            lin_cfg = params.get("linear_reg", {})
            fc = _forecast_linear_trend_ln(remainder, steps, lin_cfg)
        if fc is None or fc.isna().all():
            return None
        seasonal_tail = res.seasonal.iloc[-seasonal_periods:].values
        if len(seasonal_tail) == 0:
            seasonal_component = np.zeros(steps, dtype=float)
        else:
            seasonal_component = np.resize(seasonal_tail, steps).astype(float)
        forecast_values = fc.values + seasonal_component
        return pd.Series(forecast_values.astype(float), index=fc.index)
    except Exception:
        return None


def _forecast_linear_trend_ln(y: pd.Series, steps: int, cfg: dict) -> Optional[pd.Series]:
    params = cfg or {}
    y = y.dropna()
    if y.empty:
        return None
    window = params.get("window")
    if window:
        try:
            window = int(window)
            if window > 0:
                y = y.iloc[-window:]
        except Exception:
            pass
    if len(y) < 3:
        return None
    x = np.arange(len(y), dtype=float)
    try:
        coeffs = np.polyfit(x, y.values.astype(float), 1)
    except Exception:
        return None
    slope, intercept = coeffs[0], coeffs[1]
    future_x = np.arange(len(y), len(y) + steps, dtype=float)
    forecast = intercept + slope * future_x
    idx_start = int(y.index.max()) + 1 if len(y.index) else 0
    idx = np.arange(idx_start, idx_start + steps)
    return pd.Series(forecast.astype(float), index=idx)


def _choose_univariate_fallback(
    y: pd.Series,
    steps: int,
    fallback_cfg: Optional[Dict[str, object]] = None,
    factor_metrics: Optional[FactorMetrics] = None,
) -> Tuple[str, pd.Series, Optional[float]]:
    settings = fallback_cfg or {}
    cyc_cfg = settings.get("cyclical", {}) if isinstance(settings.get("cyclical", {}), dict) else {}
    is_cyclical = bool(factor_metrics and factor_metrics.cyclical)
    detected_period = factor_metrics.detected_period if factor_metrics else None

    if is_cyclical and cyc_cfg.get("order"):
        order_cfg = cyc_cfg.get("order")
    else:
        order_cfg = settings.get("order") or DEFAULT_FALLBACK_ORDER
    order: Sequence[str] = [str(m).lower() for m in order_cfg]
    smape_base = _rolling_cv_smape(y)

    for method_name in order:
        method = method_name.lower()

        if method == "auto_arima":
            auto_cfg = (
                cyc_cfg.get("auto_arima", {})
                if is_cyclical and cyc_cfg.get("auto_arima")
                else settings.get("auto_arima", {})
            )
            if not auto_cfg.get("enabled", True) or not PMDARIMA_AVAILABLE:
                continue
            cfg_local = dict(auto_cfg)
            if is_cyclical and detected_period and cfg_local.get("seasonal", True):
                cfg_local.setdefault("seasonal", True)
                cfg_local["seasonal_periods"] = detected_period
            fc = _forecast_auto_arima_ln(y, steps, cfg_local)
            if fc is not None and not fc.isna().all():
                return "AUTO_ARIMA", fc, smape_base

        elif method in ("seasonal_ets", "ets"):
            if method == "seasonal_ets":
                if not is_cyclical:
                    continue
                ets_cfg = cyc_cfg.get("seasonal_ets", {})
            else:
                ets_cfg = (
                    cyc_cfg.get("ets", {})
                    if is_cyclical and cyc_cfg.get("ets")
                    else settings.get("ets", {})
                )
            if not ets_cfg.get("enabled", True):
                continue
            cfg_local = dict(ets_cfg)
            if is_cyclical and detected_period:
                cfg_local.setdefault("seasonal", "add")
                cfg_local["seasonal_periods"] = detected_period
                cfg_local.setdefault("min_points", max(6, detected_period * 2))
            fc = _forecast_ets_ln(y, steps, cfg_local)
            if fc is not None and not fc.isna().all():
                label = "SEASONAL_ETS" if method == "seasonal_ets" or cfg_local.get("seasonal") else "ETS"
                return label, fc, smape_base

        elif method in ("stl_arima", "seasonal_arima"):
            if not is_cyclical or not cyc_cfg.get("stl_arima", {}).get("enabled", True):
                continue
            cfg_local = dict(cyc_cfg.get("stl_arima", {}))
            period = detected_period or int(cfg_local.get("seasonal_periods", 0) or 0)
            if not period or period < 2:
                continue
            cfg_local["seasonal_periods"] = period
            fc = _forecast_stl_arima_ln(y, steps, cfg_local)
            if fc is not None and not fc.isna().all():
                return "STL_ARIMA", fc, smape_base

        elif method in ("linear", "linear_reg", "linear_trend"):
            lin_cfg = (
                cyc_cfg.get("linear_reg", {})
                if is_cyclical and cyc_cfg.get("linear_reg")
                else settings.get("linear_reg", {})
            )
            if not lin_cfg.get("enabled", True):
                continue
            fc = _forecast_linear_trend_ln(y, steps, lin_cfg)
            if fc is not None and not fc.isna().all():
                return "LINEAR_TREND", fc, smape_base

        elif method == "arima011":
            y_clean = y.dropna()
            if len(y_clean) < 6:
                continue
            fc = _forecast_arima011_ln(y, steps)
            if fc is None or fc.isna().all():
                continue
            if len(fc) > 1 and all(abs(v - fc.iloc[0]) < 1e-6 for v in fc if pd.notna(v)):
                continue
            penalty = 0.9 if len(y_clean) >= 10 else 1.1
            cv = smape_base * penalty * 0.9
            return "ARIMA011", fc, cv

        elif method == "rw_drift":
            fc = _forecast_rw_drift_ln(y, steps)
            if fc is not None:
                return "RW_DRIFT", fc, smape_base

    fc_default = _forecast_rw_drift_ln(y, steps)
    return "RW_DRIFT", fc_default, smape_base


def _series_to_dict(series: pd.Series) -> Dict[int, float]:
    return {
        int(idx): float(val)
        for idx, val in series.items()
        if pd.notna(val)
    }


def _auto_select_vecm_groups(
    root: Path,
    company: str,
    cfg: dict,
    file_map: dict,
    search_paths: list,
    det: str,
    p_min: int,
    p_max: int,
    alpha: float,
    cointegration_cfg: dict,
    horizon: int,
    cleaned_overrides: Optional[Dict[str, Dict[int, float]]],
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    vecm_cfg = cfg.get("vecm", {})
    auto_cfg = vecm_cfg.get("auto_select", {})
    if not auto_cfg or not auto_cfg.get("enabled", False):
        return [], []

    factors_pool_cfg = auto_cfg.get("factors")
    if factors_pool_cfg:
        factors_pool = [str(f).strip() for f in factors_pool_cfg if f]
    else:
        factors_pool = _load_project_factors(root, company)
    if not factors_pool:
        return [], []

    min_group_size = int(auto_cfg.get("min_group_size", 2))
    max_group_size = int(auto_cfg.get("max_group_size", max(2, len(factors_pool))))
    max_groups = int(auto_cfg.get("max_groups", len(factors_pool)))
    max_combinations = int(auto_cfg.get("max_combinations", 40))
    prefer_manual = bool(auto_cfg.get("prefer_manual", True))
    score_metric = str(auto_cfg.get("score_metric", "aic")).lower()

    run_cfg = cfg.get("run", {})
    require_span_years = int(run_cfg.get("require_span_years", 15))
    require_min_history_years = int(run_cfg.get("require_min_history_years", 12))

    manual_groups = vecm_cfg.get("groups", [])
    manual_sets = {
        tuple(sorted(group.get("factors", group if isinstance(group, list) else [])))
        for group in manual_groups
        if isinstance(group, (dict, list)) and group
    }

    use_dummies = cointegration_cfg.get("use_dummies", False)
    shock_years = cointegration_cfg.get("shock_years", [2020, 2022])
    max_dummies = cointegration_cfg.get("max_dummies", 2)
    dummy_aic_penalty = float(cointegration_cfg.get("dummy_aic_penalty", 10.0))

    results: List[Dict[str, object]] = []
    combo_counter = 0
    factors_pool = list(dict.fromkeys(factors_pool))  # preserve order, remove duplicates

    for size in range(min_group_size, max_group_size + 1):
        for combo in combinations(factors_pool, size):
            if combo_counter >= max_combinations:
                break
            combo_counter += 1
            combo_key = tuple(sorted(combo))
            if combo_key in manual_sets:
                continue

            Y = _stack_block_ln(
                root,
                company,
                list(combo),
                file_map,
                search_paths,
                cleaned_overrides=cleaned_overrides,
            )
            if Y.empty:
                continue

            history_years = len(Y.index.unique())
            if history_years < require_min_history_years:
                continue

            try:
                span_years = int(Y.index.max()) - int(Y.index.min()) + 1
            except Exception:
                span_years = history_years
            if span_years < require_span_years:
                continue

            best = _fit_vecm(
                Y,
                det,
                p_min,
                p_max,
                alpha,
                use_dummies,
                shock_years,
                max_dummies,
                dummy_aic_penalty,
            )

            method = ""
            note = ""
            score = float("-inf")
            rank = 0
            aic = None

            if best and best["rank"] > 0:
                method = "vecm"
                rank = int(best["rank"])
                aic = float(best["aic"])
                if score_metric == "span":
                    score = span_years
                elif score_metric == "rank":
                    score = rank * 1000 + history_years
                else:  # aic
                    score = -aic
            else:
                if best is None:
                    note = "vecm_fit_failed"
                else:
                    note = "vecm_rank_0"
                F = _try_var_forecast_ln(Y, horizon)
                if F is not None:
                    method = "var"
                    rank = 0
                    if score_metric == "span":
                        score = span_years
                    elif score_metric == "rank":
                        score = history_years
                    else:
                        score = history_years
                    note = note or "var_fallback"
                else:
                    continue

            results.append(
                {
                    "combo": list(combo),
                    "history_years": int(history_years),
                    "span_years": int(span_years),
                    "method": method,
                    "rank": int(rank),
                    "score": float(score) if score is not None else None,
                    "aic": float(aic) if aic is not None else None,
                    "note": note,
                }
            )

    if not results:
        # добавим в лог, что авто-подбор не дал результатов
        selection_log = []
        for idx, group in enumerate(manual_groups):
            factors = list(group.get("factors", group if isinstance(group, list) else []))
            selection_log.append(
                {
                    "name": group.get("name", f"manual_{idx+1}"),
                    "factors": factors,
                    "method": "manual",
                    "rank": None,
                    "history_years": None,
                    "score": None,
                    "note": "manual_config",
                    "selected": True if prefer_manual else False,
                    "source": "manual",
                }
            )
        return (manual_groups if prefer_manual else []), selection_log

    results.sort(key=lambda x: x["score"], reverse=True)

    selected_groups: List[Dict[str, object]] = []
    selection_log: List[Dict[str, object]] = []
    selected_keys = set()

    if prefer_manual and manual_groups:
        for idx, group in enumerate(manual_groups):
            if len(selected_groups) >= max_groups:
                break
            factors = list(group.get("factors", group if isinstance(group, list) else []))
            if not factors:
                continue
            name = group.get("name", f"manual_{idx+1}")
            selected_groups.append({"name": name, "factors": factors})
            selected_keys.add(tuple(sorted(factors)))
            selection_log.append(
                {
                    "name": name,
                    "factors": factors,
                    "method": "manual",
                    "rank": None,
                    "history_years": None,
                    "score": None,
                    "note": "manual_config",
                    "selected": True,
                    "source": "manual",
                }
            )

    auto_idx = 1
    for entry in results:
        factors = entry["combo"]
        combo_key = tuple(sorted(factors))
        log_entry = {
            "factors": factors,
            "method": entry["method"],
            "rank": entry["rank"],
            "history_years": entry["history_years"],
            "score": entry["score"],
            "note": entry["note"],
            "aic": entry["aic"],
            "source": "auto",
            "selected": False,
        }

        if len(selected_groups) < max_groups and combo_key not in selected_keys:
            name = f"auto_group_{auto_idx}"
            auto_idx += 1
            selected_groups.append({"name": name, "factors": factors})
            selected_keys.add(combo_key)
            log_entry["name"] = name
            log_entry["selected"] = True
        else:
            name = f"auto_candidate_{auto_idx}"
            auto_idx += 1
            log_entry["name"] = name

        selection_log.append(log_entry)

    return selected_groups, selection_log

def _save_forecast_to_db_and_csv(
    db,
    company: str,
    factor_name: str,
    data: Dict[int, float],
    method: str,
    outdir: Path,
    *,
    history_end_year: int | None = None,
):
    """Сохраняет прогноз только через витрину данных (без экспорта в CSV)."""
    if not data:
        return
    filtered = {}
    for year, value in sorted(data.items()):
        if history_end_year is not None and year <= history_end_year:
            continue
        if pd.isna(value):
            continue
        filtered[int(year)] = float(value)
    if not filtered:
        return
    _save_forecast(db, company, factor_name, filtered, method)


def _save_diagnostics_to_db_and_csv(db, company: str, factor_name: str, method: str, block_name: str,
                                   p: int = None, rank: int = None, span_start: int = None, span_end: int = None,
                                   lb_pvalue: float = None, note: str = None, cv_smape: float = None, outdir: Path = None):
    """Legacy wrapper: сохраняет diagnostics только через витрину данных."""
    _save_diagnostics(db, company, factor_name, method, block_name, p, rank, span_start, span_end, lb_pvalue, note, cv_smape)


def _save_avf_to_db_and_csv(db, company: str, factor_name: str, actual: Dict[int, float], fitted: Dict[int, float], outdir: Path):
    """Legacy wrapper: сохраняет Actual vs Fitted только через витрину данных."""
    _save_actual_vs_fitted(db, company, factor_name, actual, fitted)


def _save_diag_to_db_and_csv(db, company: str, factor_name: str, slope: float, flat_flag: bool, outdir: Path):
    """Legacy wrapper: сохраняет diagnostics только через витрину данных."""
    _save_forecast_diag(db, company, factor_name, slope, flat_flag)

def _try_var_forecast_ln(Y: pd.DataFrame, steps: int):
    """Попытка построить VAR на ln-уровнях с выбором лага по AIC.
    Возвращает DataFrame прогноза или None при неудаче."""
    try:
        if len(Y) < 5:
            return None
        # Ограничиваем maxlags с учетом числа наблюдений и переменных
        # Для VAR(p) с k переменными нужно минимум p*k*k + p*k параметров
        # Ограничиваем maxlags чтобы оставалось достаточно степеней свободы
        max_allowed_lag = max(1, (len(Y) - 2) // max(1, Y.shape[1]))
        maxlags = min(6, max(2, len(Y)//3), max_allowed_lag)
        sel = VAR(Y).select_order(maxlags=maxlags)
        p = int(sel.aic) if hasattr(sel, 'aic') and sel.aic is not None else None
        # Если select_order вернул таблицу, возьмём лучший лаг по aic
        if p is None:
            # иногда sel.aic может быть Series/array
            try:
                p = int(sel.aic.idxmin())  # type: ignore[attr-defined]
            except Exception:
                p = 2
        p = max(1, min(6, p))
        model = VAR(Y).fit(maxlags=p, ic='aic')
        f = model.forecast(Y.values[-model.k_ar:], steps)
        f_ix = np.arange(int(Y.index.max())+1, int(Y.index.max())+1+steps)
        F = pd.DataFrame(f, index=f_ix, columns=Y.columns)
        return F
    except Exception:
        return None
def run_vecm_all(root: str|Path, company: str, cfg_path: str|Path):
    root=Path(root); cfg=_read_yaml(Path(cfg_path)); outdir = None
    logdir = root/f'companies/{company}/outputs/logs'; logdir.mkdir(parents=True, exist_ok=True)
    det=cfg.get('deterministic','ci'); p_min=int(cfg.get('lag_search',{}).get('p_min',1)); p_max=int(cfg.get('lag_search',{}).get('p_max',2))
    alpha=float(cfg.get('rank_test',{}).get('alpha',0.05)); horizon=int(cfg.get('horizon_years',5)); lb_alpha=float(cfg.get('diagnostics',{}).get('ljung_box_alpha',0.05))
    resid_ar1=cfg.get('run',{}).get('resid_ar1',True)
    resid_arma=cfg.get('run',{}).get('resid_arma',False)
    proj=_read_yaml(root/f'companies/{company}/configs/project.yaml'); file_map=proj.get('macro_forecast',{}).get('file_map',{}); search_paths=proj.get('macro_forecast',{}).get('search_paths',[])
    
    # ========== ИНИЦИАЛИЗАЦИЯ ЛОГИРОВАНИЯ ECM ==========
    ecm_logger = None
    try:
        from engine.logging.context import get_logger
        from engine.logging.modules.ecm_logger import ECMLogger
        base_logger = get_logger()
        if base_logger:
            ecm_logger = ECMLogger(base_logger, company)
            factors_list = proj.get('macro_forecast', {}).get('factors', []) or list(file_map.keys())
            ecm_logger.log_vecm_setup(factors_list, {
                "p_min": p_min,
                "p_max": p_max,
                "alpha": alpha,
                "horizon": horizon,
                "deterministic": det
            })
    except:
        pass
    periods_cfg = (
        proj.get('model', {})
        .get('standard', {})
        .get('periods', proj.get('model', {}).get('periods', {}))
        or {}
    )
    history_end_year_cfg = periods_cfg.get('history_end_year')
    fallback_settings = cfg.get('fallback', {})
    preprocess_cfg = cfg.get('preprocess', {})
    coint_test_cfg = cfg.get('cointegration_testing', {})
    
    # Инициализация БД для сохранения результатов
    db = _db_adapter  # Set by caller via set_db_adapter()
    
    cleaned_ln_overrides: Dict[str, Dict[int, float]] = {}
    preprocess_result = None
    auto_shock_candidates: List[Tuple[int, float]] = []
    preprocess_needed = preprocess_cfg.get('enabled', False) or coint_test_cfg.get('auto_detect_shocks', False)
    if preprocess_needed:
        preprocess_options = dict(preprocess_cfg or {})
        if not preprocess_options.get('enabled', False):
            preprocess_options['enabled'] = True
            if 'smoothing' not in preprocess_options:
                preprocess_options['smoothing'] = {'method': 'none'}
        factors_for_preprocess = proj.get('macro_forecast', {}).get('factors', []) or list(file_map.keys())
        preprocess_result = preprocess_macro_history(
            root=root,
            company=company,
            factors=factors_for_preprocess,
            config=preprocess_options,
            history_end_year=history_end_year_cfg,
        )
        cleaned_ln_overrides = preprocess_result.ln_series or {}
        auto_shock_candidates = preprocess_result.auto_shock_candidates or []
        if db is not None:
            try:
                anomaly_rows = []
                for anomaly in preprocess_result.anomalies:
                    if hasattr(anomaly, "to_record"):
                        record = anomaly.to_record()
                    elif isinstance(anomaly, dict):
                        record = anomaly
                    else:
                        continue
                    anomaly_rows.append(record)
                metric_rows = []
                for factor_name, metric in (preprocess_result.metrics or {}).items():
                    if hasattr(metric, "to_record"):
                        metric_rows.append(metric.to_record(factor_name))
                    elif isinstance(metric, dict):
                        record = dict(metric)
                        record["factor_name"] = factor_name
                        metric_rows.append(record)
                if anomaly_rows or metric_rows:
                    db.save_macro_anomaly_report(anomaly_rows, metric_rows)
            except Exception:
                pass
    factor_metrics_map: Dict[str, FactorMetrics] = preprocess_result.metrics if preprocess_result else {}

    # Параметры тестирования коинтеграции
    use_dummies = coint_test_cfg.get('use_dummies', False)
    shock_years = coint_test_cfg.get('shock_years', [2020, 2022])
    max_dummies = coint_test_cfg.get('max_dummies', 2)
    dummy_aic_penalty = float(coint_test_cfg.get('dummy_aic_penalty', 10))
    check_stability = coint_test_cfg.get('check_forecast_stability', True)
    stability_max_change_pct = float(coint_test_cfg.get('stability_max_change_pct', 20.0))
    stability_max_volatility = float(coint_test_cfg.get('stability_max_volatility', 0.15))
    stability_max_trend_slope = float(coint_test_cfg.get('stability_max_trend_slope', 0.05))
    switch_to_univariate = coint_test_cfg.get('switch_to_univariate_if_unstable', True)
    
    auto_groups, selection_log = _auto_select_vecm_groups(
        root,
        company,
        cfg,
        file_map,
        search_paths,
        det,
        p_min,
        p_max,
        alpha,
        coint_test_cfg,
        horizon,
        cleaned_ln_overrides,
    )
    if selection_log is None:
        selection_log = []

    auto_shock_enabled = coint_test_cfg.get('auto_detect_shocks', True)
    merge_manual_shocks = coint_test_cfg.get('merge_with_manual', True)
    max_auto_dummies_cfg = int(coint_test_cfg.get('max_auto_dummies', max_dummies))
    auto_shock_years: List[int] = []
    if auto_shock_enabled and auto_shock_candidates:
        auto_shock_years = [year for year, _ in auto_shock_candidates]
        if max_auto_dummies_cfg > 0:
            auto_shock_years = auto_shock_years[:max_auto_dummies_cfg]
        if merge_manual_shocks:
            shock_years = list(dict.fromkeys(shock_years + auto_shock_years))
        elif auto_shock_years:
            shock_years = auto_shock_years
    max_dummies = max(max_dummies, len(shock_years))

    if preprocess_result:
        selection_log.append(
            {
                "step": "macro_preprocess",
                "auto_shock_candidates": auto_shock_candidates,
                "selected_auto_shocks": auto_shock_years,
                "cyclical_factors": {
                    factor: metric.detected_period
                    for factor, metric in factor_metrics_map.items()
                    if getattr(metric, "cyclical", False)
                },
            }
        )
    if selection_log:
        try:
            (logdir / "vecm_group_selection.json").write_text(
                json.dumps(selection_log, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass
    
    summary=[]
    report_lines=["# VECM Run Report", "", f"Config: {Path(cfg_path)}", ""]
    if use_dummies:
        report_lines.append(f"- Cointegration testing with dummies: enabled")
        report_lines.append(f"- Shock years: {shock_years}")
        report_lines.append(f"- Max dummies: {max_dummies}")
        report_lines.append("")
    elif auto_shock_years:
        report_lines.append(f"- Auto-detected shocks: {auto_shock_years}")
        report_lines.append("")
    elif auto_shock_candidates:
        preview_candidates = [year for year, _ in auto_shock_candidates[:max_auto_dummies_cfg]]
        if preview_candidates:
            report_lines.append(f"- Auto-shock candidates: {preview_candidates}")
            report_lines.append("")
    if factor_metrics_map:
        cyclical_factors = [f for f, metric in factor_metrics_map.items() if getattr(metric, "cyclical", False)]
        if cyclical_factors:
            report_lines.append(f"- Cyclical factors detected: {', '.join(cyclical_factors)}")
            report_lines.append("")
    fallback_order = fallback_settings.get("order")
    if fallback_order:
        report_lines.append(f"- Univariate fallback order: {', '.join(map(str, fallback_order))}")
        report_lines.append("")
    cyc_order_cfg = fallback_settings.get("cyclical", {}).get("order")
    if cyc_order_cfg:
        report_lines.append(f"- Cyclical fallback order: {', '.join(map(str, cyc_order_cfg))}")
        report_lines.append("")
    vecm_cfg = cfg.get('vecm', {})
    groups_source_list = auto_groups if auto_groups else vecm_cfg.get('groups', [])

    if selection_log:
        report_lines.append("## Group Selection Summary")
        for entry in selection_log:
            if entry.get("selected"):
                factors_list = entry.get("factors", [])
                report_lines.append(
                    f"- {entry.get('name')}: {', '.join(factors_list)} "
                    f"({entry.get('method')}, score={entry.get('score')})"
                )
        report_lines.append("")

    if groups_source_list:
        blocks_dict = {}
        for i, group in enumerate(groups_source_list):
            if isinstance(group, dict):
                block_name = group.get('name', f'group_{i}')
                block_factors = group.get('factors', [])
            elif isinstance(group, list):
                block_name = f'group_{i}'
                block_factors = group
            else:
                continue
            if block_factors:
                blocks_dict[block_name] = {'factors': block_factors}
        blocks_source = blocks_dict
    else:
        # Старый формат: blocks (словарь)
        blocks_source = vecm_cfg.get('blocks', {})
    
    for block_name, blk in blocks_source.items():
        facs=list(blk.get('factors',[])); 
        if not facs: continue
        report_lines.append(f"## Block: {block_name}")
        report_lines.append(f"- factors: {', '.join(facs)}")
        Y=_stack_block_ln(
            root,
            company,
            facs,
            file_map,
            search_paths,
            cleaned_overrides=cleaned_ln_overrides,
        )
        # ограничиваем окно на [start_year .. min(last_year_i)]
        start_year=int(cfg.get('window',{}).get('start_year', 2006))
        if not Y.empty:
            last_years=[int(Y[c].dropna().index.max()) for c in Y.columns if not Y[c].dropna().empty]
            if last_years:
                min_last=min(last_years)
                Y=Y[(Y.index>=start_year) & (Y.index<=min_last)]
        report_lines.append(f"- history_years: {len(Y)}")
        if len(Y)<int(cfg.get('min_history_years',15)):
            # Попробовать VAR как более информативный fallback, если истории хоть немного хватает
            F = _try_var_forecast_ln(Y, horizon)
            if F is not None:
                report_lines.append(f"- decision: VAR fallback (insufficient history)")
                ALL = pd.concat([Y, F])
                last = int(Y.index.max())
                for col in Y.columns:
                    fac = col.replace('ln_','')
                    row={'metric':col}
                    for yr,val in ALL[col].items(): row[str(int(yr))]=float(val) if pd.notna(val) else np.nan
                    # Сохраняем прогноз в БД и CSV
                    forecast_dict = _series_to_dict(F[col])
                    _save_forecast_to_db_and_csv(
                        db,
                        company,
                        fac,
                        forecast_dict,
                        'VAR',
                        outdir,
                        history_end_year=last,
                    )
                    # Сохраняем diagnostics
                    _save_diagnostics_to_db_and_csv(db, company, fac, 'VAR', block_name, None, None, int(Y.index.min()), last, None, 'fallback_insufficient_history_var', None, outdir)
                    # fitted (VAR one-step):
                    try:
                        sel = VAR(Y).select_order(maxlags=min(6, max(2, len(Y)//3)))
                        p_sel = int(sel.aic) if hasattr(sel, 'aic') and sel.aic is not None else 2
                        model = VAR(Y).fit(maxlags=p_sel, ic='aic')
                        fv = model.fittedvalues
                        fv.index = Y.index[model.k_ar:]
                        fitted_series = fv[col]
                        actual_dict = {int(yr): float(val) for yr, val in Y[col].items() if pd.notna(val)}
                        fitted_dict = {int(yr): float(val) for yr, val in fitted_series.items() if pd.notna(val)}
                        _save_avf_to_db_and_csv(db, company, fac, actual_dict, fitted_dict, outdir)
                    except Exception:
                        pass
                    summary.append({'factor':fac,'method':'VAR','span_ok':False,'block':block_name})
                report_lines.append("")
                continue
            # Если VAR не получился — унивариантный фоллбек
            report_lines.append(f"- decision: univariate fallback (insufficient history)")
            last=int(Y.index.max()) if len(Y)>0 else None
            for f in facs:
                col=f'ln_{f}'; row={'metric':col}
                method_name = 'RW_DRIFT'
                cv = None
                forecast_dict: Dict[int, float] = {}
                if len(Y)>0 and last is not None:
                    for yr,val in Y[col].items(): row[str(int(yr))]=float(val)
                    y_ln = Y[col]
                    method_name, fc_ln, cv = _choose_univariate_fallback(
                        y_ln,
                        horizon,
                        fallback_settings,
                        factor_metrics_map.get(f),
                    )
                    forecast_dict = _series_to_dict(fc_ln)
                # Сохраняем прогноз в БД и CSV
                _save_forecast_to_db_and_csv(
                    db,
                    company,
                    f,
                    forecast_dict,
                    method_name,
                    outdir,
                    history_end_year=last if last is not None else history_end_year_cfg,
                )
                # Сохраняем diagnostics
                _save_diagnostics_to_db_and_csv(
                    db,
                    company,
                    f,
                    method_name,
                    block_name,
                    None,
                    None,
                    int(Y.index.min()) if len(Y)>0 else None,
                    int(Y.index.max()) if len(Y)>0 else None,
                    None,
                    'fallback_insufficient_history',
                    cv if len(Y)>0 else None,
                    outdir,
                )
                # fitted for univariate
                try:
                    y_ln = Y[col]
                    if method_name == 'ARIMA011':
                        fitted = _fitted_arima011_ln(y_ln)
                    else:
                        fitted = _fitted_rw_drift_ln(y_ln)
                    actual_dict = {int(yr): float(val) for yr, val in y_ln.items() if pd.notna(val)}
                    fitted_dict = {int(yr): float(val) for yr, val in fitted.items() if pd.notna(val)}
                    _save_avf_to_db_and_csv(db, company, f, actual_dict, fitted_dict, outdir)
                except Exception:
                    pass
                summary.append({'factor':f,'method':method_name,'span_ok':False,'block':block_name})
            report_lines.append("")
            continue
        best=_fit_vecm(Y, det, p_min, p_max, alpha, use_dummies, shock_years, max_dummies, dummy_aic_penalty)
        if best is None:
            # Попытка VAR как fallback
            F = _try_var_forecast_ln(Y, horizon)
            if F is not None:
                report_lines.append(f"- decision: VAR fallback (VECM fit failed)")
                ALL = pd.concat([Y, F]); last=int(Y.index.max())
                for col in Y.columns:
                    fac = col.replace('ln_','')
                    row={'metric':col}
                    for yr,val in ALL[col].items(): row[str(int(yr))]=float(val) if pd.notna(val) else np.nan
                    # Сохраняем прогноз в БД и CSV
                    forecast_dict = _series_to_dict(F[col])
                    _save_forecast_to_db_and_csv(
                        db,
                        company,
                        fac,
                        forecast_dict,
                        'VAR',
                        outdir,
                        history_end_year=last,
                    )
                    # Сохраняем diagnostics
                    _save_diagnostics_to_db_and_csv(db, company, fac, 'VAR', block_name, None, None, int(Y.index.min()), last, None, 'fallback_vecm_fit_failed_var', None, outdir)
                    # fitted (VAR one-step)
                    try:
                        sel = VAR(Y).select_order(maxlags=min(6, max(2, len(Y)//3)))
                        p_sel = int(sel.aic) if hasattr(sel, 'aic') and sel.aic is not None else 2
                        model = VAR(Y).fit(maxlags=p_sel, ic='aic')
                        fv = model.fittedvalues
                        fv.index = Y.index[model.k_ar:]
                        fitted_series = fv[col]
                        actual_dict = {int(yr): float(val) for yr, val in Y[col].items() if pd.notna(val)}
                        fitted_dict = {int(yr): float(val) for yr, val in fitted_series.items() if pd.notna(val)}
                        _save_avf_to_db_and_csv(db, company, fac, actual_dict, fitted_dict, outdir)
                    except Exception:
                        pass
                    summary.append({'factor':fac,'method':'VAR','span_ok':False,'block':block_name})
                report_lines.append("")
                continue
            report_lines.append(f"- decision: univariate fallback (VECM fit failed)")
            last=int(Y.index.max())
            for f in facs:
                col=f'ln_{f}'; row={'metric':col}
                for yr,val in Y[col].items(): row[str(int(yr))]=float(val)
                y_ln = Y[col]
                method_name, fc_ln, cv = _choose_univariate_fallback(
                    y_ln,
                    horizon,
                    fallback_settings,
                    factor_metrics_map.get(f),
                )
                forecast_dict = _series_to_dict(fc_ln)
                # Сохраняем прогноз в БД и CSV
                _save_forecast_to_db_and_csv(
                    db,
                    company,
                    f,
                    forecast_dict,
                    method_name,
                    outdir,
                    history_end_year=last,
                )
                # Сохраняем diagnostics
                _save_diagnostics_to_db_and_csv(
                    db,
                    company,
                    f,
                    method_name,
                    block_name,
                    None,
                    None,
                    int(Y.index.min()),
                    last,
                    None,
                    'fallback_vecm_fit_failed',
                    cv,
                    outdir,
                )
                # fitted for univariate
                try:
                    if method_name == 'ARIMA011':
                        fitted = _fitted_arima011_ln(y_ln)
                    else:
                        fitted = _fitted_rw_drift_ln(y_ln)
                    actual_dict = {int(yr): float(val) for yr, val in y_ln.items() if pd.notna(val)}
                    fitted_dict = {int(yr): float(val) for yr, val in fitted.items() if pd.notna(val)}
                    _save_avf_to_db_and_csv(db, company, f, actual_dict, fitted_dict, outdir)
                except Exception:
                    pass
                summary.append({'factor':f,'method':method_name,'span_ok':False,'block':block_name})
            report_lines.append("")
            continue
        m,p,rank=best['model'],best['p'],best['rank']
        report_lines.append(f"- selected_lag_p: {p}")
        report_lines.append(f"- selected_rank: {rank}")
        n_dummies = best.get('n_dummies', 0)
        selected_shocks = best.get('selected_shocks', None)
        if n_dummies > 0:
            report_lines.append(f"- n_dummies: {n_dummies}")
            if selected_shocks:
                report_lines.append(f"- dummy_shock_years: {selected_shocks}")
        
        # Проверка: если rank=0, VECM не имеет смысла, используем VAR fallback
        if rank == 0:
            report_lines.append(f"- decision: VAR fallback (rank=0, no cointegration)")
            F = _try_var_forecast_ln(Y, horizon)
            if F is not None:
                ALL = pd.concat([Y, F]); last=int(Y.index.max())
                for col in Y.columns:
                    fac = col.replace('ln_','')
                    row={'metric':col}
                    for yr,val in ALL[col].items(): row[str(int(yr))]=float(val) if pd.notna(val) else np.nan
                    # Сохраняем прогноз в БД и CSV
                    forecast_dict = _series_to_dict(F[col])
                    _save_forecast_to_db_and_csv(
                        db,
                        company,
                        fac,
                        forecast_dict,
                        'VAR',
                        outdir,
                        history_end_year=last,
                    )
                    # Сохраняем diagnostics
                    _save_diagnostics_to_db_and_csv(db, company, fac, 'VAR', block_name, None, 0, int(Y.index.min()), last, None, 'fallback_rank_0_no_cointegration', None, outdir)
                    # fitted (VAR one-step)
                    try:
                        sel = VAR(Y).select_order(maxlags=min(6, max(2, len(Y)//3)))
                        p_sel = int(sel.aic) if hasattr(sel, 'aic') and sel.aic is not None else 2
                        model = VAR(Y).fit(maxlags=p_sel, ic='aic')
                        fv = model.fittedvalues
                        fv.index = Y.index[model.k_ar:]
                        fitted_series = fv[col]
                        actual_dict = {int(yr): float(val) for yr, val in Y[col].items() if pd.notna(val)}
                        fitted_dict = {int(yr): float(val) for yr, val in fitted_series.items() if pd.notna(val)}
                        _save_avf_to_db_and_csv(db, company, fac, actual_dict, fitted_dict, outdir)
                    except Exception:
                        pass
                    summary.append({'factor':fac,'method':'VAR','span_ok':True,'block':block_name})
                report_lines.append("")
                continue
            else:
                # Если VAR не получился - univariate fallback
                report_lines.append(f"- decision: univariate fallback (rank=0, VAR failed)")
                last=int(Y.index.max())
                for f in facs:
                    col=f'ln_{f}'; row={'metric':col}
                    for yr,val in Y[col].items(): row[str(int(yr))]=float(val)
                    y_ln = Y[col]
                    method_name, fc_ln, cv = _choose_univariate_fallback(
                        y_ln,
                        horizon,
                        fallback_settings,
                        factor_metrics_map.get(f),
                    )
                    forecast_dict = _series_to_dict(fc_ln)
                    # Сохраняем прогноз в БД и CSV
                    _save_forecast_to_db_and_csv(
                        db,
                        company,
                        f,
                        forecast_dict,
                        method_name,
                        outdir,
                        history_end_year=last,
                    )
                    # Сохраняем diagnostics
                    _save_diagnostics_to_db_and_csv(
                        db,
                        company,
                        f,
                        method_name,
                        block_name,
                        None,
                        0,
                        int(Y.index.min()),
                        last,
                        None,
                        'fallback_rank_0_univariate',
                        cv,
                        outdir,
                    )
                    # fitted for univariate
                    try:
                        if method_name == 'ARIMA011':
                            fitted = _fitted_arima011_ln(y_ln)
                        else:
                            fitted = _fitted_rw_drift_ln(y_ln)
                        actual_dict = {int(yr): float(val) for yr, val in y_ln.items() if pd.notna(val)}
                        fitted_dict = {int(yr): float(val) for yr, val in fitted.items() if pd.notna(val)}
                        _save_avf_to_db_and_csv(db, company, f, actual_dict, fitted_dict, outdir)
                    except Exception:
                        pass
                    summary.append({'factor':f,'method':method_name,'span_ok':True,'block':block_name})
                report_lines.append("")
                continue
        
        # экспорт уравнений коинтеграции для блока (читаемый CSV для дальнейшего Markdown-отчёта)
        try:
            beta = getattr(m, 'beta', None)
            if beta is not None:
                eq_rows = []
                # beta имеет размерность (k_endog x rank)
                for r_idx in range(beta.shape[1]):
                    coeffs = beta[:, r_idx]
                    terms = []
                    for coef, col in zip(coeffs, Y.columns):
                        terms.append(f"{coef:+.4f}*{col}")
                    equation = " ".join(terms) + " = 0"
                    eq_rows.append({'rank_idx': int(r_idx+1), 'equation': equation})
                if eq_rows:
                    # Сохраняем уравнения в БД
                    if db is not None:
                        try:
                            for eq_row in eq_rows:
                                db.save_ecm_equation(company, block_name, eq_row['rank_idx'], eq_row['equation'])
                        except Exception:
                            pass
                    report_lines.append(f"- equations_exported: yes ({len(eq_rows)})")
                else:
                    report_lines.append(f"- equations_exported: no (empty beta)")
        except Exception:
            # безопасно пропускаем экспорт уравнений, чтобы не ломать основной пайплайн
            report_lines.append(f"- equations_exported: error (export failed)")
        
        # Прогнозирование с учетом dummy переменных (если они использовались)
        try:
            if n_dummies > 0 and selected_shocks is not None:
                # Модель была построена с exog (dummy переменными)
                # При прогнозировании нужно передать exog_fc для будущих периодов (нулевые значения)
                # Проверяем, была ли модель построена с exog
                model_has_exog = (
                    hasattr(m, 'model') and hasattr(m.model, 'exog') and m.model.exog is not None
                ) or (
                    hasattr(m, 'exog') and m.exog is not None
                )
                if model_has_exog:
                    last_year = int(Y.index.max())
                    # Создаем exog_fc для будущих периодов (все нули, так как dummy относятся только к историческим шокам)
                    # Важно: exog_fc должен быть numpy array или DataFrame с правильной формой
                    exog_fc = np.zeros((horizon, n_dummies))
                    # Пробуем разные варианты передачи exog (в зависимости от версии statsmodels)
                    # statsmodels VECM требует exog_fc для будущих значений экзогенных переменных
                    try:
                        F = m.predict(steps=horizon, exog_fc=exog_fc)
                    except TypeError:
                        try:
                            # Альтернативный вариант: передать как DataFrame
                            forecast_years = np.arange(last_year + 1, last_year + 1 + horizon)
                            exog_future = pd.DataFrame({
                                f'dummy_{y}': [0] * horizon for y in selected_shocks
                            }, index=forecast_years)
                            F = m.predict(steps=horizon, exog_fc=exog_future)
                        except TypeError:
                            try:
                                F = m.predict(steps=horizon, exog=exog_fc)
                            except TypeError:
                                try:
                                    F = m.predict(steps=horizon, exog_future=exog_fc)
                                except TypeError:
                                    # Если не поддерживается - используем без exog (dummy влияли только на построение модели)
                                    F = m.predict(steps=horizon)
                else:
                    # Модель без exog - стандартное прогнозирование
                    F = m.predict(steps=horizon)
            else:
                # Модель без dummy - стандартное прогнозирование
                F = m.predict(steps=horizon)
        except Exception as e:
            # Fallback: если прогнозирование с exog не удалось, пробуем без exog
            try:
                F = m.predict(steps=horizon)
            except Exception:
                # Если и это не удалось - пропускаем этот блок
                report_lines.append(f"- ERROR: прогнозирование не удалось: {str(e)}")
                continue
        
        f_ix = np.arange(int(Y.index.max())+1, int(Y.index.max())+1+horizon)
        F = pd.DataFrame(F, index=f_ix, columns=Y.columns)
        # Обработка resid с защитой от ошибок (если включен resid_ar1 или resid_arma)
        try:
            resid=pd.DataFrame(m.resid, columns=Y.columns); 
            if resid_arma:
                phis_thetas = _apply_residual_arma_if_needed(resid, lb_alpha)
                phi = {c: pt[0] for c, pt in phis_thetas.items()}  # Извлекаем только phi для обратной совместимости
            else:
                phi=_apply_residual_ar1_if_needed(resid, lb_alpha) if resid_ar1 else {c: 0.0 for c in Y.columns}
        except Exception as e:
            # Если resid недоступен, используем пустые phi
            phi = {c: 0.0 for c in Y.columns}
        ALL=pd.concat([Y,F]); last=int(Y.index.max())
        
        # Проверяем стабильность прогноза
        use_univariate = False
        unstable_factors = []
        if check_stability:
            for col in Y.columns:
                last_val = Y[col].iloc[-1]
                forecast_series = F[col]
                is_stable, reason = check_forecast_stability(
                    forecast_series, last_val, 
                    stability_max_change_pct, stability_max_volatility, stability_max_trend_slope
                )
                if not is_stable:
                    use_univariate = True
                    unstable_factors.append(f"{col.replace('ln_','')}")
                    report_lines.append(f"  - factor {col.replace('ln_','')}: forecast unstable ({reason})")
        
        # Дополнительная проверка: совокупная нестабильность блока
        if check_stability and not use_univariate and len(Y.columns) >= 2:
            # Если несколько факторов идут в одном направлении с большими изменениями - это может быть проблемой
            slopes = []
            for col in Y.columns:
                s = ALL[col]
                if pd.notna(s.loc[last+1]) and pd.notna(s.loc[last+horizon]):
                    slope = float((s.loc[last+horizon] - s.loc[last+1]) / max(1,horizon-1))
                    slopes.append(slope)
            if slopes:
                avg_slope = np.mean(slopes)
                if abs(avg_slope) > 0.03:  # Сильный совокупный тренд
                    # Все факторы идут в одном направлении - возможна проблема с коинтеграцией
                    sign_consistency = all(np.sign(s) == np.sign(slopes[0]) for s in slopes)
                    if sign_consistency and all(abs(s) > 0.02 for s in slopes):
                        use_univariate = True
                        unstable_factors = [f"block_{block_name}"]
                        report_lines.append(f"  - block avg slope: {avg_slope:.4f}, all factors declining/growing (cointegration issue)")
        
        if use_univariate and switch_to_univariate:
            report_lines.append(f"- decision: switching to univariate ECM (VECM forecast unstable)")
            for f in facs:
                col=f'ln_{f}'; row={'metric':col}
                for yr,val in Y[col].items(): row[str(int(yr))]=float(val)
                y_ln = Y[col]
                method_name, fc_ln, cv = _choose_univariate_fallback(
                    y_ln,
                    horizon,
                    fallback_settings,
                    factor_metrics_map.get(f),
                )
                forecast_dict = _series_to_dict(fc_ln)
                # Сохраняем прогноз в БД и CSV
                _save_forecast_to_db_and_csv(
                    db,
                    company,
                    f,
                    forecast_dict,
                    method_name,
                    outdir,
                    history_end_year=last,
                )
                # Сохраняем diagnostics
                _save_diagnostics_to_db_and_csv(
                    db,
                    company,
                    f,
                    method_name,
                    block_name,
                    None,
                    None,
                    int(Y.index.min()),
                    last,
                    None,
                    'forecast_unstable_switched_to_univariate',
                    cv,
                    outdir,
                )
                # fitted for univariate
                try:
                    if method_name == 'ARIMA011':
                        fitted = _fitted_arima011_ln(y_ln)
                    else:
                        fitted = _fitted_rw_drift_ln(y_ln)
                    actual_dict = {int(yr): float(val) for yr, val in y_ln.items() if pd.notna(val)}
                    fitted_dict = {int(yr): float(val) for yr, val in fitted.items() if pd.notna(val)}
                    _save_avf_to_db_and_csv(db, company, f, actual_dict, fitted_dict, outdir)
                except Exception:
                    pass
                
                # ========== ЛОГИРОВАНИЕ FALLBACK (нестабильный прогноз) ==========
                if ecm_logger:
                    try:
                        ecm_logger.log_fallback(f, "forecast_unstable", method_name, "VECM")
                        forecast_years = list(forecast_dict.keys())
                        ecm_logger.log_forecast(f, forecast_dict, method_name, forecast_years)
                    except Exception:
                        pass
                
                summary.append({'factor':f,'method':method_name,'span_ok':True,'block':block_name})
            report_lines.append("")
            continue
        
        for col in Y.columns:
            fac=col.replace('ln_',''); s=ALL[col].copy()
            if phi[col]!=0.0:
                tail=s.loc[last+1:]
                if not tail.empty:
                    corr=[tail.iloc[0]]
                    for t in range(1,len(tail)):
                        corr.append(phi[col]*corr[t-1] + (1-phi[col])*tail.iloc[t])
                    s.loc[last+1:]=corr
            row={'metric':col}
            for yr,val in s.items(): row[str(int(yr))]=float(val) if pd.notna(val) else np.nan
            # Сохраняем прогноз в БД и CSV
            s_dict = {
                int(yr): float(val)
                for yr, val in s.loc[last+1:].items()
                if pd.notna(val)
            }
            _save_forecast_to_db_and_csv(
                db,
                company,
                fac,
                s_dict,
                'VECM',
                outdir,
                history_end_year=last,
            )
            lb=float(acorr_ljungbox(resid[col], lags=[1], return_df=True)['lb_pvalue'].iloc[0])
            _save_diagnostics_to_db_and_csv(db, company, fac, 'VECM', block_name, int(p), int(rank), int(Y.index.min()), last, lb, None, None, outdir)
            report_lines.append(f"  - factor {fac}: lb_pvalue={lb:.4f}")
            tail_vals=s.loc[last+1:]
            slope=float((tail_vals.iloc[-1]-tail_vals.iloc[0]) / max(1,len(tail_vals)-1)) if len(tail_vals)>1 else 0.0
            _save_diag_to_db_and_csv(db, company, fac, slope, abs(slope)<1e-6, outdir)
            
            # ========== ЛОГИРОВАНИЕ РЕЗУЛЬТАТОВ VECM ==========
            if ecm_logger:
                try:
                    ecm_logger.log_vecm_results(fac, block_name, {
                        "method": "VECM",
                        "rank": int(rank),
                        "p": int(p),
                        "span_start": int(Y.index.min()),
                        "span_end": last,
                        "lb_pvalue": float(lb) if not pd.isna(lb) else None,
                        "cv_smape": None,
                        "note": None
                    })
                    
                    # Логируем прогноз
                    forecast_years = list(s_dict.keys())
                    ecm_logger.log_forecast(fac, s_dict, "VECM", forecast_years)
                except Exception:
                    pass
            
            summary.append({'factor':fac,'method':'VECM','span_ok':True,'block':block_name,'p':p,'rank':rank})
        report_lines.append("")
    summary_df = pd.DataFrame(summary)
    (logdir/"vecm_run_report.md").write_text("\n".join(report_lines), encoding='utf-8')
    
    # ========== ЛОГИРОВАНИЕ ЗАВЕРШЕНИЯ ECM ==========
    if ecm_logger:
        try:
            # Подсчитываем статистику
            factors_processed = len(summary_df) if not summary_df.empty else 0
            vecm_count = len(summary_df[summary_df['method'] == 'VECM']) if not summary_df.empty else 0
            fallback_count = factors_processed - vecm_count
            
            ecm_logger.log_module_end({
                "status": "completed",
                "factors_processed": int(factors_processed),
                "vecm_count": int(vecm_count),
                "fallback_count": int(fallback_count),
                "blocks_processed": len(blocks_source) if 'blocks_source' in locals() else 0
            }, {
                "summary": summary_df.to_dict('records') if not summary_df.empty else []
            })
        except Exception:
            pass
    
    # Закрываем БД
    if db is not None:
        try:
            db.close()
        except Exception:
            pass
    return summary_df

