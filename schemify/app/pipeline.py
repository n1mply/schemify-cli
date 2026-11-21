"""Генерация схем: C-файл -> диаграммы ГОСТ -> (хуманайзер) -> png/svg/drawio."""
from __future__ import annotations

import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from schemify.app.config import Config
from schemify.gost import Options, build_diagrams
from schemify.gost.builder import Diagram
from schemify.renderers.drawio import DrawioRenderer
from schemify.renderers.svg import SVGRenderer, WatermarkInfo

logger = logging.getLogger(__name__)

_TASK_RE = re.compile(r"^(?P<prefix>.*?)(?P<num>\d+)$")


# ------------------------------------------------------------------ inputs
@dataclass
class TaskFile:
    number: int
    path: Path


@dataclass
class ScanResult:
    tasks: list[TaskFile] = field(default_factory=list)
    ignored: list[Path] = field(default_factory=list)       # .c без номера на конце
    duplicates: list[tuple[int, list[Path]]] = field(default_factory=list)


def scan_inputs(inputs_dir: Path) -> ScanResult:
    """Ищет *.c, у которых имя заканчивается числом: task1.c, lab3_task12.c ..."""
    result = ScanResult()
    by_number: dict[int, list[Path]] = {}
    if inputs_dir.is_dir():
        for path in sorted(inputs_dir.iterdir()):
            if not path.is_file() or path.suffix.lower() != ".c":
                continue
            m = _TASK_RE.match(path.stem)
            if not m:
                result.ignored.append(path)
                continue
            by_number.setdefault(int(m["num"]), []).append(path)
    for number in sorted(by_number):
        paths = by_number[number]
        if len(paths) > 1:
            result.duplicates.append((number, paths))
        result.tasks.append(TaskFile(number, paths[0]))
    return result


def read_source(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1251"):     # студенческие .c часто в cp1251
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


# --------------------------------------------------------------- generator
class FlowchartGenerator:
    def __init__(self, cfg: Config, output_dir: Path) -> None:
        self.cfg = cfg
        self.output_dir = output_dir
        self.has_api_key = bool(os.getenv("LLM_API_KEY", "").strip())
        self._frontend = None

    @property
    def frontend(self):
        if self._frontend is None:
            from schemify.gost.frontends import get_frontend
            self._frontend = get_frontend("tree-sitter")
        return self._frontend

    def generate(self, source_path: Path, base_name: str,
                 watermark: WatermarkInfo | None) -> tuple[list[Path], list[str]]:
        """Строит схемы для всех функций файла.

        Первая диаграмма (main, а если его нет - первая функция) сохраняется как
        `<base_name>.<fmt>`, остальные - как `<base_name>_<функция>.<fmt>`.
        Возвращает (созданные файлы, предупреждения).
        """
        code = read_source(source_path)
        diagrams = build_diagrams(code, Options(), frontend=self.frontend)
        if not diagrams:
            raise ValueError("в файле не найдено ни одной функции")

        files: list[Path] = []
        warnings: list[str] = []
        for index, diagram in enumerate(diagrams):
            warnings += [f"{diagram.name}: {w}" for w in diagram.warnings]
            if self.cfg.humanize:
                diagram = self._humanize(diagram)
            stem = base_name if index == 0 else f"{base_name}_{diagram.name}"
            files.append(self._save(diagram, stem, source_path.name, watermark))
        return files, warnings

    # -------------------------------------------------------------- steps
    def _humanize(self, diagram: Diagram) -> Diagram:
        from schemify.humanizer.humanizer import humanize_diagram
        try:
            diagram, _ = humanize_diagram(
                diagram, use_ai=self.has_api_key,
                on_ai_delegated=lambda: print("    ИИ обрабатывает сложные узлы..."))
        except Exception as error:                  # хуманайзер не должен ронять генерацию
            logger.warning("Хуманайзер пропущен: %s", error)
        return diagram

    def _save(self, diagram: Diagram, stem: str, source_name: str,
              watermark: WatermarkInfo | None) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        fmt = self.cfg.output_format
        target = self.output_dir / f"{stem}.{fmt}"
        if fmt == "drawio":
            return DrawioRenderer(self.output_dir).render(
                diagram, source_name, watermark, output_path=target)
        renderer = SVGRenderer(output_dir=self.output_dir)
        if fmt == "svg":
            return renderer.render_svg(diagram, source_name, watermark, output_path=target)
        with tempfile.TemporaryDirectory(prefix="schemify_") as tmp:
            svg_path = renderer.render_svg(diagram, source_name, watermark,
                                           output_path=Path(tmp) / f"{stem}.svg")
            return renderer.render_png(svg_path, target)
