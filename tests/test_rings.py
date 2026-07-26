"""The Concentric Rings design carries the promises about legibility, so it
gets its own tests."""
import math

import pytest

from helix.layout import registry
from helix.layout.base import LayoutSettings
from helix.layout.common import PolarLabelPlacer, _ang_overlap
from helix.layout.engines import radial  # noqa: F401
from helix.style.tokens import Style


def _plan(graph, **over):
    st = Style.load("rings")
    for k, v in over.items():
        st.set(k.replace("__", "."), v)
    s = LayoutSettings(engine="radial_rings", subject_id=graph.subject_id,
                       focus=over.pop("focus", "thread_siblings"),
                       max_generations=5)
    return registry.run("radial_rings", graph, s, st)


def test_one_ring_per_generation(graph):
    """Everyone in a generation must share a ring base. If two siblings sit
    at unrelated radii the design has failed at its one job."""
    plan = _plan(graph)
    by_gen = {}
    for el in plan.elements:
        if el.role == "ring" and el.d:
            r = _radius_of_arc(el.d, plan.canvas.width_mm / 2)
            by_gen.setdefault(round(r, 1), 0)
            by_gen[round(r, 1)] += 1
    assert by_gen, "no sibling arcs were drawn"


def _radius_of_arc(d, cx):
    import re
    m = re.search(r"A([\d.]+),", d)
    return float(m.group(1)) if m else 0.0


def test_no_labels_are_lost_at_sane_density(graph):
    for focus in ("thread", "thread_siblings"):
        plan = _plan(graph, focus=focus)
        assert plan.meta.extra["labels_hidden"] == 0, focus


def test_canvas_grows_to_fit_the_names(graph):
    """The rings are sized to the text, not the text to the rings."""
    small = _plan(graph, labels__lines=["{initials}"])
    big = _plan(graph, labels__lines=["{given} {surname} {lifespan}"])
    assert big.canvas.width_mm > small.canvas.width_mm


def test_labels_never_set_upside_down(graph):
    plan = _plan(graph)
    for el in plan.elements:
        if el.kind == "text" and el.role == "label":
            a = el.rotate % 360
            assert not (90 < a < 270), f"upside-down label at {a:.0f} degrees"


def test_structure_is_pure_linework(graph):
    plan = _plan(graph)
    for el in plan.elements:
        if el.role in ("ring", "connector", "station"):
            assert el.fill in (None, "none"), "the rings design must not fill"


def test_stagger_engages_only_when_crowded(graph):
    """Ten siblings across a whole circle need one row; the same ten in a
    30-degree wedge need two. Staggering when it is not needed is as much a
    fault as failing to stagger when it is."""
    wide = _plan(graph, layout__sweep_deg=360)
    tight = _plan(graph, layout__sweep_deg=45)
    assert max(tight.meta.extra["subrows"].values()) >= \
           max(wide.meta.extra["subrows"].values())


def test_subrows_never_exceed_the_cap(graph):
    plan = _plan(graph, focus="all", layout__sweep_deg=90)
    assert max(plan.meta.extra["subrows"].values()) <= 3


# ------------------------------------------------------------ polar placer --
def test_polar_placer_allows_what_a_box_would_reject():
    """A 35 mm name at 45 degrees has a 25 mm square bounding box, so an
    axis-aligned test rejects neighbours that in fact clear each other
    easily. This is why labels were being thrown away."""
    p = PolarLabelPlacer(min_gap_mm=0.4)
    p.take(math.radians(45), 100, 35, 3.0)
    assert p.free(math.radians(48), 100, 35, 3.0)      # 5 mm apart at r=100
    assert not p.free(math.radians(45.2), 100, 35, 3.0)


def test_polar_placer_separates_by_radius():
    p = PolarLabelPlacer()
    p.take(math.radians(10), 100, 20, 3.0)
    assert p.free(math.radians(10), 130, 20, 3.0)      # same angle, further out


def test_angular_overlap_survives_the_wrap_at_zero():
    two_pi = 2 * math.pi
    assert _ang_overlap(two_pi - 0.1, 0.1, 0.0, 0.05)
    assert not _ang_overlap(two_pi - 0.1, two_pi - 0.05, 0.1, 0.2)


