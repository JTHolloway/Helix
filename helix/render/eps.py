"""RenderPlan -> Encapsulated PostScript.

Single responsibility: serialise finished geometry as EPS. No trigonometry.

Some older CAD, sign-cutting and laser software still prefers EPS over SVG,
and Illustrator opens it with vectors intact. Like the PDF writer, this uses
nothing but the standard library.
"""
from __future__ import annotations

from pathlib import Path

from ..layout.plan import RenderPlan
from .pathflatten import flatten

MM_TO_PT = 72.0 / 25.4


def write(plan: RenderPlan, path: str | Path, *, production: bool = False) -> str:
    path = Path(path)
    W = plan.canvas.width_mm * MM_TO_PT
    H = plan.canvas.height_mm * MM_TO_PT
    o: list[str] = [
        "%!PS-Adobe-3.0 EPSF-3.0",
        f"%%BoundingBox: 0 0 {W:.0f} {H:.0f}",
        f"%%HiResBoundingBox: 0 0 {W:.4f} {H:.4f}",
        f"%%Creator: Helix ({plan.meta.engine})",
        "%%LanguageLevel: 2", "%%EndComments",
        "/mm { 2.834645669 mul } def",
        "1 setlinecap 1 setlinejoin",
    ]

    def X(v):
        return v * MM_TO_PT

    def Y(v):
        return (plan.canvas.height_mm - v) * MM_TO_PT

    for el in plan.sorted_elements():
        if production and el.layer == "PRINT_ONLY":
            continue
        if el.kind == "text":
            f = el.font
            size = (f.size_mm if f else 3.0) * MM_TO_PT
            fam = "Helvetica"
            low = (f.family if f else "").lower()
            if "serif" in low or "georgia" in low or "garamond" in low:
                fam = "Times-Roman"
            elif "mono" in low or "courier" in low:
                fam = "Courier"
            o.append("gsave")
            o.append(f"{_c(el.fill)} setrgbcolor")
            o.append(f"/{fam} findfont {size:.3f} scalefont setfont")
            o.append(f"{X(el.x):.3f} {Y(el.y):.3f} translate")
            if el.rotate:
                o.append(f"{-el.rotate:.3f} rotate")
            txt = (el.text or "").replace("\\", r"\\").replace("(", r"\(") \
                                 .replace(")", r"\)")
            anchor = f.anchor if f else "middle"
            if anchor == "middle":
                o.append(f"({txt}) dup stringwidth pop 2 div neg "
                         f"{-size * 0.34:.3f} moveto show")
            elif anchor == "end":
                o.append(f"({txt}) dup stringwidth pop neg "
                         f"{-size * 0.34:.3f} moveto show")
            else:
                o.append(f"0 {-size * 0.34:.3f} moveto ({txt}) show")
            o.append("grestore")
            continue

        o.append("newpath")
        if el.kind == "circle":
            o.append(f"{X(el.x):.3f} {Y(el.y):.3f} {el.r * MM_TO_PT:.3f} "
                     f"0 360 arc closepath")
        else:
            for pts, closed in flatten(el, 0.08):
                if len(pts) < 2:
                    continue
                o.append(f"{X(pts[0][0]):.3f} {Y(pts[0][1]):.3f} moveto")
                for x, y in pts[1:]:
                    o.append(f"{X(x):.3f} {Y(y):.3f} lineto")
                if closed:
                    o.append("closepath")
        if el.fill and el.fill != "none":
            o.append(f"{_c(el.fill)} setrgbcolor fill")
        if el.stroke and el.stroke != "none":
            o.append(f"{_c(el.stroke)} setrgbcolor "
                     f"{max(0.05, el.stroke_width or 0.3) * MM_TO_PT:.3f} "
                     f"setlinewidth stroke")
    o.append("showpage")
    o.append("%%EOF")
    path.write_text("\n".join(o))
    return str(path)


def _c(colour: str | None) -> str:
    if not colour or colour == "none":
        return "0 0 0"
    c = colour.lstrip("#")
    if len(c) == 3:
        c = "".join(x * 2 for x in c)
    try:
        r, g, b = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return "0 0 0"
    return f"{r:.3f} {g:.3f} {b:.3f}"
