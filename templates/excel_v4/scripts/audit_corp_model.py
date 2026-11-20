#!/usr/bin/env python3
"""
audit_corp_model.py — аудит корпоративных Excel-моделей (Русал / Норникель)
по «Стандарту верификации финансовых моделей в Excel» (23.10.2026).

Проверки: A (открываемость), B (кэш/сходимость/ошибки), C (тождества),
D (знаки), E (сетка/история), F (параметры), G (эконометрика),
H (формульность), I (сценарии), J (выход).

Режимы:
  --excel   пересчитывать книгу в Microsoft Excel (AppleScript) и сравнивать
            пересчитанные значения с кэшем; требует установленный Excel
  --md      путь к отчёту Markdown

Пример:
  python3 audit_corp_model.py model/rusal_v4.xlsx --excel --md audit_rusal.md
"""
import argparse
import datetime
import json
import math
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter, column_index_from_string


# --------------------------------------------------------------------------
# Excel (AppleScript) helpers
# --------------------------------------------------------------------------

def run_applescript(script: str, timeout: int = 600) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"AppleScript error: {result.stderr.strip()}")
    return result.stdout.strip()


def excel_open(path: str) -> None:
    run_applescript(f'''
        tell application "Microsoft Excel"
            activate
            open POSIX file "{path}"
            delay 3
        end tell
    ''')


def excel_read_cells(pairs) -> dict:
    """Читает список ("Sheet","A1") одной AppleScript-командой. Возвращает {sheet!cell: value}."""
    if not pairs:
        return {}
    list_s = ", ".join(f'"{sh}!{cl}"' for sh, cl in pairs)
    raw = run_applescript(f'''
        tell application "Microsoft Excel"
            set pairs to {{{list_s}}}
            set res to ""
            set AppleScript's text item delimiters to "!"
            repeat with p in pairs
                try
                    set sh to text item 1 of p
                    set cl to text item 2 of p
                    set ws to worksheet sh of workbook 1
                    set v to value of range cl of ws
                    if v is missing value then
                        set res to res & p & "=EMPTY" & linefeed
                    else
                        set res to res & p & "=" & (v as text) & linefeed
                    end if
                on error
                    set res to res & p & "=ERR" & linefeed
                end try
            end repeat
            return res
        end tell
    ''')
    out = {}
    for line in raw.split("\n"):
        line = line.strip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip()
    return out


def parse_num(s):
    s = str(s).strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    if s in ("", "EMPTY", "ERR", "missing value"):
        return None
    try:
        return float(s)
    except ValueError:
        return s


def excel_verify(path: Path, cells, cached_wb) -> dict:
    """Открывает книгу в Excel, пересчитывает, читает ячейки, сверяет с кэшем."""
    excel_open(str(path))
    try:
        run_applescript('''
            tell application "Microsoft Excel"
                repeat 10 times
                    calculate
                end repeat
                delay 2
            end tell
        ''')
        vals = excel_read_cells(cells)
    finally:
        run_applescript('''
            tell application "Microsoft Excel"
                close workbook 1 saving no
            end tell
        ''')
    mismatches = []
    checked = 0
    for sh, cl in cells:
        key = f"{sh}!{cl}"
        excel_val = vals.get(key)
        cached = None
        if sh in cached_wb:
            cached = cached_wb[sh][cl].value
        checked += 1
        if excel_val is None:
            continue
        if isinstance(cached, (int, float)):
            ev = parse_num(excel_val)
            if isinstance(ev, (int, float)):
                if abs(ev - cached) > 1e-6 * max(1.0, abs(cached)):
                    mismatches.append((key, cached, ev))
        elif isinstance(cached, str):
            if str(excel_val) != cached:
                mismatches.append((key, cached, excel_val))
    return {"checked": checked, "mismatches": mismatches}


def excel_close_no_save() -> None:
    run_applescript('''
        tell application "Microsoft Excel"
            close workbook 1 saving no
        end tell
    ''')


def excel_recalc(n: int = 10) -> None:
    run_applescript(f'''
        tell application "Microsoft Excel"
            repeat {n} times
                calculate
            end repeat
            delay 2
        end tell
    ''')


def excel_read_cell(sheet: str, cell: str) -> str:
    return run_applescript(f'''
        tell application "Microsoft Excel"
            set ws to worksheet "{sheet}" of workbook 1
            set v to value of range "{cell}" of ws
            if v is missing value then return "EMPTY"
            return (v as text)
        end tell
    ''')


def excel_set_cell(sheet: str, cell: str, value) -> None:
    run_applescript(f'''
        tell application "Microsoft Excel"
            set ws to worksheet "{sheet}" of workbook 1
            set value of range "{cell}" of ws to {value}
        end tell
    ''')


# --------------------------------------------------------------------------
# XML / архив (группа A)
# --------------------------------------------------------------------------

def check_group_a(path: Path) -> list:
    """A1..A4: архив читается, формулы валидны, нет внешних ссылок."""
    results = []
    # A1
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            xml_files = [n for n in names if n.endswith('.xml')]
            bad = z.testzip()
        results.append(("A1", "PASS" if bad is None else "FAIL",
                        f"архив читается, {len(xml_files)} xml, bad={bad}"))
    except Exception as e:
        results.append(("A1", "FAIL", f"архив не читается: {e}"))
        return results

    wb = openpyxl.load_workbook(path, data_only=False)
    # A2: подозрительные формулы
    n_long = n_deep = n_badname = 0
    suspicious = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("="):
                    f = c.value
                    if len(f) > 8192:
                        n_long += 1
                        suspicious.append(f"{ws.title}!{c.coordinate} len={len(f)}")
                    if "ORG.OPENOFFICE" in f or "LEGACY." in f:
                        n_badname += 1
                        suspicious.append(f"{ws.title}!{c.coordinate} legacy name")
    a2 = "PASS" if not suspicious else "FAIL"
    results.append(("A2", a2, f"длинных/битых формул: {len(suspicious)}" +
                    ("; " + "; ".join(suspicious[:5]) if suspicious else "")))

    # A3a: внешние ссылки TargetMode=External
    external_refs = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("="):
                    if re.search(r"\[\d+\]|'?\[[^\]]+\]", c.value):
                        external_refs.append(f"{ws.title}!{c.coordinate}: {c.value[:80]}")
    results.append(("A3a", "PASS" if not external_refs else "FAIL",
                    f"внешних ссылок: {len(external_refs)}" +
                    ("; " + "; ".join(external_refs[:5]) if external_refs else "")))

    # A3b: ссылки на несуществующие листы
    sheet_names = set(wb.sheetnames)
    missing_sheet_refs = []
    quoted_sheet_re = re.compile(r"(?:'([^']+)'|([A-Za-zА-Яа-я0-9_]+))!\$?[A-Z]{1,3}\$?\d+")
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("="):
                    for m in quoted_sheet_re.finditer(c.value):
                        name = m.group(1) or m.group(2)
                        if name and name not in sheet_names and not name.startswith("_xlfn"):
                            missing_sheet_refs.append(f"{ws.title}!{c.coordinate} -> {name}")
                            break
    results.append(("A3b", "WARN" if missing_sheet_refs else "PASS",
                    f"ссылок на несуществующие листы: {len(missing_sheet_refs)}" +
                    ("; " + "; ".join(missing_sheet_refs[:5]) if missing_sheet_refs else "")))

    # A4: calcPr (для корпората не обязательно, информируем)
    try:
        cp = wb.calculation
        iterate = getattr(cp, "iterate", None)
        full = getattr(cp, "fullCalcOnLoad", None)
        it_count = getattr(cp, "iterateCount", None)
        it_delta = getattr(cp, "iterateDelta", None)
        results.append(("A4", "INFO",
                        f"calcPr: iterate={iterate}, count={it_count}, delta={it_delta}, fullCalcOnLoad={full}"))
    except Exception as e:
        results.append(("A4", "INFO", f"calcPr: {e}"))

    wb.close()
    return results


