"""Non-radial design family.

  metro_map        -- classic octilinear transit diagram (Beck, 1933)
  timeline_lanes   -- horizontal life bars against a year axis
  dendrogram       -- traditional left-to-right tree
  icicle           -- stacked proportional bands
  arc_diagram      -- one baseline of people, relationships as arcs
  circle_pack      -- families nested inside families

Same Grid, different world. Nothing here knows about the database.
"""
from __future__ import annotations

import math
from typing import Optional

from .. import geometry as G
from ..base import Grid, LayoutSettings, build_grid
from ..common import (LabelPlacer, add_label, add_title, colour_for,
                      dash_for, est_text_width, fill_template, opacity_for,
                      place_label, template_for)
from ..plan import Canvas, Element, PlanMeta, RenderPlan
from ..registry import register
from ..scales import nice_ticks, x_time


def _frame(graph, s, style, default_w=1189.0, default_h=841.0):
    # A wide design on a square page is cramped and ugly. Use the design's
    # own proportions unless the style actually asked for something else.
    W = style.get("canvas.width_mm") if style.chose("canvas.width_mm") else default_w
    H = style.get("canvas.height_mm") if style.chose("canvas.height_mm") else default_h
    m = style.get("canvas.margin_mm", 24)
    g = build_grid(graph, s)
    plan = RenderPlan(
        canvas=Canvas(W, H, style.get("canvas.background", "#FBF8F2"), "rect"),
        meta=PlanMeta(engine=s.engine, style=style.get("id", ""),
                      people=len(g.slots), generations=g.max_gen + 1,
                      year_min=int(g.year_min), year_max=int(g.year_max),
                      warnings=list(g.warnings)))
    return plan, g, W, H, m


def _thread_set(graph, s):
    from ...graph.thread import thread
    return thread(graph, s.subject_id).members


# ========================================================== 1. METRO MAP ===
@register("metro_map", "Transit Map", "linear",
          "The classic underground-map treatment: octilinear routes in flat "
          "colour, tick stations, ringed interchanges, horizontal labels.",
          good_for="A wall piece people will actually stand and read. Handles "
                   "many separate families elegantly.",
          laser="good")
