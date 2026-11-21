"""Измерение и перенос текста, подписи ввода/вывода, размеры блоков.

Шрифт заранее неизвестен (SVG рисует тот, кто его откроет), поэтому ширина
оценивается по таблице средних ширин символов с запасом (Options.text_scale).
"""
from __future__ import annotations

import re

from .options import Options
from .syntax import Call

# --- ширина символов (доля от кегля, для Times New Roman) -------------------
_NARROW = set("ijltfI.,;:'!|()[]{} 1")
_WIDE = set("mwMWЖШЩЮЫФМЖжшщюыфм@%")
_CYR_UP = set("АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ")


def _char_em(ch: str) -> float:
    if ch == " ":
        return 0.25
    if ch in "ijl.,;:'!|":
        return 0.28
    if ch in "()[]{}1tf":
        return 0.34
    if ch in "mwMW":
        return 0.78
    if ch in "ЖШЩЮЫФМжшщюыфм":
        return 0.72
    if ch in _CYR_UP or ch.isupper():
        return 0.68
    if ch.isdigit():
        return 0.5
    if ch in "+-=<>*/&^~%":
        return 0.56
    if ch.isalpha():
        return 0.5
    return 0.55


def text_width(s: str, o: Options) -> float:
    return sum(_char_em(c) for c in s) * o.font_size * o.text_scale


_SPLIT = re.compile(r"(?<=[,;]) |(?<=&&) |(?<=\|\|) |\s+")


def _hard_split(token: str, max_w: float, o: Options) -> list[str]:
    parts, cur = [], ""
    for ch in token:
        if cur and text_width(cur + ch, o) > max_w:
            parts.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        parts.append(cur)
    return parts


def wrap(text: str, max_w: float, o: Options) -> list[str]:
    """Переносит текст по словам так, чтобы строка не превышала max_w."""
    out: list[str] = []
    for para in text.split("\n"):
        tokens = [t for t in _SPLIT.split(para) if t]
        cur = ""
        for tok in tokens:
            cand = tok if not cur else cur + " " + tok
            if text_width(cand, o) <= max_w:
                cur = cand
                continue
            if cur:
                out.append(cur)
                cur = ""
            if text_width(tok, o) <= max_w:
                cur = tok
            else:
                pieces = _hard_split(tok, max_w, o)
                out.extend(pieces[:-1])
                cur = pieces[-1]
        out.append(cur)
    return out or [""]


# --- размеры блоков --------------------------------------------------------
MIN_W = 160
MIN_H = 48
PAD_X = 16
PAD_Y = 12
MAX_TEXT_W = 300
SKEW = 16      # скос параллелограмма (ввод/вывод)
SLOPE = 22     # скос шестиугольника (подготовка)
BAR = 14       # отступ вертикальных линий предопределённого процесса


def measure(kind: str, text: str, o: Options) -> tuple[float, float, list[str]]:
    """Возвращает (ширина, высота, строки) блока заданного вида."""
    lh = o.line_height
    if kind == "decision":
        return _measure_decision(text, o)

    extra = {"predefined": 2 * BAR, "io": 2 * SKEW, "hexagon": 2 * SLOPE}.get(kind, 0)
    lines = wrap(text, MAX_TEXT_W, o)
    tw = max(text_width(ln, o) for ln in lines)
    if kind == "terminator":
        return max(120.0, tw + 44), 40.0, lines
    w = max(MIN_W + extra * 0.0, tw + 2 * PAD_X + extra)
    h = max(MIN_H, len(lines) * lh + 2 * PAD_Y)
    return w, h, lines


def _measure_decision(text: str, o: Options) -> tuple[float, float, list[str]]:
    """Подбирает перенос так, чтобы ромб был приплюснутым (W:H около 2:1)."""
    lh = o.line_height
    best = None
    for max_w in range(70, 321, 10):
        lines = wrap(text, max_w, o)
        tw = max(text_width(ln, o) for ln in lines)
        th = len(lines) * lh
        w = 2 * tw + 28
        h = 2 * th + 22
        w = max(w, 170.0)
        h = max(h, 76.0)
        ratio = w / h
        area = w * h
        # предпочитаем соотношение 1.8..2.4, дальше - минимальная площадь
        score = (0 if 1.8 <= ratio <= 3.0 else abs(ratio - 2.4), len(lines), area)
        if best is None or score < best[0]:
            best = (score, w, h, lines)
    _, w, h, lines = best
    return w, h, lines


