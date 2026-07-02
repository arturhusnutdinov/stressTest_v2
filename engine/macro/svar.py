"""
SVAR (Structural VAR) модель для макро-прогнозирования.

SVAR позволяет идентифицировать структурные шоки и анализировать их влияние
на макроэкономические переменные через импульсные отклики (IRF).
"""

from __future__ import annotations

import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from statsmodels.tsa.api import VAR
from statsmodels.tsa.vector_ar.svar_model import SVAR

def _save_svar_forecast(db, company: str, factor_name: str, data: Dict[int, float], method: str) -> None:
    if db is None or not data:
        return
    try:
        db.save_macro_forecast(factor_name, data, method=method)
    except Exception:
        pass


def _save_svar_diagnostics(db, company: str, factor_name: str, method: str,
                           irf_data: Optional[Dict] = None, variance_decomp: Optional[Dict] = None) -> None:
    if db is None:
        return
    try:
        db.save_ecm_diagnostics(company, factor_name, method, "svar")
    except Exception:
        pass


def _create_identification_matrix(n_vars: int, identification_type: str = "short_run") -> Optional[np.ndarray]:
    """
    Создает матрицу идентификации для SVAR.
    
    Args:
        n_vars: Количество переменных
        identification_type: Тип идентификации
            - "short_run": Нижняя треугольная матрица (Cholesky decomposition)
            - "long_run": Долгосрочные ограничения
            - "sign": Sign restrictions (требует дополнительной настройки)
    
    Returns:
        Матрица идентификации (n_vars x n_vars) или None для использования Cholesky
    """
    if identification_type == "short_run":
        # Нижняя треугольная матрица для SVAR типа 'A' (Cholesky decomposition)
        # Структура: единицы на диагонали, NaN ниже диагонали (свободные параметры), нули выше
        A = np.zeros((n_vars, n_vars))
        np.fill_diagonal(A, 1.0)  # Единицы на диагонали
        for i in range(n_vars):
            for j in range(i):
                A[i, j] = np.nan  # Свободные параметры ниже диагонали
        return A
    elif identification_type == "long_run":
        # Долгосрочные ограничения (требует дополнительной логики)
        # Пока используем простую структуру
        A = np.eye(n_vars)
        for i in range(n_vars):
            for j in range(i):
                A[i, j] = np.nan
        return A
    else:
        # По умолчанию - short_run (Cholesky)
        return None


def fit_svar(
    Y: pd.DataFrame,
    maxlags: int = 2,
    identification_type: str = "short_run",
    var_order: Optional[List[str]] = None,
    **kwargs
) -> Optional[Tuple[SVAR, Dict[str, Any]]]:
    """
    Оценивает SVAR модель на данных.
    
    Args:
        Y: DataFrame с временными рядами (строки = наблюдения, колонки = переменные)
        maxlags: Максимальный порядок лагов для VAR
        identification_type: Тип идентификации структурных шоков
        var_order: Порядок переменных (важен для интерпретации шоков)
        **kwargs: Дополнительные параметры для VAR
    
    Returns:
        Tuple (svar_model, diagnostics) или None при ошибке
    """
    if Y.empty or Y.shape[1] < 2:
        return None
    
    # Удаляем пропуски
    Y_clean = Y.dropna()
    if len(Y_clean) < maxlags + 5:
        return None
    
    try:
        # 1. Оцениваем VAR модель
        var_model = VAR(Y_clean, **kwargs)
        var_result = var_model.fit(maxlags=maxlags, ic='aic')
        
        # Определяем оптимальный порядок лагов
        optimal_lag = var_result.k_ar
        
        # Если оптимальный лаг равен 0, устанавливаем минимум 1 для стабильности
        if optimal_lag == 0:
            optimal_lag = 1
            # Переоцениваем VAR с лагом 1
            var_result = var_model.fit(maxlags=1)
        
        # 2. Для SVAR типа 'A' используем VAR с Cholesky decomposition для IRF
        # Это дает тот же результат, что и SVAR типа 'A', но более стабильно
        n_vars = Y_clean.shape[1]
        
        # Создаем обертку SVARResults для совместимости с остальным кодом
        # Используем VARResults напрямую, так как для Cholesky IRF это эквивалентно SVAR типа 'A'
        class SVARResultsWrapper:
            """Обертка для VARResults, имитирующая SVARResults для Cholesky IRF"""
            def __init__(self, var_result):
                self.model = var_result
                self.var_result = var_result
                self.k_ar = var_result.k_ar
                self.endog_names = var_result.endog_names if hasattr(var_result, 'endog_names') else None
                self._var_result = var_result  # Сохраняем для доступа в методах
            
            def forecast(self, steps, **kwargs):
                # VARResults.forecast() требует последние значения y
                # Используем последние k_ar наблюдений из endog (минимум 1 наблюдение)
                lag_required = max(1, self.k_ar)
                y = self._var_result.endog[-lag_required:]
                return self._var_result.forecast(y=y, steps=steps, **kwargs)
            
            def irf(self, periods=10, orth=True, **kwargs):
                # Используем Cholesky IRF из VARResults
                # irf() возвращает IRFResults объект, orth по умолчанию True для Cholesky
                return self._var_result.irf(periods=periods, **kwargs)
            
            def fevd(self, periods=10, **kwargs):
                # Используем FEVD из VARResults
                return self._var_result.fevd(periods=periods, **kwargs)
        
        svar_result = SVARResultsWrapper(var_result)
        
        # 4. Диагностика
        diagnostics = {
            'n_vars': n_vars,
            'n_obs': len(Y_clean),
            'optimal_lag': optimal_lag,
            'aic': var_result.aic,
            'bic': var_result.bic,
            'identification_type': identification_type,
            'var_order': var_order if var_order else list(Y_clean.columns),
        }
        
        return svar_result, diagnostics
        
    except Exception as e:
        warnings.warn(f"SVAR estimation failed: {e}")
        return None