def metro_map(graph, s, style) -> RenderPlan:
    plan, g, W, H, m = _frame(graph, s, style)
    lw = style.get("connectors.width_mm", 3.0)
    gapv = style.get("connectors.line_gap_mm", lw * 1.25)
    cr = style.get("connectors.corner_radius_mm", lw * 1.6)
    pal = style.get("colour.palette")
    thr = _thread_set(graph, s) if style.get("thread.enabled", True) else set()

    x0, x1 = m + 30, W - m - 60
    y0, y1 = m + 30, H - m - 30

    # x = time (or generation); y = position on the spread axis, snapped to a
    # grid so that the diagram reads as engineered rather than sprayed
    grid_y = style.get("layout.grid_mm", max(6.0, (y1 - y0) / max(12, len(g.slots) / 3)))
    use_time = style.get("layout.time_scale", True)

    pos: dict[str, tuple[float, float]] = {}
    for sl in g:
        if use_time:
            x = x_time(sl.year or g.year_min, g.year_min, g.year_max, x0, x1)
        else:
            x = x0 + (x1 - x0) * sl.gen / max(1, g.max_gen)
        y = y0 + sl.tc * (y1 - y0)
        y = round(y / grid_y) * grid_y
        pos[sl.pid] = (x, y)
    _resolve_overlaps(pos, grid_y)

    if use_time:
        _year_axis(plan, g, style, x0, x1, y0 - 14, y1 + 8)

    routes = _routes(graph, g)
    used_pairs = set()
    for i, route in enumerate(routes):
        col = pal[i % len(pal)]
        pts: list[tuple[float, float]] = []
        for j, pid in enumerate(route):
            if j == 0:
                pts.append(pos[pid])
            else:
                seg = G.octilinear(pos[route[j - 1]], pos[pid], prefer="diag_first")
                pts.extend(seg[1:])
                used_pairs.add((route[j - 1], pid))
        off = ((i % 3) - 1) * gapv * 0.45
        d = G.rounded_polyline(G.offset_along(pts, off) if off else pts, cr)
        plan.add(Element(kind="path", layer="ENGRAVE", d=d, stroke=col,
                         stroke_width=lw, fill="none", role="connector",
                         line_id=f"route{i}", z=10 + i))

    for sl in g:
        if not sl.parent or (sl.parent, sl.pid) in used_pairs:
            continue
        if sl.parent not in pos:
            continue
        col = pal[g.lineages.index(sl.lineage) % len(pal)] if sl.lineage in g.lineages else pal[0]
        d = G.rounded_polyline(
            G.octilinear(pos[sl.parent], pos[sl.pid], prefer="diag_first"), cr)
        plan.add(Element(kind="path", layer="ENGRAVE", d=d, stroke=col,
                         stroke_width=lw * 0.55, fill="none",
                         person_id=sl.pid, role="connector", z=9))

    # stations
    placer = LabelPlacer(min_gap_mm=style.get("labels.min_gap_mm", 0.8))
    for sl in sorted(g, key=lambda s2: (s2.gen, s2.order)):
        p = graph.people[sl.pid]
        x, y = pos[sl.pid]
        interchange = len(p.unions) > 1 or len(graph.children(sl.pid)) > 1
        if interchange:
            plan.add(Element(kind="circle", layer="ENGRAVE", x=x, y=y,
                             r=lw * 0.75, fill=style.get("nodes.fill", "#FFFFFF"),
                             stroke=style.get("nodes.stroke", "#17171A"),
                             stroke_width=lw * 0.3, person_id=sl.pid,
                             role="interchange", z=40))
        else:
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=G.polyline([(x, y - lw * 0.7), (x, y + lw * 0.7)]),
                             stroke=style.get("nodes.stroke", "#17171A"),
                             stroke_width=lw * 0.32, fill="none",
                             person_id=sl.pid, role="station", z=40))
        if style.get("labels.show", True):
            txt = fill_template(template_for(style, sl.gen), p, sl.order)
            place_label(plan, placer, p, txt.replace("\n", "  "),
                        x + lw * 1.3, y - lw * 1.15, style,
                        size=style.get("type.size_mm", 2.8), anchor="start")
        if sl.pid in thr:
            plan.add(Element(kind="circle", layer=style.get("thread.layer", "ENGRAVE_DEEP"),
                             x=x, y=y, r=lw * 1.35, fill="none",
                             stroke=style.get("thread.colour", "#17171A"),
                             stroke_width=style.get("thread.stroke_width_mm", 0.7),
                             person_id=sl.pid, role="thread", z=85))

    plan.meta.demotions = placer.demoted
    plan.meta.extra["labels_hidden"] = placer.dropped
    if placer.dropped:
        plan.meta.warnings.append(
            f"{placer.dropped} names did not fit. Try a bigger canvas or "
            f"fewer generations.")
    plan.meta.legend = [
        {"label": (graph.people[r[0]].surname or graph.people[r[0]].short_name) + " line",
         "colour": pal[i % len(pal)]} for i, r in enumerate(routes[:14])]
    add_title(plan, style, W / 2, m + 8)
    return plan


def _resolve_overlaps(pos: dict, step: float) -> None:
    """Nudge stations that landed on the same grid cell. Transit maps tolerate
    a lot, but never two stations at one point."""
    seen: dict[tuple[float, float], str] = {}
    for pid in list(pos):
        x, y = pos[pid]
        k = (round(x, 1), round(y, 1))
        n = 0
        while k in seen and n < 40:
            n += 1
            y += step
            k = (round(x, 1), round(y, 1))
        seen[k] = pid
        pos[pid] = (x, y)


