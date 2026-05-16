from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

try:
    from engine.database.data_mart import get_data_mart
except ImportError:
    get_data_mart = None

EPS = 1e-9


@dataclass
class PreprocessConfig:
    enabled: bool = True
    history_window: int = 3
    z_threshold: float = 2.5
    dummy_z_threshold: float = 3.0
    large_delta_threshold: float = 0.25
    detect_recent_years: int = 2
    normalize_enabled: bool = True
    normalize_scale: float = 1e12
    smoothing_method: str = "winsorize"
    smoothing_limit: float = 0.2
    max_backfill_yoy: int = 1
    detect_cycle_enabled: bool = False
    detect_cycle_max_period: int = 8
    detect_cycle_acf_threshold: float = 0.3
    detect_cycle_fft_threshold: float = 0.25

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "PreprocessConfig":
        if not data:
            return cls()
        cfg = dict(data)
        smoothing = cfg.pop("smoothing", {})
        normalize = cfg.pop("normalize", {})
        if isinstance(smoothing, dict):
            cfg.setdefault("smoothing_method", smoothing.get("method", "winsorize"))
            cfg.setdefault("smoothing_limit", float(smoothing.get("limit", 0.2)))
        if isinstance(normalize, dict):
            cfg.setdefault("normalize_enabled", normalize.get("enabled", True))
            cfg.setdefault("normalize_scale", float(normalize.get("scale", 1e12)))
        detect_cycle = cfg.pop("detect_cycle", {})
        if isinstance(detect_cycle, dict):
            cfg.setdefault("detect_cycle_enabled", detect_cycle.get("enabled", False))
            cfg.setdefault("detect_cycle_max_period", int(detect_cycle.get("max_period", 8)))
            cfg.setdefault("detect_cycle_acf_threshold", float(detect_cycle.get("acf_threshold", 0.3)))
            cfg.setdefault("detect_cycle_fft_threshold", float(detect_cycle.get("fft_threshold", 0.25)))
        return cls(**cfg)


@dataclass
class FactorAnomaly:
    factor_name: str
    year: int
    delta: float
    z_score: float
    reasons: List[str] = field(default_factory=list)
    suggested_dummy: bool = False
    value: Optional[float] = None
    ln_value: Optional[float] = None

    def to_record(self) -> dict:
        return {
            "factor_name": self.factor_name,
            "year": int(self.year),
            "delta": float(self.delta) if self.delta is not None else None,
            "z_score": float(self.z_score) if self.z_score is not None else None,
            "reasons": ",".join(self.reasons),
            "suggested_dummy": int(self.suggested_dummy),
            "value": float(self.value) if self.value is not None else None,
            "ln_value": float(self.ln_value) if self.ln_value is not None else None,
        }


@dataclass
class FactorMetrics:
    max_abs_delta: float = 0.0
    max_abs_z: float = 0.0
    outlier_years: List[int] = field(default_factory=list)
    normalization_factor: float = 1.0
    smoothing_applied: Optional[str] = None
    anomaly_share: float = 0.0
    details: dict = field(default_factory=dict)
    cyclical: bool = False
    detected_period: Optional[int] = None

    def to_record(self, factor_name: str) -> dict:
        return {
            "factor_name": factor_name,
            "max_abs_delta": float(self.max_abs_delta),
            "max_abs_z": float(self.max_abs_z),
            "outlier_years": json.dumps(self.outlier_years, ensure_ascii=False),
            "normalization_factor": float(self.normalization_factor),
            "smoothing_applied": self.smoothing_applied,
            "anomaly_share": float(self.anomaly_share),
            "details": json.dumps(self.details, ensure_ascii=False),
            "cyclical": int(self.cyclical),
            "detected_period": self.detected_period,
        }


@dataclass
class PreprocessResult:
    ln_series: Dict[str, Dict[int, float]] = field(default_factory=dict)
    original_levels: Dict[str, Dict[int, float]] = field(default_factory=dict)
    anomalies: List[FactorAnomaly] = field(default_factory=list)
    metrics: Dict[str, FactorMetrics] = field(default_factory=dict)
    auto_shock_candidates: List[Tuple[int, float]] = field(default_factory=list)
    normalization_applied: Dict[str, float] = field(default_factory=dict)


