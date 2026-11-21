"""Diagram -> SVG.

Стрелки рисуются полигонами (а не <marker>), чтобы результат одинаково
выглядел в браузере, cairosvg, resvg, Inkscape и т.д.
"""
from __future__ import annotations

import math
from xml.sax.saxutils import escape

from .builder import Diagram
from .layout import Edge, Shape
from .options import Options
from .text import BAR, SKEW, SLOPE

ARROW_LEN = 10
ARROW_HALF = 4


def _f(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s if s else "0"


def _pts(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{_f(x)},{_f(y)}" for x, y in points)


def _shape_svg(s: Shape, o: Options) -> list[str]:
    x0, x1 = s.x - s.w / 2, s.x + s.w / 2
    y0, y1 = s.y - s.h / 2, s.y + s.h / 2
    out: list[str] = []
    k = s.kind
    if k == "terminator":
        r = s.h / 2
        out.append(f'<rect x="{_f(x0)}" y="{_f(y0)}" width="{_f(s.w)}" height="{_f(s.h)}" '
                   f'rx="{_f(r)}" ry="{_f(r)}"/>')
    elif k == "process":
        out.append(f'<rect x="{_f(x0)}" y="{_f(y0)}" width="{_f(s.w)}" height="{_f(s.h)}"/>')
    elif k == "predefined":
        out.append(f'<rect x="{_f(x0)}" y="{_f(y0)}" width="{_f(s.w)}" height="{_f(s.h)}"/>')
        out.append(f'<line x1="{_f(x0 + BAR)}" y1="{_f(y0)}" x2="{_f(x0 + BAR)}" y2="{_f(y1)}"/>')
        out.append(f'<line x1="{_f(x1 - BAR)}" y1="{_f(y0)}" x2="{_f(x1 - BAR)}" y2="{_f(y1)}"/>')
    elif k == "io":
        pts = [(x0 + SKEW, y0), (x1, y0), (x1 - SKEW, y1), (x0, y1)]
        out.append(f'<polygon points="{_pts(pts)}"/>')
    elif k == "decision":
        pts = [(s.x, y0), (x1, s.y), (s.x, y1), (x0, s.y)]
        out.append(f'<polygon points="{_pts(pts)}"/>')
    elif k == "hexagon":
        pts = [(x0 + SLOPE, y0), (x1 - SLOPE, y0), (x1, s.y), (x1 - SLOPE, y1),
               (x0 + SLOPE, y1), (x0, s.y)]
        out.append(f'<polygon points="{_pts(pts)}"/>')
    else:
        raise ValueError(f"unknown shape kind {k}")

    # текст: базовая линия считается вручную (dominant-baseline поддерживают не все)
    n = len(s.lines)
    lh = o.line_height
    first = s.y - (n - 1) * lh / 2 + o.font_size * 0.34
    tspans = "".join(
        f'<tspan x="{_f(s.x)}" y="{_f(first + i * lh)}">{escape(line)}</tspan>'
        for i, line in enumerate(s.lines)
    )
    out.append(f'<text text-anchor="middle" fill="#000" stroke="none" '
               f'font-family="{o.font_family}" font-size="{o.font_size}">{tspans}</text>')
    return out


def _arrowhead(p0: tuple[float, float], p1: tuple[float, float]) -> str:
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    ln = math.hypot(dx, dy) or 1.0
    ux, uy = dx / ln, dy / ln
    bx, by = p1[0] - ux * ARROW_LEN, p1[1] - uy * ARROW_LEN
    nx, ny = -uy, ux
    pts = [(p1[0], p1[1]), (bx + nx * ARROW_HALF, by + ny * ARROW_HALF),
           (bx - nx * ARROW_HALF, by - ny * ARROW_HALF)]
    return f'<polygon fill="#000" stroke="none" points="{_pts(pts)}"/>'


def _edge_svg(e: Edge) -> list[str]:
    if len(e.pts) < 2:
        return []
    out = [f'<polyline points="{_pts(e.pts)}"/>']
    if e.arrow:
        out.append(_arrowhead(e.pts[-2], e.pts[-1]))
    return out


def render_svg(d: Diagram, o: Options | None = None) -> str:
    o = o or Options()
    sw = o.stroke_width
    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_f(d.width)}" height="{_f(d.height)}" '
        f'viewBox="0 0 {_f(d.width)} {_f(d.height)}">')
    parts.append(f'<rect width="{_f(d.width)}" height="{_f(d.height)}" fill="#fff"/>')

    parts.append(f'<g fill="none" stroke="#000" stroke-width="{sw}" stroke-linejoin="miter">')
    for e in d.edges:
        parts.extend(_edge_svg(e))
    parts.append("</g>")

    parts.append(f'<g fill="#fff" stroke="#000" stroke-width="{sw}" stroke-linejoin="miter">')
    for s in d.shapes:
        parts.extend(_shape_svg(s, o))
    parts.append("</g>")

    for lb in d.labels:
        parts.append(f'<text x="{_f(lb.x)}" y="{_f(lb.y)}" text-anchor="{lb.anchor}" '
                     f'fill="#000" stroke="none" font-family="{o.font_family}" '
                     f'font-size="{o.font_size - 1}">{escape(lb.text)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)
