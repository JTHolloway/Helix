"""Island detection: which pieces would fall out of the sheet and be lost.

THE PROBLEM. Any closed cut path frees the material inside it. Cut the outer
edge of a chart and the chart comes away, which is what you wanted. Cut a ring
inside it and the middle drops through the honeycomb, which usually is too.
But cut a shape inside THAT and the shape is a real piece of your chart, on
the floor, and nothing warned you until the job finished.

It is a nesting question and nothing more. Walk the closed loops on the CUT
layer and count how many of the others contain each one:

    depth 0   the outside edge of the piece
    depth 1   a hole in it -- waste, meant to fall out
    depth 2   material inside that hole. AN ISLAND.
    depth 3   a hole in the island, and so on, alternating

So the rule is: **even depth greater than zero is an island.** No geometry
library is needed for that, which matters, because Helix installs nothing.
Even-odd ray casting decides containment and it is exact for the polylines
this program emits.

WHAT TO DO WITH ONE. Either bridge it -- leave a sliver of material joining it
to its surroundings -- or move it onto the ENGRAVE layer so it is marked
rather than cut. `nearest` on each Island is where a bridge would be shortest.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..render import pathflatten

# Loops smaller than this are a rounding artefact or a bore for a fixing,
# not a piece of somebody's chart.
MIN_AREA_MM2 = 1.0


@dataclass
class Island:
    index: int
    area_mm2: float
    centroid: tuple[float, float]
    nearest: tuple[float, float]
    depth: int = 2
    person_id: str = ""
    gap_mm: float = 0.0


@dataclass
class Report:
    islands: list[Island] = field(default_factory=list)
    loops: int = 0
    layer: str = "CUT"

    @property
    def ok(self) -> bool:
        return not self.islands

    def summary(self) -> str:
        if not self.loops:
            return "Island check: nothing on the CUT layer that could fall out."
        if self.ok:
            return (f"Island check: {self.loops} closed cut loops, and none of "
                    f"them is a piece that would drop out.")
        worst = max(self.islands, key=lambda i: i.area_mm2)
        return (f"Island check: {len(self.islands)} of {self.loops} closed cut "
                f"loops would fall out of the sheet. The largest is "
                f"{worst.area_mm2:.0f} mm2 at "
                f"({worst.centroid[0]:.0f}, {worst.centroid[1]:.0f}) mm; a "
                f"bridge there would be {worst.gap_mm:.1f} mm long.")


def check(plan, *, layer: str = "CUT", tol: float = 0.05) -> Report:
    """Every closed loop on `layer` that would fall out of the sheet."""
    loops = _loops(plan, layer, tol)
    rep = Report(loops=len(loops), layer=layer)
    if len(loops) < 3:
        return rep                     # a piece and a hole cannot strand one
    boxes = [_bbox(p) for p, _ in loops]
    reps = [_rep(p) for p, _ in loops]
    for i, (pts, pid) in enumerate(loops):
        depth = sum(1 for j in range(len(loops))
                    if j != i and _contains(boxes[j], boxes[i])
                    and _point_in(reps[i], loops[j][0]))
        if depth < 2 or depth % 2:
            continue
        a = abs(_area(pts))
        if a < MIN_AREA_MM2:
            continue
        near, gap = _nearest(pts, loops, i)
        rep.islands.append(Island(index=i, area_mm2=a, centroid=_centroid(pts),
                                  nearest=near, depth=depth, person_id=pid,
                                  gap_mm=gap))
    rep.islands.sort(key=lambda k: -k.area_mm2)
    return rep


def auto_bridge(plan, width_mm: float = 1.5, max_bridges: int = 200):
    """Not built, on purpose. `check` says where the islands are; deciding
    where a bridge goes is a judgement about how the finished piece will look,
    and the honest answer today is that you should make that call.

    The plan, when it is: take each island's `nearest`, split both cut paths
    there and remove `width_mm` from each, on a BRIDGE sublayer so it can be
    moved. The automatic choice is topologically valid and rarely the
    prettiest, which is exactly why it needs to be movable.
    """
    raise NotImplementedError(
        "Automatic bridging is not built. Run fab.islands.check() to see where "
        "the islands are, then either add a tab in your laser software or move "
        "that shape to the ENGRAVE layer so it is marked, not cut.")


# ------------------------------------------------------------- geometry --
def _loops(plan, layer: str, tol: float):
    out = []
    for el in plan.elements:
        if el.layer != layer:
            continue
        for pts, closed in pathflatten.flatten(el, tol):
            if closed and len(pts) >= 3:
                out.append((pts, el.person_id or ""))
    return out


def _bbox(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _contains(outer, inner) -> bool:
    """Box test. It rejects almost every pair for four comparisons, and the
    ray cast behind it is the expensive part."""
    return (outer[0] <= inner[0] and outer[1] <= inner[1]
            and outer[2] >= inner[2] and outer[3] >= inner[3])


def _rep(pts):
    """A point certainly on the loop's own interior side.

    The centroid of a crescent can lie outside it, so fall back to the
    midpoint of the first diagonal from vertex 0 that stays inside.
    """
    c = _centroid(pts)
    if _point_in(c, pts):
        return c
    for k in range(2, len(pts)):
        m = ((pts[0][0] + pts[k][0]) / 2, (pts[0][1] + pts[k][1]) / 2)
        if _point_in(m, pts):
            return m
    return c


def _point_in(pt, poly) -> bool:
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            t = (y - y0) / (y1 - y0)
            if x < x0 + t * (x1 - x0):
                inside = not inside
    return inside


def _area(pts) -> float:
    s = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        s += x0 * y1 - x1 * y0
    return s / 2


def _centroid(pts):
    a = _area(pts)
    if abs(a) < 1e-9:
        return (sum(p[0] for p in pts) / len(pts),
                sum(p[1] for p in pts) / len(pts))
    cx = cy = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        f = x0 * y1 - x1 * y0
        cx += (x0 + x1) * f
        cy += (y0 + y1) * f
    return (cx / (6 * a), cy / (6 * a))


def _nearest(pts, loops, i):
    """The closest point on any other loop -- where a bridge would be
    shortest. Sampled, not exhaustive: this is advice about where to put a
    tab, and a tenth of a millimetre either way changes nothing."""
    best, gap = pts[0], float("inf")
    mine = pts[::max(1, len(pts) // 48)]
    for j, (other, _) in enumerate(loops):
        if j == i:
            continue
        for q in other[::max(1, len(other) // 48)]:
            for p in mine:
                d = math.hypot(p[0] - q[0], p[1] - q[1])
                if d < gap:
                    gap, best = d, q
    return best, (0.0 if gap == float("inf") else gap)