# --------------------------------------------------------------------------
# Общие данные по книге
# --------------------------------------------------------------------------

def collect_workbook_data(path: Path) -> dict:
    wb = openpyxl.load_workbook(path, data_only=False)
    wbv = openpyxl.load_workbook(path, data_only=True)
    data = {"sheets": {}, "sheet_names": wb.sheetnames}
    for ws in wb.worksheets:
        wsv = wbv[ws.title]
        info = {"n_formulas": 0, "n_values": 0, "n_errors": 0, "n_empty_refs": 0,
                "n_const": 0, "n_text": 0, "rows": ws.max_row, "cols": ws.max_column}
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if v is None:
                    continue
                if isinstance(v, str) and v.startswith("="):
                    info["n_formulas"] += 1
                    cv = wsv[c.coordinate].value
                    if isinstance(cv, str) and cv.startswith("#"):
                        info["n_errors"] += 1
                elif isinstance(v, (int, float)):
                    info["n_const"] += 1
                elif isinstance(v, str):
                    info["n_text"] += 1
        data["sheets"][ws.title] = info
    wb.close()
    wbv.close()
    return data


# --------------------------------------------------------------------------
# Мини-вычислитель формул (B2: самосогласованность кэша)
# --------------------------------------------------------------------------

def parse_a1(a1: str):
    m = re.match(r"([A-Z]+)(\d+)", a1)
    if not m:
        return None, None
    return m.group(1), int(m.group(2))


def col_to_idx(col: str) -> int:
    return column_index_from_string(col) - 1


def resolve_ref(ref: str, sheet: str, wb):
    """Возвращает (sheet, row_idx, col_idx) для A1 / Sheet!A1 / 'Sheet'!A1."""
    ref = ref.strip()
    if "!" in ref:
        sh, _, cell = ref.rpartition("!")
        sh = sh.strip("'")
        if sh == "":
            sh = sheet
    else:
        sh, cell = sheet, ref
    if ":" in cell:
        return None  # диапазон
    col, row = parse_a1(cell)
    if col is None:
        return None
    if sh not in wb:
        return None
    return sh, row, col_to_idx(col)


