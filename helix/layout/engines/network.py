"""The six designs that were specified and never built.

Each was registered from the start so the gallery could show it "greyed out
with a clear note", and nothing ever greyed them out — so a third of the
gallery was pictures you could click into a `NotImplementedError`. They are
built here.

  treemap        nested rectangles sized by how many descend from each line
  hive           one axis per family line, links arcing between them
  sugiyama       proper layered drawing with crossing minimisation
  sankey         ribbons whose width is the number of descendants
  geo_map        people at their birthplace, with the family's migration
  constellation  a star chart: brightness is descendants, lines are descent

WHAT THEY SHARE WITH THE OTHER FOURTEEN. `build_grid` has already done the
scoping, the ordering, the weighting and the married-in placement, so each
of these is a reading of the same Grid rather than a second layout engine.
None of them touches the database, and `RenderPlan` is still the only bridge
to the renderers.

WHAT THEY ARE FOR. Not the flagship — `radial_family` is, and none of these
tries to be a better version of it. Each answers a question the couple-cell
chart deliberately cannot: which branches thrived, which families married
into each other and how often, where a family moved, and what a heavily
intermarried tree looks like when you stop pretending it is a tree.

`within` IS FOR ASKING, NOT FOR WALKING. Every design here keeps a
`within = set(g.slots)` to test membership in one step, and iterating it is
the natural next thing to write. Do not: a set of strings comes out in an
order that depends on the hash seed, which is different in every process.
Two of these designs did exactly that, and the same file exported twice
gave two different charts — the star chart's lines in a different order,
and the map worse than that, because the order decided which place kept
its label and where the coordinate-less ones sat round the edge. Walk
`g.slots`, which is a dict and keeps the order the grid built it in, and
ask `within` whether somebody is on the chart. `tests/test_layout.py`
renders every design under two hash seeds and will fail if this comes back.
"""
from __future__ import annotations

import math

from .. import geometry as G
from ..base import build_grid
from ..common import (LabelPlacer, add_title, colour_for, est_text_width,
                      place_label)
from ..plan import Canvas, Element, FontSpec, PlanMeta, RenderPlan
from ..registry import register


def _frame(graph, s, style, default_w=1189.0, default_h=841.0):
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


def _descend(graph, pid: str, within: set) -> int:
    """How many people on this chart descend from somebody, plus themselves.

    The number every one of these designs is sized by, and the one the
    couple-cell chart cannot show: a branch that thrived and a branch that
    died out are the same width on a tidy tree.
    """
    seen, stack = set(), [pid]
    while stack:
        x = stack.pop()
        if x in seen or x not in within:
            continue
        seen.add(x)
        stack.extend(graph.children(x))
    return max(1, len(seen))


def _label(plan, text, x, y, size, col, *, anchor="middle", pid="", angle=0.0):
    """A label that is NOT a person: an axis, a place, a heading.

    Person labels go through `place_label`, which suppresses collisions and
    demotes to initials rather than piling names on top of each other. These
    do not, because there are eight of them and each one has to be there.
    """
    if not text:
        return
    plan.add(Element(kind="text", layer="ENGRAVE", text=text, x=x, y=y,
                     fill=col, rotate=angle, person_id=pid,
                     font=FontSpec(size_mm=size, anchor=anchor), role="label"))


def _report(plan, placer: LabelPlacer) -> None:
    """Say how many names could not be fitted, rather than quietly dropping.

    Every one of these designs will be asked to draw a family too big for
    the sheet. A chart missing forty names and not saying so is worse than
    one that says it.
    """
    plan.meta.demotions = placer.demoted
    if placer.dropped:
        plan.meta.warnings.append(
            f"{placer.dropped} name{'' if placer.dropped == 1 else 's'} would "
            f"not fit and {'is' if placer.dropped == 1 else 'are'} not shown. "
            f"Make the sheet bigger, reduce the generations, or narrow the "
            f"chart to one branch.")


# ══════════════════════════════ 1. TREEMAP ═══════════════════════════════
@register("treemap", "Treemap", "linear",
          "Nested rectangles sized by how many people descend from each "
          "line. The branches that thrived are the big ones.",
          good_for="Seeing at a glance which parts of a family grew and "
                   "which died out — the one thing a tidy tree hides.",
          laser="good")