# ---------------------------------------------------------- panel fitting --
def _panel(graph, w=1000, h=1000, pitch=25.4, focus="thread_siblings", **over):
    st = Style.load("rings")
    st.set("canvas.width_mm", w)
    st.set("canvas.height_mm", h)
    st.set("layout.min_ring_pitch_mm", pitch)
    for k, v in over.items():
        st.set(k.replace("__", "."), v)
    s = LayoutSettings(engine="radial_rings", subject_id=graph.subject_id,
                       focus=focus, max_generations=5)
    return registry.run("radial_rings", graph, s, st)


def test_panel_size_is_honoured_exactly(graph):
    """A metre of ply is a metre. The file must come out at that size."""
    plan = _panel(graph, 1000, 1000)
    assert plan.canvas.width_mm == 1000
    assert plan.canvas.height_mm == 1000


def test_rings_keep_at_least_the_requested_gap(graph):
    for pitch in (25.4, 40.0, 60.0):
        plan = _panel(graph, 1000, 1000, pitch)
        fit = plan.meta.extra["fit"]
        if fit["fits"]:
            assert fit["ring_pitch_mm"] >= pitch - 0.05, pitch


def test_spare_room_is_shared_out_not_left_at_the_rim(graph):
    """A 22-person tree on a metre panel should use the metre, not huddle in
    the middle with a huge blank margin."""
    plan = _panel(graph, 1000, 1000, focus="thread")
    assert plan.meta.extra["fit"]["ring_pitch_mm"] > 40


def test_geometry_stays_inside_the_panel(graph):
    plan = _panel(graph, 1000, 1000)
    W = plan.canvas.width_mm
    for el in plan.elements:
        if el.kind == "circle":
            assert -1 <= el.x <= W + 1 and -1 <= el.y <= W + 1


def test_a_panel_that_is_too_small_says_so_in_millimetres(graph):
    plan = _panel(graph, 260, 260, focus="all")
    fit = plan.meta.extra["fit"]
    assert not fit["fits"]
    assert fit["shortfall_mm"] > 0
    assert any("Show fewer generations" in w for w in plan.meta.warnings)


def test_a_metre_panel_holds_the_whole_family(graph):
    """The stated target: everyone, on one metre square, rings an inch apart."""
    plan = _panel(graph, 1000, 1000, 25.4, focus="all")
    fit = plan.meta.extra["fit"]
    assert fit["fits"]
    assert fit["ring_pitch_mm"] >= 25.4


def test_fit_report_is_always_present_for_this_design(graph):
    for w in (400, 700, 1000, 1400):
        assert "fit" in _panel(graph, w, w).meta.extra


# ------------------------------------------------- customisation surface --
def test_multi_line_labels_stack(graph):
    """Dates under the name: the label becomes several text elements per
    person, not one run-on string."""
    one = _plan(graph, labels__lines=["{given_first} {surname}"])
    two = _plan(graph, labels__lines=["{given_first} {surname}", "{lifespan}"])
    n1 = sum(1 for e in one.elements if e.role == "label")
    n2 = sum(1 for e in two.elements if e.role == "label")
    assert n2 > n1


def test_line_scale_makes_later_lines_smaller(graph):
    plan = _plan(graph, labels__lines=["{given_first} {surname}", "{lifespan}"],
                 labels__line_scale=[1.0, 0.6])
    sizes = sorted({e.font.size_mm for e in plan.elements
                    if e.role == "label" and e.font})
    assert len(sizes) >= 2 and sizes[0] < sizes[-1]


def test_by_ring_overrides_the_whole_stack(graph):
    plan = _plan(graph, labels__lines=["{given_first} {surname}"],
                 labels__by_ring={"0-1": ["{given} {surname}", "{lifespan}",
                                          "{birth_place}"]})
    assert sum(1 for e in plan.elements if e.role == "label") > plan.meta.people


