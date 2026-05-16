"""
Lease corkscrew block — Finance и Operating leases.
Поддерживает US GAAP (ASC 842) и IFRS 16 на агрегатном уровне.

Ключевые различия:
─────────────────────────────────────────────────────────────────
                    US GAAP (ASC 842)        IFRS 16
─────────────────────────────────────────────────────────────────
Operating IS:       lease_expense (single)   dep + interest (split)
Operating CF:       payment → CFO            interest → CFO
                                             principal → CFF
Finance IS:         dep + interest (split)   dep + interest (split)
Finance CF:         interest → CFO           interest → CFO
                    principal → CFF          principal → CFF
─────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple


# ─── Finance Lease (одинаково для обоих стандартов) ──────────────────────────

@dataclass
class FinanceLeaseBlock:
    """
    Finance lease corkscrew — идентично для US GAAP и IFRS 16.
    IS:  depreciation_rou (в total_da) + interest_expense_leases
    CF:  interest_paid → CFO,  principal → CFF
    """
    # Opening
    rou_open:           float = 0.0
    liab_open:          float = 0.0
    # Additions (новые договоры)
    rou_additions:      float = 0.0
    liab_additions:     float = 0.0
    # Params
    dep_rate:           float = 0.15   # ~6-7 лет средний срок
    discount_rate:      float = 0.05
    # Computed
    rou_dep:            Optional[float] = None
    interest_exp:       Optional[float] = None
    principal_pmt:      Optional[float] = None
    total_payment:      Optional[float] = None
    rou_close:          Optional[float] = None
    liab_close:         Optional[float] = None
    liab_current:       Optional[float] = None   # часть погашаемая в следующем году
    liab_noncurrent:    Optional[float] = None

    def solve(self) -> "FinanceLeaseBlock":
        self.rou_dep      = self.rou_open * self.dep_rate
        self.interest_exp = self.liab_open * self.discount_rate
        # Итоговый платёж = interest + principal; principal = total - interest
        # Упрощённо: total_payment ≈ liab_open × (dep_rate + discount_rate)
        self.total_payment    = self.liab_open * (self.dep_rate + self.discount_rate)
        self.principal_pmt    = max(0.0, self.total_payment - self.interest_exp)
        self.rou_close        = max(0.0, self.rou_open + self.rou_additions - self.rou_dep)
        self.liab_close       = max(0.0, self.liab_open + self.liab_additions - self.principal_pmt)
        # Текущая/долгосрочная части
        next_yr_principal     = self.liab_close * (self.dep_rate + self.discount_rate) - \
                                self.liab_close * self.discount_rate
        self.liab_current     = min(next_yr_principal, self.liab_close)
        self.liab_noncurrent  = max(0.0, self.liab_close - self.liab_current)
        return self

    def validate(self, tol: float = 1.0) -> Tuple[bool, list]:
        issues = []
        if self.rou_close is not None and self.rou_close < -tol:
            issues.append(f"finance ROU close < 0: {self.rou_close:.0f}")
        if self.liab_close is not None and self.liab_close < -tol:
            issues.append(f"finance liab close < 0: {self.liab_close:.0f}")
        return len(issues) == 0, issues


# ─── Operating Lease — US GAAP (ASC 842) ─────────────────────────────────────

@dataclass
class OperatingLeaseUSGAAP:
    """
    Operating lease под US GAAP (ASC 842).
    IS:  единая строка operating_lease_expense (обычно в SGA или отдельно)
    BS:  ROU asset + lease liability (как у finance, но по-другому оценивается)
    CF:  весь платёж → CFO (operating cash outflow)
    """
    rou_open:           float = 0.0
    liab_open:          float = 0.0
    rou_additions:      float = 0.0
    liab_additions:     float = 0.0
    discount_rate:      float = 0.05
    dep_rate:           float = 0.15
    # Computed
    lease_expense:      Optional[float] = None   # единая строка в IS
    interest_component: Optional[float] = None   # только для расчёта ROU амортизации
    rou_amort:          Optional[float] = None   # амортизация ROU ≠ dep_ppe
    payment_cfo:        Optional[float] = None   # весь платёж в CFO
    rou_close:          Optional[float] = None
    liab_close:         Optional[float] = None
    liab_current:       Optional[float] = None
    liab_noncurrent:    Optional[float] = None

    def solve(self) -> "OperatingLeaseUSGAAP":
        # Lease expense = straight-line total payment / срок
        # Упрощённо: lease_expense ≈ liab_open × (dep_rate + discount_rate)
        self.lease_expense      = self.liab_open * (self.dep_rate + self.discount_rate)
        self.interest_component = self.liab_open * self.discount_rate
        # ROU amortisation = lease_expense - interest_component (residual)
        self.rou_amort          = max(0.0, self.lease_expense - self.interest_component)
        # US GAAP: весь платёж в CFO
        self.payment_cfo        = self.lease_expense
        # Liability: уменьшается на principal (= payment - interest)
        principal               = max(0.0, self.lease_expense - self.interest_component)
        self.liab_close         = max(0.0, self.liab_open + self.liab_additions - principal)
        self.rou_close          = max(0.0, self.rou_open + self.rou_additions - self.rou_amort)
        next_yr_principal       = self.liab_close * (self.dep_rate + self.discount_rate) - \
                                  self.liab_close * self.discount_rate
        self.liab_current       = min(next_yr_principal, self.liab_close)
        self.liab_noncurrent    = max(0.0, self.liab_close - self.liab_current)
        return self

    def validate(self, tol: float = 1.0) -> Tuple[bool, list]:
        issues = []
        if self.rou_close is not None and self.rou_close < -tol:
            issues.append(f"GAAP op ROU close < 0: {self.rou_close:.0f}")
        if self.liab_close is not None and self.liab_close < -tol:
            issues.append(f"GAAP op liab close < 0: {self.liab_close:.0f}")
        return len(issues) == 0, issues


# ─── Operating Lease — IFRS 16 ────────────────────────────────────────────────

@dataclass
class OperatingLeaseIFRS16:
    """
    Operating lease под IFRS 16.
    IFRS 16 не различает operating/finance для лизингополучателя —
    ВСЕ договоры трактуются как finance-подобные:
    IS:  depreciation (в total_da) + interest_expense (отдельно)
    CF:  interest → CFO,  principal → CFF
    Исключения (short-term < 12 мес, low-value) → lease_expense в IS, payment в CFO.
    """
    rou_open:           float = 0.0
    liab_open:          float = 0.0
    rou_additions:      float = 0.0
    liab_additions:     float = 0.0
    discount_rate:      float = 0.05
    dep_rate:           float = 0.15
    # Exemptions (short-term / low-value) — доля от общего портфеля
    exemption_pct:      float = 0.0
    # Computed
    dep_charge:         Optional[float] = None   # в total_da
    interest_exp:       Optional[float] = None   # отдельно в IS
    principal_pmt:      Optional[float] = None   # → CFF
    interest_paid_cfo:  Optional[float] = None   # → CFO
    exemption_expense:  Optional[float] = None   # short-term → IS+CFO
    rou_close:          Optional[float] = None
    liab_close:         Optional[float] = None
    liab_current:       Optional[float] = None
    liab_noncurrent:    Optional[float] = None

    def solve(self) -> "OperatingLeaseIFRS16":
        # Основной портфель (без исключений)
        rou_main  = self.rou_open  * (1 - self.exemption_pct)
        liab_main = self.liab_open * (1 - self.exemption_pct)
        self.dep_charge      = rou_main  * self.dep_rate
        self.interest_exp    = liab_main * self.discount_rate
        total_pmt            = liab_main * (self.dep_rate + self.discount_rate)
        self.principal_pmt   = max(0.0, total_pmt - self.interest_exp)
        self.interest_paid_cfo = self.interest_exp
        # Исключения (short-term/low-value) → как operating expense
        self.exemption_expense = (
            self.liab_open * self.exemption_pct
            * (self.dep_rate + self.discount_rate)
        )
        # Closing balances
        self.rou_close  = max(0.0, self.rou_open  + self.rou_additions  - self.dep_charge)
        self.liab_close = max(0.0, self.liab_open + self.liab_additions - self.principal_pmt)
        next_yr_principal = self.liab_close * self.dep_rate
        self.liab_current    = min(next_yr_principal, self.liab_close)
        self.liab_noncurrent = max(0.0, self.liab_close - self.liab_current)
        return self

    def validate(self, tol: float = 1.0) -> Tuple[bool, list]:
        issues = []
        if self.rou_close is not None and self.rou_close < -tol:
            issues.append(f"IFRS op ROU close < 0: {self.rou_close:.0f}")
        if self.liab_close is not None and self.liab_close < -tol:
            issues.append(f"IFRS op liab close < 0: {self.liab_close:.0f}")
        return len(issues) == 0, issues


# ─── Агрегированный LeaseBlock ───────────────────────────────────────────────

@dataclass
class LeaseBlock:
    """
    Агрегированный лизинговый блок — финансовый + операционный.
    accounting_standard: US_GAAP | IFRS
    """
    accounting_standard: str = "US_GAAP"
    finance:   Optional[FinanceLeaseBlock]   = None
    operating_gaap: Optional[OperatingLeaseUSGAAP] = None
    operating_ifrs: Optional[OperatingLeaseIFRS16] = None

    def solve(self) -> "LeaseBlock":
        if self.finance:
            self.finance.solve()
        if self.operating_gaap:
            self.operating_gaap.solve()
        if self.operating_ifrs:
            self.operating_ifrs.solve()
        return self

    def validate(self, tol: float = 1.0) -> Tuple[bool, list]:
        issues = []
        for block in [self.finance, self.operating_gaap, self.operating_ifrs]:
            if block:
                ok, blk_issues = block.validate(tol)
                issues.extend(blk_issues)
        return len(issues) == 0, issues

    # ── IS outputs ────────────────────────────────────────────────────────────

    @property
    def dep_rou(self) -> float:
        """Амортизация ROU в total_da."""
        total = 0.0
        if self.finance:
            total += self.finance.rou_dep or 0
        # US GAAP operating: НЕ в dep, а в lease_expense (не в total_da)
        # IFRS operating: в dep
        if self.operating_ifrs:
            total += self.operating_ifrs.dep_charge or 0
        return total

    @property
    def interest_expense_leases(self) -> float:
        """Процентные расходы по лизингу в IS."""
        total = 0.0
        if self.finance:
            total += self.finance.interest_exp or 0
        # US GAAP operating: нет отдельной строки interest (входит в lease_expense)
        # IFRS operating: отдельная строка
        if self.operating_ifrs:
            total += self.operating_ifrs.interest_exp or 0
        return total

    @property
    def operating_lease_expense(self) -> float:
        """
        Единая строка operating lease expense (только US GAAP).
        В IFRS = 0 (заменяется dep + interest).
        """
        if self.operating_gaap:
            return self.operating_gaap.lease_expense or 0
        if self.operating_ifrs:
            return self.operating_ifrs.exemption_expense or 0
        return 0.0

    # ── BS outputs ────────────────────────────────────────────────────────────

    @property
    def rou_total_close(self) -> float:
        total = 0.0
        if self.finance:
            total += self.finance.rou_close or 0
        if self.operating_gaap:
            total += self.operating_gaap.rou_close or 0
        if self.operating_ifrs:
            total += self.operating_ifrs.rou_close or 0
        return total

    @property
    def rou_finance_close(self) -> float:
        return self.finance.rou_close or 0 if self.finance else 0.0

    @property
    def rou_operating_close(self) -> float:
        if self.operating_gaap:
            return self.operating_gaap.rou_close or 0
        if self.operating_ifrs:
            return self.operating_ifrs.rou_close or 0
        return 0.0

    @property
    def liab_finance_current(self) -> float:
        return self.finance.liab_current or 0 if self.finance else 0.0

    @property
    def liab_finance_noncurrent(self) -> float:
        return self.finance.liab_noncurrent or 0 if self.finance else 0.0

    @property
    def liab_operating_current(self) -> float:
        if self.operating_gaap:
            return self.operating_gaap.liab_current or 0
        if self.operating_ifrs:
            return self.operating_ifrs.liab_current or 0
        return 0.0

    @property
    def liab_operating_noncurrent(self) -> float:
        if self.operating_gaap:
            return self.operating_gaap.liab_noncurrent or 0
        if self.operating_ifrs:
            return self.operating_ifrs.liab_noncurrent or 0
        return 0.0

    @property
    def liab_current_total(self) -> float:
        return self.liab_finance_current + self.liab_operating_current

    @property
    def liab_noncurrent_total(self) -> float:
        return self.liab_finance_noncurrent + self.liab_operating_noncurrent

    # ── CF outputs ────────────────────────────────────────────────────────────

    @property
    def payments_cfo(self) -> float:
        """Платежи в CFO (operating section)."""
        total = 0.0
        if self.finance:
            # Finance: только interest в CFO
            total += self.finance.interest_exp or 0
        if self.operating_gaap:
            # US GAAP: весь operating платёж в CFO
            total += self.operating_gaap.payment_cfo or 0
        if self.operating_ifrs:
            # IFRS: только interest в CFO + exemption payments
            total += self.operating_ifrs.interest_paid_cfo or 0
            total += self.operating_ifrs.exemption_expense or 0
        return total

    @property
    def payments_cff(self) -> float:
        """Платежи в CFF (financing section)."""
        total = 0.0
        if self.finance:
            total += self.finance.principal_pmt or 0
        if self.operating_gaap:
            # US GAAP operating: ничего в CFF
            pass
        if self.operating_ifrs:
            # IFRS operating: principal в CFF
            total += self.operating_ifrs.principal_pmt or 0
        return total

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def from_prev_state(
        cls,
        prev,
        accounting_standard: str = "US_GAAP",
        finance_discount_rate: float = 0.05,
        operating_discount_rate: float = 0.05,
        dep_rate: float = 0.15,
        exemption_pct: float = 0.0,
    ) -> "LeaseBlock":
        """Создать блок из YearState предыдущего года."""
        block = cls(accounting_standard=accounting_standard)

        # Finance lease (одинаково для обоих стандартов)
        rou_fin = getattr(prev, "rou_finance", 0) or 0
        liab_fin_cur = getattr(prev, "lease_liab_cur_finance", 0) or 0
        liab_fin_ncur = getattr(prev, "lease_liab_ncur_finance", 0) or 0
        liab_fin = liab_fin_cur + liab_fin_ncur
        if rou_fin > 0 or liab_fin > 0:
            block.finance = FinanceLeaseBlock(
                rou_open=rou_fin,
                liab_open=liab_fin,
                dep_rate=dep_rate,
                discount_rate=finance_discount_rate,
            )

        # Operating lease — выбираем по стандарту
        rou_op = getattr(prev, "rou_operating", 0) or 0
        if rou_op == 0:
            # Если нет раздельного — берём всё из rou_asset за вычетом finance
            rou_op = max(0.0, (prev.rou_asset or 0) - rou_fin)
        liab_op_cur  = getattr(prev, "lease_liab_cur_operating", 0) or 0
        liab_op_ncur = getattr(prev, "lease_liab_ncur_operating", 0) or 0
        if liab_op_cur == 0 and liab_op_ncur == 0:
            liab_op_cur  = prev.lease_liab_current  or 0
            liab_op_ncur = prev.lease_liab_noncurrent or 0
        liab_op = liab_op_cur + liab_op_ncur - liab_fin

        if rou_op > 0 or liab_op > 0:
            if accounting_standard.upper() in ("US_GAAP", "US GAAP"):
                block.operating_gaap = OperatingLeaseUSGAAP(
                    rou_open=rou_op,
                    liab_open=max(0.0, liab_op),
                    discount_rate=operating_discount_rate,
                    dep_rate=dep_rate,
                )
            else:  # IFRS
                block.operating_ifrs = OperatingLeaseIFRS16(
                    rou_open=rou_op,
                    liab_open=max(0.0, liab_op),
                    discount_rate=operating_discount_rate,
                    dep_rate=dep_rate,
                    exemption_pct=exemption_pct,
                )

        return block.solve()

    @classmethod
    def from_config(
        cls,
        prev: "YearState",
        config: "ModelConfig",
    ) -> "LeaseBlock":
        """
        Corkscrew using EWA-calibrated rates from LeaseParams (config.lease).
        Used when no per-instrument schedule data is available.
        """
        from ..inputs import LeaseParams   # avoid circular at module level
        lp: LeaseParams = config.lease
        block = cls(accounting_standard=config.accounting_standard)

        # ── Finance lease corkscrew ────────────────────────────────────────
        fin_asset_open = abs(getattr(prev, "rou_finance", 0.0) or
                             getattr(prev, "finance_lease_asset_net", 0.0) or 0.0)
        fin_ll_cur     = abs(getattr(prev, "lease_liab_cur_finance", 0.0) or
                             getattr(prev, "finance_lease_liab_current", 0.0) or 0.0)
        fin_ll_ncur    = abs(getattr(prev, "lease_liab_ncur_finance", 0.0) or
                             getattr(prev, "finance_lease_liab_noncurrent", 0.0) or 0.0)
        fin_ll_open    = fin_ll_cur + fin_ll_ncur

        if fin_asset_open > 0 or fin_ll_open > 0:
            fin_interest     = fin_ll_open * lp.fin_interest_rate
            fin_principal    = fin_ll_open * lp.fin_principal_rate
            # BS identity: Δasset must equal Δliab for non-cash new leases.
            # dep must consume asset at same rate principal consumes liability
            # so that new_lease additions cancel on both sides.
            fin_rou_dep      = fin_principal + max(0.0, fin_asset_open - fin_ll_open) * lp.fin_amort_rate
            fin_rou_dep      = min(fin_rou_dep, fin_asset_open + lp.fin_new_leases)  # can't exceed available
            fin_asset_close  = max(0.0, fin_asset_open - fin_rou_dep + lp.fin_new_leases)
            fin_ll_close     = max(0.0, fin_ll_open - fin_principal + lp.fin_new_leases)
            fin_ll_curr_next = min(fin_ll_close, fin_principal)
            fin_ll_nc_next   = max(0.0, fin_ll_close - fin_ll_curr_next)

            block.finance = FinanceLeaseBlock(
                rou_open         = fin_asset_open,
                liab_open        = fin_ll_open,
                rou_additions    = lp.fin_new_leases,
                liab_additions   = lp.fin_new_leases,
                dep_rate         = lp.fin_amort_rate,
                discount_rate    = lp.fin_interest_rate,
            )
            # Override computed fields with rate-based results directly
            block.finance.rou_dep        = fin_rou_dep
            block.finance.interest_exp   = fin_interest
            block.finance.principal_pmt  = fin_principal
            block.finance.total_payment  = fin_interest + fin_principal
            block.finance.rou_close      = fin_asset_close
            block.finance.liab_close     = fin_ll_close
            block.finance.liab_current   = fin_ll_curr_next
            block.finance.liab_noncurrent = fin_ll_nc_next

        # ── Operating lease corkscrew (US GAAP) ───────────────────────────
        rou_op_open  = abs(getattr(prev, "rou_operating", 0.0) or 0.0)
        if rou_op_open == 0.0:
            # Fall back: total ROU minus finance
            rou_op_open = max(0.0, abs(prev.rou_asset or 0.0) - fin_asset_open)
        ll_op_cur  = abs(getattr(prev, "lease_liab_cur_operating",  0.0) or 0.0)
        ll_op_ncur = abs(getattr(prev, "lease_liab_ncur_operating", 0.0) or 0.0)
        if ll_op_cur == 0.0 and ll_op_ncur == 0.0:
            # Fall back: total lease liab minus finance
            ll_op_cur  = abs(prev.lease_liab_current or 0.0) - fin_ll_cur
            ll_op_ncur = abs(prev.lease_liab_noncurrent or 0.0) - fin_ll_ncur
        ll_op_open = max(0.0, ll_op_cur + ll_op_ncur)

        if rou_op_open > 0 or ll_op_open > 0:
            # ASC 842: rou_amort = principal (both = ll_open × dep_rate) so ΔROU = ΔLL → BS balanced.
            # op_cash_payment from EWA is used only for payment_cfo reference tracking.
            interest_comp  = ll_op_open * config.leases.default_discount_rate
            principal_op   = ll_op_open * lp.op_decay_rate
            rou_op_amort   = principal_op  # must equal principal for BS identity
            rou_op_close   = max(0.0, rou_op_open - rou_op_amort + lp.op_new_leases)
            ll_op_close    = max(0.0, ll_op_open - principal_op + lp.op_new_leases)
            ll_op_curr_next = min(ll_op_close, principal_op)
            ll_op_nc_next   = max(0.0, ll_op_close - ll_op_curr_next)

            if config.accounting_standard.upper() in ("US_GAAP", "US GAAP"):
                block.operating_gaap = OperatingLeaseUSGAAP(
                    rou_open      = rou_op_open,
                    liab_open     = ll_op_open,
                    rou_additions = lp.op_new_leases,
                    liab_additions = lp.op_new_leases,
                    discount_rate = config.leases.default_discount_rate,
                    dep_rate      = lp.op_decay_rate,
                )
                # Override with rate-based results
                block.operating_gaap.rou_amort          = rou_op_amort
                block.operating_gaap.lease_expense      = lp.op_cash_payment
                block.operating_gaap.interest_component = interest_comp
                block.operating_gaap.payment_cfo        = lp.op_cash_payment
                block.operating_gaap.rou_close          = rou_op_close
                block.operating_gaap.liab_close         = ll_op_close
                block.operating_gaap.liab_current       = ll_op_curr_next
                block.operating_gaap.liab_noncurrent    = ll_op_nc_next
            else:
                block.operating_ifrs = OperatingLeaseIFRS16(
                    rou_open      = rou_op_open,
                    liab_open     = ll_op_open,
                    rou_additions = lp.op_new_leases,
                    liab_additions = lp.op_new_leases,
                    discount_rate = config.leases.default_discount_rate,
                    dep_rate      = lp.op_decay_rate,
                )
                block.operating_ifrs.dep_charge        = rou_op_amort
                block.operating_ifrs.interest_exp      = interest_comp
                block.operating_ifrs.principal_pmt     = principal_op
                block.operating_ifrs.interest_paid_cfo = interest_comp
                block.operating_ifrs.exemption_expense = 0.0
                block.operating_ifrs.rou_close         = rou_op_close
                block.operating_ifrs.liab_close        = ll_op_close
                block.operating_ifrs.liab_current      = ll_op_curr_next
                block.operating_ifrs.liab_noncurrent   = ll_op_nc_next

        return block  # do NOT call .solve() — fields already computed above