def _routes(graph, g: Grid) -> list[list[str]]:
    used: set[str] = set()
    routes: list[list[str]] = []
    order = list(g.roots) + [sl.pid for sl in g]
    for start in order:
        if start in used or start not in g.slots:
            continue
        chain, cur = [start], start
        used.add(start)
        while True:
            kids = [c for c in graph.children(cur) if c in g.slots and c not in used]
            if not kids:
                break
            kids.sort(key=lambda c: -len(graph.descendants(c)))
            chain.append(kids[0])
            used.add(kids[0])
            cur = kids[0]
        if len(chain) > 1:
            routes.append(chain)
    return routes


def _year_axis(plan, g, style, x0, x1, ytop, ybot):
    col = style.get("ornament.time_ring_colour", "#C9C0B0")
    for yr in nice_ticks(g.year_min, g.year_max, 12):
        if not (g.year_min <= yr <= g.year_max):
            continue
        x = x_time(yr, g.year_min, g.year_max, x0, x1)
        plan.add(Element(kind="path", layer="ENGRAVE",
                         d=G.polyline([(x, ytop), (x, ybot)]), stroke=col,
                         stroke_width=0.25, dash="2,2.5", fill="none",
                         role="tick", z=1))
        add_label(plan, str(yr), x, ytop - 3, style,
                  size=style.get("type.size_mm", 3) * 0.75, colour=col, z=3)


# ====================================================== 2. TIMELINE LANES ===
@register("timeline_lanes", "Timeline Lanes", "linear",
          "A year axis across the page; every person is a bar from birth to "
          "death, stacked in generation bands.",
          good_for="Long thin posters. The clearest possible view of who "
                   "overlapped with whom.",
          laser="excellent")
def timeline_lanes(graph, s, style) -> RenderPlan:
    plan, g, W, H, m = _frame(graph, s, style, 1189.0, 594.0)
    x0, x1 = m + 46, W - m
    y0, y1 = m + 18, H - m
    lanes = sorted(g.slots, key=lambda p: (g.slots[p].gen, g.slots[p].t0))
    n = max(1, len(lanes))
    lane_h = min(style.get("layout.lane_height_mm", 6.0), (y1 - y0) / n)
    bar_h = lane_h * 0.62
    now = float(plan.meta.year_max or 2025)
    thr = _thread_set(graph, s) if style.get("thread.enabled", True) else set()

    _year_axis(plan, g, style, x0, x1, y0 - 6, y1)

    # generation bands
    yy = y0
    band_y: dict[int, float] = {}
    for gen in sorted(g.by_gen):
        band_y[gen] = yy
        count = len(g.by_gen[gen])
        h = count * lane_h
        if gen % 2 == 0:
            plan.add(Element(kind="rect", layer="PRINT_ONLY", x=x0, y=yy,
                             w=x1 - x0, h=h, fill="#00000008", stroke="none",
                             role="ornament", z=0))
        add_label(plan, f"Gen {gen}", m + 6, yy + h / 2, style,
                  size=style.get("type.size_mm", 3) * 0.8, anchor="start",
                  colour=style.get("ornament.time_ring_colour"), z=4)
        yy += h

    ypos: dict[str, float] = {}
    for gen in sorted(g.by_gen):
        y = band_y[gen]
        for pid in sorted(g.by_gen[gen], key=lambda p: g.slots[p].t0):
            ypos[pid] = y + lane_h / 2
            y += lane_h

    _tl_placer = LabelPlacer(min_gap_mm=0.3)
    for sl in g:
        p = graph.people[sl.pid]
        b = sl.year or g.year_min
        d = sl.death_year or (now if p.living is not False else b + 1)
        xa = x_time(b, g.year_min, g.year_max, x0, x1)
        xb = max(xa + 1.0, x_time(d, g.year_min, g.year_max, x0, x1))
        y = ypos[sl.pid]
        alive = sl.death_year is None and p.living is not False
        plan.add(Element(kind="path", layer="ENGRAVE",
                         d=G.rounded_rect(xa, y - bar_h / 2, xb - xa, bar_h,
                                          bar_h * 0.35),
                         stroke=colour_for(p, sl, style, graph),
                         fill=style.get("cells.fill", "none"),
                         stroke_width=style.get("cells.stroke_width_mm", 0.35),
                         dash="1.5,1.5" if alive else dash_for(p, style),
                         opacity=opacity_for(p), person_id=sl.pid,
                         role="cell", z=20))
        if style.get("labels.show", True):
            txt = fill_template(template_for(style, sl.gen), p, sl.order)
            place_label(plan, _tl_placer, p, txt.replace("\n", "  "),
                        xa - 1.5, y, style,
                        size=min(style.get("type.size_mm", 2.6), bar_h * 0.9),
                        anchor="end")
        if sl.parent and sl.parent in ypos:
            py = ypos[sl.parent]
            pb = g.slots[sl.parent].year or g.year_min
            px = x_time(max(pb, b), g.year_min, g.year_max, x0, x1)
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=G.bezier_xy((px, py), (xa, y), vertical=True,
                                           tension=0.45),
                             stroke=style.get("connectors.colour", "#22201D"),
                             stroke_width=style.get("connectors.width_mm", 0.25),
                             fill="none", opacity=0.5, person_id=sl.pid,
                             role="connector", z=10))
        if sl.pid in thr:
            plan.add(Element(kind="path", layer=style.get("thread.layer", "ENGRAVE_DEEP"),
                             d=G.polyline([(xa, y), (xb, y)]),
                             stroke=style.get("thread.colour", "#A3392B"),
                             stroke_width=style.get("thread.stroke_width_mm", 1.2),
                             fill="none", person_id=sl.pid, role="thread", z=85))
    add_title(plan, style, W / 2, m + 6)
    return plan