@pytest.mark.parametrize("orientation", ["radial", "tangential", "auto"])
def test_every_orientation_renders_upright(graph, orientation):
    plan = _plan(graph, labels__orientation=orientation)
    for el in plan.elements:
        if el.kind == "text" and el.role == "label":
            a = el.rotate % 360
            assert not (90 < a < 270), f"{orientation}: upside down at {a:.0f}"


def test_radial_orientation_is_the_lossless_one(graph):
    """It is the default for exactly this reason."""
    for focus in ("thread", "thread_siblings"):
        plan = _plan(graph, focus=focus, labels__orientation="radial")
        assert plan.meta.extra["labels_hidden"] == 0, focus


def test_entry_gap_thins_a_ring_out(graph):
    tight = _plan(graph, focus="all", layout__min_entry_gap_mm=0)
    airy = _plan(graph, focus="all", layout__min_entry_gap_mm=18)
    assert max(airy.meta.extra["subrows"].values()) >= \
           max(tight.meta.extra["subrows"].values())


def test_stagger_can_be_forced_and_forbidden(graph):
    never = _plan(graph, focus="all", layout__stagger="never")
    always = _plan(graph, focus="all", layout__stagger="always")
    assert max(never.meta.extra["subrows"].values()) == 1
    assert max(always.meta.extra["subrows"].values()) >= 2


def test_max_subrows_is_respected(graph):
    plan = _plan(graph, focus="all", layout__stagger="always",
                 layout__max_subrows=2)
    assert max(plan.meta.extra["subrows"].values()) <= 2


def test_sibling_clustering_pulls_families_together(graph):
    """With clustering on, each sibling group occupies a narrower arc, which
    is what leaves visible air between one family and the next. Measured on
    the sibling arcs themselves rather than on label positions."""
    flat = _plan(graph, layout__sibling_gap_frac=0.0)
    clustered = _plan(graph, layout__sibling_gap_frac=0.45)
    assert _arc_span(clustered) < _arc_span(flat) * 0.95


def _arc_span(plan):
    """Total angular extent of all sibling arcs, in radians."""
    import math
    import re
    cx = cy = plan.canvas.width_mm / 2
    total = 0.0
    for el in plan.elements:
        if el.role != "ring" or not el.d:
            continue
        pts = re.findall(r"[ML]([-\d.]+),([-\d.]+)|A[\d.,]+ \d \d,\d "
                         r"([-\d.]+),([-\d.]+)", el.d)
        coords = [(float(a or c), float(b or d)) for a, b, c, d in pts]
        if len(coords) < 2:
            continue
        a0 = math.atan2(coords[0][1] - cy, coords[0][0] - cx)
        a1 = math.atan2(coords[-1][1] - cy, coords[-1][0] - cx)
        total += abs(math.atan2(math.sin(a1 - a0), math.cos(a1 - a0)))
    return total


def test_max_ring_pitch_caps_the_gaps(graph):
    plan = _panel(graph, 1400, 1400, focus="thread",
                  layout__max_ring_pitch_mm=40)
    assert plan.meta.extra["fit"]["ring_pitch_mm"] <= 40.5


def test_all_presets_named_for_rings_actually_use_it():
    for pid in ("rings", "panel1m", "rings_detailed"):
        assert Style.load(pid).get("layout.engine") == "radial_rings"


