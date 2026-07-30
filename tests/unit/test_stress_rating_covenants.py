"""
Unit tests for stress, rating, and covenants modules.

Tests:
  - Rating scoring functions (leverage, coverage, profitability, liquidity)
  - Rating scale mapping (score → S&P, national RU)
  - Stress ShockSpec application
  - Stress sector packs structure
  - CreditMetrics computation from YearState
  - Integration: full pipeline with stress + rating + covenants
"""
import pytest
import logging

from engine.rating.core import (
    RatingEngine, RatingConfig, CreditMetrics,
    score_to_sp, score_to_moodys, intl_to_national,
    is_investment_grade, sp_to_numeric,
)
from engine.stress.core import ShockSpec, SECTOR_PACKS
from engine.model.inputs import YearState
from engine.constants import (
    RATING_DEFAULT_SCORE, RATING_INDUSTRY_ADJ_DEFAULT,
    RATING_SIZE_ADJ_DEFAULT,
)


# ── Rating Unit Tests ─────────────────────────────────────────────────────────


class TestScoreToRating:
    """Test score → rating conversion."""

    def test_aaa(self):
        assert score_to_sp(100) == "AAA"

    def test_d(self):
        assert score_to_sp(0) == "D"

    def test_bbb_range(self):
        r = score_to_sp(60)
        assert r in ("BBB+", "BBB", "BBB-", "A-")

    def test_moodys(self):
        r = score_to_moodys(100)
        assert r == "Aaa"

    def test_moodys_low(self):
        r = score_to_moodys(0)
        assert r == "C"


class TestNationalScale:
    """Test international → national RU mapping."""

    def test_sovereign_maps_to_aaa(self):
        assert intl_to_national("BBB+", "BBB+") == "AAA(RU)"

    def test_one_below_sovereign(self):
        assert intl_to_national("BBB", "BBB+") == "AA+(RU)"

    def test_ccc_maps_low(self):
        r = intl_to_national("CCC+", "BBB+")
        assert "(RU)" in r
        # CCC+ is ~10 notches below BBB+
        idx = ["AAA(RU)", "AA+(RU)", "AA(RU)", "AA-(RU)",
               "A+(RU)", "A(RU)", "A-(RU)",
               "BBB+(RU)", "BBB(RU)", "BBB-(RU)",
               "BB+(RU)", "BB(RU)", "BB-(RU)"].index(r) if r in [
            "AAA(RU)", "AA+(RU)", "AA(RU)", "AA-(RU)",
            "A+(RU)", "A(RU)", "A-(RU)",
            "BBB+(RU)", "BBB(RU)", "BBB-(RU)",
            "BB+(RU)", "BB(RU)", "BB-(RU)",
        ] else -1
        # Should be well below A range
        assert idx >= 7 or idx == -1

    def test_invalid_rating(self):
        assert intl_to_national("INVALID") == "NR(RU)"


class TestInvestmentGrade:
    """Test IG/HY classification."""

    def test_bbb_minus_is_ig(self):
        assert is_investment_grade("BBB-") is True

    def test_bb_plus_is_hy(self):
        assert is_investment_grade("BB+") is False

    def test_aaa_is_ig(self):
        assert is_investment_grade("AAA") is True

    def test_d_is_hy(self):
        assert is_investment_grade("D") is False


class TestSpToNumeric:
    """Test S&P → numeric conversion."""

    def test_aaa(self):
        assert sp_to_numeric("AAA") == 1

    def test_d(self):
        assert sp_to_numeric("D") == 22

    def test_unknown(self):
        assert sp_to_numeric("INVALID") == 15  # default B+


class TestRatingEngine:
    """Test RatingEngine scoring functions."""

    @pytest.fixture
    def engine(self):
        return RatingEngine(RatingConfig(
            industry_adjustment=0.0,
            size_adjustment=0.0,
            cycle_avg_ebitda_margin=0.12,
        ))

    def test_leverage_strong(self, engine):
        m = CreditMetrics(year=2026, net_debt_ebitda=1.0, debt_to_equity=0.5)
        score = engine.score_leverage(m)
        assert score > 60  # BBB territory

    def test_leverage_weak(self, engine):
        m = CreditMetrics(year=2026, net_debt_ebitda=8.0, debt_to_equity=4.0)
        score = engine.score_leverage(m)
        assert score < 20  # CCC territory

    def test_leverage_negative_nd(self, engine):
        m = CreditMetrics(year=2026, net_debt_ebitda=-1.0)
        score = engine.score_leverage(m)
        assert score > 80  # net cash position

    def test_coverage_strong(self, engine):
        m = CreditMetrics(year=2026, ebitda_coverage=8.0, interest_coverage=6.0)
        score = engine.score_coverage(m)
        assert score > 60

    def test_coverage_weak(self, engine):
        m = CreditMetrics(year=2026, ebitda_coverage=0.5, interest_coverage=0.3)
        score = engine.score_coverage(m)
        assert score < 10

    def test_profitability_strong(self, engine):
        m = CreditMetrics(year=2026, ebitda_margin=0.25, roa=0.10)
        score = engine.score_profitability(m)
        assert score > 60

    def test_profitability_negative(self, engine):
        m = CreditMetrics(year=2026, ebitda_margin=-0.05, roa=-0.03)
        score = engine.score_profitability(m)
        assert score < 15

    def test_liquidity_strong(self, engine):
        m = CreditMetrics(year=2026, current_ratio=3.0, cash_to_debt=0.40)
        score = engine.score_liquidity(m)
        assert score > 70

    def test_no_data_returns_default(self, engine):
        m = CreditMetrics(year=2026)
        for fn in [engine.score_leverage, engine.score_coverage,
                   engine.score_profitability, engine.score_liquidity]:
            assert fn(m) == RATING_DEFAULT_SCORE

    def test_calculate_full(self, engine):
        m = CreditMetrics(
            year=2026,
            net_debt_ebitda=2.0, debt_to_equity=0.8,
            ebitda_coverage=5.0, interest_coverage=4.0,
            ebitda_margin=0.15, roa=0.06,
            current_ratio=1.8, cash_to_debt=0.20,
            revenue=10e9, ebitda=1.5e9,
        )
        result = engine.calculate(m)
        assert "score" in result
        assert "rating" in result
        assert 0 <= result["score"] <= 100
        assert result["rating"] in ["AAA", "AA+", "AA", "AA-",
                                     "A+", "A", "A-",
                                     "BBB+", "BBB", "BBB-",
                                     "BB+", "BB", "BB-",
                                     "B+", "B", "B-",
                                     "CCC+", "CCC", "CCC-",
                                     "CC", "C", "D"]

    def test_industry_adj_lowers_score(self):
        eng_no_adj = RatingEngine(RatingConfig(industry_adjustment=0.0, size_adjustment=0.0))
        eng_with_adj = RatingEngine(RatingConfig(
            industry_adjustment=RATING_INDUSTRY_ADJ_DEFAULT,
            size_adjustment=RATING_SIZE_ADJ_DEFAULT,
        ))
        m = CreditMetrics(
            year=2026, net_debt_ebitda=2.5, ebitda_coverage=4.0,
            ebitda_margin=0.12, current_ratio=1.5,
        )
        r1 = eng_no_adj.calculate(m)
        r2 = eng_with_adj.calculate(m)
        assert r2["score"] < r1["score"]  # industry adj is negative


