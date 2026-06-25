"""Math Engine module for TerminalX EcoSystem.

polsoft.ITS(TM) Group  *  Sebastian Januchowski
Module: Math Engine  v1.0.0

Silnik matematyczny dla skomplikowanych obliczeń.
Obsługuje: wyrażenia, statystyki, macierze, trygonometrię,
           kombinatorykę, konwersję jednostek, zmienne sesji,
           historię wyrażeń i eksport wyników.

Komendy:
  math <wyrażenie>             - oblicz wyrażenie (pełna składnia Python)
  math stat <l1> <l2> ...      - statystyki listy liczb (mean, median, std, var, ...)
  math matrix <op> ...         - operacje macierzowe (det, inv, mul, add, trans)
  math trig <funkcja> <stopnie>- sin/cos/tan/asin/acos/atan (wejście w stopniach)
  math comb <n> <k>            - kombinacje C(n,k) i permutacje P(n,k)
  math perm <n> <k>            - permutacje P(n,k)
  math fact <n>                - silnia n!
  math prime <n>               - sprawdź czy n jest liczbą pierwszą
  math primes <n>              - lista liczb pierwszych <= n
  math gcd <a> <b>             - NWD(a, b)
  math lcm <a> <b>             - NWW(a, b)
  math conv <wartość> <z> <do> - konwersja jednostek
  math solve <a> <b> <c>       - pierwiastki równania kwadratowego ax²+bx+c=0
  math set <nazwa> <wyrażenie> - zapisz zmienną do sesji
  math get <nazwa>             - odczytaj zmienną z sesji
  math vars                    - wylistuj zmienne sesji
  math history [n]             - ostatnie n wyrażeń (domyślnie 10)
  math clear                   - wyczyść historię i zmienne
  math export [plik]           - eksportuj historię do JSON
  math help                    - lista komend

Integracja:
  - _shared    : stałe ANSI, ROOT_DIR, CACHE_DIR
  - lang       : pełna i18n przez terminal.t() z prefixem math_
  - cache      : historia + eksport w .cache/math/
"""

import cmath
import hashlib
import json
import math
import os
import re
import sys
import time
from datetime import datetime
from typing import Any

from ._shared import (
    ROOT_DIR, CACHE_DIR,
    RST, BOLD, DIM, YLW, ORG, RED, GRN, CYN, BCYN, MGT, BLU, WHT,
    _w, _strip, _pad,
)

# ---------------------------------------------------------------------------
# Stałe
# ---------------------------------------------------------------------------

_VERSION    = "1.0.0"
_CACHE_DIR  = os.path.join(CACHE_DIR, "math")
_HIST_FILE  = os.path.join(_CACHE_DIR, "history.json")
_MAX_HIST   = 200
_MAX_PRIMES = 100_000

# ---------------------------------------------------------------------------
# Stan sesji (per-process, nie per-terminal-instance)
# ---------------------------------------------------------------------------

_session_vars: dict[str, Any] = {}
_history: list[dict]          = []

# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _ensure_cache() -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)


def _load_history() -> None:
    global _history
    _ensure_cache()
    if os.path.isfile(_HIST_FILE):
        try:
            with open(_HIST_FILE, encoding="utf-8") as f:
                _history = json.load(f)
        except Exception:
            _history = []