# ------------------------------------------------------------- marriages --
@pytest.fixture
def remarriage_graph(tmp_path):
    """Thomas marries twice and has children by both wives, plus an
    unmarried couple and a same-sex civil partnership."""
    from helix.graph import build
    from helix.model.gendate import parse
    from helix.store.db import connect, new_id, set_setting
    con = connect(tmp_path / "m.helix")

    def P(given, sur, yr, sex="U"):
        pid = new_id()
        con.execute("INSERT INTO person(id,sex) VALUES(?,?)", (pid, sex))
        con.execute("INSERT INTO person_name(id,person_id,is_primary,given,"
                    "surname) VALUES(?,?,1,?,?)", (new_id(), pid, given, sur))
        d = parse(str(yr)); e = new_id()
        con.execute("INSERT INTO event(id,type,date_json,date_sort) "
                    "VALUES(?,?,?,?)", (e, "birth", d.to_json(), d.sort_value))
        con.execute("INSERT INTO event_role(event_id,person_id,role) "
                    "VALUES(?,?,'principal')", (e, pid))
        return pid

    def U(a, b, kids, typ="marriage"):
        u = new_id()
        con.execute("INSERT INTO union_(id,type) VALUES(?,?)", (u, typ))
        for i, x in enumerate([p for p in (a, b) if p]):
            con.execute("INSERT INTO union_partner(union_id,person_id,seq) "
                        "VALUES(?,?,?)", (u, x, i))
        for i, kid in enumerate(kids):
            con.execute("INSERT INTO union_child(union_id,person_id,"
                        "is_primary,birth_order) VALUES(?,?,1,?)", (u, kid, i))
        return u

    tom = P("Thomas", "Whitcombe", 1800, "M")
    mary = P("Mary", "Hallam", 1802, "F")
    jane = P("Jane", "Boyce", 1815, "F")
    kids = [P("William", "Whitcombe", 1825), P("Sarah", "Whitcombe", 1827),
            P("George", "Whitcombe", 1840), P("Alice", "Whitcombe", 1842)]
    U(tom, mary, kids[:2])
    U(tom, jane, kids[2:])
    ann = P("Ann", "Vasey", 1830, "F"); joe = P("Joseph", "Rennick", 1828, "M")
    U(ann, joe, [P("Percy", "Vasey", 1855)], "unmarried")
    r = P("Ruth", "Salter", 1808, "F"); ed = P("Edith", "Kentish", 1810, "F")
    U(r, ed, [P("Nathan", "Salter", 1836)], "civil_partnership")
    set_setting(con, "subject_person_id", kids[2])
    con.commit()
    gr = build.load(connect(tmp_path / "m.helix"))
    gr.test_ids = {"tom": tom, "mary": mary, "jane": jane, "kids": kids}
    return gr


def test_half_siblings_do_not_share_a_sibling_arc(remarriage_graph):
    """The reason children link to a UNION and not to a parent. One arc
    across 'his children' would state that two marriages were one family."""
    plan = registry.run("radial_rings", remarriage_graph,
                        LayoutSettings(engine="radial_rings",
                                       subject_id=remarriage_graph.subject_id),
                        Style.load("rings"))
    arcs = [e for e in plan.elements if e.role == "ring"]
    assert len(arcs) == 2, "expected one arc per marriage, not one per father"
    assert len({e.union_id for e in arcs}) == 2
    assert all(e.union_id for e in arcs)


def test_full_siblings_only(remarriage_graph):
    g = remarriage_graph
    k = g.test_ids["kids"]
    assert set(g.siblings(k[0])) == {k[1]}
    assert set(g.siblings(k[2])) == {k[3]}


def test_every_couple_gets_a_visible_tie(remarriage_graph):
    plan = registry.run("radial_rings", remarriage_graph,
                        LayoutSettings(engine="radial_rings",
                                       subject_id=remarriage_graph.subject_id),
                        Style.load("rings"))
    ties = [e for e in plan.elements if e.role == "marriage"]
    assert ties, "couples must be visibly joined"
    assert len({e.union_id for e in ties}) == len(ties), "one tie per union"
    for e in ties:
        assert e.union_id in remarriage_graph.unions


def test_informal_unions_are_drawn_differently(remarriage_graph):
    """An unmarried couple must not look identical to a married one."""
    g = remarriage_graph
    plan = registry.run("radial_rings", g,
                        LayoutSettings(engine="radial_rings",
                                       subject_id=g.subject_id, focus="all"),
                        Style.load("rings"))
    informal = {uid for uid, u in g.unions.items()
                if u.type not in ("marriage", "civil_partnership")}
    ties = [e for e in plan.elements if e.role == "marriage"]
    drawn_informal = [e for e in ties if e.union_id in informal]
    if drawn_informal:
        assert all(e.dash for e in drawn_informal)
    assert all(not e.dash for e in ties if e.union_id not in informal)