class SimpleEvaluator:
    """Считает формулы на кэшированных значениях книги.

    Рекурсивный спуск: сравнения < + - < * / < ^ (правоассоц.) < унарный минус.
    Функции: SUM, ABS, IF, MAX, MIN, ROUND, AVERAGE, ссылки и диапазоны.
    """

    FUNC_RE = re.compile(r"([A-Za-zА-Яа-я._]+)\(")
    REF_RE = re.compile(r"^(?:'([^']+)'|([A-Za-zА-Яа-я0-9_]+))?!?\$?([A-Z]+)\$?(\d+)$")
    RANGE_RE = re.compile(r"^(?:'([^']+)'|([A-Za-zА-Яа-я0-9_]+))?!?\$?([A-Z]+)\$?(\d+):\$?([A-Z]+)\$?(\d+)$")

    def __init__(self, wb_values, wb_formulas):
        self.wb = wb_values      # data_only workbook
        self.wbf = wb_formulas   # formula workbook
        self.current_sheet = None
        self.tokens = []
        self.pos = 0

    def get_value(self, sheet, col, row):
        if sheet not in self.wb:
            return None
        ws = self.wb[sheet]
        v = ws.cell(row=row, column=col + 1).value
        if isinstance(v, str) and v.startswith("#"):
            return None
        return v

    def eval_range(self, a1, b1, sheet):
        """Список значений диапазона."""
        ca, ra = parse_a1(a1)
        cb, rb = parse_a1(b1)
        if not ca or not cb:
            return None
        cai, cbi = col_to_idx(ca), col_to_idx(cb)
        if sheet not in self.wb:
            return None
        ws = self.wb[sheet]
        vals = []
        for r in range(ra, rb + 1):
            for c in range(cai, cbi + 1):
                v = ws.cell(row=r, column=c + 1).value
                if v is None:
                    v = 0
                if isinstance(v, str):
                    if v.startswith("#"):
                        return None
                    try:
                        v = float(v)
                    except ValueError:
                        return None
                vals.append(v)
        return vals

    def eval_func(self, name, args, sheet):
        name = name.lower().lstrip("_xlfn.")
        if name == "sum":
            vals = []
            for a in args:
                if isinstance(a, list):
                    vals.extend(a)
                elif isinstance(a, (int, float)):
                    vals.append(a)
                else:
                    return None
            return sum(vals)
        if name == "abs":
            if len(args) != 1 or not isinstance(args[0], (int, float)):
                return None
            return abs(args[0])
        if name == "if":
            if len(args) < 2:
                return None
            cond = args[0]
            if isinstance(cond, bool):
                branch = args[1] if cond else (args[2] if len(args) > 2 else 0)
            elif isinstance(cond, (int, float)):
                branch = args[1] if cond != 0 else (args[2] if len(args) > 2 else 0)
            else:
                return None
            return branch
        if name == "max":
            vals = []
            for a in args:
                if isinstance(a, list):
                    vals.extend(a)
                elif isinstance(a, (int, float)):
                    vals.append(a)
                else:
                    return None
            return max(vals) if vals else None
        if name == "min":
            vals = []
            for a in args:
                if isinstance(a, list):
                    vals.extend(a)
                elif isinstance(a, (int, float)):
                    vals.append(a)
                else:
                    return None
            return min(vals) if vals else None
        if name == "round":
            if len(args) < 1 or not isinstance(args[0], (int, float)):
                return None
            nd = int(args[1]) if len(args) > 1 and isinstance(args[1], (int, float)) else 0
            return round(args[0], nd)
        if name == "average":
            vals = []
            for a in args:
                if isinstance(a, list):
                    vals.extend(a)
                elif isinstance(a, (int, float)):
                    vals.append(a)
                else:
                    return None
            return sum(vals) / len(vals) if vals else None
        return None

    def tokenize(self, s):
        tokens = []
        i = 0
        while i < len(s):
            ch = s[i]
            if ch.isspace():
                i += 1
                continue
            if ch in "+-*/^(),":
                tokens.append((ch, ch))
                i += 1
                continue
            if ch == "=":
                tokens.append(("=", "="))
                i += 1
                continue
            if ch in "><":
                if i + 1 < len(s) and s[i + 1] in "=>":
                    tokens.append((ch + s[i + 1], ch + s[i + 1]))
                    i += 2
                else:
                    tokens.append((ch, ch))
                    i += 1
                continue
            m = re.match(r"\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?", s[i:])
            if m:
                tokens.append(("num", float(m.group(0))))
                i += len(m.group(0))
                continue
            if ch == '"':
                j = s.index('"', i + 1) if '"' in s[i + 1:] else len(s)
                tokens.append(("str", s[i + 1:j]))
                i = j + 1
                continue
            m = re.match(r"(?:'[^']+'|[A-Za-zА-Яа-я0-9_]+)!?\$?[A-Z]+(?:\$?\d+)?(?::\$?[A-Z]+\$?\d+)?", s[i:])
            if m:
                tokens.append(("ref", m.group(0)))
                i += len(m.group(0))
                continue
            m = re.match(r"[A-Za-zА-Яа-я._]+", s[i:])
            if m:
                tokens.append(("name", m.group(0)))
                i += len(m.group(0))
                continue
            tokens.append(("?", ch))
            i += 1
        return tokens

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def next(self):
        t = self.peek()
        self.pos += 1
        return t

    def expect(self, kind):
        t = self.next()
        if t[0] != kind:
            raise ValueError(f"expected {kind}, got {t}")
        return t

    def parse_primary(self, sheet):
        kind, val = self.next()
        if kind == "num":
            return val
        if kind == "str":
            return None
        if kind == "ref":
            rng = self.RANGE_RE.match(val)
            if rng:
                sh = rng.group(1) or rng.group(2) or sheet
                return self.eval_range(rng.group(3) + rng.group(4),
                                       rng.group(5) + rng.group(6), sh)
            ref = self.REF_RE.match(val)
            if ref:
                sh = ref.group(1) or ref.group(2) or sheet
                if sh not in self.wb:
                    return None
                return self.get_value(sh, col_to_idx(ref.group(3)), int(ref.group(4)))
            return None
        if kind == "name":
            fname = val
            if self.peek()[0] == "(":
                self.next()
                args = []
                if self.peek()[0] != ")":
                    while True:
                        args.append(self.parse_compare(sheet))
                        if self.peek()[0] == ",":
                            self.next()
                            continue
                        break
                self.expect(")")
                return self.eval_func(fname, args, sheet)
            return None
        if kind == "(":
            v = self.parse_compare(sheet)
            self.expect(")")
            return v
        return None

    def parse_factor(self, sheet):
        if self.peek()[0] in ("+", "-"):
            op = self.next()[0]
            v = self.parse_factor(sheet)
            if not isinstance(v, (int, float)):
                return None
            return -v if op == "-" else v
        return self.parse_primary(sheet)

    def parse_power(self, sheet):
        v = self.parse_factor(sheet)
        while self.peek()[0] == "^":
            self.next()
            rhs = self.parse_factor(sheet)
            if not isinstance(v, (int, float)) or not isinstance(rhs, (int, float)):
                return None
            try:
                v = v ** rhs
            except Exception:
                return None
        return v

    def parse_term(self, sheet):
        v = self.parse_power(sheet)
        while self.peek()[0] in ("*", "/"):
            op = self.next()[0]
            rhs = self.parse_power(sheet)
            if not isinstance(v, (int, float)) or not isinstance(rhs, (int, float)):
                return None
            if op == "*":
                v = v * rhs
            else:
                if rhs == 0:
                    return None
                v = v / rhs
        return v

    def parse_expression(self, sheet):
        v = self.parse_term(sheet)
        while self.peek()[0] in ("+", "-"):
            op = self.next()[0]
            rhs = self.parse_term(sheet)
            if not isinstance(v, (int, float)) or not isinstance(rhs, (int, float)):
                return None
            v = v + rhs if op == "+" else v - rhs
        return v

    def parse_compare(self, sheet):
        v = self.parse_expression(sheet)
        while self.peek()[0] in ("=", "<>", ">", "<", ">=", "<="):
            op = self.next()[0]
            rhs = self.parse_expression(sheet)
            if not isinstance(v, (int, float)) or not isinstance(rhs, (int, float)):
                return None
            if op == "=":
                v = 1.0 if v == rhs else 0.0
            elif op == "<>":
                v = 1.0 if v != rhs else 0.0
            elif op == ">":
                v = 1.0 if v > rhs else 0.0
            elif op == "<":
                v = 1.0 if v < rhs else 0.0
            elif op == ">=":
                v = 1.0 if v >= rhs else 0.0
            elif op == "<=":
                v = 1.0 if v <= rhs else 0.0
        return v

    def evaluate(self, formula, sheet):
        """Возвращает число/список или None, если формула непокрыта/невычислима."""
        f = formula.strip()
        if not f.startswith("="):
            return None
        f = f[1:].strip()
        if not f:
            return None
        m = re.match(r"(?i)^iferror\((.*),(.*)\)$", f, re.S)
        if m:
            # IFERROR(inner, fallback): если inner невычислим нашим ядром —
            # пропускаем (не подменяем fallback'ом, это даёт ложные расхождения).
            self.tokens = self.tokenize(m.group(1))
            self.pos = 0
            try:
                return self.parse_compare(sheet)
            except Exception:
                return None
        self.tokens = self.tokenize(f)
        self.pos = 0
        try:
            return self.parse_compare(sheet)
        except Exception:
            return None


# --------------------------------------------------------------------------
# Группа B: кэш, самосогласованность, ошибки, пустые ссылки
# --------------------------------------------------------------------------