def _save_history() -> None:
    _ensure_cache()
    try:
        with open(_HIST_FILE, "w", encoding="utf-8") as f:
            json.dump(_history[-_MAX_HIST:], f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _record(expr: str, result: Any, ok: bool) -> None:
    _history.append({
        "ts":     datetime.now().isoformat(timespec="seconds"),
        "expr":   expr,
        "result": str(result),
        "ok":     ok,
    })
    if len(_history) > _MAX_HIST:
        _history.pop(0)
    _save_history()

# ---------------------------------------------------------------------------
# Bezpieczny ewaluator wyrażeń
# ---------------------------------------------------------------------------

_SAFE_NAMES: dict[str, Any] = {
    # stałe
    "pi":    math.pi,
    "e":     math.e,
    "tau":   math.tau,
    "inf":   math.inf,
    "nan":   math.nan,
    # funkcje math
    "sqrt":  math.sqrt,
    "log":   math.log,
    "log2":  math.log2,
    "log10": math.log10,
    "exp":   math.exp,
    "pow":   math.pow,
    "abs":   abs,
    "round": round,
    "floor": math.floor,
    "ceil":  math.ceil,
    "trunc": math.trunc,
    "fabs":  math.fabs,
    "factorial": math.factorial,
    "gcd":   math.gcd,
    "lcm":   math.lcm,
    "comb":  math.comb,
    "perm":  math.perm,
    "hypot": math.hypot,
    "isnan": math.isnan,
    "isinf": math.isinf,
    # trygonometria (radiany)
    "sin":   math.sin,
    "cos":   math.cos,
    "tan":   math.tan,
    "asin":  math.asin,
    "acos":  math.acos,
    "atan":  math.atan,
    "atan2": math.atan2,
    "degrees": math.degrees,
    "radians": math.radians,
    # hiperboliczne
    "sinh":  math.sinh,
    "cosh":  math.cosh,
    "tanh":  math.tanh,
    # complex
    "cmath": cmath,
    # built-ins dozwolone
    "min":   min,
    "max":   max,
    "sum":   sum,
    "len":   len,
    "range": range,
    "list":  list,
    "int":   int,
    "float": float,
    "complex": complex,
}

_BLOCKED = re.compile(
    r"\b(import|exec|eval|open|__import__|compile|globals|locals|"
    r"getattr|setattr|delattr|vars|dir|breakpoint|__builtins__|"
    r"subprocess|os\.system|os\.popen)\b"
)


def _eval_expr(expr: str, extra_vars: dict | None = None) -> tuple[Any, str | None]:
    """Bezpiecznie ewaluuj wyrażenie matematyczne.

    Zwraca (wynik, None) lub (None, komunikat_błędu).
    """
    if _BLOCKED.search(expr):
        return None, "wyrażenie zawiera niedozwolone słowa kluczowe"
    namespace = dict(_SAFE_NAMES)
    namespace.update(_session_vars)
    if extra_vars:
        namespace.update(extra_vars)
    try:
        result = eval(compile(expr, "<math>", "eval"), {"__builtins__": {}}, namespace)  # noqa: S307
        return result, None
    except ZeroDivisionError:
        return None, "dzielenie przez zero"
    except OverflowError:
        return None, "wynik poza zakresem (overflow)"
    except Exception as exc:
        return None, str(exc)

# ---------------------------------------------------------------------------
# Formatowanie wyników
# ---------------------------------------------------------------------------

def _fmt(value: Any) -> str:
    """Formatuj liczbę: int bez .0, float do 12 miejsc, inne as-is."""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, int):
        return f"{value:,}".replace(",", "\u202f")  # thin space jako separator tysięcy
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "∞" if value > 0 else "-∞"
        # usuń zbędne zera końcowe
        s = f"{value:.12g}"
        return s
    if isinstance(value, complex):
        r, i = value.real, value.imag
        sign = "+" if i >= 0 else "-"
        return f"{_fmt(r)} {sign} {_fmt(abs(i))}i"
    return str(value)


def _sep(width: int = 60) -> str:
    return DIM + "─" * width + RST

# ---------------------------------------------------------------------------
# Polecenie główne: math <wyrażenie>
# ---------------------------------------------------------------------------

def _cmd_eval(args: list, _t) -> None:
    if not args:
        print(_t("math_usage_eval"))
        return
    expr = " ".join(args)
    t0   = time.perf_counter()
    val, err = _eval_expr(expr)
    elapsed  = time.perf_counter() - t0
    if err:
        print(RED + BOLD + _t("math_err_eval", expr=expr, err=err) + RST)
        _record(expr, err, ok=False)
    else:
        _record(expr, val, ok=True)
        # jeśli zmienna sesji — pokaż jak przypisanie
        print(
            f"  {CYN}{expr}{RST}  {DIM}={RST}  {GRN}{BOLD}{_fmt(val)}{RST}"
            f"  {DIM}({elapsed*1000:.3f} ms){RST}"
        )

# ---------------------------------------------------------------------------
# Statystyki
# ---------------------------------------------------------------------------

