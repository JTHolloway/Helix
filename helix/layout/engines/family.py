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
    sheet_w, sheet_h = W, H       # the material. The chart may use less.
    cx, cy = W / 2, H / 2
    col = style.get("cells.stroke", "#22201D")
    lw = style.get("connectors.width_mm", 0.4)
    size = style.get("type.size_mm", 2.9)
    base_inner = float(style.get("layout.inner_radius_mm", 95))
    full = math.radians(style.get("layout.sweep_deg", 360))
    base_start = math.radians(style.get("layout.start_angle_deg", -90))
    sweep, start, inner = full, base_start, base_inner

    if not g.slots:
        plan = RenderPlan(canvas=Canvas(W, H, style.get("canvas.background", "#FBF8F2")),
                          meta=PlanMeta(engine="radial_family",
                                        warnings=list(g.warnings)))
        return plan

    # ---- 0b. the padding belongs to the sweep, not to the content ---------
    #
    # The grid leaves a gap at the 0/360 seam so the first family and the last
    # do not fuse, and pads a sparse chart out so that one couple cannot own a
    # quadrant of it. Both of those are ANGLES, and the chart is about to
    # choose its own angle -- so take the padding off the content and put it
    # back on the sweep, where one decision controls it. Left in both places,
    # a small family drew across 60% of its own fan and left the rest blank.
    t_lo = min(sl.t0 for sl in g)
    t_hi = max(sl.t1 for sl in g)
    span = max(t_hi - t_lo, 1e-9)
    for sl in g:
        sl.t0 = (sl.t0 - t_lo) / span
        sl.t1 = (sl.t1 - t_lo) / span
    # The fan is always centred on the same bearing a full disc would have
    # been -- founders at the top, the family opening downward. Measure that
    # from the WHOLE turn, before the padding comes off, or shrinking the
    # sweep swings the whole chart round the sheet with it.
    mid = base_start + full / 2
    full *= span              # a whole turn, less the seam the grid asked for

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

    # How much room a name really has: the distance to the NEXT couple along
    # the ring, not the width of its own cell. Every cell is one unit wide by
    # construction, so cell width says only how many cells the chart has --
    # it called a founder couple alone on the innermost ring "starved" when
    # the entire ring was theirs, and the chart grew a hole to fix it.
    centres: dict[int, list[float]] = {}
    for cid, mem in {(sl.gen, sl.cell or sl.pid): sl for sl in g}.items():
        centres.setdefault(cid[0], []).append(mem.tc)
    thin_in: dict[int, float] = {}
    for gen, ts in centres.items():
        ts.sort()
        thin_in[gen] = min((b - a for a, b in zip(ts, ts[1:])), default=1.0)

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

    # ---- 1a. how far round to go, and how big the hole is ----------------
    #
    # These are ONE decision, not two, and the old code made them separately
    # and got both wrong. A small family spread over a full disc puts three
    # siblings forty degrees apart; drawn as a narrow fan it wastes most of
    # the sheet; and the hole in the middle has to be big enough that the
    # OLDEST ring -- which is the innermost, where there is least room -- can
    # hold its couples without crowding.
    #
    # So lay the chart out at several sweep angles and keep the best. Two
    # things decide "best", in this order:
    #
    #   1. NO STARVED CELL. Measure the TIGHTEST cell on the chart, not the
    #      average: the average is flattered by a narrow fan, where three
    #      cells share a rim a metre long and a fourth is a sliver. Once
    #      every cell clears `min_cell_arc_mm` this stops counting, because
    #      arc beyond legible is worth less than the two below.
    #   2. NAMES THAT READ AROUND THE RING. A ring whose cells are too narrow
    #      for a name has to set it radially instead, along its own branch --
    #      legible, but harder work, and it costs the ring a lot of depth.
    #   3. BIG. Of the angles that tie, take the one whose RINGS cover most
    #      sheet. Not the one with the largest radius: a thirty-degree needle
    #      has an enormous radius and draws a chart the width of a ruler.
    #      Area counts the hole in the middle for nothing, so it cannot be
    #      gamed by pushing everything out to the rim.
    #
    # On a square sheet a small family comes out as a fan of the angle it
    # actually needs and a four-hundred-person family comes out as the full
    # disc, which is what each of them wants.
    cap = float(style.get("layout.max_cell_deg", 12.0))
    widest_cell = max(sl.t1 - sl.t0 for sl in g)
    # 0 means "work it out from the type": about three characters of arc,
    # which is the point below which a name has nowhere to go.
    min_arc = float(style.get("layout.min_cell_arc_mm", 0) or 0) or size * 3.2
    panel = bool(style.chose("canvas.width_mm"))
    # A name is centred on its cell, so the one on the end of a fan hangs
    # half its width out past the edge of the sector. Pay for that in the
    # fit, not afterwards, or the chart reports itself over the panel.
    over = 0.5 * max(widest.values(), default=0.0)

    def solve(sweep: float, tighten: float = 1.0) -> dict:
        """Lay the whole chart out at one sweep and hole size, and report.

        Returns everything the drawing needs, so the search can try a shape
        and keep the winner rather than working it out a second time.
        """
        start = mid - sweep / 2                   # same bisector as the disc
        # The hole has to be big enough that the innermost ring's own
        # circumference can hold its couples, and no bigger. Size it from
        # the COUNT of them, not from the narrowest: one thin cell is thin
        # because that branch is small, and inflating the whole chart to
        # widen it leaves a hole you could lose a plate in.
        #
        # It works downward too. A descendancy chart starts from one couple,
        # so its innermost ring holds a single cell and wants a much smaller
        # hole than the style's default -- which is why `tighten` is a search
        # variable rather than a constant: rings 63 mm apart became 88 mm.
        inner = max(base_inner * tighten, cells_in[gens[0]] * min_arc / sweep
                    if sweep > 0 else 0.0)
        inner = min(inner, min(W, H) * 0.34)      # never eat the whole sheet

        def radii(bands):
            r, out = inner, {}
            for gen in gens:
                out[gen] = r
                r += bands[gen]
            return out, r - stem

        def box(r_out):
            """The bounding box of the sector, with the label overhang."""
            p = math.atan2(over, max(r_out, 1e-6)) if sweep < full - 1e-9 else 0.0
            return _sector_bounds(inner, r_out, start - p, start + sweep + p)

        def fill(bands):
            """Grow to the sheet, and never overrun it.

            Measured on the SECTOR the chart actually occupies, not on a
            disc. A quarter-circle fan fits about twice the radius into the
            same square; a full circle behaves exactly as before, because
            its sector box IS the disc.
            """
            if not panel:
                return bands
            for _ in range(8):
                _, r_now = radii(bands)
                if r_now <= inner:
                    break
                x0, y0, x1, y1 = box(r_now)
                k = min((W - 2 * margin) / max(x1 - x0, 1e-6),
                        (H - 2 * margin) / max(y1 - y0, 1e-6))
                if abs(k - 1.0) < 0.002:
                    break
                grow = ((inner + (r_now - inner) * k) - inner) / (r_now - inner)
                bands = {gen: bands[gen] * grow for gen in gens}
            return bands

        # A first guess, then grow to fill the sheet, then let any ring that
        # cannot read around the circle claim the depth a radial name needs.
        band = {gen: rows_in[gen] * pitch[gen] + stem for gen in gens}
        tang = {gen: True for gen in gens}
        for _ in range(4):
            band = fill(band)
            ring_try, _ = radii(band)
            changed = False
            for gen in gens:
                arc = (sweep * ring_try[gen]) / max(cells_in.get(gen, 1), 1)
                fits = arc >= widest.get(gen, 0.0) * 1.08
                floor = rows_in[gen] * pitch[gen] + stem
                if not fits:
                    floor = max(floor, widest.get(gen, 0.0) + stem)
                if tang[gen] != fits or band[gen] < floor - 0.01:
                    changed = True
                tang[gen] = fits
                band[gen] = max(band[gen], floor)
            if not changed:
                break
        band = fill(band)
        ring_r, R = radii(band)

        # The tightest cell anywhere, in millimetres of arc. This is the one
        # number that says whether a name can be got into its own cell.
        tight = min(sweep * thin_in[gen] * ring_r[gen] for gen in gens)
        return {"sweep": sweep, "start": start, "inner": inner, "band": band,
                "ring_r": ring_r, "R": R, "tangential": tang, "box": box(R),
                "read": tight / min_arc if min_arc > 0 else 1.0,
                "tang": sum(tang.values()) / len(gens),
                # How much of the sheet the RINGS cover. The hole in the
                # middle counts for nothing, which is what stops a narrow
                # fan winning by pushing everything out to the rim.
                "area": 0.5 * sweep * (R * R - inner * inner)}

    # The cap is the user's own upper bound on how wide one couple may get:
    # it is what keeps three brothers close together instead of a third of a
    # circle apart. The search may go tighter than it, never wider.
    cap_sweep = full
    if cap > 0 and widest_cell > 0:
        cap_sweep = min(full, math.radians(cap) / widest_cell)

    # A sweep of anything but a whole turn is the user saying "draw this arc
    # and no more" -- honour it exactly. (Every preset sets `sweep_deg`, so
    # asking whether it was set says nothing; asking what it says does.)
    tries = [cap_sweep]
    if panel and full >= 2 * math.pi - 1e-9:
        tries += [math.radians(d) for d in range(30, 361, 10)
                  if math.radians(d) < cap_sweep - 1e-9]
    holes = [1.0, 0.62, 0.38] if panel else [1.0]
    best = None
    for sw in tries:
        for hole in holes:
            got = solve(sw, hole)
            key = (round(min(got["read"], 1.0), 2), round(got["tang"], 3),
                   round(got["area"], 0))
            if best is None or key > best[0]:
                best = (key, got)
    fit = best[1]
    sweep, start, inner = fit["sweep"], fit["start"], fit["inner"]
    band, ring_r, R = fit["band"], fit["ring_r"], fit["R"]
    tangential = fit["tangential"]

    # Put the sector where it belongs. A fan is not centred on the middle of
    # its own bounding box, so centring it as if it were leaves the chart
    # sitting off to one side with the empty half of the disc still paid for.
    #
    # And the sheet is a MAXIMUM, not a shape to fill. A fan that needs
    # 760 x 440 gets a 760 x 440 canvas, cut from the metre panel with the
    # rest left on the roll -- rather than a metre square with a third of it
    # blank, which is what "the chart looks sparse" actually was.
    bx0, by0, bx1, by1 = fit["box"]
    need_w, need_h = (bx1 - bx0) + 2 * margin, (by1 - by0) + 2 * margin
    W = min(W, need_w) if panel else need_w
    H = min(H, need_h) if panel else need_h
    cx, cy = (W - (bx1 - bx0)) / 2 - bx0, (H - (by1 - by0)) / 2 - by0

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
    # What the chart NEEDS is the box round its sector, not the diameter of
    # the disc it was cut from -- a fan asked for a metre of sheet it was
    # never going to touch, and then reported itself over the panel by it.
    # Both directions, separately: a fan on a 600x900 sheet is not over the
    # panel because it is 700 mm wide, if the 700 is the way the 900 runs.
    short = max(need_w - sheet_w, need_h - sheet_h, 0.0)
    plan.meta.extra["fit"] = {
        "required_mm": round(max(need_w, need_h), 1),
        "chart_mm": [round(need_w, 1), round(need_h, 1)],
        "panel_mm": round(min(sheet_w, sheet_h), 1),
        "fits": short <= 0.5,
        "shortfall_mm": round(short, 1),
        "sweep_deg": round(math.degrees(sweep), 1),
        "inner_mm": round(inner, 1),
        "cell_arc_mm": round(fit["read"] * min_arc, 1),
        "ring_pitch_mm": round(min(band.values()), 1),
        "min_pitch_mm": round(min(pitch.values()) + stem, 1),
        "pitch_ok": True,
        "people": len(g.slots),
    }

    thr = _thread(graph, s)
    tcol = style.get("thread.colour", "#9B3A2E")
    tw = style.get("thread.stroke_width_mm", 1.2)

    cells: dict[str, list] = {}
    for sl in g:
        cells.setdefault(sl.cell or sl.pid, []).append(sl)

    # ---- 2. the families, and where they come together --------------------
    #
    # At the inner rings a two-hundred-name chart is a dozen separate
    # families. Every marriage joins two of them, and by the outermost ring
    # there is one. Nothing in the linework says so -- a stem to a couple
    # looks the same whether the partner brought a documented line with them
    # or married in from nowhere.
    #
    # So tint the ground. Each family gets a wedge running outward from its
    # founders, and where a marriage brings two families together the two
    # wedges TAPER INTO ONE CELL and continue as a single wedge in the blend
    # of their two colours. That is the shape of the family, drawn once, in
    # the one place on the chart where nothing else is competing for the
    # ink: behind everything, on the layer the cutter never sees.
    if style.get("family.wedges", True) and len(gens) > 1:
        _wedges(plan, graph, g, cells, gens, ring_r, rows_in, pitch, stem,
                cx, cy, theta, style)

    # ---- 3. the couple cells ---------------------------------------------
    #
    # A hairline under every row but the last: it reads as "and", which is
    # exactly what it means, and it stops two names in one cell running
    # together when the type is small.
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

    # ---- 4. one stem per family, one arc per sibling group ----------------
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

    # ---- 5. a cousin marriage, drawn as a chord --------------------------
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

    # ---- 6. names ---------------------------------------------------------
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


