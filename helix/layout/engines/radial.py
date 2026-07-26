"""Radial design family: five distinct visual languages on one disc.

  radial_sunburst  -- annular cells, the classic "blocky" fan
  radial_rings     -- concentric arcs joined by radial branches
  radial_organic   -- tapering roots, people as dots
  radial_lifeline  -- each person is a radial bar spanning their lifetime
  radial_spiral    -- one continuous spiral of time, branches leaving it

They share the abstract Grid from base.py and differ only in geometry, which
is exactly the point of the architecture.
"""
from __future__ import annotations

import math
from typing import Optional

from .. import geometry as G
from ..base import Grid, LayoutSettings, build_grid
from ..common import (LabelPlacer, PolarLabelPlacer, add_border, add_label,
                      add_title, colour_for, dash_for, est_text_width,
                      fill_template, label_lines, opacity_for, place_label,
                      place_radial_label, template_for)  # noqa: F401
from ..plan import Canvas, Element, PlanMeta, RenderPlan
from ..registry import register
from ..scales import nice_ticks, r_time, ring_widths


# ---------------------------------------------------------------- shared ----
def _frame(graph, s: LayoutSettings, style):
    W = style.get("canvas.width_mm", 600)
    H = style.get("canvas.height_mm", W) if style.chose("canvas.height_mm") else W
    margin = style.get("canvas.margin_mm", 20)
    cx, cy = W / 2, H / 2
    R = min(W, H) / 2 - margin
    r0 = style.get("layout.inner_radius_mm", 90)
    g = build_grid(graph, s)
    plan = RenderPlan(
        canvas=Canvas(W, H, style.get("canvas.background", "#FBF8F2"), "circle"),
        meta=PlanMeta(engine=s.engine, style=style.get("id", ""),
                      people=len(g.slots), generations=g.max_gen + 1,
                      year_min=int(g.year_min), year_max=int(g.year_max),
                      warnings=list(g.warnings)))
    return plan, g, cx, cy, r0, R


def _angles(style):
    t0 = G.rad(style.get("layout.start_angle_deg", -90))
    sweep = G.rad(style.get("layout.sweep_deg", 360))
    return t0, sweep


def _radius_of(sl, g: Grid, style, r0, R, widths):
    if style.get("layout.time_scale", True):
        return r_time(sl.year or g.year_min, g.year_min, g.year_max, r0, R,
                      style.get("layout.radius_gamma", 0.5))
    return r0 + sum(widths[:sl.gen])


def _time_rings(plan, g, style, cx, cy, r0, R):
    if not style.get("ornament.time_rings", True):
        return
    col = style.get("ornament.time_ring_colour", "#C9C0B0")
    gamma = style.get("layout.radius_gamma", 0.5)
    for yr in nice_ticks(g.year_min, g.year_max, 9):
        if not (g.year_min <= yr <= g.year_max):
            continue
        r = r_time(yr, g.year_min, g.year_max, r0, R, gamma)
        major = yr % 100 == 0
        plan.add(Element(kind="path", layer="ENGRAVE",
                         d=G.circle_path(cx, cy, r), stroke=col,
                         stroke_width=0.5 if major else 0.25, fill="none",
                         dash=None if major else "1.5,2",
                         role="tick", z=2))
        add_label(plan, str(yr), cx, cy - r - 1.6, style,
                  size=style.get("type.size_mm", 3) * 0.72, colour=col, z=3)


def _thread_set(graph, s: LayoutSettings):
    from ...graph.thread import thread
    return thread(graph, s.subject_id).members


# ============================================================ 1. SUNBURST ===
@register("radial_sunburst", "Radial Sunburst", "radial",
          "Annular cells radiating outward. Bold, architectural, unmistakably a family tree.",
          good_for="Large families; engraving; a first look at your whole tree.",
          laser="excellent")
def radial_sunburst(graph, s, style) -> RenderPlan:
    plan, g, cx, cy, r0, R = _frame(graph, s, style)
    t_start, sweep = _angles(style)
    pad = G.rad(style.get("layout.cell_pad_deg", 0.12))
    depth = style.get("cells.radial_depth_mm", 9)
    widths = ring_widths([len(g.by_gen.get(i, [])) for i in range(g.max_gen + 1)],
                         r0, R, style.get("layout.min_ring_mm", 8))
    thr = _thread_set(graph, s) if style.get("thread.enabled", True) else set()

    _time_rings(plan, g, style, cx, cy, r0, R)
    pos: dict[str, tuple[float, float]] = {}
    for sl in g:
        p = graph.people[sl.pid]
        t0 = t_start + sl.t0 * sweep + pad
        t1 = t_start + sl.t1 * sweep - pad
        if t1 <= t0:
            t1 = t0 + 1e-4
        r = _radius_of(sl, g, style, r0, R, widths)
        pos[sl.pid] = ((t0 + t1) / 2, r)
        col = colour_for(p, sl, style, graph)
        plan.add(Element(kind="path", layer="ENGRAVE",
                         d=G.annular_sector(cx, cy, r, r + depth, t0, t1),
                         stroke=col, fill=style.get("cells.fill", "none"),
                         stroke_width=style.get("cells.stroke_width_mm", 0.3),
                         dash=dash_for(p, style), opacity=opacity_for(p),
                         person_id=sl.pid, role="cell", z=20))

    _connect(plan, graph, g, style, cx, cy, pos, depth)
    _labels_radial(plan, graph, g, style, cx, cy, pos, depth, sweep)
    _thread_overlay(plan, graph, g, style, cx, cy, pos, thr, depth)
    add_border(plan, style, cx, cy, R + 6)
    add_title(plan, style, cx, cy)
    return plan


def _connect(plan, graph, g, style, cx, cy, pos, depth):
    st = style.get("connectors.style", "orthogonal")
    if st == "none":
        return
    col = style.get("connectors.colour", "#22201D")
    w = style.get("connectors.width_mm", 0.4)
    cr = style.get("connectors.corner_radius_mm", 2.0)
    for sl in g:
        if not sl.parent or sl.parent not in pos:
            continue
        tc, rc = pos[sl.pid]
        tp, rp = pos[sl.parent]
        rp_out = rp + depth
        if st == "organic":
            d = G.bezier_polar(cx, cy, rp_out, tp, rc, tc)
        elif st == "straight":
            d = G.polyline([G.polar(cx, cy, rp_out, tp), G.polar(cx, cy, rc, tc)])
        elif st == "circuit":
            d = G.polyline(G.elbow_polar(cx, cy, rp_out, tp, rc, tc, mid=0.5))
        else:                                   # orthogonal / labyrinth
            d = G.rounded_polyline(
                G.elbow_polar(cx, cy, rp_out, tp, rc, tc, mid=0.55), cr)
        plan.add(Element(kind="path", layer="ENGRAVE", d=d, stroke=col,
                         stroke_width=w, fill="none",
                         opacity=style.get("connectors.opacity", 1.0),
                         person_id=sl.pid, role="connector", z=10))