class TestCreditMetricsFromYearState:
    """Test CreditMetrics.from_year_state()."""

    def test_basic_computation(self):
        state = YearState(
            year=2026,
            revenue=10e9, ebitda=1.5e9, ebit=1.0e9,
            net_income=500e6,
            interest_expense=-200e6,
            short_term_debt=1e9, long_term_debt=4e9,
            cash=500e6,
            total_assets=15e9, total_equity=5e9,
            total_ca=3e9, total_cl=2e9,
            cfo_total=1.2e9, cfi_capex=-800e6,
        )
        m = CreditMetrics.from_year_state(state, 2026)
        assert m.net_debt_ebitda == pytest.approx(3.0, rel=0.01)
        assert m.ebitda_margin == pytest.approx(0.15, rel=0.01)
        assert m.current_ratio == pytest.approx(1.5, rel=0.01)
        assert m.ebitda_coverage == pytest.approx(7.5, rel=0.01)


# ── Stress Unit Tests ─────────────────────────────────────────────────────────


class TestShockSpec:
    """Test ShockSpec.apply()."""

    def test_percentage_shock(self):
        shock = ShockSpec(factor="lme_al", shock_type="percentage", value=-25.0)
        result = shock.apply(2000.0, 2026, 2025)
        assert result == pytest.approx(1500.0, rel=0.01)

    def test_absolute_shock(self):
        shock = ShockSpec(factor="rate", shock_type="absolute", value=0.02)
        result = shock.apply(0.05, 2026, 2025)
        assert result == pytest.approx(0.07, rel=0.01)

    def test_pp_shock(self):
        shock = ShockSpec(factor="rate", shock_type="pp", value=2.0)
        result = shock.apply(0.05, 2026, 2025)
        assert result == pytest.approx(0.07, rel=0.01)


class TestSectorPacks:
    """Test sector pack structure."""

    def test_packs_exist(self):
        assert len(SECTOR_PACKS) >= 3

    def test_metals_mining_has_shocks(self):
        pack = SECTOR_PACKS["metals_mining"]
        assert "macro_shocks" in pack
        assert "driver_shocks" in pack
        assert len(pack["macro_shocks"]) > 0

    def test_all_packs_have_description(self):
        for name, pack in SECTOR_PACKS.items():
            assert "description" in pack, f"Pack {name} missing description"


# ── Integration: Stress + Rating + Covenants ──────────────────────────────────


@pytest.mark.slow
class TestStressRatingIntegration:
    """Integration test: full pipeline with stress + rating + covenants."""

    @pytest.fixture(autouse=True)
    def setup(self):
        logging.basicConfig(level=logging.WARNING)

    def test_rusal_stress_rating_covenants(self):
        """Run Rusal with stress, rating, and covenants enabled."""
        from engine.orchestrator import build_model

        result = build_model(
            company_id="rusal",
            run_preprocessor=False,
            run_model=True,
            run_stress=True,
            run_rating=True,
            run_covenants=True,
            log_level=logging.WARNING,
        )
        assert result.success, f"Errors: {result.errors[:3]}"

        # Stress must complete for all scenarios
        assert result.stress_results is not None
        assert len(result.stress_results) > 0
        for name, sr in result.stress_results.items():
            assert sr.success, f"Stress {name} failed"
            # BS balance in stress scenarios
            for yr, diff in sr.bs_diffs.items():
                assert diff < 1_000, (
                    f"Stress {name} {yr}: BS diff={diff:.0f}"
                )

        # Rating must produce results
        assert result.rating_result is not None
        assert result.rating_result.success
        assert len(result.rating_result.ratings) > 0
        for yr, r in result.rating_result.ratings.items():
            assert "rating" in r
            assert "score" in r
            assert 0 <= r["score"] <= 100

        # Covenants must run without error
        assert result.covenants_result is not None