def check_group_b(path: Path) -> dict:
    wbf = openpyxl.load_workbook(path, data_only=False)
    wbv = openpyxl.load_workbook(path, data_only=True)
    ev = SimpleEvaluator(wbv, wbf)

    total_formulas = 0
    covered = 0
    mismatch = []
    errors = []
    empty_refs = []
    for ws in wbf.worksheets:
        ev.current_sheet = ws.title
        wsv = wbv[ws.title]
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if not (isinstance(v, str) and v.startswith("=")):
                    continue
                total_formulas += 1
                cv = wsv[c.coordinate].value
                if isinstance(cv, str) and cv.startswith("#"):
                    errors.append(f"{ws.title}!{c.coordinate} = {cv}")
                    continue
                if not isinstance(cv, (int, float)):
                    continue  # текстовый результат — не сверяем
                calc = ev.evaluate(v, ws.title)
                if calc is None:
                    continue
                if isinstance(calc, bool):
                    calc = 1 if calc else 0
                if not isinstance(calc, (int, float)):
                    continue
                covered += 1
                if abs(float(calc) - float(cv)) > 1e-6 * max(1.0, abs(float(cv))):
                    mismatch.append((f"{ws.title}!{c.coordinate}", v[:60], cv, calc))

    # B5: ссылки на пустые ячейки в формулах
    ref_re = re.compile(r"(?:'([^']+)'|([A-Za-zА-Яа-я0-9_]+))?!?\$?([A-Z]+)\$?(\d+)")
    for ws in wbf.worksheets:
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if not (isinstance(v, str) and v.startswith("=")):
                    continue
                seen = set()
                for m in ref_re.finditer(v):
                    sh = m.group(1) or m.group(2) or ws.title
                    col, rrow = m.group(3), int(m.group(4))
                    if sh not in wbf:
                        continue
                    key = (sh, col, rrow)
                    if key in seen:
                        continue
                    seen.add(key)
                    # B5 — пустая ячейка-вход: в формульном виде ячейки ничего нет
                    target_f = wbf[sh].cell(row=rrow, column=col_to_idx(col) + 1).value
                    if target_f is None:
                        empty_refs.append(f"{ws.title}!{c.coordinate} -> {sh}!{col}{rrow}")

    wbf.close()
    wbv.close()
    return {
        "total_formulas": total_formulas,
        "covered": covered,
        "coverage": covered / total_formulas if total_formulas else 0,
        "mismatches": mismatch,
        "errors": errors,
        "empty_refs": empty_refs,
    }


# --------------------------------------------------------------------------
# Группа C: тождества
# --------------------------------------------------------------------------

def sheet_row_labels(wb, sheet):
    """Строки листа: {label: row} по столбцу A (подпись)."""
    ws = wb[sheet]
    labels = {}
    for r in range(1, ws.max_row + 1):
        v = ws.cell(row=r, column=1).value
        if v is not None:
            labels[str(v).strip()] = r
    return labels


def check_group_c(wbf, wbv) -> list:
    """C1 BS=0, C2 CF bridge, C3 roll-forwards (по 90_Checks)."""
    results = []
    if "90_Checks" not in wbf.sheetnames:
        results.append(("C1-C3", "FAIL", "нет листа 90_Checks"))
        return results
    ws = wbv["90_Checks"]
    checks = {}
    for r in range(1, ws.max_row + 1):
        label = ws.cell(row=r, column=1).value
        if label:
            vals = []
            for col in range(4, 11):  # D..J — первые прогнозные колонки
                v = ws.cell(row=r, column=col).value
                if isinstance(v, (int, float)):
                    vals.append(v)
            checks[str(label).strip()] = vals
    identity_patterns = [
        "BS: Активы", "CF: ΔCash", "PPE:", "Debt:", "Equity:",
        "ST + LT", "DT.close =", "Int =", "Невязка кольца",
        "Тождество", "identity",
    ]
    for label, vals in checks.items():
        if any(p in label for p in identity_patterns):
            bad = [f"col{4 + i}={v:,.2f}" for i, v in enumerate(vals) if abs(v) > 0.01]
            status = "PASS" if not bad else "FAIL"
            results.append((f"C3:{label}", status, "; ".join(bad) if bad else "0 по всем годам"))
    return results


# --------------------------------------------------------------------------
# Группа D: знаки и единицы
# --------------------------------------------------------------------------

def check_group_d(wbf, wbv) -> list:
    results = []
    # D2: NI <= PBT по всем прогнозным колонкам PL
    if "21_PL" in wbf.sheetnames:
        wsv = wbv["21_PL"]
        labels = {}
        for r in range(1, wsv.max_row + 1):
            v = wsv.cell(row=r, column=1).value
            if v:
                labels[str(v).strip()] = r
        ni_row = None
        pbt_row = None
        for l, r in labels.items():
            if "чистая прибыль" in l.lower() or l.lower().startswith("net income"):
                ni_row = r
            if "прибыль до налога" in l.lower() or "до налога" in l.lower() or "pretax" in l.lower():
                pbt_row = r
        if ni_row and pbt_row:
            bad = []
            for col in range(4, min(wsv.max_column, 12) + 1):
                ni = wsv.cell(row=ni_row, column=col).value
                pbt = wsv.cell(row=pbt_row, column=col).value
                if isinstance(ni, (int, float)) and isinstance(pbt, (int, float)):
                    if ni > pbt * 1.001:
                        bad.append(f"{get_column_letter(col)}: NI={ni:,.1f} > PBT={pbt:,.1f}")
            results.append(("D2:NI<=PBT", "PASS" if not bad else "FAIL",
                            "; ".join(bad) if bad else "OK по всем годам"))
    # D4: ставка налога в [0;0.5] (точные строки Налог на прибыль / Прибыль до налога)
    if "21_PL" in wbf.sheetnames:
        wsv = wbv["21_PL"]
        tax_row = pbt_row = None
        for r in range(1, wsv.max_row + 1):
            v = wsv.cell(row=r, column=1).value
            if not v:
                continue
            s = str(v).strip().lower()
            if tax_row is None and ("налог на прибыль" in s or s == "налог"):
                tax_row = r
            if pbt_row is None and ("прибыль до налога" in s or s.startswith("pretax")):
                pbt_row = r
        if tax_row and pbt_row:
            bad = []
            for col in range(4, min(wsv.max_column, 12) + 1):
                t = wsv.cell(row=tax_row, column=col).value
                p = wsv.cell(row=pbt_row, column=col).value
                if not (isinstance(t, (int, float)) and isinstance(p, (int, float)) and p != 0):
                    continue
                # конвенция знаков: расходы в PL отрицательные → налог по модулю.
                # Эффективную ставку проверяем только в прибыльных годах;
                # в убыточных налог должен быть <= 0 (бенефит), иначе ошибка знака.
                if p > 0:
                    rate = abs(t) / p
                    if not (0 <= rate <= 0.5):
                        bad.append(f"{get_column_letter(col)}: tax={t:,.0f}, PBT={p:,.0f}, |rate|={rate:.1%}")
                elif t > 0:
                    bad.append(f"{get_column_letter(col)}: PBT={p:,.0f} (убыток), но налог положительный {t:,.0f}")
            results.append(("D4:tax_rate", "PASS" if not bad else "FAIL",
                            "; ".join(bad) if bad else "|налог|/PBT в [0;50%] (прибыльные годы), убыточные без положительного налога"))
    # D8: ABS внутри суммирующих формул
    abs_in_sum = 0
    for ws in wbf.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("="):
                    f = c.value
                    if re.search(r"ABS\s*\(", f, re.I) and ("+" in f or re.search(r"SUM\s*\(", f, re.I)):
                        abs_in_sum += 1
    results.append(("D8:ABS_в_суммах", "WARN" if abs_in_sum else "PASS",
                    f"формул с ABS в суммах: {abs_in_sum}"))
    return results


