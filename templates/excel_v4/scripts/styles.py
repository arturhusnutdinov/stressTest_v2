"""Design system for Corporate Financial Model v4 — mirrors bank model aesthetics."""
from openpyxl.styles import (
    Font, PatternFill, Alignment, Border, Side, NamedStyle, numbers,
)

# ── Color palette (from bank model) ──────────────────────────────────────────
SL = '3F5A73'   # Slate — headers, section titles
GR = '33383D'   # Dark gray — label text
BU = '7A2B38'   # Burgundy — action indicators
LG = '6B7580'   # Light gray — notes, footnotes

# Cell background fills
FILL_SEC      = PatternFill('solid', fgColor=SL)           # Section header (dark)
FILL_SUB      = PatternFill('solid', fgColor='E3E8ED')     # Subsection (light gray)
FILL_INPUT    = PatternFill('solid', fgColor='FFF2A8')     # Yellow — user input
FILL_RESULT   = PatternFill('solid', fgColor='E8F5E9')     # Green — result
FILL_HIST     = PatternFill('solid', fgColor='F5F5F5')     # Very light gray — historical
FILL_FORECAST = PatternFill('solid', fgColor='FFFFFF')     # White — forecast
FILL_CHECK_OK = PatternFill('solid', fgColor='DCFCE7')     # Green — check OK
FILL_CHECK_ERR= PatternFill('solid', fgColor='FEE2E2')    # Red — check error

# Tab colors for sheet organization
TAB_NAV    = '4472C4'   # Blue — navigation (00_Guide, 00_Cover)
TAB_INPUT  = 'FFC000'   # Yellow — input (CP, Macro, Hist, Assump, Raw)
TAB_ENGINE = 'A5A5A5'   # Gray — engine sheets (10-24)
TAB_REPORT = '70AD47'   # Green — reporting (30-40)
TAB_CTRL   = 'ED7D31'   # Orange — control (90, Output, Changelog)

# ── Fonts ────────────────────────────────────────────────────────────────────
F_TITLE     = Font(name='Arial', size=14, bold=True, color=SL)
F_SUBTITLE  = Font(name='Arial', size=9, color=GR)
F_SEC       = Font(name='Arial', size=10, bold=True, color='FFFFFF')   # on dark bg
F_SUB       = Font(name='Arial', size=9, bold=True, color=SL)
F_LABEL     = Font(name='Arial', size=9, color=GR)
F_LABEL_B   = Font(name='Arial', size=9, bold=True, color=GR)
F_INPUT     = Font(name='Arial', size=9, bold=True, color='0000FF')    # blue = editable
F_REF       = Font(name='Arial', size=9, color='008000')               # green = link
F_REF_BOLD  = Font(name='Arial', size=9, bold=True, color='008000')
F_FORMULA   = Font(name='Arial', size=9, color='000000')               # black = calc
F_FORMULA_B = Font(name='Arial', size=9, bold=True, color='000000')
F_UNIT      = Font(name='Arial', size=8, color=GR)
F_YEAR      = Font(name='Arial', size=9, bold=True, color=SL)
F_NOTE      = Font(name='Arial', size=8, bold=True, italic=True, color=LG)
F_GUIDE_LINK= Font(name='Arial', size=9, bold=True, color='4472C4', underline='single')

# ── Alignment ────────────────────────────────────────────────────────────────
A_LEFT   = Alignment(horizontal='left', vertical='center')
A_RIGHT  = Alignment(horizontal='right', vertical='center')
A_CENTER = Alignment(horizontal='center', vertical='center')
A_WRAP   = Alignment(horizontal='left', vertical='top', wrap_text=True)

# ── Borders ──────────────────────────────────────────────────────────────────
_thin = Side(style='thin', color='B8C2CC')
_hair = Side(style='hair', color='D0D0D0')
BORDER_BOT   = Border(bottom=_thin)
BORDER_TOP   = Border(top=_thin)
BORDER_BOTH  = Border(top=_thin, bottom=_thin)
BORDER_HAIR  = Border(bottom=_hair)

