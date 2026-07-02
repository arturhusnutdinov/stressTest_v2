#!/usr/bin/env python3
"""Единый загрузчик данных из *_unified.xlsx в data_mart_v2.db.

Один скрипт загружает ВСЕ листы — history (IS/BS/CF), schedule-расписания,
долговые инструменты, макро-факторы, сегменты, операционные драйверы.

Usage:
    python3 tools/load_unified_excel.py --company rusal
    python3 tools/load_unified_excel.py --company nornickel --dry-run
    python3 tools/load_unified_excel.py --company us_steel --excel companies/us_steel/data/excel/us_steel_input.xlsx
"""
from __future__ import annotations
import argparse, sqlite3, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = str(ROOT / 'data_mart_v2.db')


def _find_excel(company_id: str) -> Path:
    """Auto-detect unified Excel for company."""
    patterns = [
        ROOT / f'companies/{company_id}/data/excel/{company_id}_unified.xlsx',
        ROOT / f'companies/{company_id}/data/excel/{company_id}_input.xlsx',
        ROOT / f'companies/{company_id}/data/{company_id}_unified.xlsx',
    ]
    for p in patterns:
        if p.exists():
            return p
    return patterns[0]


class UnifiedExcelLoader:
    """Загружает все листы из unified Excel в SQLite."""

    def __init__(self, company_id: str, db_path: str, dry_run: bool = False):
        self.company_id = company_id
        self.db_path = db_path
        self.dry_run = dry_run
        self.conn: sqlite3.Connection | None = None
        self.period_map: dict[int, int] = {}
        self.stats: dict[str, int] = {}

    def load(self, excel_path: Path) -> dict[str, int]:
        """Main entry point. Returns {sheet_name: rows_loaded}."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA foreign_keys = ON")

        # Ensure company exists
        self._ensure_company()

        xl = pd.ExcelFile(excel_path)
        available = set(xl.sheet_names)

        print(f'UnifiedExcelLoader {"[DRY RUN]" if self.dry_run else "[LIVE]"}')
        print(f'  Company: {self.company_id}')
        print(f'  Excel:   {excel_path.name} ({len(available)} sheets)')
        print(f'  DB:      {self.db_path}')
        print()

        # ── Phase 1: History (IS/BS/CF) — creates periods ────────
        for stmt, sheet in [('IS', 'history_is'), ('BS', 'history_bs'), ('CF', 'history_cf')]:
            if sheet in available:
                df = pd.read_excel(excel_path, sheet_name=sheet)
                self._load_history(stmt, df, sheet)

        # Rebuild period map after history loaded
        self.period_map = self._get_period_map()

        # ── Phase 2: Segments ────────────────────────────────────
        for sheet in ['segments', 'segments_financial', 'segments_operational']:
            if sheet in available:
                df = pd.read_excel(excel_path, sheet_name=sheet)
                self._load_segments(df, sheet)

        # ── Phase 3: Debt instruments ────────────────────────────
        if 'debt_instruments' in available:
            df = pd.read_excel(excel_path, sheet_name='debt_instruments')
            self._load_debt_instruments(df)

        if 'debt_cashflows' in available:
            df = pd.read_excel(excel_path, sheet_name='debt_cashflows')
            self._load_debt_cashflows(df)

        # ── Phase 4: PPE components ──────────────────────────────
        for sheet in ['ppe_components', 'schedule_ppe']:
            if sheet in available:
                df = pd.read_excel(excel_path, sheet_name=sheet)
                self._load_ppe(df, sheet)

        # ── Phase 5: Macro factors ───────────────────────────────
        if 'macro_factors' in available:
            df = pd.read_excel(excel_path, sheet_name='macro_factors')
            self._load_macro(df)

        # ── Phase 6: Operational drivers ─────────────────────────
        if 'operational_drivers' in available:
            df = pd.read_excel(excel_path, sheet_name='operational_drivers')
            self._load_operational(df)

        # ── Phase 7: Schedule sheets (delegated) ─────────────────
        from load_schedule_sheets import PERIOD_HANDLERS
        for sheet in available:
            if sheet in PERIOD_HANDLERS and sheet not in self.stats:
                df = pd.read_excel(excel_path, sheet_name=sheet)
                df = df.dropna(how='all')
                if df.empty:
                    continue
                n = PERIOD_HANDLERS[sheet](
                    self.conn, df, self.company_id, self.period_map, self.dry_run)
                self.stats[sheet] = n
                self._print_stat(sheet, n)

        # ── Phase 8: Balancing adjustments ───────────────────────
        if 'balancing_adjustments' in available:
            df = pd.read_excel(excel_path, sheet_name='balancing_adjustments')
            self._load_balancing(df)

        if not self.dry_run:
            self.conn.commit()
        self.conn.close()

        print(f'\n{"─" * 50}')
        total = sum(self.stats.values())
        print(f'Total: {total} rows across {len(self.stats)} sheets')
        return self.stats

    # ── Internals ───────────────────────────────────────────────────────

    def _ensure_company(self):
        """Create company record if not exists."""
        existing = self.conn.execute(
            "SELECT company_id FROM companies WHERE company_id=?",
            (self.company_id,)).fetchone()
        if not existing and not self.dry_run:
            self.conn.execute(
                "INSERT INTO companies (company_id, name, currency) VALUES (?,?,?)",
                (self.company_id, self.company_id.replace('_', ' ').title(), 'USD'))

    def _get_period_map(self) -> dict[int, int]:
        return {yr: pid for pid, yr in self.conn.execute(
            "SELECT period_id, year FROM periods WHERE company_id=?",
            (self.company_id,))}

    def _ensure_period(self, year: int, is_forecast: int = 0) -> int:
        """Get or create period_id for year."""
        if year in self.period_map:
            return self.period_map[year]
        if self.dry_run:
            return -1
        self.conn.execute(
            "INSERT OR IGNORE INTO periods (company_id, year, is_annual, is_forecast) "
            "VALUES (?,?,1,?)", (self.company_id, year, is_forecast))
        pid = self.conn.execute(
            "SELECT period_id FROM periods WHERE company_id=? AND year=?",
            (self.company_id, year)).fetchone()[0]
        self.period_map[year] = pid
        return pid

    def _detect_year_columns(self, df: pd.DataFrame) -> list[int]:
        """Find year columns (2000-2040 range)."""
        years = []
        for c in df.columns:
            try:
                y = int(c)
                if 2000 <= y <= 2040:
                    years.append(y)
            except (ValueError, TypeError):
                pass
        return sorted(years)

    def _print_stat(self, name: str, n: int):
        action = "would load" if self.dry_run else "loaded"
        if n > 0:
            print(f'  ✓ {name}: {n} rows {action}')
        else:
            print(f'  · {name}: 0 rows')

    # ── History (wide format: metric | 2011 | 2012 | ...) ──────────────

    def _load_history(self, statement: str, df: pd.DataFrame, sheet: str):
        """Load IS/BS/CF from wide format."""
        table = f'history_{statement.lower()}'
        year_cols = self._detect_year_columns(df)
        metric_col = df.columns[0]  # First column is metric name

        n = 0
        for _, row in df.iterrows():
            metric = str(row[metric_col]).strip()
            if not metric or metric == 'nan':
                continue
            for yr in year_cols:
                val = row.get(yr)
                if pd.isna(val) or val is None:
                    continue
                pid = self._ensure_period(yr)
                if pid == -1:
                    continue
                # Values in Excel are mUSD → convert to USD
                val_usd = float(val) * 1e6
                if not self.dry_run:
                    self.conn.execute(
                        f"INSERT OR REPLACE INTO {table} "
                        "(company_id, period_id, metric, value, source, updated_at) "
                        "VALUES (?,?,?,?,'unified_excel',datetime('now'))",
                        (self.company_id, pid, metric, val_usd))
                n += 1
        self.stats[sheet] = n
        self._print_stat(sheet, n)

    # ── Segments (wide: segment_name | metric | 2011 | 2012 | ...) ─────

    def _load_segments(self, df: pd.DataFrame, sheet: str):
        """Load segment data from wide format."""
        year_cols = self._detect_year_columns(df)
        cols = [str(c).lower() for c in df.columns]

        # Detect column names
        seg_col = df.columns[0]  # segment / segment_name
        met_col = df.columns[1]  # metric

        n = 0
        for _, row in df.iterrows():
            seg_name = str(row[seg_col]).strip()
            metric = str(row[met_col]).strip()
            if not seg_name or seg_name == 'nan' or not metric or metric == 'nan':
                continue
            seg_id = seg_name.lower().replace(' ', '_')
            for yr in year_cols:
                val = row.get(yr)
                if pd.isna(val) or val is None:
                    continue
                pid = self._ensure_period(yr)
                if pid == -1:
                    continue
                if not self.dry_run:
                    self.conn.execute(
                        "INSERT OR REPLACE INTO segment_data "
                        "(company_id, period_id, segment_id, segment_name, metric, "
                        "value, source, updated_at) "
                        "VALUES (?,?,?,?,?,?,'unified_excel',datetime('now'))",
                        (self.company_id, pid, seg_id, seg_name, metric, float(val)))
                n += 1
        self.stats[sheet] = n
        self._print_stat(sheet, n)

    # ── Debt instruments ───────────────────────────────────────────────

    def _load_debt_instruments(self, df: pd.DataFrame):
        """Load debt instruments from tabular format."""
        n = 0
        for _, row in df.iterrows():
            iid = str(row.get('instrument_id', '')).strip()
            if not iid or iid == 'nan':
                continue
            name = row.get('instrument_name', iid)
            ob = row.get('opening_balance_mUSD', row.get('opening_balance'))
            ca = row.get('committed_amount_mUSD', row.get('committed_amount'))

            if not self.dry_run:
                self.conn.execute(
                    "INSERT OR REPLACE INTO debt_instruments "
                    "(instrument_id, company_id, instrument_name, db_type, currency, "
                    "opening_balance, committed_amount, maturity_date, interest_rate, "
                    "rate_type, base_rate_factor, payment_frequency, amortization_profile, "
                    "callable_flag, covenant_package, source, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'unified_excel',datetime('now'))",
                    (iid, self.company_id,
                     str(name) if pd.notna(name) else iid,
                     str(row.get('db_type', row.get('instrument_type', 'other'))),
                     str(row.get('currency', 'USD')),
                     float(ob) * 1e6 if pd.notna(ob) else 0,
                     float(ca) * 1e6 if pd.notna(ca) else None,
                     str(row.get('maturity_date', '')) if pd.notna(row.get('maturity_date')) else None,
                     float(row.get('interest_rate', 0)) if pd.notna(row.get('interest_rate')) else None,
                     str(row.get('rate_type', 'fixed')),
                     str(row.get('base_rate_factor', '')) if pd.notna(row.get('base_rate_factor')) else None,
                     str(row.get('payment_frequency', 'semi_annual')),
                     str(row.get('amortization_profile', 'bullet')),
                     int(row.get('callable_flag', 0)) if pd.notna(row.get('callable_flag')) else 0,
                     str(row.get('covenant_package', '')) if pd.notna(row.get('covenant_package')) else None))
            n += 1
        self.stats['debt_instruments'] = n
        self._print_stat('debt_instruments', n)

    # ── Debt cashflows ─────────────────────────────────────────────────

    def _load_debt_cashflows(self, df: pd.DataFrame):
        """Load debt cashflow schedule."""
        n = 0
        for _, row in df.iterrows():
            iid = str(row.get('instrument_id', '')).strip()
            yr = row.get('year')
            cft = str(row.get('cashflow_type', '')).strip()
            amt = row.get('amount_mUSD', row.get('amount'))
            if not iid or iid == 'nan' or pd.isna(yr) or not cft or pd.isna(amt):
                continue
            if not self.dry_run:
                self.conn.execute(
                    "INSERT OR REPLACE INTO debt_cashflows "
                    "(company_id, instrument_id, year, period, cashflow_type, "
                    "amount, currency, note, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,datetime('now'))",
                    (self.company_id, iid, int(yr),
                     str(row.get('period', '')) if pd.notna(row.get('period')) else None,
                     cft, float(amt) * 1e6,
                     str(row.get('currency', 'USD')),
                     str(row.get('note', '')) if pd.notna(row.get('note')) else None))
            n += 1
        self.stats['debt_cashflows'] = n
        self._print_stat('debt_cashflows', n)

    # ── PPE components ─────────────────────────────────────────────────

    def _load_ppe(self, df: pd.DataFrame, sheet: str):
        """Load PPE component detail."""
        n = 0
        for _, row in df.iterrows():
            yr = row.get('year')
            if pd.isna(yr):
                continue
            pid = self._ensure_period(int(yr))
            if pid == -1:
                continue
            cid = str(row.get('component_id', row.get('category', ''))).strip()
            if not cid or cid == 'nan':
                continue
            vtype = str(row.get('value_type', row.get('movement', 'net'))).strip()
            val = row.get('value_mUSD', row.get('value'))
            if pd.isna(val):
                continue
            if not self.dry_run:
                self.conn.execute(
                    "INSERT OR REPLACE INTO ppe_components "
                    "(company_id, period_id, component_id, component_name, value_type, "
                    "value, useful_life, source, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,'unified_excel',datetime('now'))",
                    (self.company_id, pid, cid,
                     str(row.get('component_name', cid)),
                     vtype,
                     float(val) * 1e6,
                     row.get('useful_life') if pd.notna(row.get('useful_life')) else None))
            n += 1
        self.stats[sheet] = n
        self._print_stat(sheet, n)

    # ── Macro factors (wide: factor | 2011 | 2012 | ...) ───────────────

    def _load_macro(self, df: pd.DataFrame):
        """Load macro factors from wide format."""
        year_cols = self._detect_year_columns(df)
        factor_col = df.columns[0]

        n = 0
        for _, row in df.iterrows():
            factor = str(row[factor_col]).strip()
            if not factor or factor == 'nan':
                continue
            for yr in year_cols:
                val = row.get(yr)
                if pd.isna(val) or val is None:
                    continue
                if not self.dry_run:
                    self.conn.execute(
                        "INSERT OR REPLACE INTO macro_factors "
                        "(factor_name, year, value, scope, company_id, "
                        "source, updated_at) "
                        "VALUES (?,?,?,'company',?,'unified_excel',datetime('now'))",
                        (factor, yr, float(val), self.company_id))
                n += 1
        self.stats['macro_factors'] = n
        self._print_stat('macro_factors', n)

    # ── Operational drivers (wide: driver | unit | 2011 | ...) ─────────

    def _load_operational(self, df: pd.DataFrame):
        """Load operational drivers from wide format."""
        year_cols = self._detect_year_columns(df)
        driver_col = df.columns[0]
        unit_col = df.columns[1] if len(df.columns) > 1 else None

        n = 0
        for _, row in df.iterrows():
            driver = str(row[driver_col]).strip()
            if not driver or driver == 'nan':
                continue
            unit = None
            if unit_col and pd.notna(row.get(unit_col)):
                unit = str(row[unit_col]).strip()
            for yr in year_cols:
                val = row.get(yr)
                if pd.isna(val) or val is None:
                    continue
                if not self.dry_run:
                    self.conn.execute(
                        "INSERT OR REPLACE INTO operational_drivers "
                        "(company_id, metric, year, value, unit, "
                        "source, updated_at) "
                        "VALUES (?,?,?,?,?,'unified_excel',datetime('now'))",
                        (self.company_id, driver, yr, float(val), unit))
                n += 1
        self.stats['operational_drivers'] = n
        self._print_stat('operational_drivers', n)

    # ── Balancing adjustments ──────────────────────────────────────────

    def _load_balancing(self, df: pd.DataFrame):
        """Load balancing adjustments."""
        n = 0
        for _, row in df.iterrows():
            yr = row.get('year')
            stmt = str(row.get('statement_type', '')).strip()
            metric = str(row.get('metric', '')).strip()
            adj = row.get('adjustment_value_mUSD', row.get('adjustment_value'))
            if pd.isna(yr) or not stmt or not metric or pd.isna(adj):
                continue
            pid = self._ensure_period(int(yr))
            if pid == -1:
                continue
            if not self.dry_run:
                orig = row.get('original_value_mUSD', row.get('original_value'))
                self.conn.execute(
                    "INSERT OR REPLACE INTO balancing_adjustments "
                    "(company_id, period_id, statement_type, metric, adjustment_value, "
                    "is_balancing, balancing_reason, balancing_category, original_value, "
                    "source, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,'unified_excel',datetime('now'))",
                    (self.company_id, pid, stmt, metric,
                     float(adj) * 1e6,
                     int(row.get('is_balancing', 0)) if pd.notna(row.get('is_balancing')) else 0,
                     str(row.get('balancing_reason', '')) if pd.notna(row.get('balancing_reason')) else None,
                     str(row.get('balancing_category', '')) if pd.notna(row.get('balancing_category')) else None,
                     float(orig) * 1e6 if pd.notna(orig) else None))
            n += 1
        self.stats['balancing_adjustments'] = n
        self._print_stat('balancing_adjustments', n)


def main():
    ap = argparse.ArgumentParser(
        description="Единый загрузчик данных из unified Excel в data_mart_v2.db")
    ap.add_argument('--company', required=True, help="Company ID (e.g., rusal, us_steel, nornickel)")
    ap.add_argument('--excel', default=None, help="Path to Excel (auto-detect if omitted)")
    ap.add_argument('--db', default=DEFAULT_DB, help="Path to SQLite DB")
    ap.add_argument('--dry-run', action='store_true', help="Preview without writing")
    args = ap.parse_args()

    excel_path = Path(args.excel) if args.excel else _find_excel(args.company)
    if not excel_path.exists():
        print(f'ERROR: Excel not found: {excel_path}')
        print(f'  Expected: companies/{args.company}/data/excel/{args.company}_unified.xlsx')
        return 1

    loader = UnifiedExcelLoader(
        company_id=args.company,
        db_path=args.db,
        dry_run=args.dry_run,
    )
    loader.load(excel_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
