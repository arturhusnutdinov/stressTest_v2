"""
Кредитный рейтинг v2.

Методологии: S&P, Moody's, Fitch, Internal.
Типы: Base (история), Forecast (прогноз), Stress (стресс).

Алгоритм:
1. Рассчитываем кредитные метрики из YearState
2. Нормируем метрики в скоры [0-100] — стальные пороги
3. Взвешенная сумма → итоговый скор
4. Отраслевые корректировки (cyclicality, size)
5. Маппинг скора → рейтинговая категория

Калибровка:
  US Steel 2024 actual: BB+ (S&P) / Ba1 (Moody's)
  Основная причина разрыва с финансовыми моделями:
  - Агентства используют through-the-cycle нормализацию
  - Применяют отраслевой дисконт за цикличность (сталь = high beta)
  - Учитывают качественные факторы (event risk, M&A, pension)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from engine.constants import RATING_MARGIN_NORM_CAP, RATING_CYCLE_AVG_MARGIN_DEFAULT

logger = logging.getLogger(__name__)


# ── Рейтинговые шкалы ──────────────────────────────────────────────────────────

SP_SCALE = [
    "AAA", "AA+", "AA", "AA-",
    "A+", "A", "A-",
    "BBB+", "BBB", "BBB-",
    "BB+", "BB", "BB-",
    "B+", "B", "B-",
    "CCC+", "CCC", "CCC-",
    "CC", "C", "D",
]

MOODYS_SCALE = [
    "Aaa", "Aa1", "Aa2", "Aa3",
    "A1", "A2", "A3",
    "Baa1", "Baa2", "Baa3",
    "Ba1", "Ba2", "Ba3",
    "B1", "B2", "B3",
    "Caa1", "Caa2", "Caa3",
    "Ca", "C",
]


def score_to_sp(score: float) -> str:
    """Числовой скор [0-100] → S&P рейтинг. 100 = AAA, 0 = D."""
    idx = max(0, min(len(SP_SCALE) - 1, int((100 - score) / 100 * (len(SP_SCALE) - 1))))
    return SP_SCALE[idx]


# ── Национальная шкала (маппинг international → RU) ──────────────────────────

# Суверенный рейтинг РФ по международной шкале = BBB+ = индекс 6 в SP_SCALE
# По национальной шкале суверен = AAA(RU)
# Маппинг: intl_notch + uplift_notches = national_notch (с потолком AAA)
# uplift = SP_SCALE.index("BBB+") = 6 нотчей (BBB+ → AAA = 6 ступеней)

# Национальная шкала (АКРА / Expert RA / НРА / НКР)
RU_NATIONAL_SCALE = [
    "AAA(RU)", "AA+(RU)", "AA(RU)", "AA-(RU)",
    "A+(RU)", "A(RU)", "A-(RU)",
    "BBB+(RU)", "BBB(RU)", "BBB-(RU)",
    "BB+(RU)", "BB(RU)", "BB-(RU)",
    "B+(RU)", "B(RU)", "B-(RU)",
    "CCC(RU)", "CC(RU)", "C(RU)", "D(RU)",
]


def intl_to_national(
    intl_rating: str,
    sovereign_intl: str = "BBB+",
) -> str:
    """
    Конвертирует международный рейтинг в национальную шкалу РФ.

    Логика: суверенный рейтинг РФ (BBB+ intl) = AAA по национальной шкале.
    Каждый нотч ниже суверена в intl шкале = один нотч ниже в national шкале.
    Рейтинг выше суверена невозможен → потолок AAA(RU).

    Пример: BBB+ intl → AAA(RU), B+ intl → A+(RU), CCC intl → BB(RU)
    """
    try:
        intl_idx = SP_SCALE.index(intl_rating)
    except ValueError:
        return "NR(RU)"
    try:
        sov_idx = SP_SCALE.index(sovereign_intl)
    except ValueError:
        sov_idx = 6  # BBB+ default

    # Сколько нотчей ниже суверена
    notches_below_sov = intl_idx - sov_idx
    # В national шкале: 0 = AAA(RU)
    national_idx = max(0, notches_below_sov)
    national_idx = min(national_idx, len(RU_NATIONAL_SCALE) - 1)
    return RU_NATIONAL_SCALE[national_idx]


def score_to_moodys(score: float) -> str:
    """Числовой скор [0-100] → Moody's рейтинг."""
    idx = max(0, min(len(MOODYS_SCALE) - 1, int((100 - score) / 100 * (len(MOODYS_SCALE) - 1))))
    return MOODYS_SCALE[idx]


