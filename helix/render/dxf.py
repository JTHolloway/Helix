"""RenderPlan -> DXF, with no third-party library.

Single responsibility: serialise finished geometry as DXF. No trigonometry.

WHY WRITE IT BY HAND: DXF is the format every CAD and CAM program reads, so
it must work on a machine where nothing has been installed. R12 (AC1009) is
the most widely readable revision ever published -- Fusion 360, AutoCAD,
FreeCAD, SolidWorks, Rhino, LightBurn, Illustrator and Inkscape all open it
without argument. It is also simple enough that writing it directly is less
trouble than carrying a dependency.

Curves are flattened to polylines at 0.05 mm, finer than any laser or router
resolves. Text is emitted as TEXT entities on their own layer by default,
because a CAD user usually wants editable annotation; pass
`text_as_geometry=True` once outline baking exists (see fab/textpath.py) for
a file that cuts identically everywhere.

Layers follow the plan: CUT, SCORE, ENGRAVE, ENGRAVE_DEEP, GUIDE.
"""
from __future__ import annotations

from pathlib import Path

from ..layout.plan import RenderPlan
from .pathflatten import flatten

# AutoCAD Color Index: 1 red, 3 green, 5 blue, 7 black/white, 8 grey
LAYER_COLOUR = {"CUT": 1, "SCORE": 5, "ENGRAVE": 7, "ENGRAVE_DEEP": 3,
                "GUIDE": 8, "TEXT": 7}
FLATTEN_MM = 0.05


def _g(code: int, value) -> str:
    return f"{code}\n{value}\n"


def write(plan: RenderPlan, path: str | Path, *,
          flatten_tolerance_mm: float = FLATTEN_MM,
          text_as_geometry: bool = False,
          production: bool = False) -> str:
    """Write `plan` as DXF R12, in millimetres, y upward."""
    path = Path(path)
    H = plan.canvas.height_mm
    out: list[str] = []

    # ---- header: units are millimetres, extents cover the piece ----------
    out.append(_g(0, "SECTION") + _g(2, "HEADER"))
    out.append(_g(9, "$ACADVER") + _g(1, "AC1009"))
    out.append(_g(9, "$INSUNITS") + _g(70, 4))          # 4 = millimetres
    out.append(_g(9, "$EXTMIN") + _g(10, 0.0) + _g(20, 0.0) + _g(30, 0.0))
    out.append(_g(9, "$EXTMAX") + _g(10, plan.canvas.width_mm)
               + _g(20, H) + _g(30, 0.0))
    out.append(_g(0, "ENDSEC"))

    # ---- tables: one layer per operation ---------------------------------
    out.append(_g(0, "SECTION") + _g(2, "TABLES"))
    out.append(_g(0, "TABLE") + _g(2, "LAYER") + _g(70, len(LAYER_COLOUR)))
    for name, colour in LAYER_COLOUR.items():
        out.append(_g(0, "LAYER") + _g(2, name) + _g(70, 0)
                   + _g(62, colour) + _g(6, "CONTINUOUS"))
    out.append(_g(0, "ENDTAB") + _g(0, "ENDSEC"))

    # ---- entities ---------------------------------------------------------
    out.append(_g(0, "SECTION") + _g(2, "ENTITIES"))
    n = 0
    for el in plan.sorted_elements():
        if el.layer == "PRINT_ONLY" or (production and el.layer == "GUIDE"):
            continue
        layer = el.layer if el.layer in LAYER_COLOUR else "ENGRAVE"

        if el.kind == "text":
            if text_as_geometry:
                continue                        # baked elsewhere, once built
            out.append(_text(el, H))
            n += 1
            continue

        if el.kind == "circle":
            out.append(_g(0, "CIRCLE") + _g(8, layer)
                       + _g(10, _f(el.x)) + _g(20, _f(H - el.y))
                       + _g(30, 0.0) + _g(40, _f(el.r)))
            n += 1
            continue

        for pts, closed in flatten(el, flatten_tolerance_mm):
            if len(pts) < 2:
                continue
            out.append(_polyline(pts, closed, layer, H))
            n += 1

    out.append(_g(0, "ENDSEC") + _g(0, "EOF"))
    path.write_text("".join(out))
    return str(path)


def _polyline(pts, closed: bool, layer: str, H: float) -> str:
    """R12 POLYLINE: a header entity, a VERTEX per point, then SEQEND.
    Verbose, but readable by everything ever made."""
    s = (_g(0, "POLYLINE") + _g(8, layer) + _g(66, 1)
         + _g(10, 0.0) + _g(20, 0.0) + _g(30, 0.0)
         + _g(70, 1 if closed else 0))
    for x, y in pts:
        s += (_g(0, "VERTEX") + _g(8, layer)
              + _g(10, _f(x)) + _g(20, _f(H - y)) + _g(30, 0.0))
    return s + _g(0, "SEQEND") + _g(8, layer)


def _text(el, H: float) -> str:
    f = el.font
    size = (f.size_mm if f else 3.0) * 0.72          # cap height, not em
    align = {"start": 0, "middle": 1, "end": 2}.get(f.anchor if f else "middle", 1)
    s = (_g(0, "TEXT") + _g(8, "TEXT")
         + _g(10, _f(el.x)) + _g(20, _f(H - el.y)) + _g(30, 0.0)
         + _g(40, _f(size)) + _g(1, (el.text or "").replace("\n", " "))
         + _g(50, _f(-(el.rotate or 0.0))))
    if align:
        s += (_g(72, align) + _g(11, _f(el.x)) + _g(21, _f(H - el.y))
              + _g(31, 0.0))
    return s


def _f(v) -> str:
    return f"{float(v or 0):.4f}"