def _labels_radial(plan, graph, g, style, cx, cy, pos, depth, sweep):
    if not style.get("labels.show", True):
        return
    placer = LabelPlacer(min_gap_mm=style.get("labels.min_gap_mm", 0.5))
    # inner generations first: the oldest ancestors are the ones you most
    # want named, and they have the most room
    for sl in sorted(g, key=lambda s2: (s2.gen, s2.order)):
        p = graph.people[sl.pid]
        tc, r = pos[sl.pid]
        rm = r + depth / 2
        arc = abs(sl.span * sweep) * rm
        tpl = template_for(style, sl.gen)
        txt = fill_template(tpl, p, sl.order)
        size = style.get("type.size_mm", 3.0)
        longest = max((len(x) for x in txt.split("\n")), default=1)
        radial_mode = arc < est_text_width("x" * longest, size)
        if radial_mode:
            rot = G.deg(tc) + (180 if G.text_is_upside_down(tc) else 0)
            x, y = G.polar(cx, cy, rm, tc)
            place_label(plan, placer, p, txt.replace("\n", " "), x, y, style,
                        rotate=rot, size=size)
        else:
            rot = G.deg(tc) + 90 + (180 if G.text_is_upside_down(tc + math.pi / 2) else 0)
            x, y = G.polar(cx, cy, rm, tc)
            place_label(plan, placer, p, txt, x, y, style, rotate=rot, size=size)
    plan.meta.demotions = placer.demoted
    plan.meta.extra["labels_hidden"] = placer.dropped
    if placer.dropped:
        plan.meta.warnings.append(
            f"{placer.dropped} names did not fit and were left off. Make the "
            f"piece larger, show fewer generations, or switch to numbers "
            f"with a companion list.")


def _thread_overlay(plan, graph, g, style, cx, cy, pos, thr, depth):
    if not thr:
        return
    col = style.get("thread.colour", "#A3392B")
    w = style.get("thread.stroke_width_mm", 1.4)
    layer = style.get("thread.layer", "ENGRAVE_DEEP")
    for sl in g:
        if sl.pid not in thr or not sl.parent or sl.parent not in thr:
            continue
        if sl.parent not in pos or sl.pid not in pos:
            continue
        tc, rc = pos[sl.pid]
        tp, rp = pos[sl.parent]
        d = G.rounded_polyline(
            G.elbow_polar(cx, cy, rp + depth, tp, rc, tc, mid=0.55),
            style.get("connectors.corner_radius_mm", 2.0))
        plan.add(Element(kind="path", layer=layer, d=d, stroke=col,
                         stroke_width=w, fill="none", person_id=sl.pid,
                         role="thread", z=80))
    for pid in thr:
        if pid not in pos:
            continue
        tc, r = pos[pid]
        x, y = G.polar(cx, cy, r + depth / 2, tc)
        plan.add(Element(kind="circle", layer=layer, x=x, y=y, r=w * 0.9,
                         fill=col, stroke="none", person_id=pid,
                         role="thread", z=81))


# =============================================================== 2. RINGS ===
MAX_SUBROWS = 3
SAFETY = 1.35            # stagger a little before names actually touch
LABEL_CAP_MM = 46.0
INCH_MM = 25.4           # the default minimum gap between rings


@register("radial_rings", "Concentric Rings", "radial",
          "One ring per generation, joined by radial branches. Crowded "
          "sibling groups stagger into two or three alternating rows, and "
          "every name is aligned at the end of its own branch.",
          good_for="The circular-maze look, and the most legible radial "
                   "design here \u2014 the rings are sized to fit the names, "
                   "not the other way round.",
          laser="excellent")
