"""RenderPlan -> SVG.

Single responsibility: serialise finished geometry. Contains no trigonometry.

The critical detail: width/height carry REAL UNITS (mm) and the viewBox
matches, so Illustrator, Inkscape and LightBurn all open the file at exactly
the intended physical size. Getting this wrong is the most common reason a
laser job comes out the wrong scale.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from ..layout.plan import Element, RenderPlan

LAYER_COLOURS = {"CUT": "#FF0000", "SCORE": "#0000FF", "ENGRAVE": "#000000",
                 "ENGRAVE_DEEP": "#00A000", "GUIDE": "#CCCCCC",
                 "PRINT_ONLY": "#000000"}
LAYER_ORDER = ["PRINT_ONLY", "GUIDE", "ENGRAVE", "ENGRAVE_DEEP", "SCORE", "CUT"]


def render(plan: RenderPlan, *, production: bool = False,
           interactive: bool = False) -> str:
    c = plan.canvas
    out: list[str] = []
    out.append('<?xml version="1.0" encoding="UTF-8"?>')
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        f'width="{_n(c.width_mm)}mm" height="{_n(c.height_mm)}mm" '
        f'viewBox="0 0 {_n(c.width_mm)} {_n(c.height_mm)}">')
    out.append(f'<!-- helix | engine={plan.meta.engine} style={plan.meta.style} '
               f'people={plan.meta.people} hash={plan.hash()} -->')
    if not production:
        out.append(f'<rect x="0" y="0" width="{_n(c.width_mm)}" '
                   f'height="{_n(c.height_mm)}" fill="{c.background}"/>')

    groups: dict[str, list[Element]] = {}
    for el in plan.sorted_elements():
        if production and el.layer == "PRINT_ONLY":
            continue
        groups.setdefault(el.layer, []).append(el)

    for layer in LAYER_ORDER:
        els = groups.get(layer)
        if not els:
            continue
        out.append(f'<g id="{layer}" inkscape:groupmode="layer" '
                   f'inkscape:label="{layer}">')
        for el in els:
            out.append(_el(el, layer, production, interactive))
        out.append("</g>")
    out.append("</svg>")
    return "\n".join(out)


def _el(el: Element, layer: str, production: bool, interactive: bool) -> str:
    stroke = el.stroke
    if production and layer in ("CUT", "SCORE"):
        stroke = LAYER_COLOURS[layer]
    attrs: list[str] = []
    if el.person_id and interactive:
        attrs.append(f'data-p="{el.person_id}"')
        attrs.append(f'data-role="{el.role}"')
    if el.line_id and interactive:
        attrs.append(f'data-line="{el.line_id}"')
    a = (" " + " ".join(attrs)) if attrs else ""

    if el.kind == "text":
        f = el.font
        size = f.size_mm if f else 3.0
        fam = escape(f.family if f else "sans-serif", {'"': "&quot;"})
        anchor = f.anchor if f else "middle"
        tr = (f' transform="rotate({_n(el.rotate)},{_n(el.x)},{_n(el.y)})"'
              if el.rotate else "")
        ls = (f' letter-spacing="{_n(f.letter_spacing)}"'
              if f and f.letter_spacing else "")
        wt = f' font-weight="{f.weight}"' if f and f.weight != 400 else ""
        return (f'<text x="{_n(el.x)}" y="{_n(el.y)}" font-family="{fam}" '
                f'font-size="{_n(size)}" fill="{el.fill or "#000"}" '
                f'text-anchor="{anchor}" dominant-baseline="central"'
                f'{wt}{ls}{tr}{a}>{escape(el.text or "")}</text>')

    if el.kind == "circle":
        return (f'<circle cx="{_n(el.x)}" cy="{_n(el.y)}" r="{_n(el.r)}" '
                f'{_paint(el, stroke)}{a}/>')

    if el.kind == "rect":
        rx = f' rx="{_n(el.rx)}"' if el.rx else ""
        return (f'<rect x="{_n(el.x)}" y="{_n(el.y)}" width="{_n(el.w)}" '
                f'height="{_n(el.h)}"{rx} {_paint(el, stroke)}{a}/>')

    return f'<path d="{el.d}" {_paint(el, stroke)}{a}/>'


def _paint(el: Element, stroke: str | None) -> str:
    bits = [f'fill="{el.fill or "none"}"']
    if stroke and stroke != "none":
        bits.append(f'stroke="{stroke}"')
        bits.append(f'stroke-width="{_n(el.stroke_width or 0.3)}"')
        bits.append('stroke-linecap="round" stroke-linejoin="round"')
    if el.dash:
        bits.append(f'stroke-dasharray="{el.dash}"')
    if el.opacity < 1.0:
        bits.append(f'opacity="{_n(el.opacity)}"')
    return " ".join(bits)


def _n(v) -> str:
    if v is None:
        return "0"
    s = f"{float(v):.4f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"
