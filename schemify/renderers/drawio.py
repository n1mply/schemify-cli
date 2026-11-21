from __future__ import annotations

import html
import re
import secrets
import xml.etree.ElementTree as ET
from pathlib import Path

from schemify.gost.builder import Diagram
from schemify.renderers.svg import WatermarkInfo


def _drawio_value(text: str) -> str:
    """Убирает HTML-разметку из текста SVG и возвращает значение с переносами draw.io."""
    # Разэкранируем несколько раз: <br> мог прийти как &lt;br&gt; или &amp;lt;br&amp;gt;
    for _ in range(3):
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped

    # Любые варианты <br>, <br/>, <br /> и закрывающие блочные теги -> перенос строки
    text = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", text)
    text = re.sub(r"(?i)</\s*(?:p|div|li)\s*>", "\n", text)
    # Остальные теги удаляем
    text = re.sub(r"<[^>]*>", "", text)

    # Пустые строки по краям не нужны
    lines = [line.strip() for line in text.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    while lines and not lines[0]:
        lines.pop(0)

    # Текст экранируем (чтобы <, >, & из кода C отображались как есть),
    # а переносы ставим настоящим <br>. Экранирование атрибута сделает ET.
    return "<br>".join(html.escape(line, quote=False) for line in lines)


class DrawioRenderer:
    """Export an already laid out ГОСТ diagram without running another layout engine."""

    _STYLES = {
        "terminator": "ellipse;whiteSpace=wrap;html=1;",
        "process": "rounded=0;whiteSpace=wrap;html=1;",
        "predefined": "shape=process;whiteSpace=wrap;html=1;",
        "io": "shape=parallelogram;perimeter=parallelogramPerimeter;whiteSpace=wrap;html=1;",
        "decision": "rhombus;whiteSpace=wrap;html=1;",
        "hexagon": "hexagon;whiteSpace=wrap;html=1;",
    }

    def __init__(self, output_dir: Path | None = None, scale: float = 1.0) -> None:
        if scale <= 0:
            raise ValueError("Diagram scale must be greater than zero.")
        self.output_dir = output_dir or (Path.cwd() / "output")
        self.scale = scale

    def render(self, diagram: Diagram, source_filename: str = "flowchart.c",
               watermark: WatermarkInfo | None = None,
               output_path: Path | None = None) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(source_filename).stem or "flowchart"
        path = Path(output_path) if output_path else self.output_dir / f"{stem}_{secrets.token_hex(4)}.drawio"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_xml(diagram, source_filename, watermark), encoding="utf-8")
        return path

    def to_xml(self, diagram: Diagram, source_filename: str = "flowchart.c",
               watermark: WatermarkInfo | None = None) -> str:
        offset = 0.0
        stamp_width = stamp_height = 0.0
        if watermark:
            lines = [watermark.subject, watermark.full_name, watermark.group,
                     f"Вариант {watermark.variant}", f"ЛР №{watermark.lab_num}",
                     f"Задание {watermark.task_num}"]
            stamp_width = max(150.0, max(map(len, lines), default=0) * 8.5 + 24.0)
            stamp_height = len(lines) * 20.0 + 20.0
            offset = stamp_width + 105.0
        root = ET.Element("mxfile", {"host": "app.diagrams.net", "type": "device"})
        page = ET.SubElement(root, "diagram", {
            "id": secrets.token_hex(6), "name": Path(source_filename).stem or "Page-1",
        })
        model = ET.SubElement(page, "mxGraphModel", {
            "grid": "1", "gridSize": "10", "page": "1", "pageScale": "1",
            "pageWidth": f"{max(850, (diagram.width + offset) * self.scale):g}",
            "pageHeight": f"{max(1100, max(diagram.height, stamp_height + 40) * self.scale):g}",
        })
        cells = ET.SubElement(model, "root")
        ET.SubElement(cells, "mxCell", {"id": "0"})
        ET.SubElement(cells, "mxCell", {"id": "1", "parent": "0"})

        if watermark:
            lines = [watermark.subject, watermark.full_name, watermark.group,
                     f"Вариант {watermark.variant}", f"ЛР №{watermark.lab_num}",
                     f"Задание {watermark.task_num}"]
            self._vertex(cells, "student_stamp", _drawio_value("\n".join(lines)),
                "rounded=0;whiteSpace=wrap;html=1;align=left;verticalAlign=top;"
                "spacing=8;fillColor=#d5e8d4;strokeColor=#82b366;",
                20 * self.scale, 20 * self.scale,
                stamp_width * self.scale, stamp_height * self.scale)

        for index, shape in enumerate(diagram.shapes):
            value = _drawio_value("\n".join(shape.lines))
            style = self._STYLES.get(shape.kind, self._STYLES["process"])
            if shape.kind == "predefined":
                style += "backgroundOutline=1;"
            self._vertex(cells, f"node_{index}", value, style,
                         (shape.x - shape.w / 2 + offset) * self.scale,
                         (shape.y - shape.h / 2) * self.scale,
                         shape.w * self.scale, shape.h * self.scale)

        for index, edge in enumerate(diagram.edges):
            if len(edge.pts) < 2:
                continue
            cell = ET.SubElement(cells, "mxCell", {
                "id": f"edge_{index}", "value": "",
                "style": "edgeStyle=none;html=1;rounded=0;"
                         f"endArrow={'block' if edge.arrow else 'none'};endFill=1;",
                "edge": "1", "parent": "1",
            })
            geometry = ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})
            first, last = edge.pts[0], edge.pts[-1]
            ET.SubElement(geometry, "mxPoint", {
                "x": f"{(first[0] + offset) * self.scale:g}",
                "y": f"{first[1] * self.scale:g}", "as": "sourcePoint",
            })
            ET.SubElement(geometry, "mxPoint", {
                "x": f"{(last[0] + offset) * self.scale:g}",
                "y": f"{last[1] * self.scale:g}", "as": "targetPoint",
            })
            if len(edge.pts) > 2:
                points = ET.SubElement(geometry, "Array", {"as": "points"})
                for x, y in edge.pts[1:-1]:
                    ET.SubElement(points, "mxPoint", {
                        "x": f"{(x + offset) * self.scale:g}",
                        "y": f"{y * self.scale:g}",
                    })

        for index, label in enumerate(diagram.labels):
            self._vertex(cells, f"label_{index}", _drawio_value(label.text),
                         "text;html=1;strokeColor=none;fillColor=none;",
                         (label.x + offset) * self.scale, label.y * self.scale,
                         80 * self.scale, 22 * self.scale)

        ET.indent(root, space="  ")
        return ET.tostring(root, encoding="unicode", xml_declaration=True)

    def _vertex(self, cells: ET.Element, cell_id: str, value: str, style: str,
                x: float, y: float, width: float, height: float) -> None:
        cell = ET.SubElement(cells, "mxCell", {
            "id": cell_id, "value": value,
            "style": style + f"fontSize={16 * self.scale:g};strokeWidth={1.6 * self.scale:g};",
            "vertex": "1", "parent": "1",
        })
        ET.SubElement(cell, "mxGeometry", {
            "x": f"{x:g}", "y": f"{y:g}", "width": f"{width:g}",
            "height": f"{height:g}", "as": "geometry",
        })
