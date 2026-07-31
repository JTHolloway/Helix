"""The couple-cell layout: one cell per marriage, rings from the founders.

These encode what `couple_grid.py` promises that the one-slot-per-person
layout could not. Read the promise before changing a test:

  * a child is exactly one ring outside their parents, so the descent line
    runs along a radius and can be traced with a finger
  * NOBODY stands under a sibling arc except that couple's own children --
    not a cousin, and not one of the siblings' own husbands or wives, which
    the angular layout had no way to avoid
  * a married couple is one cell, so marriage needs no tie line at all
  * two cells never share an angle
"""
from __future__ import annotations

import pytest

from helix.layout import registry
from helix.layout.base import LayoutSettings, build_grid
from helix.layout.engines import family  # noqa: F401
from helix.style.tokens import Style

FOCUSES = ["thread_siblings", "bloodline", "subtree", "all"]


def cellgrid(graph, focus="bloodline"):
    return build_grid(graph, LayoutSettings(engine="radial_family", cells=True,
                                            subject_id=graph.subject_id,
                                            focus=focus))


def _primary_kids(graph, uid, union, g):
    """The children an arc is actually drawn over.

    Row 0 only. A daughter who is on the chart solely as somebody's wife is
    drawn inside her husband's cell, on the row below, and the arc over her
    parents' children does not reach her -- it cannot, and should not try.
    """
    return [c for c in union.children
            if c in g.slots and g.slots[c].row == 0
            and graph.people[c].child_of == uid]


@pytest.mark.parametrize("focus", FOCUSES)
def test_a_child_is_exactly_one_ring_out(graph, focus):
    """What makes the chart traceable. Measuring rings from the subject
    instead let the line to a great-grandparent swing a hundred degrees
    across the disc, because parent and child were angular neighbours
    competing with siblings for the same two sides."""
    g = cellgrid(graph, focus)
    for pid, sl in g.slots.items():
        if sl.row:                       # married in; holds no ring of their own
            continue
        if sl.parent and sl.parent in g.slots:
            assert g.slots[sl.parent].gen == sl.gen - 1, (
                f"{focus}: {graph.people[pid].full_name} is {sl.gen} and their "
                f"parent is {g.slots[sl.parent].gen}")


@pytest.mark.parametrize("focus", FOCUSES)
def test_nobody_at_all_stands_under_a_sibling_arc(graph, focus):
    """The strict version. The old layout could only promise "no STRANGER
    under the arc" -- a sibling's own husband or wife was unavoidable,
    because they sat on their partner's ring by definition. Putting the
    spouse on the row below removes the exception entirely."""
    g = cellgrid(graph, focus)
    for uid, u in graph.unions.items():
        kids = _primary_kids(graph, uid, u, g)
        if len(kids) < 2:
            continue
        kidset = set(kids)
        lo = min(g.slots[c].tc for c in kids)
        hi = max(g.slots[c].tc for c in kids)
        for pid in g.by_gen.get(g.slots[kids[0]].gen, []):
            if pid in kidset or g.slots[pid].row:
                continue
            assert not (lo <= g.slots[pid].tc <= hi), (
                f"{focus}: {graph.people[pid].full_name} stands under the arc "
                f"over another couple's children")


@pytest.mark.parametrize("focus", FOCUSES)
def test_a_marriage_is_one_cell(graph, focus):
    """Two names in one cell IS the marriage. The only exception is two
    people both born into the tree -- cousins marrying -- where only one of
    them can hold the cell and the other keeps their own place."""
    g = cellgrid(graph, focus)
    scope = set(g.slots)
    for u in graph.unions.values():
        ps = [x for x in u.partners if x in g.slots]
        if len(ps) != 2:
            continue
        a, b = ps
        if g.slots[a].cell == g.slots[b].cell:
            assert g.slots[a].tc == g.slots[b].tc, "one cell, one angle"
            assert g.slots[a].row != g.slots[b].row, "one cell, two rows"
            continue
        both_born_in = all(
            any(x in scope for x in graph.parents(p, primary_only=False))
            for p in ps)
        assert both_born_in, (
            f"{focus}: {graph.people[a].full_name} and "
            f"{graph.people[b].full_name} are married and in different cells, "
            f"but only one of them was born into the tree")


@pytest.mark.parametrize("focus", FOCUSES)
def test_two_cells_never_share_an_angle(graph, focus):
    g = cellgrid(graph, focus)
    for gen, people in g.by_gen.items():
        at = {}
        for p in people:
            at.setdefault(g.slots[p].cell or p, g.slots[p].tc)
        order = sorted(at.values())
        for a, b in zip(order, order[1:]):
            assert (b - a) * 360 > 0.4, f"{focus}: two cells on ring {gen} coincide"


@pytest.mark.parametrize("focus", FOCUSES)
def test_everyone_in_scope_is_drawn_once(graph, focus):
    g = cellgrid(graph, focus)
    from helix.layout.subject_grid import _scope
    scope = _scope(graph, LayoutSettings(engine="radial_family",
                                         subject_id=graph.subject_id,
                                         focus=focus), graph.subject_id)
    assert set(g.slots) == scope
    assert len(g.order) == len(set(g.order))


def test_the_design_draws_what_it_promises(graph):
    """Marriage as cells, one arc per sibling group, one stem per family."""
    style = Style.load("panel1m")
    s = LayoutSettings(engine="radial_family", subject_id=graph.subject_id,
                       focus="bloodline")
    plan = registry.run("radial_family", graph, s, style)
    roles = {}
    for e in plan.elements:
        roles[e.role] = roles.get(e.role, 0) + 1
    assert roles.get("marriage", 0) > 5, "couples should be drawn as cells"
    assert roles.get("siblings", 0) > 5, "sibling groups should have arcs"
    assert roles.get("stem", 0) > 5, "families should hang off their parents"
    assert roles.get("label", 0) > 20
    for e in plan.elements:
        if e.kind == "path":
            assert "nan" not in e.d.lower()


# --------------------------------------------------------------- remarriage --
@pytest.fixture
def remarried(tmp_path):
    """A man with children by two women. The sample family has none, and it
    is the case the stacked rows exist for."""
    from helix.graph import build
    from helix.store import records
    from helix.store.db import connect, set_setting
    con = connect(tmp_path / "r.helix")

    def add(given, surname, to=None, how=None, union=None, **kw):
        body = {"given": given, "surname": surname, **kw}
        if to:
            body["attach"] = {"to": to, "as": how, "union": union}
        return records.add_person(con, body)["id"]

    gran = add("Arthur", "Pargeter", birth="1935")
    dad = add("Michael", "Pargeter", gran, "child", birth="1962")
    add("Susan", "Hallam", dad, "partner", birth="1964")
    g0 = build.load(con)
    u_susan = g0.people[dad].unions[0]
    add("James", "Pargeter", dad, "child", union=u_susan, birth="1992")
    add("Rachel", "Dunmore", dad, "partner", birth="1960")
    g1 = build.load(con)
    u_rachel = [u for u in g1.people[dad].unions if u != u_susan][0]
    add("Hannah", "Pargeter", dad, "child", union=u_rachel, birth="1986")
    set_setting(con, "subject_person_id", dad)
    return build.load(con), dad


