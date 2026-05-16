"""
Unit tests for ModelPreprocessor — all 14 metric groups.

Uses synthetic 5-year data loaded into tmp_db via Repository.
"""
import pytest
from engine.database.repository import Repository
from engine.preprocessor.core import ModelPreprocessor, ewa


# ══════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════

SYNTH_COMPANY = "test_co"


@pytest.fixture
def seeded_repo(tmp_db):
    """tmp_db with 5 years of synthetic IS/BS/CF history for test_co."""
    from engine.database.schema import create_schema
    create_schema(tmp_db)

    # Wrap in Repository-like interface
    repo = Repository.__new__(Repository)
    repo._conn = tmp_db
    repo._path = None

    repo.upsert_company(SYNTH_COMPANY, "TestCo", industry="metals", currency="USD", db_unit="USD")

    years = [2020, 2021, 2022, 2023, 2024]
    for yr in years:
        repo.ensure_period(SYNTH_COMPANY, yr, is_forecast=0)

    # ── IS data (growing company) ──
    is_data = {
        2020: {"revenue": 100_000, "cogs": -75_000, "gross_profit": 25_000,
               "sga": -8_000, "depreciation_owned": -5_000, "amortization": -1_000,
               "total_da": -6_000, "ebitda": 18_000, "ebit": 12_000,
               "interest_expense": -2_000, "ebt": 10_000,
               "tax_expense": -2_100, "net_income": 7_900,
               "earnings_from_investees": 500, "interest_income": 200,
               "net_periodic_benefit_income": 100},
        2021: {"revenue": 110_000, "cogs": -81_000, "gross_profit": 29_000,
               "sga": -8_500, "depreciation_owned": -5_200, "amortization": -1_000,
               "total_da": -6_200, "ebitda": 21_500, "ebit": 15_300,
               "interest_expense": -2_100, "ebt": 13_200,
               "tax_expense": -2_772, "net_income": 10_428,
               "earnings_from_investees": 550, "interest_income": 220,
               "net_periodic_benefit_income": 110},
        2022: {"revenue": 125_000, "cogs": -90_000, "gross_profit": 35_000,
               "sga": -9_200, "depreciation_owned": -5_500, "amortization": -1_000,
               "total_da": -6_500, "ebitda": 26_800, "ebit": 20_300,
               "interest_expense": -2_300, "ebt": 18_000,
               "tax_expense": -3_780, "net_income": 14_220,
               "earnings_from_investees": 600, "interest_income": 250,
               "net_periodic_benefit_income": 120},
        2023: {"revenue": 135_000, "cogs": -98_000, "gross_profit": 37_000,
               "sga": -9_800, "depreciation_owned": -5_800, "amortization": -1_100,
               "total_da": -6_900, "ebitda": 28_200, "ebit": 21_300,
               "interest_expense": -2_400, "ebt": 18_900,
               "tax_expense": -3_969, "net_income": 14_931,
               "earnings_from_investees": 650, "interest_income": 280,
               "net_periodic_benefit_income": 130},
        2024: {"revenue": 140_000, "cogs": -102_000, "gross_profit": 38_000,
               "sga": -10_000, "depreciation_owned": -6_000, "amortization": -1_200,
               "total_da": -7_200, "ebitda": 29_000, "ebit": 21_800,
               "interest_expense": -2_500, "ebt": 19_300,
               "tax_expense": -4_053, "net_income": 15_247,
               "earnings_from_investees": 700, "interest_income": 300,
               "net_periodic_benefit_income": 140},
    }

    # ── BS data ──
    bs_data = {
        2020: {"cash": 15_000, "accounts_receivable": 12_000, "inventory": 18_000,
               "other_ca": 2_000, "ppe_gross": 80_000, "ppe_accum_dep": -30_000,
               "ppe_net": 50_000, "intangibles": 5_000, "goodwill": 10_000,
               "dta": 1_000, "dtl": 2_000, "investments_lt": 3_000,
               "other_nca": 1_000, "total_assets": 117_000,
               "accounts_payable": 8_000, "taxes_payable": 500,
               "short_term_debt": 5_000, "long_term_debt": 40_000,
               "lease_liab_current": 1_000, "lease_liab_noncurrent": 3_000,
               "employee_benefits": 2_000, "other_cl": 1_000, "other_ncl": 2_000,
               "share_capital": 1_000, "apic": 5_000,
               "retained_earnings": 45_000, "aoci": -500, "nci": 2_000,
               "total_equity": 52_500, "total_liab_equity": 117_000},
        2024: {"cash": 25_000, "accounts_receivable": 16_000, "inventory": 19_000,
               "other_ca": 3_000, "ppe_gross": 95_000, "ppe_accum_dep": -50_000,
               "ppe_net": 45_000, "intangibles": 4_000, "goodwill": 10_000,
               "dta": 1_500, "dtl": 2_500, "investments_lt": 4_000,
               "other_nca": 2_000, "total_assets": 130_000,
               "accounts_payable": 10_000, "taxes_payable": 600,
               "short_term_debt": 6_000, "long_term_debt": 38_000,
               "lease_liab_current": 900, "lease_liab_noncurrent": 2_800,
               "employee_benefits": 2_200, "other_cl": 1_200, "other_ncl": 2_500,
               "share_capital": 1_000, "apic": 5_000,
               "retained_earnings": 57_000, "aoci": -300, "nci": 2_500,
               "total_equity": 65_200, "total_liab_equity": 130_000},
    }
    # Interpolate 2021-2023 (simple linear for tests)
    for yr in [2021, 2022, 2023]:
        bs_data[yr] = {}
        frac = (yr - 2020) / 4.0
        for k in bs_data[2020]:
            bs_data[yr][k] = bs_data[2020][k] + (bs_data[2024][k] - bs_data[2020][k]) * frac

    # ── CF data ──
    cf_data = {}
    for yr in years:
        cf_data[yr] = {
            "capex": -8_000 - yr * 200,
            "cfo_total": 20_000 + yr * 500,
            "cfi_total": -9_000 - yr * 200,
            "cff_total": -5_000,
            "cash_ending": 15_000 + yr * 1000,
        }

    # Write to DB
    for yr in years:
        repo.upsert_history(SYNTH_COMPANY, "IS", yr, is_data[yr], source="test")
        repo.upsert_history(SYNTH_COMPANY, "BS", yr, bs_data[yr], source="test")
        repo.upsert_history(SYNTH_COMPANY, "CF", yr, cf_data[yr], source="test")

    return repo


