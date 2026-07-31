"""How is this person related to me — the structured answer.

`helix/graph/kinship.py` is the one place that decides what a cousin is.
Four separate features read it — the relatives sidebar, the scoping filter,
the profile metrics and the highlighting — and the value of putting it in
one module is entirely that they cannot disagree. These check the answers
against the arithmetic, against the English `FamilyGraph.relationship`
already produced, and against a family built by hand where every
relationship is known in advance.
"""
from __future__ import annotations

import pytest

from helix.graph.kinship import (Kinship, all_groups, describe, group_rank,
                                 household, siblings_of)


# ------------------------------------------------------------ the arithmetic
@pytest.mark.parametrize("up,down,sex,want", [
    (0, 0, "U", "you"),
    (1, 0, "M", "father"),
    (1, 0, "F", "mother"),
    (1, 0, "U", "parent"),
    (2, 0, "F", "grandmother"),
    (3, 0, "M", "great-grandfather"),
    (4, 0, "M", "great-great-grandfather"),
    (0, 1, "F", "daughter"),
    (0, 2, "M", "grandson"),
    (0, 3, "F", "great-granddaughter"),
    (1, 1, "M", "brother"),
    (1, 1, "U", "sibling"),
    (2, 1, "F", "aunt"),
    (3, 1, "M", "great-uncle"),
    (4, 1, "F", "great-great-aunt"),
    (1, 2, "M", "nephew"),
    (1, 3, "F", "great-niece"),
    (2, 2, "U", "first cousin"),
    (3, 3, "U", "second cousin"),
    (4, 4, "U", "third cousin"),
    (3, 2, "U", "first cousin once removed"),
    (2, 3, "U", "first cousin once removed"),
    (4, 2, "U", "first cousin twice removed"),
    (5, 3, "U", "second cousin twice removed"),
])
def test_the_english_for_one_measurement(up, down, sex, want):
    assert describe(up, down, sex=sex) == want


def test_a_half_sibling_is_never_called_a_brother():
    """Not cosmetic. A half-brother shares one parent, so only half the
    ancestry above him is shared, and calling him a brother asserts a second
    parent nobody recorded. `schema.sql` and `sibling_kind` say the same."""
    assert describe(1, 1, sex="M", half=True) == "half-brother"
    assert describe(1, 1, sex="F", half=True) == "half-sister"
    assert describe(1, 1, sex="U", half=True) == "half-sibling"


def test_removal_reads_the_same_from_either_end():
    """Your father's first cousin and your first cousin's child are both
    first cousins once removed. The measurement is symmetric and the words
    have to be too, or the sidebar and the profile disagree about one pair
    of people depending on which of them you clicked."""
    for a, b in ((2, 3), (2, 4), (3, 5), (4, 6)):
        assert describe(a, b) == describe(b, a)


# --------------------------------------------------------------- the groups
def test_the_tabs_are_in_the_order_people_name_them(graph):
    """Immediate family, then grandparents, then aunts and uncles. By raw
    path length a grandparent ties with a brother and a great-grandparent
    ties with an aunt, which is arithmetically true and not how anybody
    thinks about their family."""
    order = [g["key"] for g in all_groups()]
    for earlier, later in (("self", "immediate"),
                           ("immediate", "grandparents"),
                           ("grandparents", "aunts_uncles"),
                           ("aunts_uncles", "cousins_1"),
                           ("cousins_1", "cousins_2"),
                           ("cousins_2", "cousins_3"),
                           ("cousins_3", "married_in"),
                           ("married_in", "unrelated")):
        assert order.index(earlier) < order.index(later), (
            f"{earlier} should be listed above {later}")
    assert group_rank("self") == 0


def test_every_group_offered_is_a_group_that_can_appear(graph):
    """The scoping screen is built from `all_groups`, so a key there that
    the classifier never produces is a switch that does nothing."""
    keys = {g["key"] for g in all_groups()}
    k = Kinship(graph, graph.subject_id)
    for kin in k.by_id.values():
        assert kin.group in keys, f"{kin.group} is produced but never offered"


