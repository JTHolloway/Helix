"""Family Rings: one cell per couple, one ring per generation.

The chart this program is for. Founders at the centre, present day at the
rim, and every relationship readable without a legend:

    MARRIAGE    two names in one cell, stacked inside the ring band. Not a
                tie line, not a bracket, not a chord -- the cell IS the
                marriage, and there is nothing to misread.
    CHILDREN    one stem leaving the cell, to an arc that spans exactly that
                couple's children, with a tick down to each.
    SIBLINGS    everyone under one arc, and nobody else. Their own husbands
                and wives are on the row below, not in the row the arc runs
                along, so the arc cannot pick up a stranger.
    COUSINS     two arcs hanging off one cell. Follow either stem inward one
                ring and you are standing on the couple they share.
    REMARRIAGE  a second partner takes the next row down, and the stem to
                each set of children leaves from that partner's own row. You
                can see which mother a child belongs to at a glance.

Everything above is geometry from `couple_grid.py`; this file only serialises
it. If you find yourself computing an angle here that the grid could have
given you, the layout is in the wrong place.

WHY THE RINGS ARE UNEVEN. Each is sized to hold its own content: a ring with
remarriages in it needs a taller band than one without, and the widest name
in a generation decides how much radius that generation gets. Fixed rings
would mean obstructed text, which is the one thing a chart may never do.
"""
from __future__ import annotations

import math
from dataclasses import replace

from .. import geometry as G
from ..base import LayoutSettings, build_grid
from ..common import (PolarLabelPlacer, add_border, add_title, colour_for,
                      dash_for, est_text_width, fill_template, label_lines,
                      place_radial_label)
from ..plan import Canvas, Element, FontSpec, PlanMeta, RenderPlan
from ..registry import register


@register("radial_family", "Family Rings", "radial",
          "One cell per couple, one ring per generation, founders at the centre.",
          good_for="The whole family at once, when you want to trace who "
                   "married whom and which children are whose.",
          laser="good")
