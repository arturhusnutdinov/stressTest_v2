"""
Unit tests for ModelInputLoader — validates HistoricState + ModelConfig loading.
"""
import pytest
from pathlib import Path
from engine.database.repository import Repository
from engine.model.loader import ModelInputLoader
from engine.model.inputs import HistoricState, ModelConfig, YearState


# ══════════════════════════════════════════════════════════════════════

class TestModelInputLoader:
    """Tests against real DB for both companies."""

    def test_load_us_steel(self, repo):
        """US Steel: loader returns valid HistoricState + ModelConfig."""
        loader = ModelInputLoader("us_steel", repo)
        historic, config = loader.load()

        assert isinstance(historic, HistoricState)
        assert isinstance(config, ModelConfig)

        # History
        assert historic.company_id == "us_steel"
        assert len(historic.years) >= 10, f"Expected >=10 years, got {len(historic.years)}"
        assert historic.base_year >= 2020

        # IS data
        assert len(historic.is_data) >= 5
        assert "revenue" in historic.is_data.get(historic.base_year, {})

        # BS data
        assert len(historic.bs_data) >= 5
        assert "total_assets" in historic.bs_data.get(historic.base_year, {})

        # Config
        assert config.company_id == "us_steel"
        assert config.forecast_start_year > config.history_end_year
        assert len(config.forecast_years) >= 3

    def test_load_rusal(self, repo):
        """RUSAL: loader returns valid HistoricState + ModelConfig."""
        loader = ModelInputLoader("rusal", repo)
        historic, config = loader.load()

        assert historic.company_id == "rusal"
        assert len(historic.years) >= 10
        assert historic.base_year >= 2023
        assert len(historic.is_data) >= 5
        assert config.forecast_start_year > config.history_end_year

    def test_base_year_state(self, repo):
        """Base year state is built correctly from history."""
        loader = ModelInputLoader("us_steel", repo)
        historic, config = loader.load()

        base = historic.base_year_state
        assert base is not None
        assert isinstance(base, YearState)
        assert base.year == historic.base_year

        # Core fields populated
        assert base.revenue > 0, "base year revenue <= 0"
        assert base.total_assets > 0, "base year total_assets <= 0"
        assert base.total_equity > 0, "base year total_equity <= 0"

        # BS balance check
        ta, tle, diff = base.bs_check()
        assert diff < 1_000, f"Base year BS diff={diff:.0f} exceeds $1K"

    def test_debt_instruments_loaded(self, repo):
        """Debt instruments are loaded from DB."""
        loader = ModelInputLoader("us_steel", repo)
        historic, _ = loader.load()

        assert len(historic.debt_instruments) > 0, "No debt instruments loaded"
        for inst in historic.debt_instruments:
            assert inst.instrument_id
            assert inst.db_type in ("bond_fixed", "bond_float", "term_bullet",
                                     "term_amort", "revolving", "other",
                                     "finance_lease"), f"Unknown db_type: {inst.db_type}"

    def test_macro_forecasts_loaded(self, repo):
        """Macro forecasts are loaded from DB."""
        loader = ModelInputLoader("us_steel", repo)
        historic, _ = loader.load()

        assert len(historic.macro_forecasts) > 0, "No macro forecasts loaded"

    def test_preprocess_loaded(self, repo):
        """Preprocess metrics are loaded from DB."""
        loader = ModelInputLoader("us_steel", repo)
        historic, _ = loader.load()

        assert len(historic.preprocess) >= 5, \
            f"Expected >=5 preprocess groups, got {len(historic.preprocess)}"
        assert "margin_ratios" in historic.preprocess

    def test_drivers_filled(self, repo):
        """Drivers (cogs_pct, sga_pct, dso_days, etc.) are filled from preprocessor."""
        loader = ModelInputLoader("us_steel", repo)
        _, config = loader.load()

        assert config.cogs_pct is not None and 0.5 < config.cogs_pct < 1.0
        assert config.sga_pct is not None and 0.01 < config.sga_pct < 0.30
        assert config.tax_rate is not None and 0.10 < config.tax_rate < 0.40

    def test_forecast_years_range(self, repo):
        """Forecast years are consecutive integers."""
        loader = ModelInputLoader("us_steel", repo)
        _, config = loader.load()

        years = config.forecast_years
        assert years == list(range(years[0], years[-1] + 1)), \
            f"Forecast years not consecutive: {years}"
