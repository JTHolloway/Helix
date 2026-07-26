"""Shared geometry. Millimetres, absolute coordinates, y increases downward.

Single responsibility: turn maths into SVG path strings. No family logic.
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence

Pt = tuple[float, float]
TAU = math.tau


def polar(cx: float, cy: float, r: float, theta: float) -> Pt:
    """theta in radians, 0 = 3 o'clock, increasing clockwise on screen."""
    return (cx + r * math.cos(theta), cy + r * math.sin(theta))


def fmt(v: float) -> str:
    """4 dp is 0.1 micron: far below any laser's resolution, and it keeps
    files small. Strip trailing zeros so the output is readable."""
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def M(p: Pt) -> str:
    return f"M{fmt(p[0])},{fmt(p[1])}"


def L(p: Pt) -> str:
    return f"L{fmt(p[0])},{fmt(p[1])}"


def arc_to(p: Pt, r: float, large: bool, sweep: bool) -> str:
    return f"A{fmt(r)},{fmt(r)} 0 {int(large)},{int(sweep)} {fmt(p[0])},{fmt(p[1])}"


def arc_path(cx, cy, r, t0, t1, *, move=True) -> str:
    """Circular arc from angle t0 to t1 at radius r."""
    p0, p1 = polar(cx, cy, r, t0), polar(cx, cy, r, t1)
    delta = t1 - t0
    large = abs(delta) > math.pi
    sweep = delta > 0
    return (M(p0) if move else "") + arc_to(p1, r, large, sweep)


def short_arc(cx, cy, r, t0, t1) -> str:
    """The MINOR arc between two angles.

    `arc_path` draws from t0 to t1 in the direction implied by their
    difference. For a couple sitting either side of the start angle -- one at
    5 degrees, one at 355 -- that difference is 350 degrees, and the tie
    between them gets drawn the whole way round the circle. They are in fact
    ten degrees apart.

    This is the bug behind ties that appeared to sweep across the diameter.
    Always take the short way unless you specifically want the long one.
    """
    d = t1 - t0
    while d > math.pi:
        d -= TAU
    while d < -math.pi:
        d += TAU
    return arc_path(cx, cy, r, t0, t0 + d)


def annular_sector(cx, cy, r0, r1, t0, t1) -> str:
    """The classic 'blocky' cell: two arcs joined by two radial edges."""
    a = polar(cx, cy, r0, t0)
    b = polar(cx, cy, r1, t0)
    c = polar(cx, cy, r1, t1)
    d = polar(cx, cy, r0, t1)
    large = abs(t1 - t0) > math.pi
    return (M(a) + L(b)
            + arc_to(c, r1, large, t1 > t0)
            + L(d)
            + arc_to(a, r0, large, t1 < t0) + "Z")


def circle_path(cx, cy, r) -> str:
    """A full circle as two absolute half-arcs.

    Deliberately ABSOLUTE. The relative form is shorter and every browser
    reads it, but the flattener that feeds DXF, EPS and PDF works in
    absolute coordinates -- so a relative circle came out as garbage
    geometry hundreds of millimetres outside the sheet, and only in the CAD
    exports. Browsers were fine, which is what made it easy to miss.
    """
    return (f"M{fmt(cx - r)},{fmt(cy)}"
            f"A{fmt(r)},{fmt(r)} 0 1,0 {fmt(cx + r)},{fmt(cy)}"
            f"A{fmt(r)},{fmt(r)} 0 1,0 {fmt(cx - r)},{fmt(cy)}Z")


def rounded_rect(x, y, w, h, r) -> str:
    r = min(r, w / 2, h / 2)
    return (f"M{fmt(x + r)},{fmt(y)}H{fmt(x + w - r)}"
            f"A{fmt(r)},{fmt(r)} 0 0,1 {fmt(x + w)},{fmt(y + r)}"
            f"V{fmt(y + h - r)}A{fmt(r)},{fmt(r)} 0 0,1 {fmt(x + w - r)},{fmt(y + h)}"
            f"H{fmt(x + r)}A{fmt(r)},{fmt(r)} 0 0,1 {fmt(x)},{fmt(y + h - r)}"
            f"V{fmt(y + r)}A{fmt(r)},{fmt(r)} 0 0,1 {fmt(x + r)},{fmt(y)}Z")


# --------------------------------------------------------------- polylines --
def polyline(pts: Sequence[Pt]) -> str:
    if not pts:
        return ""
    return M(pts[0]) + "".join(L(p) for p in pts[1:])


def rounded_polyline(pts: Sequence[Pt], radius: float) -> str:
    """Round every interior corner. This single function is the difference
    between a diagram that looks technical and one that looks like a
    transit map."""
    pts = _dedupe(pts)
    if len(pts) < 3 or radius <= 0:
        return polyline(pts)
    out = [M(pts[0])]
    for i in range(1, len(pts) - 1):
        p0, p1, p2 = pts[i - 1], pts[i], pts[i + 1]
        v0 = _unit(p0, p1)
        v1 = _unit(p1, p2)
        if v0 is None or v1 is None:
            continue
        d0 = _dist(p0, p1) / 2
        d1 = _dist(p1, p2) / 2
        r = min(radius, d0, d1)
        a = (p1[0] - v0[0] * r, p1[1] - v0[1] * r)
        b = (p1[0] + v1[0] * r, p1[1] + v1[1] * r)
        cross = v0[0] * v1[1] - v0[1] * v1[0]
        out.append(L(a))
        if abs(cross) > 1e-9:
            out.append(arc_to(b, r, False, cross > 0))
        else:
            out.append(L(b))
    out.append(L(pts[-1]))
    return "".join(out)