def test_two_marriages_that_both_had_children_get_a_leaf_each(remarried):
    """Stacked, a man's two wives sit under him with both families hanging
    off one leaf, and which children are whose stops being something you can
    SEE -- it becomes something you work out from which row a stem left.

    Given a leaf each the order reads [ first wife ][ HIM ][ second wife ],
    with a rule between each married pair and each family's stem leaving
    from between the right two. One marriage is different and stays stacked
    however many children it had: there is only one family, so there is
    nothing to tell apart.
    """
    graph, dad = remarried
    g = cellgrid(graph, "all")
    cell = g.slots[dad].cell
    members = sorted([sl for sl in g.slots.values() if sl.cell == cell],
                     key=lambda x: x.tc)
    names = [graph.people[m.pid].full_name for m in members]
    assert set(names) == {"Michael Pargeter", "Susan Hallam", "Rachel Dunmore"}
    assert all(m.row == 0 for m in members), "a leaf each, side by side"
    assert len({m.tc for m in members}) == 3, "three leaves, three angles"
    assert names[1] == "Michael Pargeter", (
        "the twice-married one goes in the middle, so both marriages are "
        f"between neighbours -- got {names}")


def test_one_marriage_still_shares_a_leaf(remarried):
    """The other half of the same rule, and the owner's own distinction:
    Doreen, who married twice, against Heather, who married once."""
    graph, dad = remarried
    g = cellgrid(graph, "all")
    once = [p for p in graph.people
            if p in g.slots and p != dad
            and len([u for u in graph.people[p].unions
                     if any(c in g.slots for c in graph.unions[u].children)]) == 1
            and len([q for q in g.slots
                     if g.slots[q].cell == g.slots[p].cell]) > 1]
    for p in once:
        mates = [g.slots[q] for q in g.slots
                 if g.slots[q].cell == g.slots[p].cell]
        if any(len([u for u in graph.people[m.pid].unions
                    if any(c in g.slots for c in graph.unions[u].children)]) > 1
               for m in mates):
            continue
        assert len({m.tc for m in mates}) == 1, (
            f"{graph.people[p].full_name} married once and should share a leaf")


def test_both_sets_of_children_hang_off_that_one_cell(remarried):
    """A half-sister is a child of the same cell, one ring out, and the stem
    to her leaves from her own mother's row -- so which mother is readable
    without a dash or a legend."""
    graph, dad = remarried
    g = cellgrid(graph, "all")
    kids = {graph.people[c].full_name: g.slots[c]
            for c in graph.children(dad) if c in g.slots}
    assert set(kids) == {"James Pargeter", "Hannah Pargeter"}
    for sl in kids.values():
        assert sl.gen == g.slots[dad].gen + 1

    style = Style.load("panel1m")
    plan = registry.run("radial_family", graph,
                        LayoutSettings(engine="radial_family",
                                       subject_id=dad, focus="all"), style)
    stems = [e for e in plan.elements if e.role == "stem"]
    rows = {g.slots[e.person_id].row for e in stems
            if e.person_id in g.slots and e.person_id != dad}
    assert rows, "each family's stem should leave from a partner's own row"


# ------------------------------------------------------------- the settings --
def _spread(graph, style_kw, names):
    """Degrees between the first and last of `names`, as drawn."""
    from dataclasses import replace
    from helix.layout.base import build_grid
    style = Style.load("panel1m")
    style.set("canvas.width_mm", 800)
    style.set("canvas.height_mm", 800)
    for k, v in style_kw.items():
        style.set(k, v)
    plan = registry.run("radial_family", graph,
                        LayoutSettings(engine="radial_family", focus="all",
                                       subject_id=graph.subject_id), style)
    pts = {e.person_id: (e.x, e.y) for e in plan.elements
           if e.role == "label" and e.person_id}
    import math
    cx = cy = plan.canvas.width_mm / 2
    ang = []
    for n in names:
        pid = next(p for p, q in graph.people.items() if q.full_name == n)
        if pid in pts:
            x, y = pts[pid]
            ang.append(math.degrees(math.atan2(y - cy, x - cx)))
    return max(ang) - min(ang) if len(ang) > 1 else 0.0


def test_siblings_can_be_pulled_closer_together(graph):
    """Three brothers should read as three brothers. The gap between them is
    a setting, and turning it down has to actually move them."""
    from dataclasses import replace
    from helix.layout.base import build_grid

    def gap_between_siblings(sib):
        """How far apart three brothers sit, IN CELLS. Measuring the raw
        0..1 spread instead says almost nothing: pulling the siblings in
        shrinks the whole chart too, so the fraction barely moves. A cell is
        one couple, and it is the unit the eye actually uses."""
        g = build_grid(graph, replace(
            LayoutSettings(engine="radial_family", focus="bloodline",
                           subject_id=graph.subject_id),
            cells=True, sibling_gap=sib, family_gap=0.6))
        cell = max(sl.t1 - sl.t0 for sl in g)
        worst = 0.0
        for uid, u in graph.unions.items():
            kids = [c for c in u.children
                    if c in g.slots and g.slots[c].row == 0
                    and graph.people[c].child_of == uid]
            if len(kids) < 3:
                continue
            ts = sorted(g.slots[c].tc for c in kids)
            worst = max(worst, (ts[-1] - ts[0]) / cell)
        return worst

    tight, loose = gap_between_siblings(0.05), gap_between_siblings(1.2)
    assert tight < loose, "turning the sibling gap down must bring them closer"
    assert tight < loose * 0.8, "and by a useful amount, not a rounding error"


def test_a_sparse_family_is_drawn_as_a_fan(graph):
    """A small tree cannot fill a disc. Stretched round the full circle,
    three siblings end up forty degrees apart; capped, the chart draws as a
    fan of the angle it needs and they stay together."""
    import math
    style = Style.load("panel1m")
    style.set("layout.max_cell_deg", 6.0)
    s = LayoutSettings(engine="radial_family", focus="thread",
                       subject_id=graph.subject_id)
    plan = registry.run("radial_family", graph, s, style)
    cx = cy = plan.canvas.width_mm / 2
    ang = [math.degrees(math.atan2(e.y - cy, e.x - cx)) % 360
           for e in plan.elements if e.role == "label" and e.person_id]
    assert ang, "nothing was drawn"
    used = max(ang) - min(ang)
    assert used < 359, "a sparse family should not be stretched round the disc"


def test_the_cap_does_not_bite_on_a_full_chart(graph):
    """A real family fills the circle, and the cap must leave it alone."""
    import math
    style = Style.load("panel1m")
    s = LayoutSettings(engine="radial_family", focus="all",
                       subject_id=graph.subject_id)
    plan = registry.run("radial_family", graph, s, style)
    cx = cy = plan.canvas.width_mm / 2
    ang = [math.degrees(math.atan2(e.y - cy, e.x - cx)) % 360
           for e in plan.elements if e.role == "label" and e.person_id]
    assert max(ang) - min(ang) > 300, "a 400-person family should use the disc"


# ------------------------------------------------- the sheet it is cut from --
def _drawn(plan):
    """The box the ink actually occupies, in millimetres.

    Through `pathflatten`, not a regex over the path data: `H` and `V` carry
    one number, not two, and pairing them off blind reported a 471 mm wide
    outline as 471 mm TALL and failed a test the layout had got right.
    """
    from helix.render import pathflatten
    xs, ys = [], []
    for e in plan.elements:
        for pts, _ in pathflatten.flatten(e):
            xs += [p[0] for p in pts]
            ys += [p[1] for p in pts]
        if getattr(e, "x", None) is not None:
            xs.append(e.x)
            ys.append(e.y)
    return min(xs), min(ys), max(xs), max(ys)


def _panelled(graph, w, h, focus="bloodline", **tokens):
    style = Style.load("panel1m")
    style.set("canvas.width_mm", w)
    style.set("canvas.height_mm", h)
    for k, v in tokens.items():
        style.set(k.replace("__", "."), v)
    return registry.run("radial_family", graph,
                        LayoutSettings(engine="radial_family", focus=focus,
                                       subject_id=graph.subject_id), style)


