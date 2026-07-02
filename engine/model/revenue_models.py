"""
Модели прогнозирования Revenue.

Режимы (от простого к сложному):
1. ewa       — EWA темп роста (дефолт, без макро)
2. macro_ols — OLS регрессия на один фактор (beta × Δln(factor))
3. macro_en  — Elastic Net на несколько факторов (sklearn, опционально)
4. chainlink — любой из выше + chain-link к последнему историческому уровню

Принцип консистентности: Revenue и COGS должны использовать одни факторы.
Если Revenue ~ HRC, то COGS = Revenue × ratio (driver метод) — автоматически консистентно.
"""
from __future__ import annotations

import math
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── OLS 1-фактор ─────────────────────────────────────────────────────────────

# NOTE: currently unused — reserved for future multi-factor revenue modeling
def ols_single_factor(
    revenue_history: Dict[int, float],
    factor_history: Dict[int, float],
    factor_forecast: Dict[int, float],
    forecast_years: List[int],
    use_dln: bool = True,
    chainlink: bool = True,
) -> Tuple[Dict[int, float], float, float]:
    """
    Revenue ~ beta × Δln(factor).

    Алгоритм:
    1. Обучение: OLS на исторических Δln(Revenue) ~ Δln(factor)
    2. Прогноз: Δln(Rev_t) = alpha + beta × Δln(factor_t)
    3. Chain-link: Rev_t = Rev_last × exp(Σ Δln)

    Returns:
        (forecast_dict, beta, r2)
    """
    common = sorted(set(revenue_history) & set(factor_history))
    if len(common) < 4:
        return {}, 0.0, 0.0

    if use_dln:
        dy, dx = [], []
        for i in range(1, len(common)):
            y0, y1 = common[i-1], common[i]
            if revenue_history[y0] > 0 and factor_history[y0] > 0:
                dy.append(math.log(revenue_history[y1] / revenue_history[y0]))
                dx.append(math.log(factor_history[y1] / factor_history[y0]))
    else:
        dy = [revenue_history[y] for y in common]
        dx = [factor_history[y] for y in common]

    if not dy:
        return {}, 0.0, 0.0

    n = len(dx)
    mx = sum(dx) / n; my = sum(dy) / n
    cov = sum((dx[i]-mx)*(dy[i]-my) for i in range(n))
    var = sum((dx[i]-mx)**2 for i in range(n))
    if abs(var) < 1e-12:
        return {}, 0.0, 0.0

    beta  = cov / var
    alpha = my - beta * mx

    ss_res = sum((dy[i] - alpha - beta*dx[i])**2 for i in range(n))
    ss_tot = sum((dy[i] - my)**2 for i in range(n))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    logger.info(f"Revenue OLS: alpha={alpha:.4f} beta={beta:.4f} R²={r2:.3f}")

    if chainlink:
        last_hist_year = max(revenue_history.keys())
        last_rev = revenue_history[last_hist_year]
        last_factor = factor_history.get(last_hist_year) or factor_history[max(factor_history.keys())]
    else:
        last_rev = None
        last_factor = None

    forecast = {}
    cum_ln = 0.0
    prev_factor = last_factor

    for yr in sorted(forecast_years):
        f_curr = factor_forecast.get(yr)
        if f_curr is None or prev_factor is None or prev_factor <= 0:
            cum_ln += alpha
        else:
            d_factor = math.log(f_curr / prev_factor) if use_dln else f_curr
            cum_ln += alpha + beta * d_factor
            prev_factor = f_curr

        if chainlink and last_rev:
            forecast[yr] = last_rev * math.exp(cum_ln)
        else:
            forecast[yr] = math.exp(cum_ln)

    return forecast, beta, r2


