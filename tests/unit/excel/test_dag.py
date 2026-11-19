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

CELL_RE = re.compile(
    r"(?:'([^']+)'|([A-Za-z0-9_\.]+))!?\$?([A-Z]{1,3})\$?([0-9]{1,5})"
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


@pytest.mark.parametrize("book", ["rusal_v4.xlsx", "nornickel_v4.xlsx"])
def test_book_is_dag(book):
    path = MODEL_DIR / book
    if not path.exists():
        pytest.skip(f"{book} не собран")
    comps = _find_scc(path)
    assert not comps, (
        f"Циклические ссылки в {book}: "
        + "; ".join(f"{c[0][0]}!{c[0][1]} (n={len(c)})" for c in comps[:5])
    )
