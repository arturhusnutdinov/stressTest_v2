"""Unit tests for Phase 4b-i parser upgrades."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from parsers.pdf_parser import PDFParser

def _p():
    return PDFParser(Path('parsers/adapters/rusal.yaml'))

def test_detect_year_columns_simple():
    table = [['', '', '', '2024', '', '2023'], ['Revenue', None, None, '12,082', None, '12,213']]
    assert _p()._detect_year_columns(table) == [(3, 2024), (5, 2023)]

def test_detect_year_columns_embedded_text():
    table = [['', '', '', '31 December 2024', '', '31 December 2023']]
    assert _p()._detect_year_columns(table) == [(3, 2024), (5, 2023)]

def test_detect_year_columns_bs_layout():
    table = [['', '', '', '', '2024', '', '2023', ''], ['', '', '', 'Note', 'USD million', '', 'USD million', '']]
    assert _p()._detect_year_columns(table) == [(4, 2024), (6, 2023)]

def test_parse_number_parens():
    p = _p()
    assert p._parse_number('(1,234)') == -1234.0
    assert p._parse_number('1,234') == 1234.0
    assert p._parse_number('0') == 0.0

def test_parse_number_nulls():
    p = _p()
    for v in ['—', '-', '–', 'n/a', 'N/A', '', None, '   ']:
        assert p._parse_number(v) is None, f'expected None for {v!r}'

def test_normalize():
    assert PDFParser._normalize('Cost of sales') == 'costofsales'
    assert PDFParser._normalize('Property, plant and equipment') == 'property,plantandequipment'
    assert PDFParser._normalize('') == ''
    assert PDFParser._normalize(None) == ''

def test_normalize_preserves_digits():
    assert PDFParser._normalize('Note 5') == 'note5'
    assert PDFParser._normalize('(1,234)') == '(1,234)'


# ─── Added in Phase 4b-i FIX ───────────────────────────────────

def test_smoke_file_exists():
    """Smoke test must be a REAL file, not inline heredoc."""
    p = Path('parsers/tests/smoke_rusal_is_2024.py')
    assert p.exists(), f'Smoke test file MUST exist: {p}'
    assert p.stat().st_size > 1000, f'Smoke test too small: {p.stat().st_size} bytes'


def test_yaml_no_dollar_after_letters():
    """yaml patterns should not use $ directly after letters."""
    import re as _re
    yaml_text = Path('parsers/adapters/rusal.yaml').read_text()
    dangerous = _re.findall(r'"[^"]*[a-z)]\$"', yaml_text)
    assert not dangerous, f'Dangerous anchored patterns: {dangerous}'


# ─── Added in Phase 4b-ii-agg ──────────────────────────────────

def test_combine_from_basic():
    """Aggregate sums helper components per year, helpers filtered out."""
    import tempfile
    import yaml as _y
    cfg = {
        'meta': {'thousands_separator': ','},
        'sections': {
            'TEST': {
                'page_triggers': ['Test'],
                'rows': {
                    '_a': {'patterns': ['^alpha']},
                    '_b': {'patterns': ['^beta']},
                    'agg_ab': {'combine_from': ['_a', '_b']},
                },
            }
        }
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        _y.dump(cfg, f)
        tmp_path = f.name

    p = PDFParser(Path(tmp_path))
    table = [
        ['', '', '2024', '2023'],
        ['alpha', '', '100', '200'],
        ['beta',  '', '50',  '75'],
    ]
    year_cols = [(2, 2024), (3, 2023)]
    sec_cfg = p.adapter['sections']['TEST']
    metrics, unmatched = p._map_rows(table, sec_cfg, year_cols)

    assert 'agg_ab' in metrics, f'agg_ab missing: {metrics}'
    assert metrics['agg_ab'][2024] == 150
    assert metrics['agg_ab'][2023] == 275
    assert '_a' not in metrics
    assert '_b' not in metrics


def test_combine_from_partial_year():
    """If one component missing for a year, aggregate skips that year."""
    import tempfile
    import yaml as _y
    cfg = {
        'meta': {'thousands_separator': ','},
        'sections': {
            'TEST': {
                'page_triggers': ['Test'],
                'rows': {
                    '_a': {'patterns': ['^alpha']},
                    '_b': {'patterns': ['^beta']},
                    'agg_ab': {'combine_from': ['_a', '_b']},
                },
            }
        }
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        _y.dump(cfg, f)
        tmp_path = f.name

    p = PDFParser(Path(tmp_path))
    table = [
        ['', '', '2024', '2023'],
        ['alpha', '', '100', '200'],
        ['beta',  '', '',    '75'],
    ]
    year_cols = [(2, 2024), (3, 2023)]
    sec_cfg = p.adapter['sections']['TEST']
    metrics, unmatched = p._map_rows(table, sec_cfg, year_cols)

    assert 'agg_ab' in metrics
    assert 2023 in metrics['agg_ab']
    assert metrics['agg_ab'][2023] == 275
    assert 2024 not in metrics['agg_ab'], \
        f'2024 should skip due to missing beta: {metrics}'


# ─── Added in Phase 4c-tests: lock down _build_text_table + fallback ───

def test_build_text_table_basic():
    """Basic case: header line with 2 years, 2 data lines with values."""
    page_text = '''Some heading
31 December 2024 31 December 2023
USD million USD million
Revenue 12,082 12,213
Cost of sales (9,261) (10,445)
'''
    result = PDFParser._build_text_table(page_text)
    assert result, f'expected non-empty, got {result}'
    assert result[0] == ['', '2024', '2023'], f'header: {result[0]}'
    data_rows = [r for r in result[1:] if len(r) > 1]
    assert len(data_rows) >= 2, f'expected >=2 data rows: {data_rows}'
    rev_row = next((r for r in data_rows if 'Revenue' in r[0]), None)
    assert rev_row is not None, f'Revenue not found: {data_rows}'
    assert '12,082' in rev_row, f'Revenue 2024 not in row: {rev_row}'


def test_build_text_table_no_years():
    """No years in text -> empty list (fallback wouldn't activate)."""
    page_text = '''Just some text with no year numbers at all.
Random data 100 200
More random 50 75
'''
    result = PDFParser._build_text_table(page_text)
    assert result == [], f'expected empty, got {result}'


def test_build_text_table_notes_case():
    """Structure similar to Note 16 Inventory page 47."""
    page_text = '''Disclosures
31 December 31 December
2024 2023
USD million USD million
Raw materials and consumables 1,447 1,333
Work in progress 848 766
Finished goods and goods held for resale 2,182 1,500
4,477 3,599
'''
    result = PDFParser._build_text_table(page_text)
    assert result, f'expected non-empty, got {result}'
    assert result[0] == ['', '2024', '2023'], f'header: {result[0]}'
    rm_row = next((r for r in result[1:] if 'Raw materials' in r[0]), None)
    assert rm_row is not None, f'Raw materials not found'
    assert '1,447' in rm_row, f'Raw materials 2024 missing: {rm_row}'


def test_fallback_activates_on_split_columns():
    """Virtual table from _build_text_table gives 2 years detectable
    by _detect_year_columns (integration of the two methods)."""
    import tempfile
    import yaml as _y
    page_text = '''Note 16 Inventories
Disclosures
31 December 31 December
2024 2023
USD million USD million
Raw materials and consumables 1,447 1,333
'''
    vt = PDFParser._build_text_table(page_text)
    tmp_yaml = {
        'meta': {'thousands_separator': ','},
        'sections': {'TEST': {'page_triggers': ['X'], 'rows': {}}},
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        _y.dump(tmp_yaml, f)
        tmp_path = f.name
    p = PDFParser(Path(tmp_path))
    detected = p._detect_year_columns(vt)
    years = [y for _, y in detected]
    assert 2024 in years and 2023 in years, \
        f'expected both years in fallback output: {detected}'


def test_fallback_not_needed_when_table_has_two_years():
    """Normal table with 2 years detected — fallback should NOT activate."""
    import tempfile
    import yaml as _y
    tmp_yaml = {
        'meta': {'thousands_separator': ','},
        'sections': {'TEST': {'page_triggers': ['X'], 'rows': {}}},
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        _y.dump(tmp_yaml, f)
        tmp_path = f.name
    p = PDFParser(Path(tmp_path))
    table = [
        ['', '', '', '2024', '', '2023'],
        ['Revenue', None, None, '12,082', None, '12,213'],
        ['COGS', None, None, '(9,261)', None, '(10,445)'],
    ]
    detected = p._detect_year_columns(table)
    years = [y for _, y in detected]
    assert years == [2024, 2023], f'expected [2024, 2023], got {detected}'
    assert len(detected) == 2, f'fallback would activate if <= 1: {detected}'


# ─── Added in Phase 4c-ppe: _parse_pivot_table unit tests ──────────────

def test_pivot_table_basic():
    """Basic pivot: 2 blocks, movements, 2 categories."""
    import tempfile, yaml as _y

    cfg = {
        'meta': {'thousands_separator': ','},
        'sections': {
            'TEST': {
                'page_triggers': ['X'],
                'pivot_header_rows': 1,
                'pivot_label_col': 0,
                'pivot_data_col_start': 1,
                'pivot_blocks': {
                    'cost': ['Cost'],
                    'accum_dep': ['Accumulated depreciation'],
                },
                'pivot_movements': {
                    'opening': ['Balance at 1 January'],
                    'additions': ['Additions'],
                    'closing': ['Balance at 31 December'],
                },
                'pivot_year_in_label': True,
            }
        }
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        _y.dump(cfg, f)
        tmp = f.name

    p = PDFParser(Path(tmp))
    table = [
        ['USD million', 'Land', 'Total'],
        ['Cost', '', ''],
        ['Balance at 1 January 2024', '100', '200'],
        ['Additions', '10', '15'],
        ['Balance at 31 December 2024', '110', '215'],
        ['Accumulated depreciation', '', ''],
        ['Balance at 1 January 2024', '40', '80'],
        ['Balance at 31 December 2024', '50', '95'],
    ]
    sec_cfg = cfg['sections']['TEST']
    data, categories, warnings = p._parse_pivot_text('\n'.join(' '.join(str(c or '') for c in row) for row in table), sec_cfg)

    assert 'cost' in data, f'cost block missing: {list(data)}'
    assert 2024 in data['cost'], f'2024 missing in cost'
    assert 'additions' in data['cost'][2024], f'additions missing'
    vals = list(data['cost'][2024]['additions'].values())
    assert 10.0 in vals, f'expected 10 in additions: {vals}'
    assert 'accum_dep' in data, f'accum_dep missing'


def test_pivot_table_two_years():
    """Two year sub-blocks within one block."""
    import tempfile, yaml as _y

    cfg = {
        'meta': {'thousands_separator': ','},
        'sections': {
            'TEST': {
                'page_triggers': ['X'],
                'pivot_header_rows': 1,
                'pivot_label_col': 0,
                'pivot_data_col_start': 1,
                'pivot_blocks': {'cost': ['Cost']},
                'pivot_movements': {
                    'opening': ['Balance at 1 January'],
                    'additions': ['Additions'],
                },
                'pivot_year_in_label': True,
            }
        }
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        _y.dump(cfg, f)
        tmp = f.name

    p = PDFParser(Path(tmp))
    table = [
        ['Label', 'Total'],
        ['Cost', ''],
        ['Balance at 1 January 2023', '500'],
        ['Additions', '50'],
        ['Balance at 1 January 2024', '550'],
        ['Additions', '60'],
    ]
    sec_cfg = cfg['sections']['TEST']
    data, cats, warns = p._parse_pivot_text('\n'.join(' '.join(str(c or '') for c in row) for row in table), sec_cfg)

    assert 2023 in data.get('cost', {}), f'2023 missing'
    assert 2024 in data.get('cost', {}), f'2024 missing'
    adds_2023 = list(data['cost'][2023].get('additions', {}).values())
    adds_2024 = list(data['cost'][2024].get('additions', {}).values())
    assert adds_2023 and adds_2023[0] == 50.0, f'2023 additions: {adds_2023}'
    assert adds_2024 and adds_2024[0] == 60.0, f'2024 additions: {adds_2024}'


# ─── Added in Phase 4c-debt: _parse_instrument_page unit tests ─────

def test_instrument_page_basic():
    """Basic instrument page: 2 classes, 3 instruments, 7 buckets."""
    import tempfile, yaml as _y

    cfg = {
        'meta': {'thousands_separator': ','},
        'sections': {
            'TEST': {
                'page_triggers': ['Terms'],
                'instrument_classes': {
                    'secured': ['Secured bank loans'],
                    'unsecured': ['Unsecured bank loans'],
                },
                'rate_types': {'variable': ['Variable'], 'fixed': ['Fixed']},
                'skip_rows': ['^Total', '^Interest'],
                'maturity_buckets_count': 7,
                'maturity_bucket_names': ['total', 'yr1', 'yr2', 'yr3', 'yr4', 'yr5', 'yr6_plus'],
            }
        }
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        _y.dump(cfg, f)
        tmp = f.name

    p = PDFParser(Path(tmp))
    text = (
        "Terms and debt repayment schedule as at 31 December 2024\n"
        "Total 2025 2026 2027 2028 2029 2030-2035\n"
        "Secured bank loans\n"
        "Variable\n"
        "RUB KeyRate + 2.2% 98 26 36 36 – – –\n"
        "Fixed\n"
        "CNY 4.75% 1,564 522 521 521 – – –\n"
        "Unsecured bank loans\n"
        "Variable\n"
        "CNY LPR1Y + 3.1% 333 – 333 – – – –\n"
        "Total 1,995 548 890 557 – – –\n"
    )
    instruments, year, warnings = p._parse_instrument_page(text, cfg['sections']['TEST'])

    assert year == 2024, f'expected 2024, got {year}'
    assert len(instruments) == 3, f'expected 3, got {len(instruments)}'
    assert instruments[0]['instrument_class'] == 'secured'
    assert instruments[0]['rate_type'] == 'variable'
    assert instruments[0]['total'] == 98.0
    assert instruments[0]['yr1'] == 26.0
    assert instruments[1]['rate_type'] == 'fixed'
    assert instruments[1]['total'] == 1564.0
    assert instruments[2]['instrument_class'] == 'unsecured'


def test_instrument_page_multiline_description():
    """Multi-line descriptions (SOFR, Euribor) are parsed via pending_description."""
    import tempfile, yaml as _y

    cfg = {
        'meta': {'thousands_separator': ','},
        'sections': {
            'TEST': {
                'page_triggers': ['Terms'],
                'instrument_classes': {
                    'secured': ['Secured bank loans'],
                    'unsecured': ['Unsecured bank loans'],
                },
                'rate_types': {'variable': ['Variable'], 'fixed': ['Fixed']},
                'skip_rows': ['^Total'],
                'maturity_buckets_count': 7,
                'maturity_bucket_names': ['total', 'yr1', 'yr2', 'yr3', 'yr4', 'yr5', 'yr6_plus'],
            }
        }
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        _y.dump(cfg, f)
        tmp = f.name

    p = PDFParser(Path(tmp))
    text = (
        "Terms and debt repayment schedule as at 31 December 2024\n"
        "Secured bank loans\n"
        "Variable\n"
        "RUB KeyRate + 2.2% 98 26 36 36 – – –\n"
        "USD – Term SOFR + Spread\n"
        "+ 2.1% 1 1 – – – – –\n"
        "Unsecured bank loans\n"
        "Variable\n"
        "EUR – 6M Euribor +\n"
        "(0.45%-0.67%) 26 6 6 5 5 2 2\n"
    )
    instruments, year, warns = p._parse_instrument_page(text, cfg['sections']['TEST'])

    assert len(instruments) == 3, f'expected 3, got {len(instruments)}: {[i["rate_description"] for i in instruments]}'
    assert instruments[0]['total'] == 98.0
    assert instruments[1]['total'] == 1.0
    assert 'SOFR' in instruments[1]['rate_description']
    assert instruments[2]['total'] == 26.0
    assert 'Euribor' in instruments[2]['rate_description'] or '0.45' in instruments[2]['rate_description']


# ─── Added in Phase 4c-pivot Note 15: wide-table mode ──────────────

def test_wide_pivot_table_basic():
    """Wide-table: years in column headers, 3 categories x 2 years = 6 numbers."""
    import tempfile, yaml as _y

    cfg = {
        'meta': {'thousands_separator': ','},
        'sections': {
            'TEST': {
                'page_triggers': ['X'],
                'pivot_wide_table': True,
                'pivot_blocks': {'investments': ['Balance at']},
                'pivot_movements': {
                    'opening': ['balance at the beginning'],
                    'share_of_profits': ['share of profits'],
                    'dividends': ['dividends'],
                    'closing': ['balance at the end'],
                },
                'pivot_categories': ['jv', 'associates', 'total'],
                'skip_rows': ['^Goodwill'],
            }
        }
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        _y.dump(cfg, f)
        tmp = f.name

    p = PDFParser(Path(tmp))
    text = (
        "Disclosures\n"
        "31 December 2024 2023\n"
        "Balance at the beginning of the year 850 3,671 4,521 888 4,286 5,174\n"
        "Group's share of profits 217 347 564 123 629 752\n"
        "Dividends (34) – (34) – (398) (398)\n"
        "Balance at the end of the year 1,252 3,616 4,868 850 3,671 4,521\n"
        "Goodwill included in associates 84 1,801 1,885 – 1,982 1,982\n"
    )
    data, cats, warns = p._parse_wide_pivot_text(text, cfg['sections']['TEST'])

    block = list(data.keys())[0]
    assert 2024 in data[block], f'2024 missing'
    assert 2023 in data[block], f'2023 missing'
    assert data[block][2024]['closing']['total'] == 4868.0
    assert data[block][2024]['share_of_profits']['total'] == 564.0
    assert data[block][2023]['closing']['total'] == 4521.0


# ─── Phase 4c-note8: _parse_sequential_pivot_text tests ────────────

def test_sequential_pivot_basic():
    """Sequential sub-blocks: 2023 then 2024, categories, 4 movements."""
    import tempfile, yaml as _y
    cfg = {
        'meta': {'thousands_separator': ','},
        'sections': {'TEST': {
            'page_triggers': ['Movement'],
            'pivot_sequential': True,
            'pivot_categories_rows': {
                'ppe': ['property, plant and equipment'],
                'total': ['total'],
            },
            'pivot_movement_names': ['opening', 'recognised_in_pl', 'fx', 'closing'],
            'pivot_movements_count': 4,
            'year_header_trigger': ['usd million', '1 january'],
            'skip_rows': [],
        }}
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        _y.dump(cfg, f)
        tmp = f.name

    p = PDFParser(Path(tmp))
    text = (
        "USD million 2023 P&L FX 31 Dec 2023\n"
        "Property, plant and equipment (482) (44) 23 (503)\n"
        "Total (369) 170 23 (176)\n"
        "\n"
        "USD million 2024 P&L FX 31 Dec 2024\n"
        "Property, plant and equipment (503) (72) (27) (602)\n"
        "Total (176) 65 (27) (138)\n"
    )
    data, warns = p._parse_sequential_pivot_text(text, cfg['sections']['TEST'])
    assert 2023 in data and 2024 in data
    assert data[2023]['ppe']['closing'] == -503.0
    assert data[2024]['total']['closing'] == -138.0
    assert data[2024]['total']['recognised_in_pl'] == 65.0


if __name__ == '__main__':
    import traceback
    tests = [v for k, v in list(globals().items()) if k.startswith('test_')]
    passed = failed = 0
    for t in tests:
        try:
            t(); print(f'  \u2713 {t.__name__}'); passed += 1
        except Exception:
            print(f'  \u2717 {t.__name__}'); traceback.print_exc(); failed += 1
    print(f'\n{passed} passed, {failed} failed')
    import sys; sys.exit(0 if failed == 0 else 1)
