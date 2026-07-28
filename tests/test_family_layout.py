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