# NOTE: currently unused — reserved for future multi-factor revenue modeling
def ols_multi_factor(
    revenue_history: Dict[int, float],
    factors_history: Dict[str, Dict[int, float]],
    factors_forecast: Dict[str, Dict[int, float]],
    forecast_years: List[int],
    use_dln: bool = True,
    chainlink: bool = True,
    l1_ratio: float = 0.0,
) -> Tuple[Dict[int, float], Dict[str, float], float]:
    """
    Revenue ~ Σ beta_i × Δln(factor_i).

    Returns:
        (forecast_dict, betas_dict, r2)
    """
    common = sorted(set(revenue_history.keys()))
    for factor_series in factors_history.values():
        common = sorted(set(common) & set(factor_series.keys()))

    if len(common) < 5:
        logger.warning(f"Multi-factor OLS: недостаточно данных ({len(common)} лет)")
        return {}, {}, 0.0

    factor_names = list(factors_history.keys())

    Y, X_rows = [], []
    for i in range(1, len(common)):
        y0, y1 = common[i-1], common[i]
        if revenue_history[y0] <= 0:
            continue
        y_val = math.log(revenue_history[y1] / revenue_history[y0]) if use_dln else revenue_history[y1]
        x_row = []
        valid = True
        for fname in factor_names:
            fs = factors_history[fname]
            if fs.get(y0, 0) <= 0 or fs.get(y1, 0) <= 0:
                valid = False
                break
            x_val = math.log(fs[y1] / fs[y0]) if use_dln else fs[y1]
            x_row.append(x_val)
        if valid:
            Y.append(y_val)
            X_rows.append(x_row)

    if not Y or not X_rows[0]:
        return {}, {}, 0.0

    n_obs = len(Y)
    n_fac = len(factor_names)

    if l1_ratio > 0:
        try:
            from sklearn.linear_model import ElasticNet
            from sklearn.preprocessing import StandardScaler
            import numpy as np

            X_arr = np.array(X_rows)
            Y_arr = np.array(Y)
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X_arr)
            en = ElasticNet(alpha=0.1, l1_ratio=l1_ratio, fit_intercept=True, max_iter=1000)
            en.fit(X_scaled, Y_arr)
            betas_raw = en.coef_ / scaler.scale_
            alpha_raw = en.intercept_ - sum(betas_raw[i] * scaler.mean_[i] for i in range(n_fac))
            betas = {fname: float(betas_raw[i]) for i, fname in enumerate(factor_names)}
            alpha = float(alpha_raw)
            Y_pred = [alpha + sum(betas[fname] * X_rows[j][i]
                                  for i, fname in enumerate(factor_names))
                      for j in range(n_obs)]
            ss_res = sum((Y[j]-Y_pred[j])**2 for j in range(n_obs))
            ss_tot = sum((Y[j]-sum(Y)/n_obs)**2 for j in range(n_obs))
            r2 = 1 - ss_res/ss_tot if ss_tot > 0 else 0.0
            logger.info(f"Elastic Net R²={r2:.3f} betas={betas}")
        except ImportError:
            logger.info("sklearn недоступен, используем OLS")
            l1_ratio = 0.0

    if l1_ratio == 0:
        k = n_fac + 1
        XtX = [[0.0]*k for _ in range(k)]
        XtY = [0.0]*k
        for j in range(n_obs):
            row = [1.0] + X_rows[j]
            for a in range(k):
                XtY[a] += row[a] * Y[j]
                for b in range(k):
                    XtX[a][b] += row[a] * row[b]
        Ab = [XtX[i][:] + [XtY[i]] for i in range(k)]
        for col in range(k):
            pivot = Ab[col][col]
            if abs(pivot) < 1e-12:
                continue
            for row_i in range(k):
                if row_i == col: continue
                f = Ab[row_i][col] / pivot
                for j in range(k+1):
                    Ab[row_i][j] -= f * Ab[col][j]
        coeffs = [Ab[i][k] / Ab[i][i] if abs(Ab[i][i]) > 1e-12 else 0.0 for i in range(k)]
        alpha = coeffs[0]
        betas = {fname: coeffs[i+1] for i, fname in enumerate(factor_names)}
        Y_pred = [alpha + sum(betas[fname] * X_rows[j][i]
                              for i, fname in enumerate(factor_names))
                  for j in range(n_obs)]
        my = sum(Y)/n_obs
        ss_res = sum((Y[j]-Y_pred[j])**2 for j in range(n_obs))
        ss_tot = sum((Y[j]-my)**2 for j in range(n_obs))
        r2 = 1 - ss_res/ss_tot if ss_tot > 0 else 0.0
        logger.info(f"Multi OLS: alpha={alpha:.4f} betas={betas} R²={r2:.3f}")

    last_hist_year = max(revenue_history.keys())
    last_rev = revenue_history[last_hist_year]
    last_factors = {fname: factors_history[fname].get(last_hist_year)
                    or factors_history[fname][max(factors_history[fname].keys())]
                    for fname in factor_names}

    forecast = {}
    cum_ln = 0.0
    prev_factors = dict(last_factors)

    for yr in sorted(forecast_years):
        d_factors = {}
        for fname in factor_names:
            f_curr = factors_forecast.get(fname, {}).get(yr)
            f_prev = prev_factors.get(fname)
            if f_curr and f_prev and f_prev > 0:
                d_factors[fname] = math.log(f_curr / f_prev) if use_dln else f_curr
                prev_factors[fname] = f_curr
            else:
                d_factors[fname] = 0.0
        step = alpha + sum(betas[fname] * d_factors[fname] for fname in factor_names)
        cum_ln += step
        forecast[yr] = last_rev * math.exp(cum_ln) if chainlink else math.exp(cum_ln)

    return forecast, betas, r2


def ewa_with_clamp(
    revenue_history: Dict[int, float],
    forecast_years: List[int],
    halflife: float = 3.0,
    percentile_lo: float = 0.05,
    percentile_hi: float = 0.95,
) -> Dict[int, float]:
    """
    EWA темп роста с clamp к историческому диапазону роста.
    Используется как fallback когда нет макро-факторов.
    """
    sorted_years = sorted(revenue_history.keys())
    if len(sorted_years) < 2:
        return {}

    values = [revenue_history[y] for y in sorted_years]
    last_year  = sorted_years[-1]
    last_value = values[-1]

    alpha = 1.0 - math.exp(-math.log(2) / halflife)
    growth_rates = []
    for i in range(1, len(values)):
        if values[i-1] > 0:
            growth_rates.append(math.log(values[i] / values[i-1]))

    if not growth_rates:
        return {}

    ewa_growth = growth_rates[0]
    for g in growth_rates[1:]:
        ewa_growth = alpha * g + (1 - alpha) * ewa_growth

    sorted_gr = sorted(growth_rates)
    n = len(sorted_gr)
    lo = sorted_gr[max(0, int(n*percentile_lo))]
    hi = sorted_gr[min(n-1, int(n*percentile_hi))]
    ewa_growth_clamped = max(lo, min(hi, ewa_growth))

    forecast = {}
    val = last_value
    for yr in sorted(forecast_years):
        val = val * math.exp(ewa_growth_clamped)
        forecast[yr] = val

    return forecast