def _series_from_dict(data: Dict[int, float]) -> pd.Series:
    if not data:
        return pd.Series(dtype=float)
    idx = sorted(int(k) for k in data.keys())
    return pd.Series({int(year): float(data.get(year)) for year in idx}, dtype=float).sort_index()


def _normalize_levels(values: pd.Series, scale: float) -> Tuple[pd.Series, float]:
    if values.empty:
        return values, 1.0
    abs_max = float(np.nanmax(np.abs(values.values)))
    if abs_max < scale or scale <= 0:
        return values, 1.0
    factor = scale
    normalized = values / factor
    return normalized, factor


def _detect_cycle_period(
    dln: pd.Series,
    max_period: int,
    acf_threshold: float,
    fft_threshold: float,
) -> Optional[int]:
    y = dln.dropna()
    if y.empty or max_period < 2 or len(y) < max_period * 2:
        return None

    best_lag = None
    best_score = 0.0
    for lag in range(2, max_period + 1):
        corr = y.autocorr(lag=lag)
        if corr is None or np.isnan(corr):
            continue
        score = abs(float(corr))
        if score >= acf_threshold and score > best_score:
            best_lag = lag
            best_score = score

    if best_lag is not None:
        return int(best_lag)

    values = y.values.astype(float)
    values = values - values.mean()
    if np.allclose(values, 0.0):
        return None
    fft = np.fft.rfft(values)
    power = np.abs(fft)
    if len(power) <= 1:
        return None
    power[0] = 0
    total_power = np.sum(power)
    if total_power <= 0:
        return None
    idx = int(np.argmax(power))
    if idx <= 0:
        return None
    freqs = np.fft.rfftfreq(len(values), d=1.0)
    freq = freqs[idx]
    if freq <= 0:
        return None
    period = int(round(1.0 / freq))
    if period < 2 or period > max_period:
        return None
    if power[idx] / total_power < fft_threshold:
        return None
    return period