# --- ввод / вывод ----------------------------------------------------------
INPUT_FUNCS = {"scanf", "fscanf", "scanf_s", "gets", "fgets", "getchar", "getc", "fgetc", "gets_s"}
OUTPUT_FUNCS = {"printf", "fprintf", "printf_s", "puts", "putchar", "fputs", "putc", "fputc"}
IO_FUNCS = INPUT_FUNCS | OUTPUT_FUNCS

_FMT = re.compile(
    r"%(?:%|[-+ #0]*(?:\*|\d+)?(?:\.(?:\*|\d+))?(?:hh|h|ll|l|L|z|j|t)?[diouxXeEfFgGaAcspn])"
)


def _is_string_literal(s: str) -> bool:
    return len(s) >= 2 and s[0] == '"' and s[-1] == '"'


def _format_printf(fmt: str, args: list[str]) -> str:
    inner = fmt[1:-1]
    parts: list[str] = []
    pos = 0
    arg_i = 0
    lit = ""
    for m in _FMT.finditer(inner):
        lit += inner[pos:m.start()]
        pos = m.end()
        if m.group(0) == "%%":
            lit += "%"
            continue
        if lit:
            parts.append(f'"{lit}"')
            lit = ""
        parts.append(args[arg_i] if arg_i < len(args) else "?")
        arg_i += 1
    lit += inner[pos:]
    if lit.endswith("\\n"):
        lit = lit[:-2]
    if lit:
        parts.append(f'"{lit}"')
    parts.extend(args[arg_i:])
    return ", ".join(parts)


def format_io(call: Call, o: Options) -> str | None:
    """Текст блока ввода/вывода для вызова scanf/printf/puts... или None."""
    name, args = call.name, call.args
    if name in OUTPUT_FUNCS:
        if name in ("fprintf", "fputs", "fputc", "putc"):
            args = args[1:]
        if name in ("printf", "fprintf", "printf_s") and args and _is_string_literal(args[0]):
            body = _format_printf(args[0], args[1:])
        elif name in ("puts", "fputs") and args and _is_string_literal(args[0]):
            body = args[0][:-1].removesuffix("\\n") + '"'
        else:
            body = ", ".join(args)
        return f"{o.output_prefix}: {body}" if body else o.output_prefix
    if name in INPUT_FUNCS:
        if name in ("scanf", "scanf_s"):
            targets = args[1:]
        elif name == "fscanf":
            targets = args[2:]
        elif name in ("fgets",):
            targets = args[:1]
        elif name in ("gets", "gets_s"):
            targets = args[:1]
        else:
            targets = []
        targets = [t[1:].strip() if t.startswith("&") else t for t in targets]
        if targets:
            return f"{o.input_prefix}: " + ", ".join(targets)
        return o.input_prefix
    return None


# --- декоративный вывод ----------------------------------------------------
# printf("=========\n"), puts("-----"), printf("===== ИТОГ =====\n") - рамки и
# разделители не несут алгоритмического смысла, на схеме им не место.
_DECOR = r"=\-_*#~+|<>/\\"
_DECOR_ONLY = re.compile(rf"^[{_DECOR}\s]+$")
_DECOR_BANNER = re.compile(rf"^[{_DECOR}]{{3,}}.*?[{_DECOR}]{{3,}}$")
_ESC = re.compile(r"\\[ntrfv]")
_PLAIN_OUT = {"printf", "puts", "fputs", "fprintf", "printf_s"}


def is_decorative_output(call: Call) -> bool:
    """True для вывода одной строковой константы-рамки без подстановок."""
    if call.name not in _PLAIN_OUT:
        return False
    args = call.args
    if call.name in ("fprintf", "fputs"):
        args = args[1:]
    if len(args) != 1 or not _is_string_literal(args[0]):
        return False                    # есть переменные - это уже данные
    inner = args[0][1:-1]
    if "%" in inner:
        return False
    inner = _ESC.sub(" ", inner).strip()
    if not inner:
        return False                    # пустая строка / перевод строки - не рамка
    return bool(_DECOR_ONLY.match(inner) or _DECOR_BANNER.match(inner))