def treemap(graph, s, style) -> RenderPlan:
    plan, g, W, H, m = _frame(graph, s, style, 1000.0, 700.0)
    col = style.get("colour.ink", "#26241F")
    size = style.get("type.size_mm", 3.4)
    lw = style.get("connectors.width_mm", 0.5)
    within = set(g.slots)

    def kids(pid):
        return [c for c in graph.children(pid) if c in within]

    # SQUARIFIED, which is the whole trick: laid out in plain rows the
    # rectangles come out as slivers nobody can label, and the point of a
    # treemap is that you can read the names in it.
    def squarify(items, x, y, w, h, depth):
        if not items or w <= 1 or h <= 1:
            return
        total = sum(n for _p, n in items) or 1
        row, row_n, i = [], 0, 0
        horizontal = w >= h
        while i < len(items):
            pid, n = items[i]
            trial = row + [(pid, n)]
            trial_n = row_n + n
            if row and _worst(row, row_n, w, h, total, horizontal) < \
                    _worst(trial, trial_n, w, h, total, horizontal):
                break
            row, row_n, i = trial, trial_n, i + 1
        frac = row_n / total
        if horizontal:
            bw = w * frac
            yy = y
            for pid, n in row:
                bh = h * (n / row_n)
                _cell(pid, x, yy, bw, bh, depth)
                yy += bh
            squarify(items[i:], x + bw, y, w - bw, h, depth)
        else:
            bh = h * frac
            xx = x
            for pid, n in row:
                bw = w * (n / row_n)
                _cell(pid, xx, y, bw, bh, depth)
                xx += bw
            squarify(items[i:], x, y + bh, w, h - bh, depth)

    def _worst(row, row_n, w, h, total, horizontal):
        if not row or row_n == 0:
            return 1e9
        side = (h if horizontal else w)
        thick = (w if horizontal else h) * (row_n / total)
        worst = 0.0
        for _p, n in row:
            length = side * (n / row_n)
            worst = max(worst, max(thick / max(length, 1e-6),
                                   length / max(thick, 1e-6)))
        return worst

    placer = LabelPlacer(cell_mm=12.0)
    drawn: set = set()

    def _cell(pid, x, y, w, h, depth):
        if w < 1.5 or h < 1.5:
            return
        drawn.add(pid)
        pad = min(2.0, w / 6, h / 6)
        plan.add(Element(kind="rect", layer="ENGRAVE", x=x, y=y,
                         w=w, h=h, stroke=col, stroke_width=lw,
                         fill=colour_for(graph.people[pid], g.slots[pid], style, graph)
                         if depth == 0 else "none",
                         opacity=0.16 if depth == 0 else 1.0,
                         person_id=pid, role="cell", z=depth))
        p = graph.people[pid]
        fs = min(size, h * 0.5, w / max(4, len(p.short_name) * 0.55))
        if fs >= style.get("type.min_size_mm", 2.0):
            place_label(plan, placer, p, p.short_name, x + w / 2,
                        y + min(h * 0.5, pad + fs), style, size=fs)
        inner = kids(pid)
        if inner and w > 12 and h > 10:
            squarify(sorted(((c, _descend(graph, c, within)) for c in inner),
                            key=lambda t: -t[1]),
                     x + pad, y + pad + fs, w - pad * 2, h - pad * 2 - fs,
                     depth + 1)

    roots = [r for r in g.roots if r in within] or list(g.slots)[:1]
    squarify(sorted(((r, _descend(graph, r, within)) for r in roots),
                    key=lambda t: -t[1]),
             m, m + 10, W - m * 2, H - m * 2 - 10, 0)

    # A TREEMAP DROPS PEOPLE AND HAS NO WAY OF SHOWING IT. Anyone whose
    # rectangle came out under a millimetre and a half is simply not on the
    # sheet, and a chart cannot be allowed to lose forty people in silence.
    lost = len(within) - len(drawn)
    if lost > 0:
        who = "person is" if lost == 1 else "people are"
        plan.meta.warnings.append(
            f"{lost} {who} in branches too small to draw at this size and "
            f"{'is' if lost == 1 else 'are'} not on the chart. Use a bigger "
            f"sheet, or narrow the chart to one branch to see inside it.")
    _report(plan, placer)
    add_title(plan, style, W / 2, m * 0.7)
    return plan