def _cmd_stat(args: list, _t) -> None:
    if not args:
        print(_t("math_usage_stat"))
        return
    nums = []
    for a in args:
        v, err = _eval_expr(a)
        if err or not isinstance(v, (int, float)):
            print(RED + _t("math_stat_bad_num", val=a) + RST)
            return
        nums.append(float(v))
    n   = len(nums)
    s   = sum(nums)
    mn  = min(nums)
    mx  = max(nums)
    avg = s / n
    sorted_nums = sorted(nums)
    if n % 2 == 0:
        med = (sorted_nums[n//2 - 1] + sorted_nums[n//2]) / 2
    else:
        med = sorted_nums[n//2]
    var = sum((x - avg) ** 2 for x in nums) / n
    std = math.sqrt(var)
    # zakres
    q1_i, q3_i = n // 4, 3 * n // 4
    q1  = sorted_nums[q1_i]
    q3  = sorted_nums[q3_i]
    iqr = q3 - q1

    print(BOLD + CYN + _t("math_stat_title") + RST)
    print(_sep())
    rows = [
        ("n",        f"{n}"),
        ("sum",      _fmt(s)),
        ("min",      _fmt(mn)),
        ("max",      _fmt(mx)),
        ("mean",     _fmt(avg)),
        ("median",   _fmt(med)),
        ("var",      _fmt(var)),
        ("std",      _fmt(std)),
        ("Q1",       _fmt(q1)),
        ("Q3",       _fmt(q3)),
        ("IQR",      _fmt(iqr)),
    ]
    for label, val in rows:
        print(f"  {YLW}{_pad(label, 10)}{RST}  {GRN}{val}{RST}")
    print(_sep())

# ---------------------------------------------------------------------------
# Macierze (bez numpy — czysty Python)
# ---------------------------------------------------------------------------

def _parse_matrix(s: str) -> list[list[float]] | None:
    """Parsuj macierz z formatu '[[1,2],[3,4]]' lub '1,2;3,4'."""
    s = s.strip()
    if s.startswith("[["):
        try:
            rows = json.loads(s)
            return [[float(x) for x in row] for row in rows]
        except Exception:
            return None
    # format uproszczony: wiersze oddzielone ';', elementy ','
    try:
        return [[float(x) for x in row.split(",")] for row in s.split(";")]
    except Exception:
        return None


def _mat_det(m: list[list[float]]) -> float:
    """Wyznacznik macierzy (LU bez pivotingu — wystarczy dla małych macierzy)."""
    n = len(m)
    if n == 1:
        return m[0][0]
    if n == 2:
        return m[0][0]*m[1][1] - m[0][1]*m[1][0]
    det = 0.0
    for j in range(n):
        minor = [[m[i][k] for k in range(n) if k != j] for i in range(1, n)]
        det += ((-1)**j) * m[0][j] * _mat_det(minor)
    return det


def _mat_inv(m: list[list[float]]) -> list[list[float]] | None:
    """Odwrotność macierzy (Gauss-Jordan)."""
    n = len(m)
    aug = [row[:] + [float(i == j) for j in range(n)] for i, row in enumerate(m)]
    for col in range(n):
        pivot = None
        for row in range(col, n):
            if abs(aug[row][col]) > 1e-12:
                pivot = row
                break
        if pivot is None:
            return None
        aug[col], aug[pivot] = aug[pivot], aug[col]
        scale = aug[col][col]
        aug[col] = [x / scale for x in aug[col]]
        for row in range(n):
            if row != col:
                factor = aug[row][col]
                aug[row] = [aug[row][k] - factor * aug[col][k] for k in range(2*n)]
    return [row[n:] for row in aug]


def _mat_mul(a: list[list[float]], b: list[list[float]]) -> list[list[float]] | None:
    ra, ca = len(a), len(a[0])
    rb, cb = len(b), len(b[0])
    if ca != rb:
        return None
    return [
        [sum(a[i][k] * b[k][j] for k in range(ca)) for j in range(cb)]
        for i in range(ra)
    ]


def _mat_add(a: list[list[float]], b: list[list[float]]) -> list[list[float]] | None:
    if len(a) != len(b) or len(a[0]) != len(b[0]):
        return None
    return [[a[i][j] + b[i][j] for j in range(len(a[0]))] for i in range(len(a))]


def _mat_trans(m: list[list[float]]) -> list[list[float]]:
    return [[m[j][i] for j in range(len(m))] for i in range(len(m[0]))]


def _print_mat(m: list[list[float]]) -> None:
    for row in m:
        cells = "  ".join(f"{x:10.6g}" for x in row)
        print(f"  {GRN}│ {cells} │{RST}")


def _cmd_matrix(args: list, _t) -> None:
    if not args:
        print(_t("math_usage_matrix"))
        return
    op = args[0].lower()
    rest = args[1:]

    if op == "det":
        if not rest:
            print(_t("math_matrix_need_mat")); return
        m = _parse_matrix(" ".join(rest))
        if m is None:
            print(RED + _t("math_matrix_parse_err") + RST); return
        if len(m) != len(m[0]):
            print(RED + _t("math_matrix_not_square") + RST); return
        d = _mat_det(m)
        print(f"  {CYN}det{RST} = {GRN}{BOLD}{_fmt(d)}{RST}")

    elif op == "inv":
        if not rest:
            print(_t("math_matrix_need_mat")); return
        m = _parse_matrix(" ".join(rest))
        if m is None:
            print(RED + _t("math_matrix_parse_err") + RST); return
        inv = _mat_inv(m)
        if inv is None:
            print(RED + _t("math_matrix_singular") + RST); return
        print(BOLD + CYN + _t("math_matrix_inv_title") + RST)
        _print_mat(inv)

    elif op == "mul":
        if len(rest) < 2:
            print(_t("math_matrix_need_two")); return
        # separator ':' między macierzami
        raw = " ".join(rest)
        parts = raw.split(":")
        if len(parts) != 2:
            print(_t("math_matrix_sep_hint")); return
        a = _parse_matrix(parts[0])
        b = _parse_matrix(parts[1])
        if a is None or b is None:
            print(RED + _t("math_matrix_parse_err") + RST); return
        c = _mat_mul(a, b)
        if c is None:
            print(RED + _t("math_matrix_dim_mismatch") + RST); return
        print(BOLD + CYN + _t("math_matrix_mul_title") + RST)
        _print_mat(c)

    elif op == "add":
        raw = " ".join(rest)
        parts = raw.split(":")
        if len(parts) != 2:
            print(_t("math_matrix_sep_hint")); return
        a = _parse_matrix(parts[0])
        b = _parse_matrix(parts[1])
        if a is None or b is None:
            print(RED + _t("math_matrix_parse_err") + RST); return
        c = _mat_add(a, b)
        if c is None:
            print(RED + _t("math_matrix_dim_mismatch") + RST); return
        print(BOLD + CYN + _t("math_matrix_add_title") + RST)
        _print_mat(c)

    elif op == "trans":
        if not rest:
            print(_t("math_matrix_need_mat")); return
        m = _parse_matrix(" ".join(rest))
        if m is None:
            print(RED + _t("math_matrix_parse_err") + RST); return
        print(BOLD + CYN + _t("math_matrix_trans_title") + RST)
        _print_mat(_mat_trans(m))

    else:
        print(_t("math_matrix_unknown_op", op=op))
        print(_t("math_usage_matrix"))

# ---------------------------------------------------------------------------
# Trygonometria (wejście w stopniach)
# ---------------------------------------------------------------------------

_TRIG_FUNCS = {
    "sin":  math.sin,
    "cos":  math.cos,
    "tan":  math.tan,
    "asin": lambda x: math.degrees(math.asin(x)),
    "acos": lambda x: math.degrees(math.acos(x)),
    "atan": lambda x: math.degrees(math.atan(x)),
    "sinh": math.sinh,
    "cosh": math.cosh,
    "tanh": math.tanh,
}


def _cmd_trig(args: list, _t) -> None:
    if len(args) < 2:
        print(_t("math_usage_trig"))
        return
    fn_name = args[0].lower()
    fn = _TRIG_FUNCS.get(fn_name)
    if fn is None:
        print(RED + _t("math_trig_unknown", fn=fn_name) + RST)
        return
    val, err = _eval_expr(args[1])
    if err:
        print(RED + _t("math_err_eval", expr=args[1], err=err) + RST); return
    val = float(val)
    # dla sin/cos/tan: wejście w stopniach -> przelicz na radiany
    if fn_name in ("sin", "cos", "tan", "sinh", "cosh", "tanh"):
        rad = math.radians(val)
        try:
            result = fn(rad)
        except ValueError as exc:
            print(RED + str(exc) + RST); return
        print(
            f"  {CYN}{fn_name}({val}°){RST} = {GRN}{BOLD}{_fmt(result)}{RST}"
            f"  {DIM}({_fmt(rad)} rad){RST}"
        )
    else:
        # asin/acos/atan: wejście bez jednostki, wynik w stopniach
        try:
            result = fn(val)
        except ValueError as exc:
            print(RED + str(exc) + RST); return
        print(
            f"  {CYN}{fn_name}({_fmt(val)}){RST} = {GRN}{BOLD}{_fmt(result)}°{RST}"
        )

# ---------------------------------------------------------------------------
# Kombinatoryka
# ---------------------------------------------------------------------------

def _cmd_comb(args: list, _t) -> None:
    if len(args) < 2:
        print(_t("math_usage_comb")); return
    try:
        n, k = int(args[0]), int(args[1])
    except ValueError:
        print(RED + _t("math_comb_int_required") + RST); return
    if n < 0 or k < 0:
        print(RED + _t("math_comb_negative") + RST); return
    try:
        result = math.comb(n, k)
    except ValueError as exc:
        print(RED + str(exc) + RST); return
    print(f"  {CYN}C({n},{k}){RST} = {GRN}{BOLD}{_fmt(result)}{RST}")


def _cmd_perm(args: list, _t) -> None:
    if len(args) < 2:
        print(_t("math_usage_perm")); return
    try:
        n, k = int(args[0]), int(args[1])
    except ValueError:
        print(RED + _t("math_comb_int_required") + RST); return
    try:
        result = math.perm(n, k)
    except ValueError as exc:
        print(RED + str(exc) + RST); return
    print(f"  {CYN}P({n},{k}){RST} = {GRN}{BOLD}{_fmt(result)}{RST}")


def _cmd_fact(args: list, _t) -> None:
    if not args:
        print(_t("math_usage_fact")); return
    try:
        n = int(args[0])
    except ValueError:
        print(RED + _t("math_comb_int_required") + RST); return
    if n < 0:
        print(RED + _t("math_comb_negative") + RST); return
    if n > 10000:
        print(RED + _t("math_fact_too_large") + RST); return
    result = math.factorial(n)
    s = str(result)
    display = s if len(s) <= 60 else s[:30] + f"...({len(s)} cyfr)..." + s[-10:]
    print(f"  {CYN}{n}!{RST} = {GRN}{BOLD}{display}{RST}")

# ---------------------------------------------------------------------------
# Liczby pierwsze
# ---------------------------------------------------------------------------

def _is_prime(n: int) -> bool:
    if n < 2:
        return False
    if n < 4:
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i+2) == 0:
            return False
        i += 6
    return True


def _sieve(limit: int) -> list[int]:
    """Sito Eratostenesa."""
    if limit < 2:
        return []
    sieve = bytearray([1]) * (limit + 1)
    sieve[0] = sieve[1] = 0
    for i in range(2, int(limit**0.5) + 1):
        if sieve[i]:
            sieve[i*i::i] = bytearray(len(sieve[i*i::i]))
    return [i for i, v in enumerate(sieve) if v]


def _cmd_prime(args: list, _t) -> None:
    if not args:
        print(_t("math_usage_prime")); return
    try:
        n = int(args[0])
    except ValueError:
        print(RED + _t("math_comb_int_required") + RST); return
    if _is_prime(n):
        print(f"  {GRN}{BOLD}{n}{RST} {GRN}{_t('math_prime_yes')}{RST}")
    else:
        print(f"  {YLW}{n}{RST} {YLW}{_t('math_prime_no')}{RST}")


def _cmd_primes(args: list, _t) -> None:
    if not args:
        print(_t("math_usage_primes")); return
    try:
        n = int(args[0])
    except ValueError:
        print(RED + _t("math_comb_int_required") + RST); return
    if n > _MAX_PRIMES:
        print(RED + _t("math_primes_too_large", max=_MAX_PRIMES) + RST); return
    primes = _sieve(n)
    print(BOLD + CYN + _t("math_primes_title", n=n, count=len(primes)) + RST)
    line = ""
    for p in primes:
        part = f"{GRN}{p}{RST}  "
        if len(_strip(line + part)) > 72:
            print("  " + line)
            line = part
        else:
            line += part
    if line:
        print("  " + line)

# ---------------------------------------------------------------------------
# NWD / NWW
# ---------------------------------------------------------------------------

def _cmd_gcd(args: list, _t) -> None:
    if len(args) < 2:
        print(_t("math_usage_gcd")); return
    try:
        a, b = int(args[0]), int(args[1])
    except ValueError:
        print(RED + _t("math_comb_int_required") + RST); return
    result = math.gcd(abs(a), abs(b))
    print(f"  {CYN}NWD({a},{b}){RST} = {GRN}{BOLD}{result}{RST}")


def _cmd_lcm(args: list, _t) -> None:
    if len(args) < 2:
        print(_t("math_usage_lcm")); return
    try:
        a, b = int(args[0]), int(args[1])
    except ValueError:
        print(RED + _t("math_comb_int_required") + RST); return
    result = math.lcm(abs(a), abs(b))
    print(f"  {CYN}NWW({a},{b}){RST} = {GRN}{BOLD}{result}{RST}")

# ---------------------------------------------------------------------------
# Konwersja jednostek
# ---------------------------------------------------------------------------

# (wartość_do_SI, nazwa_SI)
_UNITS: dict[str, tuple[float, str]] = {
    # długość
    "m":   (1.0, "m"),   "km":  (1000.0, "m"),  "cm": (0.01, "m"),
    "mm":  (0.001, "m"), "mi":  (1609.344, "m"), "ft": (0.3048, "m"),
    "in":  (0.0254, "m"), "yd": (0.9144, "m"),   "nm": (1e-9, "m"),
    # masa
    "kg":  (1.0, "kg"),  "g":   (0.001, "kg"),   "mg": (1e-6, "kg"),
    "lb":  (0.453592, "kg"), "oz": (0.0283495, "kg"), "t": (1000.0, "kg"),
    # temperatura — specjalna obsługa
    "c":   None,  "f": None,  "k": None,
    # czas
    "s":   (1.0, "s"),   "ms":  (0.001, "s"),    "min": (60.0, "s"),
    "h":   (3600.0, "s"),"d":   (86400.0, "s"),  "week": (604800.0, "s"),
    # prędkość
    "m/s": (1.0, "m/s"), "km/h": (1/3.6, "m/s"), "mph": (0.44704, "m/s"),
    "kn":  (0.514444, "m/s"),
    # objętość
    "l":   (0.001, "m3"), "ml":  (1e-6, "m3"), "m3": (1.0, "m3"),
    "gal": (0.00378541, "m3"), "fl_oz": (2.9574e-5, "m3"),
    # energia
    "j":   (1.0, "J"),   "kj":  (1000.0, "J"),   "cal": (4.184, "J"),
    "kcal": (4184.0, "J"), "kwh": (3.6e6, "J"),  "ev": (1.602176634e-19, "J"),
    # moc
    "w":   (1.0, "W"),   "kw":  (1000.0, "W"),   "mw": (1e6, "W"),
    "hp":  (745.7, "W"),
    # ciśnienie
    "pa":  (1.0, "Pa"),  "kpa": (1000.0, "Pa"),  "bar": (1e5, "Pa"),
    "atm": (101325.0, "Pa"), "psi": (6894.76, "Pa"),
    # dane
    "b":   (1.0, "B"),   "kb": (1024.0, "B"),    "mb": (1024**2, "B"),
    "gb":  (1024**3, "B"), "tb": (1024**4, "B"), "pb": (1024**5, "B"),
    # kąty
    "deg": (math.pi/180, "rad"), "rad": (1.0, "rad"),
    "grad": (math.pi/200, "rad"),
}

_TEMP_UNITS = {"c", "f", "k"}


def _conv_temp(val: float, src: str, dst: str) -> float:
    # do Celsjusza
    if src == "f":
        val = (val - 32) * 5/9
    elif src == "k":
        val = val - 273.15
    # z Celsjusza
    if dst == "f":
        return val * 9/5 + 32
    if dst == "k":
        return val + 273.15
    return val


def _cmd_conv(args: list, _t) -> None:
    if len(args) < 3:
        print(_t("math_usage_conv")); return
    val_s, src, dst = args[0], args[1].lower(), args[2].lower()
    val, err = _eval_expr(val_s)
    if err:
        print(RED + _t("math_err_eval", expr=val_s, err=err) + RST); return
    val = float(val)

    if src in _TEMP_UNITS or dst in _TEMP_UNITS:
        if src not in _TEMP_UNITS or dst not in _TEMP_UNITS:
            print(RED + _t("math_conv_temp_mix") + RST); return
        result = _conv_temp(val, src, dst)
        print(f"  {CYN}{_fmt(val)} {src.upper()}{RST} = {GRN}{BOLD}{_fmt(result)} {dst.upper()}{RST}")
        return

    si_src = _UNITS.get(src)
    si_dst = _UNITS.get(dst)
    if si_src is None:
        print(RED + _t("math_conv_unknown_unit", unit=src) + RST); return
    if si_dst is None:
        print(RED + _t("math_conv_unknown_unit", unit=dst) + RST); return
    if si_src[1] != si_dst[1]:
        print(RED + _t("math_conv_incompatible", a=src, b=dst,
                        sa=si_src[1], sb=si_dst[1]) + RST); return
    si_val = val * si_src[0]
    result = si_val / si_dst[0]
    print(f"  {CYN}{_fmt(val)} {src}{RST} = {GRN}{BOLD}{_fmt(result)} {dst}{RST}")

# ---------------------------------------------------------------------------
# Równanie kwadratowe
# ---------------------------------------------------------------------------

def _cmd_solve(args: list, _t) -> None:
    if len(args) < 3:
        print(_t("math_usage_solve")); return
    vals = []
    for a in args[:3]:
        v, err = _eval_expr(a)
        if err:
            print(RED + _t("math_err_eval", expr=a, err=err) + RST); return
        vals.append(float(v))
    a, b, c = vals
    if a == 0:
        if b == 0:
            print(RED + _t("math_solve_degenerate") + RST); return
        x = -c / b
        print(_t("math_solve_linear", x=_fmt(x)))
        return
    disc = b*b - 4*a*c
    print(BOLD + CYN + _t("math_solve_title", a=_fmt(a), b=_fmt(b), c=_fmt(c)) + RST)
    print(f"  Δ = {_fmt(disc)}")
    if disc > 0:
        x1 = (-b + math.sqrt(disc)) / (2*a)
        x2 = (-b - math.sqrt(disc)) / (2*a)
        print(f"  {GRN}x₁ = {BOLD}{_fmt(x1)}{RST}")
        print(f"  {GRN}x₂ = {BOLD}{_fmt(x2)}{RST}")
    elif disc == 0:
        x = -b / (2*a)
        print(f"  {GRN}x = {BOLD}{_fmt(x)}{RST}  {DIM}(podwójny pierwiastek){RST}")
    else:
        # zespolone
        re_part = -b / (2*a)
        im_part = math.sqrt(-disc) / (2*a)
        print(f"  {YLW}x₁ = {BOLD}{_fmt(re_part)} + {_fmt(im_part)}i{RST}")
        print(f"  {YLW}x₂ = {BOLD}{_fmt(re_part)} - {_fmt(im_part)}i{RST}")

# ---------------------------------------------------------------------------
# Zmienne sesji
# ---------------------------------------------------------------------------

def _cmd_set(args: list, _t) -> None:
    if len(args) < 2:
        print(_t("math_usage_set")); return
    name = args[0]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        print(RED + _t("math_set_bad_name", name=name) + RST); return
    expr = " ".join(args[1:])
    val, err = _eval_expr(expr)
    if err:
        print(RED + _t("math_err_eval", expr=expr, err=err) + RST); return
    _session_vars[name] = val
    print(f"  {CYN}{name}{RST} = {GRN}{BOLD}{_fmt(val)}{RST}")


def _cmd_get(args: list, _t) -> None:
    if not args:
        print(_t("math_usage_get")); return
    name = args[0]
    if name not in _session_vars:
        print(RED + _t("math_get_not_found", name=name) + RST); return
    print(f"  {CYN}{name}{RST} = {GRN}{BOLD}{_fmt(_session_vars[name])}{RST}")


def _cmd_vars(_args: list, _t) -> None:
    if not _session_vars:
        print(_t("math_vars_empty")); return
    print(BOLD + CYN + _t("math_vars_title") + RST)
    print(_sep())
    for name, val in sorted(_session_vars.items()):
        print(f"  {YLW}{_pad(name, 16)}{RST}  {GRN}{_fmt(val)}{RST}")
    print(_sep())

# ---------------------------------------------------------------------------
# Historia
# ---------------------------------------------------------------------------

def _cmd_history(args: list, _t) -> None:
    n = 10
    if args:
        try:
            n = int(args[0])
        except ValueError:
            pass
    subset = _history[-n:]
    if not subset:
        print(_t("math_history_empty")); return
    print(BOLD + CYN + _t("math_history_title", n=len(subset)) + RST)
    print(_sep())
    for item in subset:
        ok_flag = GRN + "✓" + RST if item["ok"] else RED + "✗" + RST
        ts = DIM + item["ts"] + RST
        expr = CYN + item["expr"] + RST
        res  = (GRN if item["ok"] else RED) + item["result"] + RST
        print(f"  {ok_flag} {ts}  {expr}  =  {res}")
    print(_sep())


def _cmd_clear(_args: list, _t) -> None:
    global _history, _session_vars
    _history = []
    _session_vars = {}
    _save_history()
    print(GRN + _t("math_cleared") + RST)

# ---------------------------------------------------------------------------
# Eksport
# ---------------------------------------------------------------------------

def _cmd_export(args: list, _t) -> None:
    _ensure_cache()
    fname = args[0] if args else os.path.join(_CACHE_DIR, "export.json")
    data  = {
        "exported_at": datetime.now().isoformat(),
        "history":     _history,
        "variables":   {k: str(v) for k, v in _session_vars.items()},
    }
    try:
        with open(fname, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(GRN + _t("math_export_ok", path=fname) + RST)
    except Exception as exc:
        print(RED + _t("math_export_err", exc=exc) + RST)

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

def _cmd_help(_args: list, _t) -> None:
    print(BOLD + CYN + f"Math Engine v{_VERSION}" + RST)
    print(_sep())
    cmds = [
        ("math <wyrażenie>",         _t("math_help_eval")),
        ("math stat <l1> <l2> ...",  _t("math_help_stat")),
        ("math matrix <op> ...",     _t("math_help_matrix")),
        ("math trig <fn> <stopnie>", _t("math_help_trig")),
        ("math comb <n> <k>",        _t("math_help_comb")),
        ("math perm <n> <k>",        _t("math_help_perm")),
        ("math fact <n>",            _t("math_help_fact")),
        ("math prime <n>",           _t("math_help_prime")),
        ("math primes <n>",          _t("math_help_primes")),
        ("math gcd <a> <b>",         _t("math_help_gcd")),
        ("math lcm <a> <b>",         _t("math_help_lcm")),
        ("math conv <v> <z> <do>",   _t("math_help_conv")),
        ("math solve <a> <b> <c>",   _t("math_help_solve")),
        ("math set <nazwa> <expr>",  _t("math_help_set")),
        ("math get <nazwa>",         _t("math_help_get")),
        ("math vars",                _t("math_help_vars")),
        ("math history [n]",         _t("math_help_history")),
        ("math clear",               _t("math_help_clear")),
        ("math export [plik]",       _t("math_help_export")),
    ]
    for cmd, desc in cmds:
        print(f"  {YLW}{_pad(cmd, 28)}{RST}  {desc}")
    print(_sep())

# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_SUBCOMMANDS = {
    "stat":    _cmd_stat,
    "matrix":  _cmd_matrix,
    "trig":    _cmd_trig,
    "comb":    _cmd_comb,
    "perm":    _cmd_perm,
    "fact":    _cmd_fact,
    "prime":   _cmd_prime,
    "primes":  _cmd_primes,
    "gcd":     _cmd_gcd,
    "lcm":     _cmd_lcm,
    "conv":    _cmd_conv,
    "solve":   _cmd_solve,
    "set":     _cmd_set,
    "get":     _cmd_get,
    "vars":    _cmd_vars,
    "history": _cmd_history,
    "clear":   _cmd_clear,
    "export":  _cmd_export,
    "help":    _cmd_help,
}


def _cmd_math(args: list, _t) -> None:
    if not args:
        _cmd_help([], _t)
        return
    sub = args[0].lower()
    if sub in _SUBCOMMANDS:
        _SUBCOMMANDS[sub](args[1:], _t)
    else:
        # traktuj jako wyrażenie do ewaluacji
        _cmd_eval(args, _t)

# ---------------------------------------------------------------------------
# setup / teardown
# ---------------------------------------------------------------------------

def setup(terminal) -> None:
    _load_history()


    # Rejestracja w _integration – inne moduly moga korzystac z tego modulu
    # bez bezposredniego importu, eliminujac cykliczne zaleznosci.
    try:
        from . import _integration as _intg
        _intg.register("math_engine", {
            "eval_expr": _eval_expr,
        })
    except Exception:
        pass
    def _t(key: str, **kw):
        return terminal.t(key, **kw)

    def math_cmd(args):
        _cmd_math(args, _t)

    terminal.register_command(
        "math", math_cmd,
        description=_t("math_cmd_desc"),
        category=_t("cat_ecosystem"),
    )


def teardown(terminal) -> None:
    try:
        from . import _integration as _intg
        _intg.unregister("math_engine")
    except Exception:
        pass
    terminal.commands.pop("math", None)