# ========================================================= 3. DENDROGRAM ===
@register("dendrogram", "Classic Tree", "linear",
          "The familiar left-to-right family tree, drawn properly: elbow "
          "connectors, aligned generations, tidy sibling groups.",
          good_for="Reference printing, checking your data, sharing with "
                   "relatives who want something conventional.",
          laser="excellent")
def dendrogram(graph, s, style) -> RenderPlan:
    plan, g, W, H, m = _frame(graph, s, style, 841.0, 1189.0)
    horizontal = style.get("layout.horizontal", True)
    x0, x1 = m + 8, W - m - 40
    y0, y1 = m + 8, H - m - 8
    col_w = (x1 - x0) / max(1, g.max_gen)
    thr = _thread_set(graph, s) if style.get("thread.enabled", True) else set()

    pos = {}
    for sl in g:
        if horizontal:
            pos[sl.pid] = (x0 + sl.gen * col_w, y0 + sl.tc * (y1 - y0))
        else:
            pos[sl.pid] = (x0 + sl.tc * (x1 - x0), y0 + sl.gen * (y1 - y0) / max(1, g.max_gen))
    cr = style.get("connectors.corner_radius_mm", 1.5)
    for sl in g:
        if not sl.parent or sl.parent not in pos:
            continue
        a, b = pos[sl.parent], pos[sl.pid]
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        pts = ([a, (mid[0], a[1]), (mid[0], b[1]), b] if horizontal
               else [a, (a[0], mid[1]), (b[0], mid[1]), b])
        plan.add(Element(kind="path", layer="ENGRAVE",
                         d=G.rounded_polyline(pts, cr),
                         stroke=style.get("connectors.colour", "#22201D"),
                         stroke_width=style.get("connectors.width_mm", 0.35),
                         fill="none", person_id=sl.pid, role="connector", z=10))
    _dg_placer = LabelPlacer(min_gap_mm=0.3)
    for sl in sorted(g, key=lambda s2: (s2.gen, s2.order)):
        p = graph.people[sl.pid]
        x, y = pos[sl.pid]
        txt = fill_template(template_for(style, sl.gen), p, sl.order)
        size = style.get("type.size_mm", 2.6)
        if style.get("cells.shape", "capsule") != "none":
            wbox = est_text_width(max(txt.split("\n"), key=len, default=""), size) + 3
            hbox = size * (1.25 * len(txt.split("\n")) + 0.6)
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=G.rounded_rect(x + 1.5, y - hbox / 2, wbox, hbox, 1.2),
                             stroke=colour_for(p, sl, style, graph),
                             fill=style.get("cells.fill", "none"),
                             stroke_width=style.get("cells.stroke_width_mm", 0.28),
                             dash=dash_for(p, style), opacity=opacity_for(p),
                             person_id=sl.pid, role="cell", z=20))
        place_label(plan, _dg_placer, p, txt, x + 3.0, y, style, size=size,
                    anchor="start")
        if sl.pid in thr:
            plan.add(Element(kind="circle", layer=style.get("thread.layer", "ENGRAVE_DEEP"),
                             x=x, y=y, r=1.1, fill=style.get("thread.colour", "#A3392B"),
                             stroke="none", person_id=sl.pid, role="thread", z=85))
    add_title(plan, style, W / 2, m + 4)
    return plan


