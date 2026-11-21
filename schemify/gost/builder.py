"""Превращает синтаксическое дерево функции в готовую раскладку (Diagram).

Здесь живут все решения «что нарисовать»:
  объявление / присваивание          -> процесс (прямоугольник)
  scanf/printf/puts ...              -> ввод/вывод (параллелограмм)
  вызов своей функции (и рекурсия)   -> предопределённый процесс (рамка с полосами)
  if / while / do-while / switch     -> решение (ромб)
  for                                -> «подготовка» (шестиугольник) или ромб
  return expr                        -> процесс; return; / break / continue -> переход
"""
from __future__ import annotations

from dataclasses import dataclass

from . import layout as L
from . import syntax as S
from .options import Options
from .text import IO_FUNCS, format_io, is_decorative_output, measure


@dataclass
class Diagram:
    name: str
    shapes: list[L.Shape]
    edges: list[L.Edge]
    labels: list[L.Label]
    width: float
    height: float
    warnings: list[str]


class Builder:
    def __init__(self, program: S.Program, o: Options):
        self.o = o
        self.user_funcs = {f.name for f in program.functions}
        self.warnings: list[str] = []

    # ------------------------------------------------------------------ API
    def function(self, fn: S.Function) -> Diagram:
        o = self.o
        self.warnings = []
        stmts = list(fn.body.stmts)
        # Завершающий return (включая обязательный `return 0` в int main)
        # уже выражен терминатором «Конец», отдельный блок здесь избыточен.
        if stmts and isinstance(stmts[-1], S.Return):
            stmts.pop()
        body = self.seq_of(stmts, tail=True)

        if fn.is_main or not o.signature_in_start:
            start_text = o.start_text
        else:
            start_text = f"{fn.name}{fn.params}"
        start = self.head("terminator", start_text)
        end = self.head("terminator", o.end_text)
        frag = L.make_function(start, body, end, o, self.warnings)
        return self.to_diagram(fn.name, frag)

    # ------------------------------------------------------------- helpers
    def head(self, kind: str, text: str) -> L.Head:
        w, h, lines = measure(kind, text, self.o)
        return kind, w, h, lines

    def blk(self, kind: str, text: str) -> L.Frag:
        kind_, w, h, lines = self.head(kind, text)
        return L.block(kind_, w, h, lines)

    def uses_user_func(self, calls: list[str]) -> bool:
        return any(c in self.user_funcs for c in calls)

    def seq_of(self, stmts: list[S.Stmt], tail: bool = False) -> L.Frag | None:
        frags: list[L.Frag] = []
        for i, s in enumerate(stmts):
            is_last = i == len(stmts) - 1
            f = self.stmt(s, tail=tail and is_last)
            if f is None:
                continue
            frags.append(f)
            if not f.falls:
                if i < len(stmts) - 1:
                    self.warnings.append(
                        f"код после перехода (строка {getattr(s, 'line', '?')}) недостижим - пропущен")
                break
        return L.seq(frags)

    def sub(self, s: S.Stmt | None, tail: bool = False) -> L.Frag | None:
        """Вложенный оператор (тело ветки/цикла) как фрагмент или None."""
        if s is None:
            return None
        if isinstance(s, S.Block):
            return self.seq_of(s.stmts, tail=tail)
        return self.seq_of([s], tail=tail)

    # -------------------------------------------------------------- stmts
    def stmt(self, s: S.Stmt, tail: bool = False) -> L.Frag | None:
        o = self.o
        if isinstance(s, S.Block):
            return self.seq_of(s.stmts, tail=tail)

        if isinstance(s, S.Decl):
            kind = "predefined" if self.uses_user_func(s.calls) else "process"
            return self.blk(kind, s.text)

        if isinstance(s, S.ExprStmt):
            if o.skip_decorative and s.top_call is not None \
                    and is_decorative_output(s.top_call):
                return None
            if s.top_call is not None and s.top_call.name in IO_FUNCS:
                text = format_io(s.top_call, o)
                if text is not None:
                    return self.blk("io", text)
            kind = "predefined" if self.uses_user_func(s.calls) else "process"
            return self.blk(kind, s.text)

        if isinstance(s, S.Return):
            if s.expr is None:
                return L.jump_frag("return")
            kind = "predefined" if self.uses_user_func(s.calls) else "process"
            b = self.blk(kind, f"return {s.expr}")
            if tail:                      # return в конце функции: сразу «Конец»
                return b
            return L.seq([b, L.jump_frag("return")])

        if isinstance(s, S.Break):
            return L.jump_frag("break")
        if isinstance(s, S.Continue):
            return L.jump_frag("continue")

        if isinstance(s, S.If):
            head = self.head("decision", s.cond)
            T = self.sub(s.then, tail=tail)
            E = self.sub(s.orelse, tail=tail)
            return L.make_if(head, T, E, o)

        if isinstance(s, S.While):
            body = self.sub(self.strip_tail_continue(s.body))
            return L.make_while(self.head("decision", s.cond or "1"), body, None, o)

        if isinstance(s, S.DoWhile):
            body = self.sub(self.strip_tail_continue(s.body))
            return L.make_do_while(self.head("decision", s.cond), body, o)

        if isinstance(s, S.For):
            return self.for_loop(s)

        if isinstance(s, S.Switch):
            return self.switch(s)

        if isinstance(s, S.Unsupported):
            self.warnings.append(f"строка {s.line}: {s.reason} - нарисовано как процесс")
            return self.blk("process", s.text)

        self.warnings.append(f"неизвестный оператор {type(s).__name__}")
        return None

    # --------------------------------------------------------------- loops
    @staticmethod
    def strip_tail_continue(body: S.Stmt | None) -> S.Stmt | None:
        """`continue;` в самом конце тела цикла ничего не меняет - убираем."""
        if isinstance(body, S.Block) and body.stmts and isinstance(body.stmts[-1], S.Continue):
            return S.Block(body.stmts[:-1], line=body.line)
        if isinstance(body, S.Continue):
            return None
        return body

    def for_loop(self, s: S.For) -> L.Frag | None:
        o = self.o
        body_stmt = self.strip_tail_continue(s.body)
        body = self.sub(body_stmt)

        def clean(t: str | None) -> str:
            return (t or "").strip().rstrip(";").strip()

        init_text = clean(s.init.text) if isinstance(s.init, (S.Decl, S.ExprStmt)) else ""
        if o.for_style == "diamond":
            parts: list[L.Frag | None] = []
            if init_text:
                parts.append(self.blk("process", init_text))
            post = self.blk("process", clean(s.update)) if clean(s.update) else None
            loop = L.make_while(self.head("decision", clean(s.cond) or "1"), body, post, o)
            parts.append(loop)
            return L.seq([p for p in parts if p is not None])

        text = "; ".join([init_text, clean(s.cond), clean(s.update)])
        text = text.replace(";  ;", "; ;")
        loop = L.make_while(self.head("hexagon", text), body, None, o, labels=False)
        return loop

    # -------------------------------------------------------------- switch
    def switch(self, s: S.Switch) -> L.Frag:
        o = self.o
        # 1. склеиваем метки с пустым телом: `case 1: case 2: ...`
        merged: list[tuple[list[str], bool, list[S.Stmt]]] = []
        pend_vals: list[str] = []
        pend_def = False
        for c in s.cases:
            pend_vals += c.values
            pend_def = pend_def or c.is_default
            if not c.body and c is not s.cases[-1]:
                continue
            merged.append((pend_vals, pend_def, c.body))
            pend_vals, pend_def = [], False

        if not any(d for _, d, _ in merged):
            merged.append(([], True, []))           # неявный default

        clauses: list[L.Clause] = []
        for vals, is_def, body in merged:
            label_parts = list(vals)
            if is_def:
                label_parts.append(o.default_label)
            label = ", ".join(label_parts)

            stmts = list(body)
            # break в конце ветки - это просто выход из switch
            explicit_break = False
            if stmts and isinstance(stmts[-1], S.Break):
                stmts.pop()
                explicit_break = True
            frag = self.seq_of(stmts)
            breaks = explicit_break or (frag is not None and not frag.falls)
            clauses.append(L.Clause(label, frag, breaks))
        # default без тела в середине не должен «проваливаться»
        return L.make_switch(self.head("decision", s.expr), clauses, o)

    # ------------------------------------------------------------- finish
    def to_diagram(self, name: str, f: L.Frag) -> Diagram:
        m = self.o.margin
        xs: list[float] = []
        ys: list[float] = []
        for sh in f.shapes:
            xs += [sh.x - sh.w / 2, sh.x + sh.w / 2]
            ys += [sh.y - sh.h / 2, sh.y + sh.h / 2]
        for e in f.edges:
            for x, y in e.pts:
                xs.append(x)
                ys.append(y)
        from .text import text_width
        for lb in f.labels:
            tw = text_width(lb.text, self.o)
            if lb.anchor == "end":
                xs += [lb.x - tw, lb.x]
            elif lb.anchor == "middle":
                xs += [lb.x - tw / 2, lb.x + tw / 2]
            else:
                xs += [lb.x, lb.x + tw]
            ys += [lb.y - self.o.font_size, lb.y + 4]
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
        dx, dy = m - minx, m - miny
        shapes = [L.Shape(s.kind, s.x + dx, s.y + dy, s.w, s.h, s.lines) for s in f.shapes]
        edges = [L.Edge([(x + dx, y + dy) for x, y in e.pts], e.arrow) for e in f.edges]
        labels = [L.Label(lb.x + dx, lb.y + dy, lb.text, lb.anchor) for lb in f.labels]
        return Diagram(name, shapes, edges, labels,
                       (maxx - minx) + 2 * m, (maxy - miny) + 2 * m, list(self.warnings))