# --------------------------------------------------------------------------
# Группа E: граница прогноза, сетка годов
# --------------------------------------------------------------------------

def year_grid(ws) -> dict:
    """Карта {col: year} по строке заголовков лет. Понимает 2026E/2026F/2026П.

    Сначала ищет в первых 10 строках (расчётная сетка), иначе — по всей
    таблице (например, сводка на Control_Panel внизу листа).
    """
    def scan(rows):
        best = {}
        for r in rows:
            cols = {}
            for c in range(1, min(ws.max_column, 15) + 1):
                v = ws.cell(row=r, column=c).value
                yr = None
                if isinstance(v, (int, float)) and 2010 <= v <= 2040:
                    yr = int(v)
                elif isinstance(v, str):
                    m = re.match(r"^(20\d{2})\s*[EFПF]?$", v.strip())
                    if m:
                        yr = int(m.group(1))
                if yr is not None:
                    cols[c] = yr
            if len(cols) > len(best):
                best = cols
        return best if len(best) >= 3 else {}

    g = scan(range(1, min(ws.max_row, 10) + 1))
    if g:
        return g
    return scan(range(1, min(ws.max_row, 400) + 1))


def check_group_e(wbf, wbv) -> list:
    results = []
    grids = {}
    for ws in wbf.worksheets:
        g = year_grid(ws)
        if g:
            grids[ws.title] = g

    def _year_of(v) -> Optional[int]:
        if isinstance(v, (int, float)) and 2010 <= v <= 2040:
            return int(v)
        if isinstance(v, str):
            m = re.match(r"^(20\d{2})\s*[EFПF]?$", v.strip())
            if m:
                return int(m.group(1))
        return None

    def _header_rows(ws) -> list:
        """Строки-заголовки (≥3 года) с картой {col: year}."""
        out = []
        for r in range(1, min(ws.max_row, 400) + 1):
            cols = {}
            for c in range(1, min(ws.max_column, 15) + 1):
                yr = _year_of(ws.cell(row=r, column=c).value)
                if yr:
                    cols[c] = yr
            if len(cols) >= 3:
                out.append((r, cols))
        return out

    def _year_at(headers, col, row) -> Optional[int]:
        """Год колонки col для ячейки в строке row: ближайший заголовок ВЫШЕ,
        содержащий год именно в этой колонке. None = скаляр вне годовой сетки."""
        best = None
        for r, cols in headers:
            if r > row:
                break
            if col in cols:
                best = cols[col]
        return best
    # E1: разрыв последний факт -> первый прогноз по выручке (±30%)
    if "21_PL" in wbf.sheetnames and "21_PL" in grids:
        wsv = wbv["21_PL"]
        g = grids["21_PL"]
        rev_row = None
        for r in range(1, wsv.max_row + 1):
            v = wsv.cell(row=r, column=1).value
            if v and str(v).strip().lower() == "выручка":
                rev_row = r
                break
        if rev_row:
            hist = sorted([(yr, c) for c, yr in g.items() if yr <= 2025])
            fcst = sorted([(yr, c) for c, yr in g.items() if yr > 2025])
            if hist and fcst:
                c_last = hist[-1][1]
                c_first = fcst[0][1]
                v_last = wsv.cell(row=rev_row, column=c_last).value
                v_first = wsv.cell(row=rev_row, column=c_first).value
                if isinstance(v_last, (int, float)) and isinstance(v_first, (int, float)) and v_last:
                    gap = (v_first - v_last) / abs(v_last)
                    status = "WARN" if abs(gap) > 0.3 else "PASS"
                    results.append(("E1:разрыв_факт/прогноз",
                                    status,
                                    f"Выручка {hist[-1][0]}→{fcst[0][0]}: {gap:+.1%}"))
    # E2: кросс-листовые ссылки: год целевой колонки должен совпадать с годом
    # исходной колонки (допускается лаг на 1 год — объявленная ацикличность B7).
    # Год — по ближайшей строке заголовков ВЫШЕ ячейки в той же колонке: на листах
    # вроде 35_Valuation несколько сеток (FCFF F:H, SOTP C:E) и скалярные блоки
    # (WACC/Net Debt на последний прогнозный год) — скаляры вне сетки пропускаются.
    ref_re = re.compile(r"(?:'([^']+)'|([A-Za-zА-Яа-я0-9_]+))!\$?([A-Z]+)\$?(\d+)")
    skip_src = {"01_Macro", "02_Hist", "03_Assump", "90_Checks", "Control_Panel", "Raw_IFRS"}
    skip_tgt = set(skip_src)
    headers_cache: Dict[str, list] = {}

    def _headers(sheet: str) -> list:
        if sheet not in headers_cache:
            headers_cache[sheet] = [] if sheet in skip_src else _header_rows(wbf[sheet])
        return headers_cache[sheet]

    issues = []
    # Параметры вне годовой сетки (статичные веса/константы, живущие в колонке
    # исторической сетки) — не годовые ссылки, эвристику заголовков обходим
    PARAM_ROWS = {("11_Segments", 21), ("11_Segments", 22)}  # PGM mix w_pd/w_pt
    for ws in wbf.worksheets:
        if ws.title in skip_src:
            continue
        for row in ws.iter_rows():
            for cell in row:
                v = cell.value
                if not (isinstance(v, str) and v.startswith("=")):
                    continue
                src_year = _year_at(_headers(ws.title), cell.column, cell.row)
                if src_year is None:
                    continue  # скаляр вне годовой сетки — не проверяется
                for m in ref_re.finditer(v):
                    if m.end() < len(v) and v[m.end()] == ":":
                        continue  # начало диапазона — не кросс-годовая ссылка
                    sh = m.group(1) or m.group(2)
                    if not sh or sh in skip_tgt or sh not in wbf.sheetnames:
                        continue
                    tgt_col = col_to_idx(m.group(3)) + 1
                    tgt_row = int(m.group(4))
                    if (sh, tgt_row) in PARAM_ROWS:
                        continue  # статичный параметр вне годовой сетки
                    tgt_year = _year_at(_headers(sh), tgt_col, tgt_row)
                    if tgt_year is None:
                        continue
                    diff = tgt_year - src_year
                    if diff != 0 and diff != -1:
                        issues.append(f"{ws.title}!{cell.coordinate} ({src_year}) -> {sh}!{m.group(3)} ({tgt_year})")
    uniq = list(dict.fromkeys(issues))
    results.append(("E2:сетка_годов_ссылок",
                    "FAIL" if uniq else "PASS",
                    f"{len(uniq)}; " + "; ".join(uniq[:12]) if uniq else "0 смещений"))

    # E7: sanity bounds — fail-fast гейты adequacy (зеркало engine ModelConfig.sanity_*).
    # Тождества сходятся и при абсурдных значениях (AUDIT_ADEQUACY §3.3:
    # STD=5.6e15, interest=7.7e14 при BS diff=0) — второй слой после C-группы.
    E7_INT_REV_MAX = 0.50   # interest_expense / revenue
    E7_DEBT_REV_MAX = 10.0  # total_debt / revenue
    E7_DEBT_GROWTH_MAX = 1.00  # |Δdebt| / debt_prev за год
    E7_ABS_MAX = 1e12       # отсечка денормалов (mUSD)

    def _row_by_label(ws, *needles) -> Optional[int]:
        want = [n.lower() for n in needles]
        for r in range(1, ws.max_row + 1):
            v = ws.cell(row=r, column=1).value
            if isinstance(v, str):
                lv = v.strip().lower()
                if all(n in lv for n in want):
                    return r
        return None

    e7_bad = []
    if {"21_PL", "17_Debt", "20_BS"} <= set(wbv.sheetnames):
        ws_pl, ws_dt, ws_bs = wbv["21_PL"], wbv["17_Debt"], wbv["20_BS"]
        r_rev = _row_by_label(wbf["21_PL"], "выручк")
        r_int = _row_by_label(wbf["21_PL"], "процентные расходы")
        r_debt = _row_by_label(wbf["17_Debt"], "итого долг")
        r_cash = _row_by_label(wbf["20_BS"], "денежные средства")
        r_ta = _row_by_label(wbf["20_BS"], "итого активы")
        if all(x is not None for x in (r_rev, r_int, r_debt, r_cash, r_ta)):
            g_pl = grids.get("21_PL", {})
            debt_prev = None
            for col, yr in sorted(g_pl.items()):
                if yr <= 2025:
                    continue  # прогнозные годы только
                rev = ws_pl.cell(row=r_rev, column=col).value
                interest = ws_pl.cell(row=r_int, column=col).value
                debt = ws_dt.cell(row=r_debt, column=col).value
                cash = ws_bs.cell(row=r_cash, column=col).value
                ta = ws_bs.cell(row=r_ta, column=col).value
                vals = [("cash", cash), ("TA", ta)]
                for name, v in vals:
                    if isinstance(v, (int, float)) and (not math.isfinite(v) or abs(v) > E7_ABS_MAX):
                        e7_bad.append(f"{yr}: {name}={v:.3g} (|x|>{E7_ABS_MAX:.0g})")
                if not (isinstance(rev, (int, float)) and rev):
                    continue
                if isinstance(interest, (int, float)) and abs(interest) / abs(rev) > E7_INT_REV_MAX:
                    e7_bad.append(f"{yr}: interest/revenue={abs(interest)/abs(rev):.2f}>{E7_INT_REV_MAX}")
                if isinstance(debt, (int, float)) and abs(debt) > E7_DEBT_REV_MAX * abs(rev):
                    e7_bad.append(f"{yr}: debt/revenue={abs(debt)/abs(rev):.1f}>{E7_DEBT_REV_MAX}")
                if debt_prev and isinstance(debt, (int, float)) and abs(debt_prev) > 0:
                    growth = abs(debt - debt_prev) / abs(debt_prev)
                    if growth > E7_DEBT_GROWTH_MAX:
                        e7_bad.append(f"{yr}: |Δdebt|/debt={growth:.2f}>{E7_DEBT_GROWTH_MAX}")
                if isinstance(debt, (int, float)):
                    debt_prev = debt
    results.append(("E7:sanity_bounds",
                    "FAIL" if e7_bad else "PASS",
                    "; ".join(e7_bad[:10]) if e7_bad else "interest/rev, debt/rev, Δdebt, денормалы — в порогах"))
    return results