# ============================================================= 4. ICICLE ===
@register("icicle", "Proportional Bands", "linear",
          "Stacked bands whose width is proportional to how many descendants "
          "each person has. A sunburst unrolled flat.",
          good_for="Seeing at a glance which lines flourished and which died out.",
          laser="excellent")
def icicle(graph, s, style) -> RenderPlan:
    plan, g, W, H, m = _frame(graph, s, style, 1189.0, 594.0)
    x0, x1 = m, W - m
    y0, y1 = m + 10, H - m
    rows = g.max_gen + 1
    rh = (y1 - y0) / max(1, rows)
    pad = style.get("layout.band_pad_mm", 0.5)
    thr = _thread_set(graph, s) if style.get("thread.enabled", True) else set()
    for sl in g:
        p = graph.people[sl.pid]
        xa = x0 + sl.t0 * (x1 - x0) + pad
        xb = x0 + sl.t1 * (x1 - x0) - pad
        y = y0 + sl.gen * rh
        if xb - xa < 0.4:
            continue
        plan.add(Element(kind="path", layer="ENGRAVE",
                         d=G.rounded_rect(xa, y, xb - xa, rh * 0.82, 0.8),
                         stroke=colour_for(p, sl, style, graph),
                         fill=style.get("cells.fill", "none"),
                         stroke_width=style.get("cells.stroke_width_mm", 0.3),
                         dash=dash_for(p, style), opacity=opacity_for(p),
                         person_id=sl.pid, role="cell", z=20))
        size = min(style.get("type.size_mm", 2.6), rh * 0.42)
        txt = fill_template(template_for(style, sl.gen), p, sl.order).replace("\n", " ")
        if est_text_width(txt, size) < (xb - xa) * 0.92 and style.get("labels.show", True):
            add_label(plan, txt, (xa + xb) / 2, y + rh * 0.41, style,
                      size=size, person_id=sl.pid, z=60)
        elif (xb - xa) > size * 1.4:
            add_label(plan, p.initials, (xa + xb) / 2, y + rh * 0.41, style,
                      size=size, person_id=sl.pid, z=60)
        if sl.pid in thr:
            plan.add(Element(kind="path", layer=style.get("thread.layer", "ENGRAVE_DEEP"),
                             d=G.polyline([(xa, y + rh * 0.82), (xb, y + rh * 0.82)]),
                             stroke=style.get("thread.colour", "#A3392B"),
                             stroke_width=style.get("thread.stroke_width_mm", 1.0),
                             fill="none", person_id=sl.pid, role="thread", z=85))
    add_title(plan, style, W / 2, m + 4)
    return plan


