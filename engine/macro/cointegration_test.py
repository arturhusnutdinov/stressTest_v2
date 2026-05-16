"""
Модуль тестирования коинтеграции с dummy-переменными для структурных разрывов

Обеспечивает:
1. Тестирование коинтеграции с учетом структурных разрывов (2020 COVID, 2022 Ukraine war)
2. Штрафование за избыточное использование dummy переменных
3. Переключение на univariate ECM если VECM дает нестабильный прогноз
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from statsmodels.tsa.vector_ar.vecm import select_coint_rank, VECM
from statsmodels.tsa.arima.model import ARIMA


# Годы с известными структурными шоками
STRUCTURAL_SHOCKS = {
    2020: "COVID-19 pandemic",
    2022: "Ukraine war, Russia sanctions"
}


def create_dummy_matrix(Y: pd.DataFrame, shock_years: List[int] = None) -> pd.DataFrame:
    """
    Создает матрицу dummy переменных для структурных разрывов
    
    Args:
        Y: DataFrame с индексом - годы
        shock_years: Список годов с шоками (по умолчанию из STRUCTURAL_SHOCKS)
    
    Returns:
        DataFrame с dummy переменными по годам
    """
    if shock_years is None:
        shock_years = list(STRUCTURAL_SHOCKS.keys())
    
    dummy_data = {}
    for year in shock_years:
        dummy_data[f'dummy_{year}'] = [1 if y == year else 0 for y in Y.index]
    
    return pd.DataFrame(dummy_data, index=Y.index)


def test_cointegration_with_dummies(
    Y: pd.DataFrame, 
    p: int, 
    det: str = 'ci',
    alpha: float = 0.05,
    shock_years: List[int] = None,
    max_dummies: int = None,
    dummy_aic_penalty: float = 10.0
) -> Tuple[Optional[VECM], float, int, Optional[List[int]]]:
    """
    Тестирует коинтеграцию с dummy переменными
    
    Args:
        Y: DataFrame с временными рядами в ln
        p: Порядок лага
        det: Детерминистический компонент ('ci', 'li', 'cili', 'nc')
        alpha: Уровень значимости
        shock_years: Годы с шоками
        max_dummies: Максимальное количество dummy переменных
    
    Returns:
        Tuple (модель VECM, AIC, количество dummy переменных, список выбранных shock_years) 
        или (None, inf, 0, None) при неудаче
    """
    if shock_years is None:
        shock_years = list(STRUCTURAL_SHOCKS.keys())
    
    if max_dummies is None:
        # По умолчанию: не более 30% от длины ряда
        max_dummies = max(1, int(len(Y) * 0.3))
    
    best_model = None
    best_aic = float('inf')
    best_n_dummies = 0
    best_selected_shocks = None
    
    # Попробуем с разным количеством dummy переменных
    max_test_dummies = min(len(shock_years), max_dummies)
    
    # Сначала без dummy
    try:
        rank = select_coint_rank(Y.values, det_order=1 if det in ('ci', 'li', 'cili') else 0, 
                                   method='trace', signif=alpha, k_ar_diff=p-1).rank
        m = VECM(Y, k_ar_diff=p-1, coint_rank=rank, deterministic=det).fit()
        n_params = Y.shape[1] * p + Y.shape[1] * rank + (1 if det in ('ci', 'li', 'cili') else 0)
        aic = -2 * m.llf + 2 * n_params
        if aic < best_aic:
            best_model = m
            best_aic = aic
            best_n_dummies = 0
            best_selected_shocks = None
    except Exception:
        pass
    
    # Теперь с dummy переменными
    dummy_matrix = create_dummy_matrix(Y, shock_years)
    
    for n_dummies in range(1, max_test_dummies + 1):
        # Выбираем n_dummies лет с наибольшими отклонениями
        # Определяем отклонения как средний абсолютный change по всем факторам
        if n_dummies == 1 and len(shock_years) >= 1:
            selected_shocks = shock_years[:n_dummies]
        else:
            # Для нескольких dummy выбираем годы с наибольшими скачками
            Y_diff = Y.diff().abs().mean(axis=1)
            Y_diff_sorted = Y_diff.sort_values(ascending=False)
            selected_shocks = [int(y) for y in Y_diff_sorted.head(n_dummies).index if y in shock_years][:n_dummies]
        
        if len(selected_shocks) < n_dummies:
            continue
        
        try:
            # Создаем dummy матрицу для выбранных шоков
            exog_dummies = pd.DataFrame({
                f'dummy_{y}': [1 if yr == y else 0 for yr in Y.index] 
                for y in selected_shocks
            }, index=Y.index)
            
            # Пробуем с dummy переменными, включая их в модель через параметр exog
            # VECM поддерживает exog для экзогенных переменных в краткосрочной динамике
            # Определяем rank коинтеграции БЕЗ учета dummy (на чистом ряде)
            rank = select_coint_rank(Y.values, det_order=1 if det in ('ci', 'li', 'cili') else 0,
                                       method='trace', signif=alpha, k_ar_diff=p-1).rank
            
            # Строим VECM с dummy переменными как экзогенными
            # exog включается в краткосрочную динамику (error correction и lagged differences)
            m = VECM(Y, k_ar_diff=p-1, coint_rank=rank, deterministic=det, exog=exog_dummies).fit()
            
            # Вычисляем AIC с учетом реальных параметров модели (включая dummy)
            # Параметры: эндогенные переменные * лаги + эндогенные * rank + детерминистика + dummy переменные
            n_params_base = Y.shape[1] * p + Y.shape[1] * rank + (1 if det in ('ci', 'li', 'cili') else 0)
            # Dummy переменные добавляют параметры: n_dummies * Y.shape[1] (влияние на каждую эндогенную переменную)
            n_params_dummy = n_dummies * Y.shape[1]
            n_params = n_params_base + n_params_dummy
            aic = -2 * m.llf + 2 * n_params
            
            # Дополнительный штраф для предотвращения избыточного использования dummy
            aic_with_penalty = aic + dummy_aic_penalty * n_dummies
            
            if aic_with_penalty < best_aic:
                best_model = m
                best_aic = aic_with_penalty
                best_n_dummies = n_dummies
                best_selected_shocks = selected_shocks.copy()
        except Exception as e:
            # Если не удалось построить модель с exog, пропускаем этот вариант
            # Возможные причины: недостаточно данных, проблемы с размерностью, и т.д.
            continue
    
    if best_model is None:
        return None, float('inf'), 0, None
    
    return best_model, best_aic, best_n_dummies, best_selected_shocks


def check_forecast_stability(
    forecast: pd.Series, 
    last_history: float,
    max_change_pct: float = 20.0,
    max_volatility: float = 0.15,
    max_trend_slope: float = 0.05
) -> Tuple[bool, str]:
    """
    Проверяет стабильность прогноза VECM
    
    Args:
        forecast: Прогнозные значения (ln-уровни)
        last_history: Последнее историческое значение (ln)
        max_change_pct: Максимальное допустимое изменение YoY в %
        max_volatility: Максимальная волатильность (std первых разностей в логарифмах)
        max_trend_slope: Максимальный средний наклон тренда (в ln-единицах)
    
    Returns:
        Tuple (стабильный ли прогноз, причина если нестабильный)
    """
    if len(forecast) == 0:
        return False, "empty_forecast"
    
    forecast_values = forecast.values
    first_forecast = forecast_values[0]
    
    # Проверка 1: Слишком большое изменение относительно последнего исторического значения
    change_ln = first_forecast - last_history
    change_pct = (np.exp(change_ln) - 1) * 100
    
    if abs(change_pct) > max_change_pct:
        return False, f"too_large_initial_change_{change_pct:.1f}pct"
    
    # Проверка 2: Волатильность в первых разностях (YoY изменения)
    if len(forecast_values) > 1:
        diffs = np.diff(forecast_values)
        vol = np.std(diffs) if len(diffs) > 0 else 0
        if vol > max_volatility:
            return False, f"too_volatile_std_{vol:.3f}"
    
    # Проверка 3: Монотонное сильное падение/рост
    if len(forecast_values) >= 3:
        # Проверяем направление тренда
        first_half = forecast_values[:len(forecast_values)//2]
        second_half = forecast_values[len(forecast_values)//2:]
        
        trend_first = np.mean(np.diff(first_half))
        trend_second = np.mean(np.diff(second_half))
        
        # Если оба тренда сильные и одного знака - возможна нестабильность
        if abs(trend_first) > max_trend_slope and abs(trend_second) > max_trend_slope:
            if np.sign(trend_first) == np.sign(trend_second):
                return False, f"persistent_extreme_trend_{trend_first:.3f}"
    
    # Проверка 4: Резкий поворот (изменение направления изменения)
    if len(forecast_values) >= 3:
        diffs = np.diff(forecast_values)
        # Проверяем, есть ли резкое изменение направления
        sign_changes = np.sum(np.diff(np.sign(diffs)) != 0)
        if sign_changes > len(diffs) / 2:
            # Слишком много изменений направления - нестабильно
            return False, f"too_many_direction_changes_{sign_changes}"
    
    # Проверка 5: Проверяем изменения YoY (не абсолютные, а процентные)
    if len(forecast_values) >= 2:
        changes_pct = []
        for i in range(1, len(forecast_values)):
            change_ln_yy = forecast_values[i] - forecast_values[i-1]
            change_pct_yy = (np.exp(change_ln_yy) - 1) * 100
            changes_pct.append(change_pct_yy)
        
        # Слишком сильное изменение YoY (используем параметр max_change_pct)
        if any(abs(cp) > max_change_pct for cp in changes_pct):
            max_change = max(abs(cp) for cp in changes_pct)
            return False, f"extreme_yoy_change_{max_change:.1f}pct"
    
    return True, "stable"


def select_forecast_method(
    Y: pd.DataFrame,
    p: int,
    det: str = 'ci',
    alpha: float = 0.05,
    horizon: int = 5,
    shock_years: List[int] = None,
    last_history_year: int = None
) -> Tuple[str, Optional[VECM], Dict]:
    """
    Выбирает метод прогнозирования: VECM, VAR или univariate ECM
    
    Args:
        Y: DataFrame с временными рядами в ln
        p: Порядок лага для VECM
        det: Детерминистический компонент
        alpha: Уровень значимости
        horizon: Горизонт прогноза
        shock_years: Годы с шоками
        last_history_year: Последний год истории
    
    Returns:
        Tuple (метод, модель, диагностика)
    """
    if shock_years is None:
        shock_years = list(STRUCTURAL_SHOCKS.keys())
    
    if last_history_year is None:
        last_history_year = int(Y.index.max())
    
    # Шаг 1: Попробуем VECM
    try:
        rank = select_coint_rank(Y.values, det_order=1 if det in ('ci', 'li', 'cili') else 0,
                                   method='trace', signif=alpha, k_ar_diff=p-1).rank
        vecm_model = VECM(Y, k_ar_diff=p-1, coint_rank=rank, deterministic=det).fit()
        
        # Генерируем пробный прогноз для проверки стабильности
        forecast_vecm = vecm_model.predict(steps=horizon)
        forecast_df = pd.DataFrame(forecast_vecm, 
                                   index=range(last_history_year+1, last_history_year+1+horizon),
                                   columns=Y.columns)
        
        # Проверяем стабильность для каждого фактора
        all_stable = True
        unstable_factors = []
        
        for col in Y.columns:
            last_val = Y[col].iloc[-1]
            forecast_series = forecast_df[col]
            is_stable, reason = check_forecast_stability(forecast_series, last_val)
            
            if not is_stable:
                all_stable = False
                unstable_factors.append(f"{col}: {reason}")
        
        if all_stable:
            return "VECM", vecm_model, {
                "method": "VECM",
                "p": p,
                "rank": rank,
                "n_dummies": 0,
                "unstable_factors": []
            }
        else:
            # VECM нестабилен - попробуем univariate ECM
            pass
            
    except Exception as e:
        # VECM не подобрался
        pass
    
    # Шаг 2: VECM нестабилен или не подобрался - используем univariate ECM
    return "UNIVARIATE_ECM", None, {
        "method": "UNIVARIATE_ECM",
        "reason": "VECM_unstable_or_infeasible",
        "unstable_factors": unstable_factors if 'unstable_factors' in locals() else []
    }

