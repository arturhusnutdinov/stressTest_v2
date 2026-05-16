"""PDF parser for company financial reports. Generic engine + YAML adapters.

Phase 4a scope: IS section only. BS/CF/Notes stubs in Phase 4b/c.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pdfplumber
import yaml


@dataclass
class ParseResult:
    section: str
    pdf_path: str
    page_used: Optional[int]
    years_detected: list
    metrics: dict
    unmatched_rows: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


class PDFParser:
    """Generic PDF parser. Adapter yaml provides company-specific layout."""

    def __init__(self, adapter_path: Path):
        self.adapter_path = Path(adapter_path)
        with open(self.adapter_path) as f:
            self.adapter = yaml.safe_load(f)
        self.meta = self.adapter.get('meta', {})
        self.thousands = self.meta.get('thousands_separator', ',')

    def parse_section(self, pdf_path: Path, section: str) -> ParseResult:
        pdf_path = Path(pdf_path)
        sec_cfg = (self.adapter.get('sections') or {}).get(section)
        if sec_cfg is None:
            return ParseResult(section, str(pdf_path), None, [], {},
                               warnings=[f'section {section} not configured'])

        with pdfplumber.open(pdf_path) as pdf:
            page_idx = self._find_target_page(pdf, sec_cfg)
            if page_idx is None:
                return ParseResult(section, str(pdf_path), None, [], {},
                                   warnings=['no page matched triggers'])

            page = pdf.pages[page_idx]
            # Try default table extraction first, then text strategy
            tables = page.extract_tables() or []
            if not tables or all(len(t) < 5 for t in tables):
                tables = page.extract_tables(table_settings={
                    "vertical_strategy": "text",
                    "horizontal_strategy": "text",
                }) or []

            # Also try next page (IS may span 2 pages)
            if page_idx + 1 < len(pdf.pages):
                tables2 = pdf.pages[page_idx + 1].extract_tables(table_settings={
                    "vertical_strategy": "text",
                    "horizontal_strategy": "text",
                }) or []
                tables.extend(tables2)

            if not tables:
                return ParseResult(section, str(pdf_path), page_idx + 1, [], {},
                                   warnings=['page matched but no tables extracted'])

            # Use largest table
            table = max(tables, key=lambda t: len(t))

            years = self._detect_years(table, sec_cfg)
            metrics, unmatched = self._map_rows(table, sec_cfg, years)

            return ParseResult(
                section=section,
                pdf_path=str(pdf_path),
                page_used=page_idx + 1,
                years_detected=years,
                metrics=metrics,
                unmatched_rows=unmatched,
            )

    def _find_target_page(self, pdf, sec_cfg) -> Optional[int]:
        triggers = sec_cfg.get('page_triggers', [])
        anti = sec_cfg.get('page_anti_triggers', [])

        for i, page in enumerate(pdf.pages[:30]):
            text = page.extract_text() or ''
            text_low = text.lower()

            if not any(t.lower() in text_low for t in triggers):
                continue
            if any(a.lower() in text_low for a in anti):
                continue

            # Check for data content (numbers on the page)
            if re.search(r'\d{1,3}(?:,\d{3})+|\(\d', text):
                return i

        # Fallback: any page with trigger
        for i, page in enumerate(pdf.pages[:30]):
            text = page.extract_text() or ''
            if any(t.lower() in text.lower() for t in triggers):
                return i

        return None

    def _detect_years(self, table, sec_cfg) -> list:
        years = []
        year_re = re.compile(r'\b(20\d{2})\b')
        # Search in all rows (header may not have explicit years)
        for row in table[:10]:
            all_text = ' '.join(str(c or '') for c in row)
            for m in year_re.finditer(all_text):
                y = int(m.group(1))
                if 2015 <= y <= 2030 and y not in years:
                    years.append(y)
            if len(years) >= 2:
                break

        # Fallback: also check page text via adapter
        if not years:
            # Try common years
            years = [2024, 2023]

        return sorted(years, reverse=True)

    def _map_rows(self, table, sec_cfg, years):
        cols = sec_cfg.get('columns', {})
        metric_col = cols.get('metric_col', 0)
        year_cols_from = cols.get('year_cols_from', 2)
        rows_cfg = sec_cfg.get('rows', {})

        compiled = {}
        for canonical, spec in rows_cfg.items():
            patterns = spec.get('patterns', [])
            compiled[canonical] = {
                'patterns': [re.compile(p, re.IGNORECASE) for p in patterns],
                'sign': spec.get('sign', 'natural'),
            }

        metrics = {}
        unmatched = []
        matched_canonicals = set()

        for row in table:
            if not row or len(row) <= metric_col:
                continue

            # Join first columns as metric text (PDF may split across cols)
            year_start = cols.get('year_cols_from', 2)
            note_col = cols.get('note_col', -1)
            metric_parts = []
            for ci in range(min(year_start, len(row))):
                if ci == note_col:
                    continue
                cell = str(row[ci] or '').strip()
                if cell and not re.match(r'^\d+(\([a-z]\))?$', cell):
                    metric_parts.append(cell)
            metric_text = ' '.join(metric_parts).strip()
            metric_text = re.sub(r'\s+', ' ', metric_text)
            # Fix PDF word-breaks: rejoin split words
            # Only join when fragment is 1-2 chars (word end split)
            metric_text = re.sub(r'(\w{2,}) ([a-z]{1,2})\b', r'\1\2', metric_text)
            # Specific broken patterns from Rusal PDFs
            for broken, fixed in [
                ('ex penses', 'expenses'), ('expens es', 'expenses'),
                ('incom e', 'income'), ('profit s', 'profits'),
                ('activit ies', 'activities'), ('ac tivities', 'activities'),
                ('credi t', 'credit'), ('associat es', 'associates'),
                ('operat ing', 'operating'), ('perating', 'operating'),
                ('taxat ion', 'taxation'), ('EBIT DA', 'EBITDA'),
                ('t losses', 't losses'),  # keep space — "credit losses"
            ]:
                metric_text = metric_text.replace(broken, fixed)

            if not metric_text or len(metric_text) < 3:
                continue

            # Skip note references and pure numbers
            if re.match(r'^\d+\.?\d*$', metric_text):
                continue

            matched_canonical = None
            for canonical, spec in compiled.items():
                if canonical in matched_canonicals:
                    continue  # Don't re-match already found
                if any(p.search(metric_text) for p in spec['patterns']):
                    matched_canonical = canonical
                    matched_canonicals.add(canonical)
                    break

            if matched_canonical is None:
                if any(c.isalpha() for c in metric_text) and len(metric_text) > 3:
                    unmatched.append(metric_text)
                continue

            sign = compiled[matched_canonical]['sign']
            year_values = {}

            # Try multiple column detection strategies
            # Strategy 1: year_cols_from sequential
            for idx, year in enumerate(years):
                col = year_cols_from + idx
                if col < len(row):
                    val = self._parse_number(row[col])
                    if val is not None:
                        if sign == 'abs':
                            val = abs(val)
                        year_values[year] = val

            # Strategy 2: scan all columns for numbers if Strategy 1 got nothing
            if not year_values:
                num_vals = []
                for col_idx in range(len(row)):
                    if col_idx == metric_col:
                        continue
                    val = self._parse_number(row[col_idx])
                    if val is not None:
                        num_vals.append(val)
                # Assign to years in order (most recent first)
                for idx, year in enumerate(years):
                    if idx < len(num_vals):
                        val = num_vals[idx]
                        if sign == 'abs':
                            val = abs(val)
                        year_values[year] = val

            if year_values:
                metrics[matched_canonical] = year_values

        return metrics, unmatched

    def _parse_number(self, raw) -> Optional[float]:
        if raw is None:
            return None
        s = str(raw).strip()
        if s in ('', '—', '–', '-', 'n/a', 'N/A', 'None'):
            return None

        neg = False
        if s.startswith('(') and s.endswith(')'):
            neg = True
            s = s[1:-1]

        s = s.replace(self.thousands, '').replace(' ', '').replace('\xa0', '')

        # Remove currency symbols
        s = re.sub(r'[^0-9.\-]', '', s)

        if not s:
            return None

        try:
            v = float(s)
        except ValueError:
            return None
        return -v if neg else v