@pytest.mark.parametrize("panel", [(800, 800), (600, 900), (1200, 400)])
@pytest.mark.parametrize("focus", ["thread", "bloodline", "all"])
def test_the_chart_never_overruns_the_sheet(graph, panel, focus):
    """The panel is the material. Whatever angle the chart chooses, the ink
    has to land on it -- a fan that reported itself 3 mm over a metre panel
    was measuring the DISC it was cut from rather than its own sector."""
    plan = _panelled(graph, *panel, focus=focus)
    x0, y0, x1, y1 = _drawn(plan)
    assert x1 - x0 <= panel[0] + 0.5, f"{focus} {panel}: {x1 - x0:.0f} mm wide"
    assert y1 - y0 <= panel[1] + 0.5, f"{focus} {panel}: {y1 - y0:.0f} mm tall"


@pytest.mark.parametrize("focus", ["thread", "bloodline", "all"])
def test_the_canvas_is_the_chart_not_the_sheet(graph, focus):
    """A fan needing 760 x 440 gets a 760 x 440 canvas, cut from the metre
    panel with the rest left on the roll. Sizing the canvas to the sheet
    instead left a third of it blank, which is what "sparse" was."""
    plan = _panelled(graph, 800, 800, focus=focus)
    x0, y0, x1, y1 = _drawn(plan)
    for used, whole, way in ((x1 - x0, plan.canvas.width_mm, "across"),
                             (y1 - y0, plan.canvas.height_mm, "down")):
        assert used > whole * 0.75, (
            f"{focus}: {used:.0f} mm of ink {way} a {whole:.0f} mm canvas")


@pytest.mark.parametrize("focus", ["thread", "bloodline", "all"])
def test_the_hole_in_the_middle_stays_a_hole(graph, focus):
    """Sized from the innermost ring, so it can never crowd -- but sized
    from the NARROWEST cell on that ring it ballooned to a third of the
    sheet, because one thin cell is thin for reasons the hole cannot fix."""
    plan = _panelled(graph, 800, 800, focus=focus)
    fit = plan.meta.extra["fit"]
    reach = max(fit["chart_mm"]) / 2
    assert fit["inner_mm"] < reach * 0.75, (
        f"{focus}: a {fit['inner_mm']:.0f} mm hole in a {reach * 2:.0f} mm chart")


# --------------------------------------------------- the family wedges --
def _wedges(plan):
    return [e for e in plan.elements if e.role == "family"]


@pytest.mark.parametrize("focus", ["bloodline", "all"])
def test_every_family_gets_ground_of_its_own(graph, focus):
    """The whole point of the tint: more than one, so the eye can tell one
    family from another. One wedge over the entire chart says nothing, which
    is what a descendancy chart got until the rule learned to drop down a
    generation when a founder's descendants ARE the chart.

    `thread` is left out on purpose. It is one line of descent, every couple
    on it married in from off the chart, and one family is the truth."""
    plan = _panelled(graph, 1000, 1000, focus=focus, family__wedges=True)
    fills = {e.fill for e in _wedges(plan)}
    assert len(fills) >= 2, f"{focus}: {len(fills)} family colour(s) on the chart"


def test_the_wedges_never_reach_the_cutter(graph):
    """They are ink on paper, not a cut. `PRINT_ONLY` is the layer that says
    so, and every writer drops it in production."""
    plan = _panelled(graph, 1000, 1000, family__wedges=True)
    assert _wedges(plan), "no wedges were drawn at all"
    assert all(e.layer == "PRINT_ONLY" for e in _wedges(plan))


def test_the_wedges_are_off_unless_asked_for(graph):
    """A reading aid, not part of the chart. A rendered file is the chart and
    nothing else; the control panel is where you turn them on."""
    assert not _wedges(_panelled(graph, 1000, 1000))
    assert _wedges(_panelled(graph, 1000, 1000, family__wedges=True))


def test_two_lines_that_marry_share_their_descendants(graph):
    """A marriage between two families is not drawn. It does not have to be:
    from that ring outward both families cover the same ground, so the two
    tints lie on top of each other and the blend IS the marriage. If no two
    wedges ever overlap, that has stopped working."""
    import math
    plan = _panelled(graph, 1000, 1000, focus="bloodline", family__wedges=True)
    cx, cy = plan.canvas.width_mm / 2, plan.canvas.height_mm / 2
    spans = {}
    for e in _wedges(plan):
        pts = [(float(a), float(b)) for a, b in
               __import__("re").findall(r'(-?\d+\.?\d*)[ ,](-?\d+\.?\d*)', e.d)]
        rs = [math.hypot(x - cx, y - cy) for x, y in pts]
        ts = [math.atan2(y - cy, x - cx) % (2 * math.pi) for x, y in pts]
        spans.setdefault(e.fill, []).append((round(min(rs)), min(ts), max(ts)))
    hits = 0
    for a in spans:
        for b in spans:
            if a >= b:
                continue
            for ra, a0, a1 in spans[a]:
                for rb, b0, b1 in spans[b]:
                    if ra == rb and a0 < b1 and b0 < a1:
                        hits += 1
    assert hits, "no two family wedges ever cover the same ground"


def test_a_sparse_family_is_given_the_angle_it_needs(graph):
    """The grid pads a small family out so one couple cannot own a quadrant,
    and the fan does the same job again. Left in both places the chart drew
    across 60% of its own sweep and left the rest blank."""
    plan = _panelled(graph, 800, 800, focus="thread")
    fit = plan.meta.extra["fit"]
    assert fit["cell_arc_mm"] >= 8.0, (
        f"the tightest couple got {fit['cell_arc_mm']:.1f} mm of arc")


# ------------------------------------------------------ shared vs split leaf --
def _leaves(graph, mode, focus="bloodline"):
    from dataclasses import replace
    from helix.layout.base import build_grid
    g = build_grid(graph, replace(
        LayoutSettings(engine="radial_family", subject_id=graph.subject_id,
                       focus=focus), cells=True, couple_leaf=mode))
    cells = {}
    for sl in g.slots.values():
        cells.setdefault(sl.cell, []).append(sl)
    return g, cells


def _is_split(members):
    return len(members) > 1 and all(m.row == 0 for m in members)


def test_shared_leaves_stack_and_split_leaves_sit_side_by_side(graph):
    g, cells = _leaves(graph, "shared")
    for members in cells.values():
        if len(members) < 2:
            continue
        assert len({m.tc for m in members}) == 1, "shared: one leaf, one angle"
        assert len({m.row for m in members}) == len(members), "stacked rows"

    g, cells = _leaves(graph, "split")
    couples = [m for m in cells.values() if len(m) > 1]
    assert couples, "the sample has married couples"
    for members in couples:
        assert _is_split(members), "split: a leaf each"
        assert len({m.tc for m in members}) == len(members), "side by side"
        assert all(m.row == 0 for m in members), "same ring, not stacked"


def test_auto_splits_only_where_a_shared_leaf_would_be_ambiguous(graph):
    """A shared leaf holding two ancestries cannot say which is whose. That
    is the ONLY thing wrong with it, so it is the only thing that triggers a
    split -- and it needs both partners to have parents on the chart, which
    is rare."""
    g, cells = _leaves(graph, "auto")
    for anchor, members in cells.items():
        if not _is_split(members):
            continue
        with_parents = [m for m in members
                        if any(x in g.slots for x in
                               graph.parents(m.pid, primary_only=False))]
        assert len(with_parents) > 1, (
            f"{graph.people[anchor].full_name} was split but only one of them "
            f"has parents on the chart -- sharing was not ambiguous")


