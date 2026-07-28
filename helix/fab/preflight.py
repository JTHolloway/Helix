"""Pre-flight checks. Runs before every production export.

Philosophy: the machine is unforgiving and material costs money, so the
program should catch what a person would only discover after 40 minutes of
cutting. Every finding says what is wrong, why it matters and what to do.
"""
from __future__ import annotations

from dataclasses import dataclass

from .materials import get as material


@dataclass
class Finding:
    level: str        # pass | warn | fail
    title: str
    detail: str
    fix: str = ""


def preflight(plan, style, *, bed_w_mm: float = 600, bed_h_mm: float = 400) -> list[Finding]:
    out: list[Finding] = []
    mat = material(style.get("production.material", "birch_ply_3mm"))
    c = plan.canvas

    out.append(_size(c, bed_w_mm, bed_h_mm))
    out.append(_text(plan, mat))
    out.append(_hairlines(plan, mat))
    out.append(_labels(plan))
    out.append(_islands(plan))
    out.append(_outside(plan))
    out.append(_layers(plan))
    return out


def _outside(plan) -> Finding:
    """Engraving on the wrong side of the cut line.

    Nothing warns you about this at the machine: the job runs, the piece comes
    away, and the part of the chart that was outside the line is still in the
    offcut. Found on the first production render -- the key was in a corner
    the cut did not reach.
    """
    from .islands import _bbox, _loops, _point_in
    cuts = _loops(plan, "CUT", 0.2)
    if not cuts:
        return Finding("pass", "No cut line to fall outside", "Nothing to check.")
    boxes = [_bbox(p) for p, _ in cuts]
    lost = 0
    for el in plan.elements:
        if el.layer in ("CUT", "PRINT_ONLY"):
            continue
        pt = ((el.x, el.y) if el.x is not None else _first(el))
        if pt is None:
            continue
        if not any(b[0] <= pt[0] <= b[2] and b[1] <= pt[1] <= b[3]
                   and _point_in(pt, cuts[i][0]) for i, b in enumerate(boxes)):
            lost += 1
    if not lost:
        return Finding("pass", "Everything is inside the cut",
                       f"{len(cuts)} cut loop(s), and all the engraving is "
                       f"within them.")
    return Finding("fail", "Engraving outside the cut line",
                   f"{lost} shapes lie outside every cut loop and would be "
                   f"left in the offcut.",
                   "Move them inside, or enlarge the cut outline to enclose "
                   "the whole canvas.")


def _first(el):
    import re
    if not el.d:
        return None
    m = re.search(r'(-?\d+\.?\d*)[ ,](-?\d+\.?\d*)', el.d)
    return (float(m.group(1)), float(m.group(2))) if m else None


def _size(c, bw, bh) -> Finding:
    if c.width_mm <= bw and c.height_mm <= bh:
        return Finding("pass", "Fits the bed",
                       f"{c.width_mm:.0f} x {c.height_mm:.0f} mm fits "
                       f"{bw:.0f} x {bh:.0f} mm.")
    return Finding("warn", "Larger than the bed",
                   f"{c.width_mm:.0f} x {c.height_mm:.0f} mm exceeds "
                   f"{bw:.0f} x {bh:.0f} mm.",
                   "Tile it into panels with registration tabs, or reduce the "
                   "diameter until it fits.")


def _text(plan, mat) -> Finding:
    sizes = [e.font.size_mm for e in plan.elements
             if e.kind == "text" and e.font]
    if not sizes:
        return Finding("pass", "No engraved text", "Nothing to check.")
    smallest = min(sizes)
    if smallest >= mat.min_text_mm:
        return Finding("pass", "Text is large enough",
                       f"Smallest is {smallest:.1f} mm; {mat.name} holds "
                       f"{mat.min_text_mm:.1f} mm.")
    n = sum(1 for s in sizes if s < mat.min_text_mm)
    return Finding("fail", "Text too small to read",
                   f"{n} labels are below {mat.min_text_mm:.1f} mm on {mat.name}.",
                   "Increase the text size, shorten the labels, show fewer "
                   "generations, or make the piece larger.")


def _hairlines(plan, mat) -> Finding:
    # A CUT line's width is not a width. It is the hairline convention that
    # tells the machine "follow this", and warning about it sent every
    # operator looking for a problem that was the file working correctly.
    thin = [e for e in plan.elements
            if e.layer not in ("CUT", "SCORE", "PRINT_ONLY")
            and e.stroke_width and 0 < e.stroke_width < 0.15]
    if not thin:
        return Finding("pass", "No hairlines", "All lines are wide enough.")
    return Finding("warn", "Very fine lines",
                   f"{len(thin)} strokes are under 0.15 mm.",
                   "Fine on paper; on wood they may disappear. Raise the line "
                   "weight to at least 0.2 mm.")


def _labels(plan) -> Finding:
    hidden = plan.meta.extra.get("labels_hidden", 0)
    if not hidden:
        return Finding("pass", "Every name fits", "No labels were dropped.")
    return Finding("warn", "Some names were left off",
                   f"{hidden} labels could not be placed without overlapping.",
                   "Make the piece larger, reduce generations, or switch to a "
                   "numbered chart with a companion list.")


def _islands(plan) -> Finding:
    from .islands import check
    rep = check(plan)
    if rep.ok:
        return Finding("pass", "Nothing falls out", rep.summary())
    worst = rep.islands[0]
    return Finding(
        "fail", "Pieces would drop out of the sheet", rep.summary(),
        f"Bridge the largest at ({worst.centroid[0]:.0f}, "
        f"{worst.centroid[1]:.0f}) mm -- its nearest neighbour is "
        f"{worst.gap_mm:.1f} mm away -- or move that shape to the ENGRAVE "
        f"layer so it is marked rather than cut.")


def _layers(plan) -> Finding:
    layers = {e.layer for e in plan.elements}
    if "CUT" not in layers:
        return Finding("warn", "Nothing on the CUT layer",
                       "This will engrave but never cut free.",
                       "Add a border or outline on the CUT layer if you want a "
                       "cut-out piece.")
    return Finding("pass", "Layers look right", f"Found: {', '.join(sorted(layers))}.")