def _wedges(plan, graph, g, cells, gens, ring_r, rows_in, pitch, stem,
            cx, cy, theta, style) -> None:
    """Tint the ground under each family, so you can see them come together.

    A family here is a founding couple and everyone descended from them. Its
    wedge covers, ring by ring, the angular ground its people stand on --
    narrow at the founders, widening outward as the family grows.

    A marriage between two of them is not drawn. It does not have to be:
    from that ring outward the two families share their descendants, so both
    wedges cover the same ground and the two tints LIE ON TOP OF EACH OTHER.
    The blend is the marriage. By the rim of a pedigree every wedge on the
    chart has converged on one cell, which is the person it was drawn for.

    Nothing here states a relationship the linework does not. It is the same
    facts at a distance you can read across a room, which is what a metre of
    plywood on a wall is for. It never reaches the cutter: `PRINT_ONLY`.
    """
    ring_of = {cid: m[0].gen for cid, m in cells.items()}
    cell_of = {sl.pid: (sl.cell or sl.pid) for sl in g}

    def parent_cells(cid):
        out = []
        for sl in cells[cid]:
            uid = graph.people[sl.pid].child_of
            u = graph.unions.get(uid) if uid else None
            if not u:
                continue
            for p in u.partners:
                pc = cell_of.get(p)
                if pc is not None and ring_of.get(pc) == ring_of[cid] - 1:
                    out.append(pc)
        return list(dict.fromkeys(out))

    kids: dict[str, list[str]] = {}
    for cid in sorted(cells):
        for pc in parent_cells(cid):
            kids.setdefault(pc, []).append(cid)

    cone: dict[str, set] = {}
    for r in reversed(gens):             # inward, so children answer first
        for cid in sorted(c for c in cells if ring_of[c] == r):
            out = {cid}
            for k in kids.get(cid, ()):
                out |= cone[k]
            cone[cid] = out

    # WHICH families get a wedge. The founders -- unless a founder's
    # descendants ARE the chart, which is the whole of a descendancy chart,
    # and one tint over all of it says nothing. Where that happens, drop down
    # to that couple's children and let their branches be the families.
    #
    # Nearly all, not most. On a pedigree BOTH of the subject's lines cover
    # about seventy per cent of the chart, because they share everything from
    # the marriage outward -- that overlap is the thing being drawn, and a
    # threshold that split it took the tint off the founders entirely.
    total = len(cells)
    share = float(style.get("family.wedge_max_share", 0.95))
    least = int(style.get("family.wedge_min_cells", 3))
    most = int(style.get("family.wedge_max", 10))
    queue = [c for c in sorted(cells) if not parent_cells(c)]
    pick: list[str] = []
    while queue:
        cid = queue.pop()
        if len(cone[cid]) > share * total and kids.get(cid):
            queue += kids[cid]
        else:
            pick.append(cid)
    keep = [f for f in sorted(set(pick), key=lambda k: (-len(cone[k]), k))
            if len(cone[f]) >= least][:most]
    if not keep:
        return

    pal = list(style.get("colour.palette"))[1:]     # [0] is the ink colour
    alpha = float(style.get("family.wedge_opacity", 0.13))

    def edges(r):
        """Ring bands that TOUCH, so a family is one wedge and not a ladder.

        The step where one ring is wider than the next is the point: it says
        the family was this wide here and that wide there.
        """
        r0 = ring_r[r] - stem * 0.5
        out = ring_r.get(r + 1)
        return r0, (out - stem * 0.5 if out is not None
                    else ring_r[r] + rows_in[r] * pitch[r])

    for i, f in enumerate(keep):
        fill = pal[i % len(pal)]
        for r in gens:
            here = [cells[c] for c in cone[f] if ring_of[c] == r]
            if not here:
                continue
            r0, r1 = edges(r)
            spans = sorted((min(m.t0 for m in c), max(m.t1 for m in c))
                           for c in here)
            # One shape per contiguous RUN. Taking the outermost pair instead
            # painted straight over whoever happened to sit in the gap, which
            # on a chart with two families interleaved is most of it.
            runs = [list(spans[0])]
            for lo, hi in spans[1:]:
                if lo <= runs[-1][1] + 0.02:
                    runs[-1][1] = max(runs[-1][1], hi)
                else:
                    runs.append([lo, hi])
            for lo, hi in runs:
                plan.add(Element(
                    kind="path", layer="PRINT_ONLY",
                    d=G.annular_sector(cx, cy, r0, r1, theta(lo), theta(hi)),
                    fill=fill, stroke="none", opacity=alpha,
                    person_id=cells[f][0].pid if f in cells else "",
                    role="family", z=-10))


def _sector_bounds(r0: float, r1: float, a0: float, a1: float):
    """Bounding box of an annular sector, relative to its own centre.

    A full disc is its own bounding box and there is nothing to think about.
    A FAN is not: a 168 degree fan drawn on a disc-sized square wastes most
    of the sheet, and on a fixed panel it could use nearly twice the radius.
    The box is the four corners plus whichever axis crossings fall inside the
    sweep -- those are where an arc bulges past its own endpoints.
    """
    pts = [(r * math.cos(a), r * math.sin(a))
           for a in (a0, a1) for r in (r0, r1)]
    lo, hi = min(a0, a1), max(a0, a1)
    k = math.ceil(lo / (math.pi / 2))
    while k * (math.pi / 2) <= hi:
        a = k * (math.pi / 2)
        pts.append((r1 * math.cos(a), r1 * math.sin(a)))
        k += 1
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


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