def forecast_svar(
    svar_result: SVAR,
    steps: int,
    last_values: Optional[pd.Series] = None
) -> Optional[pd.DataFrame]:
    """
    Генерирует прогноз из SVAR модели.
    
    Args:
        svar_result: Оцененная SVAR модель
        steps: Количество шагов прогноза
        last_values: Последние значения для инициализации (опционально)
    
    Returns:
        DataFrame с прогнозом или None при ошибке
    """
    try:
        # SVAR использует базовый VAR для прогноза
        forecast = svar_result.forecast(steps=steps)
        
        # Преобразуем в DataFrame
        if hasattr(svar_result, 'endog_names') and svar_result.endog_names:
            columns = svar_result.endog_names
        elif hasattr(svar_result, 'model'):
            var_result = svar_result.model
            if hasattr(var_result, 'endog_names') and var_result.endog_names:
                columns = var_result.endog_names
            else:
                columns = [f'var_{i}' for i in range(forecast.shape[1])]
        else:
            columns = [f'var_{i}' for i in range(forecast.shape[1])]
        
        forecast_df = pd.DataFrame(forecast, columns=columns)
        return forecast_df
        
    except Exception as e:
        warnings.warn(f"SVAR forecast failed: {e}")
        return None


def compute_irf(
    svar_result: SVAR,
    periods: int = 10,
    orth: bool = True
) -> Optional[pd.DataFrame]:
    """
    Вычисляет импульсные отклики (Impulse Response Functions).
    
    Args:
        svar_result: Оцененная SVAR модель
        periods: Количество периодов для IRF
        orth: Использовать ортогонализированные шоки
    
    Returns:
        DataFrame с IRF или None при ошибке
    """
    try:
        irf = svar_result.irf(periods=periods, orth=orth)
        
        # Преобразуем в DataFrame
        irf_data = {}
        # irf.irfs имеет размерность (periods, n_vars, n_vars)
        # где irfs[t, i, j] - отклик переменной i на шок переменной j в период t
        n_vars = irf.irfs.shape[1]
        
        # Получаем имена переменных
        if hasattr(svar_result, 'model'):
            var_result = svar_result.model
            if hasattr(var_result, 'endog_names'):
                var_names = var_result.endog_names
            else:
                var_names = [f'var_{i}' for i in range(n_vars)]
        else:
            var_names = [f'var_{i}' for i in range(n_vars)]
        
        for i in range(n_vars):
            for j in range(n_vars):
                var_name = var_names[i] if i < len(var_names) else f'var_{i}'
                shock_name = var_names[j] if j < len(var_names) else f'var_{j}'
                key = f"{var_name}_to_{shock_name}"
                irf_data[key] = irf.irfs[:, i, j]
        
        irf_df = pd.DataFrame(irf_data)
        return irf_df
        
    except Exception as e:
        warnings.warn(f"IRF computation failed: {e}")
        return None