# --------------------------------------------------------------------------
# Группа F: параметры
# --------------------------------------------------------------------------

def check_group_f(wbf, wbv) -> list:
    """F5: параметры без метки источника. F7: [РАСЧЁТ] на литерале.

    На Control_Panel метки в колонках I(Метод)/J(Источник)/K(Роль).
    Параметр — числовой литерал в колонке C (значение параметра).
    """
    results = []
    if "Control_Panel" in wbf.sheetnames:
        ws = wbf["Control_Panel"]
        unlabeled = []
        calc_literal = []
        for r in range(1, ws.max_row + 1):
            label_a = ws.cell(row=r, column=1).value
            if not isinstance(label_a, str) or not label_a.strip():
                continue
            label_a = label_a.strip()
            # пропускаем заголовки и переключатель сценария
            if label_a.isupper() and len(label_a) > 12:
                continue
            if "сценарий" in label_a.lower():
                continue
            c_val = ws.cell(row=r, column=3).value
            if not isinstance(c_val, (int, float)):
                continue
            method = ws.cell(row=r, column=9).value or ""
            source = ws.cell(row=r, column=10).value or ""
            role = ws.cell(row=r, column=11).value or ""
            tags = " ".join(str(x) for x in (method, source, role))
            if not re.search(r"\[(ДАННЫЕ|РАСЧЁТ|ОЦЕНКА|ДОГОВОР|НАСЛЕДИЕ|НОРМ|РЕЗЕРВ)", tags):
                unlabeled.append(f"{label_a[:50]} (C{r})")
            if "[РАСЧЁТ]" in tags:
                calc_literal.append(f"{label_a[:50]} (C{r})")
        if unlabeled:
            results.append(("F5:unlabeled:Control_Panel", "WARN",
                            f"{len(unlabeled)}: " + "; ".join(unlabeled[:15])))
        else:
            results.append(("F5:unlabeled:Control_Panel", "PASS", "0 констант без метки"))
        if calc_literal:
            results.append(("F7:[РАСЧЁТ]-литерал:Control_Panel", "FAIL",
                            f"{len(calc_literal)}: " + "; ".join(calc_literal[:10])))
        else:
            results.append(("F7:[РАСЧЁТ]-литерал:Control_Panel", "PASS", "0"))
    return results


# --------------------------------------------------------------------------
# Группа G: эконометрика
# --------------------------------------------------------------------------