# ── Number formats ───────────────────────────────────────────────────────────
FMT_MLN     = '#,##0.0'       # 1,234.5 (millions)
FMT_MLN0    = '#,##0'         # 1,234 (rounded millions)
FMT_BLN     = '#,##0.0,,"B"'  # billions
FMT_PCT     = '0.0%'          # 12.3%
FMT_PCT2    = '0.00%'         # 12.34%
FMT_RATIO   = '0.00'          # 3.50 (ratio)
FMT_RATIO1  = '0.0'           # 3.5
FMT_DAYS    = '#,##0'         # 45 (days)
FMT_MULT    = '0.0"x"'        # 3.5x (multiples)
FMT_INT     = '#,##0'         # integers
FMT_TEXT    = '@'              # text

# ── Column layout ────────────────────────────────────────────────────────────
# Standard: A=label, B=unit, C-F=history, G-K=forecast, L=notes
COL_WIDTHS = {
    'A': 42,   # Label
    'B': 7,    # Unit
    'C': 11, 'D': 11, 'E': 11, 'F': 11,   # History years
    'G': 11, 'H': 11, 'I': 11, 'J': 11, 'K': 11,  # Forecast years
    'L': 42,   # Notes/source
}

# Year columns: C=hist_start ... F=hist_end, G=fc_start ... K=fc_end
# Adjustable per company (different history depths)


def apply_col_widths(ws, widths=None):
    """Set standard column widths."""
    for col, w in (widths or COL_WIDTHS).items():
        ws.column_dimensions[col].width = w


def section_header(ws, row, text, cols=12):
    """Write section header row (dark background, white text)."""
    cell = ws.cell(row, 1, text)
    cell.font = F_SEC
    cell.fill = FILL_SEC
    cell.alignment = A_LEFT
    for c in range(2, cols + 1):
        ws.cell(row, c).fill = FILL_SEC


def subsection_header(ws, row, text):
    """Write subsection header (light background)."""
    cell = ws.cell(row, 1, text)
    cell.font = F_SUB
    cell.fill = FILL_SUB
    for c in range(2, 13):
        ws.cell(row, c).fill = FILL_SUB


def year_headers(ws, row, hist_years, fc_years, col_start=3):
    """Write year header row: hist years + forecast years."""
    col = col_start
    for yr in hist_years:
        cell = ws.cell(row, col, yr)
        cell.font = F_YEAR
        cell.alignment = A_CENTER
        cell.fill = FILL_HIST
        col += 1
    for yr in fc_years:
        cell = ws.cell(row, col, f"{yr}E")
        cell.font = F_YEAR
        cell.alignment = A_CENTER
        cell.fill = FILL_FORECAST
        col += 1


def label_row(ws, row, label, unit='', note=''):
    """Write label + unit + note."""
    ws.cell(row, 1, label).font = F_LABEL
    if unit:
        ws.cell(row, 2, unit).font = F_UNIT
    if note:
        ws.cell(row, 12, note).font = F_NOTE


def input_cell(ws, row, col, value, fmt=FMT_PCT):
    """Write an editable input cell (blue font, yellow bg)."""
    cell = ws.cell(row, col, value)
    cell.font = F_INPUT
    cell.fill = FILL_INPUT
    cell.number_format = fmt
    return cell


def formula_cell(ws, row, col, formula, fmt=FMT_MLN, bold=False):
    """Write a calculated formula cell (black font).
    Sets initial cached value to 0 to avoid empty <v></v> in XML."""
    cell = ws.cell(row, col)
    cell.value = formula
    cell.font = F_FORMULA_B if bold else F_FORMULA
    cell.number_format = fmt
    # Ensure cached value is not empty (prevents Excel repair dialog)
    if hasattr(cell, '_value') and cell.data_type == 'f':
        cell._value = formula  # openpyxl stores formula in _value
    return cell


def ref_cell(ws, row, col, ref_formula, fmt=FMT_MLN, bold=False):
    """Write a cross-sheet reference cell (green font).
    Sets initial cached value to 0 to avoid empty <v></v> in XML."""
    cell = ws.cell(row, col)
    cell.value = ref_formula
    cell.font = F_REF_BOLD if bold else F_REF
    cell.number_format = fmt
    return cell
