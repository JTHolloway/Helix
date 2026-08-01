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
        me = add(c, "Thomas", "Whitcombe", birth="1992", sex="M")
        c.post("subject", {"id": me})
        dad = add(c, "William", "Whitcombe", me, "father", birth="1962", sex="M")
        add(c, "Sarah", "Pargeter", me, "mother", birth="1964", sex="F")
        add(c, "Edward", "Whitcombe", me, "sibling", birth="1995", sex="M")
        gran = add(c, "Joseph", "Whitcombe", dad, "father", birth="1930", sex="M")
        add(c, "Margaret", "Whitcombe", dad, "mother", birth="1932", sex="F")
        unc = add(c, "Henry", "Whitcombe", gran, "child", birth="1960", sex="M")
        add(c, "Laura", "Whitcombe", unc, "partner", birth="1961", sex="F")
        add(c, "Alice", "Whitcombe", unc, "child", birth="1990", sex="F")
        add(c, "Jack", "Whitcombe", unc, "child", birth="1993", sex="M")
        ggran = add(c, "Samuel", "Whitcombe", gran, "father", birth="1900", sex="M")
        gunc = add(c, "Arthur", "Whitcombe", ggran, "child", birth="1928", sex="M")
        add(c, "Doreen", "Whitcombe", gunc, "child", birth="1958", sex="F")
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
    assert r["subject_name"] == "Thomas Whitcombe"
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
            ("Thomas Whitcombe", "self", "you"),
            ("William Whitcombe", "immediate", "father"),
            ("Edward Whitcombe", "immediate", "brother"),
            ("Joseph Whitcombe", "grandparents", "grandfather"),
            ("Henry Whitcombe", "aunts_uncles", "uncle"),
            ("Alice Whitcombe", "cousins_1", "first cousin"),
            ("Samuel Whitcombe", "great_grandparents", "great-grandfather"),
            ("Arthur Whitcombe", "great_aunts_uncles", "great-uncle"),
            ("Doreen Whitcombe", "cousins_1_removed",
             "first cousin once removed"),
            ("Laura Whitcombe", "married_in", "married to your uncle")):
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
        "Alice Whitcombe", "Jack Whitcombe"}
    # ...and to my uncle they are his own children
    assert {names[p] for p in theirs.get("immediate", [])} >= {
        "Alice Whitcombe", "Jack Whitcombe", "Joseph Whitcombe"}
    # Doreen is my first cousin ONCE REMOVED and my uncle's first cousin --
    # the same two people, a different answer depending on who is asking,
    # which is the whole reason this is measured twice
    assert {names[p] for p in mine.get("cousins_1_removed", [])} == {
        "Doreen Whitcombe"}
    assert {names[p] for p in theirs.get("cousins_1", [])} == {
        "Doreen Whitcombe"}


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
    assert "Joseph Whitcombe" in h
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
    for name in ("Samuel Whitcombe", "Joseph Whitcombe", "Henry Whitcombe",
                 "Alice Whitcombe"):
        assert name in h, f"{name} is missing from the outline"
    # the great-grandfather, then his son
    assert h.index("Samuel Whitcombe") < h.index("Joseph Whitcombe"), (
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


# ---------------------------------------------------------- where they came from
def test_a_grandmother_recorded_as_irish_makes_you_a_quarter_irish(family):
    """The example the whole feature exists for. Recorded on one
    grandmother, a quarter of it should arrive on her grandchild -- and the
    other three quarters should be NAMED as unrecorded rather than quietly
    dropped, because "25% Irish" beside nothing reads as a rounding error
    and "25% Irish, 75% not recorded" reads as research still to do."""
    c, ids, _db = family
    gran = [p["id"] for p in c.get("relatives")["groups"][0]["people"]]  # noqa
    kath = next(p["id"] for grp in c.get("relatives")["groups"]
                for p in grp["people"] if p["name"] == "Margaret Whitcombe")
    c.post("person/heritage", {"id": kath, "heritage": [{"label": "Irish"}]})

    her = c.get("person", id=kath)["heritage"]
    assert her["declared"] == [{"label": "Irish", "share": 1.0, "pct": 100.0}]
    assert her["inherited"] is False

    mine = c.get("person", id=ids["me"])["heritage"]
    assert mine["inherited"] is True
    assert {m["label"]: m["pct"] for m in mine["mix"]} == {
        "Irish": 25.0, "not recorded": 75.0}

    dad = c.get("person", id=ids["dad"])["heritage"]
    assert {m["label"]: m["pct"] for m in dad["mix"]}["Irish"] == 50.0


def test_two_heritages_split_evenly_unless_you_say_otherwise(family):
    c, ids, _db = family
    me = ids["me"]
    c.post("person/heritage", {"id": me, "heritage": [
        {"label": "Irish"}, {"label": "Scottish"}]})
    got = {m["label"]: m["pct"] for m in c.get("person", id=me)["heritage"]["mix"]}
    assert got == {"Irish": 50.0, "Scottish": 50.0}

    c.post("person/heritage", {"id": me, "shares_given": True, "heritage": [
        {"label": "Irish", "share": 0.75}, {"label": "Scottish", "share": 0.25}]})
    got = {m["label"]: m["pct"] for m in c.get("person", id=me)["heritage"]["mix"]}
    assert got == {"Irish": 75.0, "Scottish": 25.0}


def test_a_persons_own_heritage_beats_what_they_would_inherit(family):
    """Recording that somebody was Irish is a statement about THEM, not a
    guess to be averaged with their parents'."""
    c, ids, _db = family
    c.post("person/heritage", {"id": ids["gran"],
                               "heritage": [{"label": "Cornish"}]})
    c.post("person/heritage", {"id": ids["dad"],
                               "heritage": [{"label": "Irish"}]})
    got = {m["label"]: m["pct"]
           for m in c.get("person", id=ids["dad"])["heritage"]["mix"]}
    assert got == {"Irish": 100.0}


def test_heritage_can_be_undone(family):
    c, ids, _db = family
    c.post("person/heritage", {"id": ids["me"], "heritage": [{"label": "Irish"}]})
    assert c.get("person", id=ids["me"])["heritage"]["declared"]
    c.post("undo", {})
    assert c.get("person", id=ids["me"])["heritage"]["declared"] == []


# ------------------------------------------------------------------- DNA ---
def test_how_much_dna_you_share_with_each_relation(family):
    """Halved at every step, and doubled again when BOTH members of the
    couple at the top are shared. That doubling is the whole of the
    difference between a full relation and a half one, and it is why the
    number cannot be read off the label: `Sarah` and `Henry` are both
    filed as your aunt and uncle and they are 25% and 12.5%."""
    c, ids, _db = family
    # A full aunt: a sibling of your father, so both grandparents are shared.
    # Added here rather than in the fixture so nothing else shifts under it.
    add(c, "Hannah", "Whitcombe", ids["dad"], "sibling", birth="1965", sex="F")
    want = {"William Whitcombe": "50%",       # father
            "Edward Whitcombe": "50%",     # full brother, both parents
            "Joseph Whitcombe": "25%",       # grandfather
            "Hannah Whitcombe": "25%",      # full aunt, both grandparents
            "Samuel Whitcombe": "12.5%",    # great-grandfather
            "Henry Whitcombe": "12.5%",    # half-uncle: Joseph only
            "Alice Whitcombe": "6.25%",     # his daughter, a half-first-cousin
            "Doreen Whitcombe": "3.13%"}    # great-uncle's daughter
    for grp in c.get("relatives")["groups"]:
        for p in grp["people"]:
            if p["name"] in want:
                got = c.get("person", id=p["id"])["dna"]["display"]
                assert got == want[p["name"]], f"{p['name']}: {got}"


def test_the_percentage_keeps_the_precision_that_means_something(family):
    """6.25 is a half-first-cousin. "6.2" is neither right nor convincing,
    and "6%" has thrown away the part that identifies the relation."""
    c, ids, _db = family
    from helix.graph.kinship import dna_display
    assert dna_display(0.5) == "50%"
    assert dna_display(0.125) == "12.5%"
    assert dna_display(0.0625) == "6.25%"
    assert dna_display(0.03125) == "3.13%"      # half up, not half to even
    assert dna_display(0.0000001) == "under 0.01%"
    assert dna_display(None) == ""


def test_somebody_married_in_shares_no_dna(family):
    """ZERO IS AN ANSWER. A husband, a step-parent and a friend of the
    family share no ancestor, and the honest figure for all three is 0% --
    not a blank, which reads as "the program could not work it out"."""
    c, ids, _db = family
    laura = next(p["id"] for grp in c.get("relatives")["groups"]
                 for p in grp["people"] if p["name"] == "Laura Whitcombe")
    d = c.get("person", id=laura)["dna"]
    assert d["share"] == 0.0
    assert d["display"] == "0%"
    assert "marriage" in d["why"], "it should say why it is zero"


def test_dna_is_blank_only_for_somebody_not_in_the_file(family):
    """`None` is kept for the one case where "could not be worked out" is
    genuinely true."""
    from helix.graph.kinship import dna_display, shared_dna
    from helix.graph.build import load
    from helix.store.db import connect
    c, ids, db = family
    g = load(connect(db, create=False))
    assert shared_dna(g, ids["me"], "nobody-at-all") is None
    assert dna_display(None) == ""
    assert dna_display(0.0) == "0%"


def test_the_bloodline_seats_are_numbered_like_an_ahnentafel(family):
    """1 is the person, 2 the father, 3 the mother, 2n and 2n+1 the parents
    of n. An empty seat is a hole in the research WITH AN ADDRESS, which is
    why the empty ones are returned rather than skipped."""
    c, ids, _db = family
    bl = c.get("person", id=ids["me"])["dna"]["bloodline"]
    seats = {r["slot"]: r for r in bl}
    assert len(bl) == 15
    assert seats[1]["name"] == "Thomas Whitcombe" and seats[1]["share"] == 1.0
    assert seats[2]["name"] == "William Whitcombe" and seats[2]["share"] == 0.5
    assert seats[3]["name"] == "Sarah Pargeter"
    assert seats[4]["name"] == "Joseph Whitcombe" and seats[4]["share"] == 0.25
    assert seats[5]["name"] == "Margaret Whitcombe"
    assert seats[8]["name"] == "Samuel Whitcombe" and seats[8]["share"] == 0.125
    assert seats[6]["id"] is None            # Sarah's father, not recorded
    assert seats[6]["share"] == 0.25


# ------------------------------------------------------- where to look next --
def test_the_research_list_ranks_a_blocked_line_above_a_missing_occupation(family):
    c, ids, _db = family
    d = c.get("gaps", limit=200)
    kinds = [g["kind"] for g in d["gaps"]]
    assert "parents" in kinds
    first_parents = kinds.index("parents")
    if "occupation" in kinds:
        assert first_parents < kinds.index("occupation")
    assert d["summary"]["count"] == d["total"] > d["shown"] or d["total"] == d["shown"]
    assert "stop" in d["summary"]["headline"] or d["summary"]["count"]


def test_every_research_question_says_where_to_look(family):
    """Rule 8: an error message -- or a prompt -- that does not say what to
    do next is a nag."""
    c, ids, _db = family
    for g in c.get("gaps", limit=25)["gaps"]:
        assert g["question"].endswith("?")
        assert g["why"]
        assert g["where"], f"{g['question']} says nowhere to look"


def test_the_research_list_follows_the_chart_not_the_whole_file(family):
    """Ask for the gaps while looking at a chart narrowed to first cousins
    and you get the gaps on that chart. A to-do list about somebody who is
    not on screen is a list nobody acts on."""
    c, ids, _db = family
    wide = c.get("gaps", limit=500, focus="all")
    narrow = c.get("gaps", limit=500, focus="all", max_cousin_degree=0)
    assert narrow["considered"] < wide["considered"]
    assert narrow["scope"] == "this chart"
    assert c.get("gaps", limit=500, **{"all": "1"})["scope"] == "everybody"


def test_two_people_with_the_same_name_are_told_apart(family):
    """The case the list is FOR: two ancestors recorded as nothing but a
    surname produce two identical questions."""
    c, ids, _db = family
    gs = c.get("gaps", limit=200)["gaps"]
    seen: dict[str, set] = {}
    for g in gs:
        seen.setdefault(g["question"], set()).add(g["pid"])
    for q, pids in seen.items():
        if len(pids) < 2:
            continue
        rels = {next(x["relation"] for x in gs if x["pid"] == p) for p in pids}
        assert len(rels) == len(pids), f"{q} is ambiguous: {rels}"


def test_a_profile_says_what_to_look_up_about_that_person(family):
    c, ids, _db = family
    gaps = c.get("person", id=ids["ggran"])["gaps"]
    assert gaps and all(g["pid"] == ids["ggran"] for g in gaps)


# ------------------------------------------------ editing from the profile --
def test_a_name_corrected_in_the_profile_changes_everywhere(family):
    """One save, and the chart, the sidebar and the printout all say the new
    name. Written to only one of them, a file quietly holds two versions of
    the same person."""
    c, ids, _db = family
    c.post("person", {"id": ids["uncle"], "given": "Martyn",
                      "surname": "Whitcumbe", "sex": "M"})
    assert c.get("person", id=ids["uncle"])["name"] == "Martyn Whitcumbe"
    names = [p["name"] for grp in c.get("relatives")["groups"]
             for p in grp["people"]]
    assert "Martyn Whitcumbe" in names and "Henry Whitcombe" not in names
    plan = c.get("plan", design="radial_family", focus="all")
    texts = [e.get("text", "") for e in plan["elements"] if e["kind"] == "text"]
    assert any("Martyn" in t or "Whitcumbe" in t for t in texts)
    sheet = _fetch(c, f"/print/profile?id={ids['uncle']}")
    assert "Martyn Whitcumbe" in sheet


def test_saving_one_field_from_the_profile_leaves_the_others_alone(family):
    """The trap that cost a birth date: an absent key means 'leave this
    alone' and an empty string means 'clear it'."""
    c, ids, _db = family
    before = c.get("person", id=ids["dad"])
    c.post("person", {"id": ids["dad"], "birth_place": "Bath"})
    after = c.get("person", id=ids["dad"])
    assert after["birth_place"] == "Bath"
    assert after["birth"] == before["birth"]
    assert after["name"] == before["name"]


# ----------------------------------------------------------- on paper ------
def test_a_printed_profile_is_something_you_can_file(family):
    """WHAT IS KNOWN, AND NOTHING ELSE. A printed profile goes in a folder
    with the certificates and is read again in ten years; a research to-do
    list printed onto it is out of date the week it comes off the printer
    and looks like a reproach for the rest of its life. The questions get
    their own sheet."""
    c, ids, _db = family
    kath = next(p["id"] for grp in c.get("relatives")["groups"]
                for p in grp["people"] if p["name"] == "Margaret Whitcombe")
    c.post("person/heritage", {"id": kath, "heritage": [{"label": "Irish"}]})
    sheet = _fetch(c, f"/print/profile?id={ids['me']}")
    assert "Where they came from" in sheet and "Irish" in sheet
    assert "Bloodline" in sheet and "Grandparents" in sheet
    # NEVER A BARE PERCENTAGE ON PAPER. Read in twenty years it would be
    # taken for something somebody measured.
    assert "not a test result" in sheet
    assert "Where to look next" not in sheet


def test_the_research_list_prints_on_its_own_sheet(family):
    c, ids, _db = family
    sheet = _fetch(c, "/print/research")
    assert "where to look next" in sheet.lower()
    assert "☐" in sheet, "a list you take with you wants ticking off"
    assert "parents" in sheet.lower()


def test_printing_everybody_still_works_with_the_new_sections(family):
    c, ids, _db = family
    sheet = _fetch(c, "/print/profiles?all=1")
    assert sheet.count("<article class=person>") == c.get("relatives")["total"]


# ------------------------------------------------- the family, in order ----
def test_the_whole_family_reads_as_one_story(family):
    """A chart says who was related to whom and nothing about when; a
    person's own timeline shows one life. This is the third view."""
    c, ids, _db = family
    d = c.get("family-timeline", **{"all": "1"})
    kinds = [e["kind"] for e in d["events"]]
    assert "birth" in kinds
    assert d["counts"]["birth"] >= 7
    years = [e["year"] for e in d["events"]]
    assert years == sorted(years), "it has to be in order"
    assert d["span"][0] <= d["span"][1]


def test_a_stretch_with_nothing_in_it_is_reported(family):
    """A decade with no events between two dense stretches is usually not a
    family that stopped happening; it is a register nobody has looked at."""
    c, ids, _db = family
    d = c.get("family-timeline", **{"all": "1"})
    assert isinstance(d["quiet"], list)
    for g in d["quiet"]:
        assert g["years"] >= 10 and g["to"] > g["from"]


def test_only_a_known_day_becomes_an_anniversary(family):
    """A date recorded as "1841" has no day in it, and offering somebody a
    birthday the program invented is worse than offering none."""
    c, ids, _db = family
    d = c.get("family-timeline", **{"all": "1"})
    for a in d["anniversaries"]:
        assert 0 <= a["in_days"] <= 31
        assert a["kind"] in ("birthday", "anniversary")


def test_the_chronicle_prints(family):
    c, ids, _db = family
    h = _fetch(c, "/print/chronicle?all=1")
    assert "in order" in h.lower()
    assert "Thomas Whitcombe" in h


# ------------------------------------------------ first and middle names ---
def test_a_middle_name_is_two_boxes_and_one_field(family):
    """`given` holds the whole string -- that is what a certificate says and
    what GEDCOM writes -- but nobody thinks of "Harriet Florence" as one
    thing to type, and a middle name was the commonest thing left out."""
    c, ids, _db = family
    c.post("person", {"id": ids["me"], "given": "Thomas Alexander"})
    d = c.get("person", id=ids["me"])
    assert d["given"] == "Thomas Alexander"
    assert d["name"] == "Thomas Alexander Whitcombe"
    # and it survives a trip through GEDCOM
    import urllib.request
    with urllib.request.urlopen(f"{c.base}/api/gedcom") as r:
        text = r.read().decode()
    assert "2 GIVN Thomas Alexander" in text


# -------------------------------------------- families that married in ----
def test_nobody_is_told_to_research_an_in_laws_parents(family):
    """WHOSE LINES ARE WORTH FOLLOWING is decided by the root person, and
    only by that. Somebody who married into the family is at every
    gathering and is not somebody whose parents you are researching --
    their line is a different family's line. Asked for it anyway, the panel
    filled with questions about surnames nobody in the family carries."""
    c, ids, _db = family
    d = c.get("gaps", limit=400, **{"all": "1"})
    names = {p["id"]: p for p in c.get("meta")["people"]}
    rel = c.get("relatives")
    married = {p["id"] for g in rel["groups"] if g["key"] == "married_in"
               for p in g["people"]}
    assert married, "the fixture has nobody who married in"
    for g in d["gaps"]:
        assert not (g["kind"] == "parents" and g["pid"] in married), \
            f"asked who {g['name']}'s parents were, and they married in"
    assert not any(g["key"] == "in_laws" for g in d["groups"])


def test_moving_the_root_is_what_makes_a_line_worth_following(family):
    """The same woman, asked about from two different chairs. Married into
    the family she is a stranger's daughter; make her grandchild the root
    and she is a grandmother, her line is the direct line, and her parents
    are the first question on the list. There is no setting for this: it is
    what the root person MEANS."""
    c, ids, _db = family
    # Laura married the subject's uncle. Put her children in the marriage,
    # so she is a mother rather than only a wife -- which is the shape the
    # question is really about.
    laura = next(p["id"] for g in c.get("relatives")["groups"]
                 for p in g["people"] if p["name"] == "Laura Whitcombe")
    u = c.get("person", id=laura)["families"][0]["union_id"]
    kids = [p["id"] for p in c.get("meta")["people"]
            if p["name"] in ("Alice Whitcombe", "Jack Whitcombe")]
    for kid in kids:
        c.post("union/child", {"union_id": u, "person_id": kid,
                               "action": "attach"})

    asked = lambda: {g["pid"] for g in c.get("gaps", limit=400,
                                             **{"all": "1"})["gaps"]
                     if g["kind"] == "parents"}
    assert laura not in asked(), "asked about an in-law's parents"
    c.post("subject", {"id": kids[0]})            # the chart moves to Alice
    assert laura in asked(), \
        "made the root her daughter and still nobody asks about her parents"


# ------------------------------------------------------- related lines ----
def test_a_profile_says_whether_the_parents_were_related(family):
    c, ids, _db = family
    d = c.get("person", id=ids["me"])["inbreeding"]
    assert d["coefficient"] == 0.0 and d["percent"] == "0%"
    assert "in this file" in d["why"], "it must say how far it can see"
    assert d["married_a_relative"] == []


def test_somebody_with_one_parent_recorded_gets_no_figure(family):
    c, ids, _db = family
    d = c.get("person", id=ids["gran"])["inbreeding"]
    assert d["coefficient"] is None