def test_auto_is_never_wider_than_forcing_split(graph):
    """Auto exists to spend width only where it buys clarity."""
    _, auto = _leaves(graph, "auto")
    _, forced = _leaves(graph, "split")
    n_auto = sum(1 for m in auto.values() if _is_split(m))
    n_forced = sum(1 for m in forced.values() if _is_split(m))
    assert n_auto <= n_forced


def test_a_split_couple_still_hangs_its_children_from_between_them(graph):
    """Children of a marriage belong to the marriage, not to one partner, so
    the stem leaves from between the two leaves."""
    style = Style.load("panel1m")
    style.set("couple.leaf", "split")
    plan = registry.run("radial_family", graph,
                        LayoutSettings(engine="radial_family", focus="bloodline",
                                       subject_id=graph.subject_id), style)
    assert any(e.role == "marriage" for e in plan.elements), \
        "a split couple needs a tie -- it is the one line this design must draw"
    assert any(e.role == "stem" for e in plan.elements)


# ------------------------------------------- whose line is it, in a leaf --
@pytest.mark.parametrize("focus", ["thread", "bloodline", "all"])
def test_a_stacked_name_never_owns_somebody_elses_ancestry(graph, focus):
    """The rule the shared leaf turns on.

    Two names in one leaf are read as "this couple, and the line inward is
    the top one's". So the only person who may be stacked UNDER is somebody
    who married in from off the chart and brings no line with them. A wife
    with three recorded generations behind her sitting on row 1, under a
    husband who married in from nowhere, hands her whole ancestry to him --
    three couples on the owner's own tree did exactly that.
    """
    g, cells = _leaves(graph, "auto", focus)
    scope = set(g.slots)
    for members in cells.values():
        if len(members) < 2 or _is_split(members):
            continue
        members.sort(key=lambda m: m.row)
        for under in members[1:]:
            line = [p for p in graph.parents(under.pid, primary_only=False)
                    if p in scope]
            assert not line, (
                f"{focus}: {graph.people[under.pid].full_name} is stacked "
                f"under {graph.people[members[0].pid].full_name} but has "
                f"parents on this chart")


@pytest.mark.parametrize("focus", ["bloodline", "all"])
def test_two_lines_meeting_get_a_leaf_each(graph, focus):
    """When BOTH partners have parents on the chart there is no top name that
    could own both, so the leaf has to split."""
    g, cells = _leaves(graph, "auto", focus)
    scope = set(g.slots)
    for members in cells.values():
        if len(members) < 2:
            continue
        lines = sum(1 for m in members
                    if any(p in scope
                           for p in graph.parents(m.pid, primary_only=False)))
        if lines > 1:
            assert _is_split(members), (
                f"{focus}: {lines} ancestries sharing one leaf")


def test_the_direct_line_highlight_is_a_setting(graph):
    """It is a highlight, not a relationship: every line it recolours is
    drawn either way. So turning it off has to leave the chart complete."""
    on = _panelled(graph, 800, 800)
    off = _panelled(graph, 800, 800, thread__enabled=False)
    assert len(on.elements) == len(off.elements), "the chart lost something"
    tcol = Style.load("panel1m").get("thread.colour", "#9B3A2E")
    assert [e for e in on.elements if e.stroke == tcol]
    assert not [e for e in off.elements if e.stroke == tcol]


# ------------------------------------------ every line reaches what it means --
def _paths_by_union(plan):
    from helix.render import pathflatten
    out = {}
    for e in plan.elements:
        if e.role not in ("stem", "siblings", "branch") or not e.union_id:
            continue
        pts = [p for pp, _ in pathflatten.flatten(e) for p in pp]
        out.setdefault(e.union_id, {}).setdefault(e.role, []).extend(pts)
    return out


@pytest.mark.parametrize("focus", ["thread", "bloodline", "all"])
def test_every_stem_reaches_its_own_children(graph, focus):
    """A stem that stops short of the arc it belongs to is not a shortcut,
    it is a lie about who somebody's parents are -- and it is what "branches
    that stem from nothing" looks like.

    A cell is centred over ALL its children, both marriages together, so a
    stem drawn from the middle of the cell points at the middle of both. For
    either family on its own that is off to one side: five stems on a real
    142-person tree ended up as much as 16 mm clear of the arc they were
    supposed to meet.
    """
    import math
    plan = _panelled(graph, 1000, 1000, focus=focus)
    for uid, d in _paths_by_union(plan).items():
        if "stem" not in d:
            continue
        others = d.get("siblings", []) + d.get("branch", [])
        if not others:
            continue
        tip = d["stem"][-1]
        gap = min(math.hypot(tip[0] - q[0], tip[1] - q[1]) for q in others)
        assert gap < 1.5, (
            f"{focus}: a stem ends {gap:.0f} mm from the arc over its own "
            f"children: {[graph.people[c].full_name for c in graph.unions[uid].children][:3]}")


def _components(pairs, everyone):
    adj: dict = {}
    for a, b in pairs:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    seen, out = set(), []
    for p in everyone:
        if p in seen:
            continue
        stack, comp = [p], set()
        while stack:
            q = stack.pop()
            if q in comp:
                continue
            comp.add(q)
            seen.add(q)
            stack += [x for x in adj.get(q, ()) if x not in comp]
        out.append(comp)
    return out


@pytest.mark.parametrize("focus", FOCUSES)
def test_the_chart_never_splits_a_family_that_is_joined(graph, focus):
    """Whoever is related in the FILE must be joined on the CHART.

    Stated relative to the data on purpose. A chart cannot join two families
    that have no relation to each other -- the shipped sample file happens to
    hold 97 unrelated groups, which is a fault in the generator and not in
    the layout -- but it must never take a family that IS connected and draw
    it in pieces. That is what "branches disconnected from any previous ring"
    would be, and it is the thing to hold at zero.
    """
    g = cellgrid(graph, focus)
    want = []
    for u in graph.unions.values():
        ps = [p for p in u.partners if p in g.slots]
        want += list(zip(ps, ps[1:]))
        want += [(ps[0], c) for c in u.children if c in g.slots and ps]
    in_data = _components(want, list(g.slots))
    drawn = list(want)
    bycell: dict = {}
    for pid in g.slots:
        bycell.setdefault(g.slots[pid].cell or pid, []).append(pid)
    for m in bycell.values():
        drawn += list(zip(m, m[1:]))
    in_chart = _components(drawn, list(g.slots))
    assert len(in_chart) <= len(in_data), (
        f"{focus}: the file holds {len(in_data)} related groups but the chart "
        f"draws {len(in_chart)} -- it has split a family that is joined")


def _runs_of(graph, g, uid, kids):
    """The contiguous runs a couple's children fall into on their ring --
    which is what the chart draws an arc over, one arc each."""
    S = g.slots
    ring = sorted({(S[p].tc, S[p].cell or p)
                   for p in g.by_gen.get(S[kids[0]].gen, []) if S[p].row == 0})
    own = {S[c].cell or c for c in kids}
    runs, cur = [], []
    for tc, cid in ring:
        if cid in own:
            cur.append(tc)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return runs or [sorted(S[c].tc for c in kids)]


