"""Синтаксическое дерево, не зависящее от парсера.

Фронтенд (tree-sitter-c или любой другой) превращает исходник в эти классы,
а всё остальное (раскладка, SVG) знает только про них. Благодаря этому
парсер можно заменить, не трогая движок отрисовки.

Тексты (cond, text, expr) - это уже готовые строки для подписей в блоках,
без завершающей ';' и без внешних скобок у условий.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Call:
    """Вызов функции, который является всем выражением-оператором: f(a, b);"""
    name: str
    args: list[str]


class Stmt:
    """Базовый класс операторов (маркер для isinstance)."""


@dataclass
class Block(Stmt):
    stmts: list[Stmt]
    line: int = field(default=0, kw_only=True)


@dataclass
class Decl(Stmt):
    """Объявление переменных: int a = 5, b;"""
    text: str
    calls: list[str] = field(default_factory=list)
    line: int = field(default=0, kw_only=True)


@dataclass
class ExprStmt(Stmt):
    """Оператор-выражение: присваивание, вызов, i++ ..."""
    text: str
    calls: list[str] = field(default_factory=list)   # имена всех вызванных функций
    top_call: Call | None = None                      # если оператор - это один вызов
    line: int = field(default=0, kw_only=True)


@dataclass
class Return(Stmt):
    expr: str | None
    calls: list[str] = field(default_factory=list)
    line: int = field(default=0, kw_only=True)


@dataclass
class If(Stmt):
    cond: str
    then: Stmt | None
    orelse: Stmt | None
    line: int = field(default=0, kw_only=True)


@dataclass
class While(Stmt):
    cond: str
    body: Stmt | None
    line: int = field(default=0, kw_only=True)


@dataclass
class DoWhile(Stmt):
    body: Stmt | None
    cond: str
    line: int = field(default=0, kw_only=True)


@dataclass
class For(Stmt):
    init: Stmt | None        # Decl или ExprStmt
    cond: str | None
    update: str | None
    body: Stmt | None
    line: int = field(default=0, kw_only=True)


@dataclass
class SwitchCase:
    """Одна метка switch вместе с телом до следующей метки (как в исходнике)."""
    values: list[str]
    is_default: bool
    body: list[Stmt]


@dataclass
class Switch(Stmt):
    expr: str
    cases: list[SwitchCase]
    line: int = field(default=0, kw_only=True)


@dataclass
class Break(Stmt):
    line: int = field(default=0, kw_only=True)


@dataclass
class Continue(Stmt):
    line: int = field(default=0, kw_only=True)


@dataclass
class Unsupported(Stmt):
    """Конструкция, которую пока не умеем (goto, метки ...). Рисуется как процесс."""
    text: str
    reason: str
    line: int = field(default=0, kw_only=True)


@dataclass
class Function:
    name: str
    params: str                 # как в исходнике, со скобками: "(int n, int m)"
    return_type: str
    body: Block
    line: int = 0

    @property
    def is_main(self) -> bool:
        return self.name == "main"


@dataclass
class Program:
    functions: list[Function]
    warnings: list[str] = field(default_factory=list)
