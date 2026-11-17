"""
Unit tests for sanity bounds — fail-fast adequacy gates (AUDIT_ADEQUACY §3.3).

Проверяет engine/model/core.py::_sanity_checks:
  - interest/revenue > порога → нарушение
  - debt/revenue > порога → нарушение
  - |Δdebt|/debt_prev > порога → нарушение
  - денормалы (non-finite, |x| > sanity_abs_max) → нарушение
  - адекватное состояние → пустой список
"""
import pytest

from engine.model.core import ThreeStatementModel
from engine.model.inputs import ModelConfig, YearState


def _make_model(sanity_mode: str = "fail", **cfg_kw) -> ThreeStatementModel:
    """Модель без полного __init__ — тестируем только _sanity_checks (использует self._c)."""
    config = ModelConfig(company_id="test", sanity_mode=sanity_mode, **cfg_kw)
    model = ThreeStatementModel.__new__(ThreeStatementModel)
    model._c = config
    return model


def _state(year=2026, revenue=10_000e6, interest=500e6, debt=5_000e6,
           cash=1_000e6, ta=20_000e6) -> YearState:
    return YearState(year=year, revenue=revenue, interest_expense=interest,
                     total_debt=debt, cash=cash, total_assets=ta)


class TestSanityBounds:
    """Гейты adequacy: тождества не ловят «согласованно-безумное» решение."""

    def test_ok_state_no_issues(self):
        model = _make_model()
        issues = model._sanity_checks(_state(), _state(year=2025, debt=4_800e6))
        assert issues == []

    def test_interest_revenue_exceeded(self):
        model = _make_model()
        # interest = 60% выручки (порог 50%) — как взрыв на усечённой БД
        issues = model._sanity_checks(
            _state(interest=6_000e6, revenue=10_000e6),
            _state(year=2025),
        )
        assert any("interest/revenue" in i for i in issues)

    def test_debt_revenue_exceeded(self):
        model = _make_model()
        issues = model._sanity_checks(
            _state(debt=120_000e6, ta=130_000e6),  # 12× выручки (порог 10)
            _state(year=2025),
        )
        assert any("debt/revenue" in i for i in issues)

    def test_debt_growth_exceeded(self):
        model = _make_model()
        # долг вырос в 3 раза за год (порог 100%)
        issues = model._sanity_checks(
            _state(debt=15_000e6, ta=30_000e6),
            _state(year=2025, debt=5_000e6),
        )
        assert any("d_debt" in i for i in issues)

    def test_denormal_rejected(self):
        model = _make_model()
        issues = model._sanity_checks(
            _state(revenue=float("inf")),
            _state(year=2025),
        )
        assert any("revenue" in i for i in issues)

    def test_huge_values_rejected(self):
        model = _make_model()
        issues = model._sanity_checks(
            _state(cash=5.6e15, ta=5.6e15),  # STD=5.6e15 из эксперимента §3.3
            _state(year=2025),
        )
        assert any("cash_close" in i for i in issues)

    def test_thresholds_configurable(self):
        model = _make_model(sanity_interest_rev_max=0.70)
        issues = model._sanity_checks(
            _state(interest=6_000e6, revenue=10_000e6),
            _state(year=2025),
        )
        assert issues == []  # 60% < 70% — проходит

    def test_zero_revenue_skips_ratios(self):
        model = _make_model()
        issues = model._sanity_checks(_state(revenue=0.0), _state(year=2025, debt=0.0))
        # ratio-проверки пропускаются при нулевой базе; денормал-guard не срабатывает на 0
        assert issues == []