@pytest.mark.parametrize("focus", FOCUSES)
def test_an_arc_never_covers_a_stranger(graph, focus):
    """THE rule, and it is absolute: an arc may only ever cover children of
    that marriage, or one of those children's own husbands or wives.

    Never a cousin, never a half-brother by the other marriage, never a
    spouse of one of the parents. Drawn as a single arc from the first child
    to the last it covered whoever the layout put in between, and the layout
    cannot always avoid putting somebody there -- a couple belongs to two
    sibling groups at once and can be nested in only one. So the chart stopped
    promising what the layout cannot deliver: the children are split into runs
    that ARE side by side and each run gets its own arc. Two arcs off one
    couple say "two of them here and two there", which is true; one arc across
    the gap says they are all brothers and sisters with strangers among them.
    """
    g = cellgrid(graph, focus)
    for uid, u in graph.unions.items():
        kids = [c for c in u.children
                if c in g.slots and graph.people[c].child_of == uid]
        if len(kids) < 2:
            continue
        ks = set(kids)
        runs = _runs_of(graph, g, uid, kids)
        for pid in g.by_gen.get(g.slots[kids[0]].gen, []):
            if pid in ks or g.slots[pid].row:
                continue
            if not any(r[0] <= g.slots[pid].tc <= r[-1] for r in runs):
                continue
            assert any(x in ks for x in graph.partners(pid)), (
                f"{focus}: {graph.people[pid].full_name} is under the arc over "
                f"{[graph.people[c].full_name for c in kids[:3]]} and is not "
                f"one of them, nor married to one of them")


@pytest.mark.parametrize("focus", ["bloodline", "all"])
def test_no_two_sibling_arcs_on_a_ring_overlap(graph, focus):
    """Two arcs at the same radius that overlap draw as ONE ring, which says
    the people at both ends are brothers and sisters. Michaela's arc to her
    brother and David's to his were half a millimetre apart in radius and
    overlapped by thirteen degrees, so a husband and wife appeared to be
    siblings as well as spouses."""
    g = cellgrid(graph, focus)
    spans = []
    for uid, u in graph.unions.items():
        kids = [c for c in u.children
                if c in g.slots and graph.people[c].child_of == uid]
        if len(kids) < 2:
            continue
        gen = g.slots[kids[0]].gen
        for r in _runs_of(graph, g, uid, kids):
            spans.append((gen, r[0], r[-1], uid))
    for i, (ga, a0, a1, ua) in enumerate(spans):
        for gb, b0, b1, ub in spans[i + 1:]:
            if ga != gb or ua == ub:
                continue
            assert not (a0 < b1 and b0 < a1), (
                f"{focus}: two sibling arcs on ring {ga} overlap "
                f"({a0:.3f}-{a1:.3f} and {b0:.3f}-{b1:.3f})")


def test_a_partner_nobody_recorded_is_named_unknown(tmp_path):
    """Every set of children has two parents. A union with children and only
    one partner recorded is not somebody who had children alone, it is
    somebody whose partner is not known YET -- and one name with a blank
    beside it reads as though there never was one.

    Dashed, and never written to the file: the gap is a gap in the research.
    """
    from helix.graph import build
    from helix.store import records
    from helix.store.db import connect, set_setting
    con = connect(tmp_path / "u.helix")

    def add(given, surname, to=None, how=None, **kw):
        body = {"given": given, "surname": surname, **kw}
        if to:
            body["attach"] = {"to": to, "as": how}
        return records.add_person(con, body)["id"]

    dad = add("Michael", "Pargeter", birth="1930")
    add("James", "Pargeter", dad, "child", birth="1960")
    add("Claire", "Pargeter", dad, "child", birth="1962")
    set_setting(con, "subject_person_id", dad)
    graph = build.load(con)

    style = Style.load("panel1m")
    plan = registry.run("radial_family", graph,
                        LayoutSettings(engine="radial_family", focus="all",
                                       subject_id=dad), style)
    marks = [e for e in plan.elements if e.role == "unknown_partner"]
    assert marks, "two children and one parent, and nothing said so"
    assert all(e.dash for e in marks), "an unrecorded partner is dashed"
    said = [e for e in plan.elements
            if e.kind == "text" and (e.text or "").lower() == "unknown"]
    assert said, "the word itself should be on the chart"
    # and nothing was invented in the file
    assert len(build.load(con).people) == 3


# ---------------------------------------------- two lines that touch are one --
#
# Everything above measures what the layout MEANT. These measure the ink,
# because every fault the owner of this program found in a fortnight was two
# correct lines that happened to land close enough together to read as one,
# and no check that asks the layout a question can ever see that.
#
# `tools/ink_check.py` reports the same three numbers on any file.
def _ink(plan):
    """Every tangential run of ink on the chart, with the family it belongs
    to: (radius, from, to, sweep, family, role)."""
    import math

    from helix.render import pathflatten
    cx, cy = plan.meta.extra["centre_mm"]
    roles = {"siblings", "stem", "branch", "thread", "marriage",
             "unknown_partner", "chord"}
    out = []
    for el in plan.elements:
        if el.kind != "path" or el.role not in roles or not el.d:
            continue
        key = el.union_id or el.person_id or id(el)
        for pts, _closed in pathflatten.flatten(el, 0.25):
            pol = [(math.hypot(x - cx, y - cy), math.atan2(y - cy, x - cx))
                   for x, y in pts]
            runs, cur = [], [pol[0]]
            for b in pol[1:]:
                rs = [r for r, _ in cur] + [b[0]]
                # measured over the RUN: a stem curving round a narrow band
                # changes radius by a hair per step and by the whole band
                # overall, and step by step it is indistinguishable from an arc
                if max(rs) - min(rs) < 0.4:
                    cur.append(b)
                else:
                    runs.append(cur)
                    cur = [b]
            runs.append(cur)
            for run in runs:
                if len(run) < 2:
                    continue
                turn = sum(_wrap(b[1] - a[1]) for a, b in zip(run, run[1:]))
                r = sum(p[0] for p in run) / len(run)
                # long enough to read as a line: a stem curving across the
                # band is very nearly tangential for a millimetre or two in
                # the middle, and those scraps are not arcs
                if abs(turn) * r < 4.0:
                    continue
                lo, hi = ((run[0][1], run[0][1] + turn) if turn > 0
                          else (run[0][1] + turn, run[0][1]))
                if r > 1.0:
                    out.append((r, lo % math.tau, hi % math.tau,
                                abs(turn), key, el.role))
    return out


def _wrap(d):
    import math
    return (d + math.pi) % math.tau - math.pi


def _apart(a0, a1, b0, b1):
    """Angle between two spans, going round; zero if they meet or overlap."""
    import math

    def inside(x, lo, hi):
        return (x - lo) % math.tau <= (hi - lo) % math.tau + 1e-12

    if (inside(b0, a0, a1) or inside(b1, a0, a1)
            or inside(a0, b0, b1) or inside(a1, b0, b1)):
        return 0.0
    return min((b0 - a1) % math.tau, (a0 - b1) % math.tau)