def radial_rings(graph, s, style) -> RenderPlan:
    """One generation per ring, with staggered rows and aligned labels.

    THE IDEA THAT MAKES THIS WORK: the rings are sized to fit the text,
    rather than the text being squeezed into fixed rings. Nothing is ever
    obstructed, because the space was reserved before anything was drawn.

    Built outward, one generation at a time:

      1. Count the people in the ring and measure the longest name in it.
      2. Work out how many people fit round the circumference at that
         radius. If they do not fit, stagger them into 2 or 3 SUB-ROWS at
         slightly different radii. Neighbours alternate, so same-row
         neighbours sit two apart and can be packed twice as tightly
         without their labels touching.
      3. Reserve a band = (sub-rows - 1) x step + longest name + padding,
         never less than the minimum ring pitch (one inch by default).
      4. The next ring starts where that band ends.

    Given a FIXED panel -- a metre square of ply, say -- the same figures
    run the other way: any spare radius is shared out evenly so the rings
    breathe, and if the content genuinely will not fit, the shortfall is
    reported in millimetres rather than being quietly squashed.

    Drawing, per family:

      * a RADIAL SPOKE outward from the parent to the children's ring
      * a RING ARC at the inner edge of that ring, spanning only that
        parent's children -- the arcs lining up are what read as rings
      * a RADIAL BRANCH from the arc out to each child, long or short
        depending on the child's sub-row
      * the child's NAME set radially at the end of its own branch

    Tracing a family is therefore always the same three moves: out, along,
    out. The alternating branch lengths are what buy the room.
    """
    g = build_grid(graph, s)
    t_start, sweep = _angles(style)
    font = style.get("type.size_mm", 2.8)
    pad = style.get("layout.ring_pad_mm", 5.0)
    r0 = style.get("layout.inner_radius_mm", 70)
    lw = style.get("connectors.width_mm", 0.45)
    branch = style.get("nodes.branch_mm", 4.0)
    step = style.get("layout.subrow_step_mm", font * 2.2)
    gap = style.get("layout.label_gap_mm", 1.4)
    margin = style.get("canvas.margin_mm", 24)

    # ---- 1. how much room each ring needs for its text ------------------
    longest = {}
    for gen, pids in g.by_gen.items():
        w = 0.0
        for pid in pids:
            for txt, size, _ in label_lines(style, graph.people[pid], gen,
                                            g.slots[pid].order):
                w = max(w, est_text_width(txt, size))
        longest[gen] = min(w, style.get("labels.max_width_mm", LABEL_CAP_MM))

    # ---- 2. ring bands: content need, floored at the minimum pitch -------
    #
    # Two rules fight here and both must hold:
    #   * a ring must be wide enough for the longest name in it
    #   * no two rings may sit closer than the minimum pitch -- an inch by
    #     default -- because tight rings read as clutter however well the
    #     text technically fits
    # So band = max(content, min_pitch). Sub-row count depends on radius and
    # radius depends on the bands, so it is settled over a few passes.
    min_pitch = style.get("layout.min_ring_pitch_mm", INCH_MM)
    max_pitch = style.get("layout.max_ring_pitch_mm", 0) or 1e6
    max_rows = int(style.get("layout.max_subrows", MAX_SUBROWS))
    stagger = style.get("layout.stagger", "auto")     # auto | always | never
    # How much arc one entry is entitled to. Raising this thins a ring out
    # (by staggering sooner); lowering it packs people tighter.
    slot_need = max(font * 1.35, style.get("layout.min_entry_gap_mm", 0.0))
    ring_r: dict[int, float] = {}
    ring_k: dict[int, int] = {}
    bands: dict[int, float] = {gen: min_pitch for gen in range(g.max_gen + 1)}
    for _ in range(4):
        r = r0
        for gen in range(g.max_gen + 1):
            ring_r[gen] = r
            ring_k[gen] = _subrows(g, g.by_gen.get(gen, []), r, sweep,
                                   slot_need, max_rows, stagger)
            content = ((ring_k[gen] - 1) * step + branch + gap
                       + longest.get(gen, 0.0) + pad)
            bands[gen] = min(max_pitch, max(min_pitch, content))
            r += bands[gen]
    r_needed = r

    # ---- 3. fit it to the panel, or say plainly that it will not ---------
    if style.chose("canvas.width_mm"):
        W = style.get("canvas.width_mm")
        H = style.get("canvas.height_mm", W)
        r_avail = min(W, H) / 2 - margin
        if r_needed <= r_avail:
            # Spread the spare room evenly so the rings breathe -- but never
            # past max_ring_pitch, or a small family on a big panel ends up
            # as a few lonely hoops with acres of nothing between them.
            extra = (r_avail - r_needed) / max(1, g.max_gen + 1)
            r = r0
            for gen in range(g.max_gen + 1):
                ring_r[gen] = r
                bands[gen] = min(max_pitch, bands[gen] + extra)
                r += bands[gen]
            R = min(r_avail, r)
        else:
            # compress toward the pitch floor, then report the shortfall
            squeeze = max(0.05, (r_avail - r0) / max(1e-6, r_needed - r0))
            r = r0
            for gen in range(g.max_gen + 1):
                ring_r[gen] = r
                bands[gen] = max(min_pitch * 0.6, bands[gen] * squeeze)
                r += bands[gen]
            R = r
    else:
        W = H = 2 * (r_needed + margin)
        r_avail = r_needed
        R = r_needed
    cx, cy = W / 2, H / 2

    pitch = min(bands.values()) if bands else 0.0
    fit = {
        "required_mm": round(2 * (r_needed + margin), 1),
        "panel_mm": round(min(W, H), 1),
        "fits": r_needed <= r_avail + 0.01,
        "shortfall_mm": round(max(0.0, r_needed - r_avail) * 2, 1),
        "ring_pitch_mm": round(pitch, 1),
        "min_pitch_mm": round(min_pitch, 1),
        "pitch_ok": pitch >= min_pitch - 0.01,
        "people": len(g.slots),
    }

    plan = RenderPlan(
        canvas=Canvas(W, H, style.get("canvas.background", "#FBF8F2"), "circle"),
        meta=PlanMeta(engine="radial_rings", style=style.get("id", ""),
                      people=len(g.slots), generations=g.max_gen + 1,
                      year_min=int(g.year_min), year_max=int(g.year_max),
                      warnings=list(g.warnings)))
    plan.meta.extra["subrows"] = {str(k): v for k, v in ring_k.items()}
    plan.meta.extra["auto_size_mm"] = round(W, 1)
    plan.meta.extra["fit"] = fit
    if not fit["fits"]:
        plan.meta.warnings.append(
            f"This needs about {fit['required_mm']:.0f} mm across to breathe "
            f"properly and the panel is {fit['panel_mm']:.0f} mm. The rings "
            f"have been squeezed by {fit['shortfall_mm']:.0f} mm. Show fewer "
            f"generations, shorten the labels, or use a bigger panel.")
    elif not fit["pitch_ok"]:
        plan.meta.warnings.append(
            f"Rings are {fit['ring_pitch_mm']:.0f} mm apart, closer than the "
            f"{fit['min_pitch_mm']:.0f} mm you asked for.")

    # ---- 4. sub-row assignment: alternate around each ring ---------------
    row: dict[str, int] = {}
    for gen, pids in g.by_gen.items():
        k = ring_k[gen]
        for i, pid in enumerate(sorted(pids, key=lambda p: g.slots[p].tc)):
            row[pid] = i % k
    plan_rows = row

    # Optional clustering: squeeze each sibling group toward its own centre
    # so that families read as groups with visible air between them, rather
    # than as one undifferentiated chain of names around the ring.
    centre = {sl.pid: sl.tc for sl in g}
    cluster = float(style.get("layout.sibling_gap_frac", 0.0) or 0.0)
    if cluster > 0:
        for sl in g:
            kids = [c for c in graph.children(sl.pid) if c in centre]
            if len(kids) < 2:
                continue
            vals = [centre[c] for c in kids]
            mid = (min(vals) + max(vals)) / 2
            for c in kids:
                centre[c] = mid + (centre[c] - mid) * (1.0 - min(0.6, cluster))

    pos: dict[str, tuple[float, float]] = {}     # pid -> (theta, node radius)
    for sl in g:
        t = t_start + centre[sl.pid] * sweep
        pos[sl.pid] = (t, ring_r[sl.gen] + row[sl.pid] * step + branch)

    _generation_guides(plan, g, style, cx, cy, ring_r, R)

    col = style.get("connectors.colour", "#2A2622")

    # ---- 5. spokes, sibling arcs, branches -------------------------------
    #
    # ARCS ARE PER UNION, NEVER PER PERSON. This is the whole reason the
    # database links a child to a union rather than to a parent. One arc
    # drawn across "his children" would silently state that two marriages
    # were a single family of eight.
    #
    # A parent with more than one family is drawn ONCE PER FAMILY, each
    # instance sitting directly above its own children, and the instances
    # joined by a dotted arc meaning "the same person". A father who had
    # children by two women therefore appears twice, each time at the head of
    # the right family, with the dotted arc showing they are one man.
    repeat = style.get("layout.repeat_parents", False)
    dash_half = style.get("lines.half_dash", "3,2")
    dash_same = style.get("lines.same_person_dash", "0.8,1.6")
    dash_unknown = style.get("lines.unknown_dash", "0.8,1.6")

    instances: dict[str, list[tuple[str, float]]] = {}   # pid -> [(uid, theta)]
    seen_children: set[str] = set()

    for uid, union in graph.unions.items():
        kids = [c for c in union.children if c in pos]
        if not kids:
            continue
        parents = [pp for pp in union.partners if pp in pos]
        if not parents:
            continue
        seen_children.update(kids)
        angles = sorted(pos[c][0] for c in kids)
        gen_k = g.slots[kids[0]].gen
        r_bar = ring_r[gen_k]
        r_par = min(pos[pp][1] for pp in parents)

        # this family's head sits directly above this family
        t_anchor = (angles[0] + angles[-1]) / 2
        if not repeat or all(len(graph.people[pp].unions) <= 1 for pp in parents):
            t_anchor = sum(pos[pp][0] for pp in parents) / len(parents)
        for pp in parents:
            instances.setdefault(pp, []).append((uid, t_anchor))

        # WHAT THE DASH MEANS: half-siblinghood, not a missing partner.
        #
        # If a father had children by two women, both mothers may well be
        # recorded -- you simply do not follow the second woman's family any
        # further. The half-relationship is the fact worth drawing, and it
        # exists whether or not she is on the chart. Dashing on "partner
        # missing" instead would mean that entering her name silently turned
        # your half-sister into a full sister.
        half = _is_half_family(graph, uid, union, s.subject_id)
        single = len(union.partners) < 2
        informal = union.type not in ("marriage", "civil_partnership")

        plan.add(Element(kind="path", layer="ENGRAVE",
                         d=G.polyline([G.polar(cx, cy, r_par, t_anchor),
                                       G.polar(cx, cy, r_bar, t_anchor)]),
                         stroke=col, stroke_width=lw, fill="none",
                         dash=dash_half if half else None,
                         person_id=parents[0], union_id=uid,
                         role="connector", z=10))
        if angles[-1] - angles[0] > 1e-6:
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=G.arc_path(cx, cy, r_bar, angles[0], angles[-1]),
                             stroke=col, stroke_width=lw, fill="none",
                             dash=dash_half if (half or informal) else None,
                             person_id=parents[0], union_id=uid,
                             role="ring", z=11))
        if single and style.get("lines.mark_unknown_partner", True):
            off = style.get("lines.unknown_offset_mm", 5.0) / max(r_par, 1e-3)
            xu, yu = G.polar(cx, cy, r_par, t_anchor + off)
            plan.add(Element(kind="circle", layer="ENGRAVE", x=xu, y=yu,
                             r=lw * 1.7, fill="none", stroke=col,
                             stroke_width=lw * 0.8, dash=dash_unknown,
                             union_id=uid, role="unknown_partner", z=14))
        for c in kids:
            tc, rc = pos[c]
            pr = graph.people[c]
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=G.polyline([G.polar(cx, cy, r_bar, tc),
                                           G.polar(cx, cy, rc, tc)]),
                             stroke=colour_for(pr, g.slots[c], style, graph),
                             stroke_width=lw, dash=dash_for(pr, style),
                             opacity=opacity_for(pr), fill="none",
                             person_id=c, union_id=uid, role="station", z=12))

    # any child whose union fell outside the chart still needs its branch
    for sl in g:
        if sl.pid in seen_children or not sl.parent or sl.parent not in pos:
            continue
        tc, rc = pos[sl.pid]
        tp, rp = pos[sl.parent]
        pr = graph.people[sl.pid]
        plan.add(Element(kind="path", layer="ENGRAVE",
                         d=G.polyline([G.polar(cx, cy, rp, tp),
                                       G.polar(cx, cy, ring_r[sl.gen], tp)]),
                         stroke=col, stroke_width=lw, fill="none",
                         person_id=sl.parent, role="connector", z=10))
        plan.add(Element(kind="path", layer="ENGRAVE",
                         d=G.polyline([G.polar(cx, cy, ring_r[sl.gen], tc),
                                       G.polar(cx, cy, rc, tc)]),
                         stroke=colour_for(pr, g.slots[sl.pid], style, graph),
                         stroke_width=lw, fill="none", person_id=sl.pid,
                         role="station", z=12))

    # ---- 5b. repeated parents, joined by a dotted "same person" arc ------
    repeats: dict[str, float] = {}
    repeat_pids: set[str] = set()
    if repeat:
        for pid, items in instances.items():
            if len(items) < 2:
                continue
            repeat_pids.add(pid)
            t_home, r_p = pos[pid]
            ts = sorted(t for _, t in items)
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=G.short_arc(cx, cy, r_p, ts[0], ts[-1]),
                             stroke=style.get("lines.same_person_colour", col),
                             stroke_width=lw * 0.8, fill="none", dash=dash_same,
                             person_id=pid, role="same_person", z=9))
            for uid, t in items:
                repeats[f"{pid}|{uid}"] = t
                x, y = G.polar(cx, cy, r_p, t)
                plan.add(Element(kind="path", layer="ENGRAVE",
                                 d=G.polyline([G.polar(cx, cy, r_p - branch, t),
                                               G.polar(cx, cy, r_p, t)]),
                                 stroke=col, stroke_width=lw, fill="none",
                                 dash=dash_same, person_id=pid,
                                 union_id=uid, role="repeat", z=12))

    # ---- 5b2. half-sibling ties ------------------------------------------
    #
    # The father is drawn once, so his two families hang from one node. What
    # is still missing is the relationship BETWEEN those families, and that
    # is the fact the chart is being asked to show.
    #
    # Each family keeps its own solid arc; the gap between them is bridged by
    # a dashed arc at the same radius. The three read as one rail with a
    # dashed section: continuous, because they share a parent; broken,
    # because they do not share both.
    if style.get("lines.half_sibling_tie", True):
        for pid, person in graph.people.items():
            if pid not in pos:
                continue
            groups = []
            for uid in person.unions:
                kids = [c for c in graph.unions[uid].children if c in pos]
                if not kids:
                    continue
                angs = sorted(pos[c][0] for c in kids)
                groups.append((angs[0], angs[-1], ring_r[g.slots[kids[0]].gen],
                               uid))
            if len(groups) < 2:
                continue
            groups.sort()
            for (a0, a1, r1, u1), (b0, b1, r2, u2) in zip(groups, groups[1:]):
                if abs(r1 - r2) > 0.5:
                    continue
                # Bridge the gap between the two sibling groups. Where the
                # groups interleave rather than sit apart, join their centres
                # on a slightly inset arc so the half-relationship is still
                # stated rather than silently dropped.
                if b0 > a1:
                    t_a, t_b, rr = a1, b0, r1
                else:
                    t_a, t_b = (a0 + a1) / 2, (b0 + b1) / 2
                    rr = r1 - style.get("lines.half_tie_inset_mm", 2.4)
                if abs(t_b - t_a) < 1e-6 or rr <= 0:
                    continue
                plan.add(Element(kind="path", layer="ENGRAVE",
                                 d=G.short_arc(cx, cy, rr, t_a, t_b),
                                 stroke=style.get("lines.half_tie_colour", col),
                                 stroke_width=lw,
                                 dash=style.get("lines.half_dash", "3,2"),
                                 fill="none", person_id=pid, union_id=u2,
                                 role="half_tie", z=11))

    # ---- 5c. marriage ties -----------------------------------------------
    if style.get("marriage.show", True):
        mcol = style.get("marriage.colour", col)
        mw = style.get("marriage.width_mm", lw * 1.6)
        inset = style.get("marriage.inset_mm", 1.2)
        for uid, union in graph.unions.items():
            ps = [pp for pp in union.partners if pp in pos]
            if len(ps) < 2:
                continue
            ts = sorted(pos[pp][0] for pp in ps)
            rr = min(pos[pp][1] for pp in ps) - inset
            if ts[-1] - ts[0] < 1e-6 or rr <= 0:
                continue
            informal = union.type not in ("marriage", "civil_partnership")
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=G.short_arc(cx, cy, rr, ts[0], ts[-1]),
                             stroke=mcol, stroke_width=mw, fill="none",
                             dash=style.get("marriage.informal_dash", "1.6,1.4")
                             if informal else None,
                             union_id=uid, person_id=ps[0],
                             role="marriage", z=13))

    # every person carries a mark of their own, spouses included, so that a
    # name never floats with nothing attaching it to the structure
    marked = {e.person_id for e in plan.elements
              if e.role in ("station", "repeat") and e.person_id}
    for sl in g:
        if sl.pid in marked or sl.pid in repeat_pids:
            continue
        t, rn = pos[sl.pid]
        pr = graph.people[sl.pid]
        plan.add(Element(kind="path", layer="ENGRAVE",
                         d=G.polyline([G.polar(cx, cy, rn - branch * 0.6, t),
                                       G.polar(cx, cy, rn, t)]),
                         stroke=colour_for(pr, sl, style, graph),
                         stroke_width=lw, dash=dash_for(pr, style),
                         fill="none", person_id=sl.pid, role="station", z=12))

    # ---- 5d. where the lines end -----------------------------------------
    #
    # Two very different facts look identical on most charts: "this line is
    # not mine to follow" and "I have not got any further yet". Marking them
    # apart turns the chart into a research map -- every open cap is a
    # question still worth asking.
    if style.get("lines.mark_line_ends", True):
        cap = style.get("lines.cap_mm", 2.2)
        for sl in g:
            if graph.parents(sl.pid, primary_only=False):
                continue                      # ancestry recorded; not an end
            t, rn = pos[sl.pid]
            person = graph.people[sl.pid]
            deliberate = ("line_stops_here" in person.tags
                          or bool(graph.partners(sl.pid)) and sl.pid not in g.roots)
            r_cap = rn - branch * 0.9
            a, b = G.polar(cx, cy, r_cap, t - cap / (2 * max(r_cap, 1e-3))), \
                   G.polar(cx, cy, r_cap, t + cap / (2 * max(r_cap, 1e-3)))
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=G.arc_path(cx, cy, r_cap, t - cap / (2 * max(r_cap, 1e-3)),
                                          t + cap / (2 * max(r_cap, 1e-3))),
                             stroke=col, stroke_width=lw,
                             dash=None if deliberate
                             else style.get("lines.frontier_dash", "0.6,1.2"),
                             fill="none", person_id=sl.pid,
                             role="line_end" if deliberate else "frontier",
                             z=12))

    for pid in g.roots:                          # the innermost ancestors
        if pid not in pos:
            continue
        t, rn = pos[pid]
        plan.add(Element(kind="path", layer="ENGRAVE",
                         d=G.polyline([G.polar(cx, cy, ring_r[0], t),
                                       G.polar(cx, cy, rn, t)]),
                         stroke=col, stroke_width=lw * 1.5, fill="none",
                         person_id=pid, role="station", z=12))

    # ---- 6. the Thread ---------------------------------------------------
    thr = _thread_set(graph, s) if style.get("thread.enabled", True) else set()
    if thr:
        tcol = style.get("thread.colour", "#9B3A2E")
        tw = style.get("thread.stroke_width_mm", 1.2)
        layer = style.get("thread.layer", "ENGRAVE_DEEP")
        for sl in g:
            if sl.pid not in thr or not sl.parent or sl.parent not in thr:
                continue
            tp, rp = pos[sl.parent]
            tc, rc = pos[sl.pid]
            r_bar = ring_r[sl.gen]
            pts = [G.polar(cx, cy, rp, tp), G.polar(cx, cy, r_bar, tp)]
            steps = max(2, int(abs(tc - tp) / 0.02))
            pts += [G.polar(cx, cy, r_bar, tp + (tc - tp) * i / steps)
                    for i in range(1, steps + 1)]
            pts.append(G.polar(cx, cy, rc, tc))
            plan.add(Element(kind="path", layer=layer, d=G.polyline(pts),
                             stroke=tcol, stroke_width=tw, fill="none",
                             person_id=sl.pid, role="thread", z=80))

    # ---- 7. labels, aligned at the end of every branch -------------------
    _labels_rings(plan, graph, g, style, cx, cy, pos, gap, sweep,
                  repeats=repeats, repeat_pids=repeat_pids)
    _line_key(plan, style, W, H, margin, lw, col)
    add_border(plan, style, cx, cy, R + margin * 0.4)
    add_title(plan, style, cx, cy)
    return plan


