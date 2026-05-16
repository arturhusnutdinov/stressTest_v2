# Old PDF Discovery Report

## Parser Results on Old PDFs

| Year | IS | BS | CF |
|------|----|----|-----|
| 2019 | page 9, 15 metrics, years [2018,2019] | page 12, 13 metrics, years [2018,2019] | FAIL (page 2 = TOC) |
| 2016 | page 9, 14 metrics, years [2015,2016] | FAIL (page 2 = TOC) | FAIL (page 2 = TOC) |
| 2014 | page 6, 13 metrics, WRONG years [2025,2026] | page 9, 12 metrics, WRONG year [2015] | FAIL (page 2 = TOC) |

## Root Causes

### 1. CF FAIL: All old PDFs — fallback ignores anti-triggers
- CF spans 2 pages in old PDFs (Operating on page N, Investing/Financing on page N+1)
- Current anchors require ALL 3 ("Operating", "Investing", "Financing") on ONE page
- First pass fails → fallback returns page 2 (TOC) because fallback doesn't check anti-triggers
- **Fix**: (a) add anti-trigger check to fallback loop, (b) relax CF anchors to require 1 of 3

### 2. BS FAIL for 2016: Same fallback bug
- BS also spans 2 pages (Assets on page 11, Equity+Liabilities on separate page)
- Anchors "Total assets" + "Total equity" not both on page 11
- Fallback hits TOC

### 3. IS wrong years for 2014: Year detection confused
- IS page 6 has correct data (Revenue 9,357/9,760 for 2014/2013)
- But year detection picks up 2025/2026 from somewhere on page (possibly page numbering or misparse)
- Text fallback `_build_text_table` finds wrong year header line

### 4. Correct CF pages found by discovery
| Year | Real CF page(s) | Operating | Investing+Financing |
|------|----------------|-----------|---------------------|
| 2019 | 14 + 15 | page 14 | page 15 |
| 2016 | 14 + 15 | page 14 | page 15 |
| 2014 | 12 + 13 | page 12 | page 13 |

## Needed Parser Fixes (2 changes to pdf_parser.py)

### Fix 1: Fallback respects anti-triggers
```python
# Current (broken):
for i, page in enumerate(pdf.pages[:80]):
    text = page.extract_text() or ''
    if any(t.lower() in text.lower() for t in triggers):
        return i

# Fixed:
for i, page in enumerate(pdf.pages[:80]):
    text = page.extract_text() or ''
    text_low = text.lower()
    if any(t.lower() in text_low for t in triggers):
        if any(a.lower() in text_low for a in anti):
            continue
        return i
```

### Fix 2: CF anchors — require ANY 1 of 3 (not ALL)
Add yaml option `anchor_mode: any` (default: all). When `any`, at least 1 anchor must match instead of ALL.

## What This Would Fix

With these 2 changes:
- **2019**: IS ✓, BS ✓, CF would find page 14 (has "Operating activities")
- **2016**: IS ✓, BS would find page 11 (has "Total assets"), CF would find page 14
- **2014**: IS needs separate year detection fix, BS+CF would improve

## Coverage Estimate After Fixes
| Year range | IS | BS | CF |
|-----------|----|----|-----|
| 2019-2025 | 100% | ~80% | ~80% |
| 2015-2018 | ~80% | ~60% | ~50% |
| 2012-2014 | ~50% (year issues) | ~40% | ~40% |