@pytest.mark.parametrize("focus", FOCUSES)
def test_no_two_families_are_drawn_as_one_line(graph, focus):
    """THE one that kept coming back, and the reason this file now measures
    ink instead of intent.

    An elbow -- the tangential part of a stem, carrying it round to children
    lying off to one side -- used to be drawn at the radius of the sibling
    arcs. It never OVERLAPPED one, so every check passed. It ABUTTED them,
    end to end, at the same radius, which on the sheet is a single unbroken
    line running out of one family and into the next:

      * Paul, Derek and Gorden's arc ran on into the stem carrying Barry
        Viney, their half-brother by a different mother -- four children of
        two mothers on one branch;
      * the arc over Peter and his brother Richard ran on into the stem
        bringing Kathleen down from her own parents, which drew a man and
        his WIFE as brother and sister.

    Two millimetres is not a gap. Nothing else on this chart means "these
    people are one family" except a continuous line, so nothing else may
    look like one.
    """
    plan = _panelled(graph, 1000, 1000, focus=focus)
    ink = sorted(_ink(plan))
    for i, a in enumerate(ink):
        for b in ink[i + 1:]:
            if b[0] - a[0] > 1.6:
                break
            if a[4] == b[4]:
                continue
            gap = _apart(a[1], a[2], b[1], b[2]) * a[0]
            assert gap > 1.6 or abs(a[0] - b[0]) > 1.6, (
                f"{focus}: a {a[5]} and a {b[5]} of two different families "
                f"run into each other at r={a[0]:.0f} mm "
                f"({abs(a[0] - b[0]):.2f} mm apart, {gap:.2f} mm end to end)")


@pytest.mark.parametrize("focus", ["bloodline", "all"])
def test_an_arc_never_sweeps_further_than_its_own_children(graph, focus):
    """A sibling group really can be spread over most of the disc, so a long
    arc is not a fault in itself. An arc LONGER THAN THE CHILDREN IT HOLDS
    is: it went round the outside of the circle to reach its own last child,
    which happens when the family straddles the seam at the start angle and
    the angles are sorted as plain numbers.
    """
    import math

    from helix.render import pathflatten
    plan = _panelled(graph, 1000, 1000, focus=focus)
    cx, cy = plan.meta.extra["centre_mm"]
    t_start = plan.meta.extra["start_rad"]
    closed = plan.meta.extra["sweep_rad"] >= math.tau - 1e-9
    ticks: dict = {}
    for el in plan.elements:
        if el.kind != "path" or el.role not in ("branch", "thread") or not el.d:
            continue
        for pts, _c in pathflatten.flatten(el, 1.0):
            mx = (pts[0][0] + pts[-1][0]) / 2, (pts[0][1] + pts[-1][1]) / 2
            ticks.setdefault(el.union_id or "", []).append(
                math.atan2(mx[1] - cy, mx[0] - cx) % math.tau)
    pad = math.radians(0.5)          # an arc end and its own tick round apart
    for r, t0, t1, sweep, key, role in _ink(plan):
        if role != "siblings":
            continue
        angs = sorted(x for x in ticks.get(key, ())
                      if _apart(t0 - pad, t1 + pad, x, x) == 0.0)
        if len(angs) < 2:
            continue
        if closed:
            gaps = [b - a for a, b in zip(angs, angs[1:])]
            gaps.append(math.tau - (angs[-1] - angs[0]))
            need = math.tau - max(gaps)
        else:
            us = sorted((x - t_start) % math.tau for x in angs)
            need = us[-1] - us[0]
        assert sweep <= need + math.radians(2), (
            f"{focus}: an arc sweeps {math.degrees(sweep):.0f} deg to hold "
            f"children {math.degrees(need):.0f} deg apart -- it went the "
            f"long way round")


@pytest.mark.parametrize("focus", ["bloodline", "all"])
def test_no_line_is_drawn_through_a_name(graph, focus):
    """A name with a line through it is unreadable, and this chart's whole
    claim is that you can read it. The elbows are routed LAST, after the
    placer has settled where every name went, for exactly this reason."""
    import math

    from helix.layout.common import est_text_width
    from helix.render import pathflatten
    plan = _panelled(graph, 1000, 1000, focus=focus)
    boxes = []
    for el in plan.elements:
        if el.kind != "text" or not el.text:
            continue
        sz = el.font.size_mm if el.font else 3.0
        w, h = est_text_width(el.text, sz), sz * 1.05
        dx = {"start": 0.0, "end": -w}.get(
            el.font.anchor if el.font else "middle", -w / 2)
        a = math.radians(el.rotate)
        ca, sa = math.cos(a), math.sin(a)
        boxes.append((el, [(el.x + lx * ca - ly * sa, el.y + lx * sa + ly * ca)
                           for lx, ly in ((dx, -h / 2), (dx + w, -h / 2),
                                          (dx + w, h / 2), (dx, h / 2))]))

    def crosses(p, q, box):
        def side(o, a, b):
            return ((a[0] - o[0]) * (b[1] - o[1])
                    - (a[1] - o[1]) * (b[0] - o[0]))
        for i in range(4):
            r, s = box[i], box[(i + 1) % 4]
            if (((side(p, q, r) > 0) != (side(p, q, s) > 0))
                    and ((side(r, s, p) > 0) != (side(r, s, q) > 0))):
                return True
        return False

    for el in plan.elements:
        if el.kind != "path" or el.role not in ("stem", "siblings") or not el.d:
            continue
        for pts, _c in pathflatten.flatten(el, 0.4):
            for p, q in zip(pts, pts[1:]):
                for tel, box in boxes:
                    if tel.person_id and tel.person_id == el.person_id:
                        continue
                    assert not crosses(p, q, box), (
                        f"{focus}: a {el.role} is drawn through "
                        f"'{tel.text}'")


@pytest.mark.parametrize("focus", ["bloodline", "all"])
def test_a_child_of_two_unions_is_under_one_arc_only(graph, focus):
    """Somebody adopted, fostered, or whose parentage is in doubt is a child
    of two unions in the file. Drawing an arc from each puts them in two
    families as a full sibling of both -- which is what had Essie Sell under
    the McGiverns' arc AND the Sells'.

    `schema.sql` is explicit: the layout follows the union marked primary,
    and the other link is drawn as a chord across the disc.
    """
    plan = _panelled(graph, 1000, 1000, focus=focus)
    owners: dict = {}
    for el in plan.elements:
        if el.role == "branch" and el.person_id and el.union_id:
            owners.setdefault(el.person_id, set()).add(el.union_id)
    for pid, uids in owners.items():
        assert len(uids) == 1, (
            f"{focus}: {graph.people[pid].full_name} hangs off "
            f"{len(uids)} sibling arcs")


def test_every_name_reads_outward(graph):
    """`labels.face = outward` sets the chart as if you were standing outside
    the rim looking in: the tops of the letters point AWAY from the centre,
    the whole way round, and you turn the chart rather than your head.

    It was 180 degrees out -- every name faced inward, upright along the
    bottom of the disc and upside down along the top, which is the opposite
    of what the token says and of what was asked for.
    """
    import math
    plan = _panelled(graph, 1000, 1000, labels__orientation="tangential",
                     labels__face="outward")
    cx, cy = plan.meta.extra["centre_mm"]
    seen = 0
    for el in plan.elements:
        # NAMES. The legend and the title are set on the page, not on a ring.
        if el.kind != "text" or not el.text or not el.person_id:
            continue
        # the tops of the letters, after the rotation the renderer applies
        up = (math.sin(math.radians(el.rotate)), -math.cos(math.radians(el.rotate)))
        out = (el.x - cx, el.y - cy)
        n = math.hypot(*out) or 1.0
        assert (up[0] * out[0] + up[1] * out[1]) / n > 0.7, (
            f"'{el.text}' faces inward")
        seen += 1
    assert seen > 20, "no names to check"