def test_the_sidebar_lists_everybody_exactly_once(graph):
    k = Kinship(graph, graph.subject_id)
    seen = [p for grp in k.groups() for p in grp["people"]]
    assert len(seen) == len(set(seen)), "somebody is in two tabs"
    assert set(seen) == set(graph.people), "somebody is in no tab at all"


def test_no_tab_opens_onto_nothing(graph):
    for grp in Kinship(graph, graph.subject_id).groups():
        assert grp["count"] == len(grp["people"]) > 0


def test_the_closest_relatives_come_first(graph):
    """The whole point of the ordering: you should not have to scroll past
    two hundred fourth cousins to reach your mother."""
    groups = Kinship(graph, graph.subject_id).groups()
    ranks = [group_rank(g["key"]) for g in groups]
    assert ranks == sorted(ranks)
    for grp in groups:
        steps = [Kinship(graph, graph.subject_id).of(p).steps
                 for p in grp["people"]]
        assert steps == sorted(steps), f"{grp['title']} is out of order"


# ------------------------------------------------- agreement with what exists
def test_it_agrees_with_the_relationship_sentence(graph):
    """`FamilyGraph.relationship` came first and is used elsewhere. The two
    are allowed to differ in wording -- this one knows the person's sex and
    says "grandmother" where the old one says "grandparent" -- but never in
    substance. A cousin here has to be a cousin there."""
    g = graph
    k = Kinship(g, g.subject_id)
    for pid, kin in k.by_id.items():
        if pid == g.subject_id or not kin.blood:
            continue
        old = g.relationship(g.subject_id, pid)
        if "cousin" in old:
            assert kin.label.split(" removed")[0].split()[0] == old.split()[0], (
                f"{old!r} against {kin.label!r}")
            assert ("removed" in old) == ("removed" in kin.label)
        assert old.startswith("half-") == kin.label.startswith("half-"), (
            f"{old!r} against {kin.label!r}")


def test_a_married_in_partner_is_named_for_who_they_married(graph):
    """Your aunt's husband shares no ancestor with you, so the arithmetic
    says "no relation" -- true, and useless: he is at every family
    gathering."""
    g = graph
    k = Kinship(g, g.subject_id)
    married = [x for x in k.by_id.values() if x.group == "married_in"]
    assert married, "this family has nobody who married into it"
    for kin in married:
        assert kin.through and kin.through in g.people
        assert kin.label.startswith("married to your ")
        assert kin.through in g.partners(kin.pid)
        assert not kin.blood


def test_nobody_is_their_own_relative(graph):
    k = Kinship(graph, graph.subject_id)
    me = k.of(graph.subject_id)
    assert me.group == "self" and me.steps == 0 and me.label == "you"


def test_relatives_of_somebody_else_is_measured_from_them(graph):
    """Clicking a person lights up THEIR cousins, not mine. A second
    measurement from a different origin, so it gets its own index rather
    than being read off the subject's."""
    g = graph
    k = Kinship(g, g.subject_id)
    other = next(p for p in g.people
                 if p != g.subject_id and g.parents(p, primary_only=False))
    sets = k.relatives_of(other)
    for pid in sets.get("immediate", []):
        assert pid != other
        assert (pid in g.parents(other, primary_only=False)
                or pid in g.children(other)
                or pid in siblings_of(g, other)), (
            f"{g.people[pid].full_name} is not immediate family of "
            f"{g.people[other].full_name}")


# ------------------------------------------------------------- the numbers
def test_the_profile_numbers_are_counted_from_the_file(graph):
    """Not from the drawn chart. A chart narrowed to first cousins still has
    to be able to say "and four more children who are not shown"."""
    g = graph
    pid = next(p for p in g.people if len(g.children(p)) > 1)
    h = household(g, pid)
    assert h["children"] == len(g.children(pid))
    assert h["siblings"] == h["full_siblings"] + h["half_siblings"]
    assert h["ancestors_known"] == len(g.ancestors(pid)) - 1
    assert h["descendants_known"] == len(g.descendants(pid)) - 1


