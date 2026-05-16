"""
Unit tests for ThreeStatementModel core solver.

Validates:
  - Revenue forecast produces positive values
  - BS identity after each forecast year
  - CF bridge integrity
  - Key financial ratios are reasonable
"""
import pytest
import logging
from pathlib import Path
from engine.model.loader import ModelInputLoader
from engine.model.core import ThreeStatementModel
from engine.model.inputs import YearState


@pytest.fixture(autouse=True)
def quiet():
    logging.basicConfig(level=logging.WARNING)


def _cfg(company_id):
    from engine import ROOT
    return ROOT / "companies" / company_id / "configs" / "project.yaml"


@pytest.fixture
def us_steel_inputs(repo):
    loader = ModelInputLoader("us_steel", repo, config_path=_cfg("us_steel"))
    return loader.load()


@pytest.fixture
def rusal_inputs(repo):
    loader = ModelInputLoader("rusal", repo, config_path=_cfg("rusal"))
    return loader.load()


# ══════════════════════════════════════════════════════════════════════

class TestThreeStatementModel:
    """Core model tests for both companies."""

    def test_run_us_steel(self, us_steel_inputs):
        """US Steel: model runs and produces BS/CF balance."""
        historic, config = us_steel_inputs
        model = ThreeStatementModel(historic, config)
        result = model.run()

        assert result.success, f"Errors: {result.errors}"
        assert len(result.years) >= 3

        for yr, diff in result.bs_diffs.items():
            assert diff < 1_000, f"US Steel {yr}: BS diff={diff:.0f}"

        for yr, diff in result.cf_diffs.items():
            assert diff < 1_000, f"US Steel {yr}: CF diff={diff:.0f}"

    def test_run_rusal(self, rusal_inputs):
        """RUSAL: model runs and produces BS/CF balance."""
        historic, config = rusal_inputs
        model = ThreeStatementModel(historic, config)
        result = model.run()

        assert result.success, f"Errors: {result.errors}"
        assert len(result.years) >= 3

        for yr, diff in result.bs_diffs.items():
            assert diff < 1_000, f"RUSAL {yr}: BS diff={diff:.0f}"

        for yr, diff in result.cf_diffs.items():
            assert diff < 1_000, f"RUSAL {yr}: CF diff={diff:.0f}"


class TestForecastSanity:
    """Sanity checks on forecast results."""

    def test_revenue_grows(self, us_steel_inputs):
        """Revenue should be positive and reasonable."""
        historic, config = us_steel_inputs
        model = ThreeStatementModel(historic, config)
        result = model.run()

        for yr, state in sorted(result.years.items()):
            assert state.revenue > 0, f"{yr}: revenue <= 0"
            # Revenue shouldn't grow/shrink by more than 50% per year
            if yr > min(result.years):
                prev_yr = yr - 1
                if prev_yr in result.years:
                    prev_rev = result.years[prev_yr].revenue
                    change = abs(state.revenue / prev_rev - 1)
                    assert change < 0.50, f"{yr}: revenue changed {change:.0%}"

    def test_ebitda_positive(self, us_steel_inputs):
        """EBITDA must be positive (base scenario)."""
        historic, config = us_steel_inputs
        model = ThreeStatementModel(historic, config)
        result = model.run()

        for yr, state in result.years.items():
            assert state.ebitda > 0, f"{yr}: EBITDA={state.ebitda:.0f} <= 0"

    def test_assets_grow_with_revenue(self, us_steel_inputs):
        """Total assets should be > 0 and correlate with revenue."""
        historic, config = us_steel_inputs
        model = ThreeStatementModel(historic, config)
        result = model.run()

        for yr, state in result.years.items():
            assert state.total_assets > 0, f"{yr}: total_assets <= 0"
            # Asset turnover between 0.1x and 3x
            turnover = state.revenue / state.total_assets
            assert 0.1 < turnover < 3.0, f"{yr}: asset turnover={turnover:.2f}"

    def test_debt_not_exploding(self, us_steel_inputs):
        """Net debt / EBITDA should be reasonable."""
        historic, config = us_steel_inputs
        model = ThreeStatementModel(historic, config)
        result = model.run()

        for yr, state in result.years.items():
            total_debt = abs(state.short_term_debt or 0) + abs(state.long_term_debt or 0)
            ebitda = abs(state.ebitda or 1)
            leverage = total_debt / ebitda
            assert leverage < 15.0, f"{yr}: Debt/EBITDA={leverage:.1f}x unreasonably high"


class TestYearState:
    """Unit tests for YearState dataclass."""

    def test_to_dict(self):
        state = YearState(year=2025, revenue=1000, cogs=-600, net_income=200)
        d = state.to_dict()
        assert d["revenue"] == 1000
        assert d["cogs"] == -600
        assert d["net_income"] == 200
        assert "year" not in d  # year is excluded

    def test_bs_check_balanced(self):
        state = YearState(year=2025, total_assets=1000, total_liab_equity=1000)
        ta, tle, diff = state.bs_check()
        assert diff == 0

    def test_bs_check_imbalanced(self):
        state = YearState(year=2025, total_assets=1000, total_liab_equity=900)
        ta, tle, diff = state.bs_check()
        assert diff == 100

    def test_cf_bridge_check(self):
        state = YearState(year=2025, cf_cash_opening=100, cf_net_change=50,
                          cf_cash_ending=150)
        exp, act, diff = state.cf_bridge_check()
        assert diff == 0

    def test_cf_bridge_broken(self):
        state = YearState(year=2025, cf_cash_opening=100, cf_net_change=50,
                          cf_cash_ending=200)
        exp, act, diff = state.cf_bridge_check()
        assert diff == 50
