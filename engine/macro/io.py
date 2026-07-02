"""Macro data I/O — loads factor history via MacroDBAdapter or Repository."""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Module-level adapter — set by vecm_bridge before calling vecm functions
_adapter = None


def set_adapter(adapter) -> None:
    """Set the module-level MacroDBAdapter for data loading."""
    global _adapter
    _adapter = adapter


def read_one_row_annual(
    root: Path, company: str, factor: str,
    file_map: dict = None, search_paths: list = None,
) -> Tuple[Dict[int, float], Optional[int]]:
    """Load annual time series for a macro factor.

    Uses module-level _adapter if set (preferred), otherwise tries
    data_mart_v2.db via direct SQL as last resort.

    Returns:
        (data_dict, last_year) or ({}, None) if not found.
    """
    # Primary: use adapter (set by vecm_bridge/runner before VECM run)
    if _adapter is not None:
        data = _adapter.get_macro_factor(factor)
        if not data:
            data = _adapter.get_macro_factor_company(factor)
        if data:
            years = sorted(data.keys())
            return data, (years[-1] if years else None)
        logger.debug(f"Factor {factor}: not found via adapter")
        return {}, None

    # Fallback: try data_mart_v2.db directly (for standalone/notebook usage)
    import sqlite3
    db_path = root / "data_mart_v2.db"
    if not db_path.exists():
        logger.warning(f"No adapter and no DB at {db_path} — cannot load {factor}")
        return {}, None

    try:
        conn = sqlite3.connect(str(db_path))
        import pandas as pd
        df = pd.read_sql_query(
            "SELECT year, value FROM macro_factors WHERE factor_name = ? "
            "AND scope = 'global' ORDER BY year",
            conn, params=(factor,)
        )
        if df.empty:
            df = pd.read_sql_query(
                "SELECT year, value FROM macro_factors WHERE factor_name = ? "
                "AND company_id = ? ORDER BY year",
                conn, params=(factor, company)
            )
        conn.close()
        if not df.empty:
            out = df.set_index('year')['value'].to_dict()
            years = sorted(out.keys())
            return out, (years[-1] if years else None)
    except Exception as e:
        logger.warning(f"DB fallback failed for {factor}: {e}")

    return {}, None