def radial_family(graph, s: LayoutSettings, style) -> RenderPlan:
    # ---- 0. the knobs worth turning --------------------------------------
    #
    # All of these are style tokens, so a preset can carry a whole look and
    # the control panel can offer them as sliders. See docs/OPTIONS.md.
    sib = float(style.get("layout.sibling_gap_cells", 0.10))
    fam = float(style.get("layout.family_gap_cells", 0.60))
    # `sibling_gap_frac` is the older, gentler control and still works: it
    # squeezes a sibling group toward its own centre, which is the same
    # intention said a different way.
    squeeze = float(style.get("layout.sibling_gap_frac", 0.0) or 0.0)
    if squeeze:
        sib *= max(0.0, 1.0 - min(squeeze, 0.95))
    g = build_grid(graph, replace(
        s, cells=True, sibling_gap=sib, family_gap=max(sib, fam),
        couple_leaf=str(style.get("couple.leaf", "auto")),
        min_cells=float(style.get("layout.min_cells", 0))))

    W = style.get("canvas.width_mm", 600)
    H = style.get("canvas.height_mm", W) if style.chose("canvas.height_mm") else W
    margin = style.get("canvas.margin_mm", 20)
    cx, cy = W / 2, H / 2
    col = style.get("cells.stroke", "#22201D")
    lw = style.get("connectors.width_mm", 0.4)
    size = style.get("type.size_mm", 2.9)
    inner = style.get("layout.inner_radius_mm", 95)
    sweep = math.radians(style.get("layout.sweep_deg", 360))
    start = math.radians(style.get("layout.start_angle_deg", -90))

    # ---- 0b. never let one couple own a quadrant --------------------------
    #
    # A small family cannot fill a disc. Spread over the full circle, three
    # siblings end up forty degrees apart and the arc over them sweeps like a
    # rainbow. Cap how wide one cell may be and draw a FAN of whatever angle
    # the family actually needs -- the names stay the same size and the
    # brothers and sisters stay together.
    if g.slots:
        widest_cell = max(sl.t1 - sl.t0 for sl in g)
        cap = float(style.get("layout.max_cell_deg", 12.0))
        if cap > 0 and widest_cell > 0:
            want = math.radians(cap) / widest_cell
            if want < sweep:
                # centre the fan on the angle the full circle would have
                # started from, so a small family looks composed rather than
                # like a full chart that ran out half way round
                start += (sweep - want) / 2
                sweep = want

    if not g.slots:
        plan = RenderPlan(canvas=Canvas(W, H, style.get("canvas.background", "#FBF8F2")),
                          meta=PlanMeta(engine="radial_family",
                                        warnings=list(g.warnings)))
        return plan

    # ---- 1. how tall each ring has to be ---------------------------------
    #
    # Reserve the space a name needs BEFORE drawing anything, so nothing is
    # ever squeezed on top of anything else. How much it needs depends on
    # which way it is set, so the two decisions have to be made together:
    #
    #   tangential  reads around the ring. Costs its WIDTH in arc and only
    #               its height in radius, so the band is thin. Far easier to
    #               read, and the right answer wherever there is room.
    #   radial      reads along its own branch. Costs its LENGTH in radius,
    #               so the band has to be as deep as the longest name in that
    #               generation -- but it fits where tangential cannot.
    #
    # Decide per ring, because the inner rings are roomy and the rim is not.
    rows_in: dict[int, int] = {}
    widest: dict[int, float] = {}
    cells_in: dict[int, int] = {}
    seen_cell: set[tuple[int, str]] = set()
    for sl in g:
        rows_in[sl.gen] = max(rows_in.get(sl.gen, 1), sl.row + 1)
        person = graph.people[sl.pid]
        for text, sz, _ in label_lines(style, person, sl.gen, sl.order):
            widest[sl.gen] = max(widest.get(sl.gen, 0.0),
                                 est_text_width(text, sz))
        key = (sl.gen, sl.cell or sl.pid)
        if key not in seen_cell:
            seen_cell.add(key)
            cells_in[sl.gen] = cells_in.get(sl.gen, 0) + 1

    # A row has to be as deep as the LABEL that goes in it, not as deep as
    # one line of type: a name with its dates under it is two lines, and
    # sizing rows by one printed the wife's name through her husband's.
    lab_h: dict[int, float] = {}
    for sl in g:
        h = sum(sz * 1.16 for _, sz, _ in
                label_lines(style, graph.people[sl.pid], sl.gen, sl.order))
        lab_h[sl.gen] = max(lab_h.get(sl.gen, 0.0), h)
    # 1.5, not 1.12: the label may be three lines deep (name, dates,
    # place) and the row under it has to start clear of the last of them,
    # with room left over for the rule that marks the marriage.
    pitch = {gen: lab_h.get(gen, size * 1.16) * 1.5 for gen in rows_in}
    stem = max(size * 2.2, style.get("layout.min_ring_gap_mm", 6.0))
    gens = sorted(rows_in)

    def radii(bands: dict[int, float]) -> tuple[dict[int, float], float]:
        r, out = inner, {}
        for gen in gens:
            out[gen] = r
            r += bands[gen]
        return out, r - stem

    def fit_to_panel(bands: dict[int, float]) -> dict[int, float]:
        """Fill the sheet, and never overrun it."""
        if not style.chose("canvas.width_mm"):
            return bands
        _, r_now = radii(bands)
        room = min(W, H) / 2 - margin
        if r_now <= inner or room <= inner:
            return bands
        k = (room - inner) / (r_now - inner)
        return {gen: bands[gen] * k for gen in gens}

    # A first guess, then grow to fill the sheet, then let any ring that
    # cannot read around the circle claim the depth a radial name needs.
    band = {gen: rows_in[gen] * pitch[gen] + stem for gen in gens}
    tangential: dict[int, bool] = {gen: True for gen in gens}
    for _ in range(4):
        band = fit_to_panel(band)
        ring_try, _ = radii(band)
        changed = False
        for gen in gens:
            arc = (sweep * ring_try[gen]) / max(cells_in.get(gen, 1), 1)
            fits = arc >= widest.get(gen, 0.0) * 1.08
            floor = rows_in[gen] * pitch[gen] + stem
            if not fits:
                floor = max(floor, widest.get(gen, 0.0) + stem)
            if tangential[gen] != fits or band[gen] < floor - 0.01:
                changed = True
            tangential[gen] = fits
            band[gen] = max(band[gen], floor)
        if not changed:
            break
    band = fit_to_panel(band)

    ring_r, R = radii(band)

    if not style.chose("canvas.width_mm"):
        W = H = 2 * (R + margin)
        cx, cy = W / 2, H / 2

    def row_r(sl) -> float:
        return ring_r[sl.gen] + sl.row * pitch[sl.gen]

    def theta(t: float) -> float:
        return start + t * sweep

    plan = RenderPlan(
        canvas=Canvas(W, H, style.get("canvas.background", "#FBF8F2"), "circle"),
        meta=PlanMeta(engine="radial_family", style=style.get("id", ""),
                      people=len(g.slots), generations=g.max_gen + 1,
                      year_min=int(g.year_min), year_max=int(g.year_max),
                      warnings=list(g.warnings)))
    plan.meta.extra["fit"] = {
        "required_mm": round(2 * (R + margin), 1),
        "panel_mm": round(min(W, H), 1),
        "fits": 2 * (R + margin) <= min(W, H) + 0.01,
        "shortfall_mm": round(max(0.0, 2 * (R + margin) - min(W, H)), 1),
        "ring_pitch_mm": round(min(band.values()), 1),
        "min_pitch_mm": round(min(pitch.values()) + stem, 1),
        "pitch_ok": True,
        "people": len(g.slots),
    }

    thr = _thread(graph, s)
    tcol = style.get("thread.colour", "#9B3A2E")
    tw = style.get("thread.stroke_width_mm", 1.2)

    # ---- 2. the couple cells ---------------------------------------------
    #
    # A hairline under every row but the last: it reads as "and", which is
    # exactly what it means, and it stops two names in one cell running
    # together when the type is small.
    cells: dict[str, list] = {}
    for sl in g:
        cells.setdefault(sl.cell or sl.pid, []).append(sl)
    for cid, members in cells.items():
        members.sort(key=lambda x: (x.row, x.tc))
        split = len(members) > 1 and all(m.row == 0 for m in members)
        if split:
            # TWO leaves, one per partner, so each ancestry sits inside the
            # partner it belongs to. The marriage is the tie between them --
            # the one place this design has to draw a line for it.
            for a, b in zip(members, members[1:]):
                r = row_r(a) + lab_h.get(a.gen, 0.0) * 0.5
                plan.add(Element(kind="path", layer="ENGRAVE",
                                 d=G.short_arc(cx, cy, r, theta(a.tc),
                                               theta(b.tc)),
                                 stroke=style.get("lines.marriage_colour", col),
                                 stroke_width=lw * 0.9, fill="none",
                                 person_id=a.pid, role="marriage", z=8))
            continue
        t0, t1 = theta(members[0].t0), theta(members[0].t1)
        mid = (t0 + t1) / 2
        for sl in members[:-1]:
            # in the GAP between two names, never through one of them: a rule
            # at the middle of the row pitch struck the dates out.
            r = row_r(sl) + lab_h.get(sl.gen, 0.0) + \
                (pitch[sl.gen] - lab_h.get(sl.gen, 0.0)) * 0.45
            half = (t1 - t0) * 0.22
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=G.arc_path(cx, cy, r, mid - half, mid + half),
                             stroke=style.get("lines.marriage_colour", col),
                             stroke_width=lw * 0.6, fill="none",
                             person_id=sl.pid, role="marriage", z=8))

    # ---- 3. one stem per family, one arc per sibling group ----------------
    #
    # ONE line for each fact, and never two. The direct line is not drawn as
    # a second path laid over the first -- it is the SAME stem, arc and tick,
    # in a different colour. A highlight drawn on top of the linework is
    # exactly the doubled-up clutter this chart exists to avoid.
    for uid, union in graph.unions.items():
        kids = [c for c in union.children if c in g.slots and g.slots[c].row == 0]
        parents = [p for p in union.partners if p in g.slots]
        if not kids or not parents:
            continue
        gen_k = g.slots[kids[0]].gen
        if gen_k - 1 not in ring_r:
            continue
        ts = sorted(theta(g.slots[c].tc) for c in kids)
        r_arc = ring_r[gen_k] - stem * 0.55
        # the stem leaves from the row of the partner this family belongs to,
        # so a second marriage is visibly a second marriage
        anchor = max(parents, key=lambda p: g.slots[p].row)
        r_from = row_r(g.slots[anchor]) + pitch[g.slots[anchor].gen] * 0.55
        same = [p for p in parents if g.slots[p].cell == g.slots[anchor].cell]
        if len(same) > 1 and all(g.slots[p].row == 0 for p in same):
            # split leaves: the children hang from BETWEEN the two, which is
            # what says they are the children of that marriage and not of one
            # of the partners alone
            t_head = sum(theta(g.slots[p].tc) for p in same) / len(same)
            r_from = max(row_r(g.slots[p]) for p in same) + \
                lab_h.get(g.slots[anchor].gen, 0.0) * 0.7
        else:
            t_head = theta(g.slots[anchor].tc)
        line = all(p in thr for p in parents[:1]) and any(c in thr for c in kids)
        c_line = tcol if line else col
        w_line = tw if line else lw

        plan.add(Element(kind="path", layer="ENGRAVE",
                         d=G.polyline([G.polar(cx, cy, r_from, t_head),
                                       G.polar(cx, cy, r_arc, t_head)]),
                         stroke=c_line, stroke_width=w_line, fill="none",
                         person_id=anchor, union_id=uid, role="stem", z=10))
        if len(kids) > 1:
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=G.short_arc(cx, cy, r_arc, ts[0], ts[-1]),
                             stroke=c_line, stroke_width=w_line, fill="none",
                             union_id=uid, role="siblings", z=10))
        for c in kids:
            tc = theta(g.slots[c].tc)
            person = graph.people[c]
            on = c in thr and line
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=G.polyline([G.polar(cx, cy, r_arc, tc),
                                           G.polar(cx, cy, ring_r[gen_k], tc)]),
                             stroke=tcol if on else colour_for(person, g.slots[c],
                                                               style, graph),
                             stroke_width=tw if on else lw,
                             dash=dash_for(person, style),
                             fill="none", person_id=c, union_id=uid,
                             role="thread" if on else "branch", z=10))

    # ---- 4. a cousin marriage, drawn as a chord --------------------------
    #
    # When both partners were born into the tree only one can hold the cell.
    # The chord says so, and it is the one relationship on this chart that
    # cannot be read off adjacency.
    if style.get("lines.marriage", True):
        for union in graph.unions.values():
            ps = [p for p in union.partners if p in g.slots]
            if len(ps) != 2:
                continue
            a, b = ps
            if g.slots[a].cell == g.slots[b].cell:
                continue                       # already one cell: nothing to draw
            ta, tb = theta(g.slots[a].tc), theta(g.slots[b].tc)
            ra, rb = row_r(g.slots[a]), row_r(g.slots[b])
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=G.polyline(_chord(cx, cy, ra, ta, rb, tb)),
                             stroke=style.get("lines.marriage_colour", "#8A6F4E"),
                             stroke_width=lw * 0.8, fill="none",
                             dash=style.get("lines.marriage_dash", "1.6,1.2"),
                             person_id=a, role="married_across", z=7))

    # ---- 5. names ---------------------------------------------------------
    placer = PolarLabelPlacer()
    for sl in sorted(g, key=lambda x: (x.gen, x.tc, x.row)):
        person = graph.people[sl.pid]
        t = theta(sl.tc)
        arc = abs(sl.t1 - sl.t0) * sweep * max(row_r(sl), 1e-3)
        lines = label_lines(style, person, sl.gen, sl.order)
        place_radial_label(plan, placer, person, lines, t, row_r(sl), cx, cy,
                           style, flip=_flip(t),
                           orientation="tangential" if tangential[sl.gen] else "radial",
                           arc_available=arc)

    plan.meta.extra["labels_hidden"] = placer.dropped
    add_border(plan, style, cx, cy, R + margin * 0.4)
    add_title(plan, style, cx, cy)
    _key(plan, style, W, H, margin, lw, col)
    return plan