# ═══════════════════════════════ 2. HIVE PLOT ════════════════════════════
@register("hive", "Hive Plot", "network",
          "One straight axis per family line; every marriage arcs between "
          "two axes. Intermarriage stops being a suspicion and becomes a "
          "count.",
          good_for="Analysing how a few families married into each other "
                   "over generations.",
          laser="good")
def hive(graph, s, style) -> RenderPlan:
    plan, g, W, H, m = _frame(graph, s, style, 900.0, 900.0)
    col = style.get("colour.ink", "#26241F")
    lw = style.get("connectors.width_mm", 0.45)
    size = style.get("type.size_mm", 3.0)
    cx, cy = W / 2, H / 2
    r0, r1 = min(W, H) * 0.10, min(W, H) * 0.44

    # ONE AXIS PER SURNAME, biggest first, and everybody else on a shared
    # axis at the end: forty axes is not a hive plot, it is a hedgehog.
    by_name: dict = {}
    for pid in g.slots:
        by_name.setdefault(graph.people[pid].surname or "—", []).append(pid)
    ranked = sorted(by_name.items(), key=lambda kv: -len(kv[1]))
    keep, rest = ranked[:7], ranked[7:]
    axes = [(nm, ids) for nm, ids in keep]
    if rest:
        axes.append(("others", [p for _n, ids in rest for p in ids]))

    where: dict = {}
    for i, (name, ids) in enumerate(axes):
        th = -math.pi / 2 + 2 * math.pi * i / len(axes)
        ids = sorted(ids, key=lambda p: graph.people[p].birth_year or 9999)
        plan.add(Element(kind="path", layer="ENGRAVE",
                         d=G.polyline([G.polar(cx, cy, r0, th),
                                       G.polar(cx, cy, r1, th)]),
                         stroke=col, stroke_width=lw * 1.6, fill="none",
                         role="axis", z=1))
        for k, pid in enumerate(ids):
            r = r0 + (r1 - r0) * ((k + 0.5) / max(1, len(ids)))
            x, y = G.polar(cx, cy, r, th)
            where[pid] = (x, y)
            plan.add(Element(kind="circle", layer="ENGRAVE", x=x, y=y,
                             r=max(0.7, lw * 2.2), stroke=col,
                             stroke_width=lw * 0.7, fill=col,
                             person_id=pid, role="node", z=6))
        # The axis name is the only text on this chart and there are eight of
        # them, so it can afford to be a heading rather than a caption. Set
        # along the axis, turned upright, with how many people are on it --
        # the count is half the answer the design exists to give.
        lx, ly = G.polar(cx, cy, r1 + size * 3.6, th)
        rot, anch = G.deg(th), "start"
        if G.text_is_upside_down(th):
            rot, anch = rot + 180, "end"
        _label(plan, f"{name} · {len(ids)}", lx, ly, size * 1.9, col,
               anchor=anch, angle=rot)

    # THE MARRIAGES ARE THE POINT. A tie inside one axis is a family marrying
    # itself, which is exactly what this design exists to make countable.
    same = 0
    for u in graph.unions.values():
        pair = [x for x in u.partners if x in where][:2]
        if len(pair) < 2:
            continue
        (x0, y0), (x1, y1) = where[pair[0]], where[pair[1]]
        inside = (graph.people[pair[0]].surname == graph.people[pair[1]].surname)
        same += inside
        plan.add(Element(kind="path", layer="ENGRAVE",
                         d=_bow(x0, y0, x1, y1, cx, cy, 0.55 if inside else 0.22),
                         stroke=style.get("lines.marriage_colour", col),
                         stroke_width=lw * (1.8 if inside else 0.8),
                         fill="none", opacity=1.0 if inside else 0.55,
                         person_id=pair[0], role="marriage", z=4))
    plan.meta.extra["same_surname_marriages"] = same
    plan.meta.legend.append({
        "label": f"{same} marriage{'' if same == 1 else 's'} within one "
                 f"surname" if same else "no two people of the same surname "
                                         "married each other",
        "note": "drawn heavier, and looping back to the axis it started on"})
    add_title(plan, style, cx, m * 0.8)
    return plan