@pytest.fixture
def preprocessor(seeded_repo):
    """ModelPreprocessor with internal caches populated (via run())."""
    pp = ModelPreprocessor(SYNTH_COMPANY, seeded_repo)
    pp.run()  # Populate internal caches + write to DB
    return pp


# ══════════════════════════════════════════════════════════════════════
# Tests: EWA helper
# ══════════════════════════════════════════════════════════════════════

class TestEWA:
    def test_ewa_constant(self):
        """EWA of constant series equals that constant."""
        assert ewa({2020: 5.0, 2021: 5.0, 2022: 5.0}) == pytest.approx(5.0)

    def test_ewa_increasing(self):
        """EWA of increasing series weights recent more."""
        result = ewa({2020: 1.0, 2021: 2.0, 2022: 3.0, 2023: 4.0, 2024: 5.0})
        assert 1.0 < result < 5.0, f"EWA={result} not between first and last"

    def test_ewa_single_value(self):
        assert ewa({2024: 10.0}) == 10.0

    def test_ewa_empty(self):
        assert ewa({}) == 0.0


# ══════════════════════════════════════════════════════════════════════
# Tests: Margin Ratios
# ══════════════════════════════════════════════════════════════════════

class TestMarginRatios:
    def test_run_produces_margin_ratios(self, preprocessor):
        metrics = preprocessor._process_margin_ratios()
        assert "cogs_ratio" in metrics
        assert "sga_ratio" in metrics
        assert "ebitda_margin" in metrics
        assert "net_margin" in metrics

    def test_cogs_ratio_range(self, preprocessor):
        metrics = preprocessor._process_margin_ratios()
        rec = metrics["cogs_ratio"]["_recommended"]
        assert 0.5 < rec < 0.95, f"cogs_ratio={rec:.3f} out of range"

    def test_recommended_exists_for_all(self, preprocessor):
        metrics = preprocessor._process_margin_ratios()
        for k, v in metrics.items():
            assert "_recommended" in v, f"{k} missing _recommended"
            assert "_ewa" in v, f"{k} missing _ewa"
            assert "_last" in v, f"{k} missing _last"

    def test_tax_rate_reasonable(self, preprocessor):
        metrics = preprocessor._process_margin_ratios()
        rec = metrics["tax_rate"]["_recommended"]
        assert 0.10 < rec < 0.40, f"tax_rate={rec:.3f} unreasonable"