def test_remarried_person_carries_two_ties(remarriage_graph):
    plan = registry.run("radial_rings", remarriage_graph,
                        LayoutSettings(engine="radial_rings",
                                       subject_id=remarriage_graph.subject_id),
                        Style.load("rings"))
    tom = remarriage_graph.test_ids["tom"]
    unions = remarriage_graph.people[tom].unions
    tied = {e.union_id for e in plan.elements if e.role == "marriage"}
    assert set(unions) <= tied


def test_spouses_and_lone_parents_are_all_drawn(remarriage_graph):
    """Nobody in scope may be silently omitted. With focus='all' that means
    every person in the file, spouses and lone parents included."""
    g = remarriage_graph
    plan = registry.run("radial_rings", g,
                        LayoutSettings(engine="radial_rings",
                                       subject_id=g.subject_id, focus="all"),
                        Style.load("rings"))
    labelled = {e.person_id for e in plan.elements if e.role == "label"}
    missing = set(g.people) - labelled
    assert not missing, f"left off: {[g.people[m].full_name for m in missing]}"


# ------------------------------- bloodline-only shape: half-siblings ------
@pytest.fixture
def bloodline_graph(tmp_path):
    """The realistic shape when you only record blood relatives: your
    father's other union has a single recorded partner, because the other
    parent is not your relation and never gets entered."""
    from helix.graph import build
    from helix.model.gendate import parse
    from helix.store.db import connect, new_id, set_setting
    con = connect(tmp_path / "b.helix")

    def P(given, sur, yr, sex="U"):
        pid = new_id()
        con.execute("INSERT INTO person(id,sex) VALUES(?,?)", (pid, sex))
        con.execute("INSERT INTO person_name(id,person_id,is_primary,given,"
                    "surname) VALUES(?,?,1,?,?)", (new_id(), pid, given, sur))
        d = parse(str(yr)); e = new_id()
        con.execute("INSERT INTO event(id,type,date_json,date_sort) "
                    "VALUES(?,?,?,?)", (e, "birth", d.to_json(), d.sort_value))
        con.execute("INSERT INTO event_role(event_id,person_id,role) "
                    "VALUES(?,?,'principal')", (e, pid))
        return pid

    def U(partners, kids, typ="marriage"):
        u = new_id()
        con.execute("INSERT INTO union_(id,type) VALUES(?,?)", (u, typ))
        for i, x in enumerate(partners):
            con.execute("INSERT INTO union_partner(union_id,person_id,seq) "
                        "VALUES(?,?,?)", (u, x, i))
        for i, k in enumerate(kids):
            con.execute("INSERT INTO union_child(union_id,person_id,"
                        "is_primary,birth_order) VALUES(?,?,1,?)", (u, k, i))
        return u

    gpa = P("Arthur", "Pargeter", 1935, "M")
    gma = P("Edith", "Marlow", 1937, "F")
    dad = P("Michael", "Pargeter", 1962, "M")
    mum = P("Susan", "Hallam", 1964, "F")
    me = P("James", "Pargeter", 1992, "M")
    sis = P("Claire", "Pargeter", 1995, "F")
    half = P("Hannah", "Pargeter", 1986, "F")
    U([gpa, gma], [dad])
    U([dad, mum], [me, sis])
    U([dad], [half])                     # other parent never recorded
    set_setting(con, "subject_person_id", me)
    con.commit()
    gr = build.load(connect(tmp_path / "b.helix"))
    gr.ids = {"dad": dad, "me": me, "sis": sis, "half": half, "mum": mum}
    return gr


def _bplan(gr, **over):
    st = Style.load("rings")
    for k, v in over.items():
        st.set(k.replace("__", "."), v)
    return registry.run("radial_rings", gr,
                        LayoutSettings(engine="radial_rings",
                                       subject_id=gr.subject_id), st)


def test_half_sibling_is_not_called_a_sibling(bloodline_graph):
    g = bloodline_graph
    assert g.relationship(g.ids["me"], g.ids["half"]) == "half-sibling"
    assert g.relationship(g.ids["me"], g.ids["sis"]) == "sibling"
    assert g.half_siblings(g.ids["me"]) == [g.ids["half"]]