def check_group_g(wbf) -> list:
    results = []
    reg_funcs = {"SLOPE": 0, "INTERCEPT": 0, "RSQ": 0, "STEYX": 0, "CORREL": 0, "LINEST": 0}
    for ws in wbf.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("="):
                    for fn in reg_funcs:
                        if re.search(rf"\b{fn}\s*\(", c.value, re.I):
                            reg_funcs[fn] += 1
    total = sum(reg_funcs.values())
    results.append(("G1:регрессии_в_книге", "PASS" if total else "FAIL",
                    f"SLOPE/INTERCEPT/RSQ/STEYX: {reg_funcs}"))
    return results


# --------------------------------------------------------------------------
# Группа H: формульность
# --------------------------------------------------------------------------

def strip_quoted(s: str) -> str:
    """Убирает текстовые строки в кавычках и имена листов '...', чтобы не считать их числа."""
    s = re.sub(r'"[^"]*"', '""', s)
    s = re.sub(r"'[^']*'", "''", s)
    return s


def check_group_h(wbf) -> list:
    results = []
    # H1: литералы внутри формул (числа, не 0/1/2/12/100/1000...)
    literals = []
    for ws in wbf.worksheets:
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if isinstance(v, str) and v.startswith("="):
                    f = strip_quoted(v[1:])
                    tokens = re.findall(r"(?<![\w$])(\d+(?:\.\d+)?)(?![\w$])", f)
                    for t in tokens:
                        num = float(t)
                        if num not in (0, 1, 2, 12, 100, 1000, 10000):
                            literals.append((f"{ws.title}!{c.coordinate}", num, v[:60]))
    results.append(("H1:литералы_в_формулах", "WARN" if literals else "PASS",
                    f"{len(literals)}; " + "; ".join(f"{a}={b}" for a, b, _ in literals[:10])))
    # H2: константы в прогнозных столбцах расчётных листов.
    # Годовая сетка: находим строку заголовков лет (2010..2040), прогноз = год > 2025.
    input_sheets = {"01_Macro", "02_Hist", "Control_Panel", "03_Assump", "Raw_IFRS", "00_Guide", "00_Cover"}
    calc_sheets = [s for s in wbf.sheetnames
                   if re.match(r"^\d\d_", s) and s not in input_sheets]
    const_forecast = []
    for ws_name in calc_sheets:
        ws = wbf[ws_name]
        year_cols = {}
        header_row = None
        for r in range(1, min(ws.max_row, 10) + 1):
            for c in range(1, min(ws.max_column, 15) + 1):
                v = ws.cell(row=r, column=c).value
                if isinstance(v, (int, float)) and 2010 <= v <= 2040:
                    year_cols[c] = int(v)
            if year_cols:
                header_row = r
                break
        if not year_cols:
            continue
        for c, yr in year_cols.items():
            if yr <= 2025:
                continue
            for r in range(1, ws.max_row + 1):
                if r == header_row:
                    continue
                v = ws.cell(row=r, column=c).value
                if isinstance(v, (int, float)):
                    const_forecast.append(f"{ws_name}!{get_column_letter(c)}{r}={v}")
    results.append(("H2:константы_в_прогнозе", "FAIL" if const_forecast else "PASS",
                    f"{len(const_forecast)}; " + "; ".join(const_forecast[:12])))
    # H3: строки "=прошлый год" (прямые ссылки на соседние ячейки)
    carry = 0
    for ws in wbf.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("="):
                    if re.match(r"^=\$?[A-Z]{1,3}\$?\d+$", c.value[1:].strip()):
                        carry += 1
    results.append(("H3:=прошлый_год", "WARN" if carry else "PASS", f"{carry} ячеек"))
    # H4 (W4/F6): кросс-листовые ссылки в аналитике — конвенция зелёного цвета.
    # INFO-уровень: чёрный = внутрилистовая формула, зелёный = ссылка на другой лист.
    xref_re = re.compile(r"(?:'[^']+'|[A-Za-zА-Яа-я0-9_]{2,})!")
    analytics = ("30_Ratios", "31_Score", "32_Covenants", "33_RevStress",
                 "35_Valuation", "40_Scen")
    not_green = []
    for sh in analytics:
        if sh not in wbf.sheetnames:
            continue
        for row in wbf[sh].iter_rows():
            for c in row:
                v = c.value
                if isinstance(v, str) and v.startswith("=") and xref_re.search(v):
                    rgb = None
                    if c.font and c.font.color and c.font.color.rgb:
                        rgb = str(c.font.color.rgb)
                    if not (rgb and rgb.endswith("008000")):
                        not_green.append(f"{sh}!{c.coordinate}")
    results.append(("H4:цвета_кросс-ссылок",
                    "WARN" if not_green else "PASS",
                    f"{len(not_green)} не зелёных: " + "; ".join(not_green[:10]) if not_green
                    else "все кросс-ссылки аналитики зелёные"))
    return results


# --------------------------------------------------------------------------
# Группа I: сценарии
# --------------------------------------------------------------------------

def check_group_i(wbf) -> list:
    results = []
    # I1/I3: переключатель сценария на Control_Panel
    if "Control_Panel" in wbf.sheetnames:
        ws = wbf["Control_Panel"]
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("="):
                    if "IF(" in c.value.upper() and "$C$5" in c.value.replace(" ", ""):
                        results.append(("I3:переключатель", "PASS",
                                        f"Control_Panel!{c.coordinate} использует C5"))
                        return results
        results.append(("I3:переключатель", "WARN", "не найден IF по C5 на Control_Panel"))
    return results


# --------------------------------------------------------------------------
# Группа J: выход
# --------------------------------------------------------------------------

