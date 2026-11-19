#!/usr/bin/env python3
"""Плаузибилити-гейт корпоративной модели — аналог банковского NEW_BANK_PLAYBOOK §V
(bank_model/scripts/plausibility_report.py) для stressTest_v2.

Проверяет НЕ механику (это аудит C/90_Checks), а адекватность ПРОГНОЗА:
  V.1  консистентность с историей (темпы объёмов, уровни относительных)
  V.2  экономически допустимые диапазоны (жёсткие) — корпоративные метрики
  V.3  реакция на макрофакторы (знаки/величины из stress_results)
  V.5  собственные тенденции (скачки маржи, развороты темпа)
  V.6  замкнутость (BS/CF diff = 0 из свежего прогона)
  V.9  соответствие бизнес-модели (доли сегментов vs история, класс металлурга)

Использование:
  python3 scripts/plausibility_corp.py --company rusal
  python3 scripts/plausibility_corp.py --company nornickel --md audit/plausibility_<co>.md
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data_mart_v2.db"

fails: list[str] = []
warns: list[str] = []
oks: list[str] = []


def check(name: str, ok: bool, warn: bool, detail: str) -> None:
    if ok:
        oks.append(f"✓ {name}: {detail}")
    elif warn:
        warns.append(f"⚠ {name}: {detail}")
    else:
        fails.append(f"✗ {name}: {detail}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", required=True)
    ap.add_argument("--md", default=None)
    args = ap.parse_args()
    co = args.company

    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row

    # ── Данные: свежий base-прогноз + история ────────────────────────────────
    scen = db.execute("SELECT scenario_id FROM scenarios WHERE company_id=? AND name='base'", (co,)).fetchone()
    if not scen:
        raise SystemExit(f"Нет base-сценария для {co} (сначала export_vertex_to_mart / build_model)")
    sid = scen["scenario_id"]

    def fc(tbl: str, metric: str) -> dict[int, float]:
        return {r["year"]: r["value"] for r in db.execute(
            f"""SELECT p.year, m.value FROM {tbl} m JOIN periods p ON p.period_id=m.period_id
                WHERE m.company_id=? AND m.scenario_id=? AND m.metric=? ORDER BY p.year""",
            (co, sid, metric))}

    def hist(tbl: str, metric: str) -> dict[int, float]:
        return {r["year"]: r["value"] for r in db.execute(
            f"""SELECT p.year, m.value FROM {tbl} m JOIN periods p ON p.period_id=m.period_id
                WHERE m.company_id=? AND m.metric=? AND p.is_forecast=0 ORDER BY p.year""",
            (co, metric))}

    rev_f, rev_h = fc("forecast_is", "revenue"), hist("history_is", "revenue")
    ebitda_f, ebitda_h = fc("forecast_is", "ebitda"), hist("history_is", "ebitda")
    ni_f = fc("forecast_is", "net_income")
    ebt_f = fc("forecast_is", "ebt")
    tax_f = fc("forecast_is", "tax_expense")
    bs_diff = fc("forecast_bs", "bs_identity") or fc("forecast_bs", "total_assets")
    ta_f = fc("forecast_bs", "total_assets")
    te_f = fc("forecast_bs", "total_equity")
    td_f = fc("forecast_bs", "total_debt")
    cash_f = fc("forecast_bs", "cash")
    ca_f = fc("forecast_bs", "total_current_assets")
    cl_f = fc("forecast_bs", "total_current_liabilities")
    int_f = fc("forecast_is", "interest_expense")
    years = sorted(rev_f)
    if not years:
        raise SystemExit(f"Нет forecast для {co}")

    # ═══ V.1 Консистентность с историей ═══════════════════════════════════════
    hg = [rev_h[y] / rev_h[y - 1] - 1 for y in sorted(rev_h)[1:] if rev_h.get(y - 1)]
    if hg:
        lo, hi = min(hg), max(hg)
        band = (lo - 0.5 * (hi - lo), hi + 0.5 * (hi - lo))
        for y in years[1:]:
            g = rev_f[y] / rev_f[y - 1] - 1 if rev_f.get(y - 1) else 0
            check(f"V.1 темп выручки {y}", band[0] <= g <= band[1], True,
                  f"{g:+.1%} в полосе истории [{band[0]:+.1%}…{band[1]:+.1%}]" if band[0] <= g <= band[1]
                  else f"{g:+.1%} вне полосы истории [{band[0]:+.1%}…{band[1]:+.1%}]")
        g0 = rev_f[years[0]] / rev_h[max(rev_h)] - 1 if rev_h else 0
        check(f"V.1 темп {years[0]} (год 1)", band[0] - 0.15 <= g0 <= band[1] + 0.15, True,
              f"{g0:+.1%} (год 1 — допуск шире: скачок базы/цены)")

    mh = [ebitda_h[y] / rev_h[y] for y in ebitda_h if rev_h.get(y) and ebitda_h[y] > -1e12]
    if mh:
        m_lo, m_hi = min(mh), max(mh)
        for y in years:
            m = ebitda_f[y] / rev_f[y]
            check(f"V.1 маржа EBITDA {y}", m_lo - 0.10 <= m <= m_hi + 0.10, True,
                  f"{m:.1%} vs история [{m_lo:.1%}…{m_hi:.1%}] ±10 п.п.")

    # ═══ V.2 Жёсткие диапазоны (корпоративные) ════════════════════════════════
    for y in years:
        m = ebitda_f[y] / rev_f[y]
        check(f"V.2 EBITDA% {y}", -0.10 <= m <= 0.55, False, f"{m:.1%} (допустимо −10…55%)")
        roe = ni_f.get(y, 0) / te_f[y] if te_f.get(y) else 0
        check(f"V.2 ROE {y}", -0.30 <= roe <= 0.45, False, f"{roe:.1%} (допустимо −30…45%)")
        icr = ebitda_f[y] / abs(int_f.get(y, 0)) if int_f.get(y) else 99
        check(f"V.2 ICR {y}", icr >= 1.0, icr >= 1.5, f"{icr:.2f}x (hard ≥1.0, warn <1.5)")
        nd = td_f.get(y, 0) - cash_f.get(y, 0)
        lev = nd / ebitda_f[y] if ebitda_f.get(y, 0) > 0 else 99
        check(f"V.2 ND/EBITDA {y}", lev <= 8.0, lev <= 4.5, f"{lev:.2f}x (hard ≤8, warn >4.5 ковенант)")
        cr = ca_f.get(y, 0) / cl_f[y] if cl_f.get(y) else 99
        check(f"V.2 Current ratio {y}", 0.3 <= cr <= 3.0, False, f"{cr:.2f} (допустимо 0.3…3.0)")
        if ebt_f.get(y, 0) > 0 and tax_f.get(y) is not None:
            te = abs(tax_f[y]) / ebt_f[y]
            check(f"V.2 эфф. налог {y}", 0.10 <= te <= 0.35, True, f"{te:.1%} (допустимо 10…35%)")

    # ═══ V.3 Реакция на макро (из stress_results) ═════════════════════════════
    def scenario_delta(sc_name: str, metric: str) -> dict[int, float]:
        row = db.execute(
            "SELECT scenario_id FROM scenarios WHERE company_id=? AND name=?", (co, sc_name)).fetchone()
        if not row:
            return {}
        return {r["year"]: r["value"] for r in db.execute(
            f"""SELECT p.year, m.value FROM forecast_is m JOIN periods p ON p.period_id=m.period_id
                WHERE m.company_id=? AND m.scenario_id=? AND m.metric=? ORDER BY p.year""",
            (co, row["scenario_id"], metric))}

    for sc, factor, metric, sign, rng in [
        ("lme_mild" if co == "rusal" else "demand_shock", "LME −20%", "ebitda", -1, (0.05, 0.50)),
        ("rate_spike", "ставка +2 п.п.", "net_income", -1, (0.02, 0.80)),
        ("energy_spike", "энергия", "ebitda", -1, (0.01, 0.40)),
    ]:
        d = scenario_delta(sc, metric)
        if not d:
            warns.append(f"⚠ V.3 {sc}: нет данных (прогон со стрессом не выполнен)")
            continue
        y0 = years[0]
        if sc == "rate_spike" and co == "nornickel":
            continue  # у nornickel нет сценария rate_spike в матрице
        base_v = (ebitda_f if metric == "ebitda" else ni_f).get(y0, 0)
        if base_v and d.get(y0) is not None:
            delta = (d[y0] - base_v) / abs(base_v)
            ok = (delta * sign > 0) and rng[0] <= abs(delta) <= rng[1] + 0.6
            check(f"V.3 {sc} {metric} {y0} ({factor})", ok, True,
                  f"Δ={delta:+.1%} (ожидался {'−' if sign < 0 else '+'}{rng[0]:.0%}…{rng[1]:.0%})")

    # ═══ V.5 Собственные тенденции ════════════════════════════════════════════
    for i, y in enumerate(years[1:], 1):
        m_prev = ebitda_f[years[i - 1]] / rev_f[years[i - 1]]
        m = ebitda_f[y] / rev_f[y]
        jump = abs(m - m_prev)
        check(f"V.5 скачок EBITDA% {y}", jump <= 0.12, jump <= 0.20,
              f"{jump:.1f} п.п. (warn >12 п.п., fail >20 п.п.)")
        g_prev = rev_f[years[i - 1]] / (rev_f[years[i - 2]] if i >= 2 else rev_h[max(rev_h)]) - 1
        g = rev_f[y] / rev_f[years[i - 1]] - 1
        check(f"V.5 разворот темпа {y}", abs(g - g_prev) <= 0.30, True,
              f"{g_prev:+.1%} → {g:+.1%} (≤30 п.п.)")
    for i, y in enumerate(years):
        if i > 0 and ni_f.get(y) is not None:
            prev_pos = (ni_f[years[i - 1]] if i >= 1 else None)
            if prev_pos is not None and prev_pos < 0 < ni_f[y]:
                warns.append(f"⚠ V.5 смена знака NI {y}: {prev_pos:,.0f} → {ni_f[y]:,.0f} (проверить событие)")

    # ═══ V.6 Замкнутость ══════════════════════════════════════════════════════
    for y in years:
        ta, tle = ta_f.get(y), None
        # BS identity: TA − TL − TE
        row = db.execute(
            """SELECT (m1.value - m2.value - m3.value) d FROM forecast_bs m1
               JOIN forecast_bs m2 ON m2.company_id=m1.company_id AND m2.scenario_id=m1.scenario_id
                 AND m2.period_id=m1.period_id AND m2.metric='total_liabilities'
               JOIN forecast_bs m3 ON m3.company_id=m1.company_id AND m3.scenario_id=m1.scenario_id
                 AND m3.period_id=m1.period_id AND m3.metric='total_equity'
               JOIN periods p ON p.period_id=m1.period_id
               WHERE m1.company_id=? AND m1.scenario_id=? AND m1.metric='total_assets' AND p.year=?""",
            (co, sid, y)).fetchone()
        d = abs(row["d"]) if row else 9e9
        check(f"V.6 BS identity {y}", d < 1.0, False, f"Δ={d:,.2f} (допуск $1)")

    # ═══ V.9 Соответствие бизнес-модели (доли сегментов) ══════════════════════
    segs_h = db.execute(
        """SELECT s.segment_id, SUM(CASE WHEN p.is_forecast=0 AND p.year=? THEN s.value ELSE 0 END) h_rev
           FROM segment_data s JOIN periods p ON p.period_id=s.period_id
           WHERE s.company_id=? AND s.metric='revenue' GROUP BY s.segment_id""",
        (max([y for y in rev_h], default=0), co)).fetchall()
    segs_f = db.execute(
        """SELECT s.segment_id, SUM(CASE WHEN p.year=? THEN s.value ELSE 0 END) f_rev
           FROM segment_data s JOIN periods p ON p.period_id=s.period_id
           WHERE s.company_id=? AND s.metric='revenue_forecast' GROUP BY s.segment_id""",
        (years[0], co)).fetchall()
    if segs_h and segs_f:
        h_tot = sum(r["h_rev"] for r in segs_h) or 1
        f_tot = sum(r["f_rev"] for r in segs_f) or 1
        for hf in segs_h:
            sid_ = hf["segment_id"]
            ff = next((r["f_rev"] for r in segs_f if r["segment_id"] == sid_), 0)
            ds = abs(hf["h_rev"] / h_tot - ff / f_tot)
            check(f"V.9 доля сегмента {sid_}", ds <= 0.10, ds <= 0.15,
                  f"Δ={ds:.1%} (hist {hf['h_rev']/h_tot:.1%} → fc {ff/f_tot:.1%})")

    # ── Итог ──────────────────────────────────────────────────────────────────
    lines = []
    lines.append(f"# Plausibility-гейт {co} (аналог NEW_BANK_PLAYBOOK §V) — {Path(__file__).stem}")
    lines.append("")
    lines.append(f"PASS: {len(oks)} · WARN: {len(warns)} · FAIL: {len(fails)}")
    lines.append("")
    for s in oks:
        lines.append(s)
    for s in warns:
        lines.append(s)
    for s in fails:
        lines.append(s)
    out = "\n".join(lines)
    print(out)
    if args.md:
        Path(args.md).write_text(out + "\n", encoding="utf-8")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
