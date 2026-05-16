# Phase 4c-inventory Report

## Changes
- `parsers/adapters/rusal.yaml`: NOTE_16_INVENTORY section added (3 rows: RM/WIP/FG)
- `parsers/tests/smoke_rusal_note16_inventory.py`: created (103 lines)
- `parsers/pdf_parser.py`: three enhancements for Notes support:
  1. Page scan limit increased from 40 to 80 (Notes are on pages 47+)
  2. Text-line fallback: when table extraction gives <=1 year but page text has 2+, builds a virtual table from text lines
  3. `_build_text_table()`: finds year header line, then splits data lines into [metric, val1, val2, ...]

## Inventory Smoke Test
- Page: 47
- Years: [2024, 2023]
- **Expected-vs-parsed: 6/6 (100%)**
- Sum sanity: 2024: 1,447+848+2,182 = 4,477 = DB ✓ | 2023: 1,333+766+1,500 = 3,599 = DB ✓
- Status: **PASS**

## Key findings
- `parse_section()` works for Notes **with the text-line fallback**
- pdfplumber's text strategy splits Note 16 numbers across columns (e.g. "1,447" → cols "1,44" | "7")
- The text fallback builds a clean virtual table from `page.extract_text()` which has proper spacing
- Trigger strategy for Notes: use a data-specific phrase ("Raw materials and consumables") rather than Note number, because the Note header and data are on different pages

## IS/BS/CF regression
- IS: identical (16/16, 100%)
- BS: identical (25/27, 93%)
- CF: identical (34/34, 100%)

## Unit tests
- 11/11 passed

## Prod sanity
- us_steel BS: 0.000004
- rusal BS: 0.000004

## Status: PASS

## Architecture verdict
The text-line fallback proves that Notes-level tables CAN be parsed through the existing `parse_section()` engine. For Notes 13 (PPE movement) and 19 (Debt instruments), which have pivot/multi-column layouts, additional parser capabilities will likely be needed.

## Next
Phase 4c-debt (Note 19: debt instruments — pivot layout, needs new parsing capability)