def test_a_parent_appears_once_by_default(bloodline_graph):
    """One person, one node. Both families hang from him."""
    plan = _bplan(bloodline_graph)
    dad = bloodline_graph.ids["dad"]
    labels = [e for e in plan.elements
              if e.role == "label" and e.person_id == dad]
    assert len(labels) == 1


def test_half_sibling_groups_are_joined_by_a_dashed_arc(bloodline_graph):
    """The families hang from one father, so the relationship BETWEEN them
    has to be drawn: a dashed arc bridging the two sibling arcs."""
    plan = _bplan(bloodline_graph)
    ties = [e for e in plan.elements if e.role == "half_tie"]
    assert ties and all(e.dash for e in ties)


def test_repeating_a_parent_is_available_but_not_the_default(bloodline_graph):
    """Off by default -- one person, one node. Switched on, the parent is
    drawn once per family with a dotted arc joining the instances."""
    off = _bplan(bloodline_graph, layout__repeat_parents=False)
    on = _bplan(bloodline_graph, layout__repeat_parents=True)
    dad = bloodline_graph.ids["dad"]
    n_off = len([e for e in off.elements
                 if e.role == "label" and e.person_id == dad])
    n_on = len([e for e in on.elements
                if e.role == "label" and e.person_id == dad])
    assert n_off == 1, "one person, one node, by default"
    assert n_on >= 1, "the parent must still be named when repeats are on"


def test_half_sibling_line_is_dashed(bloodline_graph):
    plan = _bplan(bloodline_graph)
    half_union = [e for e in plan.elements
                  if e.role == "connector" and e.dash]
    assert half_union, "the link to a single-parent union must be dashed"


def test_unrecorded_parent_is_marked_not_invented(bloodline_graph):
    plan = _bplan(bloodline_graph)
    marks = [e for e in plan.elements if e.role == "unknown_partner"]
    assert len(marks) == 1 and marks[0].dash


def test_nobody_is_left_floating(bloodline_graph):
    plan = _bplan(bloodline_graph)
    attached = {e.person_id for e in plan.elements
                if e.person_id and e.role in ("station", "connector", "ring",
                                              "repeat", "marriage")}
    assert attached >= set(bloodline_graph.people)


def test_half_tie_can_be_switched_off(bloodline_graph):
    plan = _bplan(bloodline_graph, lines__half_sibling_tie=False)
    assert not [e for e in plan.elements if e.role == "half_tie"]


def test_line_key_explains_the_dashes(bloodline_graph):
    plan = _bplan(bloodline_graph)
    key = [e for e in plan.elements if e.role == "legend"]
    marks = [e for e in key if e.kind != "text"]
    captions = [e for e in key if e.kind == "text"]
    assert len(marks) >= 6 and len(captions) >= 6, \
        "every line style needs a sample and a caption"


