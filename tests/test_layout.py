"""Every registered design must produce a valid plan on real data."""
import pytest

from helix.layout import registry
from helix.layout.base import LayoutSettings, build_grid
from helix.layout.engines import family, linear, network, radial  # noqa: F401
from helix.style.tokens import Style

# EVERY design, with nothing skipped. This list used to exclude eight, six of
# them because they were registered and never implemented -- so the suite was
# green while a third of the gallery threw NotImplementedError when clicked.
# The exclusions are what let that sit there. If a design cannot go in this
# list it does not belong in the registry.
BUILT = [d.key for d in registry.all_designs()]


@pytest.mark.parametrize("key", BUILT)
def test_design_renders(key, graph):
    style = Style.load()
    style.set("layout.engine", key)
    s = LayoutSettings(engine=key, subject_id=graph.subject_id,
                       max_generations=4)
    plan = registry.run(key, graph, s, style)
    assert plan.elements, f"{key} produced nothing"
    assert plan.canvas.width_mm > 0 and plan.canvas.height_mm > 0
    for el in plan.elements:
        assert el.layer in {"CUT", "SCORE", "ENGRAVE", "ENGRAVE_DEEP",
                            "GUIDE", "PRINT_ONLY"}
        if el.kind == "path":
            assert el.d, f"{key}: empty path"
            assert "nan" not in el.d.lower(), f"{key}: NaN leaked into geometry"


@pytest.mark.parametrize("key", BUILT)
def test_every_person_element_is_traceable(key, graph):
    """Hover, search and the what-if overlay all depend on provenance."""
    style = Style.load()
    s = LayoutSettings(engine=key, subject_id=graph.subject_id, max_generations=3)
    plan = registry.run(key, graph, s, style)
    tagged = {e.person_id for e in plan.elements if e.person_id}
    assert len(tagged) > 5


def test_grid_covers_everyone_once(graph):
    s = LayoutSettings(engine="radial_sunburst")
    g = build_grid(graph, s)
    assert len(g.slots) == len(g.order)
    assert len(set(g.order)) == len(g.order), "a person was placed twice"


def test_spread_axis_stays_in_range(graph):
    g = build_grid(graph, LayoutSettings(engine="radial_sunburst"))
    for sl in g:
        assert -0.001 <= sl.t0 <= 1.001
        assert -0.001 <= sl.t1 <= 1.001
        assert sl.t1 >= sl.t0


def test_missing_years_are_inferred_not_left_none(graph):
    """Chronological designs collapse if any year is None."""
    g = build_grid(graph, LayoutSettings(engine="timeline_lanes"))
    assert all(sl.year is not None for sl in g)


def test_nothing_in_the_gallery_is_a_plan():
    """The gallery must not offer a design that cannot draw.

    This test used to assert the opposite -- that six named designs raised
    NotImplementedError with a helpful message -- because six of the twenty
    were specified, registered and never built. A greyed-out promise is
    still a third of the gallery you cannot use, and `DesignInfo.built` was
    load-bearing for hiding them. They are built now, so the promise is
    gone and the invariant is the strong one: everything registered draws.
    """
    plans = [d for d in registry.all_designs() if not d.built]
    assert not plans, ("registered but not implemented: "
                       + ", ".join(d.key for d in plans))
    assert len(registry.all_designs()) >= 20


def test_unknown_design_names_the_alternatives():
    with pytest.raises(KeyError) as e:
        registry.get("does_not_exist")
    assert "radial_sunburst" in str(e.value)


# ---------------------------------------------------------------------------
# The tidy-tree allocation in subject_grid.py. These four encode
# docs/KNOWN_ISSUE_LAYOUT.md: the chart it describes had 77 sibling arcs
# sweeping over strangers and 10 pairs of people at an identical angle, and
# every one of them survived a passing test suite. Read the failure before
# changing any of these.
# ---------------------------------------------------------------------------
FOCUSES = ["thread", "thread_siblings", "bloodline", "all"]


