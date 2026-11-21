from __future__ import annotations

import logging
import re
from types import SimpleNamespace
from typing import Callable

from schemify.humanizer.llm_client import LLMHumanizerClient

logger = logging.getLogger(__name__)


class RuleBasedHumanizer:
    """Локальный быстрый транслятор кода C в лаконичный русский псевдокод."""

    @classmethod
    def try_humanize(cls, node) -> tuple[str | None, bool]:
        """Возвращает кортеж (новый_текст, needs_ai).

        Если needs_ai=True, ноду стоит отдать LLM для красивой формулировки.
        """
        text = node.text.strip()
        node_type = node.type

        # Системные узлы не меняем
        if node_type in {"START", "END", "terminator"}:
            return text, False

        # ГОСТ builder уже преобразует scanf/printf в читаемые подписи.
        if node_type == "io" and "scanf" not in text and "printf" not in text:
            return text, False

        # 1. Завершение работы
        if "return" in text:
            if re.search(r"return\s+0\s*;", text):
                return "Конец", False
            m = re.search(r"return\s+([^;]+);", text)
            if m:
                code = m.group(1).strip()
                return f"Выход с кодом {code}", False

        # 2. Ввод данных (scanf)
        if node_type in {"INPUT", "io"} or "scanf" in text:
            # Извлекаем переменные из scanf("...", &a, &b)
            scanf_match = re.search(r'scanf\s*\(\s*"[^"]*"\s*,\s*([^)]+)\)', text)
            if scanf_match:
                raw_args = scanf_match.group(1)
                # Очищаем от взятия адреса & и лишних пробелов
                vars_list = [v.strip().lstrip("&") for v in raw_args.split(",")]
                clean_vars = ", ".join(filter(None, vars_list))
                return f"Ввод: {clean_vars}", False
            return None, True  # Нестандартный scanf отдаем LLM

        # 3. Вывод данных (printf)
        if node_type == "OUTPUT" or "printf" in text:
            # Случай чистого переноса строки: printf("\n");
            if re.search(r'printf\s*\(\s*"\\n"\s*\)', text):
                return "Перевод строки", False

            # Простой строковый вывод без аргументов: printf("Текст: ")
            m_simple = re.search(r'printf\s*\(\s*"([^"]*)"\s*\)', text)
            if m_simple:
                msg = m_simple.group(1).replace("\\n", "").strip()
                # Если это шапка таблицы вида "| x | y |", делаем её компактной
                if re.match(r"^\|\s*[a-zA-Z_]\w*\s*\|\s*[a-zA-Z_]\w*\s*\|$", msg):
                    clean_header = msg.replace("|", " ").strip()
                    return f'Вывод шапки: {clean_header}', False
                return f'Вывод: "{msg}"' if msg else "Перевод строки", False

            # printf с переменными (включая табличный формат printf("| %3.1f | %14.8f |\n", x, y))
            m_arg = re.search(r'printf\s*\(\s*"[^"]*"\s*,\s*([^)]+)\)', text)
            if m_arg:
                raw_args = m_arg.group(1).strip()
                args_list = [a.strip() for a in raw_args.split(",")]
                # Если все аргументы — это простые переменные (x, y, sum, count)
                if all(re.match(r"^[a-zA-Z_]\w*$", a) for a in args_list):
                    return f"Вывод: {', '.join(args_list)}", False
                # Если внутри аргументов сложные вычисления -> отдаем в LLM
                return None, True

            return None, True

        # 4. Условия (ромбы)
        if node_type in {"DECISION", "SWITCH", "decision", "hexagon"}:
            # Если условие проверяет ввод через scanf:
            if "scanf" in text:
                scanf_match = re.search(r'scanf\s*\(\s*"[^"]*"\s*,\s*([^)]+)\)', text)
                if scanf_match:
                    raw_args = scanf_match.group(1)
                    vars_list = [v.strip().lstrip("&") for v in raw_args.split(",")]
                    clean_vars = ", ".join(filter(None, vars_list))
                    return f"Корректный ввод: {clean_vars}?", False

            if "printf" in text or "||" in text or "&&" in text:
                return None, True

            clean_cond = text.replace("(", "").replace(")", "").strip()
            return clean_cond, False

        # 5. Процессы (присваивания, инкременты, объявления)
        if node_type in {"PROCESS", "process", "predefined"}:
            # Тернарный оператор -> отдаем в ИИ
            if "?" in text and ":" in text:
                return None, True

            # Объединение простых строк процесса (после компактизации)
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            humanized_lines = []
            all_succeeded = True

            for line in lines:
                h_line = cls._humanize_single_process(line)
                if h_line is not None:
                    humanized_lines.append(h_line)
                else:
                    all_succeeded = False
                    break

            if all_succeeded and humanized_lines:
                return ";\n".join(humanized_lines), False

            return None, True

        return None, False

    @staticmethod
    def _humanize_single_process(stmt: str) -> str | None:
        stmt = stmt.rstrip(";").strip()

        # Инкременты и декременты
        if re.match(r"^\+\+([a-zA-Z_]\w*)$", stmt) or re.match(r"^([a-zA-Z_]\w*)\+\+$", stmt):
            var = stmt.replace("+", "")
            return f"{var} = {var} + 1"
        if re.match(r"^--([a-zA-Z_]\w*)$", stmt) or re.match(r"^([a-zA-Z_]\w*)--$", stmt):
            var = stmt.replace("-", "")
            return f"{var} = {var} - 1"

        # Составные присваивания: a += b -> a = a + b
        m_compound = re.match(r"^([a-zA-Z_]\w*)\s*([\+\-\*\/])=\s*(.+)$", stmt)
        if m_compound:
            var, op, expr = m_compound.groups()
            return f"{var} = {var} {op} {expr.strip()}"

        # Объявления простых переменных: int height; int width;
        m_decl = re.match(r"^(?:int|long\s+long|double|float|char)\s+([a-zA-Z_]\w*(?:\s*,\s*[a-zA-Z_]\w*)*)$", stmt)
        if m_decl:
            return f"Объявление: {m_decl.group(1)}"

        # Простое присваивание с объявлением: int row = 0; -> row = 0
        m_init = re.match(r"^(?:int|long\s+long|double|float|char)\s+([a-zA-Z_]\w*\s*=\s*.+)$", stmt)
        if m_init:
            return m_init.group(1)

        # Обычное присваивание: a = b + c
        if re.match(r"^[a-zA-Z_]\w*\s*=\s*[^?:]+$", stmt):
            return stmt

        return None


