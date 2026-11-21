"""Фронтенд на tree-sitter-c: исходник C -> schemify.syntax.Program.

Зависимости:  pip install tree-sitter tree-sitter-c

Названия узлов и полей - из грамматики tree-sitter-c. Код написан так, чтобы
работать и со старыми (else без else_clause, for без поля body), и с новыми
версиями грамматики.
"""
from __future__ import annotations

import re

from .. import syntax as S

_WS = re.compile(r"\s*\n\s*")


class TreeSitterC:
    def __init__(self) -> None:
        import tree_sitter_c
        from tree_sitter import Language, Parser

        lang = Language(tree_sitter_c.language())
        try:                                   # py-tree-sitter >= 0.22
            self.parser = Parser(lang)
        except TypeError:                      # более старый API
            self.parser = Parser()
            self.parser.set_language(lang)

    # ------------------------------------------------------------------ API
    def parse(self, code: str) -> S.Program:
        self.src = code.encode("utf-8")
        self.warnings: list[str] = []
        tree = self.parser.parse(self.src)
        root = tree.root_node
        if root.has_error:
            self._collect_errors(root)

        funcs: list[S.Function] = []
        for n in root.children:
            if n.type == "function_definition":
                fn = self._function(n)
                if fn is not None:
                    funcs.append(fn)
        return S.Program(funcs, self.warnings)

    # -------------------------------------------------------------- helpers
    def _text(self, n) -> str:
        return self.src[n.start_byte:n.end_byte].decode("utf-8")

    def _norm(self, n) -> str:
        return _WS.sub(" ", self._text(n)).strip()

    def _line(self, n) -> int:
        return n.start_point[0] + 1

    def _named(self, n) -> list:
        return [c for c in n.named_children if c.type != "comment"]

    def _collect_errors(self, node) -> None:
        stack = [node]
        while stack:
            n = stack.pop()
            if n.type == "ERROR" or n.is_missing:
                self.warnings.append(f"синтаксическая ошибка около строки {self._line(n)}")
            stack.extend(n.children)

    def _strip_parens(self, n) -> str:
        """Текст условия без внешних скобок parenthesized_expression."""
        if n is None:
            return ""
        if n.type == "parenthesized_expression":
            inner = self._named(n)
            if inner:
                return self._norm(inner[0])
        return self._norm(n)

    def _calls(self, n) -> list[str]:
        names: list[str] = []
        stack = [n]
        while stack:
            x = stack.pop()
            if x.type == "call_expression":
                fn = x.child_by_field_name("function")
                if fn is not None and fn.type == "identifier":
                    names.append(self._text(fn))
            stack.extend(x.children)
        return names

    def _call_info(self, n) -> S.Call | None:
        if n.type != "call_expression":
            return None
        fn = n.child_by_field_name("function")
        if fn is None or fn.type != "identifier":
            return None
        args_n = n.child_by_field_name("arguments")
        args = [self._norm(a) for a in self._named(args_n)] if args_n is not None else []
        return S.Call(self._text(fn), args)

    # ------------------------------------------------------------ functions
    def _function(self, n) -> S.Function | None:
        d = n.child_by_field_name("declarator")
        while d is not None and d.type in (
                "pointer_declarator", "parenthesized_declarator", "attributed_declarator"):
            nxt = d.child_by_field_name("declarator")
            d = nxt if nxt is not None else (self._named(d)[-1] if self._named(d) else None)
        if d is None or d.type != "function_declarator":
            self.warnings.append(f"не удалось разобрать функцию в строке {self._line(n)}")
            return None
        name_n = d.child_by_field_name("declarator")
        params_n = d.child_by_field_name("parameters")
        type_n = n.child_by_field_name("type")
        body = n.child_by_field_name("body")
        return S.Function(
            name=self._text(name_n) if name_n is not None else "?",
            params=self._norm(params_n) if params_n is not None else "()",
            return_type=self._norm(type_n) if type_n is not None else "",
            body=self._compound(body),
            line=self._line(n),
        )

    # ----------------------------------------------------------- statements
    def _compound(self, n) -> S.Block:
        stmts: list[S.Stmt] = []
        for c in self._named(n):
            s = self._stmt(c)
            if s is not None:
                stmts.append(s)
        return S.Block(stmts, line=self._line(n))

    def _stmt(self, n) -> S.Stmt | None:
        t = n.type
        line = self._line(n)

        # Tree-sitter normally represents braces as anonymous tokens, but in
        # recovered/error trees a brace can be wrapped in a named ERROR node.
        # Treating that node as Unsupported creates an empty process block
        # when its text is only "{" or "}" (common with K&R-style brace
        # placement and imperfect snippets).
        raw = self._norm(n)
        if not raw or raw in {"{", "}"}:
            return None

        if t == "compound_statement":
            return self._compound(n)

        if t == "declaration":
            return S.Decl(self._norm(n).rstrip(";").strip(), self._calls(n), line=line)

        if t == "expression_statement":
            kids = self._named(n)
            if not kids:                         # пустой оператор ';'
                return None
            e = kids[0]
            return S.ExprStmt(self._norm(e), self._calls(e), self._call_info(e), line=line)

        if t == "if_statement":
            cond = self._strip_parens(n.child_by_field_name("condition"))
            then = self._stmt_or_none(n.child_by_field_name("consequence"))
            alt = n.child_by_field_name("alternative")
            if alt is not None and alt.type == "else_clause":
                kids = self._named(alt)
                alt = kids[0] if kids else None
            return S.If(cond, then, self._stmt_or_none(alt), line=line)

        if t == "while_statement":
            return S.While(self._strip_parens(n.child_by_field_name("condition")),
                           self._stmt_or_none(n.child_by_field_name("body")), line=line)

        if t == "do_statement":
            return S.DoWhile(self._stmt_or_none(n.child_by_field_name("body")),
                             self._strip_parens(n.child_by_field_name("condition")), line=line)

        if t == "for_statement":
            return self._for(n)

        if t == "switch_statement":
            return self._switch(n)

        if t == "return_statement":
            kids = self._named(n)
            if kids:
                return S.Return(self._norm(kids[0]), self._calls(kids[0]), line=line)
            return S.Return(None, [], line=line)

        if t == "break_statement":
            return S.Break(line=line)
        if t == "continue_statement":
            return S.Continue(line=line)

        if t == "comment" or t.startswith("preproc_"):
            return None

        if t in ("goto_statement", "labeled_statement"):
            return S.Unsupported(self._norm(n).rstrip(";"), f"{t} не поддерживается", line=line)

        return S.Unsupported(self._norm(n).rstrip(";"), f"узел '{t}' не поддерживается", line=line)

    def _stmt_or_none(self, n) -> S.Stmt | None:
        return None if n is None else self._stmt(n)

    def _for(self, n) -> S.For:
        line = self._line(n)
        init_n = n.child_by_field_name("initializer") or n.child_by_field_name("init")
        cond_n = n.child_by_field_name("condition")
        upd_n = n.child_by_field_name("update")
        body_n = n.child_by_field_name("body")
        if body_n is None:                      # старые версии: тело без имени поля
            kids = self._named(n)
            body_n = kids[-1] if kids else None

        init: S.Stmt | None = None
        if init_n is not None:
            if init_n.type == "declaration":
                init = S.Decl(self._norm(init_n).rstrip(";").strip(), self._calls(init_n), line=line)
            else:
                init = S.ExprStmt(self._norm(init_n), self._calls(init_n), None, line=line)
        return S.For(
            init=init,
            cond=self._norm(cond_n) if cond_n is not None else None,
            update=self._norm(upd_n) if upd_n is not None else None,
            body=self._stmt_or_none(body_n),
            line=line,
        )

    def _switch(self, n) -> S.Switch:
        expr = self._strip_parens(n.child_by_field_name("condition"))
        body = n.child_by_field_name("body")
        cases: list[S.SwitchCase] = []
        if body is not None:
            for c in self._named(body):
                if c.type != "case_statement":
                    # операторы вне case (редкость): добавляем к предыдущей метке
                    s = self._stmt(c)
                    if s is not None and cases:
                        cases[-1].body.append(s)
                    continue
                value = c.child_by_field_name("value")
                is_default = value is None
                stmts: list[S.Stmt] = []
                for k in self._named(c):
                    if value is not None and k.start_byte == value.start_byte \
                            and k.end_byte == value.end_byte:
                        continue
                    s = self._stmt(k)
                    if s is not None:
                        stmts.append(s)
                cases.append(S.SwitchCase(
                    [self._norm(value)] if value is not None else [], is_default, stmts))
        return S.Switch(expr, cases, line=self._line(n))