def _bow(x0, y0, x1, y1, cx, cy, bend: float) -> str:
    """A curve between two points, bowed off to one side.

    THE OBVIOUS VERSION IS WRONG. Pushing the control point radially outward
    from the centre works until the two ends are on opposite axes -- then
    their midpoint IS the centre, there is nothing to push away from, and
    every long marriage was drawn as a straight line through the middle of
    the hive. Bowing perpendicular to the chord instead always has a
    direction, and the side is chosen away from the centre so short links
    still bulge outward the way a hive plot expects.
    """
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy) or 1.0
    px, py = -dy / length, dx / length
    if (mx - cx) * px + (my - cy) * py < 0:
        px, py = -px, -py
    k = length * bend
    return f"M {x0:.3f},{y0:.3f} Q {mx + px * k:.3f},{my + py * k:.3f} " \
           f"{x1:.3f},{y1:.3f}"


# ═════════════════════════ 3. LAYERED NETWORK ════════════════════════════
@register("sugiyama", "Layered Network", "network",
          "Proper layered graph drawing with crossing minimisation. The one "
          "design that handles heavy cousin marriage without spaghetti.",
          good_for="Tangled trees where the simple layouts give up.",
          laser="good")
def sugiyama(graph, s, style) -> RenderPlan:
    plan, g, W, H, m = _frame(graph, s, style, 1189.0, 841.0)
    col = style.get("colour.ink", "#26241F")
    lw = style.get("connectors.width_mm", 0.45)
    size = style.get("type.size_mm", 3.0)
    within = set(g.slots)

    layers: dict = {}
    for pid, sl in g.slots.items():
        layers.setdefault(sl.gen, []).append(pid)
    gens = sorted(layers)
    if not gens:
        return plan

    # THE ONE THING THIS DESIGN IS FOR: the barycentre sweep. Each person is
    # moved to the average position of whoever they are joined to on the
    # layer before, and the sweep is repeated until it stops improving.
    # Cousin marriage is what breaks the tidy-tree layouts, and it is
    # exactly what this absorbs.
    pos = {pid: float(i) for gen in gens
           for i, pid in enumerate(layers[gen])}

    def neighbours(pid, other_gen):
        out = [x for x in graph.parents(pid, primary_only=False)
               if x in within and g.slots[x].gen == other_gen]
        out += [x for x in graph.children(pid)
                if x in within and g.slots[x].gen == other_gen]
        out += [x for x in graph.partners(pid)
                if x in within and g.slots[x].gen == other_gen]
        return out

    def couple_up(row: list[str]) -> list[str]:
        """Bring partners next to each other without disturbing the order.

        THE SWEEP CANNOT DO THIS. It reads the layer above, and a husband and
        wife are on the SAME layer, so a marriage exerted no pull at all --
        which drew a couple at opposite ends of a row joined by a rail
        straight through forty other people. Placing the partner immediately
        after, at the position the barycentre already chose for the first of
        them, keeps the crossing count the sweep worked for.
        """
        out, seen = [], set()
        for pid in row:
            if pid in seen:
                continue
            out.append(pid)
            seen.add(pid)
            for mate in graph.partners(pid):
                if mate in within and mate not in seen and \
                        g.slots[mate].gen == g.slots[pid].gen:
                    out.append(mate)
                    seen.add(mate)
        return out

    for sweep in range(8):
        order = gens if sweep % 2 == 0 else list(reversed(gens))
        for k, gen in enumerate(order):
            if k == 0:
                continue
            prev = order[k - 1]
            keyed = []
            for pid in layers[gen]:
                ns = neighbours(pid, prev)
                keyed.append((sum(pos[n] for n in ns) / len(ns) if ns
                              else pos[pid], pid))
            keyed.sort()
            row = couple_up([pid for _b, pid in keyed])
            for i, pid in enumerate(row):
                pos[pid] = float(i)
            layers[gen] = row
    for gen in gens:
        layers[gen] = couple_up(layers[gen])
        for i, pid in enumerate(layers[gen]):
            pos[pid] = float(i)

    widest = max(len(v) for v in layers.values())
    xstep = (W - m * 2) / max(1, widest)
    ystep = (H - m * 2 - 12) / max(1, len(gens))
    at: dict = {}
    for gi, gen in enumerate(gens):
        row = layers[gen]
        y = m + 12 + ystep * (gi + 0.5)
        span = xstep * len(row)
        x0 = (W - span) / 2 + xstep / 2
        for i, pid in enumerate(row):
            at[pid] = (x0 + i * xstep, y)

    # A GENERATION OF NINETY GETS THIRTEEN MILLIMETRES A PERSON, and a name
    # needs twenty. Set horizontally the row came out as a grey smear with
    # the letters of four names interleaved. Turned on its side each name has
    # the whole band height to run into, which is how every layered drawing
    # with a crowded rank handles it. MEASURED, not guessed at: the longest
    # name on the chart against the width one person actually gets.
    longest = max((est_text_width(graph.people[p].short_name, size)
                   for p in g.slots), default=0.0)
    upright = longest <= xstep

    # Edges first, so the names sit on top of them.
    for pid in g.slots:
        for kid in graph.children(pid):
            if kid not in at or pid not in at:
                continue
            (x0, y0), (x1, y1) = at[pid], at[kid]
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=f"M {x0:.3f},{y0:.3f} C {x0:.3f},"
                               f"{(y0 + y1) / 2:.3f} {x1:.3f},"
                               f"{(y0 + y1) / 2:.3f} {x1:.3f},{y1:.3f}",
                             stroke=col, stroke_width=lw, fill="none",
                             person_id=pid, role="edge", z=2))
    for u in graph.unions.values():
        pair = [x for x in u.partners if x in at][:2]
        if len(pair) == 2:
            (x0, y0), (x1, y1) = at[pair[0]], at[pair[1]]
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=f"M {x0:.3f},{y0:.3f} L {x1:.3f},{y1:.3f}",
                             stroke=style.get("lines.marriage_colour", col),
                             stroke_width=lw * 1.4, fill="none",
                             person_id=pair[0], role="marriage", z=3))
    placer = LabelPlacer(cell_mm=max(6.0, xstep))
    for pid, (x, y) in at.items():
        plan.add(Element(kind="circle", layer="ENGRAVE", x=x, y=y,
                         r=max(0.8, lw * 2.2), stroke=col, stroke_width=lw,
                         fill=colour_for(graph.people[pid], g.slots[pid], style, graph),
                         person_id=pid, role="node", z=6))
        p = graph.people[pid]
        if upright:
            place_label(plan, placer, p, p.short_name, x, y - lw * 5, style,
                        size=size)
        else:
            place_label(plan, placer, p, p.short_name, x, y - lw * 5, style,
                        size=size, rotate=-90, anchor="start")
    _report(plan, placer)
    add_title(plan, style, W / 2, m * 0.7)
    return plan


