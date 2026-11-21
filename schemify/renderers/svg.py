from __future__ import annotations

import secrets
import shutil
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from schemify.gost.builder import Diagram
from schemify.gost.options import Options
from schemify.gost.svg import render_svg


@dataclass(slots=True)
class WatermarkInfo:
    subject: str
    full_name: str
    group: str
    variant: str
    lab_num: str
    task_num: str


class SVGRenderer:
    """Save ГОСТ engine diagrams to SVG and rasterize them for Telegram."""

    def __init__(self, project_root: Path | None = None, output_dir: Path | None = None,
                 scale: float = 1.0) -> None:
        if scale <= 0:
            raise ValueError("Diagram scale must be greater than zero.")
        self.scale = scale
        root = project_root.resolve() if project_root else Path.cwd().resolve()
        self.output_dir = output_dir or root / "output"

    def to_svg(self, diagram: Diagram, *, title: str = "Блок-схема алгоритма",
               watermark: WatermarkInfo | None = None) -> str:
        options = Options()
        svg = render_svg(diagram, options)
        if watermark is not None:
            svg = self._add_watermark(svg, watermark)
        if self.scale != 1.0:
            root = ET.fromstring(svg)
            root.set("width", f"{float(root.get('width', diagram.width)) * self.scale:g}")
            root.set("height", f"{float(root.get('height', diagram.height)) * self.scale:g}")
            svg = ET.tostring(root, encoding="unicode")
        return svg

    @staticmethod
    def _add_watermark(svg: str, watermark: WatermarkInfo) -> str:
        root = ET.fromstring(svg)
        ns = "http://www.w3.org/2000/svg"
        ET.register_namespace("", ns)
        width = float(root.get("width", "0"))
        height = float(root.get("height", "0"))
        lines = [watermark.subject, watermark.full_name, watermark.group,
                 f"Вариант {watermark.variant}", f"ЛР №{watermark.lab_num}",
                 f"Задание {watermark.task_num}"]
        box_width = max(150.0, max(map(len, lines), default=0) * 8.5 + 24.0)
        box_height = len(lines) * 20.0 + 20.0
        offset = box_width + 105.0
        root.set("width", f"{width + offset:g}")
        root.set("viewBox", f"0 0 {width + offset:g} {max(height, box_height + 35):g}")
        children = list(root)
        background = children[0] if children and children[0].tag.endswith("rect") else None
        stamp = ET.Element(f"{{{ns}}}g", {"id": "student-watermark"})
        ET.SubElement(stamp, f"{{{ns}}}rect", {
            "x": "20", "y": "20", "width": f"{box_width:g}",
            "height": f"{box_height:g}", "fill": "#d5e8d4",
            "stroke": "#82b366", "stroke-width": "1.5",
        })
        for i, line in enumerate(lines):
            text = ET.SubElement(stamp, f"{{{ns}}}text", {
                "x": "32", "y": f"{42 + i * 20}",
                "font-family": "Times New Roman, Times, serif",
                "font-size": "16", "fill": "#000000",
            })
            text.text = line
        if background is not None:
            root.remove(background)
            background.set("width", f"{width + offset:g}")
            background.set("height", f"{max(height, box_height + 35):g}")
            root.insert(0, background)
        root.insert(1 if background is not None else 0, stamp)
        content = ET.Element(f"{{{ns}}}g", {"transform": f"translate({offset:g},0)"})
        for child in list(root):
            if child is not background and child is not stamp:
                root.remove(child)
                content.append(child)
        root.append(content)
        return ET.tostring(root, encoding="unicode", xml_declaration=True)

    def render(self, diagram: Diagram, source_filename: str,
               watermark: WatermarkInfo | None = None) -> tuple[Path, Path]:
        svg_path = self.render_svg(diagram, source_filename, watermark=watermark)
        return svg_path, self.render_png(svg_path)

    def render_svg(self, diagram: Diagram, source_filename: str,
                   watermark: WatermarkInfo | None = None,
                   output_path: Path | None = None) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if output_path is None:
            stem = Path(source_filename).stem or "flowchart"
            output_path = self.output_dir / f"{stem}_{secrets.token_hex(4)}.svg"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        svg = self.to_svg(diagram, title=f"Блок-схема: {Path(source_filename).name}",
                          watermark=watermark)
        output_path.write_text(svg, encoding="utf-8")
        return output_path

    def render_png(self, svg_path: Path, output_path: Path | None = None,
                   *, scale: float = 2.0) -> Path:
        svg_path = Path(svg_path)
        if not svg_path.is_file():
            raise FileNotFoundError(svg_path)
        output_path = Path(output_path) if output_path else svg_path.with_suffix(".png")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        errors: list[str] = []
        try:
            import resvg_py
            output_path.write_bytes(resvg_py.svg_to_bytes(svg_path=str(svg_path), zoom=scale))
            if output_path.stat().st_size:
                return output_path
            errors.append("resvg_py returned an empty image")
        except Exception as error:
            errors.append(f"resvg_py: {error}")
        try:
            import cairosvg
            cairosvg.svg2png(url=str(svg_path), write_to=str(output_path), scale=scale)
            if output_path.is_file() and output_path.stat().st_size:
                return output_path
            errors.append("CairoSVG returned an empty image")
        except Exception as error:
            errors.append(f"CairoSVG: {error}")
        executable = shutil.which("resvg")
        if executable:
            result = subprocess.run([executable, str(svg_path), str(output_path)],
                                     capture_output=True, text=True, check=False)
            if result.returncode == 0 and output_path.is_file() and output_path.stat().st_size:
                return output_path
            errors.append(result.stderr.strip() or "resvg CLI failed")
        rsvg = shutil.which("rsvg-convert")
        if rsvg:
            result = subprocess.run([rsvg, "-z", str(scale), "-b", "white", "-o", str(output_path),
                                     str(svg_path)], capture_output=True, text=True, check=False)
            if result.returncode == 0 and output_path.is_file() and output_path.stat().st_size:
                return output_path
            errors.append(result.stderr.strip() or "rsvg-convert failed")
        raise RuntimeError("Could not convert SVG to PNG: " + "; ".join(errors))