def test_an_empty_subject_is_not_an_error():
    """A file with nobody chosen yet still has to answer. Every screen that
    reads this runs before a subject is picked."""
    from helix.graph.build import FamilyGraph
    k = Kinship(FamilyGraph({}, {}), None)
    assert k.groups() == []
    assert k.of("nobody").group == "unrelated"


# ------------------------------------------------------- narrowing the chart
def _filt(**kw):
    from helix.graph.kinship import KinFilter
    return KinFilter(**kw)


def test_an_untouched_filter_changes_nothing(graph):
    """A chart that has never been near the scoping screen is the chart it
    always was. Every field defaults to "everybody"."""
    from helix.graph.kinship import KinFilter, narrow
    f = KinFilter()
    assert not f.active
    got = narrow(graph, graph.subject_id, f)
    assert got.keep == set(graph.people) and not got.elided


def test_you_are_never_filtered_out(graph):
    """Whose chart it is cannot be narrowed off it."""
    from helix.graph.kinship import narrow
    got = narrow(graph, graph.subject_id, _filt(max_steps=0, married_in=False))
    assert graph.subject_id in got.keep


def test_narrowing_by_cousin_degree_removes_the_right_people(graph):
    from helix.graph.kinship import Kinship, narrow
    idx = Kinship(graph, graph.subject_id)
    got = narrow(graph, graph.subject_id, _filt(max_cousin_degree=1), index=idx)
    for pid in graph.people:
        k = idx.of(pid)
        if k.degree > 1 and pid not in got.kept_for_others:
            assert pid not in got.keep, (
                f"{graph.people[pid].full_name} is a {k.label} and should be off")


def test_what_is_left_is_still_connected(graph):
    """A tree cannot have a hole in the middle of it. Switch off aunts and
    uncles while leaving first cousins on and every cousin is left hanging
    from nobody, so anyone standing between a survivor and the subject is
    put back."""
    from helix.graph.kinship import narrow
    from helix.graph.kinship import Kinship
    idx = Kinship(graph, graph.subject_id)
    for kw in ({"max_cousin_degree": 0}, {"max_steps": 4},
               {"groups": frozenset(["self", "immediate", "cousins_1"])},
               {"max_removal": 0}, {"married_in": False}):
        got = narrow(graph, graph.subject_id, _filt(**kw), index=idx)
        for pid in got.keep:
            # a married-in partner hangs off their spouse, not off parents:
            # that is what marrying in MEANS, and most spouses on any chart
            # have no ancestry drawn at all
            if not idx.of(pid).blood:
                continue
            pars = [p for p in graph.parents(pid, primary_only=True)
                    if p in graph.people]
            assert not pars or any(p in got.keep for p in pars), (
                f"{kw}: {graph.people[pid].full_name} is on the chart and "
                f"neither parent is")


def test_every_person_cut_is_counted_exactly_once(graph):
    """A missing child has two parents. Counted per person they are counted
    twice -- "45 marks hiding 86 children" on a chart that cut 43 people --
    so the mark counts per MARRIAGE, which is also the one place on the
    chart there is somewhere to put it."""
    from helix.graph.kinship import narrow
    got = narrow(graph, graph.subject_id, _filt(max_cousin_degree=0))
    cut = set(graph.people) - got.keep
    counted = sum(got.elided_union.values())
    assert counted <= len(cut), (
        f"{counted} counted against {len(cut)} actually removed")
    for uid, n in got.elided_union.items():
        gone = [c for c in graph.unions[uid].children if c not in got.keep]
        assert n == len([c for c in gone
                         if (graph.people[c].child_of or uid) == uid])


def test_a_narrowed_chart_says_so_rather_than_looking_complete(graph):
    """The whole point. You cannot tell a family of two from a family of
    nine you narrowed down, so every marriage that lost children carries a
    mark and the mark carries the number."""
    from helix.graph.kinship import narrow
    got = narrow(graph, graph.subject_id, _filt(max_cousin_degree=0))
    assert got.elided_union, "this narrowing cut nobody, so it proves nothing"
    for uid in got.elided_union:
        assert any(p in got.keep for p in graph.unions[uid].partners), (
            "a mark with nobody on the chart to draw it on")