# ═══════════════════════════ 4. RIVER OF DESCENT ═════════════════════════
@register("sankey", "River of Descent", "network",
          "Ribbons whose width is the number of descendants flowing forward "
          "through time. A line that dies out visibly narrows to nothing.",
          good_for="Emotional impact. Showing which branches carried on.",
          laser="poor")
def sankey(graph, s, style) -> RenderPlan:
    plan, g, W, H, m = _frame(graph, s, style, 1189.0, 700.0)
    col = style.get("colour.ink", "#26241F")
    size = style.get("type.size_mm", 3.2)
    within = set(g.slots)

    layers: dict = {}
    for pid, sl in g.slots.items():
        layers.setdefault(sl.gen, []).append(pid)
    gens = sorted(layers)
    if not gens:
        return plan

    xstep = (W - m * 2) / max(1, len(gens))
    band = H - m * 2 - 14
    boxes: dict = {}
    placer = LabelPlacer(cell_mm=10.0)
    for gi, gen in enumerate(gens):
        row = sorted(layers[gen], key=lambda p: g.slots[p].tc)
        weights = [_descend(graph, p, within) for p in row]
        total = sum(weights) or 1
        # A gap per person so the ribbons read as separate flows.
        gap = min(2.0, band * 0.02 / max(1, len(row)))
        y = m + 14
        x = m + gi * xstep
        for pid, wt in zip(row, weights):
            h = max(1.2, (band - gap * len(row)) * wt / total)
            boxes[pid] = (x, y, xstep * 0.22, h)
            plan.add(Element(kind="rect", layer="ENGRAVE", x=x, y=y,
                             w=xstep * 0.22, h=h,
                             stroke=col, stroke_width=0.3,
                             fill=colour_for(graph.people[pid], g.slots[pid], style, graph),
                             opacity=0.55, person_id=pid, role="node", z=5))
            # The name has to fit in the ribbon's own thickness, and the
            # placer refuses it if a neighbour has already taken the space --
            # so the wide branches keep their names and the threads go bare,
            # which is the reading this design wants anyway.
            if h >= size * 1.4:
                place_label(plan, placer, graph.people[pid],
                            graph.people[pid].short_name,
                            x + xstep * 0.24, y + h / 2 + size * 0.35, style,
                            size=min(size, h * 0.7), anchor="start")
            y += h + gap
    _report(plan, placer)

    # THE RIBBON IS THE POINT: its width at each end is how many people that
    # line carried, so a branch that died out tapers to a thread and stops.
    for pid, (x, y, w, h) in boxes.items():
        kids = [c for c in graph.children(pid) if c in boxes]
        if not kids:
            continue
        share = sum(boxes[c][3] for c in kids) or 1
        yy = y
        for c in sorted(kids, key=lambda c: boxes[c][1]):
            cx0, cy0, _cw, ch = boxes[c]
            take = h * (boxes[c][3] / share)
            plan.add(Element(
                kind="path", layer="ENGRAVE",
                d=(f"M {x + w:.3f},{yy:.3f} "
                   f"C {(x + w + cx0) / 2:.3f},{yy:.3f} "
                   f"{(x + w + cx0) / 2:.3f},{cy0:.3f} {cx0:.3f},{cy0:.3f} "
                   f"L {cx0:.3f},{cy0 + ch:.3f} "
                   f"C {(x + w + cx0) / 2:.3f},{cy0 + ch:.3f} "
                   f"{(x + w + cx0) / 2:.3f},{yy + take:.3f} "
                   f"{x + w:.3f},{yy + take:.3f} Z"),
                stroke="none", stroke_width=0,
                fill=colour_for(graph.people[pid], g.slots[pid], style, graph), opacity=0.30,
                person_id=pid, role="flow", z=2))
            yy += take
    add_title(plan, style, W / 2, m * 0.7)
    return plan


