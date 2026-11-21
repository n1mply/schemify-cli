from __future__ import annotations

from .. import syntax as S


def get_frontend(name: str = "tree-sitter"):
    """Возвращает объект с методом parse(code) -> syntax.Program."""
    if name in ("tree-sitter", "tree_sitter", "ts"):
        from .tree_sitter_c import TreeSitterC
        return TreeSitterC()
    raise ValueError(f"неизвестный фронтенд: {name!r}")


def parse(code: str, frontend: str = "tree-sitter") -> S.Program:
    return get_frontend(frontend).parse(code)
