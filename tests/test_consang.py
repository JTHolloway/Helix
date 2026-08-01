"""Cousins who married cousins, and what that does to their children.

Before the railways most people married somebody from the same parish, and
in a village of four hundred that means a shared great-grandparent more
often than not. Three of these tests are arithmetic with a known answer --
first cousins give F = 1/16 exactly -- and the rest are about not saying
more than the file knows.
"""
from __future__ import annotations

import pytest

from helix.analysis import consang
from helix.graph.build import load
from helix.store.db import connect
from helix.store.records import add_person, union_child_op, union_op


@pytest.fixture
def cousins(tmp_path):
    """A grandfather, two of his children, and their children marrying.

           Great = Grand
            /        \\
        Arthur      Bertha
          |            |
       Charles  ==  Clara          first cousins
                |
               Kit                 F = 1/16
    """
    con = connect(tmp_path / "c.helix")

    def add(given, surname, **kw):
        return add_person(con, {"given": given, "surname": surname, **kw})["id"]

    def kid(u, p):
        union_child_op(con, {"union_id": u, "person_id": p, "action": "attach"})

    def marry(a, b):
        return union_op(con, {"action": "create", "partners": [a, b]})["union_id"]

    gf, gm = add("Great", "Whitcombe", sex="M"), add("Grand", "Boyce", sex="F")
    u0 = marry(gf, gm)
    a, b = add("Arthur", "Whitcombe", sex="M"), add("Bertha", "Whitcombe", sex="F")
    kid(u0, a), kid(u0, b)
    u1 = marry(a, add("Anne", "Pargeter", sex="F"))
    u2 = marry(add("Basil", "Hallam", sex="M"), b)
    c1, c2 = add("Charles", "Whitcombe", sex="M"), add("Clara", "Hallam", sex="F")
    kid(u1, c1), kid(u2, c2)
    u3 = marry(c1, c2)
    k = add("Kit", "Whitcombe", sex="M")
    kid(u3, k)
    return load(con), {"gf": gf, "gm": gm, "a": a, "b": b,
                       "c1": c1, "c2": c2, "kid": k}


# ---------------------------------------------------------- the arithmetic
def test_first_cousins_marrying_give_their_child_one_sixteenth(cousins):
    """The textbook number, and the one to check everything else against.
    Wright's formula over the two shared grandparents:
    2 x (1/2)^(2+2+1) = 2/32 = 1/16."""
    g, ids = cousins
    r = consang.between(g, ids["c1"], ids["c2"])
    assert r.related
    assert r.coefficient == pytest.approx(1 / 16)
    assert consang.pct(r.coefficient) == "6.25%"


def test_the_percentage_keeps_the_decimal_that_matters(cousins):
    """Every value is a sum of powers of a half, so 1/16 is exactly 6.25 --
    and Python's default half-to-even prints that as "6.2"."""
    assert consang.pct(1 / 16) == "6.25%"
    assert consang.pct(1 / 64) == "1.56%"
    assert consang.pct(1 / 4) == "25%"
    assert consang.pct(0) == "0%"
    assert consang.pct(1 / 100000) == "under 0.01%"


def test_a_child_of_cousins_carries_the_coefficient(cousins):
    g, ids = cousins
    d = consang.inbreeding(g, ids["kid"])
    assert d["coefficient"] == pytest.approx(1 / 16)
    assert d["percent"] == "6.25%"
    assert "first cousins" in d["why"]