def humanize_diagram(
    diagram,
    use_ai: bool = True,
    on_ai_delegated: Callable[[], None] | None = None,
) -> tuple[object, bool]:
    """Хуманизирует подписи блоков ГОСТ-диаграммы; сложные передаёт в LLM."""
    logger.info("Хуманайзер: старт обработки графа")

    complex_nodes: dict[str, str] = {}
    local_count = 0

    for index, node in enumerate(diagram.shapes):
        if node.kind == "terminator":
            continue
        node_id = str(index)
        text = "\n".join(node.lines)
        new_text, needs_ai = RuleBasedHumanizer.try_humanize(
            SimpleNamespace(id=node_id, text=text, type=node.kind)
        )
        if new_text is not None:
            node.lines = new_text.splitlines()
            local_count += 1
        if needs_ai:
            complex_nodes[node_id] = text

    logger.info("Хуманайзер: локально обработано %d нод, в LLM уйдёт %d", local_count, len(complex_nodes))

    used_ai = False

    # Шаг 2: Если есть сложные ноды — уведомляем пользователя и отправляем пачку в LLM
    if use_ai and complex_nodes:
        used_ai = True
        if on_ai_delegated is not None:
            try:
                on_ai_delegated()
            except Exception as exc:
                logger.warning("Ошибка вызова on_ai_delegated: %s", exc)

        llm_client = LLMHumanizerClient()
        ai_results = llm_client.humanize_batch(complex_nodes)

        logger.info("Хуманайзер: ответ LLM получен для %d/%d нод", len(ai_results), len(complex_nodes))
        for index, node in enumerate(diagram.shapes):
            if str(index) in ai_results:
                node.lines = ai_results[str(index)].splitlines()

    return diagram, used_ai