# ======================================================== 5. ARC DIAGRAM ===
@register("arc_diagram", "Arc Diagram", "network",
          "Everyone on one line in date order; every parent-child link is a "
          "semicircle above it. Cousin marriages show as unmistakable loops.",
          good_for="Spotting pedigree collapse and endogamy.",
          laser="good")
def arc_diagram(graph, s, style) -> RenderPlan:
    plan, g, W, H, m = _frame(graph, s, style, 1189.0, 420.0)
    x0, x1 = m + 6, W - m - 6
    baseline = H - m - 34
    order = sorted(g.slots, key=lambda p: (g.slots[p].year or 0, g.slots[p].t0))
    n = max(1, len(order) - 1)
    px = {pid: x0 + (x1 - x0) * i / n for i, pid in enumerate(order)}
    thr = _thread_set(graph, s) if style.get("thread.enabled", True) else set()
    plan.add(Element(kind="path", layer="ENGRAVE",
                     d=G.polyline([(x0, baseline), (x1, baseline)]),
                     stroke=style.get("ornament.time_ring_colour", "#C9C0B0"),
                     stroke_width=0.3, fill="none", role="tick", z=1))
    for sl in g:
        if not sl.parent or sl.parent not in px:
            continue
        a, b = px[sl.parent], px[sl.pid]
        r = abs(b - a) / 2
        mid = (a + b) / 2
        d = (f"M{G.fmt(a)},{G.fmt(baseline)}"
             f"A{G.fmt(r)},{G.fmt(min(r, style.get('layout.arc_max_mm', 150)))} "
             f"0 0,{1 if b > a else 0} {G.fmt(b)},{G.fmt(baseline)}")
        onthr = sl.pid in thr and sl.parent in thr
        plan.add(Element(kind="path", layer="ENGRAVE", d=d,
                         stroke=(style.get("thread.colour") if onthr
                                 else colour_for(graph.people[sl.pid], sl, style, graph)),
                         stroke_width=(style.get("thread.stroke_width_mm", 1.0)
                                       if onthr else style.get("connectors.width_mm", 0.28)),
                         fill="none", opacity=1.0 if onthr else 0.55,
                         person_id=sl.pid, role="thread" if onthr else "connector",
                         z=80 if onthr else 10))
    _arc_placer = LabelPlacer(min_gap_mm=0.2)
    for sl in g:
        p = graph.people[sl.pid]
        x = px[sl.pid]
        plan.add(Element(kind="circle", layer="ENGRAVE", x=x, y=baseline,
                         r=style.get("nodes.size_mm", 0.9), fill="#FBF8F2",
                         stroke=style.get("nodes.stroke", "#22201D"),
                         stroke_width=0.28, person_id=sl.pid, role="station", z=40))
        if style.get("labels.show", True):
            place_label(plan, _arc_placer, p, p.short_name, x, baseline + 3,
                        style, rotate=90, size=style.get("type.size_mm", 2.2),
                        anchor="start")
    add_title(plan, style, W / 2, m + 4)
    return plan


# ======================================================== 6. CIRCLE PACK ===
@register("circle_pack", "Nested Families", "network",
          "Each family is a circle; its children are circles inside it. "
          "Nesting depth is descent.",
          good_for="Grasping the shape of a family at a glance, without dates.",
          laser="good")