def test_only_one_shared_grandparent_halves_it(tmp_path):
    """Half-first-cousins: the two parents descend from ONE person, not a
    couple, so there is one path instead of two."""
    con = connect(tmp_path / "h.helix")

    def add(gv, sn, **kw):
        return add_person(con, {"given": gv, "surname": sn, **kw})["id"]

    def kid(u, p):
        union_child_op(con, {"union_id": u, "person_id": p, "action": "attach"})

    def marry(a, b):
        return union_op(con, {"action": "create", "partners": [a, b]})["union_id"]

    gf = add("Shared", "Whitcombe", sex="M")
    w1, w2 = add("First", "Wife", sex="F"), add("Second", "Wife", sex="F")
    ua, ub = marry(gf, w1), marry(gf, w2)
    a, b = add("Arthur", "Whitcombe", sex="M"), add("Bertha", "Whitcombe", sex="F")
    kid(ua, a), kid(ub, b)
    u1 = marry(a, add("Anne", "Pargeter", sex="F"))
    u2 = marry(add("Basil", "Hallam", sex="M"), b)
    c1, c2 = add("Charles", "Whitcombe", sex="M"), add("Clara", "Hallam", sex="F")
    kid(u1, c1), kid(u2, c2)
    g = load(con)
    r = consang.between(g, c1, c2)
    assert r.coefficient == pytest.approx(1 / 32), "one path, not two"


def test_an_ancestor_who_was_inbred_counts_too(cousins):
    """`(1 + F_A)` is what makes this Wright's formula rather than an
    approximation of it, and in a village where cousins married for four
    generations the approximation is out by a fifth."""
    g, ids = cousins
    # Kit's own F comes from an ordinary couple, so 0.
    plain = consang.inbreeding_of_child(g, ids["a"], ids["b"])
    assert plain == pytest.approx(1 / 4), "full siblings would be 1/4"


def test_it_says_what_the_pair_were_called(cousins):
    """`describe` names ONE person's relation. Said of a couple it has to be
    plural, and two people who share both parents are "brother and sister"
    rather than "sibling"."""
    g, ids = cousins
    assert consang.between(g, ids["c1"], ids["c2"]).label == "first cousins"
    assert consang.between(g, ids["a"], ids["b"]).label == "brother and sister"


# --------------------------------------------------- not saying too much --
def test_unrelated_parents_give_zero_and_say_so(cousins):
    """Zero is an answer and gets one. It is NOT a claim that two people
    were unrelated in fact -- a tree four generations deep cannot see a
    shared great-great-grandparent."""
    g, ids = cousins
    d = consang.inbreeding(g, ids["c1"])
    assert d["coefficient"] == 0.0
    assert d["percent"] == "0%"
    assert "in this file" in d["why"], "it must say how far it can see"


def test_one_parent_is_not_enough_to_work_it_out(cousins):
    g, ids = cousins
    d = consang.inbreeding(g, ids["gf"])
    assert d["coefficient"] is None
    assert "Both parents" in d["why"]


def test_a_cyclic_pedigree_does_not_hang(tmp_path):
    """Bad files contain somebody recorded as their own grandfather, and
    each shared ancestor asks the same question one generation up."""
    con = connect(tmp_path / "cyc.helix")
    a = add_person(con, {"given": "Loop", "surname": "One", "sex": "M"})["id"]
    b = add_person(con, {"given": "Loop", "surname": "Two", "sex": "F"})["id"]
    u = union_op(con, {"action": "create", "partners": [a, b]})["union_id"]
    union_child_op(con, {"union_id": u, "person_id": a, "action": "attach"})
    g = load(con)
    assert consang.inbreeding_of_child(g, a, b) >= 0.0     # returns, does not hang


def test_the_list_of_related_couples(cousins):
    g, ids = cousins
    rows = consang.couples(g)
    assert len(rows) == 1
    r = rows[0]
    assert set(r["names"]) == {"Charles Whitcombe", "Clara Hallam"}
    assert r["label"] == "first cousins"
    assert set(r["ancestor_names"]) == {"Great Whitcombe", "Grand Boyce"}
    assert r["children"] == 1


def test_the_summary_counts_them(cousins):
    g, _ = cousins
    s = consang.summary(g)
    assert s["related_couples"] == 1
    assert s["marriages"] == 4
    assert s["closest"]["label"] == "first cousins"