@pytest.mark.parametrize("focus", FOCUSES)
def test_a_marriage_sits_outside_the_sibling_arc(graph, focus):
    """THE ORDER OF THE LINES ROUND A NAME, which has to be the same
    everywhere or none of them means anything:

        the sibling arc    inside   -- where you came from
        the name
        the marriage rule  outside  -- who you married
        the stem           outside that -- your children

    Read with the near half of the disc upright, "outside" is underneath, so
    the marriage sits under the sibling line and over the children. Swap
    those two anywhere and a marriage reads as a descent.
    """
    import math

    from helix.render import pathflatten
    plan = _panelled(graph, 1000, 1000, focus=focus)
    cx, cy = plan.meta.extra["centre_mm"]
    arc_r: dict = {}
    for el in plan.elements:
        if el.role == "siblings" and el.union_id and el.d:
            for pts, _c in pathflatten.flatten(el, 1.0):
                arc_r[el.union_id] = min(
                    arc_r.get(el.union_id, 1e9),
                    min(math.hypot(p[0] - cx, p[1] - cy) for p in pts))
    checked = 0
    for el in plan.elements:
        if el.role not in ("marriage", "unknown_partner") or not el.d:
            continue
        uid = (graph.people[el.person_id].child_of
               if el.person_id in graph.people else None)
        if uid not in arc_r:
            continue
        for pts, _c in pathflatten.flatten(el, 1.0):
            rr = min(math.hypot(p[0] - cx, p[1] - cy) for p in pts)
            assert rr > arc_r[uid], (
                f"{focus}: {graph.people[el.person_id].full_name}'s marriage "
                f"rule is at r={rr:.1f}, inside the arc over their brothers "
                f"and sisters at r={arc_r[uid]:.1f}")
            checked += 1
    assert checked, "no couple had both lines to compare"


@pytest.mark.parametrize("focus", FOCUSES)
def test_every_relationship_in_the_file_is_drawn(graph, focus):
    """Not "does it look right" but "is it all there". One line per fact and
    every fact with a line: a stem for every marriage with children on the
    chart, exactly one tick for each of those children, and exactly one tie
    for every couple both of whom are drawn.

    A child with no tick is a name floating with nothing joining it to its
    parents, which is the "branches out of nowhere" the owner reported.
    """
    plan = _panelled(graph, 1000, 1000, focus=focus)
    placed = {e.person_id for e in plan.elements
              if e.kind == "text" and e.person_id}
    stems = {e.union_id for e in plan.elements if e.role == "stem"}
    ticks: dict = {}
    for e in plan.elements:
        if e.role in ("branch", "thread") and e.person_id:
            ticks[e.person_id] = ticks.get(e.person_id, 0) + 1
    tied = {e.person_id for e in plan.elements
            if e.role in ("marriage", "chord", "married_across")}
    for uid, u in graph.unions.items():
        ps = [p for p in u.partners if p in placed]
        if not ps:
            continue                 # parents outside the focus
        # strictly the union marked primary: somebody with several parent
        # links and no primary is a gap in the research, and the chart may
        # not guess which set of parents to draw
        kids = [c for c in u.children
                if c in placed and graph.people[c].child_of == uid]
        if kids:
            assert uid in stems, (
                f"{focus}: no stem from "
                f"{' + '.join(graph.people[p].full_name for p in ps)} "
                f"to their {len(kids)} children")
        for c in kids:
            assert ticks.get(c, 0) == 1, (
                f"{focus}: {graph.people[c].full_name} has "
                f"{ticks.get(c, 0)} lines to their parents, not one")
        if len(ps) == 2:
            assert set(ps) & tied, (
                f"{focus}: nothing joins {graph.people[ps[0]].full_name} and "
                f"{graph.people[ps[1]].full_name}, who are married")


@pytest.fixture
def cousins(tmp_path):
    """Two documented families that marry into each other.

    The one case the couple grid cannot draw without a bracket: both
    partners were born on the chart, so only one of them can hold the cell
    and the other's family has to reach across to draw its own child. A
    generated sample family never does this -- every spouse in it married in
    from nowhere -- so without this fixture the checks on the search pass
    whatever the cost model says, which is exactly how two broken cost
    models got through.
    """
    from helix.graph import build
    from helix.store import records
    from helix.store.db import connect, set_setting
    con = connect(tmp_path / "c.helix")

    def add(given, surname, to=None, how=None, union=None, **kw):
        body = {"given": given, "surname": surname, **kw}
        if to:
            body["attach"] = {"to": to, "as": how, "union": union}
        return records.add_person(con, body)["id"]

    reed = add("Walter", "Reed", birth="1901")
    add("Ada", "Reed", reed, "partner", birth="1903")
    paul = add("Paul", "Reed", reed, "child", birth="1930")
    add("Derek", "Reed", reed, "child", birth="1932")
    add("Gorden", "Reed", reed, "child", birth="1935")

    murray = add("Thomas", "Murraycarr", birth="1900")
    add("Gurtrude", "Murraycarr", murray, "partner", birth="1902")
    margret = add("Margret", "Murraycarr", murray, "child", birth="1931")
    add("David", "Murraycarr", murray, "child", birth="1934")

    # the cousin marriage: both of them were already on the chart
    records.link_person(con, {"id": margret,
                              "attach": {"to": paul, "as": "partner"}})
    g0 = build.load(con)
    sarah = add("Sarah", "Reed", paul, "child",
                union=g0.people[paul].unions[0], birth="1958")
    add("Colin", "Tye", sarah, "partner", birth="1957")
    g1 = build.load(con)
    # THE SUBJECT IS TWO GENERATIONS BELOW THE MARRIAGE, and it has to be:
    # the couple where two lines meet is only walked as ANCESTRY -- with both
    # families behind them on one side, which is the arrangement being tested
    # -- when somebody below them is whose chart it is. Made the subject
    # himself, Paul's cell is walked as a descent instead, his wife's family
    # is a separate block altogether, and there is nothing here to measure.
    emma = add("Emma", "Tye", sarah, "child",
               union=g1.people[sarah].unions[0], birth="1985")
    set_setting(con, "subject_person_id", emma)
    return build.load(con)


@pytest.mark.parametrize("focus", FOCUSES)
def test_the_search_optimises_what_the_chart_draws(graph, focus):
    """The ordering search counts the crossings it expects in cells; the
    engine then draws them in angles. This checks the two agree.

    It is the invariant the whole search rests on, and it has been broken
    twice. The cost model recorded one position per CELL, so a married-in
    partner was invisible to it and the cost came out zero on a chart with
    five crossings on it -- the search never ran, and everything it was
    supposed to fix was fixed by hand instead. Then it modelled one stem per
    cell rather than one per MARRIAGE, so a man who married twice had both
    his families leaving from the same point and the commonest crossing of
    the lot could not be seen.

    Both times the numbers looked healthy and the chart did not. Nothing
    catches that except counting the same thing twice, from the two ends.
    """
    from helix.layout.engines.family import _stem_runs

    g = cellgrid(graph, focus)
    assert g.search, "the couple grid did not record what the search found"

    stems = []
    for uid, gen_k, _anchor, _parents, head_t, run in _stem_runs(graph, g, False):
        ts = [g.slots[c].tc for c in run]
        stems.append((gen_k, head_t, min(max(head_t, min(ts)), max(ts)), uid))
    drawn = 0
    for gen, head, foot, uid in stems:
        if abs(foot - head) < 1e-9:
            continue                     # straight out; no bracket to cross
        lo, hi = min(head, foot), max(head, foot)
        for gen2, head2, foot2, uid2 in stems:
            if gen2 != gen or uid2 == uid:
                continue
            drawn += lo + 1e-6 < head2 < hi - 1e-6
            drawn += (abs(foot2 - head2) > 1e-9
                      and lo + 1e-6 < foot2 < hi - 1e-6)

    assert drawn == g.search["crossings"], (
        f"{focus}: the search settled for {g.search['crossings']} crossings "
        f"and the chart draws {drawn}. The cost model in couple_grid.py has "
        f"drifted from family._stem_runs, so the search is optimising "
        f"something this chart does not do.")