def _line_key(plan, style, W, H, margin, lw, col):
    """A key to the linework.

    Dashes only mean something if the reader is told what they mean, and a
    chart that outlives its maker has to explain itself. Six lines, bottom
    left, small.
    """
    if not style.get("ornament.line_key", True):
        return
    size = style.get("type.size_mm", 2.8) * 0.82
    x = margin
    y = H - margin - 8 * size * 2.0
    rows = [
        ("solid", None, lw, "Descent, and a recorded marriage"),
        ("dash", style.get("marriage.informal_dash", "1.6,1.4"), lw,
         "Unmarried or unrecorded union"),
        ("dash", style.get("lines.half_dash", "3,2"), lw,
         "Joins half-siblings \u2014 one parent shared"),
        ("ring", None, lw * 0.8, "Parent not recorded"),
        ("solid", None, lw, "Line ends here by choice \u2014 not my family"),
        ("dot", style.get("lines.frontier_dash", "0.6,1.2"), lw,
         "Line ends here for now \u2014 still to research"),
        ("fine", "2,1.4", lw, "Uncertain \u2014 not yet proved"),
    ]
    for i, (kind, dash, w, caption) in enumerate(rows):
        yy = y + i * size * 2.0
        if kind == "ring":
            plan.add(Element(kind="circle", layer="ENGRAVE", x=x + 4, y=yy,
                             r=lw * 1.7, fill="none", stroke=col,
                             stroke_width=lw * 0.8, dash=dash or "0.8,1.6",
                             role="legend", z=70))
        else:
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=G.polyline([(x, yy), (x + 9, yy)]), stroke=col,
                             stroke_width=w, dash=dash, fill="none",
                             role="legend", z=70))
        add_label(plan, caption, x + 12, yy, style, size=size,
                  anchor="start", colour=style.get("type.colour"), z=70,
                  role="legend")