def circle_pack(graph, s, style) -> RenderPlan:
    plan, g, W, H, m = _frame(graph, s, style, 800.0, 800.0)
    thr = _thread_set(graph, s) if style.get("thread.enabled", True) else set()
    R = min(W, H) / 2 - m
    cx, cy = W / 2, H / 2

    def place(pid: str, x: float, y: float, r: float, depth: int):
        p = graph.people[pid]
        sl = g.slots[pid]
        plan.add(Element(kind="circle", layer="ENGRAVE", x=x, y=y, r=r,
                         fill=style.get("cells.fill", "none"),
                         stroke=colour_for(p, sl, style, graph),
                         stroke_width=max(0.18, style.get("cells.stroke_width_mm", 0.4) / (depth + 1) ** 0.4),
                         dash=dash_for(p, style), opacity=opacity_for(p),
                         person_id=pid, role="cell", z=20 + depth))
        if pid in thr:
            plan.add(Element(kind="circle", layer=style.get("thread.layer", "ENGRAVE_DEEP"),
                             x=x, y=y, r=r * 0.94, fill="none",
                             stroke=style.get("thread.colour", "#A3392B"),
                             stroke_width=style.get("thread.stroke_width_mm", 0.8),
                             person_id=pid, role="thread", z=85))
        kids = [c for c in graph.children(pid) if c in g.slots]
        if not kids or r < 6:
            if style.get("labels.show", True) and r > 3:
                add_label(plan, graph.people[pid].short_name, x, y, style,
                          size=min(style.get("type.size_mm", 2.4), r * 0.55),
                          person_id=pid, z=60)
            return
        if style.get("labels.show", True) and r > 12:
            add_label(plan, graph.people[pid].surname or graph.people[pid].short_name,
                      x, y - r + 3.5, style,
                      size=min(style.get("type.size_mm", 2.6), r * 0.22),
                      person_id=pid, z=60)
        k = len(kids)
        sub = r * (0.42 if k <= 2 else 0.85 / (1 + math.sqrt(k)))
        ring = r - sub - r * 0.12
        for i, c in enumerate(kids):
            a = G.TAU * i / k - math.pi / 2
            place(c, x + ring * math.cos(a), y + ring * math.sin(a), sub, depth + 1)

    roots = g.roots
    if len(roots) == 1:
        place(roots[0], cx, cy, R, 0)
    else:
        rr = R / (1 + math.sqrt(len(roots)))
        for i, rt in enumerate(roots):
            a = G.TAU * i / len(roots) - math.pi / 2
            place(rt, cx + (R - rr) * math.cos(a), cy + (R - rr) * math.sin(a), rr, 0)
    add_title(plan, style, W / 2, m + 4)
    return plan


# ========================================================== 7. HOURGLASS ===
def ancestor_slots(graph, subject: str, max_gen: int = 6):
    """Ancestors positioned by Ahnentafel number.

    You are 1, your father 2, your mother 3, their parents 4-7. Within a
    generation the numbers run left to right in a fixed order, so the layout
    is stable, gaps are meaningful (a missing grandparent leaves a hole where
    they should be), and merging pairs are always adjacent.

    Returns {person: (generation, fraction across the row)}.
    """
    from ..base import pedigree_paths
    paths = pedigree_paths(graph, subject)
    out: dict[str, tuple[int, float]] = {}
    for pid, path in paths.items():
        g = len(path)
        if g > max_gen:
            continue
        idx = int(path, 2) if path else 0
        out[pid] = (g, (idx + 0.5) / (2 ** g))
    return out


@register("hourglass", "Hourglass", "linear",
          "Your ancestors fanning upward, your descendants fanning downward, "
          "with you at the waist.",
          good_for="A chart centred on one living person. The most natural "
                   "shape when you are the point of the exercise.",
          laser="excellent")
