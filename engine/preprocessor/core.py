"""
Препроцессор финансовой модели v2.
Читает history_* из БД, вычисляет драйверы, пишет в preprocess_metrics.
Принцип: один метод = одна группа метрик. Каждый метод тестируется изолированно.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..database.repository import Repository

logger = logging.getLogger(__name__)

# ─── EWA helper ───────────────────────────────────────────────────────────────

def ewa(series: Dict[int, float], halflife_years: float = 3.0) -> float:
    """
    Exponentially Weighted Average.
    α = 1 − exp(−ln2 / halflife)
    """
    if not series:
        return 0.0
    alpha = 1.0 - math.exp(-math.log(2) / max(halflife_years, 0.5))
    years = sorted(series.keys())
    result = series[years[0]]
    for yr in years[1:]:
        result = alpha * series[yr] + (1 - alpha) * result
    return result


def _safe_div(num: float, den: float, default: float = 0.0) -> float:
    return num / den if den and not math.isnan(den) and abs(den) > 1e-12 else default


def _summary(series: Dict[int, float], halflife: float = 3.0) -> Dict:
    """Возвращает {year: v, ..., _ewa, _mean, _last, _recommended}."""
    if not series:
        return {}
    result = dict(series)
    valid = {y: v for y, v in series.items() if v is not None and not math.isnan(v)}
    if not valid:
        return result
    result["_ewa"] = ewa(valid, halflife)
    result["_mean"] = sum(valid.values()) / len(valid)
    result["_last"] = valid[max(valid.keys())]
    # Winsorized EWA: clip extreme values at p10/p90 before EWA
    # Protects against anomalous commodity cycle years (e.g. 2021 steel peak)
    if len(valid) >= 5:
        sorted_vals = sorted(valid.values())
        p10 = sorted_vals[max(0, int(len(sorted_vals) * 0.10))]
        p90 = sorted_vals[min(len(sorted_vals) - 1, int(len(sorted_vals) * 0.90))]
        clipped = {yr: max(p10, min(p90, v)) for yr, v in valid.items()}
        result["_ewa_winsorized"] = ewa(clipped, halflife)
    else:
        result["_ewa_winsorized"] = result["_ewa"]
    # AR(1): ratio_t = a + b × ratio_{t-1}
    # Captures persistence/mean-reversion better than EWA for ratios
    sorted_yrs = sorted(valid.keys())
    if len(sorted_yrs) >= 5:
        vals = [valid[y] for y in sorted_yrs]
        x, y_ar = vals[:-1], vals[1:]
        n_ar = len(x)
        mx_ar = sum(x) / n_ar
        my_ar = sum(y_ar) / n_ar
        cov_ar = sum((x[i] - mx_ar) * (y_ar[i] - my_ar) for i in range(n_ar))
        var_ar = sum((xi - mx_ar) ** 2 for xi in x)
        ar1_b = cov_ar / var_ar if abs(var_ar) > 1e-12 else 0
        ar1_a = my_ar - ar1_b * mx_ar
        # R²
        ss_res = sum((y_ar[i] - (ar1_a + ar1_b * x[i])) ** 2 for i in range(n_ar))
        ss_tot = sum((y_ar[i] - my_ar) ** 2 for i in range(n_ar))
        ar1_r2 = 1 - ss_res / ss_tot if ss_tot > 1e-12 else 0
        # AR(1) forecast = a + b × last_value
        ar1_forecast = ar1_a + ar1_b * vals[-1]
        result["_ar1_coef"] = ar1_b
        result["_ar1_intercept"] = ar1_a
        result["_ar1_r2"] = ar1_r2
        result["_ar1_recommended"] = ar1_forecast
        # Use AR(1) if R² > 0.3 (meaningful persistence)
        if ar1_r2 > 0.3:
            result["_recommended"] = ar1_forecast
        else:
            result["_recommended"] = result["_ewa"]
    else:
        result["_recommended"] = result["_ewa"]
    return result


# ─── результат ────────────────────────────────────────────────────────────────

@dataclass
class PreprocessResult:
    company_id: str
    groups_computed: List[str] = field(default_factory=list)
    metrics_written: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        lines = [
            f"Препроцессор: {self.company_id}",
            f"  Групп: {len(self.groups_computed)}  Метрик: {self.metrics_written}",
        ]
        if self.warnings:
            lines += [f"  ⚠ {w}" for w in self.warnings[:3]]
        if self.errors:
            lines += [f"  ✗ {e}" for e in self.errors[:3]]
        return "\n".join(lines)


# ─── препроцессор ─────────────────────────────────────────────────────────────

class ModelPreprocessor:
    """
    Вычисляет все драйверы прогноза из исторических данных.

    Использование:
        with Repository() as repo:
            pp = ModelPreprocessor("us_steel", repo)
            result = pp.run()
    """

    def __init__(
        self,
        company_id: str,
        repo: Repository,
        ewa_halflife: float = 3.0,
        wc_halflife: float = 3.0,
        beta_min_years: int = 5,
    ) -> None:
        self.company_id = company_id
        self._repo = repo
        self._ewa_halflife = ewa_halflife
        self._wc_halflife = wc_halflife
        self._beta_min_years = beta_min_years

        # Кеши истории — загружаются один раз в run()
        self._is: Dict[int, Dict[str, float]] = {}
        self._bs: Dict[int, Dict[str, float]] = {}
        self._cf: Dict[int, Dict[str, float]] = {}
        self._years: List[int] = []

    # ── публичный API ──────────────────────────────────────────────────────────

    def run(self) -> PreprocessResult:
        result = PreprocessResult(company_id=self.company_id)

        # Загрузить историю один раз
        self._is = self._repo.get_history(self.company_id, "IS")
        self._bs = self._repo.get_history(self.company_id, "BS")
        self._cf = self._repo.get_history(self.company_id, "CF")
        self._years = sorted(set(self._is) | set(self._bs) | set(self._cf))

        if not self._years:
            result.errors.append("Нет исторических данных в БД")
            return result

        logger.info(f"Препроцессор: {self.company_id}, лет={len(self._years)} ({self._years[0]}–{self._years[-1]})")

        # Запускаем все блоки
        blocks = [
            ("margin_ratios",               self._process_margin_ratios),
            ("wc_days",                     self._process_wc_days),
            ("capex",                       self._process_capex),
            ("debt",                        self._process_debt),
            ("interest",                    self._process_interest),
            ("equity",                      self._process_equity),
            ("extended",                    self._process_extended),
            ("beta_coefficients",           self._process_beta_coefficients),
            ("revenue_betas",               self._process_revenue_betas),
            ("cf_reconciliation_adjustment",self._process_cf_reconciliation),
            ("is_reconciliation_adjustment",self._process_is_reconciliation),
            ("unmodeled_items_adjustment",  self._process_unmodeled_items),
            ("lease",                        self._process_lease),
            ("cogs_macro",                   self._process_cogs_macro),
            ("production_kpi",               self._process_production_kpi),
        ]

        for group_name, method in blocks:
            try:
                metrics = method()
                if metrics:
                    n = self._repo.upsert_preprocess(
                        self.company_id, group_name, metrics,
                        source="preprocessor_v2",
                    )
                    result.metrics_written += n
                    result.groups_computed.append(group_name)
                    logger.info(f"  {group_name}: {n} метрик")
            except Exception as e:
                msg = f"{group_name}: {e}"
                result.errors.append(msg)
                logger.warning(f"  ✗ {msg}", exc_info=True)

        return result

    # ── helpers ────────────────────────────────────────────────────────────────

    def _is_val(self, year: int, metric: str) -> Optional[float]:
        return self._is.get(year, {}).get(metric)

    def _bs_val(self, year: int, metric: str) -> Optional[float]:
        return self._bs.get(year, {}).get(metric)

    def _cf_val(self, year: int, metric: str) -> Optional[float]:
        return self._cf.get(year, {}).get(metric)

    def _is_series(self, metric: str) -> Dict[int, float]:
        return {y: v for y, v in
                ((yr, self._is.get(yr, {}).get(metric)) for yr in self._years)
                if v is not None}

    def _bs_series(self, metric: str) -> Dict[int, float]:
        return {y: v for y, v in
                ((yr, self._bs.get(yr, {}).get(metric)) for yr in self._years)
                if v is not None}

    def _cf_series(self, metric: str) -> Dict[int, float]:
        return {y: v for y, v in
                ((yr, self._cf.get(yr, {}).get(metric)) for yr in self._years)
                if v is not None}

    # ── блоки метрик ──────────────────────────────────────────────────────────

    def _process_margin_ratios(self) -> Dict[str, Dict]:
        """
        Маржи и коэффициенты IS.
        Группа: margin_ratios
        Метрики: gross_margin, ebitda_margin, ebit_margin, ebt_margin,
                 net_margin, cogs_ratio, sga_ratio, tax_rate
        """
        out: Dict[str, Dict] = {}
        revenue = self._is_series("revenue")

        margin_defs = [
            ("gross_margin",  "gross_profit",  True),
            ("ebitda_margin", "ebitda",        True),
            ("ebit_margin",   "ebit",          True),
            ("ebt_margin",    "ebt",           True),
            ("net_margin",    "net_income",    True),
            ("cogs_ratio",    "cogs",          False),   # abs(cogs)/revenue
            ("sga_ratio",     "sga",           False),
        ]

        for metric_name, numerator_metric, signed in margin_defs:
            num_series = self._is_series(numerator_metric)
            ratios: Dict[int, float] = {}
            for yr in self._years:
                rev = revenue.get(yr)
                num = num_series.get(yr)
                if rev and num is not None and abs(rev) > 1e-9:
                    ratio = num / rev if signed else abs(num) / abs(rev)
                    ratios[yr] = ratio
            if ratios:
                out[metric_name] = _summary(ratios, self._ewa_halflife)

        # opex_ratio: (|sga| + |distribution_expenses|) / Revenue — total opex below GP
        dist_series = self._is_series("distribution_expenses")
        sga_series_raw = self._is_series("sga")
        opex_ratios: Dict[int, float] = {}
        for yr in self._years:
            rev = revenue.get(yr)
            sga_v = sga_series_raw.get(yr)
            dist_v = dist_series.get(yr)
            if rev and abs(rev) > 1e-9 and (sga_v is not None or dist_v is not None):
                total_opex = abs(sga_v or 0) + abs(dist_v or 0)
                opex_ratios[yr] = total_opex / abs(rev)
        if opex_ratios:
            out["opex_ratio"] = _summary(opex_ratios, self._ewa_halflife)

        # COGS ratio ex-D&A: (|COGS| - D&A) / Revenue — when D&A is embedded in COGS
        da_series = self._is_series("total_da")
        cogs_series = self._is_series("cogs")
        cogs_ex_da_ratios: Dict[int, float] = {}
        for yr in self._years:
            rev = revenue.get(yr)
            cogs_v = cogs_series.get(yr)
            da_v = da_series.get(yr)
            if rev and cogs_v is not None and abs(rev) > 1e-9:
                cogs_ex = abs(cogs_v) - abs(da_v or 0)
                cogs_ex_da_ratios[yr] = max(0.0, cogs_ex) / abs(rev)
        if cogs_ex_da_ratios:
            out["cogs_ratio_ex_da"] = _summary(cogs_ex_da_ratios, self._ewa_halflife)

        # SGA sub-line ratios: distribution, admin (sgna), ECL, other opex
        # SGA sub-line ratios: distribution, admin, ECL, other opex
        # Distribution and ECL/other_opex are separate IS lines.
        # Admin = SGA - distribution (if both exist; SGA often = admin only)
        sga_sublines = [
            ("distribution_ratio",  "distribution_expenses"),
            ("ecl_ratio",           "expected_credit_losses"),
            ("other_opex_ratio",    "other_operating_expenses"),
        ]
        for metric_name, is_metric in sga_sublines:
            sub_series = self._is_series(is_metric)
            sub_ratios: Dict[int, float] = {}
            for yr in self._years:
                rev = revenue.get(yr)
                val = sub_series.get(yr)
                if rev and val is not None and abs(rev) > 1e-9:
                    sub_ratios[yr] = abs(val) / abs(rev)
            if sub_ratios:
                out[metric_name] = _summary(sub_ratios, self._ewa_halflife)

        # Admin ratio: derived as SGA - distribution (if distribution is separate IS line)
        admin_ratios: Dict[int, float] = {}
        for yr in self._years:
            rev = revenue.get(yr)
            sga_v = sga_series_raw.get(yr)
            dist_v = dist_series.get(yr)
            if rev and sga_v is not None and abs(rev) > 1e-9:
                admin = abs(sga_v) - abs(dist_v or 0)
                if admin > 0:
                    admin_ratios[yr] = admin / abs(rev)
        if admin_ratios:
            out["admin_ratio"] = _summary(admin_ratios, self._ewa_halflife)

        # SGA composition: share of each sub-line in total operating expenses
        # Total opex = |distribution| + |sga| + |ecl| + |other_opex|
        ecl_series = self._is_series("expected_credit_losses")
        other_opex_series = self._is_series("other_operating_expenses")
        composition_defs = [
            ("distribution_share_of_opex", dist_series),
            ("admin_share_of_opex",        sga_series_raw),  # sga here = admin component
            ("ecl_share_of_opex",          ecl_series),
            ("other_opex_share_of_opex",   other_opex_series),
        ]
        for metric_name, sub_series in composition_defs:
            shares: Dict[int, float] = {}
            for yr in self._years:
                # Total opex = sum of all sub-lines
                comps = [abs(s.get(yr) or 0) for s in
                         [dist_series, sga_series_raw, ecl_series, other_opex_series]]
                total = sum(comps)
                val = sub_series.get(yr)
                if total > 1e-9 and val is not None:
                    shares[yr] = abs(val) / total
            if shares:
                out[metric_name] = _summary(shares, self._ewa_halflife)

        # Tax rate: tax_expense / ebt
        tax_series  = self._is_series("tax_expense")
        ebt_series  = self._is_series("ebt")
        tax_rates: Dict[int, float] = {}
        for yr in self._years:
            tax = tax_series.get(yr)
            ebt = ebt_series.get(yr)
            if tax is not None and ebt and abs(ebt) > 1e-9 and ebt > 0:
                tax_rates[yr] = abs(tax) / ebt
        if tax_rates:
            out["tax_rate"] = _summary(tax_rates, self._ewa_halflife)

        # Current/deferred tax split ratios (for DT categories)
        cur_tax_series = self._is_series("current_tax")
        def_tax_series = self._is_series("deferred_tax")
        for metric_name, tax_sub in [("current_tax_ratio", cur_tax_series),
                                      ("deferred_tax_ratio", def_tax_series)]:
            ratios = {}
            for yr in self._years:
                ebt = ebt_series.get(yr)
                val = tax_sub.get(yr)
                if ebt and val is not None and abs(ebt) > 1e-9 and ebt > 0:
                    ratios[yr] = abs(val) / ebt
            if ratios:
                out[metric_name] = _summary(ratios, self._ewa_halflife)

        # DTA/DTL rates: Δ(DTA or DTL) / total_assets — for deferred tax category calibration
        dta_series = self._bs_series("dta")
        dtl_series = self._bs_series("dtl")
        assets_series = self._bs_series("total_assets")
        for metric_name, dt_series in [("dta_pct_assets", dta_series),
                                        ("dtl_pct_assets", dtl_series)]:
            ratios = {}
            for yr in self._years:
                dt = dt_series.get(yr)
                ta = assets_series.get(yr)
                if dt is not None and ta and abs(ta) > 1e-9:
                    ratios[yr] = abs(dt) / abs(ta)
            if ratios:
                out[metric_name] = _summary(ratios, self._ewa_halflife)

        # Provisions ratio: employee_benefits / revenue (for provisions corkscrew)
        eb_series = self._bs_series("employee_benefits")
        prov_ratios: Dict[int, float] = {}
        for yr in self._years:
            eb = eb_series.get(yr)
            rev = revenue.get(yr)
            if eb is not None and rev and abs(rev) > 1e-9:
                prov_ratios[yr] = abs(eb) / abs(rev)
        if prov_ratios:
            out["provisions_pct_revenue"] = _summary(prov_ratios, self._ewa_halflife)

        return out

    def _process_wc_days(self) -> Dict[str, Dict]:
        """
        Дни оборачиваемости рабочего капитала.
        Группа: wc_days
        Метрики: dso (AR/Revenue×365), dih (Inv/COGS×365), dpo (AP/COGS×365), ccc
        """
        out: Dict[str, Dict] = {}
        revenue  = self._is_series("revenue")
        cogs     = self._is_series("cogs")
        ar       = self._bs_series("accounts_receivable")
        inv      = self._bs_series("inventory")
        ap       = self._bs_series("accounts_payable")

        dso_s: Dict[int, float] = {}
        dih_s: Dict[int, float] = {}
        dpo_s: Dict[int, float] = {}

        for yr in self._years:
            rev  = revenue.get(yr)
            cg   = cogs.get(yr)
            ar_v = ar.get(yr)
            inv_v = inv.get(yr)
            ap_v = ap.get(yr)

            if rev and ar_v is not None and abs(rev) > 1e-9:
                dso_s[yr] = abs(ar_v) / abs(rev) * 365
            if cg and inv_v is not None and abs(cg) > 1e-9:
                dih_s[yr] = abs(inv_v) / abs(cg) * 365
            if cg and ap_v is not None and abs(cg) > 1e-9:
                dpo_s[yr] = abs(ap_v) / abs(cg) * 365

        for name, series in [("dso", dso_s), ("dih", dih_s), ("dpo", dpo_s)]:
            if series:
                out[name] = _summary(series, self._wc_halflife)

        # CCC = DSO + DIH - DPO
        ccc_s: Dict[int, float] = {}
        for yr in self._years:
            if yr in dso_s and yr in dih_s and yr in dpo_s:
                ccc_s[yr] = dso_s[yr] + dih_s[yr] - dpo_s[yr]
        if ccc_s:
            out["ccc"] = _summary(ccc_s, self._wc_halflife)

        # NWC/Revenue ratio
        rev_s = self._is_series("revenue")
        ar_s  = self._bs_series("accounts_receivable")
        inv_s = self._bs_series("inventory")
        ap_s  = self._bs_series("accounts_payable")
        common = sorted(set(rev_s) & set(ar_s) & set(inv_s) & set(ap_s))
        if common:
            nwc_ratios = {}
            for yr in common:
                rev = rev_s[yr]
                if rev > 0:
                    nwc = (abs(ar_s[yr]) + abs(inv_s[yr]) - abs(ap_s[yr]))
                    nwc_ratios[yr] = nwc / rev
            if nwc_ratios:
                out["nwc_to_revenue"] = nwc_ratios
                out["nwc_to_revenue_recommended"] = {
                    -1: ewa({i: v for i, v in enumerate(nwc_ratios.values())}, halflife_years=3)
                }

        return out

    def _process_capex(self) -> Dict[str, Dict]:
        """
        CapEx и амортизационные коэффициенты.
        Группа: capex
        Метрики: capex_to_rev, dep_to_rev, dep_rate (dep/ppe_net), disposal_ratio
        """
        out: Dict[str, Dict] = {}
        revenue  = self._is_series("revenue")
        total_da = self._is_series("total_da")
        ppe_net  = self._bs_series("ppe_net")
        capex    = self._cf_series("capex")
        disposal = self._cf_series("ppe_disposal_proceeds")

        capex_ratio: Dict[int, float] = {}
        dep_ratio:   Dict[int, float] = {}
        dep_rate:    Dict[int, float] = {}
        disp_ratio:  Dict[int, float] = {}

        for yr in self._years:
            rev  = revenue.get(yr)
            da   = total_da.get(yr)
            ppe  = ppe_net.get(yr)
            cx   = capex.get(yr)
            disp = disposal.get(yr)

            if rev and cx is not None and abs(rev) > 1e-9:
                capex_ratio[yr] = abs(cx) / abs(rev)
            if rev and da is not None and abs(rev) > 1e-9:
                dep_ratio[yr] = abs(da) / abs(rev)
            if ppe and da is not None and abs(ppe) > 1e-9:
                dep_rate[yr] = abs(da) / abs(ppe)
            if cx and disp is not None and abs(cx) > 1e-9:
                disp_ratio[yr] = abs(disp) / abs(cx)

        for name, series in [
            ("capex_to_rev",   capex_ratio),
            ("dep_to_rev",     dep_ratio),
            ("dep_rate",       dep_rate),
            ("disposal_ratio", disp_ratio),
        ]:
            if series:
                out[name] = _summary(series, self._ewa_halflife)

        # Acquisitions из истории CF
        acq_series = self._cf_series("acquisitions")
        if not acq_series:
            acq_series = self._cf_series("cfi_acquisitions")
        if acq_series:
            out["acquisitions"] = acq_series
            summary = _summary(acq_series, halflife=3.0)
            out["acquisitions_recommended"] = {-1: summary.get("_recommended", 0.0)}

        return out

    def _process_debt(self) -> Dict[str, Dict]:
        """
        Долговые метрики.
        Группа: debt
        Метрики: avg_interest_rate, debt_to_rev, debt_to_ebitda,
                 net_debt_to_ebitda, interest_coverage, net_debt
        """
        out: Dict[str, Dict] = {}
        revenue  = self._is_series("revenue")
        ebitda   = self._is_series("ebitda")
        ebit     = self._is_series("ebit")
        int_exp  = self._is_series("interest_expense")
        ltd      = self._bs_series("long_term_debt")
        std      = self._bs_series("short_term_debt")
        cash     = self._bs_series("cash")

        avg_rate:   Dict[int, float] = {}
        debt_rev:   Dict[int, float] = {}
        debt_ebitda:Dict[int, float] = {}
        nd_ebitda:  Dict[int, float] = {}
        icr:        Dict[int, float] = {}
        net_debt_s: Dict[int, float] = {}

        for yr in self._years:
            lt  = ltd.get(yr, 0) or 0
            st  = std.get(yr, 0) or 0
            csh = cash.get(yr, 0) or 0
            total_debt = abs(lt) + abs(st)
            net_debt   = total_debt - abs(csh)
            rev    = revenue.get(yr)
            eb     = ebitda.get(yr)
            ebit_v = ebit.get(yr)
            int_v  = int_exp.get(yr)

            if total_debt > 1e-9:
                net_debt_s[yr] = net_debt
            if rev and total_debt > 1e-9:
                debt_rev[yr] = total_debt / abs(rev)
            if eb and abs(eb) > 1e-9 and total_debt > 1e-9:
                debt_ebitda[yr] = total_debt / abs(eb)
            if eb and abs(eb) > 1e-9 and net_debt > 0:
                nd_ebitda[yr] = net_debt / abs(eb)
            if ebit_v and int_v and abs(int_v) > 1e-9:
                icr[yr] = abs(ebit_v) / abs(int_v)
            if int_v and total_debt > 1e-9:
                avg_rate[yr] = abs(int_v) / total_debt

        for name, series in [
            ("avg_interest_rate",    avg_rate),
            ("debt_to_rev",          debt_rev),
            ("debt_to_ebitda",       debt_ebitda),
            ("net_debt_to_ebitda",   nd_ebitda),
            ("interest_coverage",    icr),
            ("net_debt",             net_debt_s),
        ]:
            if series:
                out[name] = _summary(series, self._ewa_halflife)

        # ST/Total debt ratio из истории
        st_series  = self._bs_series("short_term_debt")
        lt_series  = self._bs_series("long_term_debt")
        if st_series and lt_series:
            st_ratios = {}
            for yr in sorted(set(st_series) & set(lt_series)):
                total = abs(st_series[yr]) + abs(lt_series[yr])
                if total > 0:
                    st_ratios[yr] = abs(st_series[yr]) / total
            if st_ratios:
                out["st_debt_ratio"] = st_ratios
                # EWA рекомендация
                ewa_ratio = ewa({i: v for i, v in enumerate(st_ratios.values())}, halflife_years=3)
                out["st_debt_ratio_recommended"] = {-1: ewa_ratio}

        # ── Min Cash (операционный минимум) ──────────────────────────────
        # Методология: max(P10 исторического cash, cash эквивалентный 15 дням расходов)
        # Логика: компания должна держать минимум достаточный для операций
        cash_series = self._bs_series("cash")
        rev_series  = self._is_series("revenue")
        cogs_series = self._is_series("cogs")

        if cash_series and len(cash_series) >= 3:
            cash_vals = sorted(cash_series.values())
            n = len(cash_vals)

            # P10 исторического cash (нижняя граница)
            p10_cash = cash_vals[max(0, int(n * 0.10))]

            # 15 дней операционных расходов (cash burn proxy)
            sga_series = self._is_series("sga")
            last_yr = max(set(rev_series) & set(cogs_series)) if rev_series and cogs_series else None

            daily_opex_min = None
            if last_yr and cogs_series.get(last_yr) and sga_series.get(last_yr):
                annual_opex = abs(cogs_series[last_yr]) + abs(sga_series.get(last_yr, 0))
                daily_opex_min = annual_opex / 365 * 15  # 15 дней

            # Min cash = max(P10, 15-day opex, 2% revenue)
            last_rev = rev_series.get(max(rev_series)) if rev_series else 0
            min_cash_rev_pct = last_rev * 0.02  # 2% выручки

            candidates = [p10_cash]
            if daily_opex_min:
                candidates.append(daily_opex_min)
            if min_cash_rev_pct:
                candidates.append(min_cash_rev_pct)

            min_cash_recommended = max(candidates)

            # EWA cash / Revenue ratio (для нормализации по размеру)
            cash_rev_ratios = {}
            for yr in set(cash_series) & set(rev_series):
                if rev_series[yr] > 0:
                    cash_rev_ratios[yr] = cash_series[yr] / rev_series[yr]

            out["min_cash_recommended"]     = {-1: min_cash_recommended}
            out["min_cash_p10"]             = {-1: p10_cash}
            out["min_cash_15day_opex"]      = {-1: daily_opex_min or 0}
            out["min_cash_pct_revenue"]     = {-1: 0.02}
            if cash_rev_ratios:
                out["cash_to_revenue_ratio"]       = cash_rev_ratios
                out["cash_to_revenue_recommended"] = {-1: ewa({i: v for i, v in enumerate(cash_rev_ratios.values())}, halflife_years=3)}

        return out

    def _process_interest(self) -> Dict[str, Dict]:
        """
        Interest accrual ratios — отношение начисленных к уплаченным процентам.
        Группа: interest
        """
        out: Dict[str, Dict] = {}
        int_exp   = self._is_series("interest_expense")
        int_paid  = self._cf_series("interest_paid")
        int_payable = self._bs_series("interest_payable")
        cash      = self._bs_series("cash")
        int_income = self._is_series("interest_income")

        # interest_income_rate: income / avg(cash)
        inc_rate: Dict[int, float] = {}
        years_s = sorted(self._years)
        for i, yr in enumerate(years_s):
            if i == 0:
                continue
            inc = int_income.get(yr)
            c0  = cash.get(years_s[i-1], 0) or 0
            c1  = cash.get(yr, 0) or 0
            avg_cash = (c0 + c1) / 2
            if inc and avg_cash > 1e-9:
                inc_rate[yr] = abs(inc) / avg_cash
        if inc_rate:
            out["interest_income_rate"] = _summary(inc_rate, self._ewa_halflife)

        # accrual_ratio: interest_payable / interest_expense
        accrual: Dict[int, float] = {}
        for yr in self._years:
            exp = int_exp.get(yr)
            pay = int_payable.get(yr)
            if exp and pay is not None and abs(exp) > 1e-9:
                accrual[yr] = abs(pay) / abs(exp)
        if accrual:
            out["interest_accrual_ratio"] = _summary(accrual, self._ewa_halflife)

        return out

    def _process_equity(self) -> Dict[str, Dict]:
        """
        Equity flows.
        Группа: equity
        Метрики: dividend_payout, buyback_to_ni, roe
        """
        out: Dict[str, Dict] = {}
        ni       = self._is_series("net_income")
        divs     = self._cf_series("dividends_paid")
        buybacks = self._cf_series("share_buybacks")
        eq       = self._bs_series("total_equity")

        payout:   Dict[int, float] = {}
        buyback:  Dict[int, float] = {}
        roe_s:    Dict[int, float] = {}

        years_s = sorted(self._years)
        for i, yr in enumerate(years_s):
            ni_v  = ni.get(yr)
            div_v = divs.get(yr)
            bb_v  = buybacks.get(yr)
            eq_v  = eq.get(yr)
            eq0   = eq.get(years_s[i-1]) if i > 0 else None

            if ni_v and div_v is not None and abs(ni_v) > 1e-9 and ni_v > 0:
                payout[yr] = abs(div_v) / abs(ni_v)
            if ni_v and bb_v is not None and abs(ni_v) > 1e-9 and ni_v > 0:
                buyback[yr] = abs(bb_v) / abs(ni_v)
            if ni_v and eq_v and eq0 and abs((eq_v + eq0) / 2) > 1e-9:
                roe_s[yr] = ni_v / ((eq_v + eq0) / 2)

        for name, series in [
            ("dividend_payout", payout),
            ("buyback_to_ni",   buyback),
            ("roe",             roe_s),
        ]:
            if series:
                out[name] = _summary(series, self._ewa_halflife)

        return out

    def _process_extended(self) -> Dict[str, Dict]:
        """
        Расширенные метрики: EWA для статей с методом EWA в прогнозе.
        Группа: extended
        """
        out: Dict[str, Dict] = {}
        ewa_metrics = {
            "earnings_from_investees":  ("IS", self._is_series),
            "net_periodic_benefit_income": ("IS", self._is_series),
            "other_financial_costs":    ("IS", self._is_series),
            "aoci":                     ("BS", self._bs_series),
            "employee_benefits":        ("BS", self._bs_series),
        }
        for metric, (_, series_fn) in ewa_metrics.items():
            series = series_fn(metric)
            if series:
                out[metric] = _summary(series, self._ewa_halflife)
        return out

    def _process_beta_coefficients(self) -> Dict[str, Dict]:
        """
        Beta-коэффициенты для индексации COGS/SGA на PPI/CPI.
        Группа: beta_coefficients
        Метрики: ppi_beta, cpi_beta, demand_decline_beta
        """
        out: Dict[str, Dict] = {}

        # Загружаем макро факторы из БД
        ppi_series = self._repo.get_macro_factor("ppi_us")
        cpi_series = self._repo.get_macro_factor("cpi_us")
        revenue    = self._is_series("revenue")
        cogs       = self._is_series("cogs")
        sga        = self._is_series("sga")

        years_s = sorted(self._years)

        # PPI beta: регрессия Δln(COGS/Rev) ~ Δln(PPI)
        ppi_beta = _calc_beta(
            y_series={yr: _safe_div(abs(cogs.get(yr, 0)), abs(revenue.get(yr, 1))) for yr in years_s if cogs.get(yr) and revenue.get(yr)},
            x_series=ppi_series,
            min_points=self._beta_min_years,
            log_diff=True,
        )
        if ppi_beta is not None:
            out["ppi_beta"] = {-1: ppi_beta}

        # CPI beta: регрессия Δln(SGA/Rev) ~ Δln(CPI)
        cpi_beta = _calc_beta(
            y_series={yr: _safe_div(abs(sga.get(yr, 0)), abs(revenue.get(yr, 1))) for yr in years_s if sga.get(yr) and revenue.get(yr)},
            x_series=cpi_series,
            min_points=self._beta_min_years,
            log_diff=True,
        )
        if cpi_beta is not None:
            out["cpi_beta"] = {-1: cpi_beta}

        # Demand decline beta: регрессия ΔSGA ~ ΔRev только при отрицательном ΔRev
        dd_beta = _calc_demand_decline_beta(
            revenue=revenue,
            sga=sga,
            min_points=3,
        )
        if dd_beta is not None:
            out["demand_decline_beta"] = {-1: dd_beta}

        return out

    def _process_cf_reconciliation(self) -> Dict[str, Dict]:
        """
        CF reconciliation: разница между subtotals и компонентами.
        Группа: cf_reconciliation_adjustment
        """
        out: Dict[str, Dict] = {}
        for section, total_metric, components in [
            ("cfo", "cfo_total", ["net_income", "total_da"]),
            ("cfi", "cfi_total", ["capex"]),
        ]:
            total_s = self._cf_series(total_metric)
            comp_series = [self._cf_series(c) for c in components]
            adj: Dict[int, float] = {}
            for yr in self._years:
                total = total_s.get(yr)
                comp_sum = sum(s.get(yr, 0) or 0 for s in comp_series)
                if total is not None:
                    adj[yr] = total - comp_sum
            if adj:
                out[f"{section}_adjustment"] = _summary(adj, self._ewa_halflife)
        return out

    def _process_revenue_betas(self) -> Dict[str, Dict]:
        """
        Регрессионные коэффициенты для Revenue и сегментного моделирования.
        Группа: revenue_betas

        Вычисляет:
        - rev_beta_{factor}  — OLS beta: dln(Revenue) ~ dln(factor)
        - rev_r2_{factor}    — R² этой регрессии
        - rev_best_factor    — фактор с наибольшим R²
        - rev_best_beta      — beta лучшего фактора
        - vol_beta_{factor}  — OLS beta для сегментного Volume прогноза
        - vol_r2_{factor}    — R² для Volume регрессии
        """
        import math
        out: Dict[str, Dict] = {}

        rev_series = self._is_series("revenue")
        if len(rev_series) < 5:
            return out

        # Implied volume = Revenue / commodity_price (для сегментного моделирования)
        # Берём первый доступный commodity фактор как proxy для price
        price_factors = ["steel_price_hrc", "brent", "brent_usd", "lme_aluminum"]
        volume_series = {}
        for pf in price_factors:
            price_s = self._repo.get_macro_factor(pf)
            if len(price_s) >= 5:
                common = set(rev_series) & set(price_s)
                if len(common) >= 5:
                    volume_series = {y: rev_series[y] / price_s[y]
                                     for y in common if price_s[y] > 0}
                    out["vol_price_factor"] = {-1: 0}  # placeholder, записываем имя
                    break

        def _ols_beta_r2(x_series, y_series):
            """OLS dln(y) ~ dln(x) → (beta, r2)"""
            common = sorted(set(x_series) & set(y_series))
            if len(common) < 5:
                return None, None
            dx, dy = [], []
            for i in range(1, len(common)):
                y0, y1 = common[i-1], common[i]
                if x_series[y0] > 0 and y_series[y0] > 0:
                    dx.append(math.log(x_series[y1] / x_series[y0]))
                    dy.append(math.log(y_series[y1] / y_series[y0]))
            if not dx:
                return None, None
            n = len(dx)
            mx = sum(dx)/n; my = sum(dy)/n
            cov = sum((dx[i]-mx)*(dy[i]-my) for i in range(n))
            var = sum((dx[i]-mx)**2 for i in range(n))
            if abs(var) < 1e-12:
                return None, None
            beta = cov / var
            alpha = my - beta * mx
            ss_res = sum((dy[i]-alpha-beta*dx[i])**2 for i in range(n))
            ss_tot = sum((dy[i]-my)**2 for i in range(n))
            r2 = max(0.0, 1 - ss_res/ss_tot) if ss_tot > 0 else 0.0
            return beta, r2

        # Revenue betas — тестируем все доступные макро-факторы
        candidate_factors = {
            "steel_price_hrc":          self._repo.get_macro_factor("steel_price_hrc"),
            "gdp_us":                   self._repo.get_macro_factor("gdp_us"),
            "brent":                    self._repo.get_macro_factor("brent"),
            "steel_ppi_iron_steel":     self._repo.get_macro_factor("steel_ppi_iron_steel"),
            "industrial_production_us": self._repo.get_macro_factor("industrial_production_us"),
            "gdp_world":                self._repo.get_macro_factor("gdp_world"),
        }

        best_r2     = 0.0
        best_beta   = None
        best_factor = None

        for factor_name, factor_series in candidate_factors.items():
            if len(factor_series) < 5:
                continue

            # Revenue beta
            beta, r2 = _ols_beta_r2(factor_series, rev_series)
            if beta is not None:
                out[f"rev_beta_{factor_name}"] = {-1: beta}
                out[f"rev_r2_{factor_name}"]   = {-1: r2}
                if r2 > best_r2:
                    best_r2     = r2
                    best_beta   = beta
                    best_factor = factor_name

            # Volume beta (если есть implied volume)
            if volume_series and len(volume_series) >= 5:
                vol_beta, vol_r2 = _ols_beta_r2(factor_series, volume_series)
                if vol_beta is not None:
                    out[f"vol_beta_{factor_name}"] = {-1: vol_beta}
                    out[f"vol_r2_{factor_name}"]   = {-1: vol_r2}

        # Лучший фактор для Revenue
        if best_beta is not None:
            out["rev_best_beta"]   = {-1: best_beta}
            out["rev_best_r2"]     = {-1: best_r2}
            out["rev_best_factor"] = {-1: best_factor or ""}

        return out

    def _process_is_reconciliation(self) -> Dict[str, Dict]:
        """
        IS reconciliation: разница между subtotals и суммой компонентов.
        Группа: is_reconciliation_adjustment
        """
        out: Dict[str, Dict] = {}
        ebit_s  = self._is_series("ebit")
        rev_s   = self._is_series("revenue")
        cogs_s  = self._is_series("cogs")
        sga_s   = self._is_series("sga")
        da_s    = self._is_series("total_da")

        ebit_adj: Dict[int, float] = {}
        for yr in self._years:
            ebit = ebit_s.get(yr)
            if ebit is None:
                continue
            calc = (rev_s.get(yr, 0) or 0) + (cogs_s.get(yr, 0) or 0) + \
                   (sga_s.get(yr, 0) or 0) - abs(da_s.get(yr, 0) or 0)
            ebit_adj[yr] = ebit - calc
        if ebit_adj:
            out["ebit_adjustment"] = _summary(ebit_adj, self._ewa_halflife)
        return out

    def _process_lease(self) -> Dict[str, Dict]:
        """
        Лизинговые параметры из истории.
        Группа: lease
        Метрики: op_lease_decay_rate, op_lease_new_leases, op_lease_cash_payment,
                 fin_lease_principal_rate, fin_lease_amort_rate,
                 fin_lease_interest_rate, fin_lease_new_leases
        """
        out: Dict[str, Dict] = {}

        # BS series
        rou_total   = self._bs_series("rou_asset")
        fin_asset   = self._bs_series("finance_lease_asset_net")
        fin_ll_cur  = self._bs_series("finance_lease_liab_current")
        fin_ll_ncur = self._bs_series("finance_lease_liab_noncurrent")

        # CF series
        new_op_cf   = self._cf_series("rou_assets_from_op_leases")
        cash_op_cf  = self._cf_series("op_lease_cash_cfo")
        fin_prin_cf = self._cf_series("fin_lease_principal_cff")
        new_fin_cf  = self._cf_series("rou_assets_from_fin_leases")
        fin_int_cf  = self._cf_series("fin_lease_interest_cfo")

        # Finance lease amortisation stored as IS metric (from D&A note)
        fin_amort_is = self._is_series("finance_lease_amort")

        years_sorted = sorted(self._years)

        op_decay_rates:  Dict[int, float] = {}
        op_new_s:        Dict[int, float] = {}
        op_cash_s:       Dict[int, float] = {}
        fin_prin_rates:  Dict[int, float] = {}
        fin_amort_rates: Dict[int, float] = {}
        fin_int_rates:   Dict[int, float] = {}
        fin_new_s:       Dict[int, float] = {}

        for i, yr in enumerate(years_sorted):
            prev_yr = years_sorted[i - 1] if i > 0 else None

            # ── Operating lease decay rate ────────────────────────────────
            # op_rou_open = total_rou(prev) − fin_asset(prev)
            rou_prev   = rou_total.get(prev_yr) if prev_yr else None
            rou_curr   = rou_total.get(yr)
            fin_prev   = fin_asset.get(prev_yr, 0.0) if prev_yr else 0.0
            fin_curr   = fin_asset.get(yr, 0.0)
            new_op_v   = abs(new_op_cf.get(yr, 0.0))

            if rou_prev is not None and rou_curr is not None and rou_prev > 1e-6:
                op_rou_open  = max(0.0, rou_prev - fin_prev)
                op_rou_close = max(0.0, rou_curr - fin_curr)
                if op_rou_open > 1e-6:
                    op_amort = op_rou_open + new_op_v - op_rou_close
                    decay = _safe_div(op_amort, op_rou_open)
                    if 0.0 < decay < 1.5:
                        op_decay_rates[yr] = decay

            # ── Operating lease cash payment & new leases ─────────────────
            cash_v = cash_op_cf.get(yr)
            if cash_v is not None:
                op_cash_s[yr] = abs(cash_v)
            if new_op_v > 0:
                op_new_s[yr] = new_op_v

            # ── Finance lease rates ───────────────────────────────────────
            fin_ll_open = (
                abs(fin_ll_cur.get(prev_yr, 0.0) or 0.0) +
                abs(fin_ll_ncur.get(prev_yr, 0.0) or 0.0)
            ) if prev_yr else 0.0

            if fin_ll_open > 1e-6:
                fp = fin_prin_cf.get(yr)
                if fp is not None:
                    fin_prin_rates[yr] = _safe_div(abs(fp), fin_ll_open)
                fi = fin_int_cf.get(yr)
                if fi is not None:
                    fin_int_rates[yr] = _safe_div(abs(fi), fin_ll_open)

            fin_asset_open = fin_asset.get(prev_yr, 0.0) if prev_yr else 0.0
            if fin_asset_open > 1e-6:
                fa = fin_amort_is.get(yr)
                if fa is not None:
                    fin_amort_rates[yr] = _safe_div(abs(fa), fin_asset_open)

            new_fin_v = abs(new_fin_cf.get(yr, 0.0))
            if new_fin_v > 0:
                fin_new_s[yr] = new_fin_v

        for name, series in [
            ("op_lease_decay_rate",      op_decay_rates),
            ("op_lease_new_leases",      op_new_s),
            ("op_lease_cash_payment",    op_cash_s),
            ("fin_lease_principal_rate", fin_prin_rates),
            ("fin_principal_rate",       fin_prin_rates),   # alias for backward compat
            ("fin_lease_amort_rate",     fin_amort_rates),
            ("fin_lease_interest_rate",  fin_int_rates),
            ("fin_lease_new_leases",     fin_new_s),
        ]:
            if series:
                out[name] = _summary(series, self._ewa_halflife)

        return out

    def _process_cogs_macro(self) -> Dict[str, Dict]:
        """
        OLS: COGS/Rev ~ alpha + beta × ln(commodity_price).
        Captures how margins respond to commodity cycles.
        For steel: rising HRC → COGS% drops (revenue grows faster).
        For aluminium: similar — rising LME → margin expansion.
        """
        import numpy as np
        out: Dict[str, Dict] = {}

        revenue = self._is_series("revenue")
        cogs_s  = self._is_series("cogs")
        da_s    = self._is_series("total_da")

        # Build COGS/Rev ratio series
        cogs_ratio: Dict[int, float] = {}
        for yr in self._years:
            rev  = revenue.get(yr)
            cogs = cogs_s.get(yr)
            da   = da_s.get(yr, 0) or 0
            if rev and cogs and abs(rev) > 1e-9:
                # ex-DA if da_in_cogs=False
                cogs_ex = abs(cogs)
                cogs_ratio[yr] = cogs_ex / abs(rev)

        if len(cogs_ratio) < 5:
            return out

        # Get all macro factors from DB
        try:
            macro_rows = self._repo.query(
                "SELECT factor_name, year, value FROM macro_factors "
                "WHERE year BETWEEN ? AND ? ORDER BY factor_name, year",
                (min(self._years), max(self._years)),
            )
        except Exception:
            return out

        factors: Dict[str, Dict[int, float]] = {}
        for r in macro_rows:
            factors.setdefault(r["factor_name"], {})[r["year"]] = r["value"]

        best_r2 = -1.0
        best_factor = None
        best_beta = 0.0
        best_alpha = 0.0

        for factor_name, fseries in factors.items():
            common = sorted(set(cogs_ratio) & set(fseries))
            if len(common) < 5:
                continue

            X_vals = [np.log(fseries[yr]) for yr in common if fseries[yr] > 0]
            Y_vals = [cogs_ratio[yr] for yr in common if fseries[yr] > 0]
            if len(X_vals) < 5:
                continue

            X = np.array(X_vals)
            Y = np.array(Y_vals)
            X_mat = np.column_stack([np.ones(len(X)), X])

            try:
                coeffs = np.linalg.lstsq(X_mat, Y, rcond=None)[0]
                alpha, beta = float(coeffs[0]), float(coeffs[1])
                Y_hat = alpha + beta * X
                ss_res = float(np.sum((Y - Y_hat) ** 2))
                ss_tot = float(np.sum((Y - np.mean(Y)) ** 2))
                r2 = max(0.0, 1 - ss_res / ss_tot) if ss_tot > 0 else 0.0
            except Exception:
                continue

            out[f"cogs_beta_{factor_name}"] = {-1: beta}
            out[f"cogs_r2_{factor_name}"] = {-1: r2}

            if r2 > best_r2:
                best_r2 = r2
                best_factor = factor_name
                best_beta = beta
                best_alpha = alpha

        if best_factor:
            out["cogs_best_beta"] = {-1: best_beta}
            out["cogs_best_alpha"] = {-1: best_alpha}
            out["cogs_best_factor"] = {-1: best_factor}
            out["cogs_best_r2"] = {-1: best_r2}

        return out

    def _process_unmodeled_items(self) -> Dict[str, Dict]:
        """
        Неучтённые статьи BS.
        Разница между total_assets и суммой моделируемых активов.
        Группа: unmodeled_items_adjustment
        """
        out: Dict[str, Dict] = {}
        total_assets = self._bs_series("total_assets")
        modeled_assets_metrics = [
            "cash", "accounts_receivable", "inventory",
            "ppe_net", "goodwill", "intangibles",
        ]
        adj: Dict[int, float] = {}
        for yr in self._years:
            total = total_assets.get(yr)
            if total is None:
                continue
            modeled = sum(abs(self._bs_val(yr, m) or 0) for m in modeled_assets_metrics)
            adj[yr] = total - modeled
        if adj:
            out["unmodeled_assets"] = _summary(adj, self._ewa_halflife)
        return out


    def _process_production_kpi(self) -> Dict[str, Dict]:
        """
        Production KPI из segment_data + расчёт segment_cost_usd_t если отсутствует.

        Метод расчёта cash cost per tonne (если нет в segment_data):
          segment_cost = (total_segment_revenue - segment_EBITDA - segment_DA) / production_kt
          Adjustment factor калибруется по последнему году с Databook значением.
        """
        out: Dict[str, Dict] = {}

        # Загружаем segment_data
        seg_rows = self._repo.query(
            "SELECT p.year, s.segment_name, s.metric, s.value "
            "FROM segment_data s JOIN periods p ON s.period_id=p.period_id "
            "WHERE s.company_id=? AND p.is_forecast=0 "
            "ORDER BY p.year, s.segment_name",
            (self.company_id,),
        )
        if not seg_rows:
            return out

        # Структурируем: {year: {segment: {metric: value}}}
        seg: Dict[int, Dict[str, Dict[str, float]]] = {}
        for row in seg_rows:
            yr, sn, m, v = row["year"], row["segment_name"], row["metric"], row["value"]
            seg.setdefault(yr, {}).setdefault(sn, {})[m] = v

        # Находим Al segment (Primary Aluminium / Primary Al и т.д.)
        al_seg_name = None
        for yr_data in seg.values():
            for sn in yr_data:
                if 'primary' in sn.lower() or ('aluminium' in sn.lower() and 'alumina' not in sn.lower()):
                    al_seg_name = sn
                    break
            if al_seg_name:
                break

        if not al_seg_name:
            return out

        # Собираем KPI метрики
        for metric_key in ['production_kt', 'sales_kt', 'avg_price_usd_t', 'segment_cost_usd_t',
                           'revenue', 'al_revenue']:
            series: Dict[int, float] = {}
            for yr, yr_data in sorted(seg.items()):
                al = yr_data.get(al_seg_name, {})
                val = al.get(metric_key)
                if val is not None and val != 0:
                    series[yr] = val
            if series:
                canonical = {
                    'production_kt': 'production_al_kt',
                    'sales_kt': 'sales_al_kt',
                    'avg_price_usd_t': 'avg_al_price_usd_t',
                    'segment_cost_usd_t': 'al_segment_cost_usd_t',
                    'revenue': 'al_revenue',
                }.get(metric_key, metric_key)
                out[canonical] = series

        # Расчёт segment_cost_usd_t для годов без Databook данных
        cost_series = out.get('al_segment_cost_usd_t', {})
        prod_series = out.get('production_al_kt', {})
        years_with_cost = set(cost_series.keys())
        years_with_prod = set(prod_series.keys())
        missing_years = years_with_prod - years_with_cost

        if missing_years and years_with_cost:
            # Калибровочный коэффициент: Databook_cost / IFRS_calc_cost
            # IFRS calc = (total_segment_rev - EBITDA - DA) / production_kt
            # Используем segment_data + history_is для EBITDA proxy
            adj_factors = []
            for yr in sorted(years_with_cost):
                al_data = seg.get(yr, {}).get(al_seg_name, {})
                rev_seg = al_data.get('revenue', 0)
                prod = prod_series.get(yr, 0)
                cogs_is = abs(self._is_val(yr, 'cogs') or 0)
                ebitda_is = self._is_val(yr, 'ebitda') or 0
                da_is = abs(self._is_val(yr, 'total_da') or 0)
                if prod > 0 and cogs_is > 0:
                    # Proxy: total_COGS / production (грубо)
                    calc_cost = cogs_is / prod / 1000
                    databook_cost = cost_series[yr]
                    if calc_cost > 0:
                        adj_factors.append(databook_cost / calc_cost)

            if adj_factors:
                # Используем среднее за последние 3 года
                adj = sum(adj_factors[-3:]) / len(adj_factors[-3:])

                for yr in sorted(missing_years):
                    prod = prod_series.get(yr, 0)
                    cogs_is = abs(self._is_val(yr, 'cogs') or 0)
                    if prod > 0 and cogs_is > 0:
                        calc = cogs_is / prod / 1000
                        est = round(calc * adj)
                        cost_series[yr] = est
                        # Сохраняем в segment_data
                        pid_row = self._repo.query_one(
                            "SELECT period_id FROM periods WHERE company_id=? AND year=? AND is_forecast=0",
                            (self.company_id, yr),
                        )
                        if pid_row:
                            self._repo.execute(
                                "INSERT OR REPLACE INTO segment_data "
                                "(company_id, period_id, segment_id, segment_name, metric, value, source) "
                                "VALUES (?, ?, 'primary_al', ?, 'segment_cost_usd_t', ?, 'preprocessor_calc')",
                                (self.company_id, pid_row["period_id"], al_seg_name, est),
                            )
                            logger.info(f"  segment_cost_usd_t {yr}: ${est}/t (calc, adj={adj:.3f})")

                out['al_segment_cost_usd_t'] = cost_series

        # Alumina KPIs
        for al_name in seg.get(max(seg.keys()), {}):
            if 'alumina' in al_name.lower():
                for mk in ['revenue', 'sales_kt', 'avg_price_usd_t', 'production_kt']:
                    series = {yr: seg[yr].get(al_name, {}).get(mk, 0)
                              for yr in seg if seg[yr].get(al_name, {}).get(mk)}
                    if series:
                        out[f'alumina_{mk}' if mk != 'revenue' else 'alumina_revenue'] = series
                break

        return out


# ─── helpers для регрессий ─────────────────────────────────────────────────────

def _calc_beta(
    y_series: Dict[int, float],
    x_series: Dict[int, float],
    min_points: int = 5,
    log_diff: bool = True,
) -> Optional[float]:
    """OLS beta для регрессии y ~ x (в log-diff пространстве)."""
    common_years = sorted(set(y_series) & set(x_series))
    if len(common_years) < min_points + 1:
        return None

    y_vals = [y_series[yr] for yr in common_years]
    x_vals = [x_series[yr] for yr in common_years]

    if log_diff:
        try:
            dy = [math.log(y_vals[i] / y_vals[i-1]) for i in range(1, len(y_vals))
                  if y_vals[i] > 0 and y_vals[i-1] > 0]
            dx = [math.log(x_vals[i] / x_vals[i-1]) for i in range(1, len(x_vals))
                  if x_vals[i] > 0 and x_vals[i-1] > 0]
        except (ValueError, ZeroDivisionError):
            return None
        if len(dy) < min_points or len(dy) != len(dx):
            return None
    else:
        dy, dx = y_vals[1:], x_vals[1:]

    # OLS: beta = Cov(x,y) / Var(x)
    n = len(dx)
    mean_x = sum(dx) / n
    mean_y = sum(dy) / n
    cov_xy = sum((dx[i] - mean_x) * (dy[i] - mean_y) for i in range(n))
    var_x  = sum((dx[i] - mean_x) ** 2 for i in range(n))

    if abs(var_x) < 1e-12:
        return None
    return cov_xy / var_x


def _calc_demand_decline_beta(
    revenue: Dict[int, float],
    sga: Dict[int, float],
    min_points: int = 3,
) -> Optional[float]:
    """Beta SGA при снижении Revenue."""
    years_s = sorted(set(revenue) & set(sga))
    dx, dy = [], []
    for i in range(1, len(years_s)):
        yr0, yr1 = years_s[i-1], years_s[i]
        r0, r1 = revenue.get(yr0), revenue.get(yr1)
        s0, s1 = sga.get(yr0), sga.get(yr1)
        if r0 and r1 and s0 and s1 and r1 < r0:  # только при снижении Rev
            dx.append(r1 - r0)
            dy.append(abs(s1) - abs(s0))

    if len(dx) < min_points:
        return None

    n = len(dx)
    mean_x = sum(dx) / n
    mean_y = sum(dy) / n
    cov = sum((dx[i]-mean_x)*(dy[i]-mean_y) for i in range(n))
    var = sum((dx[i]-mean_x)**2 for i in range(n))
    return cov / var if abs(var) > 1e-12 else None
