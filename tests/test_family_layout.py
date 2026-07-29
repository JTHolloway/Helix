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


def test_a_second_marriage_stacks_in_the_same_cell(remarried):
    graph, dad = remarried
    g = cellgrid(graph, "all")
    cell = g.slots[dad].cell
    members = sorted([sl for sl in g.slots.values() if sl.cell == cell],
                     key=lambda x: x.row)
    names = [graph.people[m.pid].full_name for m in members]
    assert names[0] == "Michael Pargeter", "the blood member holds row 0"
    assert set(names[1:]) == {"Susan Hallam", "Rachel Dunmore"}
    assert [m.row for m in members] == [0, 1, 2]
    assert len({m.tc for m in members}) == 1, "one cell is one angle"


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
    plan = _panelled(graph, 1000, 1000, focus=focus)
    fills = {e.fill for e in _wedges(plan)}
    assert len(fills) >= 2, f"{focus}: {len(fills)} family colour(s) on the chart"


def test_the_wedges_never_reach_the_cutter(graph):
    """They are ink on paper, not a cut. `PRINT_ONLY` is the layer that says
    so, and every writer drops it in production."""
    plan = _panelled(graph, 1000, 1000)
    assert _wedges(plan), "no wedges were drawn at all"
    assert all(e.layer == "PRINT_ONLY" for e in _wedges(plan))


def test_the_wedges_can_be_turned_off(graph):
    plan = _panelled(graph, 1000, 1000, family__wedges=False)
    assert not _wedges(plan)


def test_two_lines_that_marry_share_their_descendants(graph):
    """A marriage between two families is not drawn. It does not have to be:
    from that ring outward both families cover the same ground, so the two
    tints lie on top of each other and the blend IS the marriage. If no two
    wedges ever overlap, that has stopped working."""
    import math
    plan = _panelled(graph, 1000, 1000, focus="bloodline")
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