def sp_to_numeric(rating: str) -> int:
    """S&P рейтинг → число (AAA=1, D=22)."""
    try:
        return SP_SCALE.index(rating) + 1
    except ValueError:
        return 15  # B+ как дефолт


def is_investment_grade(rating: str) -> bool:
    """BBB- и выше = investment grade."""
    try:
        return SP_SCALE.index(rating) <= SP_SCALE.index("BBB-")
    except ValueError:
        return False


# ── Метрики ─────────────────────────────────────────────────────────────────────

@dataclass
class CreditMetrics:
    """Кредитные метрики для одного года."""
    year: int

    # Leverage
    net_debt_ebitda:    Optional[float] = None  # <2x = strong, >5x = weak
    debt_to_equity:     Optional[float] = None
    debt_to_capital:    Optional[float] = None

    # Coverage
    interest_coverage:  Optional[float] = None  # EBIT/Interest, >5x = strong
    ebitda_coverage:    Optional[float] = None  # EBITDA/Interest
    dscr:               Optional[float] = None  # EBITDA/(Int+Princ)

    # Profitability
    ebitda_margin:      Optional[float] = None  # >15% = strong
    ebit_margin:        Optional[float] = None
    net_margin:         Optional[float] = None
    roa:                Optional[float] = None  # NI/Assets

    # Liquidity
    current_ratio:      Optional[float] = None  # >1.5 = adequate
    cash_to_debt:       Optional[float] = None  # >0.2 = adequate
    fcf_to_debt:        Optional[float] = None  # FCF/Total Debt

    # Cash Flow
    cfo_to_debt:        Optional[float] = None
    fcf:                Optional[float] = None

    # Absolute values for TTC normalization
    revenue:            Optional[float] = None
    ebitda:             Optional[float] = None

    @classmethod
    def from_year_state(cls, state, year: int) -> "CreditMetrics":
        """Вычисляет метрики из YearState."""
        total_debt = abs(state.short_term_debt or 0) + abs(state.long_term_debt or 0)
        cash       = abs(state.cash or 0)
        net_debt   = total_debt - cash
        ebitda     = state.ebitda or 0
        ebit       = state.ebit or 0
        revenue    = state.revenue or 0
        assets     = state.total_assets or 0
        equity     = state.total_equity or 0
        int_exp    = state.interest_expense or 0
        ni         = state.net_income or 0
        cfo        = state.cfo_total or 0
        capex      = state.cfi_capex or 0
        ca         = state.total_ca or 0
        cl         = state.total_cl or 0
        fcf        = cfo + capex  # capex уже отрицательный

        def safe_div(a, b, default=None):
            if b and abs(b) > 1e-6 and a is not None:
                return a / b
            return default

        return cls(
            year=year,
            # Leverage
            net_debt_ebitda   = safe_div(net_debt, ebitda),
            debt_to_equity    = safe_div(total_debt, equity),
            debt_to_capital   = safe_div(total_debt, total_debt + equity),
            # Coverage — S&P uses EBITDA/Int for metals/mining (EBIT also tracked)
            interest_coverage = safe_div(ebit, abs(int_exp)),
            ebitda_coverage   = safe_div(ebitda, abs(int_exp)),
            # Profitability
            ebitda_margin     = safe_div(ebitda, revenue),
            ebit_margin       = safe_div(ebit, revenue),
            net_margin        = safe_div(ni, revenue),
            roa               = safe_div(ni, assets),
            # Liquidity
            current_ratio     = safe_div(ca, cl),
            cash_to_debt      = safe_div(cash, total_debt),
            fcf_to_debt       = safe_div(fcf, total_debt),
            # Cash Flow
            cfo_to_debt       = safe_div(cfo, total_debt),
            fcf               = fcf,
            # Absolute values for TTC
            revenue           = revenue,
            ebitda            = ebitda,
        )

    def summary(self) -> str:
        return (
            f"  Net Debt/EBITDA: {self.net_debt_ebitda:.1f}x  "
            f"EBITDA Cov: {self.ebitda_coverage:.1f}x  "
            f"EBITDA%: {(self.ebitda_margin or 0)*100:.1f}%  "
            f"Curr: {self.current_ratio:.1f}x"
        )