# ══════════════════════════════ 5. MAP VIEW ══════════════════════════════
@register("geo_map", "Map View", "spatial",
          "People at the place they were born, with lines showing how the "
          "family moved. Places without coordinates are laid out around the "
          "edge and said so.",
          good_for="Families that moved. Turns the chart into a story of "
                   "place rather than of time.",
          laser="excellent")
def geo_map(graph, s, style) -> RenderPlan:
    plan, g, W, H, m = _frame(graph, s, style, 1000.0, 800.0)
    col = style.get("colour.ink", "#26241F")
    lw = style.get("connectors.width_mm", 0.4)
    size = style.get("type.size_mm", 3.0)
    within = set(g.slots)

    # THE PLACES THIS PROGRAM ACTUALLY HAS. `place` carries lat/lon and the
    # sample generator fills them in; a file typed by hand has names and no
    # coordinates, and this has to work for both. Named places without
    # coordinates go round the edge, labelled -- rather than being silently
    # dropped, which would be a map that lies by omission.
    named: dict = {}
    for pid in g.slots:
        p = graph.people[pid]
        nm = (p.birth_place or "").strip()
        if nm:
            named.setdefault(nm, []).append(pid)
    coords = {nm: c for nm, c in getattr(graph, "coords", {}).items()
              if nm in named}

    # Scaled to the places ON THIS CHART, not to every place in the file: a
    # single ancestor from Nova Scotia otherwise shrinks four generations of
    # Somerset into one dot.
    lats = [c[0] for c in coords.values()]
    lons = [c[1] for c in coords.values()]
    have_geo = len(lats) >= 2
    if have_geo:
        la0, la1 = min(lats), max(lats)
        lo0, lo1 = min(lons), max(lons)
        pad = 0.08
        span_la = max(1e-6, la1 - la0) * (1 + pad * 2)
        span_lo = max(1e-6, lo1 - lo0) * (1 + pad * 2)
        # Equirectangular, corrected for latitude so a county is not stretched.
        kx = math.cos(math.radians((la0 + la1) / 2))
        scale = min((W - m * 2) / (span_lo * kx), (H - m * 2 - 14) / span_la)

        def project(la, lo):
            x = W / 2 + (lo - (lo0 + lo1) / 2) * kx * scale
            y = H / 2 - (la - (la0 + la1) / 2) * scale
            return x, y
    else:
        def project(la, lo):
            return W / 2, H / 2

    ring, placed = [], {}
    for nm, _ids in sorted(named.items(), key=lambda kv: -len(kv[1])):
        c = coords.get(nm)
        if have_geo and c:
            placed[nm] = project(*c)
        else:
            ring.append(nm)
    for i, nm in enumerate(ring):
        th = -math.pi / 2 + 2 * math.pi * i / max(1, len(ring))
        placed[nm] = G.polar(W / 2, H / 2, min(W, H) * 0.42, th)

    if ring:
        one = len(ring) == 1
        plan.meta.warnings.append(
            f"{len(ring)} place{'' if one else 's'} on this chart "
            f"{'has' if one else 'have'} no latitude and longitude, so "
            f"{'it is' if one else 'they are'} laid out round the edge "
            f"instead: {', '.join(sorted(ring)[:4])}"
            f"{'…' if len(ring) > 4 else ''}. Open one of those people, "
            f"open the place on their birth, and give it coordinates.")

    # Biggest first, so where two places overlap the one that mattered keeps
    # its name. Set at heading size: there are ten of these on a metre of
    # sheet, not four hundred.
    lp = LabelPlacer(cell_mm=20.0)
    for nm, (x, y) in sorted(placed.items(), key=lambda kv: -len(named[kv[0]])):
        people = named[nm]
        n = len(people)
        r = max(2.4, math.sqrt(n) * 2.4)
        plan.add(Element(kind="circle", layer="ENGRAVE", x=x, y=y, r=r,
                         stroke=col, stroke_width=lw, fill=col, opacity=0.22,
                         role="place", z=4))
        # ONE MARK PER PERSON, not one per place. A disc whose area is a
        # headcount is a picture of a number; hover, search, highlighting and
        # the what-if overlay all work by finding the element that carries a
        # person on it, and with only the place drawn there was nothing on
        # this design to click. Set in a ring round the place so the count is
        # still readable at a glance.
        ring_r = r + max(1.4, lw * 4)
        for i, pid in enumerate(sorted(people,
                                       key=lambda p: graph.people[p].birth_year
                                       or 9999)):
            th = -math.pi / 2 + 2 * math.pi * i / n
            px, py = G.polar(x, y, ring_r, th)
            plan.add(Element(kind="circle", layer="ENGRAVE", x=px, y=py,
                             r=max(0.6, lw * 1.8), stroke=col,
                             stroke_width=lw * 0.5,
                             fill=colour_for(graph.people[pid], g.slots[pid],
                                             style, graph),
                             person_id=pid, role="node", z=6))
        fs = size * 1.6
        for dy in (-ring_r - fs * 0.9, ring_r + fs * 1.3):
            box = lp.box_for(nm, x, y + dy, fs, 0.0, "middle")
            if lp.free(box):
                lp.take(box)
                _label(plan, f"{nm} · {n}", x, y + dy, fs, col)
                break

    # HOW THE FAMILY MOVED: a line from where a parent was born to where
    # their child was, which is the only migration a family tree can honestly
    # claim to know.
    moves: dict = {}
    for pid in g.slots:
        a = (graph.people[pid].birth_place or "").strip()
        for kid in graph.children(pid):
            if kid not in within:
                continue
            b = (graph.people[kid].birth_place or "").strip()
            if a and b and a != b and a in placed and b in placed:
                moves.setdefault((a, b), []).append(kid)
    for (a, b), movers in moves.items():
        (x0, y0), (x1, y1) = placed[a], placed[b]
        n = len(movers)
        plan.add(Element(kind="path", layer="ENGRAVE",
                         d=_bow(x0, y0, x1, y1, W / 2, H / 2, 0.12),
                         stroke=col, stroke_width=lw * min(4.0, 0.8 + n * 0.35),
                         fill="none", opacity=0.5, person_id=movers[0],
                         role="move", z=2))
    plan.meta.extra["places"] = len(placed)
    plan.meta.extra["migrations"] = len(moves)
    add_title(plan, style, W / 2, m * 0.7)
    return plan


