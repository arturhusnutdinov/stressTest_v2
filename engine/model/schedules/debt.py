"""
Debt corkscrew + DebtOptimizer.
Перенос логики из engine/model3/debt.py в новую архитектуру.
Полная реализация: mandatory → refi → draw (RC first) → repay surplus → interest avg.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _nz(v) -> float:
    """None → 0.0."""
    return float(v) if v is not None else 0.0


def _avg(a: float, b: float) -> float:
    return (a + b) / 2.0


# ─── Instrument kinds ─────────────────────────────────────────────────────────

class InstrumentKind:
    RC          = "RC"
    TERM_AMORT  = "TERM_AMORT"
    BOND_BULLET = "BOND_BULLET"
    BULLET      = "BULLET"
    LEASE       = "LEASE"      # исключается из debt-оптимизации
    OTHER       = "OTHER"


def infer_kind(name: str, raw_type: str = "") -> str:
    """Определить kind инструмента по имени и типу."""
    n = (name + " " + raw_type).upper()
    if "LEASE" in n:
        return InstrumentKind.LEASE
    if any(x in n for x in ("REVOLVER", "CREDIT", "FACILITY", "ABL", "RC", "REVOLVING")):
        return InstrumentKind.RC
    if any(x in n for x in ("NOTES", "BONDS", "SENIOR NOTE", "BOND")):
        return InstrumentKind.BOND_BULLET
    if "NOTE" in n:
        return InstrumentKind.BULLET
    if "TERM" in n or "AMORT" in n or "LOAN" in n:
        return InstrumentKind.TERM_AMORT
    return InstrumentKind.TERM_AMORT


# ─── DebtInstrumentOpen ───────────────────────────────────────────────────────

@dataclass
class DebtInstrumentOpen:
    """Состояние инструмента на начало года — входной объект для DebtOptimizer."""
    instrument_id:  str
    name:           str
    kind:           str             # RC | TERM_AMORT | BOND_BULLET | BULLET | OTHER
    opening:        float = 0.0
    rate:           float = 0.0     # годовая ставка в долях (0.05 = 5%)
    limit:          float = 0.0     # для RC: лимит линии
    maturity:       Optional[int] = None
    amort_schedule: Dict[int, float] = field(default_factory=dict)
    priority:       int = 2
    classification: str = "LT"
    callable_flag:  bool = False
    rate_type:      str  = "fixed"   # "fixed" | "floating" — floating rates adjust with macro

    def __post_init__(self):
        # Нормализация ставки: если > 1.0 → в процентах, делим на 100
        if self.rate > 1.0:
            self.rate = self.rate / 100.0
        self.kind = self.kind.upper()
        self.rate_type = self.rate_type.lower()  # normalise: fixed / floating

    @property
    def is_revolving(self) -> bool:
        return self.kind == InstrumentKind.RC

    @property
    def is_lease(self) -> bool:
        return self.kind == InstrumentKind.LEASE or "LEASE" in self.name.upper()


# ─── DebtYearLine ─────────────────────────────────────────────────────────────

@dataclass
class DebtYearLine:
    """Результат по одному инструменту за один год."""
    instrument_id:  str
    name:           str
    opening:        float = 0.0
    draw:           float = 0.0
    refi_draw:      float = 0.0
    repay:          float = 0.0
    mandatory:      float = 0.0
    interest:       float = 0.0
    refi_fees:      float = 0.0
    closing:        float = 0.0
    is_st:          bool  = False


# ─── DebtSolveResult ──────────────────────────────────────────────────────────

@dataclass
class DebtSolveResult:
    """Итог работы DebtOptimizer за один год."""
    lines:                  List[DebtYearLine] = field(default_factory=list)
    cff_debt:               float = 0.0   # net CFF (draws - repays - fees, non-lease)
    st_debt:                float = 0.0   # closing ST
    lt_debt:                float = 0.0   # closing LT
    interest_expense_total: float = 0.0
    new_instruments:        List[DebtInstrumentOpen] = field(default_factory=list)

    @property
    def total_debt(self) -> float:
        return self.st_debt + self.lt_debt

    @property
    def total_draws(self) -> float:
        return sum(l.draw + l.refi_draw for l in self.lines)

    @property
    def total_repayments(self) -> float:
        return sum(l.repay for l in self.lines)


# ─── DebtOptimizer ────────────────────────────────────────────────────────────

class DebtOptimizer:
    """
    Оптимизатор долгового портфеля.

    Целевая функция: минимизировать свободный кэш при cash >= min_cash.
    Draw при нехватке кэша (RC первым), Repay — весь surplus сверх min_cash.

    Алгоритм:
    1. Mandatory — TERM_AMORT из amort_schedule, BOND_BULLET при maturity
    2. Refinancing — simple (продлить) или new (новый инструмент)
    3. pre-fin cash = opening_cash + cfo + cfi - non_refi_mandatory - fees
    4. Draw: RC first, затем LT по (priority, rate)
    5. Repay: surplus сверх min_cash, RC first
    6. Interest = avg(opening_after_refi, closing) × rate
    7. ST/LT split по next_year_mandatory_hint
    """

    @staticmethod
    def _order_indices(
        instruments: List[DebtInstrumentOpen],
        override: Optional[List[str]] = None,
        rc_first: bool = True,
    ) -> List[int]:
        """Отсортировать индексы инструментов для draw/repay порядка."""
        if override:
            name_to_idx = {inst.name: i for i, inst in enumerate(instruments)}
            ordered = [name_to_idx[n] for n in override if n in name_to_idx]
            rest = [i for i in range(len(instruments)) if i not in ordered]
            return ordered + rest

        def sort_key(idx: int):
            inst = instruments[idx]
            rc_priority = 0 if inst.is_revolving else 1
            return (rc_priority, inst.priority, inst.rate)

        return sorted(range(len(instruments)), key=sort_key)

    @classmethod
    def solve_year(
        cls,
        year: int,
        opening_cash: float,
        cfo: float,
        cfi: float,
        instruments_open: List[DebtInstrumentOpen],
        min_cash: float = 0.0,
        refi_mode: str = "simple",
        refi_extend_years: int = 5,
        refi_rate_adj_pct: float = 0.0,
        refi_fees_bps: float = 10.0,
        refi_spread_adj: float = 0.0,
        refi_availability: float = 1.0,
        allow_new_money: bool = True,
        draw_order_override: Optional[List[str]] = None,
        repay_order_override: Optional[List[str]] = None,
        next_year_mandatory_hint: Optional[Dict[str, float]] = None,
        covenant_breach_instruments: Optional[set] = None,
        max_voluntary_repay: Optional[float] = None,  # cap on total voluntary repayment
        cbr_key_rate: float = 0.0,  # base rate added to floating instrument spreads
    ) -> DebtSolveResult:

        # ── Инициализация ────────────────────────────────────────────────────
        # Глубокие копии — не мутируем оригиналы (кроме refi simple → maturity/rate)
        import copy
        insts = [copy.copy(inst) for inst in instruments_open]
        n = len(insts)

        draws      = [0.0] * n
        repays     = [0.0] * n
        interests  = [0.0] * n
        refi_draws = [0.0] * n
        refi_fees_ = [0.0] * n
        mandatorys = [0.0] * n

        new_instruments: List[DebtInstrumentOpen] = []
        total_refi_fees = 0.0

        # ── ШАГ 0: Mandatory ─────────────────────────────────────────────────
        for idx, inst in enumerate(insts):
            mandatory = 0.0
            kind = inst.kind
            if kind == InstrumentKind.TERM_AMORT:
                mandatory = _nz(inst.amort_schedule.get(year, 0.0))
            elif kind in (InstrumentKind.BOND_BULLET, InstrumentKind.BULLET):
                if inst.maturity == year:
                    mandatory = inst.opening
            mandatorys[idx] = min(max(mandatory, 0.0), inst.opening)

        # ── ШАГ 1: Рефинансирование ──────────────────────────────────────────
        rm = (refi_mode or "simple").lower()
        if rm == "auto":
            rm = "simple"

        old_to_new_idx: Dict[int, int] = {}

        for idx, inst in enumerate(insts):
            if inst.is_lease:
                continue
            mandatory = mandatorys[idx]
            if mandatory <= 1e-9:
                continue

            should_refi = (
                inst.maturity == year
                or (inst.kind == InstrumentKind.TERM_AMORT and mandatory > 0)
            )
            if not should_refi:
                continue

            # haircut при стрессе
            refi_amt     = mandatory * refi_availability
            non_refi_amt = mandatory - refi_amt

            if non_refi_amt > 1e-9:
                repays[idx] += non_refi_amt
                mandatory    = refi_amt
                mandatorys[idx] = refi_amt

            # Комиссия
            fee = mandatory * _nz(refi_fees_bps) / 10_000.0
            refi_fees_[idx] += fee
            total_refi_fees  += fee

            if rm == "simple":
                # Продлеваем тот же инструмент
                new_mat  = year + refi_extend_years
                new_rate = inst.rate * (1.0 + refi_rate_adj_pct) + refi_spread_adj
                insts[idx].maturity = new_mat
                insts[idx].rate     = new_rate
                # обновляем оригинал (чтобы следующий год видел новый rate/maturity)
                instruments_open[idx].maturity = new_mat
                instruments_open[idx].rate     = new_rate
                refi_draws[idx] += mandatory
                repays[idx]     += mandatory  # парная проводка, net=0

            elif rm == "new":
                new_rate = inst.rate + refi_spread_adj
                new_inst = DebtInstrumentOpen(
                    instrument_id=f"{inst.instrument_id}_refi_{year}",
                    name=f"{inst.name}_Refi_{year}",
                    kind=inst.kind,
                    opening=0.0,
                    rate=new_rate,
                    maturity=year + refi_extend_years,
                    priority=inst.priority,
                )
                new_instruments.append(new_inst)
                old_to_new_idx[idx] = len(insts) + len(new_instruments) - 1
                repays[idx] += mandatory

            else:
                # No refinancing — straight repayment at maturity / scheduled amort
                repays[idx] += mandatory

        # Добавляем новые инструменты в рабочий список
        for old_idx, new_inst in zip(old_to_new_idx.keys(), new_instruments):
            new_idx = len(insts)
            insts.append(new_inst)
            draws.append(0.0); repays.append(0.0); interests.append(0.0)
            refi_draws.append(0.0); refi_fees_.append(0.0); mandatorys.append(0.0)
            refi_draws[new_idx] = mandatorys[old_idx]

        # ── ШАГ 2: pre-financing cash ────────────────────────────────────────
        non_refi_mandatory = sum(mandatorys) - sum(refi_draws)
        cash_before = opening_cash + cfo + cfi - non_refi_mandatory

        target_cash   = min_cash * 1.02   # буфер 2%
        required_draw = max(0.0, target_cash - cash_before)

        # ── ШАГ 3: Draw ──────────────────────────────────────────────────────
        draw_order = cls._order_indices(insts, draw_order_override)

        for idx in draw_order:
            if required_draw <= 1e-9:
                break
            inst = insts[idx]
            if inst.is_lease:
                continue
            # Лимит для RC
            if inst.is_revolving:
                current_balance = inst.opening + refi_draws[idx] + draws[idx]
                cap = max(0.0, _nz(inst.limit) - current_balance)
            else:
                cap = float("inf")
            take = min(required_draw, cap)
            if take <= 1e-9:
                continue
            draws[idx]    += take
            required_draw -= take

        # Fallback: если RC не хватило → новый LT-инструмент (new money)
        if required_draw > 1e-9 and allow_new_money:
            # Средняя рыночная ставка — берём из существующих LT-инструментов
            lt_rates = [
                insts[i].rate for i in range(len(insts))
                if not insts[i].is_revolving and not insts[i].is_lease
                and insts[i].rate > 0
            ]
            avg_lt_rate = sum(lt_rates) / len(lt_rates) if lt_rates else 0.05
            new_money_inst = DebtInstrumentOpen(
                instrument_id=f"_newmoney_{year}",
                name=f"NewMoney_{year}",
                kind=InstrumentKind.BOND_BULLET,
                opening=0.0,  # new instrument: no prior balance; draw covers the shortfall
                rate=avg_lt_rate,
                maturity=year + 5,
                amort_schedule={year + 5: required_draw},
                priority=1,
                classification="LT",
            )
            nm_idx = len(insts)
            insts.append(new_money_inst)
            draws.append(required_draw)
            repays.append(0.0); interests.append(0.0)
            refi_draws.append(0.0); refi_fees_.append(0.0); mandatorys.append(0.0)
            # Also register in the passed-in list so mutations persist to caller
            instruments_open.append(new_money_inst)

        # ── ШАГ 4: Repay surplus ─────────────────────────────────────────────
        cash_after_draws = cash_before + sum(draws)
        # вычитаем только voluntary repays (refi repays уже учтены через -mandatory)
        voluntary_repays_sum = sum(
            repays[i] - mandatorys[i] - (refi_draws[i] if rm == "simple" else 0)
            for i in range(len(insts))
            if repays[i] > mandatorys[i]
        )
        cash_after_draws -= max(0.0, voluntary_repays_sum)

        surplus = max(0.0, cash_after_draws - min_cash)
        # Apply voluntary prepay cap if set
        vol_cap = max_voluntary_repay if max_voluntary_repay is not None else float('inf')
        repay_order = cls._order_indices(insts, repay_order_override)
        total_repays_voluntary = 0.0

        for idx in repay_order:
            if surplus <= 1e-9 or total_repays_voluntary >= vol_cap:
                break
            inst = insts[idx]
            if inst.is_lease:
                continue
            open_after_refi = inst.opening + refi_draws[idx]
            max_repayable   = open_after_refi + draws[idx]
            already_repaid  = repays[idx]
            can_repay       = max(0.0, max_repayable - already_repaid)

            # Не уходить ниже min_cash
            max_pay = min(can_repay, surplus)
            # Не превышать voluntary prepay cap
            max_pay = min(max_pay, vol_cap - total_repays_voluntary)
            cash_check = cash_after_draws - total_repays_voluntary - max_pay
            if cash_check < min_cash:
                max_pay = max(0.0, cash_after_draws - total_repays_voluntary - min_cash)

            if max_pay <= 1e-9:
                continue
            repays[idx]           += max_pay
            total_repays_voluntary += max_pay
            surplus               -= max_pay

        # ── ШАГ 5: Interest + closing ────────────────────────────────────────
        lines: List[DebtYearLine] = []
        total_interest = 0.0

        for idx, inst in enumerate(insts):
            if inst.is_lease:
                continue
            open_after_refi = inst.opening + refi_draws[idx]
            closing = max(0.0, open_after_refi + draws[idx] - repays[idx])
            # Floating: all-in = spread + base rate (e.g. CBR key rate)
            effective_rate = _nz(inst.rate)
            if inst.rate_type == "floating" and cbr_key_rate > 0:
                effective_rate = inst.rate + cbr_key_rate
            interest = _avg(open_after_refi, closing) * effective_rate
            interests[idx] = interest
            total_interest += interest

            lines.append(DebtYearLine(
                instrument_id=inst.instrument_id,
                name=inst.name,
                opening=inst.opening,
                draw=draws[idx],
                refi_draw=refi_draws[idx],
                repay=repays[idx],
                mandatory=mandatorys[idx],
                interest=interest,
                refi_fees=refi_fees_[idx],
                closing=closing,
                is_st=inst.is_revolving,  # уточняется ниже
            ))

        # ── ШАГ 6: ST/LT split ───────────────────────────────────────────────
        # Four rules applied in priority order:
        # 1. RC always current
        # 2. Matures next year (within 12 months) → full balance current
        # 3. Amortization due next year → split (next_mandatory → ST, rest → LT)
        # 4. Covenant acceleration (callable_flag + breach) → full balance current
        # Default: LT
        _breach = covenant_breach_instruments or set()
        st_total = 0.0
        lt_total = 0.0

        for line in lines:
            inst_match = next(
                (inst for inst in insts if inst.instrument_id == line.instrument_id),
                None
            )
            closing = line.closing
            if inst_match is None or closing <= 0:
                lt_total += closing
                continue

            # Rule 1: RC always current
            if inst_match.is_revolving:
                line.is_st = True
                st_total += closing
                continue

            # Rule 2: Matures next year → full balance is current portion
            if inst_match.maturity is not None and inst_match.maturity == year + 1:
                line.is_st = True
                st_total += closing
                continue

            # Rule 3: Scheduled amortization next year → partial current/non-current split
            next_mandatory = _nz(inst_match.amort_schedule.get(year + 1, 0))
            if next_mandatory > 0:
                current_portion = min(next_mandatory, closing)
                line.is_st = True
                st_total += current_portion
                lt_total += max(0.0, closing - current_portion)
                continue

            # Rule 4: Covenant acceleration — callable instrument + breach → full current
            if inst_match.instrument_id in _breach:
                line.is_st = True
                st_total += closing
                continue

            # Default: non-current (LT)
            lt_total += closing

        # ── ШАГ 7: CFF ───────────────────────────────────────────────────────
        cff_debt = 0.0
        for idx, line in enumerate(lines):
            cff_debt += line.draw + line.refi_draw - line.repay

        return DebtSolveResult(
            lines=lines,
            cff_debt=cff_debt,
            st_debt=st_total,
            lt_debt=lt_total,
            interest_expense_total=total_interest,
            new_instruments=new_instruments if rm == "new" else [],
        )


# ─── Simple corkscrew struct (для schedule_based) ─────────────────────────────

@dataclass
class InstrumentLine:
    instrument_id:  str
    opening:        float = 0.0
    draw:           float = 0.0
    repay_mandatory:float = 0.0
    repay_voluntary:float = 0.0
    interest:       float = 0.0
    closing:        Optional[float] = None
    classification: str = "LT"
    is_revolving:   bool = False

    def solve(self) -> "InstrumentLine":
        self.closing = max(0.0,
            self.opening + self.draw - self.repay_mandatory - self.repay_voluntary
        )
        return self

    @property
    def is_st(self) -> bool:
        return self.classification == "ST" or self.is_revolving


@dataclass
class DebtBlock:
    """Простой corkscrew из готового schedule (для schedule_based режима)."""
    lines: List[InstrumentLine] = field(default_factory=list)

    def add(self, line: InstrumentLine) -> None:
        self.lines.append(line)

    def solve(self) -> "DebtBlock":
        for line in self.lines:
            if line.closing is None:
                line.solve()
        return self

    @property
    def total_st(self) -> float:
        return sum(l.closing or 0 for l in self.lines if l.is_st)

    @property
    def total_lt(self) -> float:
        return sum(l.closing or 0 for l in self.lines if not l.is_st)

    @property
    def total_debt(self) -> float:
        return self.total_st + self.total_lt

    @property
    def total_interest(self) -> float:
        return sum(l.interest for l in self.lines)

    @property
    def total_draws(self) -> float:
        return sum(l.draw for l in self.lines)

    @property
    def total_repayments(self) -> float:
        return sum(l.repay_mandatory + l.repay_voluntary for l in self.lines)

    def validate(self, tol: float = 1.0) -> Tuple[bool, List[str]]:
        issues = []
        for line in self.lines:
            if line.closing is not None:
                expected = (line.opening + line.draw
                           - line.repay_mandatory - line.repay_voluntary)
                if abs(line.closing - expected) > tol:
                    issues.append(f"{line.instrument_id}: {line.closing:.0f} ≠ {expected:.0f}")
                if line.closing < -tol:
                    issues.append(f"{line.instrument_id}: closing < 0")
        return len(issues) == 0, issues

    @classmethod
    def from_schedule(cls, instruments, year: int) -> "DebtBlock":
        block = cls()
        for inst in instruments:
            if not inst.schedule or year not in inst.schedule:
                continue
            row = inst.schedule[year]
            line = InstrumentLine(
                instrument_id=inst.instrument_id,
                opening=float(row.get("opening_balance", 0) or 0),
                draw=float(row.get("draw", 0) or 0),
                repay_mandatory=float(row.get("repay_mandatory", 0) or 0),
                repay_voluntary=float(row.get("repay_voluntary", 0) or 0),
                interest=float(row.get("interest_expense", 0) or 0),
                closing=float(row.get("closing_balance", 0) or 0),
                classification=str(row.get("classification", "LT")).upper(),
                is_revolving=inst.is_revolving,
            )
            block.add(line)
        return block
