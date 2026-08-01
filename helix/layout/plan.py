"""The Render Plan: the one intermediate format everything else speaks.

Single responsibility: describe finished geometry in millimetres.

  layout engines  ->  RenderPlan  ->  { screen, SVG, DXF, PDF }

Nothing downstream of this file may compute an angle, a radius or a curve.
If an exporter starts doing trigonometry, the architecture has been broken.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Literal, Optional

Layer = Literal["CUT", "SCORE", "ENGRAVE", "ENGRAVE_DEEP", "GUIDE", "PRINT_ONLY"]
Kind = Literal["path", "circle", "rect", "text", "textarc", "group"]


@dataclass
class FontSpec:
    family: str = "sans-serif"
    size_mm: float = 3.0
    weight: int = 400
    italic: bool = False
    letter_spacing: float = 0.0
    anchor: Literal["start", "middle", "end"] = "middle"
    baseline: Literal["auto", "middle", "hanging"] = "middle"


@dataclass
class Element:
    kind: Kind = "path"
    layer: Layer = "ENGRAVE"
    d: Optional[str] = None                # SVG path data, absolute, mm
    x: Optional[float] = None
    y: Optional[float] = None
    r: Optional[float] = None
    w: Optional[float] = None
    h: Optional[float] = None
    rx: Optional[float] = None
    stroke: Optional[str] = None
    stroke_width: Optional[float] = None
    dash: Optional[str] = None
    fill: Optional[str] = None
    opacity: float = 1.0
    text: Optional[str] = None
    font: Optional[FontSpec] = None
    rotate: float = 0.0                    # degrees, about (x, y)
    # provenance -- this is what makes hover, search and contingency work
    person_id: Optional[str] = None
    union_id: Optional[str] = None
    role: str = "ornament"                 # cell|connector|label|thread|station
                                           # |interchange|tick|bore|bridge|error
    line_id: Optional[str] = None          # which "route" (metro designs)
    z: int = 0


@dataclass
class Canvas:
    width_mm: float = 600.0
    height_mm: float = 600.0
    background: str = "#FFFFFF"
    shape: str = "rect"                    # rect | circle


@dataclass
class PlanMeta:
    engine: str = ""
    style: str = ""
    people: int = 0
    generations: int = 0
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    warnings: list[str] = field(default_factory=list)
    demotions: int = 0
    legend: list[dict] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class RenderPlan:
    canvas: Canvas = field(default_factory=Canvas)
    elements: list[Element] = field(default_factory=list)
    meta: PlanMeta = field(default_factory=PlanMeta)

    def add(self, el: Element) -> Element:
        self.elements.append(el)
        return el

    def sorted_elements(self) -> list[Element]:
        return sorted(self.elements, key=lambda e: e.z)

    def to_dict(self) -> dict:
        return {
            "canvas": asdict(self.canvas),
            "meta": asdict(self.meta),
            "elements": [
                {k: v for k, v in asdict(e).items() if v is not None and v != ""}
                for e in self.sorted_elements()
            ],
        }

    def to_json(self, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":") if indent is None else None,
                          indent=indent)

    def hash(self) -> str:
        return hashlib.sha256(self.to_json().encode()).hexdigest()[:12]
