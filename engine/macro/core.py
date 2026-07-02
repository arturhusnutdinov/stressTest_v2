
import numpy as np, pandas as pd, yaml, os, re
from pathlib import Path
from .vecm import run_vecm_all as _run_vecm_all
from .svar import run_svar_block
from typing import Dict

# Импорт БД модуля для сохранения результатов
try:
    from engine.database.data_mart import get_data_mart
    DM_AVAILABLE = True
except ImportError:
    get_data_mart = None
    DM_AVAILABLE = False

def _read_yaml(p: Path):
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}

def _resolve_macro_paths(root: Path, company: str):
    croot = root/"companies"/company
    proj = _read_yaml(croot/"configs"/"project.yaml")
    industry = proj.get("industry","")
    paths = proj.get("macro_forecast",{}).get("search_paths",[
        "companies/{company}/drivers",
        "companies/{company}/data/macro",
        "macro/industry/{industry}/drivers",
        "macro/global/drivers"
    ])
    resolved = []
    for p in paths:
        p = p.replace("{company}", company).replace("{industry}", industry)
        resolved.append(root/p)
    return resolved

def _file_map(root: Path, company: str):
    croot = root/"companies"/company
    proj = _read_yaml(croot/"configs"/"project.yaml")
    return proj.get("macro_forecast",{}).get("file_map",{})

def _factors(root: Path, company: str):
    croot = root/"companies"/company
    proj = _read_yaml(croot/"configs"/"project.yaml")
    return proj.get("macro_forecast",{}).get("factors", [])

def _find_driver_csv(root: Path, company: str, factor: str):
    fmap = _file_map(root, company)
    preferred = fmap.get(factor, f"{factor}.csv")
    for d in _resolve_macro_paths(root, company):
        p = d/preferred
        if p.exists():
            return p
    for d in _resolve_macro_paths(root, company):
        p = d/f"{factor}.csv"
        if p.exists():
            return p
    return None

def _read_driver_one_row(p: Path):
    # Expect one row: metric + year columns
    df = pd.read_csv(p)
    years = [c for c in df.columns if re.fullmatch(r"\d{4}", str(c))]
    if len(df) >= 1:
        row = df.iloc[0].to_dict()
    else:
        row = {"metric": p.stem}
    return row, [int(y) for y in years]

def ensure_outputs_even_if_insufficient_history_2005(root: Path, company: str):
    croot = root/"companies"/company
    proj = _read_yaml(croot/"configs"/"project.yaml")
    mf = proj.get("macro_forecast", {})
    periods_cfg = (
        proj.get("model", {})
        .get("standard", {})
        .get("periods", proj.get("model", {}).get("periods", {}))
        or {}
    )
    history_end_year_cfg = periods_cfg.get("history_end_year")
    start_req = int(mf.get("start_year_required", 2005))
    min_years = int(mf.get("require_min_history_years", 20))
    factors = _factors(root, company)

    mart = None
    if DM_AVAILABLE:
        try:
            mart = get_data_mart(root, company)
        except Exception:
            mart = None

    summary_rows = []
    for f in factors:
        # Загрузка из DataMart (основной источник)
        history_data = {}
        y0 = None
        y1 = None
        
        if mart is not None:
            try:
                # Пытаемся загрузить из DataMart
                history_data = mart.get_macro_factor(f) or {}
                if history_data:
                    years = sorted(history_data.keys())
                    y0 = min(years) if years else None
                    y1 = max(years) if years else None
            except Exception:
                history_data = {}
        
        # Если не найдено в DataMart, пытаемся CSV fallback (legacy)
        if not history_data:
            p = _find_driver_csv(root, company, f)
            try:
                src = str(p.relative_to(croot)) if p else ""
            except Exception:
                src = os.path.relpath(str(p), str(croot)) if p else ""

            if p and p.exists():
                row, years = _read_driver_one_row(p)
                y0 = min(years) if years else None
                y1 = max(years) if years else None
                # Конвертируем CSV данные в формат {year: value}
                for year in years:
                    value = row.get(str(year))
                    try:
                        numeric = float(value)
                        if numeric is not None and numeric > 0:
                            history_data[year] = numeric
                    except Exception:
                        pass
            else:
                src = "DataMart (not found)"
        else:
            src = "DataMart"

        span_ok = (y0 is not None) and (y0 <= start_req) and (len(history_data) >= min_years)

        history_ln: Dict[int, float] = {}
        for year, value in history_data.items():
            try:
                numeric = float(value)
                if numeric is not None and numeric > 0:
                    history_ln[year] = float(np.log(numeric))
            except Exception:
                pass

        forecast_ln: Dict[int, float] = {}
        if y1 and y1 in history_data:
            base_val = history_data.get(y1)
            try:
                base_val = float(base_val)
                if base_val is not None and base_val > 0:
                    for i in range(1, 6):
                        forecast_ln[y1 + i] = float(np.log(base_val))
            except Exception:
                pass

        series_ln = {**history_ln, **forecast_ln}
        method = "ECM_OR_PASSTHROUGH_LN" if span_ok else "DRIFT_LN"
        note = "" if span_ok else "insufficient_span"

        # Сохраняем только прогнозный хвост (годы > истории)
        if mart is not None:
            history_cutoff = history_end_year_cfg or y1
            forecast_only = {
                year: value for year, value in forecast_ln.items() if value is not None
            }
            if history_cutoff is not None:
                forecast_only = {
                    year: value
                    for year, value in forecast_only.items()
                    if year > int(history_cutoff)
                }
            if forecast_only:
                mart.save_macro_forecast(f, forecast_only, method=method)
        if mart is not None:
            mart.save_ecm_diagnostics(company, f, method, "fallback", None, None, y0, y1, None, note, None)

        summary_rows.append({
            "factor": f,
            "method": method,
            "span_ok": span_ok,
            "span_start": y0,
            "span_end": y1,
            "source": src
        })

    if mart is not None:
        mart.close()

    return pd.DataFrame(summary_rows)