def _dedupe(pts: Sequence[Pt]) -> list[Pt]:
    out: list[Pt] = []
    for p in pts:
        if not out or _dist(out[-1], p) > 1e-7:
            out.append(p)
    return out


def _dist(a: Pt, b: Pt) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _unit(a: Pt, b: Pt):
    d = _dist(a, b)
    if d < 1e-9:
        return None
    return ((b[0] - a[0]) / d, (b[1] - a[1]) / d)


# ------------------------------------------------------------- octilinear --
def octilinear(a: Pt, b: Pt, *, prefer: str = "diag_last") -> list[Pt]:
    """Route from a to b using only 0/45/90 degree segments -- the geometric
    rule that defines every transit map since Beck's 1933 Underground diagram.

    Two segments: one axis-aligned run and one 45-degree diagonal.
    prefer='diag_first' puts the diagonal at the start, 'diag_last' at the end.
    """
    dx, dy = b[0] - a[0], b[1] - a[1]
    adx, ady = abs(dx), abs(dy)
    if adx < 1e-9 or ady < 1e-9 or abs(adx - ady) < 1e-9:
        return [a, b]                                   # already octilinear
    sx = 1 if dx > 0 else -1
    sy = 1 if dy > 0 else -1
    diag = min(adx, ady)
    if prefer == "diag_first":
        knee = (a[0] + sx * diag, a[1] + sy * diag)
    else:
        knee = (b[0] - sx * diag, b[1] - sy * diag)
    return [a, knee, b]


def polar_octilinear(cx, cy, r0, t0, r1, t1, *, arc_first=True,
                     samples: int = 24) -> list[Pt]:
    """The radial equivalent: move along a constant-radius ARC, then along a
    RADIAL spoke (or the reverse). Produces the metro look in polar space,
    where 'straight lines' are arcs."""
    pts: list[Pt] = []
    if arc_first:
        for i in range(samples + 1):
            pts.append(polar(cx, cy, r0, t0 + (t1 - t0) * i / samples))
        pts.append(polar(cx, cy, r1, t1))
    else:
        pts.append(polar(cx, cy, r0, t0))
        for i in range(samples + 1):
            pts.append(polar(cx, cy, r1, t0 + (t1 - t0) * i / samples))
    return _dedupe(pts)


def elbow_polar(cx, cy, r0, t0, r1, t1, *, mid: float = 0.5,
                samples: int = 20) -> list[Pt]:
    """Radial out to an intermediate radius, arc across, radial out again.
    The classic 'organ pipe' connector of orthogonal radial charts."""
    rm = r0 + (r1 - r0) * mid
    pts = [polar(cx, cy, r0, t0), polar(cx, cy, rm, t0)]
    for i in range(1, samples + 1):
        pts.append(polar(cx, cy, rm, t0 + (t1 - t0) * i / samples))
    pts.append(polar(cx, cy, r1, t1))
    return _dedupe(pts)


def bezier_polar(cx, cy, r0, t0, r1, t1, tension: float = 0.55) -> str:
    """Smooth 'root/branch' connector: control points pushed along the radius
    so curves leave and arrive perpendicular to their rings."""
    p0 = polar(cx, cy, r0, t0)
    p1 = polar(cx, cy, r1, t1)
    rm = r0 + (r1 - r0) * tension
    c0 = polar(cx, cy, rm, t0)
    c1 = polar(cx, cy, rm, t1)
    return (M(p0) + f"C{fmt(c0[0])},{fmt(c0[1])} {fmt(c1[0])},{fmt(c1[1])} "
            f"{fmt(p1[0])},{fmt(p1[1])}")


def bezier_xy(p0: Pt, p1: Pt, *, vertical: bool = True, tension: float = 0.5) -> str:
    if vertical:
        c0 = (p0[0], p0[1] + (p1[1] - p0[1]) * tension)
        c1 = (p1[0], p1[1] - (p1[1] - p0[1]) * tension)
    else:
        c0 = (p0[0] + (p1[0] - p0[0]) * tension, p0[1])
        c1 = (p1[0] - (p1[0] - p0[0]) * tension, p1[1])
    return (M(p0) + f"C{fmt(c0[0])},{fmt(c0[1])} {fmt(c1[0])},{fmt(c1[1])} "
            f"{fmt(p1[0])},{fmt(p1[1])}")


def offset_along(pts: Sequence[Pt], d: float) -> list[Pt]:
    """Offset a polyline sideways by d. Used to bundle parallel metro lines
    so that shared corridors show every route side by side."""
    if abs(d) < 1e-9 or len(pts) < 2:
        return list(pts)
    out: list[Pt] = []
    for i, p in enumerate(pts):
        a = pts[max(0, i - 1)]
        b = pts[min(len(pts) - 1, i + 1)]
        v = _unit(a, b)
        if v is None:
            out.append(p)
            continue
        out.append((p[0] - v[1] * d, p[1] + v[0] * d))
    return out


def deg(r: float) -> float:
    return r * 180.0 / math.pi


def rad(d: float) -> float:
    return d * math.pi / 180.0


def normalise_angle(t: float) -> float:
    while t < 0:
        t += TAU
    while t >= TAU:
        t -= TAU
    return t


def text_is_upside_down(theta: float) -> bool:
    t = normalise_angle(theta)
    return math.pi / 2 < t < 3 * math.pi / 2