# ═════════════════════════════ 6. STAR CHART ═════════════════════════════
@register("constellation", "Star Chart", "spatial",
          "The family as a night sky: each person a star whose brightness is "
          "how many descend from them, joined by the lines of descent.",
          good_for="A piece for a wall. Beautiful rather than analytical, "
                   "and it engraves superbly on dark stock.",
          laser="good")
def constellation(graph, s, style) -> RenderPlan:
    plan, g, W, H, m = _frame(graph, s, style, 900.0, 900.0)
    col = style.get("colour.ink", "#26241F")
    lw = style.get("connectors.width_mm", 0.35)
    size = style.get("type.size_mm", 2.8)
    within = set(g.slots)
    cx, cy = W / 2, H / 2
    rmax = min(W, H) / 2 - m - 6

    # Generation is the radius and the spread axis is the angle, so the
    # oldest are at the centre — the same reading as the flagship, which
    # means somebody who knows one chart can read this one.
    at: dict = {}
    for pid, sl in g.slots.items():
        r = rmax * (0.14 + 0.86 * (sl.gen / max(1, g.max_gen)))
        th = -math.pi / 2 + 2 * math.pi * sl.tc
        at[pid] = G.polar(cx, cy, r, th)

    for pid in g.slots:
        for kid in graph.children(pid):
            if kid in at:
                (x0, y0), (x1, y1) = at[pid], at[kid]
                plan.add(Element(kind="path", layer="ENGRAVE",
                                 d=f"M {x0:.3f},{y0:.3f} L {x1:.3f},{y1:.3f}",
                                 stroke=col, stroke_width=lw, fill="none",
                                 opacity=0.55, person_id=pid, role="edge", z=2))

    big = max(_descend(graph, p, within) for p in within) if within else 1
    placer = LabelPlacer(cell_mm=10.0)
    # BRIGHTEST FIRST, which is the whole reason to sort here: the placer is
    # greedy, so whoever asks first keeps their name. Ask in file order and a
    # childless in-law takes the space belonging to the founder beside them.
    for pid, (x, y) in sorted(at.items(),
                              key=lambda kv: -_descend(graph, kv[0], within)):
        n = _descend(graph, pid, within)
        # Brightness as a magnitude, not a count: doubling the descendants
        # should not double the disc, or one founder swallows the sky.
        r = 0.9 + 2.8 * math.sqrt(n / big)
        plan.add(Element(kind="circle", layer="ENGRAVE", x=x, y=y, r=r,
                         stroke=col, stroke_width=lw * 0.6,
                         fill=colour_for(graph.people[pid], g.slots[pid], style, graph),
                         person_id=pid, role="star", z=6))
        if n > big * 0.06 or g.slots[pid].gen == 0:
            place_label(plan, placer, graph.people[pid],
                        graph.people[pid].short_name, x, y - r - size * 0.45,
                        style, size=size)
    _report(plan, placer)
    add_title(plan, style, cx, m * 0.8)
    return plan