def check_group_j(wbf, wbv) -> list:
    results = []
    cover_sheets = [s for s in wbf.sheetnames if "cover" in s.lower() or s in ("Model_Output", "00_Guide")]
    statuses = []
    for ws_name in cover_sheets:
        wsv = wbv[ws_name]
        for r in range(1, min(wsv.max_row, 60) + 1):
            for c in range(1, min(wsv.max_column, 8) + 1):
                v = wsv.cell(row=r, column=c).value
                if isinstance(v, str) and ("✅" in v or "⚠" in v or "❌" in v):
                    statuses.append(f"{ws_name}!{get_column_letter(c)}{r}: {v.strip()[:60]}")
    # J1: у сигнальной величины (счётчик нарушений) есть потребитель — статус обложки
    consumer = None
    if "00_Cover" in wbf.sheetnames:
        ws = wbf["00_Cover"]
        for r in range(1, ws.max_row + 1):
            for c in range(1, ws.max_column + 1):
                f = ws.cell(row=r, column=c).value
                if isinstance(f, str) and f.startswith("=") and ("КОВЕНАНТЫ" in f or "C$19" in f or "C19" in f):
                    consumer = f"00_Cover!{get_column_letter(c)}{r}"
                    break
            if consumer:
                break
    results.append(("J1:потребитель_сигнала", "PASS" if consumer else "FAIL",
                    consumer or "статус не ссылается на счётчик нарушений"))
    # J2: статус на обложке один
    n_status = len(statuses)
    results.append(("J2:статус_обложки",
                    "PASS" if n_status == 1 else ("WARN" if n_status == 0 else "FAIL"),
                    f"{n_status} статус(ов): " + " | ".join(statuses) if statuses else "не найден"))
    return results


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model", help="путь к xlsx")
    ap.add_argument("--excel", action="store_true", help="пересчитать в Microsoft Excel")
    ap.add_argument("--md", help="путь к отчёту Markdown")
    args = ap.parse_args()

    path = Path(args.model).resolve()
    print(f"Аудит: {path.name}")
    print("=" * 70)

    report = []
    report.append(f"# Аудит {path.name}\n")
    report.append(f"Дата: {datetime.date.today()} · Стандарт: СТАНДАРТ_верификации_моделей.md\n")

    # A
    a_results = check_group_a(path)
    print("--- Группа A: открываемость ---")
    for code, status, msg in a_results:
        print(f"  [{status:4}] {code}: {msg}")
        report.append(f"- **{code}** [{status}]: {msg}")

    # B
    print("--- Группа B: кэш и сходимость ---")
    b = check_group_b(path)
    print(f"  Формул: {b['total_formulas']}, покрыто: {b['covered']} ({b['coverage']:.1%})")
    print(f"  Расхождений кэша: {len(b['mismatches'])}, ошибок: {len(b['errors'])}, пустых ссылок: {len(b['empty_refs'])}")
    report.append(f"\n## Группа B: кэш и сходимость\n")
    report.append(f"- Формул: {b['total_formulas']}, покрыто мини-вычислителем: {b['covered']} ({b['coverage']:.1%})")
    report.append(f"- Расхождений кэша: {len(b['mismatches'])}")
    for m in b["mismatches"][:20]:
        print(f"    MISMATCH {m}")
        report.append(f"  - MISMATCH {m[0]}: кэш={m[2]}, пересчёт={m[3]} :: {m[1]}")
    report.append(f"- Ошибочных ячеек: {len(b['errors'])}")
    for e in b["errors"][:20]:
        print(f"    ERROR {e}")
        report.append(f"  - {e}")
    report.append(f"- Ссылок на пустые ячейки: {len(b['empty_refs'])}")
    for e in b["empty_refs"][:20]:
        print(f"    EMPTYREF {e}")
        report.append(f"  - {e}")

    # Excel recalc + сверка ключевых ячеек
    if args.excel:
        print("--- Пересчёт в Microsoft Excel и сверка с кэшем ---")
        wbv0 = openpyxl.load_workbook(path, data_only=True)
        cells = []
        for sh, ranges in [
            ("90_Checks", ["F7", "G7", "H7", "F8", "G8", "H8", "F9", "G9", "H9",
                           "F10", "G10", "H10", "F11", "G11", "H11", "F12", "G12", "H12",
                           "F13", "G13", "H13", "F14", "G14", "H14"]),
            ("21_PL", ["F7", "F12", "F20", "F21", "F22"]),
            ("00_Cover", ["C17", "C19", "C20"]),
            ("Control_Panel", ["C25"]),
            ("30_Ratios", ["F7", "F8", "F13"]),
            ("03_Assump", ["F35", "F36", "F39"]),
        ]:
            for cl in ranges:
                cells.append((sh, cl))
        try:
            xv = excel_verify(path, cells, wbv0)
            print(f"  Excel: прочитано {xv['checked']}, расхождений с кэшем: {len(xv['mismatches'])}")
            for m in xv["mismatches"]:
                print(f"    EXCEL MISMATCH {m}")
            report.append(f"\n## Excel-сверка\n- Прочитано ячеек: {xv['checked']}, расхождений: {len(xv['mismatches'])}")
            for m in xv["mismatches"]:
                report.append(f"  - {m[0]}: кэш={m[1]}, Excel={m[2]}")
        except Exception as e:
            print(f"  Excel-сверка не удалась: {e}")
            report.append(f"\n## Excel-сверка\n- Ошибка: {e}")
        wbv0.close()

    wbf = openpyxl.load_workbook(path, data_only=False)
    wbv = openpyxl.load_workbook(path, data_only=True)

    # C
    print("--- Группа C: тождества ---")
    c_results = check_group_c(wbf, wbv)
    if not c_results:
        c_results = [("C1-C3", "FAIL", "90_Checks пуст")]
    for code, status, msg in c_results:
        print(f"  [{status:4}] {code}: {msg}")
        report.append(f"\n### C {code} [{status}]\n{msg}")

    # D
    print("--- Группа D: знаки и единицы ---")
    d_results = check_group_d(wbf, wbv)
    for code, status, msg in d_results:
        print(f"  [{status:4}] {code}: {msg}")
        report.append(f"- **{code}** [{status}]: {msg}")

    # E
    print("--- Группа E: сетка годов ---")
    e_results = check_group_e(wbf, wbv)
    for code, status, msg in e_results:
        print(f"  [{status:4}] {code}: {msg}")
        report.append(f"- **{code}** [{status}]: {msg}")

    # F
    print("--- Группа F: параметры ---")
    f_results = check_group_f(wbf, wbv)
    for code, status, msg in f_results:
        print(f"  [{status:4}] {code}: {msg}")
        report.append(f"- **{code}** [{status}]: {msg}")

    # G
    print("--- Группа G: эконометрика ---")
    g_results = check_group_g(wbf)
    for code, status, msg in g_results:
        print(f"  [{status:4}] {code}: {msg}")
        report.append(f"- **{code}** [{status}]: {msg}")

    # H
    print("--- Группа H: формульность ---")
    h_results = check_group_h(wbf)
    for code, status, msg in h_results:
        print(f"  [{status:4}] {code}: {msg}")
        report.append(f"- **{code}** [{status}]: {msg}")

    # I
    print("--- Группа I: сценарии ---")
    i_results = check_group_i(wbf)
    for code, status, msg in i_results:
        print(f"  [{status:4}] {code}: {msg}")
        report.append(f"- **{code}** [{status}]: {msg}")

    # J
    print("--- Группа J: выход ---")
    j_results = check_group_j(wbf, wbv)
    for code, status, msg in j_results:
        print(f"  [{status:4}] {code}: {msg}")
        report.append(f"- **{code}** [{status}]: {msg}")

    wbf.close()
    wbv.close()

    print("\n" + "=" * 70)
    if args.md:
        out = Path(args.md)
        out.write_text("\n".join(report))
        print(f"Отчёт: {out}")


if __name__ == "__main__":
    main()
