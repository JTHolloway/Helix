"""The ancestry side of the program, driven over real HTTP.

Helix started as a way to draw a family and print it. These are the parts
that make it somewhere to KEEP one: the relatives sidebar, the profile with
its photograph and its facts, the narrowing that decides how far a chart
spreads, and the printouts.

Over the wire rather than by function call, for the reason in
`test_records.py`: `ThreadingHTTPServer` hands every request to its own
thread and a SQLite connection made on the main thread cannot be used from
one. Every database-backed endpoint in this program once failed exactly that
way, and the tests that existed did not catch it because they called the
handlers directly.
"""
from __future__ import annotations

import base64
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import pytest

from helix.server import make_server
from helix.store.db import connect, set_setting

from test_records import Client, add

# A one-pixel PNG. Small enough to inline, real enough to be decoded, stored,
# hashed and served back with the right content type.
PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM"
    "IQAAAABJRU5ErkJggg==")
PIXEL_URL = "data:image/png;base64," + base64.b64encode(PIXEL).decode()


@pytest.fixture
def family(tmp_path):
    """Three generations with a cousin in them, behind a running server.

    Built through the API, so the fixture is also a check that a family can
    be entered the way a person would enter it.
    """
    db = tmp_path / "kin.helix"
    con = connect(db)
    set_setting(con, "project_title", "Kin test")
    con.close()
    srv = make_server(str(db), port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    c = Client(f"http://127.0.0.1:{srv.server_port}")
    try:
        # SEX IS RECORDED, because the words depend on it: "father" where
        # it is known, "parent" where it is not. Leaving it out would test
        # the neutral fallback and nothing else.
        me = add(c, "James", "Holloway", birth="1992", sex="M")
        c.post("subject", {"id": me})
        dad = add(c, "David", "Holloway", me, "father", birth="1962", sex="M")
        add(c, "Michaela", "Reed", me, "mother", birth="1964", sex="F")
        add(c, "Anthony", "Holloway", me, "sibling", birth="1995", sex="M")
        gran = add(c, "Peter", "Holloway", dad, "father", birth="1930", sex="M")
        add(c, "Kathleen", "Holloway", dad, "mother", birth="1932", sex="F")
        unc = add(c, "Martin", "Holloway", gran, "child", birth="1960", sex="M")
        add(c, "Laura", "Holloway", unc, "partner", birth="1961", sex="F")
        add(c, "Alice", "Holloway", unc, "child", birth="1990", sex="F")
        add(c, "Jack", "Holloway", unc, "child", birth="1993", sex="M")
        ggran = add(c, "Thomas", "Holloway", gran, "father", birth="1900", sex="M")
        gunc = add(c, "William", "Holloway", ggran, "child", birth="1928", sex="M")
        add(c, "Doreen", "Holloway", gunc, "child", birth="1958", sex="F")
        yield c, {"me": me, "dad": dad, "gran": gran, "uncle": unc,
                  "ggran": ggran, "great_uncle": gunc}, db
    finally:
        srv.shutdown()
        srv.server_close()


def by_name(groups, name):
    for grp in groups:
        for p in grp["people"]:
            if p["name"] == name:
                return grp, p
    raise AssertionError(f"{name} is in no tab at all")


# ------------------------------------------------------------ the sidebar --
def test_the_sidebar_puts_everybody_in_a_tab(family):
    c, ids, _db = family
    r = c.get("relatives")
    assert r["subject_name"] == "James Holloway"
    seen = [p["id"] for grp in r["groups"] for p in grp["people"]]
    assert len(seen) == r["total"] == len(set(seen))


def test_the_tabs_run_closest_first(family):
    """You should not have to scroll past the second cousins to reach your
    mother. The order is the one people name their family in."""
    c, ids, _db = family
    groups = c.get("relatives")["groups"]
    order = [g["key"] for g in groups]
    assert order.index("self") < order.index("immediate")
    assert order.index("immediate") < order.index("grandparents")
    assert order.index("grandparents") < order.index("aunts_uncles")
    assert order.index("aunts_uncles") < order.index("cousins_1")


def test_each_person_is_filed_under_the_right_relation(family):
    c, ids, _db = family
    groups = c.get("relatives")["groups"]
    for name, group, relation in (
            ("James Holloway", "self", "you"),
            ("David Holloway", "immediate", "father"),
            ("Anthony Holloway", "immediate", "brother"),
            ("Peter Holloway", "grandparents", "grandfather"),
            ("Martin Holloway", "aunts_uncles", "uncle"),
            ("Alice Holloway", "cousins_1", "first cousin"),
            ("Thomas Holloway", "great_grandparents", "great-grandfather"),
            ("William Holloway", "great_aunts_uncles", "great-uncle"),
            ("Doreen Holloway", "cousins_1_removed",
             "first cousin once removed"),
            ("Laura Holloway", "married_in", "married to your uncle")):
        grp, person = by_name(groups, name)
        assert grp["key"] == group, f"{name} is under {grp['key']}"
        assert person["relation"] == relation, f"{name}: {person['relation']}"


# -------------------------------------------------------------- a profile --
def test_a_profile_says_how_they_are_related_and_how_far(family):
    c, ids, _db = family
    d = c.get("kin", id=ids["uncle"])
    assert d["relation"]["label"] == "uncle"
    assert d["relation"]["up"] == 2 and d["relation"]["down"] == 1
    assert d["relation"]["steps"] == 3
    assert d["counts"]["children"] == 2
    assert d["counts"]["siblings"] == 1


def test_clicking_somebody_lights_up_THEIR_relatives_not_yours(family):
    """Two different measurements from two different origins. Read the
    second off the first and you get YOUR cousins in a halo round somebody
    else."""
    c, ids, _db = family
    mine = c.get("kin", id=ids["me"])["highlight"]
    theirs = c.get("kin", id=ids["uncle"])["highlight"]
    names = {}
    for grp in c.get("relatives")["groups"]:
        for p in grp["people"]:
            names[p["id"]] = p["name"]
    # Alice and Jack are MY first cousins
    assert {names[p] for p in mine.get("cousins_1", [])} == {
        "Alice Holloway", "Jack Holloway"}
    # ...and to my uncle they are his own children
    assert {names[p] for p in theirs.get("immediate", [])} >= {
        "Alice Holloway", "Jack Holloway", "Peter Holloway"}
    # Doreen is my first cousin ONCE REMOVED and my uncle's first cousin --
    # the same two people, a different answer depending on who is asking,
    # which is the whole reason this is measured twice
    assert {names[p] for p in mine.get("cousins_1_removed", [])} == {
        "Doreen Holloway"}
    assert {names[p] for p in theirs.get("cousins_1", [])} == {
        "Doreen Holloway"}


def test_a_profile_holds_what_you_know_about_them(family):
    """Birth place, occupation, education and free notes. The whole point of
    keeping a file rather than drawing a picture."""
    c, ids, _db = family
    c.post("person", {"id": ids["gran"], "birth_place": "Openshaw",
                      "occupation": "Boilermaker",
                      "education": "Ashton Grammar",
                      "notes": "Kept pigeons on the yard roof."})
    d = c.get("person", id=ids["gran"])
    assert d["birth_place"] == "Openshaw"
    assert d["occupation"] == "Boilermaker"
    assert d["education"] == "Ashton Grammar"
    assert d["notes"].startswith("Kept pigeons")
    # and it survives a reload, because it is rows and not memory
    assert c.get("person", id=ids["gran"])["occupation"] == "Boilermaker"


def test_clearing_a_fact_does_not_wipe_the_others(family):
    c, ids, _db = family
    c.post("person", {"id": ids["gran"], "occupation": "Boilermaker",
                      "education": "Ashton Grammar"})
    c.post("person", {"id": ids["gran"], "occupation": ""})
    d = c.get("person", id=ids["gran"])
    assert d["occupation"] == "" and d["education"] == "Ashton Grammar"


# ---------------------------------------------------------- a photograph --
def test_a_photograph_is_copied_beside_the_family_file(family):
    """Not referenced. A path into somebody's Pictures folder is a promise
    the program cannot keep: the folder gets tidied, the phone gets replaced,
    and the file that survives is the one thing this program tells people to
    keep."""
    c, ids, db = family
    out = c.post("person/photo", {"id": ids["gran"], "filename": "gran.png",
                                  "data": PIXEL_URL})
    album = Path(db).parent / "kin-media"
    assert (album / out["name"]).is_file()
    assert (album / out["name"]).read_bytes() == PIXEL
    d = c.get("person", id=ids["gran"])
    assert [p["portrait"] for p in d["photos"]] == [True]


def test_the_same_photograph_twice_is_stored_once(family):
    """Named by the hash of its own bytes. The same picture attached to five
    brothers is one file, and re-adding one somebody already has is silently
    the same picture rather than a second copy."""
    c, ids, db = family
    a = c.post("person/photo", {"id": ids["gran"], "data": PIXEL_URL})
    b = c.post("person/photo", {"id": ids["dad"], "data": PIXEL_URL})
    assert a["name"] == b["name"]
    album = Path(db).parent / "kin-media"
    assert len(list(album.iterdir())) == 1


def test_a_new_portrait_demotes_the_old_one_rather_than_deleting_it(family):
    c, ids, _db = family
    c.post("person/photo", {"id": ids["gran"], "data": PIXEL_URL})
    other = "data:image/png;base64," + base64.b64encode(PIXEL + b"\0").decode()
    c.post("person/photo", {"id": ids["gran"], "data": other})
    photos = c.get("person", id=ids["gran"])["photos"]
    assert len(photos) == 2, "the earlier picture is still a picture of them"
    assert sum(1 for p in photos if p["portrait"]) == 1


def test_a_picture_is_served_back(family):
    c, ids, _db = family
    out = c.post("person/photo", {"id": ids["gran"], "data": PIXEL_URL})
    with urllib.request.urlopen(f"{c.base}/api/media?name={out['name']}") as r:
        assert r.headers["Content-Type"] == "image/png"
        assert r.read() == PIXEL


@pytest.mark.parametrize("name", [
    "../../etc/passwd", "..%2f..%2fkin.helix", "/etc/passwd", ".hidden", ""])
def test_a_picture_name_cannot_point_outside_the_album(family, name):
    """The name arrives over HTTP, so it is checked rather than trusted."""
    c, _ids, _db = family
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(
            f"{c.base}/api/media?name={urllib.parse.quote(name, safe='')}")
    assert e.value.code == 404


def test_an_archive_carries_the_pictures(family):
    """The `media` rows name files that live beside the database, so a zip
    holding only the rows is a zip of captions with nothing under them."""
    c, ids, _db = family
    c.post("person/photo", {"id": ids["gran"], "data": PIXEL_URL})
    path = c.post("archive", {})["path"]
    with zipfile.ZipFile(path) as z:
        assert [n for n in z.namelist() if n.startswith("media/")]


# ------------------------------------------------------------ narrowing ----
def test_narrowing_removes_people_from_the_chart(family):
    c, _ids, _db = family
    full = c.get("plan", design="radial_family", focus="bloodline")
    cut = c.get("plan", design="radial_family", focus="bloodline",
                max_cousin_degree=0)
    assert cut["meta"]["people"] < full["meta"]["people"]


def test_a_narrowed_chart_says_what_it_left_off(family):
    """You cannot tell a family of two from a family of nine you narrowed
    down, so every marriage that lost children carries a mark."""
    c, _ids, _db = family
    cut = c.get("plan", design="radial_family", focus="bloodline",
                max_cousin_degree=0)
    el = cut["meta"]["extra"]["elided"]
    assert el["marriages"] > 0 and el["people"] > 0
    marks = [e for e in cut["elements"] if e.get("role") == "elided"]
    assert len(marks) == el["marriages"]


def test_narrowing_lays_the_chart_out_again_rather_than_hiding_branches(family):
    """The difference between a chart with the cousins removed and a chart
    with a gap where the cousins were. Everybody left has to have moved."""
    c, _ids, _db = family
    full = c.get("plan", design="radial_family", focus="bloodline")
    cut = c.get("plan", design="radial_family", focus="bloodline",
                max_cousin_degree=0)

    def at(plan):
        return {e["person_id"]: (round(e["x"], 2), round(e["y"], 2))
                for e in plan["elements"]
                if e.get("kind") == "text" and e.get("person_id")}

    a, b = at(full), at(cut)
    shared = set(a) & set(b)
    assert shared, "the two charts have nobody in common"
    assert any(a[p] != b[p] for p in shared), (
        "every survivor is in exactly the same place, so the branches were "
        "hidden rather than the chart being laid out again")


def test_you_are_never_narrowed_off_your_own_chart(family):
    c, ids, _db = family
    cut = c.get("plan", design="radial_family", focus="bloodline",
                max_steps=0, married_in=0)
    assert any(e.get("person_id") == ids["me"] for e in cut["elements"])


def test_the_groups_offered_are_the_groups_that_exist(family):
    """The scoping screen is built from this list, so a key here that the
    classifier never produces is a switch that does nothing."""
    c, _ids, _db = family
    offered = {g["key"] for g in c.get("groups")}
    used = {grp["key"] for grp in c.get("relatives")["groups"]}
    assert used <= offered
    assert {"self", "immediate", "cousins_1", "married_in"} <= offered


def test_saving_one_fact_does_not_wipe_another(family):
    """The rule this module lives by: never destroy what somebody typed.

    A request that does not mention a field is not a request to clear it.
    Written the other way round -- absent read as empty -- saving somebody's
    birthplace sent an empty date along with it and wiped the birth date
    that was already there, and the profile then said "dates unknown" two
    lines above the date it was still showing.
    """
    c, ids, _db = family
    before = c.get("person", id=ids["gran"])
    assert before["birth"], "this fixture person has no birth date to lose"
    c.post("person", {"id": ids["gran"], "birth_place": "Openshaw"})
    after = c.get("person", id=ids["gran"])
    assert after["birth"] == before["birth"]
    assert after["birth_place"] == "Openshaw"
    assert after["life"] == before["life"]


def test_a_year_is_the_year_the_date_is_in(family):
    """11 August 1967 is 1967. Taken as a rounded midpoint it came out as
    1968, so everybody born in the second half of a year was a year out --
    on their profile, and under their name on every chart."""
    c, ids, _db = family
    c.post("person", {"id": ids["gran"], "birth": "11 Aug 1967"})
    d = c.get("person", id=ids["gran"])
    assert d["birth"] == "11 Aug 1967"
    assert d["life"].startswith("1967"), d["life"]


# --------------------------------------------------------------- printing --
def _fetch(c, path):
    with urllib.request.urlopen(f"{c.base}{path}") as r:
        assert r.headers["Content-Type"].startswith("text/html")
        return r.read().decode()


def test_one_profile_prints(family):
    c, ids, _db = family
    c.post("person", {"id": ids["gran"], "occupation": "Boilermaker",
                      "notes": "Kept pigeons."})
    c.post("person/photo", {"id": ids["gran"], "data": PIXEL_URL})
    h = _fetch(c, f"/print/profile?id={ids['gran']}")
    assert "Peter Holloway" in h
    assert "Boilermaker" in h and "Kept pigeons." in h
    assert "/api/media?name=" in h, "the portrait is not on the page"
    assert "grandfather" in h, "it does not say how they are related to you"
    assert "@media print" in h


def test_everybody_prints_one_to_a_page(family):
    c, _ids, _db = family
    h = _fetch(c, "/print/profiles?all=1")
    n = c.get("relatives")["total"]
    assert h.count("<article class=person>") == n
    assert "page-break-after:always" in h


def test_a_printout_covers_the_same_people_as_the_chart(family):
    """Print a chart narrowed to first cousins and then a dossier of
    everybody and the two do not describe the same family."""
    c, _ids, _db = family
    everyone = _fetch(c, "/print/profiles?all=1").count("<article class=person>")
    narrowed = _fetch(
        c, "/print/profiles?focus=bloodline&max_cousin_degree=0"
    ).count("<article class=person>")
    assert 0 < narrowed < everyone


def test_the_tree_prints_as_an_outline(family):
    """A chart is a picture, and a picture cannot be read down a column or
    ticked off against a list."""
    c, _ids, _db = family
    h = _fetch(c, "/print/outline?focus=bloodline")
    for name in ("Thomas Holloway", "Peter Holloway", "Martin Holloway",
                 "Alice Holloway"):
        assert name in h, f"{name} is missing from the outline"
    assert h.index("Thomas Holloway") < h.index("Peter Holloway"), (
        "descendants should be indented under their parents")


def test_the_outline_says_where_it_was_cut(family):
    c, _ids, _db = family
    h = _fetch(c, "/print/outline?focus=bloodline&max_cousin_degree=0")
    assert "not on this chart" in h


# ------------------------------------------------------------ the window --
def test_every_script_the_page_asks_for_is_served(family):
    """Cheap, and it catches the mistake that breaks the whole window: a
    module renamed or a path typed wrong shows up as a blank page and a
    console error nobody sees from Python."""
    import re
    c, _ids, _db = family
    with urllib.request.urlopen(f"{c.base}/") as r:
        page = r.read().decode()
    wanted = set(re.findall(r'(?:src|href)="([^"]+\.(?:js|css))"', page))
    assert wanted, "the page pulls in no assets at all"
    seen = set()
    todo = list(wanted)
    while todo:
        rel = todo.pop()
        if rel in seen:
            continue
        seen.add(rel)
        with urllib.request.urlopen(f"{c.base}/{rel.lstrip('/')}") as r:
            body = r.read().decode()
        if rel.endswith(".js"):
            base = rel.rsplit("/", 1)[0]
            for imp in re.findall(r"from\s+'\.\/([^']+)'", body):
                todo.append(f"{base}/{imp}")


def test_the_window_opens_on_the_flagship_design(family):
    """`radial_family` is the design every other part of this program is
    written around, and the one that draws the marks for a narrowed branch.
    The window used to open on the older one-slot-per-person layout, so the
    flagship was something you had to go and find."""
    c, _ids, _db = family
    with urllib.request.urlopen(f"{c.base}/js/main.js") as r:
        js = r.read().decode()
    assert "design: 'radial_family'" in js


def test_every_design_says_what_it_left_off(family):
    """The flagship marks each family; the other eighteen share the same
    scoping and would otherwise drop people silently."""
    c, _ids, _db = family
    for design in ("radial_family", "radial_rings", "dendrogram"):
        plan = c.get("plan", design=design, focus="bloodline",
                     max_cousin_degree=0)
        el = plan["meta"]["extra"].get("elided")
        assert el and el["people"] > 0, f"{design} says nothing about what it cut"
