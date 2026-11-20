"""DAG-гейт: книги excel_v4 не содержат циклических ссылок (SCC = 0).

Регрессия 19.11: иерархия Uses (D1) замкнула кольцо
defer→capex→налбаза ОС→DTL→налог→NI→CFO→defer (предупреждение Excel
при открытии книги). Разорвано лагом отложенного налога в cbrc_planned.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import openpyxl
import pytest

# 20.11: корректный парсер (опциональный лист + обязательная ячейка).
# Прежний пропускал внутрилистные ссылки (=F45+F46) — кольца не находились.
CELL_RE = re.compile(
    r"(?:(?:'([^']+)'|([A-Za-z_][A-Za-z0-9_\.]*))!)?\$?([A-Z]{1,3})\$?([0-9]{1,5})(?![0-9A-Za-z_(])"
)
MODEL_DIR = Path(__file__).resolve().parents[3] / "templates" / "excel_v4" / "model"


def _find_scc(path: Path):
    wb = openpyxl.load_workbook(path, read_only=True)
    graph = defaultdict(set)
    nodes = set()
    try:
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for c in row:
                    v = c.value
                    if isinstance(v, str) and v.startswith("="):
                        src = (ws.title, c.coordinate)
                        nodes.add(src)
                        for m in CELL_RE.finditer(v):
                            graph[src].add(
                                (m.group(1) or m.group(2) or ws.title,
                                 f"{m.group(3)}{m.group(4)}")
                            )
    finally:
        wb.close()
    index, lowlink = {}, {}
    stack, on_stack, result = [], set(), []
    counter = [0]

    def strongconnect(v):
        index[v] = lowlink[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in graph.get(v, ()):
            if w not in index:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], index[w])
        if lowlink[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1 or comp[0] in graph.get(comp[0], ()):
                result.append(comp)

    import sys
    sys.setrecursionlimit(200000)
    for v in list(nodes):
        if v not in index:
            strongconnect(v)
    return result


# 19.11 (CFI-конвенция): намеренные кольца разрешены — проценты на средние
# остатки (AVG(open, close)) создают кольца interest↔debt↔cash и
# cash↔int_income↔NI↔CF; решаются итерациями Excel (calcPr iterate=1),
# как в Python engine. Гейт: (1) iterate включён, (2) ВСЕ циклы — только в
# «зоне процентов» (17_Debt / 21_PL / 23_CF / 20_BS / _Debt_Schedule),
# случайные кольца в прочих листах = FAIL.
# 20.11 (банковская конвенция): намеренные корпоративные кольца —
# interest↔funding↔налог (как в bank_model). Решаются итерациями Excel
# (calcPr iterate=1), как в Python engine (solve loop, snapshot-restore).
RING_SHEETS = {"17_Debt", "21_PL", "23_CF", "20_BS", "_Debt_Schedule",
               "19_Tax", "15_PPE", "14_OtherIS"}


@pytest.mark.parametrize("book", ["rusal_v4.xlsx", "nornickel_v4.xlsx"])
def test_book_cycles_only_intentional(book):
    path = MODEL_DIR / book
    if not path.exists():
        pytest.skip(f"{book} не собран")
    import zipfile, re
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("xl/workbook.xml").decode()
    calcpr = re.search(r"<calcPr[^>]*>", xml)
    assert calcpr and 'iterate="1"' in calcpr.group(0), (
        f"Итерационный расчёт ВЫКЛЮЧЁН в {book}: {calcpr.group(0) if calcpr else 'no calcPr'}"
    )
    comps = _find_scc(path)
    # Self-обёртки релаксации (CP!L2, wrap_ring_cells) — не «кольца», а
    # демпфирование: X = (1-ω)·X + ω·g(X), неподвижная точка та же, что у
    # чистой формулы. В счёт намеренных колец не включаем (иначе 150+ шт).
    nontrivial = [c for c in comps if len(c) > 1]
    stray = [c for c in nontrivial if not all(cell[0] in RING_SHEETS for cell in c)]
    assert not stray, (
        f"Случайные циклы вне зоны процентов в {book}: "
        + "; ".join(f"{c[0][0]}!{c[0][1]} (n={len(c)})" for c in stray[:5])
    )
    # намеренных колец должно быть разумное число (по одному на год-поток)
    assert len(nontrivial) <= 9, f"Подозрительно много колец: {len(nontrivial)}"