def hourglass(graph, s, style) -> RenderPlan:
    plan, g, W, H, m = _frame(graph, s, style, 841.0, 1189.0)
    subject = s.subject_id or (graph.apexes() or [None])[0]
    if not subject:
        plan.meta.warnings.append("Choose whose chart this is first.")
        return plan

    up = ancestor_slots(graph, subject, s.max_generations or 6)
    down = _descendant_slots(graph, subject, s.max_generations or 4)
    x0, x1 = m + 6, W - m - 6
    rows_up = max((gg for gg, _ in up.values()), default=0)
    rows_dn = max((gg for gg, _ in down.values()), default=0)
    row_h = (H - 2 * m) / max(2, rows_up + rows_dn + 1)
    waist = m + rows_up * row_h

    def place(gen, frac, upward):
        return (x0 + frac * (x1 - x0),
                waist - gen * row_h if upward else waist + gen * row_h)

    pos = {pid: place(gg, fr, True) for pid, (gg, fr) in up.items()}
    for pid, (gg, fr) in down.items():
        pos.setdefault(pid, place(gg, fr, False))

    cr = style.get("connectors.corner_radius_mm", 2.0)
    col = style.get("connectors.colour", "#22201D")
    lw = style.get("connectors.width_mm", 0.4)

    for pid in list(up):                       # child -> parent, going up
        for par in graph.parents(pid, primary_only=False):
            if par not in pos or pid not in pos:
                continue
            a, b = pos[pid], pos[par]
            mid = (a[1] + b[1]) / 2
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=G.rounded_polyline(
                                 [a, (a[0], mid), (b[0], mid), b], cr),
                             stroke=col, stroke_width=lw, fill="none",
                             person_id=pid, role="connector", z=10))
    for pid in list(down):                     # parent -> child, going down
        for kid in graph.children(pid):
            if kid not in down or kid not in pos:
                continue
            a, b = pos[pid], pos[kid]
            mid = (a[1] + b[1]) / 2
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=G.rounded_polyline(
                                 [a, (a[0], mid), (b[0], mid), b], cr),
                             stroke=col, stroke_width=lw, fill="none",
                             person_id=kid, role="connector", z=10))

    placer = LabelPlacer(min_gap_mm=0.4)
    size = style.get("type.size_mm", 2.6)
    for pid, (x, y) in pos.items():
        p = graph.people[pid]
        sl = g.slots.get(pid)
        gen = up.get(pid, down.get(pid, (0, 0)))[0]
        is_subject = pid == subject
        plan.add(Element(kind="circle", layer="ENGRAVE", x=x, y=y,
                         r=style.get("nodes.size_mm", 1.2) * (1.8 if is_subject else 1.0),
                         fill=style.get("nodes.fill", "#FBF8F2") if not is_subject
                         else style.get("thread.colour", "#A3392B"),
                         stroke=style.get("nodes.stroke", "#22201D"),
                         stroke_width=0.35, person_id=pid,
                         role="station", z=40))
        txt = fill_template(template_for(style, gen), p, 0)
        place_label(plan, placer, p, txt, x, y - size * 1.5, style,
                    size=size * (1.25 if is_subject else 1.0), anchor="middle")

    plan.add(Element(kind="path", layer="GUIDE",
                     d=G.polyline([(x0, waist), (x1, waist)]),
                     stroke=style.get("ornament.time_ring_colour", "#D8D0C0"),
                     stroke_width=0.25, dash="2,2.5", fill="none",
                     role="tick", z=1))
    plan.meta.people = len(pos)
    plan.meta.extra["labels_hidden"] = placer.dropped
    add_title(plan, style, W / 2, m + 4)
    return plan


def _descendant_slots(graph, subject: str, max_gen: int):
    """Descendants of one person, laid out by leaf count."""
    out: dict[str, tuple[int, float]] = {}

    def width(pid, depth):
        if depth >= max_gen:
            return 1
        kids = graph.children(pid)
        return sum(width(k, depth + 1) for k in kids) or 1

    total = width(subject, 0)

    def walk(pid, depth, lo, hi):
        out[pid] = (depth, (lo + hi) / 2)
        if depth >= max_gen:
            return
        kids = graph.children(pid)
        if not kids:
            return
        cur = lo
        tot = sum(width(k, depth + 1) for k in kids) or 1
        for k in kids:
            w = width(k, depth + 1) / tot
            walk(k, depth + 1, cur, cur + (hi - lo) * w)
            cur += (hi - lo) * w

    walk(subject, 0, 0.0, 1.0)
    return out