def _flip(t: float) -> bool:
    """Radial text on the left half reads upside down unless it is turned."""
    d = math.degrees(t) % 360
    return 90 < d < 270


def _chord(cx, cy, r0, t0, r1, t1, bow: float = 0.45):
    """A shallow curve between two points, bowed toward the centre so it
    reads as a tie rather than as a branch."""
    x0, y0 = G.polar(cx, cy, r0, t0)
    x1, y1 = G.polar(cx, cy, r1, t1)
    pts = [(x0, y0)]
    n = 24
    for i in range(1, n):
        f = i / n
        r = (r0 + (r1 - r0) * f) * (1 - bow * math.sin(math.pi * f))
        t = t0 + (t1 - t0) * f
        pts.append(G.polar(cx, cy, max(r, 1.0), t))
    pts.append((x1, y1))
    return pts


def _thread(graph, s) -> set:
    from ...graph.thread import thread
    if not s.subject_id:
        return set()
    return set(thread(graph, s.subject_id).members)


def _key(plan, style, W, H, margin, lw, col):
    """Six lines, bottom left. A chart that outlives its maker has to say
    what its own marks mean."""
    if not style.get("lines.key", True):
        return
    x, y = margin, H - margin - 14
    size = style.get("type.size_mm", 2.9) * 0.72
    rows = [("cell", "two names in one cell — married"),
            ("arc", "an arc over brothers and sisters"),
            ("stem", "a stem from a couple to their children"),
            ("chord", "a marriage between two people already on the chart")]
    for i, (kind, text) in enumerate(rows):
        yy = y + i * size * 1.7
        if kind == "arc":
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=f"M {x:.3f},{yy:.3f} L {x + 7:.3f},{yy:.3f}",
                             stroke=col, stroke_width=lw, fill="none",
                             role="key", z=90))
        elif kind == "chord":
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=f"M {x:.3f},{yy:.3f} L {x + 7:.3f},{yy:.3f}",
                             stroke=style.get("lines.marriage_colour", "#8A6F4E"),
                             stroke_width=lw * 0.8, dash="1.6,1.2",
                             fill="none", role="key", z=90))
        elif kind == "cell":
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=f"M {x:.3f},{yy:.3f} L {x + 7:.3f},{yy:.3f}",
                             stroke=style.get("lines.marriage_colour", col),
                             stroke_width=lw * 0.55, fill="none",
                             role="key", z=90))
        else:
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=f"M {x + 3.5:.3f},{yy - 2:.3f} "
                               f"L {x + 3.5:.3f},{yy + 2:.3f}",
                             stroke=col, stroke_width=lw, fill="none",
                             role="key", z=90))
        plan.add(Element(kind="text", layer="ENGRAVE", text=text,
                         x=x + 10, y=yy + size * 0.35, fill=col,
                         font=FontSpec(size_mm=size, anchor="start"),
                         role="key", z=90))