def _subject_grid(graph, focus):
    return build_grid(graph, LayoutSettings(engine="radial_rings",
                                            subject_id=graph.subject_id,
                                            focus=focus))


@pytest.mark.parametrize("focus", FOCUSES)
def test_no_two_people_share_an_angle(graph, focus):
    """A minimum neighbour gap of zero means two names printed on top of
    each other. The old allocator handed out angle in four unrelated
    places, which is how it happened."""
    g = _subject_grid(graph, focus)
    for gen, people in g.by_gen.items():
        order = sorted(people, key=lambda p: g.slots[p].tc)
        for a, b in zip(order, order[1:]):
            gap = (g.slots[b].tc - g.slots[a].tc) * 360
            assert gap > 0.4, (
                f"{focus}: ring {gen} has two people {gap:.2f} deg apart")


@pytest.mark.parametrize("focus", FOCUSES)
def test_sibling_groups_are_contiguous(graph, focus):
    """The arc over a sibling group must not cover anyone outside that
    family. Two exceptions, both structural rather than sloppiness:

    A married-in partner of one of those siblings is allowed and
    unavoidable -- they sit on their partner's ring by definition.

    Only PRIMARY children count. An adopted child belongs to two unions and
    is laid out with the family that raised them, so the union they were
    born into cannot have them contiguous. `store/schema.sql` says that edge
    is drawn as a chord instead.
    """
    g = _subject_grid(graph, focus)
    for uid, u in graph.unions.items():
        kids = [c for c in u.children
                if c in g.slots and graph.people[c].child_of == uid]
        if len(kids) < 2:
            continue
        kidset = set(kids)
        lo = min(g.slots[c].tc for c in kids)
        hi = max(g.slots[c].tc for c in kids)
        for pid in g.by_gen.get(g.slots[kids[0]].gen, []):
            if pid in kidset or not (lo <= g.slots[pid].tc <= hi):
                continue
            assert any(x in kidset for x in graph.partners(pid)), (
                f"{focus}: {graph.people[pid].full_name} is under a sibling "
                f"arc they have nothing to do with")


@pytest.mark.parametrize("focus", FOCUSES)
def test_couples_are_placed_side_by_side(graph, focus):
    """A married-in spouse gets a person-sized slot beside their partner,
    never a share of their partner's lineage. Getting this wrong put
    couples 160 degrees apart."""
    g = _subject_grid(graph, focus)
    for pid, sl in g.slots.items():
        if not sl.partner_of or sl.partner_of not in g.slots:
            continue
        apart = abs(sl.tc - g.slots[sl.partner_of].tc) * 360
        assert apart <= 20, (
            f"{focus}: {graph.people[pid].full_name} is {apart:.0f} deg from "
            f"the person they married")


@pytest.mark.parametrize("focus", FOCUSES)
def test_everyone_in_scope_is_placed_exactly_once(graph, focus):
    """The old fallback pass attached stragglers beside whoever was nearest
    and was the source of most collisions. Nothing should need it."""
    from helix.layout.subject_grid import _scope
    g = _subject_grid(graph, focus)
    scope = _scope(graph, LayoutSettings(engine="radial_rings",
                                         subject_id=graph.subject_id,
                                         focus=focus), graph.subject_id)
    assert set(g.slots) == scope, "someone in scope was left off the chart"
    assert len(g.order) == len(set(g.order)), "a person was placed twice"


@pytest.mark.parametrize("focus", FOCUSES)
def test_siblings_share_a_ring(graph, focus):
    """Where the tree folds back on itself the walk out from the subject can
    reach two children of one union by paths of different length. Left alone,
    one of them sits a ring out from the rest of their family and their
    sibling arc spans two rings, where contiguity means nothing."""
    g = _subject_grid(graph, focus)
    for uid, u in graph.unions.items():
        kids = [c for c in u.children
                if c in g.slots and graph.people[c].child_of == uid]
        if len(kids) < 2:
            continue
        rings = {g.slots[c].gen for c in kids}
        assert len(rings) == 1, (
            f"{focus}: children of one union are spread over rings "
            f"{sorted(rings)}")