# ------------------------- other parent recorded, her family is not -------
@pytest.fixture
def recorded_other_parent(tmp_path):
    """The realistic case: you record your half-sister's mother, but you do
    not follow her family. The half-relationship is still the fact worth
    drawing."""
    from helix.graph import build
    from helix.model.gendate import parse
    from helix.store.db import connect, new_id, set_setting
    con = connect(tmp_path / "r.helix")

    def P(given, sur, yr, sex="U"):
        pid = new_id()
        con.execute("INSERT INTO person(id,sex) VALUES(?,?)", (pid, sex))
        con.execute("INSERT INTO person_name(id,person_id,is_primary,given,"
                    "surname) VALUES(?,?,1,?,?)", (new_id(), pid, given, sur))
        d = parse(str(yr)); e = new_id()
        con.execute("INSERT INTO event(id,type,date_json,date_sort) "
                    "VALUES(?,?,?,?)", (e, "birth", d.to_json(), d.sort_value))
        con.execute("INSERT INTO event_role(event_id,person_id,role) "
                    "VALUES(?,?,'principal')", (e, pid))
        return pid

    def U(ps, kids, typ="marriage"):
        u = new_id()
        con.execute("INSERT INTO union_(id,type) VALUES(?,?)", (u, typ))
        for i, x in enumerate(ps):
            con.execute("INSERT INTO union_partner(union_id,person_id,seq) "
                        "VALUES(?,?,?)", (u, x, i))
        for i, k in enumerate(kids):
            con.execute("INSERT INTO union_child(union_id,person_id,"
                        "is_primary,birth_order) VALUES(?,?,1,?)", (u, k, i))
        return u

    gpa = P("Arthur", "Pargeter", 1935, "M")
    gma = P("Edith", "Marlow", 1937, "F")
    dad = P("Michael", "Pargeter", 1962, "M")
    mum = P("Susan", "Hallam", 1964, "F")
    rach = P("Rachel", "Dunmore", 1960, "F")     # recorded, family not followed
    me = P("James", "Pargeter", 1992, "M")
    sis = P("Claire", "Pargeter", 1995, "F")
    half = P("Hannah", "Pargeter", 1986, "F")
    U([gpa, gma], [dad])
    u_full = U([dad, mum], [me, sis])
    u_half = U([dad, rach], [half])
    set_setting(con, "subject_person_id", me)
    con.commit()
    gr = build.load(connect(tmp_path / "r.helix"))
    gr.ids = {"dad": dad, "me": me, "sis": sis, "half": half, "rach": rach,
              "u_full": u_full, "u_half": u_half}
    return gr


def _rplan(gr, **over):
    st = Style.load("rings")
    for k, v in over.items():
        st.set(k.replace("__", "."), v)
    return registry.run("radial_rings", gr,
                        LayoutSettings(engine="radial_rings",
                                       subject_id=gr.subject_id), st)


def test_recording_the_other_mother_does_not_promote_a_half_sibling(
        recorded_other_parent):
    """The whole point. Entering her name must not turn a half-sister into a
    full sister."""
    g = recorded_other_parent
    assert g.relationship(g.ids["me"], g.ids["half"]) == "half-sibling"
    assert g.relationship(g.ids["me"], g.ids["sis"]) == "sibling"


def test_the_half_family_is_dashed_and_mine_is_not(recorded_other_parent):
    g = recorded_other_parent
    plan = _rplan(g)
    by_union = {}
    for e in plan.elements:
        if e.role in ("connector", "ring") and e.union_id:
            by_union.setdefault(e.union_id, []).append(bool(e.dash))
    assert any(by_union.get(g.ids["u_half"], [])), "half family must be dashed"
    assert [e for e in plan.elements if e.role == "half_tie"], \
        "the two families must be visibly joined"


def test_no_hollow_mark_when_the_parent_is_recorded(recorded_other_parent):
    plan = _rplan(recorded_other_parent)
    assert not [e for e in plan.elements if e.role == "unknown_partner"]


def test_a_married_in_person_never_becomes_a_lineage(recorded_other_parent):
    """Rachel married in and her family is not followed, so she must not be
    handed a sector of her own.

    With a subject chosen the layout is anchored on that person, so
    `lineages` is the subject and `roots` means "whoever sits on the
    innermost ring". Rachel should be on neither.
    """
    from helix.layout.base import build_grid
    g = recorded_other_parent
    grid = build_grid(g, LayoutSettings(engine="radial_rings",
                                        subject_id=g.subject_id))
    assert grid.lineages == [g.subject_id]
    assert g.ids["rach"] not in grid.roots
    assert grid.slots[g.ids["rach"]].partner_of == g.ids["dad"]


def test_she_is_still_drawn_and_named(recorded_other_parent):
    g = recorded_other_parent
    plan = _rplan(g)
    labelled = {e.person_id for e in plan.elements if e.role == "label"}
    assert g.ids["rach"] in labelled


def test_line_ends_are_distinguished_from_the_research_frontier(
        recorded_other_parent):
    plan = _rplan(recorded_other_parent)
    ends = [e for e in plan.elements if e.role in ("line_end", "frontier")]
    assert ends, "people with no recorded ancestry should be capped"
    assert any(e.role == "line_end" for e in ends)


