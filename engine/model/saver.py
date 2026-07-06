"""
ModelSaver — сохраняет результаты модели в БД.
Записывает YearState → forecast_is/bs/cf через Repository.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from ..database.repository import Repository
from .inputs import ModelConfig, YearState
from .core import ModelResult

logger = logging.getLogger(__name__)

# Маппинг полей YearState → канонические имена метрик в БД
IS_METRICS = {
    "revenue":                    "revenue",
    "cogs":                       "cogs",
    "gross_profit":               "gross_profit",
    "sga":                        "sga",
    "dep_ppe":                    "depreciation_owned",
    "dep_rou":                    "depreciation_rou",
    "amort_intangibles":          "amortization",
    "total_da":                   "total_da",
    "ebitda":                     "ebitda",
    "asset_impairment":           "asset_impairment_charges",
    "restructuring":              "restructuring_and_other_charges",
    "other_losses_gains":         "other_losses_gains_net",
    "earnings_from_investees":    "earnings_from_investees",
    "net_periodic_benefit":       "net_periodic_benefit_income",
    "ebit":                       "ebit",
    "interest_expense_debt":      "interest_expense_debt",
    "interest_expense_leases":    "lease_interest",
    "interest_expense":           "interest_expense",
    "interest_income":            "interest_income",
    "loss_on_debt_extinguishment":"loss_on_debt_extinguishment",
    "other_financial_costs":      "other_financial_costs",
    "ebt":                        "ebt",
    "tax_expense":                "tax_expense",
    "net_income":                 "net_income",
    "eps_basic":                  "eps_basic",
    "eps_diluted":                "eps_diluted",
    "distribution_expenses":      "distribution_expenses",
    "admin_expenses":             "administrative_expenses",
    "ecl_expenses":               "expected_credit_losses",
    "other_opex":                 "other_operating_expenses",
    "cfo_stock_compensation":     "cfo_stock_compensation",
    "current_tax":                "current_tax_expense",
    "deferred_tax":               "deferred_tax_expense",
}

BS_METRICS = {
    "cash":                       "cash",
    "restricted_cash":            "restricted_cash",
    "accounts_receivable":        "accounts_receivable",
    "inventory":                  "inventory",
    "other_ca":                   "other_current_assets",
    "total_ca":                   "total_current_assets",
    "ppe_gross":                  "ppe_gross",
    "ppe_accum_dep":              "ppe_accum_dep",
    "ppe_net":                    "ppe_net",
    "rou_asset":                  "rou_asset",
    "intangibles":                "intangibles",
    "goodwill":                   "goodwill",
    "investments_lt":             "investments_and_long_term_receivables",
    "dta":                        "dta",
    "other_nca":                  "other_non_current_assets",
    "total_nca":                  "total_non_current_assets",
    "total_assets":               "total_assets",
    "short_term_debt":            "short_term_debt",
    "accounts_payable":           "accounts_payable",
    "payroll_payable":            "payroll_and_benefits_payable",
    "taxes_payable":              "taxes_payable",
    "interest_payable":           "interest_payable",
    "lease_liab_current":         "lease_liab_current",
    "other_cl":                   "other_current_liabilities",
    "total_cl":                   "total_current_liabilities",
    "long_term_debt":             "long_term_debt",
    "lease_liab_noncurrent":      "lease_liab_noncurrent",
    "employee_benefits":          "employee_benefits",
    "dtl":                        "dtl",
    "other_ncl":                  "other_non_current_liabilities",
    "total_ncl":                  "total_non_current_liabilities",
    "total_liabilities":          "total_liabilities",
    "share_capital":              "share_capital",
    "apic":                       "apic",
    "treasury_stock":             "treasury_stock",
    "retained_earnings":          "retained_earnings",
    "aoci":                       "aoci",
    "nci":                        "nci",
    "total_equity":               "total_equity",
    "total_liab_equity":          "total_liab_equity",
    "finance_lease_asset":        "finance_lease_asset_net",
    "finance_lease_liab_current": "finance_lease_liab_current",
    "finance_lease_liab_noncurrent": "finance_lease_liab_noncurrent",
    "ppe_net_ex_lease":           "ppe_net_ex_lease",
    "accrued_liabilities":        "accrued_liabilities",
    "accounts_payable_rp":        "accounts_payable_related_parties",
    "deferred_credits":           "deferred_credits",
}

CF_METRICS = {
    "cfo_net_income":             "net_income",
    "cfo_total_da":               "total_da",
    "cfo_deferred_tax":           "deferred_income_taxes",
    "cfo_change_ar":              "wc_accounts_receivable_change",
    "cfo_change_inv":             "wc_inventory_change",
    "cfo_change_ap":              "wc_accounts_payable_change",
    "cfo_wc_delta":               "wc_delta",
    "cfo_interest_paid":          "interest_paid",
    "cfo_taxes_paid":             "taxes_paid",
    "cfo_other":                  "cfo_other",
    "cfo_total":                  "cfo_total",
    "cfi_capex":                  "capex",
    "cfi_disposal_proceeds":      "disposal_proceeds",
    "cfi_acquisitions":           "acquisitions",
    "cfi_other":                  "cfi_other",
    "cfi_total":                  "cfi_total",
    "cff_debt_issuance":          "debt_issuance",
    "cff_debt_repayment":         "debt_repayments",
    "cff_revolver_draws":         "cff_borrowings",
    "cff_revolver_repayments":    "cff_repayments",
    "cff_dividends":              "dividends_paid",
    "cff_buybacks":               "cff_share_repurchases",
    "cff_equity_issuance":        "cff_equity_issuance",
    "cff_other":                  "cff_other",
    "cff_total":                  "cff_total",
    "cf_fx_effect":               "cf_fx_effect",
    "cf_net_change":              "net_change",
    "cf_cash_opening":            "cash_opening",
    "cf_cash_ending":             "cash_ending",
    "cfo_change_other_wc":        "change_other_wc",
    "cfo_lease_payments_operating": "lease_payments_cfo",
    "cfo_stock_comp":             "cfo_stock_compensation",
    "cff_finance_lease_principal": "fin_lease_principal_cff",
}


class ModelSaver:
    """Сохраняет ModelResult в БД."""

    def __init__(
        self,
        company_id: str,
        repo: Repository,
        config: ModelConfig,
    ) -> None:
        self.company_id = company_id
        self._repo = repo
        self._config = config

    def save(self, result: ModelResult) -> int:
        """
        Сохранить все прогнозные годы в forecast_is/bs/cf.
        Возвращает общее количество записанных строк.
        """
        if not result.success:
            logger.warning("ModelResult содержит ошибки — сохранение отменено")
            return 0

        scenario_id = self._repo.ensure_scenario(
            self.company_id,
            self._config.scenario_name,
            type_=self._config.scenario_name,
        )
        version_id = self._get_or_create_version()

        # Удаляем прогнозы за годы ДО forecast_start (стейл от предыдущих прогонов)
        forecast_start = self._config.forecast_start_year
        self._cleanup_stale_forecasts(scenario_id, forecast_start)

        total = 0
        for year, state in sorted(result.years.items()):
            total += self._save_year(year, state, scenario_id, version_id)

        # Сохраняем прогнозный долговой график (по инструментам × год)
        if getattr(result, "debt_lines", None):
            self._save_debt_schedule(result.debt_lines)

        logger.info(
            f"Сохранено: {self.company_id} сценарий={self._config.scenario_name} "
            f"лет={len(result.years)} строк={total}"
        )

        # Аудит
        self._repo.log(
            operation="MODEL_RUN",
            company_id=self.company_id,
            details={
                "scenario": self._config.scenario_name,
                "years": list(result.years.keys()),
                "rows": total,
                "bs_max_diff": max(result.bs_diffs.values()) if result.bs_diffs else 0,
                "cf_max_diff": max(result.cf_diffs.values()) if result.cf_diffs else 0,
            },
        )
        return total

    def _save_year(
        self,
        year: int,
        state: YearState,
        scenario_id: int,
        version_id: Optional[int],
    ) -> int:
        state_dict = state.to_dict()
        n = 0

        # IS
        is_metrics = {
            canonical: state_dict[field_name]
            for field_name, canonical in IS_METRICS.items()
            if field_name in state_dict and state_dict[field_name] is not None
        }
        n += self._repo.upsert_forecast(
            self.company_id, "IS", year, scenario_id,
            is_metrics, version_id=version_id,
        )

        # BS
        bs_metrics = {
            canonical: state_dict[field_name]
            for field_name, canonical in BS_METRICS.items()
            if field_name in state_dict and state_dict[field_name] is not None
        }
        n += self._repo.upsert_forecast(
            self.company_id, "BS", year, scenario_id,
            bs_metrics, version_id=version_id,
        )

        # CF
        cf_metrics = {
            canonical: state_dict[field_name]
            for field_name, canonical in CF_METRICS.items()
            if field_name in state_dict and state_dict[field_name] is not None
        }
        n += self._repo.upsert_forecast(
            self.company_id, "CF", year, scenario_id,
            cf_metrics, version_id=version_id,
        )

        return n

    def _save_debt_schedule(self, debt_lines_by_year: Dict) -> None:
        """
        Записывает прогнозный долговой график в таблицу debt_schedule.
        Одна строка на инструмент × год (period_id берётся из таблицы periods).

        Before upserting, deletes stale model_forecast rows for each forecast year
        so that instruments removed from the current instrument set don't persist
        from previous runs (prevents double-counting).
        """
        try:
            # Clean stale forecast entries before writing
            for year in sorted(debt_lines_by_year.keys()):
                row_period = self._repo.query_one(
                    "SELECT period_id FROM periods WHERE company_id=? AND year=?",
                    (self.company_id, year),
                )
                if row_period is not None:
                    self._repo.execute(
                        "DELETE FROM debt_schedule "
                        "WHERE company_id=? AND period_id=? AND source='model_forecast'",
                        (self.company_id, row_period["period_id"]),
                    )

            for year, lines in sorted(debt_lines_by_year.items()):
                row_period = self._repo.query_one(
                    "SELECT period_id FROM periods WHERE company_id=? AND year=?",
                    (self.company_id, year),
                )
                if row_period is None:
                    logger.warning(f"  debt_schedule: period_id not found for year={year}, skipping")
                    continue
                period_id = row_period["period_id"]
                for ln in lines:
                    self._repo.execute(
                        """
                        INSERT INTO debt_schedule
                            (company_id, period_id, instrument_id, instrument_name,
                             opening_balance, draw, repay_mandatory, repay_voluntary,
                             interest_expense, interest_paid, closing_balance,
                             interest_rate, classification, source, updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
                        ON CONFLICT(company_id, period_id, instrument_id) DO UPDATE SET
                            opening_balance=excluded.opening_balance,
                            draw=excluded.draw,
                            repay_mandatory=excluded.repay_mandatory,
                            repay_voluntary=excluded.repay_voluntary,
                            interest_expense=excluded.interest_expense,
                            interest_paid=excluded.interest_paid,
                            closing_balance=excluded.closing_balance,
                            interest_rate=excluded.interest_rate,
                            classification=excluded.classification,
                            source=excluded.source,
                            updated_at=CURRENT_TIMESTAMP
                        """,
                        (
                            self.company_id,
                            period_id,
                            ln.instrument_id,
                            ln.name,
                            ln.opening,
                            ln.draw + ln.refi_draw,     # total draw incl refi
                            ln.mandatory,                # scheduled repayment
                            ln.repay - ln.mandatory,     # voluntary / optimizer repayment
                            ln.interest,
                            ln.interest,                 # interest_paid = interest (accrual=cash here)
                            ln.closing,
                            None,                        # rate not stored per-line (on instrument)
                            "ST" if ln.is_st else "LT",
                            "model_forecast",
                        ),
                    )
            logger.debug(
                f"  debt_schedule: saved forecast lines for {len(debt_lines_by_year)} years"
            )
        except Exception as e:
            logger.warning(f"  debt_schedule save failed: {e}")

    def _cleanup_stale_forecasts(self, scenario_id: int, forecast_start: int) -> None:
        """
        Удаляет прогнозные строки за годы < forecast_start.

        При смене history_end_year (напр. 2024→2025) старые прогнозы за 2025
        остаются в БД и конфликтуют с актуальными данными.
        """
        tables = ["forecast_is", "forecast_bs", "forecast_cf"]
        for table in tables:
            try:
                self._repo.execute(
                    f"DELETE FROM {table} "
                    f"WHERE company_id = ? AND scenario_id = ? "
                    f"AND period_id IN (SELECT period_id FROM periods WHERE company_id = ? AND year < ?)",
                    (self.company_id, scenario_id, self.company_id, forecast_start),
                )
            except Exception as e:
                logger.debug(f"  stale cleanup {table}: {e}")
        logger.info(
            f"  Stale forecast cleanup: удалены строки year < {forecast_start} "
            f"для {self.company_id} scenario_id={scenario_id}"
        )

    def _get_or_create_version(self) -> Optional[int]:
        try:
            cur = self._repo.execute(
                "INSERT INTO model_versions (company_id, version, status, description) "
                "VALUES (?, ?, 'published', ?) "
                "ON CONFLICT(company_id, version) DO UPDATE SET status='published'",
                (self.company_id, "v2.1", f"Прогноз {self._config.forecast_start_year}–{self._config.forecast_end_year}"),
            )
            row = self._repo.query_one(
                "SELECT version_id FROM model_versions WHERE company_id=? AND version=?",
                (self.company_id, "v2.1"),
            )
            return row["version_id"] if row else None
        except Exception as e:
            logger.warning(f"Не удалось создать version: {e}")
            return None