def _is_half_family(graph, uid, union, subject_id) -> bool:
    """Are the children of this union half-siblings to the main family?

    True when a parent of this union also had children by someone else. The
    union the SUBJECT belongs to is the reference point and stays solid --
    your own brothers and sisters are not the exception, they are the
    baseline. Where the subject is not involved, the earliest union is
    treated as the main one.
    """
    for pid in union.partners:
        person = graph.people.get(pid)
        if not person:
            continue
        others = [u for u in person.unions
                  if u != uid and graph.unions[u].children]
        if not others:
            continue
        siblings_of_subject = subject_id and subject_id in union.children
        if siblings_of_subject:
            return False                       # this is the reference family
        if subject_id and any(subject_id in graph.unions[u].children
                              for u in others):
            return True                        # the subject is in the other one
        earliest = sorted([uid] + others,
                          key=lambda u: min(
                              (graph.people[c].birth.sort_value or 9e9)
                              for c in graph.unions[u].children) or 9e9)
        return uid != earliest[0]
    return False


def _subrows(g, pids, radius: float, sweep: float, need_mm: float,
             max_rows: int = MAX_SUBROWS, mode: str = "auto") -> int:
    """How many alternating rows this ring needs.

    Judged on the TIGHTEST real spacing, not the average. A ring can be
    half empty and still unreadable if one family had ten children, and
    that pair of facts is exactly the case the stagger exists for. So look
    at the 20th-percentile gap between neighbours: if a fifth of the ring
    is tighter than a name is tall, split it into two rows; if it is very
    much tighter, three.
    """
    if mode == "never":
        return 1
    if mode == "always":
        return max(2, min(max_rows, 2))
    if len(pids) < 3 or radius <= 0:
        return 1
    angles = sorted(g.slots[p].tc for p in pids)
    gaps = [(b - a) * sweep * radius for a, b in zip(angles, angles[1:])]
    gaps = [x for x in gaps if x > 1e-9]
    if not gaps:
        return 1
    gaps.sort()
    tight = gaps[max(0, int(len(gaps) * 0.2))]      # 20th percentile, in mm
    if tight <= 0:
        return max_rows
    return max(1, min(max_rows, math.ceil(need_mm * SAFETY / tight)))