# ── Методология рейтинга ────────────────────────────────────────────────────────

@dataclass
class RatingConfig:
    """Настройки методологии рейтинга."""
    methodology: str = "sp"
    # Отраслевой дисконт: сталь = высокая цикличность, commodity exposure
    # BB+ компании имеют типичный ND/EBITDA 2.5-4x, ICR 3-5x
    industry_adjustment: float = -12.0   # баллов дисконта для цикличных отраслей (steel: -12)
    # Корректировка за размер/рыночную позицию (крупный интегрированный производитель)
    size_adjustment: float = 2.0
    # Through-the-cycle (through_the_cycle): нормализованная EBITDA маржа (историческое среднее 2018-2024)
    cycle_avg_ebitda_margin: float = RATING_CYCLE_AVG_MARGIN_DEFAULT   # 10% for US Steel
    # Суверенный рейтинг для маппинга international → national шкала
    sovereign_rating: str = "BBB+"  # РФ по международной шкале

    @property
    def cycle_avg_margin(self) -> float:
        """Alias: through_the_cycle normalised EBITDA margin."""
        return self.cycle_avg_ebitda_margin
    weights: Dict[str, float] = field(default_factory=lambda: {
        "leverage":      0.35,   # ключевой фактор для стали
        "coverage":      0.30,
        "profitability": 0.20,
        "liquidity":     0.15,
    })