def run_ecm_all(root: Path, company: str):
    """
    Запуск ECM/VECM/SVAR прогнозирования для компании
    
    Сначала запускает VECM/SVAR с конфигурацией из macro_ecm.yaml,
    затем fallback на ensure_outputs_even_if_insufficient_history_2005.
    """
    # Сначала пытаемся запустить полноценный VECM/SVAR
    try:
        # Ищем конфиг macro_ecm.yaml
        # Сначала проверяем в project.yaml компании
        proj = _read_yaml(root/f'companies/{company}/configs/project.yaml')
        mf_cfg = proj.get('macro_forecast', {}).get('config')
        
        cfg_path = None
        if mf_cfg:
            # Используем путь из project.yaml
            cfg_path = root / mf_cfg
            if not cfg_path.exists():
                cfg_path = None
        
        # Если не нашли - используем кандидатов
        if cfg_path is None:
            cfg_candidates = [
                root / f'companies/{company}/configs/forecast/macro_ecm.yaml',
                root / f'companies/{company}/configs/macro_ecm.yaml',
            ]
            for candidate in cfg_candidates:
                if candidate.exists():
                    cfg_path = candidate
                    break
        
        if cfg_path:
            cfg = _read_yaml(cfg_path)
            
            # Проверяем, используется ли SVAR
            use_svar = cfg.get('svar', {}).get('enabled', False)
            
            if use_svar:
                # Запускаем SVAR
                run_svar_all(root, company, cfg_path)
            else:
                # Запускаем VECM
                _run_vecm_all(root, company, cfg_path)
            return
    except Exception as e:
        print(f"⚠️ ECM/VECM/SVAR не удалось запустить: {e}, используем fallback")
    
    # Fallback на базовый метод
    ensure_outputs_even_if_insufficient_history_2005(root, company)


def run_svar_all(root: Path, company: str, cfg_path: Path):
    """
    Запуск SVAR прогнозирования для компании.
    
    Args:
        root: Корень проекта
        company: Название компании
        cfg_path: Путь к конфигурационному файлу macro_ecm.yaml
    """
    cfg = _read_yaml(cfg_path)
    svar_cfg = cfg.get('svar', {})
    
    # Параметры из конфига
    identification_type = svar_cfg.get('identification_type', 'short_run')
    maxlags = int(svar_cfg.get('maxlags', 2))
    forecast_years = int(cfg.get('horizon_years', 5))
    
    # Загружаем факторы из project.yaml
    proj = _read_yaml(root / f'companies/{company}/configs/project.yaml')
    factors = proj.get('macro_forecast', {}).get('factors', [])
    file_map = proj.get('macro_forecast', {}).get('file_map', {})
    search_paths = proj.get('macro_forecast', {}).get('search_paths', [])
    
    # Загружаем историю факторов (используем логику из vecm.py)
    from .vecm import _stack_block_ln
    Y_all = _stack_block_ln(
        root, company, factors, file_map, search_paths, cleaned_overrides=None
    )
    
    if Y_all.empty:
        print("⚠️ SVAR: Нет данных для моделирования, используем fallback")
        ensure_outputs_even_if_insufficient_history_2005(root, company)
        return
    
    # Инициализация БД
    db = None
    if DM_AVAILABLE:
        try:
            db = get_data_mart(root, company)
        except Exception:
            db = None
    
    # Определяем блоки для SVAR
    svar_blocks = svar_cfg.get('blocks', [])
    if not svar_blocks:
        # Если блоки не указаны, используем все факторы как один блок
        svar_blocks = [{'name': 'all_factors', 'factors': factors}]
    
    # Запускаем SVAR для каждого блока
    for block_cfg in svar_blocks:
        block_name = block_cfg.get('name', 'svar_block')
        block_factors = block_cfg.get('factors', factors)
        var_order = block_cfg.get('var_order', None)  # Порядок переменных для идентификации
        
        # Фильтруем данные по факторам блока
        block_cols = [f'ln_{f}' for f in block_factors if f'ln_{f}' in Y_all.columns]
        if len(block_cols) < 2:
            print(f"⚠️ SVAR блок {block_name}: недостаточно факторов ({len(block_cols)})")
            continue
        
        Y_block = Y_all[block_cols].copy()
        
        # Запускаем SVAR
        results = run_svar_block(
            Y=Y_block,
            factors=[f.replace('ln_', '') for f in block_cols],
            forecast_steps=forecast_years,
            identification_type=identification_type,
            var_order=var_order,
            db=db,
            company=company,
            block_name=block_name
        )
        
        print(f"✅ SVAR блок {block_name}: прогноз сгенерирован для {len(results.get('forecasts', {}))} факторов")
    
    if db:
        db.close()
 
# Backward-compatible alias used by orchestrator
ensure_outputs_even_if_insufficient_history = ensure_outputs_even_if_insufficient_history_2005