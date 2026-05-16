from pathlib import Path
import pandas as pd, numpy as np, re, io as _io, chardet, sqlite3
def _read_text(p: Path) -> str:
    raw = p.read_bytes(); enc = chardet.detect(raw).get('encoding') or 'utf-8'
    return raw.decode(enc, errors='ignore')
def _guess_delim(text: str) -> str:
    return max([',',';','\t','|'], key=lambda d: text.count(d))
def _guess_decimal(text: str) -> str:
    sample='\n'.join(text.splitlines()[:2000])
    import re
    return ',' if re.findall(r'\d+,\d+', sample) and not re.findall(r'\d+\.\d+', sample) else '.'
def read_one_row_annual(root: Path, company: str, factor: str, file_map: dict, search_paths: list):
    # ПЕРВЫЙ ПРИОРИТЕТ: попытка загрузить из единой централизованной БД
    db_path = root / "data_mart.db"
    if db_path.exists():
        try:
            conn = sqlite3.connect(db_path)
            industry_code = None
            try:
                df_company = pd.read_sql_query(
                    "SELECT industry FROM companies WHERE company_name = ?",
                    conn,
                    params=(company,),
                )
                if not df_company.empty:
                    industry_code = df_company.iloc[0]['industry'] or None
            except Exception:
                industry_code = None
            
            # Сначала пытаемся загрузить ПРОГНОЗЫ из macro_forecasts
            df_db = pd.read_sql_query(
                "SELECT year, value FROM macro_forecasts WHERE factor_name = ? AND company = ? ORDER BY year",
                conn, params=(factor, company)
            )
            
            # Если не найдены прогнозы, пытаемся загрузить историю из macro_factors (глобальные факторы)
            if df_db.empty:
                df_db = pd.read_sql_query(
                    "SELECT year, value FROM macro_factors WHERE factor_name = ? AND (company IS NULL OR company = '') AND scope = 'global' ORDER BY year",
                    conn, params=(factor,)
                )

            # Попробуем отраслевой scope
            if df_db.empty and industry_code:
                df_db = pd.read_sql_query(
                    "SELECT year, value FROM macro_factors WHERE factor_name = ? AND scope = 'industry' AND industry = ? ORDER BY year",
                    conn,
                    params=(factor, industry_code),
                )
            
            # Если не найден глобальный, пытаемся загрузить company-specific историю
            if df_db.empty:
                df_db = pd.read_sql_query(
                    "SELECT year, value FROM macro_factors WHERE factor_name = ? AND company = ? ORDER BY year",
                    conn, params=(factor, company)
                )
            
            conn.close()
            if not df_db.empty:
                out = df_db.set_index('year')['value'].to_dict()
                years = sorted(out.keys())
                return out, (years[-1] if years else None)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Не удалось загрузить макро-фактор {factor} из БД: {e}")
    
    # CSV fallback удален - все макро-факторы должны быть в БД
    # Если данные не найдены в БД, возвращаем пустой словарь
    import logging
    logger = logging.getLogger(__name__)
    if not db_path.exists():
        logger.warning(f"БД не найдена: {db_path}. Макро-фактор {factor} не может быть загружен.")
    else:
        logger.warning(f"Макро-фактор {factor} не найден в БД. CSV fallback удален. Убедитесь, что данные загружены в БД.")
    return {}, None