def compute_variance_decomposition(
    svar_result: SVAR,
    periods: int = 10
) -> Optional[pd.DataFrame]:
    """
    Вычисляет разложение дисперсии (Variance Decomposition).
    
    Args:
        svar_result: Оцененная SVAR модель
        periods: Количество периодов
    
    Returns:
        DataFrame с разложением дисперсии или None при ошибке
    """
    try:
        vd = svar_result.fevd(periods=periods)
        
        # Преобразуем в DataFrame
        vd_data = {}
        # vd.decomp имеет размерность (n_vars, periods, n_vars)
        # где decomp[i, t, j] - доля дисперсии переменной i, объясняемая шоком переменной j в период t
        decomp_shape = vd.decomp.shape
        n_vars = decomp_shape[0]  # Первая размерность - переменные
        n_periods = decomp_shape[1] if len(decomp_shape) >= 2 else periods  # Вторая размерность - периоды
        
        # Получаем имена переменных
        if hasattr(svar_result, 'endog_names') and svar_result.endog_names:
            var_names = svar_result.endog_names
        elif hasattr(svar_result, 'model'):
            var_result = svar_result.model
            if hasattr(var_result, 'endog_names') and var_result.endog_names:
                var_names = var_result.endog_names
            else:
                var_names = [f'var_{i}' for i in range(n_vars)]
        else:
            var_names = [f'var_{i}' for i in range(n_vars)]
        
        for i in range(n_vars):
            for j in range(n_vars):
                var_name = var_names[i] if i < len(var_names) else f'var_{i}'
                shock_name = var_names[j] if j < len(var_names) else f'var_{j}'
                key = f"{var_name}_from_{shock_name}"
                # Правильная индексация: decomp[i, :, j] - все периоды для переменной i и шока j
                vd_data[key] = vd.decomp[i, :, j]
        
        vd_df = pd.DataFrame(vd_data)
        return vd_df
        
    except Exception as e:
        warnings.warn(f"Variance decomposition failed: {e}")
        return None


def run_svar_block(
    Y: pd.DataFrame,
    factors: List[str],
    forecast_steps: int,
    identification_type: str = "short_run",
    var_order: Optional[List[str]] = None,
    db=None,
    company: str = "",
    block_name: str = "svar_block"
) -> Dict[str, Any]:
    """
    Запускает SVAR модель для блока факторов.
    
    Args:
        Y: DataFrame с данными (строки = годы, колонки = факторы)
        factors: Список факторов для моделирования
        forecast_steps: Количество шагов прогноза
        identification_type: Тип идентификации
        var_order: Порядок переменных (важен для интерпретации)
        db: Объект базы данных для сохранения результатов
        company: Название компании
        block_name: Имя блока
    
    Returns:
        Словарь с результатами: forecasts, diagnostics, irf, variance_decomp
    """
    results = {
        'forecasts': {},
        'diagnostics': {},
        'irf': None,
        'variance_decomp': None,
        'method': 'SVAR'
    }
    
    # Фильтруем данные по факторам
    # factors могут быть без префикса 'ln_', но Y содержит колонки с префиксом
    # Проверяем оба варианта
    available_cols = []
    for f in factors:
        if f in Y.columns:
            available_cols.append(f)
        elif f'ln_{f}' in Y.columns:
            available_cols.append(f'ln_{f}')
    
    if len(available_cols) < 2:
        return results
    
    Y_block = Y[available_cols].copy()
    if Y_block.empty or Y_block.shape[1] < 2:
        return results
    
    # Удаляем пропуски
    Y_clean = Y_block.dropna()
    if len(Y_clean) < 5:
        return results
    
    # Оцениваем SVAR
    svar_result_diagnostics = fit_svar(
        Y_clean,
        maxlags=2,
        identification_type=identification_type,
        var_order=var_order if var_order else list(Y_clean.columns)
    )
    
    if svar_result_diagnostics is None:
        return results
    
    svar_result, diagnostics = svar_result_diagnostics
    results['diagnostics'] = diagnostics
    
    # Генерируем прогноз
    forecast_df = forecast_svar(svar_result, steps=forecast_steps)
    if forecast_df is not None:
        # Преобразуем прогноз в словарь {factor: {year: value}}
        last_year = int(Y_clean.index.max()) if len(Y_clean.index) > 0 else None
        if last_year:
            # Создаем маппинг между именами колонок в прогнозе и исходными факторами
            col_to_factor = {}
            for i, col_name in enumerate(forecast_df.columns):
                # Убираем префикс 'ln_' если есть
                factor_name = col_name.replace('ln_', '') if col_name.startswith('ln_') else col_name
                col_to_factor[col_name] = factor_name
            
            for col_name, factor_name in col_to_factor.items():
                if col_name in forecast_df.columns:
                    factor_forecast = {}
                    for step in range(min(forecast_steps, len(forecast_df))):
                        year = last_year + step + 1
                        value = forecast_df.iloc[step][col_name]
                        if pd.notna(value):
                            factor_forecast[year] = float(value)
                    
                    if factor_forecast:
                        results['forecasts'][factor_name] = factor_forecast
                        
                        # Сохраняем в БД
                        if db:
                            _save_svar_forecast(db, company, factor_name, factor_forecast, 'SVAR')
    
    # Вычисляем IRF
    irf_df = compute_irf(svar_result, periods=10)
    if irf_df is not None:
        results['irf'] = irf_df.to_dict()
    
    # Вычисляем разложение дисперсии
    vd_df = compute_variance_decomposition(svar_result, periods=10)
    if vd_df is not None:
        results['variance_decomp'] = vd_df.to_dict()
    
    return results

