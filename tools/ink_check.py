#!/usr/bin/env python3
"""Measure the DRAWN CHART, not the grid behind it.

    python3 tools/ink_check.py my-family.helix --style panel1m

Every other check in this repository asks the layout what it intended.
This one asks the plan what it actually put on the sheet, because the
faults the owner keeps finding are not errors of intent -- the grid was
right every time -- they are two correct lines that happen to land close
enough together to read as one.

Three questions, all of them about ink:

  1. TOUCHING ARCS   two tangential lines belonging to different families,
     at almost the same radius, whose angles meet or overlap. On the page
     that is ONE line, and it says the two families are one family. This is
     what put "four children with different mothers on the same branch".

  2. LONG WAY ROUND  an arc that sweeps further than the names it gathers
     up. A wrap bug: the children straddle the seam at the start angle, the
     angles get sorted numerically, and the arc is drawn between the two
     extremes the long way instead of across the seam. NOT the same thing as
     a long arc -- the founders' children really can be spread over most of
     the disc, and an arc that spans them honestly is not a fault.

  3. TEXT ON A LINE  a name whose box a line passes through.

Numbers going down is the only evidence a change helped.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from helix.graph import build                        # noqa: E402
from helix.layout import registry                    # noqa: E402
from helix.layout.base import LayoutSettings         # noqa: E402
from helix.layout.engines import family              # noqa: E402,F401
from helix.render.pathflatten import flatten         # noqa: E402
from helix.store.db import connect                   # noqa: E402
from helix.style.tokens import Style                 # noqa: E402

TAU = math.tau
LINEWORK = {"siblings", "stem", "branch", "thread", "marriage",
            "unknown_partner", "chord", "reach",
            "marriage_divider"}


def norm(a: float) -> float:
    """Into 0..TAU."""
    return a % TAU


def arc_gap(a0: float, a1: float, b0: float, b1: float) -> float:
    """Angular gap between two arcs [a0,a1] and [b0,b1], each given
    anticlockwise from its first to its second angle. Zero if they overlap.

    Cyclic: an arc from 350 to 10 degrees is twenty degrees long and does
    contain zero. Doing this with plain comparisons is what let a family
    straddling the seam be measured as if it spanned the whole circle.
    """
    def inside(x, lo, hi):
        return norm(x - lo) <= norm(hi - lo) + 1e-12

    if (inside(b0, a0, a1) or inside(b1, a0, a1)
            or inside(a0, b0, b1) or inside(a1, b0, b1)):
        return 0.0
    return min(norm(b0 - a1), norm(a0 - b1))


def runs_of(pts, cx, cy, flat_mm=0.4):
    """Split a polyline into TANGENTIAL runs -- the stretches that follow a
    circle about the centre, and ONLY those. The tolerance is tight on
    purpose: an arc is sampled exactly on its circle, so a genuine one has
    no radial change at all, while a stem curving round the band changes
    radius steadily all the way. Loose enough to admit the second, this
    reported every curve as an arc at its own mean radius and found it
    "merging" with whatever real arc happened to be at that radius.

    Yields (r_mean, t_start, t_end, sweep) with t_start->t_end anticlockwise.
    """
    if len(pts) < 2:
        return
    pol = [(math.hypot(x - cx, y - cy), math.atan2(y - cy, x - cx))
           for x, y in pts]
    cur, out = [pol[0]], []
    for now in pol[1:]:
        rs = [r for r, _ in cur] + [now[0]]
        # The test is on the RUN, not on the step. A stem curving round a
        # narrow band changes radius by a hair per sample and by the width of
        # the band overall; step by step it looked exactly like an arc, and
        # every curve was reported as merging with whatever real arc happened
        # to lie at its mean radius.
        if max(rs) - min(rs) < flat_mm:
            cur.append(now)
        else:
            out.append(cur)
            cur = [now]
    out.append(cur)
    for run in out:
        if len(run) < 2:
            continue
        rs = [r for r, _ in run]
        # accumulate the turn so a run that wraps is measured as it is drawn
        t0 = run[0][1]
        turn = 0.0
        for a, b in zip(run, run[1:]):
            d = b[1] - a[1]
            while d > math.pi:
                d -= TAU
            while d < -math.pi:
                d += TAU
            turn += d
        if abs(turn) < 1e-4:
            continue
        r = sum(rs) / len(rs)
        # LONG ENOUGH TO READ AS A LINE. A stem curving across the band is
        # very nearly tangential for a millimetre or two in the middle, and
        # counting those scraps as arcs had every curve "merging" with
        # whatever real arc it happened to pass.
        if abs(turn) * r < 4.0:
            continue
        t1 = t0 + turn
        lo, hi = (t0, t1) if turn > 0 else (t1, t0)
        yield (r, norm(lo), norm(hi), abs(turn))


def label_boxes(plan):
    """Rough oriented box for each name, as four corners in mm."""
    for el in plan.elements:
        if el.kind != "text" or not el.text:
            continue
        f = el.font
        size = getattr(f, "size_mm", 3.0) if f else 3.0
        w = len(el.text) * size * 0.52
        h = size * 1.05
        anchor = getattr(f, "anchor", "middle") if f else "middle"
        dx = {"start": 0.0, "middle": -w / 2, "end": -w}.get(anchor, -w / 2)
        a = math.radians(el.rotate)
        ca, sa = math.cos(a), math.sin(a)
        pts = []
        for lx, ly in ((dx, -h / 2), (dx + w, -h / 2),
                       (dx + w, h / 2), (dx, h / 2)):
            pts.append((el.x + lx * ca - ly * sa, el.y + lx * sa + ly * ca))
        yield el, pts


def _cross_point(p, q, r, s):
    """Where two segments cross, or None. Touching at an end does not count:
    that is a junction, and the chart is full of them by design."""
    d1 = (q[0] - p[0], q[1] - p[1])
    d2 = (s[0] - r[0], s[1] - r[1])
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(den) < 1e-12:
        return None
    t = ((r[0] - p[0]) * d2[1] - (r[1] - p[1]) * d2[0]) / den
    u = ((r[0] - p[0]) * d1[1] - (r[1] - p[1]) * d1[0]) / den
    if 0.02 < t < 0.98 and 0.02 < u < 0.98:
        return (p[0] + t * d1[0], p[1] + t * d1[1])
    return None


def seg_box_hit(p, q, box) -> bool:
    """Does segment p-q pass through the quadrilateral `box`?"""
    def cross(o, a, b):
        return ((a[0] - o[0]) * (b[1] - o[1])
                - (a[1] - o[1]) * (b[0] - o[0]))

    for i in range(4):
        r, s = box[i], box[(i + 1) % 4]
        d1, d2 = cross(p, q, r), cross(p, q, s)
        d3, d4 = cross(r, s, p), cross(r, s, q)
        if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
            return True
    return False


def _coerce(v: str):
    low = v.strip().lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v


def report(db, style_name, focus, engine, gap_mm, quiet=False,
           panel=None, sets=()) -> dict:
    g = build.load(connect(db, create=False, backup_daily=False))
    style = Style.load(style_name) if style_name else Style.load()
    if panel:
        w, _, h = panel.partition("x")
        style.set("canvas.width_mm", float(w))
        style.set("canvas.height_mm", float(h or w))
    for s in sets:
        k, _, v = s.partition("=")
        style.set(k.strip(), _coerce(v))
    st = LayoutSettings(engine=engine, subject_id=g.subject_id, focus=focus,
                        cells=True)
    plan = registry.get(engine).fn(g, st, style)
    # NOT the middle of the sheet. A fan is recentred on the box round its
    # own sector; measuring from the sheet centre put every radius tens of
    # millimetres out and had this file reporting faults that were not there
    # while missing the ones that were.
    cx, cy = plan.meta.extra.get(
        "centre_mm", [plan.canvas.width_mm / 2, plan.canvas.height_mm / 2])
    name = {p: g.people[p].full_name.strip() for p in g.people}

    # WHERE EVERY NAME IS. A line is reported by the names it appears to
    # join, not by the union it belongs to: the union knows children who
    # were never placed, and the whole point of this file is to describe
    # what somebody looking at the sheet would say.
    at: list[tuple[float, float, str]] = []
    seen_p: set[str] = set()
    for el in plan.elements:
        if el.kind != "text" or not el.person_id or el.person_id in seen_p:
            continue
        seen_p.add(el.person_id)
        at.append((norm(math.atan2(el.y - cy, el.x - cx)),
                   math.hypot(el.x - cx, el.y - cy),
                   name.get(el.person_id, "?")))
    at.sort()
    at_pid = {el.person_id for el in plan.elements
              if el.kind == "text" and el.person_id}
    # The rows of names, found from the names themselves rather than from a
    # fixed distance: on a metre panel the rings are further apart than the
    # 34 mm this first assumed, and half of every family fell outside the
    # window and was not counted.
    rows: list[list[float]] = []
    for rr in sorted(x[1] for x in at):
        if rows and rr - rows[-1][-1] < 6.0:
            rows[-1].append(rr)
        else:
            rows.append([rr])
    bands = [(min(x) - 1.0, max(x) + 1.0) for x in rows]

    def joins(r, t0, t1) -> list[str]:
        """The names a line at this radius and span appears to gather up:
        the nearest row of names outside it, as far as it reaches."""
        band = next((b for b in bands if b[0] > r), None)
        if band is None:
            return []
        return [n for a, rr, n in at
                if band[0] <= rr <= band[1] and arc_gap(t0, t1, a, a) == 0.0]

    # ---------------------------------------------------- collect the ink
    arcs = []          # (r, t0, t1, sweep, key, role, el)
    for el in plan.elements:
        if el.kind != "path" or el.role not in LINEWORK or not el.d:
            continue
        # `line_id` is the CELL: the two ties under somebody who
        # married twice are one cell's business and may meet.
        key = el.union_id or el.line_id or el.person_id or id(el)
        for pts, _closed in flatten(el, 0.25):
            for r, t0, t1, sweep in runs_of(pts, cx, cy):
                if r < 1.0:
                    continue
                arcs.append((r, t0, t1, sweep, key, el.role, el))

    # 1 ------------------------------------------------------ touching arcs
    hits = []
    arcs.sort(key=lambda a: a[0])
    for i, a in enumerate(arcs):
        for b in arcs[i + 1:]:
            if b[0] - a[0] > gap_mm:
                break
            if a[4] == b[4]:
                continue
            dt = arc_gap(a[1], a[2], b[1], b[2])
            # a gap of a millimetre or less at this radius reads as joined
            if dt * max(a[0], 1.0) <= gap_mm:
                hits.append((abs(a[0] - b[0]), dt * a[0], a, b))
    hits.sort(key=lambda h: (h[0], h[1]))

    # 2 ----------------------------------------------------- long way round
    #
    # Measured against the TICKS -- the little radial marks dropping from an
    # arc to each child -- because they sit at exactly the angle the layout
    # gave that person. Names cannot be used: the label placer nudges them
    # aside to stop them colliding, and an arc was reported as overshooting
    # by the width of the nudge.
    #
    # An arc should be the tightest span that holds its own children. A
    # sibling group really can be spread over most of the disc, so a long
    # arc is not in itself a fault; an arc longer than the children it
    # covers went round the outside to reach them, and that is.
    ticks: dict[str, list[float]] = {}
    for el in plan.elements:
        if el.kind != "path" or el.role not in ("branch", "thread") or not el.d:
            continue
        for pts, _c in flatten(el, 1.0):
            if len(pts) >= 2:
                mx = (pts[0][0] + pts[-1][0]) / 2, (pts[0][1] + pts[-1][1]) / 2
                ticks.setdefault(el.union_id or "", []).append(
                    norm(math.atan2(mx[1] - cy, mx[0] - cx)))
    t_start = plan.meta.extra.get("start_rad", 0.0)
    closed = plan.meta.extra.get("sweep_rad", TAU) >= TAU - 1e-9
    long_way = []
    pad = math.radians(0.5)      # an arc END and its own tick round differently
    for a in arcs:
        if a[5] != "siblings":
            continue
        angs = sorted(x for x in ticks.get(a[4], ())
                      if arc_gap(a[1] - pad, a[2] + pad, x, x) == 0.0)
        if len(angs) < 2:
            continue
        if closed:
            gaps = [b - x for x, b in zip(angs, angs[1:])]
            gaps.append(TAU - (angs[-1] - angs[0]))
            need = TAU - max(gaps)                   # the tightest cover
        else:
            # A FAN IS NOT A CIRCLE. The tightest span holding these
            # children may only be measured inside the chart's own sweep --
            # going round the outside crosses the empty sector the chart
            # does not occupy, and calling that "tighter" reported an
            # honest 273-degree arc over six Pargeters as a wrap bug.
            us = sorted((x - t_start) % TAU for x in angs)
            need = us[-1] - us[0]
        if a[3] > need + math.radians(2):
            long_way.append(a)

    # 3 ------------------------------------------------------ text on lines
    boxes = list(label_boxes(plan))
    crossed = []
    for el in plan.elements:
        if el.kind != "path" or el.role not in LINEWORK or not el.d:
            continue
        for pts, _c in flatten(el, 0.4):
            for p, q in zip(pts, pts[1:]):
                # Which PART of the line: a stem is a radial run out from
                # its couple and a tangential elbow carrying it round, and
                # the two are fixed in completely different places.
                dr = abs(math.hypot(q[0] - cx, q[1] - cy)
                         - math.hypot(p[0] - cx, p[1] - cy))
                part = "elbow" if dr < 0.35 else "spoke"
                for tel, box in boxes:
                    if tel.person_id and tel.person_id == el.person_id:
                        continue
                    if seg_box_hit(p, q, box):
                        crossed.append((tel.text, f"{el.role} ({part})"))
                        break
    crossed = sorted(set(crossed))

    # 4 ------------------------------------------------------------ crossings
    #
    # One line passing THROUGH another. Nothing on this chart means "these
    # two lines meet"; a crossing is always an accident of routing, and at
    # the width the direct line is drawn it is the loudest thing on the
    # sheet. Counted between different families only -- a stem meeting its
    # own arc is a junction, which is the whole point of it.
    segs = []
    for el in plan.elements:
        if el.kind != "path" or el.role not in LINEWORK or not el.d:
            continue
        key = el.union_id or el.person_id or str(id(el))
        for pts, _c in flatten(el, 0.4):
            for p, q in zip(pts, pts[1:]):
                segs.append((p, q, key, el.role))
    grid: dict = {}
    for i, (p, q, _k, _r) in enumerate(segs):
        for gx in range(int(min(p[0], q[0]) // 12), int(max(p[0], q[0]) // 12) + 1):
            for gy in range(int(min(p[1], q[1]) // 12),
                            int(max(p[1], q[1]) // 12) + 1):
                grid.setdefault((gx, gy), []).append(i)
    crossings = set()
    for cell in grid.values():
        for ai in range(len(cell)):
            for bi in range(ai + 1, len(cell)):
                a, b = segs[cell[ai]], segs[cell[bi]]
                if a[2] == b[2]:
                    continue
                x = _cross_point(a[0], a[1], b[0], b[1])
                if x:
                    crossings.add((round(x[0], 1), round(x[1], 1),
                                   *sorted((a[3], b[3]))))

    # 5 ----------------------------------------------------------- loose ends
    #
    # A line that stops in mid-air. Every end of every line on this chart
    # belongs to something: a stem ends on an arc, an arc ends on a tick, a
    # tick ends at a name. An end with nothing within a millimetre of it is
    # a branch that appears to come from nowhere.
    ends, body = [], []
    for el in plan.elements:
        if el.kind != "path" or el.role not in LINEWORK or not el.d:
            continue
        if el.role in ("marriage", "unknown_partner", "chord",
                       "marriage_divider"):
            # something to LAND on, never something with a loose end of its
            # own: a rule is a tie between two names and ends at each of them
            for pts, _c in flatten(el, 0.4):
                body += [((a, b), id(el)) for a, b in zip(pts, pts[1:])]
            continue
        key = id(el)                 # THE PATH, not the family: a tick
        # ONLY THE ENDS THAT MUST JOIN SOMETHING, and measured over the WHOLE
        # path. A tick ends at the name it points at and a stem begins at the
        # name it comes from -- names are not lines, and an end resting on
        # one is not adrift. Nor is either side of a deliberate hop, which is
        # why this counts subpaths together: what must never happen is the
        # far end of a stem, or either end of an arc, finding nothing.
        subs = [pts for pts, _c in flatten(el, 0.4) if len(pts) >= 2]
        if not subs:
            continue
        allp = [p for pts in subs for p in pts]
        far = max(math.hypot(q[0] - cx, q[1] - cy) for q in allp)
        near = min(math.hypot(q[0] - cx, q[1] - cy) for q in allp)
        for pts in subs:
            for p in (pts[0], pts[-1]):
                rp = math.hypot(p[0] - cx, p[1] - cy)
                if el.role in ("branch", "thread"):
                    if rp >= far - 0.01:
                        continue
                elif el.role == "stem":
                    if rp < far - 0.01:      # a hop, or the name it leaves
                        continue
                ends.append((p, key, el.role))
            body += [((a, b), key) for a, b in zip(pts, pts[1:])]
    # Against the SEGMENTS, not against the sampled points. A long arc at a
    # small radius is flattened into steps twenty millimetres apart, so a
    # tick landing squarely on the middle of one was reported ten
    # millimetres from the nearest point and called adrift.
    bgrid: dict = {}
    for (a, b), key in body:
        for gx in range(int(min(a[0], b[0]) // 8), int(max(a[0], b[0]) // 8) + 1):
            for gy in range(int(min(a[1], b[1]) // 8),
                            int(max(a[1], b[1]) // 8) + 1):
                bgrid.setdefault((gx, gy), []).append(((a, b), key))

    def _to_seg(p, a, b) -> float:
        dx, dy = b[0] - a[0], b[1] - a[1]
        d2 = dx * dx + dy * dy
        t = 0.0 if d2 < 1e-12 else max(0.0, min(
            1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / d2))
        return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))

    loose = []
    for p, key, role in ends:
        near = False
        for gx in (-1, 0, 1):
            for gy in (-1, 0, 1):
                for (a, b), k2 in bgrid.get((int(p[0] // 8) + gx,
                                             int(p[1] // 8) + gy), ()):
                    if k2 != key and _to_seg(p, a, b) < 1.2:
                        near = True
                        break
                if near:
                    break
            if near:
                break
        if not near:
            loose.append((p, role,
                          math.hypot(p[0] - cx, p[1] - cy),
                          norm(math.atan2(p[1] - cy, p[0] - cx))))

    # 6 ------------------------------------------- marriage under the siblings
    #
    # THE ORDER OF THE THREE LINES ROUND A NAME, and it has to be the same
    # everywhere or none of them means anything:
    #
    #     the sibling arc    inside, nearer the centre  -- where you came from
    #     the name
    #     the marriage rule  outside                    -- who you married
    #     the stem           outside that               -- your children
    #
    # Read with the near half of the disc the right way up, "outside" is
    # underneath, so the marriage sits under the sibling line and over the
    # children. Any couple where those two swap makes a marriage look like a
    # descent.
    arc_r: dict[str, float] = {}
    for el in plan.elements:
        if el.role == "siblings" and el.union_id and el.d:
            for pts, _c in flatten(el, 1.0):
                arc_r[el.union_id] = min(
                    arc_r.get(el.union_id, 1e9),
                    min(math.hypot(p[0] - cx, p[1] - cy) for p in pts))
    wrong_order = []
    for el in plan.elements:
        if el.role not in ("marriage", "unknown_partner") or not el.d:
            continue
        pid = el.person_id
        uid = g.people[pid].child_of if pid in g.people else None
        if uid is None or uid not in arc_r:
            continue
        for pts, _c in flatten(el, 1.0):
            rr = min(math.hypot(p[0] - cx, p[1] - cy) for p in pts)
            if rr <= arc_r[uid]:
                wrong_order.append((name.get(pid, "?"), rr, arc_r[uid]))

    # 7 --------------------------------------------- every relationship drawn
    #
    # Not "does it look right" but "is it all there". One line per fact, and
    # every fact with a line: a stem for every marriage that has children on
    # the chart, a tick for every one of those children, and exactly one tie
    # for every couple both of whom are drawn.
    stems = {el.union_id for el in plan.elements if el.role == "stem"}
    ticks: dict[str, int] = {}
    for el in plan.elements:
        if el.role in ("branch", "thread") and el.person_id:
            ticks[el.person_id] = ticks.get(el.person_id, 0) + 1
    ties = set()
    for el in plan.elements:
        if el.role in ("marriage", "chord", "married_across"):
            ties.add(el.person_id)
    placed = set(at_pid)
    missing = []
    for uid, u in g.unions.items():
        ps = [p for p in u.partners if p in placed]
        if not ps:
            continue                 # parents outside the focus: nothing to
                                     # draw a descent line FROM
        # Strictly the union marked primary. Somebody with several parent
        # links and none of them primary is a gap in the research, not a
        # missing line -- `graph/validate.py` reports that, and the chart may
        # not guess which set to draw.
        kids = [c for c in u.children
                if c in placed and g.people[c].child_of == uid]
        if kids and uid not in stems:
            missing.append(f"no stem for {'+'.join(name[p] for p in ps)}")
        for c in kids:
            if ticks.get(c, 0) != 1:
                missing.append(f"{name[c]} has {ticks.get(c, 0)} branch ticks")
    for uid, u in g.unions.items():
        ps = [p for p in u.partners if p in placed]
        if len(ps) == 2 and not (set(ps) & ties):
            missing.append(f"no tie between {name[ps[0]]} and {name[ps[1]]}")

    if not quiet:
        print(f"{db}  engine {engine}  style {style_name or 'default'}  "
              f"{plan.canvas.width_mm:.0f}x{plan.canvas.height_mm:.0f} mm")
        print(f"{len(arcs)} tangential runs of ink\n")

        print(f"1. TOUCHING ARCS           {len(hits)}"
              f"   (different families, reads as one line)")
        for dr, dtmm, a, b in hits[:10]:
            print(f"     r={a[0]:6.1f} {a[5]:<9} "
                  f"{', '.join(joins(*a[:3]))[:46]}")
            print(f"     r={b[0]:6.1f} {b[5]:<9} "
                  f"{', '.join(joins(*b[:3]))[:46]}"
                  f"   dr={dr:.2f}mm gap={dtmm:.2f}mm")

        print(f"\n2. LONG WAY ROUND          {len(long_way)}"
              f"   (an arc more than half the disc)")
        for a in long_way[:6]:
            print(f"     r={a[0]:6.1f} {a[5]:<9} {math.degrees(a[3]):6.1f} deg"
                  f"  {', '.join(joins(*a[:3]))[:44]}")

        print(f"\n3. TEXT ON A LINE          {len(crossed)}")
        for t, role in crossed[:10]:
            print(f"     {t[:34]:<34} crossed by {role}")

        print(f"\n4. LINES CROSSING          {len(crossings)}"
              f"   (two families' linework, passing through)")
        tally: dict = {}
        for _x, _y, r1, r2 in crossings:
            tally[(r1, r2)] = tally.get((r1, r2), 0) + 1
        for (r1, r2), n in sorted(tally.items(), key=lambda kv: -kv[1])[:8]:
            print(f"     {n:4d}   {r1} x {r2}")

        print(f"\n5. LOOSE ENDS              {len(loose)}"
              f"   (a line stopping in mid-air)")
        for p, role, r, t in loose[:8]:
            print(f"     {role:<9} r={r:6.1f} at {math.degrees(t):6.1f} deg"
                  f"   {', '.join(joins(r, t - 0.02, t + 0.02))[:36]}")

        print(f"\n6. MARRIAGE ABOVE SIBLINGS  {len(wrong_order)}"
              f"   (the two lines round a name, swapped)")
        for who_, rr, ar in wrong_order[:8]:
            print(f"     {who_[:28]:<28} rule r={rr:.1f} vs arc r={ar:.1f}")

        print(f"\n7. RELATIONSHIP NOT DRAWN  {len(missing)}")
        for m in missing[:10]:
            print(f"     {m}")

        print("\nAll seven should be ZERO.")

    return {"touching": len(hits), "long_way": len(long_way),
            "text_on_line": len(crossed), "crossings": len(crossings),
            "loose": len(loose), "order": len(wrong_order),
            "undrawn": len(missing), "hits": hits}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("db")
    ap.add_argument("--style", default=None)
    ap.add_argument("--focus", default="bloodline")
    ap.add_argument("--engine", default="radial_family")
    ap.add_argument("--gap-mm", type=float, default=1.6,
                    help="how close two lines have to be to read as one")
    ap.add_argument("--panel", default=None, help="finished size, e.g. 700x700")
    ap.add_argument("--set", action="append", default=[], metavar="NAME=VALUE")
    a = ap.parse_args()
    report(a.db, a.style, a.focus, a.engine, a.gap_mm,
           panel=a.panel, sets=getattr(a, "set"))


if __name__ == "__main__":
    main()