def _thread_marks(plan, graph, g, style, cx, cy, pos, thr):
    """Ring the people on the Thread. Used by the designs whose connectors
    are too light to carry a heavier overlay."""
    if not thr:
        return
    col = style.get("thread.colour", "#A3392B")
    w = style.get("thread.stroke_width_mm", 0.8)
    for pid in thr:
        if pid not in pos:
            continue
        t, r = pos[pid][0], pos[pid][1]
        x, y = G.polar(cx, cy, r, t)
        plan.add(Element(kind="circle",
                         layer=style.get("thread.layer", "ENGRAVE_DEEP"),
                         x=x, y=y, r=w * 2.6, fill="none", stroke=col,
                         stroke_width=w, person_id=pid, role="thread", z=85))


def _generation_guides(plan, g, style, cx, cy, ring_r, R):
    """A hairline at the base of each ring. Faint on purpose: it should
    organise the eye without competing with the family."""
    if not style.get("ornament.time_rings", True):
        return
    col = style.get("ornament.time_ring_colour", "#D8D0C0")
    for gen, r in sorted(ring_r.items()):
        if gen == 0:
            continue
        plan.add(Element(kind="path", layer="GUIDE",
                         d=G.circle_path(cx, cy, r), stroke=col,
                         stroke_width=0.2, fill="none", dash="1,2.5",
                         role="tick", z=1))


def _labels_rings(plan, graph, g, style, cx, cy, pos, gap, sweep,
                  repeats=None, repeat_pids=None):
    """Set every name at the end of its own branch.

    Same-row neighbours share a radius, so a ring reads as a tidy column of
    names. Text is never set upside down: on the lower half of the disc it is
    turned through 180 degrees and anchored at its far end, which keeps it
    reading left to right while occupying exactly the same space.
    """
    if not style.get("labels.show", True):
        return
    orientation = style.get("labels.orientation", "auto")
    flip_bottom = style.get("labels.flip_bottom", True)
    placer = PolarLabelPlacer(min_gap_mm=style.get("labels.min_gap_mm", 0.5))
    counts = {gen: max(1, len(pids)) for gen, pids in g.by_gen.items()}

    # Only skip the main pass for people the repeat pass will actually name.
    # Skipping them unconditionally lost their label entirely when the repeat
    # placement failed.
    skip = {p for p in (repeat_pids or set())
            if any(k.split("|")[0] == p for k in (repeats or {}))}
    for sl in sorted(g, key=lambda s2: (s2.gen, s2.order)):
        if sl.pid in skip:
            continue            # named once per family, in the repeat pass
        lines = label_lines(style, graph.people[sl.pid], sl.gen, sl.order)
        if not lines:
            continue
        t, r = pos[sl.pid]
        arc = sweep * r / counts.get(sl.gen, 1)
        flip = G.text_is_upside_down(t) if flip_bottom else False
        place_radial_label(plan, placer, graph.people[sl.pid], lines, t,
                           r + gap, cx, cy, style, flip=flip,
                           orientation=orientation, arc_available=arc)

    # A repeated parent is named again above their other family, set lighter
    # so it reads as a cross-reference rather than a second person.
    first_seen: set[str] = set()
    named: set[str] = set()
    for key, t in (repeats or {}).items():
        pid = key.split("|")[0]
        if pid not in pos:
            continue
        person = graph.people[pid]
        # the first instance is the person proper; later ones are lighter,
        # so they read as a cross-reference rather than as a second person
        primary = pid not in first_seen
        first_seen.add(pid)
        base = style.get("type.size_mm", 2.8)
        size = base if primary else base * style.get("lines.repeat_scale", 0.82)
        colour = (style.get("type.colour", "#22201D") if primary
                  else style.get("lines.repeat_colour", "#8A8073"))
        lines = [(person.short_name, size, colour)]
        if place_radial_label(plan, placer, person, lines, t,
                              pos[pid][1] + gap, cx, cy, style,
                              flip=G.text_is_upside_down(t),
                              orientation="radial", arc_available=0):
            named.add(pid)

    # if every instance of a repeated parent failed to place, name them once
    # at their own position rather than leaving them anonymous
    for pid in (repeat_pids or set()):
        if pid in named or pid not in pos:
            continue
        t, r = pos[pid]
        person = graph.people[pid]
        place_radial_label(plan, placer, person,
                           [(person.short_name, style.get("type.size_mm", 2.8),
                             style.get("type.colour", "#22201D"))],
                           t, r + gap, cx, cy, style,
                           flip=G.text_is_upside_down(t),
                           orientation="radial", arc_available=0)

    plan.meta.demotions = placer.demoted
    plan.meta.extra["labels_hidden"] = placer.dropped
    if placer.dropped:
        plan.meta.warnings.append(
            f"{placer.dropped} names still did not fit. Show fewer "
            f"generations, drop a label line, or use a larger panel.")


