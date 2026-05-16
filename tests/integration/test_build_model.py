"""
Integration tests: build_model() for all supported companies.

Tests the full pipeline: preprocessor → macro → model.
Verifies:
  - No errors
  - BS and CF balance within tolerance
  - All forecast years produce output
  - Revenue and assets are positive and reasonable
"""
import pytest
import logging

from engine.orchestrator import build_model


@pytest.mark.slow
class TestBuildModel:
    """Run full pipeline for each company."""

    @pytest.fixture(autouse=True)
    def setup(self):
        logging.basicConfig(level=logging.WARNING)

    def test_build_us_steel(self):
        """US Steel: full pipeline, verify BS/CF balance."""
        result = build_model(
            company_id="us_steel",
            run_preprocessor=True,
            run_macro=True,
            run_model=True,
            run_stress=False,
            log_level=logging.WARNING,
        )
        self._verify_result(result, "us_steel")

    def test_build_rusal(self):
        """RUSAL: full pipeline, verify BS/CF balance."""
        result = build_model(
            company_id="rusal",
            run_preprocessor=True,
            run_macro=True,
            run_model=True,
            run_stress=False,
            log_level=logging.WARNING,
        )
        self._verify_result(result, "rusal")

    def _verify_result(self, result, company_id):
        assert result.success, f"{company_id}: errors={result.errors[:3]}"

        # Preprocessor must produce metrics
        assert result.preprocess_result is not None
        assert result.preprocess_result.success
        assert result.preprocess_result.metrics_written > 0, "No preprocess metrics"

        # Macro must produce forecasts
        assert result.macro_result is not None
        assert len(result.macro_result.factors_forecast) > 0, "No macro factors"

        # Model must produce forecast years
        assert result.model_result is not None
        assert result.model_result.success
        years = result.model_result.years
        assert len(years) >= 3, f"Expected >=3 forecast years, got {len(years)}"

        # BS Identity: max diff < $1K per year
        for yr, diff in result.model_result.bs_diffs.items():
            assert diff < 1_000, f"{company_id} {yr}: BS diff={diff:.0f} exceeds $1K tolerance"

        # CF Bridge: max diff < $1K per year
        for yr, diff in result.model_result.cf_diffs.items():
            assert diff < 1_000, f"{company_id} {yr}: CF diff={diff:.0f} exceeds $1K tolerance"

        # Sanity checks on forecast values
        for yr, state in years.items():
            assert state.revenue > 0, f"{company_id} {yr}: revenue <= 0"
            assert state.total_assets > 0, f"{company_id} {yr}: total_assets <= 0"
            assert state.total_equity > 0, f"{company_id} {yr}: total_equity <= 0"
            # Net income can be negative in stress, but not in base
            # (allow small negative for cyclical downturn)
            assert state.net_income > -1e9, f"{company_id} {yr}: net_income unreasonably negative"


class TestBuildModelQuick:
    """Quick checks that don't run the full model."""

    def test_companies_exist(self, repo):
        """Both companies must be in the DB."""
        companies = repo.query("SELECT company_id FROM companies")
        ids = {r["company_id"] for r in companies}
        assert "us_steel" in ids, "us_steel not in DB"
        assert "rusal" in ids, "rusal not in DB"

    def test_history_not_empty(self, repo):
        """Each company must have IS/BS/CF history."""
        for cid in ["us_steel", "rusal"]:
            for stmt in ["IS", "BS", "CF"]:
                data = repo.get_history(cid, stmt)
                assert len(data) >= 3, f"{cid} {stmt}: expected >=3 years, got {len(data)}"

    def test_configs_exist(self, project_root):
        """Each company must have a project.yaml."""
        for cid in ["us_steel", "rusal"]:
            cfg = project_root / "companies" / cid / "configs" / "project.yaml"
            assert cfg.exists(), f"{cid}: project.yaml not found at {cfg}"
