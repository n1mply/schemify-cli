"""schemify: блок-схемы по ГОСТ 19.701-90 из кода на C.

    from schemify import code_to_svgs
    svgs = code_to_svgs(source)          # {"main": "<svg ...>", "fact": "<svg ...>"}

Конвейер:  C -> (фронтенд) syntax.Program -> builder -> layout -> svg
"""
from __future__ import annotations

from . import syntax
from .builder import Builder, Diagram
from .options import Options
from .svg import render_svg

__all__ = ["Options", "Diagram", "build_diagrams", "code_to_svgs", "render_svg", "syntax"]


def build_diagrams(code: str | None = None, options: Options | None = None, *,
                   program: syntax.Program | None = None,
                   frontend: str | object = "tree-sitter") -> list[Diagram]:
    """По одной диаграмме на каждую функцию. main - первой.

    Либо передайте исходник `code` (разберётся фронтендом), либо уже готовый
    `program` (удобно для тестов и своих фронтендов).
    """
    o = options or Options()
    if program is None:
        if code is None:
            raise ValueError("нужен code или program")
        if isinstance(frontend, str):
            from .frontends import get_frontend
            frontend = get_frontend(frontend)
        program = frontend.parse(code)
    builder = Builder(program, o)
    funcs = sorted(program.functions, key=lambda f: not f.is_main)
    diagrams = []
    for fn in funcs:
        d = builder.function(fn)
        d.warnings = program.warnings + d.warnings
        diagrams.append(d)
    return diagrams


def code_to_svgs(code: str, options: Options | None = None, *,
                 frontend: str | object = "tree-sitter") -> dict[str, str]:
    o = options or Options()
    return {d.name: render_svg(d, o) for d in build_diagrams(code, o, frontend=frontend)}