@register("radial_organic", "Radial Roots", "radial",
          "Tapering curves that thicken toward the centre like a root system. "
          "People are dots; the structure does the talking.",
          good_for="Elegant posters; a delicate, natural look.",
          laser="good")
def radial_organic(graph, s, style) -> RenderPlan:
    plan, g, cx, cy, r0, R = _frame(graph, s, style)
    t_start, sweep = _angles(style)
    thr = _thread_set(graph, s) if style.get("thread.enabled", True) else set()
    widths = ring_widths([len(g.by_gen.get(i, [])) for i in range(g.max_gen + 1)],
                         r0, R, style.get("layout.min_ring_mm", 8))
    _time_rings(plan, g, style, cx, cy, r0, R)

    pos = {sl.pid: (t_start + sl.tc * sweep,
                    _radius_of(sl, g, style, r0, R, widths)) for sl in g}
    base_w = style.get("connectors.width_mm", 0.5)
    maxw = sum(sl.weight for sl in g if sl.parent is None) or 1
    for sl in g:
        if not sl.parent or sl.parent not in pos:
            continue
        tp, rp = pos[sl.parent]
        tc, rc = pos[sl.pid]
        w = base_w * (0.35 + 2.4 * (sl.weight / maxw) ** 0.42)
        p = graph.people[sl.pid]
        plan.add(Element(kind="path", layer="ENGRAVE",
                         d=G.bezier_polar(cx, cy, rp, tp, rc, tc, 0.6),
                         stroke=colour_for(p, sl, style, graph),
                         stroke_width=max(0.18, w), fill="none",
                         dash=dash_for(p, style), opacity=opacity_for(p),
                         person_id=sl.pid, role="connector", z=10))
    dot = style.get("nodes.size_mm", 1.1)
    for sl in g:
        p = graph.people[sl.pid]
        t, r = pos[sl.pid]
        x, y = G.polar(cx, cy, r, t)
        alive = p.death_year is None and (p.living is not False)
        plan.add(Element(kind="circle", layer="ENGRAVE", x=x, y=y,
                         r=dot * (1.5 if alive else 1.0),
                         fill=style.get("nodes.fill", "#22201D") if not alive else "none",
                         stroke=style.get("nodes.stroke", "#22201D"),
                         stroke_width=style.get("nodes.stroke_width_mm", 0.3),
                         person_id=sl.pid, role="station", z=40))
    _labels_radial(plan, graph, g, style, cx, cy,
                   {k: (v[0], v[1] - 1.5) for k, v in pos.items()}, 3, sweep)
    _thread_marks(plan, graph, g, style, cx, cy, pos, thr)
    add_border(plan, style, cx, cy, R + 6)
    add_title(plan, style, cx, cy)
    return plan


# ============================================================ 4. LIFELINE ===
@register("radial_lifeline", "Radial Lifelines", "radial",
          "Each person is a bar running from the year they were born to the "
          "year they died. Bar length IS lifespan.",
          good_for="Seeing infant mortality, epidemics and long-lived "
                   "matriarchs at a glance. The most information-dense design.",
          laser="excellent")
def radial_lifeline(graph, s, style) -> RenderPlan:
    plan, g, cx, cy, r0, R = _frame(graph, s, style)
    t_start, sweep = _angles(style)
    pad = G.rad(style.get("layout.cell_pad_deg", 0.1))
    gamma = style.get("layout.radius_gamma", 0.5)
    thr = _thread_set(graph, s) if style.get("thread.enabled", True) else set()
    now = float(plan.meta.year_max or 2025)
    _time_rings(plan, g, style, cx, cy, r0, R)

    pos = {}
    for sl in g:
        p = graph.people[sl.pid]
        t0 = t_start + sl.t0 * sweep + pad
        t1 = t_start + sl.t1 * sweep - pad
        if t1 <= t0:
            t1 = t0 + 2e-4
        b = sl.year or g.year_min
        d = sl.death_year or (now if (p.living is not False) else b + 1)
        ri = r_time(b, g.year_min, g.year_max, r0, R, gamma)
        ro = max(ri + 1.0, r_time(d, g.year_min, g.year_max, r0, R, gamma))
        pos[sl.pid] = ((t0 + t1) / 2, ri, ro)
        alive = sl.death_year is None and p.living is not False
        plan.add(Element(kind="path", layer="ENGRAVE",
                         d=G.annular_sector(cx, cy, ri, ro, t0, t1),
                         stroke=colour_for(p, sl, style, graph),
                         fill=style.get("cells.fill", "none"),
                         stroke_width=style.get("cells.stroke_width_mm", 0.35),
                         dash="1.5,1.5" if alive else dash_for(p, style),
                         opacity=opacity_for(p), person_id=sl.pid,
                         role="cell", z=20))
    for sl in g:
        if not sl.parent or sl.parent not in pos:
            continue
        tc, ri, _ = pos[sl.pid]
        tp, rpi, rpo = pos[sl.parent]
        rp = min(rpo, max(rpi, ri))
        plan.add(Element(kind="path", layer="ENGRAVE",
                         d=G.rounded_polyline(
                             G.elbow_polar(cx, cy, rp, tp, ri, tc, mid=0.5),
                             style.get("connectors.corner_radius_mm", 1.5)),
                         stroke=style.get("connectors.colour", "#22201D"),
                         stroke_width=style.get("connectors.width_mm", 0.3),
                         fill="none", opacity=0.75, person_id=sl.pid,
                         role="connector", z=10))
    if style.get("labels.show", True):
        placer = LabelPlacer(min_gap_mm=0.4)
        for sl in sorted(g, key=lambda s2: (s2.gen, s2.order)):
            p = graph.people[sl.pid]
            t, ri, ro = pos[sl.pid]
            txt = fill_template(template_for(style, sl.gen), p, sl.order)
            rot = G.deg(t) + (180 if G.text_is_upside_down(t) else 0)
            x, y = G.polar(cx, cy, (ri + ro) / 2, t)
            place_label(plan, placer, p, txt.replace("\n", " "), x, y, style,
                        rotate=rot, size=style.get("type.size_mm", 2.6))
        plan.meta.demotions = placer.demoted
        plan.meta.extra["labels_hidden"] = placer.dropped
    _thread_marks(plan, graph, g, style, cx, cy,
                  {k: (v[0], v[1]) for k, v in pos.items()}, thr)
    add_border(plan, style, cx, cy, R + 6)
    add_title(plan, style, cx, cy)
    return plan