def preprocess_macro_history(
    root: Path,
    company: str,
    factors: Sequence[str],
    config: Optional[dict],
    history_end_year: Optional[int] = None,
) -> PreprocessResult:
    cfg = PreprocessConfig.from_dict(config)
    if not cfg.enabled:
        return PreprocessResult()

    root_path = Path(root)
    result = PreprocessResult()

    unique_factors: List[str] = []
    for factor in factors:
        if factor and factor not in unique_factors:
            unique_factors.append(str(factor))

    with get_data_mart(root_path, company) as mart:
        for factor in unique_factors:
            history = mart.get_macro_factor(factor)
            if not history:
                continue

            series_levels = _series_from_dict(history).dropna()
            if series_levels.empty:
                continue

            series_original = series_levels.copy()
            normalization_factor = 1.0
            if cfg.normalize_enabled:
                series_levels, normalization_factor = _normalize_levels(series_levels, cfg.normalize_scale)

            # Ensure positivity for log transform
            positive_values = np.maximum(series_levels.values, EPS)
            ln_series = pd.Series(np.log(positive_values), index=series_levels.index)
            ln_series = ln_series.sort_index()

            dln = ln_series.diff()
            if dln.dropna().empty:
                # Not enough data for differencing
                clean_ln = ln_series.copy()
                result.ln_series[factor] = {int(y): float(v) for y, v in clean_ln.items() if pd.notna(v)}
                result.original_levels[factor] = {int(y): float(v) for y, v in series_original.items() if pd.notna(v)}
                metrics = FactorMetrics(normalization_factor=float(normalization_factor))
                metrics.details["cycle_detection"] = {
                    "enabled": cfg.detect_cycle_enabled,
                    "detected_period": None,
                    "method": "insufficient_history",
                }
                result.metrics[factor] = metrics
                continue

            window = max(2, int(cfg.history_window))
            rolling_mean = dln.rolling(window=window, center=True, min_periods=1).mean()
            rolling_std = dln.rolling(window=window, center=True, min_periods=1).std(ddof=0)

            global_std = float(dln.std(ddof=0))
            if global_std <= 0 or np.isnan(global_std):
                global_std = float(np.nanstd(dln.values))
            if global_std <= 0 or np.isnan(global_std):
                global_std = 1e-6

            rolling_std = rolling_std.replace(0, np.nan)
            z_scores = (dln - rolling_mean) / rolling_std
            z_scores = z_scores.fillna(dln / global_std)

            anomalies: List[FactorAnomaly] = []
            outlier_years: List[int] = []

            for year, z_val in z_scores.dropna().items():
                delta_val = float(dln.loc[year]) if year in dln.index else np.nan
                reasons: List[str] = []
                abs_z = abs(float(z_val))
                abs_delta = abs(delta_val) if not np.isnan(delta_val) else 0.0

                if abs_z >= cfg.z_threshold:
                    reasons.append("z_score")
                if cfg.large_delta_threshold and abs_delta >= cfg.large_delta_threshold:
                    reasons.append("large_jump")
                if (
                    history_end_year
                    and cfg.detect_recent_years > 0
                    and year >= history_end_year - cfg.detect_recent_years + 1
                ):
                    if abs_z >= cfg.z_threshold:
                        reasons.append("recent_spike")

                if not reasons:
                    continue

                suggested_dummy = abs_z >= cfg.dummy_z_threshold or "large_jump" in reasons

                anomaly = FactorAnomaly(
                    factor_name=factor,
                    year=int(year),
                    delta=float(delta_val) if not np.isnan(delta_val) else 0.0,
                    z_score=float(z_val),
                    reasons=reasons,
                    suggested_dummy=suggested_dummy,
                    value=float(series_levels.get(year, np.nan)),
                    ln_value=float(ln_series.get(year, np.nan)),
                )
                anomalies.append(anomaly)
                outlier_years.append(int(year))

            # Smoothing / winsorization
            clean_ln = ln_series.copy()
            smoothing_applied = None
            if cfg.smoothing_method.lower() == "winsorize" and cfg.smoothing_limit > 0:
                limit = float(cfg.smoothing_limit)
                clipped_dln = dln.clip(lower=-limit, upper=limit)
                adjusted = ln_series.iloc[0] + clipped_dln.fillna(0).cumsum()
                clean_ln.update(adjusted)
                smoothing_applied = f"winsorize({limit})"

            cyclical_flag = False
            detected_period: Optional[int] = None
            if cfg.detect_cycle_enabled:
                detected_period = _detect_cycle_period(
                    dln,
                    max_period=cfg.detect_cycle_max_period,
                    acf_threshold=cfg.detect_cycle_acf_threshold,
                    fft_threshold=cfg.detect_cycle_fft_threshold,
                )
                cyclical_flag = detected_period is not None

            metrics = FactorMetrics(
                max_abs_delta=float(np.nanmax(np.abs(dln.values))) if len(dln) else 0.0,
                max_abs_z=float(np.nanmax(np.abs(z_scores.values))) if len(z_scores) else 0.0,
                outlier_years=sorted(set(outlier_years)),
                normalization_factor=float(normalization_factor),
                smoothing_applied=smoothing_applied,
                cyclical=cyclical_flag,
                detected_period=int(detected_period) if detected_period is not None else None,
            )
            total_points = len(dln.dropna())
            metrics.anomaly_share = float(len(outlier_years) / total_points) if total_points else 0.0
            metrics.details = {
                "std_global": global_std,
                "window": window,
                "anomalies": [a.to_record() for a in anomalies],
                "cycle_detection": {
                    "enabled": cfg.detect_cycle_enabled,
                    "detected_period": detected_period,
                    "acf_threshold": cfg.detect_cycle_acf_threshold,
                    "fft_threshold": cfg.detect_cycle_fft_threshold,
                },
            }

            result.metrics[factor] = metrics
            result.ln_series[factor] = {
                int(year): float(value)
                for year, value in clean_ln.items()
                if pd.notna(value)
            }
            result.original_levels[factor] = {
                int(year): float(value)
                for year, value in series_original.items()
                if pd.notna(value)
            }
            result.normalization_applied[factor] = float(normalization_factor)
            result.anomalies.extend(anomalies)

            for anomaly in anomalies:
                if anomaly.suggested_dummy:
                    score = abs(anomaly.z_score)
                    result.auto_shock_candidates.append((anomaly.year, score))

    # Deduplicate auto shock candidates (keep max z per year)
    if result.auto_shock_candidates:
        by_year: Dict[int, float] = {}
        for year, score in result.auto_shock_candidates:
            by_year[year] = max(score, by_year.get(year, 0.0))
        result.auto_shock_candidates = sorted(by_year.items(), key=lambda item: (-item[1], -item[0]))

    return result

