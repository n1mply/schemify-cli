from __future__ import annotations

from dataclasses import asdict

from schemify.gost import Options, build_diagrams
from schemify.gost.builder import Diagram
from schemify.gost.layout import Edge, Label, Shape
from schemify.renderers.svg import WatermarkInfo


def diagram_from_source(source: str) -> Diagram:
    diagrams = build_diagrams(source, Options())
    if not diagrams:
        raise ValueError("Не найдены функции C-кода для построения блок-схемы.")
    return next((item for item in diagrams if item.name == "main"), diagrams[0])


def serialize_diagram(diagram: Diagram, watermark: WatermarkInfo | None = None) -> dict:
    return {
        "name": diagram.name,
        "nodes": [
            {"type": shape.kind, "text": "\n".join(shape.lines),
             "x": shape.x, "y": shape.y, "w": shape.w, "h": shape.h,
             "lines": list(shape.lines)}
            for shape in diagram.shapes
        ],
        "edges": [{"pts": edge.pts, "arrow": edge.arrow} for edge in diagram.edges],
        "labels": [asdict(label) for label in diagram.labels],
        "width": diagram.width,
        "height": diagram.height,
        "warnings": list(diagram.warnings),
        "watermark": asdict(watermark) if watermark else None,
    }


def deserialize_diagram(data: dict) -> tuple[Diagram, WatermarkInfo | None]:
    shapes = [Shape(
        item["type"], float(item["x"]), float(item["y"]), float(item["w"]),
        float(item["h"]), list(item.get("lines") or item["text"].splitlines()),
    ) for item in data["nodes"]]
    edges = [Edge([tuple(map(float, point)) for point in item["pts"]],
                  bool(item.get("arrow", False))) for item in data["edges"]]
    labels = [Label(float(item["x"]), float(item["y"]), item["text"],
                    item.get("anchor", "start")) for item in data.get("labels", [])]
    diagram = Diagram(data.get("name", "main"), shapes, edges, labels,
                      float(data["width"]), float(data["height"]),
                      list(data.get("warnings", [])))
    watermark_data = data.get("watermark")
    return diagram, WatermarkInfo(**watermark_data) if watermark_data else None