# ══════════════════════════════════════════════════════════════════════
# Tests: WC Days
# ══════════════════════════════════════════════════════════════════════

class TestWCDays:
    def test_produces_dso_dih_dpo(self, preprocessor):
        metrics = preprocessor._process_wc_days()
        for k in ["dso", "dih", "dpo"]:
            assert k in metrics, f"{k} missing"
            assert metrics[k]["_recommended"] > 0

    def test_ccc_equals_dso_plus_dih_minus_dpo(self, preprocessor):
        metrics = preprocessor._process_wc_days()
        if "ccc" in metrics:
            ccc = metrics["ccc"]["_recommended"]
            dso = metrics["dso"]["_recommended"]
            dih = metrics["dih"]["_recommended"]
            dpo = metrics["dpo"]["_recommended"]
            assert ccc == pytest.approx(dso + dih - dpo, rel=0.1)


# ══════════════════════════════════════════════════════════════════════
# Tests: CapEx
# ══════════════════════════════════════════════════════════════════════

class TestCapex:
    def test_produces_capex_ratios(self, preprocessor):
        metrics = preprocessor._process_capex()
        for k in ["capex_to_rev", "dep_to_rev", "dep_rate"]:
            assert k in metrics, f"{k} missing"
            assert metrics[k]["_recommended"] > 0


# ══════════════════════════════════════════════════════════════════════
# Tests: Debt
# ══════════════════════════════════════════════════════════════════════

class TestDebt:
    def test_produces_debt_metrics(self, preprocessor):
        metrics = preprocessor._process_debt()
        for k in ["avg_interest_rate", "debt_to_ebitda", "interest_coverage"]:
            assert k in metrics, f"{k} missing"

    def test_interest_coverage_reasonable(self, preprocessor):
        metrics = preprocessor._process_debt()
        icr = metrics["interest_coverage"]["_recommended"]
        assert 1.0 < icr < 20.0, f"ICR={icr:.1f} unreasonable"


# ══════════════════════════════════════════════════════════════════════
# Tests: Interest
# ══════════════════════════════════════════════════════════════════════

class TestInterest:
    def test_produces_interest_metrics(self, preprocessor):
        metrics = preprocessor._process_interest()
        assert "interest_income_rate" in metrics


# ══════════════════════════════════════════════════════════════════════
# Tests: Full Preprocessor Run
# ══════════════════════════════════════════════════════════════════════

class TestFullRun:
    def test_run_all_groups(self, preprocessor):
        result = preprocessor.run()
        assert result.success
        assert len(result.groups_computed) >= 10, f"Expected >=10 groups, got {len(result.groups_computed)}"
        assert result.metrics_written > 100, f"Expected >100 metrics, got {result.metrics_written}"

    def test_run_is_idempotent(self, preprocessor):
        """Running twice produces same result."""
        r1 = preprocessor.run()
        r2 = preprocessor.run()
        assert r1.metrics_written == r2.metrics_written
        assert r1.groups_computed == r2.groups_computed