# ============================================================== 5. SPIRAL ===
@register("radial_spiral", "Time Spiral", "radial",
          "One continuous Archimedean spiral of years. Everyone sits on the "
          "spiral at the moment they were born, with branches linking them.",
          good_for="Long thin lineages; emphasising time over structure.",
          laser="good")
def radial_spiral(graph, s, style) -> RenderPlan:
    plan, g, cx, cy, r0, R = _frame(graph, s, style)
    turns = style.get("layout.spiral_turns", 4.0)
    span = max(1.0, g.year_max - g.year_min)

    def spiral_pt(year: float, offset: float = 0.0):
        f = (year - g.year_min) / span
        th = G.rad(style.get("layout.start_angle_deg", -90)) + f * turns * G.TAU
        r = r0 + f * (R - r0) + offset
        return G.polar(cx, cy, r, th), th, r

    steps = 600
    pts = [spiral_pt(g.year_min + span * i / steps)[0] for i in range(steps + 1)]
    plan.add(Element(kind="path", layer="ENGRAVE", d=G.polyline(pts),
                     stroke=style.get("ornament.time_ring_colour", "#C9C0B0"),
                     stroke_width=0.35, fill="none", role="tick", z=2))
    for yr in nice_ticks(g.year_min, g.year_max, 12):
        if g.year_min <= yr <= g.year_max:
            (x, y), th, r = spiral_pt(yr)
            add_label(plan, str(yr), x, y - 2.2, style,
                      size=style.get("type.size_mm", 3) * 0.7,
                      colour=style.get("ornament.time_ring_colour"), z=3)

    _spiral_placer = LabelPlacer(min_gap_mm=0.5)
    pos = {}
    for sl in g:
        lane = ((sl.order % 5) - 2) * style.get("layout.spiral_lane_mm", 3.2)
        (x, y), th, r = spiral_pt(sl.year or g.year_min, lane)
        pos[sl.pid] = (x, y, th)
    for sl in g:
        if not sl.parent or sl.parent not in pos:
            continue
        x0, y0, _ = pos[sl.parent]
        x1, y1, _ = pos[sl.pid]
        plan.add(Element(kind="path", layer="ENGRAVE",
                         d=G.bezier_xy((x0, y0), (x1, y1), vertical=False,
                                       tension=0.42),
                         stroke=colour_for(graph.people[sl.pid], sl, style, graph),
                         stroke_width=style.get("connectors.width_mm", 0.35),
                         fill="none", opacity=0.8, person_id=sl.pid,
                         role="connector", z=10))
    for sl in g:
        p = graph.people[sl.pid]
        x, y, th = pos[sl.pid]
        plan.add(Element(kind="circle", layer="ENGRAVE", x=x, y=y,
                         r=style.get("nodes.size_mm", 1.0), fill="#FBF8F2",
                         stroke=style.get("nodes.stroke", "#22201D"),
                         stroke_width=0.3, person_id=sl.pid, role="station", z=40))
        if style.get("labels.show", True):
            txt = fill_template(template_for(style, sl.gen), p, sl.order)
            rot = G.deg(th) + (180 if G.text_is_upside_down(th) else 0)
            place_label(plan, _spiral_placer, p, txt.replace("\n", " "), x, y,
                        style, rotate=rot, size=style.get("type.size_mm", 2.4))
    add_title(plan, style, cx, cy)
    return plan


# ============================================================ 6. HALF FAN ===
@register("fan_180", "Half Fan", "radial",
          "The traditional pedigree fan: you at the centre, your ancestors "
          "spreading outward over a half circle.",
          good_for="A mantelpiece. Fits a conventional frame, and every "
                   "generation doubles neatly.",
          laser="excellent")
def fan_180(graph, s, style) -> RenderPlan:
    """Ancestors, not descendants -- the one design here that runs backwards.

    Positions come from Ahnentafel numbering, so a missing grandparent leaves
    a visible hole exactly where they belong. That hole is the point: it is
    the next thing to go and research.
    """
    from .linear import ancestor_slots
    subject = s.subject_id or (graph.apexes() or [None])[0]
    if not subject:
        return RenderPlan(meta=PlanMeta(engine="fan_180",
                                        warnings=["Choose whose chart this is first."]))
    slots = ancestor_slots(graph, subject, s.max_generations or 6)
    max_gen = max((gg for gg, _ in slots.values()), default=0)

    sweep = G.rad(style.get("layout.sweep_deg", 180))
    t_start = G.rad(style.get("layout.start_angle_deg", 180))
    r0 = style.get("layout.inner_radius_mm", 45)
    ring = style.get("layout.min_ring_pitch_mm", 30)
    margin = style.get("canvas.margin_mm", 24)
    R = r0 + (max_gen + 1) * ring
    W = 2 * (R + margin)
    H = R + 2 * margin if sweep <= G.rad(190) else W
    cx, cy = W / 2, H - margin - r0 * 0.2

    plan = RenderPlan(
        canvas=Canvas(W, H, style.get("canvas.background", "#FBF8F2"), "rect"),
        meta=PlanMeta(engine="fan_180", style=style.get("id", ""),
                      people=len(slots), generations=max_gen + 1))
    lw = style.get("connectors.width_mm", 0.45)
    col = style.get("connectors.colour", "#22201D")
    pad = G.rad(style.get("layout.cell_pad_deg", 0.4))

    placer = PolarLabelPlacer(min_gap_mm=style.get("labels.min_gap_mm", 0.5))
    for pid, (gen, frac) in sorted(slots.items(), key=lambda kv: kv[1]):
        n = 2 ** gen
        t0 = t_start + (frac - 0.5 / n) * sweep + pad
        t1 = t_start + (frac + 0.5 / n) * sweep - pad
        ri = r0 + gen * ring
        person = graph.people[pid]
        plan.add(Element(kind="path", layer="ENGRAVE",
                         d=G.annular_sector(cx, cy, ri, ri + ring * 0.86, t0, t1),
                         stroke=colour_for(person, type("S", (), {
                             "gen": gen, "lineage": "", "pid": pid})(),
                             style, graph),
                         fill=style.get("cells.fill", "none"),
                         stroke_width=lw, dash=dash_for(person, style),
                         opacity=opacity_for(person), person_id=pid,
                         role="cell", z=20))
        tc = (t0 + t1) / 2
        lines = label_lines(style, person, gen, 0)
        if lines:
            place_radial_label(plan, placer, person, lines, tc,
                               ri + ring * 0.12, cx, cy, style,
                               flip=G.text_is_upside_down(tc),
                               orientation="radial",
                               arc_available=abs(t1 - t0) * ri)
    plan.meta.extra["labels_hidden"] = placer.dropped
    add_title(plan, style, cx, margin)
    return plan