class RatingEngine:
    """
    Вычисляет кредитный рейтинг из CreditMetrics.

    Логика скоринга (стальная калибровка):
    - Каждая категория → скор 0-100
    - Взвешенная сумма → итоговый скор 0-100
    - Отраслевые/размерные корректировки
    - Скор → рейтинговая категория

    Пороги S&P для стали (через-цикл, metals/mining методология):
    - Net Debt/EBITDA: <1.5 = A, 1.5-2.5 = BBB, 2.5-3.5 = BB+, 3.5-5.0 = BB, >5 = B
    - EBITDA/Int:      >8 = A, 5-8 = BBB, 3-5 = BB+, 2-3 = BB, <2 = B/CCC
    - EBITDA%:         >18% = A, 12-18% = BBB, 8-12% = BB, 5-8% = B
      (нормализуется к through-the-cycle среднему)
    """

    def __init__(self, config: Optional[RatingConfig] = None):
        self.config = config or RatingConfig()

    def score_leverage(self, m: CreditMetrics) -> float:
        """
        Скор левериджа 0-100.

        Стальная калибровка S&P (metals/mining):
        - Агентства смотрят на ND/EBITDA через цикл
        - BB+ компании: 2.5-4.0x (текущий цикл)
        - BBB- компании: 1.5-2.5x
        - Порог IG/HY для стали: ~2.5-3.0x
        """
        scores = []

        if m.net_debt_ebitda is not None:
            # TTC normalization: use cycle-average EBITDA margin to prevent
            # artificially low ND/EBITDA at cycle peaks (S&P metals/mining methodology)
            _cycle_margin = self.config.cycle_avg_ebitda_margin
            if _cycle_margin > 0 and m.ebitda_margin and m.revenue:
                _cycle_ebitda = m.revenue * _cycle_margin
                _net_debt = (m.net_debt_ebitda or 0) * (m.ebitda or 1)
                nd = _net_debt / _cycle_ebitda if _cycle_ebitda > 0 else m.net_debt_ebitda
            else:
                nd = m.net_debt_ebitda
            # Стальная шкала: учитывает более высокий "нормальный" леверидж в отрасли
            if nd < 0:      s = 88   # чистый кэш (редко для стали)
            elif nd < 0.5:  s = 80   # очень низкий долг
            elif nd < 1.0:  s = 72   # сильный BBB/A-
            elif nd < 1.5:  s = 63   # BBB
            elif nd < 2.0:  s = 55   # BBB-
            elif nd < 2.5:  s = 47   # BB+
            elif nd < 3.0:  s = 40   # BB+/BB
            elif nd < 3.5:  s = 33   # BB
            elif nd < 4.5:  s = 24   # BB-/B+
            elif nd < 6.0:  s = 14   # B
            else:            s = 5   # CCC
            scores.append(s)

        if m.debt_to_equity is not None:
            de = m.debt_to_equity
            # Стальная калибровка: высокий D/E нормален в капиталоёмкой отрасли
            if de < 0.3:    s = 82
            elif de < 0.7:  s = 68
            elif de < 1.0:  s = 54
            elif de < 1.5:  s = 40
            elif de < 2.5:  s = 25
            else:            s = 10
            scores.append(s)

        return sum(scores) / len(scores) if scores else 50.0

    def score_coverage(self, m: CreditMetrics) -> float:
        """
        Скор покрытия 0-100.

        S&P для metals/mining использует EBITDA/Interest (а не EBIT/Interest)
        как основной coverage метрик, так как высокая амортизация в отрасли
        делает EBIT менее репрезентативным.

        Стальная шкала:
        - EBITDA/Int > 6x  = BBB+
        - EBITDA/Int 4-6x  = BBB/BBB-
        - EBITDA/Int 2.5-4x = BB+/BB
        - EBITDA/Int 1.5-2.5x = BB-/B+
        """
        scores = []

        # EBITDA coverage — основной (S&P metals/mining)
        if m.ebitda_coverage is not None:
            ec = m.ebitda_coverage
            if ec > 10:     s = 88
            elif ec > 7:    s = 74
            elif ec > 5:    s = 62   # BBB zone
            elif ec > 3.5:  s = 52   # BB+/BB zone
            elif ec > 2.5:  s = 42   # BB zone
            elif ec > 1.5:  s = 28   # B+ zone
            elif ec > 1.0:  s = 16
            else:            s = 5
            scores.append(ec)  # placeholder — replaced below

        # EBIT coverage — вторичный (более консервативный)
        if m.interest_coverage is not None:
            icr = m.interest_coverage
            if icr > 8:     s = 82
            elif icr > 5:   s = 65
            elif icr > 3.5: s = 52
            elif icr > 2.5: s = 42
            elif icr > 1.5: s = 28
            elif icr > 1.0: s = 15
            else:            s = 4
            scores.append(s)

        # Переводим EBITDA coverage в скор (заменяем placeholder)
        if m.ebitda_coverage is not None:
            ec = m.ebitda_coverage
            if ec > 10:     ec_score = 88
            elif ec > 7:    ec_score = 74
            elif ec > 5:    ec_score = 62
            elif ec > 3.5:  ec_score = 52
            elif ec > 2.5:  ec_score = 42
            elif ec > 1.5:  ec_score = 28
            elif ec > 1.0:  ec_score = 16
            else:            ec_score = 5
            # Заменяем placeholder значение EBITDA coverage на реальный скор
            scores[0] = ec_score if scores else ec_score

        return sum(scores) / len(scores) if scores else 50.0

    def score_profitability(self, m: CreditMetrics) -> float:
        """
        Скор прибыльности 0-100.

        Через-цикл нормализация:
        Сталь — высококиклична (EBITDA% от 5% до 30%+ в разных фазах).
        S&P нормализует маржу к mid-cycle estimate.
        Берём min(текущая, исторический средний cycle_avg) чтобы не
        завышать рейтинг в пиковые годы.

        Стальная шкала (нормализованная):
        - >15%  = BBB+/A
        - 10-15% = BBB/BBB-
        - 7-10%  = BB+/BB
        - 4-7%   = BB-/B+
        """
        scores = []

        if m.ebitda_margin is not None:
            # Through-the-cycle: нормализуем к cycle_avg если выше среднего
            cycle_avg = self.config.cycle_avg_ebitda_margin
            normalized_margin = min(m.ebitda_margin, cycle_avg * RATING_MARGIN_NORM_CAP)  # cap at 150% of avg
            em = normalized_margin
            if em > 0.20:    s = 82
            elif em > 0.15:  s = 68   # BBB zone
            elif em > 0.10:  s = 55   # BBB-/BB+ zone
            elif em > 0.07:  s = 42   # BB zone
            elif em > 0.04:  s = 28   # B+ zone
            elif em > 0:     s = 14
            else:             s = 3
            scores.append(s)

        if m.roa is not None:
            roa = m.roa
            if roa > 0.08:   s = 80
            elif roa > 0.05: s = 62
            elif roa > 0.02: s = 44
            elif roa > 0:    s = 24
            else:             s = 6
            scores.append(s)

        return sum(scores) / len(scores) if scores else 50.0

    def score_liquidity(self, m: CreditMetrics) -> float:
        """Скор ликвидности 0-100."""
        scores = []

        if m.current_ratio is not None:
            cr = m.current_ratio
            if cr > 2.5:    s = 88
            elif cr > 1.8:  s = 72
            elif cr > 1.3:  s = 56
            elif cr > 1.0:  s = 38
            elif cr > 0.7:  s = 18
            else:            s = 4
            scores.append(s)

        if m.cash_to_debt is not None:
            ctd = m.cash_to_debt
            if ctd > 0.30:   s = 85
            elif ctd > 0.15: s = 65
            elif ctd > 0.08: s = 46
            elif ctd > 0.03: s = 26
            else:             s = 8
            scores.append(s)

        if m.fcf_to_debt is not None:
            fcd = m.fcf_to_debt
            if fcd > 0.25:   s = 85
            elif fcd > 0.12: s = 68
            elif fcd > 0.04: s = 48
            elif fcd > 0:    s = 26
            else:             s = 6
            scores.append(s * 0.8)  # FCF менее вес чем balance sheet metrics

        return sum(scores) / len(scores) if scores else 50.0

    def calculate(self, metrics: CreditMetrics) -> Dict:
        """
        Рассчитывает итоговый рейтинг.

        Корректировки после взвешенной суммы:
        1. industry_adjustment: дисконт за цикличность/commodity exposure
        2. size_adjustment:     бонус за крупный/диверсифицированный производитель

        Returns:
            dict с полями: score, rating, is_investment_grade,
                          sub_scores, metrics_used, adjustments
        """
        w = self.config.weights

        sub_scores = {
            "leverage":      self.score_leverage(metrics),
            "coverage":      self.score_coverage(metrics),
            "profitability": self.score_profitability(metrics),
            "liquidity":     self.score_liquidity(metrics),
        }

        total_weight = sum(w.get(k, 0) for k in sub_scores)
        if total_weight <= 0:
            return {"score": 50.0, "rating": "B+", "error": "zero weights"}

        base_score = sum(
            sub_scores[k] * w.get(k, 0) / total_weight
            for k in sub_scores
        )

        # Отраслевые/размерные корректировки
        industry_adj = getattr(self.config, 'industry_adjustment', 0.0)
        size_adj     = getattr(self.config, 'size_adjustment', 0.0)
        score = max(0.0, min(100.0, base_score + industry_adj + size_adj))

        meth = self.config.methodology
        if meth == "moodys":
            rating = score_to_moodys(score)
        else:
            rating = score_to_sp(score)

        # Национальная шкала (RU) — маппинг через суверенный рейтинг
        sovereign = getattr(self.config, 'sovereign_rating', 'BBB+')
        national = intl_to_national(rating, sovereign) if meth != "moodys" else ""

        return {
            "score":               round(score, 2),
            "base_score":          round(base_score, 2),
            "rating":              rating,
            "rating_national":     national,
            "is_investment_grade": is_investment_grade(rating),
            "numeric":             sp_to_numeric(rating),
            "sub_scores":          {k: round(v, 1) for k, v in sub_scores.items()},
            "adjustments": {
                "industry": industry_adj,
                "size":     size_adj,
            },
            "methodology":         meth,
            "sovereign_rating":    sovereign,
        }
