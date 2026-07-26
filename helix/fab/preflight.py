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
    out.append(_islands_stub())
    out.append(_layers(plan))
    return out


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
    thin = [e for e in plan.elements
            if e.stroke_width and 0 < e.stroke_width < 0.15]
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


def _islands_stub() -> Finding:
    return Finding("warn", "Island check not yet run",
                   "Closed cut loops can drop out of the piece.",
                   "Run fab.islands.check() once Phase 4 is built, or visually "
                   "inspect for fully enclosed cut shapes.")


def _layers(plan) -> Finding:
    layers = {e.layer for e in plan.elements}
    if "CUT" not in layers:
        return Finding("warn", "Nothing on the CUT layer",
                       "This will engrave but never cut free.",
                       "Add a border or outline on the CUT layer if you want a "
                       "cut-out piece.")
    return Finding("pass", "Layers look right", f"Found: {', '.join(sorted(layers))}.")