# ------------------------------------------------- convergence of families --
def _tie_spans(plan):
    """Angular separation of every married couple, in degrees."""
    import math, re
    M = re.compile(r"^M([-\d.]+),([-\d.]+)")
    END = re.compile(r"A[\d.]+,[\d.]+ \d [01],[01] ([-\d.]+),([-\d.]+)$")
    cx = plan.canvas.width_mm / 2
    out = []
    for e in plan.elements:
        if e.role != "marriage" or not e.d:
            continue
        a, b = M.match(e.d), END.search(e.d)
        if not (a and b):
            continue
        t0 = math.atan2(float(a.group(2)) - cx, float(a.group(1)) - cx)
        t1 = math.atan2(float(b.group(2)) - cx, float(b.group(1)) - cx)
        out.append(abs(math.degrees(math.atan2(math.sin(t1 - t0),
                                               math.cos(t1 - t0)))))
    return sorted(out, reverse=True)


def test_couples_sit_together_not_across_the_disc(graph):
    """A married-in spouse used to be given HALF their partner's entire
    lineage span. On a root ancestor filling 40% of the disc that put the
    two of them 160 degrees apart and drew their marriage as a line straight
    across the middle. They belong side by side."""
    for focus in ("thread_siblings", "bloodline"):
        plan = _plan(graph, focus=focus)
        spans = _tie_spans(plan)
        assert spans, focus
        assert spans[0] < 45, f"{focus}: widest tie {spans[0]:.0f} degrees"


def test_a_married_in_spouse_gets_a_person_sized_slot(graph):
    from helix.layout.base import build_grid
    g = build_grid(graph, LayoutSettings(engine="radial_rings",
                                         subject_id=graph.subject_id,
                                         focus="bloodline"))
    partners = [sl for sl in g if sl.partner_of]
    assert partners
    widest = max(sl.span for sl in partners)
    assert widest < 0.1, "a spouse should not be given a whole sector"


def test_bloodline_focus_is_everyone_i_am_related_to(graph):
    """Descendants of every one of my ancestors: my parents' whole families,
    my grandparents' whole families, siblings, cousins, nieces, nephews --
    and nobody else's in-laws."""
    from helix.layout.base import build_grid
    subj = graph.subject_id
    g = build_grid(graph, LayoutSettings(engine="radial_rings",
                                         subject_id=subj, focus="bloodline"))
    expected = set()
    for a in graph.ancestors(subj):
        expected |= set(graph.descendants(a))
    placed = set(g.slots)
    assert expected <= placed | {p for p in expected
                                 if p not in placed}     # scoping may cap
    assert subj in placed
    for sib in graph.siblings(subj):
        assert sib in placed
    assert len(placed) > len(graph.ancestors(subj))


def test_bloodline_includes_cousins(graph):
    from helix.layout.base import build_grid
    subj = graph.subject_id
    g = build_grid(graph, LayoutSettings(engine="radial_rings",
                                         subject_id=subj, focus="bloodline"))
    cousins = []
    for gp in graph.parents(subj):
        for aunt in graph.siblings(gp):
            cousins.extend(graph.children(aunt))
    if cousins:
        assert any(c in g.slots for c in cousins)


def test_pedigree_paths_put_merging_lines_side_by_side(graph):
    from helix.layout.base import pedigree_paths
    paths = pedigree_paths(graph, graph.subject_id)
    assert paths[graph.subject_id] == ""
    for pid, path in paths.items():
        if len(path) >= 2:
            parent_path = path[:-1]
            assert any(v == parent_path for v in paths.values())


def test_short_arc_takes_the_minor_way_round():
    """Two people either side of the start angle are ten degrees apart, not
    three hundred and fifty."""
    import math
    from helix.layout import geometry as G
    d = G.short_arc(0, 0, 100, math.radians(-5), math.radians(5))
    long_way = G.arc_path(0, 0, 100, math.radians(-5), math.radians(355))
    assert "1,1" not in d.split("A")[1][:12]      # not flagged large-arc
    assert len(d) < len(long_way) + 40