def test_the_search_and_the_chart_agree_about_reach(cousins):
    """The same check with the numbers that are never zero.

    Counting crossings alone is not enough to catch drift: a small tidy
    family has none, so the assertion above passes on a cost model that has
    been thoroughly broken. REACH -- how far the brackets travel to gather
    up children who are not beside each other -- is non-zero the moment two
    documented families intermarry, which is the case the whole search
    exists for, and both ends of the check now count it in the same units.
    """
    from helix.layout.engines.family import _stem_runs

    graph = cousins
    g = cellgrid(graph, "all")
    reach = 0.0
    for _uid, _gen, _a, _p, head_t, run in _stem_runs(graph, g, False):
        ts = [g.slots[c].tc for c in run]
        reach += abs(min(max(head_t, min(ts)), max(ts)) - head_t)
    assert reach > 1e-6, (
        "this family was built so the brackets have somewhere to reach; if "
        "they do not, the fixture no longer tests anything")
    assert abs(reach - g.search["reach_turns"]) < 0.002, (
        f"the search believes its brackets reach "
        f"{g.search['reach_turns'] * 360:.1f} degrees and the chart draws "
        f"{reach * 360:.1f}. The cost model in couple_grid.py has drifted "
        f"from family._stem_runs.")


def test_a_couple_sits_between_the_two_families_they_join(cousins):
    """The shape this whole layout is named for, in the one place it was
    not being drawn.

    His family behind him, hers behind her, the two meeting at the marriage.
    A couple with children of their own in the block has to sit over those
    children instead -- that is what keeps the descent radial -- but a couple
    whose only child is drawn elsewhere has nothing to sit over, and used to
    be shoved against one end with BOTH families on one side. Whichever
    family ended up further away then had a bracket right across the other
    to reach its own child: on this eleven-person chart, two of them
    sweeping 116 degrees each.
    """
    graph = cousins
    g = cellgrid(graph, "all")
    at = {graph.people[p].full_name: sl.tc for p, sl in g.slots.items()}
    ring = {graph.people[p].full_name: sl.gen for p, sl in g.slots.items()}
    assert ring["Paul Reed"] == ring["Margret Murraycarr"], (
        "the couple whose two families meet are not even on one ring")
    # his brothers on his side, her brother on hers, and the couple between
    for reed in ("Derek Reed", "Gorden Reed"):
        assert at[reed] < at["Paul Reed"] < at["Margret Murraycarr"] \
            or at[reed] > at["Paul Reed"] > at["Margret Murraycarr"], (
                f"{reed} is not on Paul's side of the marriage: "
                f"{sorted(at, key=at.get)}")
    assert (at["David Murraycarr"] - at["Margret Murraycarr"]) * \
           (at["Margret Murraycarr"] - at["Paul Reed"]) > 0, (
        "Margret's brother is not on Margret's side of the marriage: "
        f"{sorted(at, key=at.get)}")
    # ...which is the whole point: neither set of parents needs a bracket
    from helix.layout.engines.family import _stem_runs
    for uid, _gen, _a, _p, head_t, run in _stem_runs(graph, g, False):
        if not {"Walter Reed", "Thomas Murraycarr"} & {
                graph.people[q].full_name for q in graph.unions[uid].partners}:
            continue
        ts = [g.slots[c].tc for c in run]
        assert min(ts) - 1e-9 <= head_t <= max(ts) + 1e-9, (
            f"{' + '.join(graph.people[q].full_name for q in graph.unions[uid].partners)}"
            " still has to reach round to their own children")


def test_a_name_is_the_whole_name_with_its_years(graph):
    """What the default chart says about a person.

    Two things, and both are about being able to check the chart against a
    record. The WHOLE name as it was entered -- "Harry Albert Reed", not
    "Harry Reed", because the middle name is often the only thing telling
    two of them apart -- and the years under it. Somebody with no dates
    recorded gets no second line, so a gap in the research reads as a gap
    rather than being papered over.
    """
    from helix.layout.common import label_lines
    style = Style.load()
    both = named = 0
    for person in graph.people.values():
        lines = [t for t, _sz, _c in label_lines(style, person, 3, 0)]
        assert lines, f"{person.full_name} got no label at all"
        assert lines[0] == person.full_name, (
            f"the first line should be the whole name: {lines[0]!r} against "
            f"{person.full_name!r}")
        named += 1
        if person.birth_year:
            assert len(lines) > 1 and str(person.birth_year) in lines[1], (
                f"{person.full_name} was born in {person.birth_year} and the "
                f"chart does not say so: {lines}")
            both += 1
        elif not person.death_year:
            assert len(lines) == 1, (
                f"{person.full_name} has no dates recorded, so there is "
                f"nothing to put on a second line: {lines}")
    assert named and both, "this family has no dates in it to check"


def test_a_style_that_asks_for_one_line_still_gets_one_line(graph):
    """`labels.lines` beats `labels.template` -- but a preset is MERGED over
    the defaults rather than replacing them, so once full name and dates
    became the default stack every style that says only `template` would
    have had that stack imposed on it. Circuit asks for surnames alone."""
    from helix.layout.common import label_lines, template_for
    person = next(p for p in graph.people.values() if p.surname)
    for preset, want in (("circuit", "{surname}"),
                         ("nordic", "{surname}"),
                         ("botanical", "{given_first} {surname}")):
        style = Style.load(preset)
        lines = label_lines(style, person, 3, 0)
        assert len(lines) == 1, (
            f"{preset} asked for {want!r} and got {len(lines)} lines: {lines}")
        assert template_for(style, 3) == want, (
            f"{preset} should still resolve to {want!r}")


def test_a_long_name_loses_its_surname_before_its_given_name(graph):
    """The rung that keeps a name readable when the room runs out.

    Without it the ladder drops from a whole name straight to two letters
    for anybody whose short form IS their whole name -- everyone with a
    single given name. On the owner's chart that put "PH" next to "Kathleen
    Holloway". A surname is the one thing a family tree never has to repeat:
    it is written on the branch the person is standing on.
    """
    from helix.layout.common import (PolarLabelPlacer, est_text_width,
                                     place_radial_label)
    from helix.layout.plan import Canvas, RenderPlan

    person = next(p for p in graph.people.values()
                  if p.given_first and p.surname
                  and p.short_name == p.full_name)
    style = Style.load()
    size, r = 3.0, 100.0
    whole = est_text_width(person.full_name, size)
    given = est_text_width(person.given_first, size)
    assert given < whole, "this person's names are the same length"

    # A NEIGHBOUR STANDING JUST TOO CLOSE. Placed so the window left over is
    # wider than the given name and narrower than the whole one -- which is
    # exactly the squeeze the rung exists for, and is what happened to Peter
    # Holloway for the sake of half a millimetre.
    block_h = 20.0
    half_block = (block_h / 2 + 0.5) / r
    at = half_block + ((given + whole) / 4 + 0.5) / r
    plan = RenderPlan(canvas=Canvas(400, 400))
    placer = PolarLabelPlacer()
    for side in (-1, 1):
        placer.take(side * at, r, 4.0, block_h)

    assert place_radial_label(plan, placer, person,
                              [(person.full_name, size, "#000")],
                              0.0, r, 200, 200, style, flip=False,
                              orientation="tangential"), (
        "the given name should have fitted where the whole name did not")
    drawn = [e.text for e in plan.elements if e.kind == "text"]
    assert drawn == [person.given_first], (
        f"expected the given name alone, got {drawn}")
