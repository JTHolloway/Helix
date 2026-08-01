"""The record system, driven over real HTTP against a running server.

WHY HTTP AND NOT FUNCTION CALLS. `ThreadingHTTPServer` hands every request to
its own thread, and a SQLite connection made on the main thread cannot be
used from one. Every database-backed endpoint in this program once failed
that way and no test caught it, because the tests that existed called the
handler functions directly. A test that does not go over the wire does not
test the thing that broke. So these start a real server on a real port.

The centrepiece is `test_the_ten_step_acceptance_sequence`, which is the
sequence at the end of `docs/DATA_ENTRY_UI.md`, in order, with nothing
touching the database except the API.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from helix.server import make_server
from helix.store.db import connect, set_setting


# ------------------------------------------------------------------ fixtures
class Client:
    """The API as a person's browser sees it."""

    def __init__(self, base: str):
        self.base = base

    def get(self, path: str, **params):
        q = "&".join(f"{k}={urllib.parse.quote(str(v))}"
                     for k, v in params.items() if v not in (None, ""))
        url = f"{self.base}/api/{path}" + (f"?{q}" if q else "")
        try:
            with urllib.request.urlopen(url) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise AssertionError(
                f"GET /api/{path} failed: {json.loads(e.read()).get('error')}")

    def post(self, path: str, body: dict | None = None):
        req = urllib.request.Request(
            f"{self.base}/api/{path}",
            data=json.dumps(body or {}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise AssertionError(
                f"POST /api/{path} failed: {json.loads(e.read()).get('error')}")

    def post_expecting_failure(self, path: str, body: dict):
        req = urllib.request.Request(
            f"{self.base}/api/{path}", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        return json.loads(e.value.read())


@pytest.fixture
def app(tmp_path):
    """An empty family file behind a running server, on a free port."""
    db = tmp_path / "mine.helix"
    con = connect(db)
    set_setting(con, "project_title", "Test family")
    con.close()

    srv = make_server(str(db), port=0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield Client(f"http://127.0.0.1:{srv.server_port}")
    finally:
        srv.shutdown()
        srv.server_close()


def add(c: Client, given, surname, to=None, how=None, **kw) -> str:
    body = {"given": given, "surname": surname, **kw}
    if to:
        body["attach"] = {"to": to, "as": how}
    return c.post("person/new", body)["id"]


def names(rows) -> set[str]:
    return {r["name"] for r in rows}


# ============================================================ the ten steps ===
def test_the_ten_step_acceptance_sequence(app, tmp_path):
    """docs/DATA_ENTRY_UI.md, "Done when", start to finish."""
    c = app

    # 1 -- start from an empty file
    assert c.get("meta")["stats"]["people"] == 0

    # 2 -- add yourself
    me = add(c, "James", "Pargeter", birth="1992")
    c.post("subject", {"id": me})
    assert c.get("person", id=me)["is_subject"]

    # 3 -- parents, their parents, their parents
    dad = add(c, "Michael", "Pargeter", me, "father", birth="1962")
    mum = add(c, "Susan", "Hallam", me, "mother", birth="1964")
    gpa = add(c, "Arthur", "Pargeter", dad, "father", birth="1935", death="2011")
    gma = add(c, "Edith", "Marlow", dad, "mother", birth="1937")
    ggpa = add(c, "Walter", "Pargeter", gpa, "father", birth="abt 1900")

    assert names(c.get("person", id=me)["parents"]) == {"Michael Pargeter",
                                                        "Susan Hallam"}
    assert names(c.get("person", id=dad)["parents"]) == {"Arthur Pargeter",
                                                         "Edith Marlow"}
    assert [p["id"] for p in c.get("person", id=gpa)["parents"]] == [ggpa]
    # both parents landed in ONE family, not one each
    assert len(c.get("person", id=gpa)["families"]) == 1

    # 4 -- add your siblings
    sis = add(c, "Claire", "Pargeter", me, "sibling", birth="1995")
    assert names(c.get("person", id=me)["siblings"]) == {"Claire Pargeter"}
    assert names(c.get("person", id=sis)["parents"]) == {"Michael Pargeter",
                                                         "Susan Hallam"}

    # 5 -- your father's second partner, and a half-sibling under her
    rachel = add(c, "Rachel", "Dunmore", dad, "partner", birth="1960")
    fams = {f["partner"]["name"]: f for f in c.get("person", id=dad)["families"]
            if f["partner"]}
    assert set(fams) == {"Susan Hallam", "Rachel Dunmore"}
    # "+ Add a child" appears once per partner, so the dialogue already knows
    # which family it is attaching to.
    half = c.post("person/new", {
        "given": "Hannah", "surname": "Pargeter", "birth": "1986",
        "attach": {"to": dad, "as": "child",
                   "union": fams["Rachel Dunmore"]["union_id"]}})["id"]

    # 6 -- the half-sibling hangs off the OTHER partner, not yours
    dadfams = {f["partner"]["name"]: names(f["children"])
               for f in c.get("person", id=dad)["families"] if f["partner"]}
    assert dadfams["Susan Hallam"] == {"James Pargeter", "Claire Pargeter"}
    assert dadfams["Rachel Dunmore"] == {"Hannah Pargeter"}
    # and she is a half-sibling of yours: shares one parent, not two
    assert "Hannah Pargeter" in names(c.get("person", id=me)["siblings"])
    assert names(c.get("person", id=half)["parents"]) == {"Michael Pargeter",
                                                          "Rachel Dunmore"}

    # 7 -- fix a typo in a date
    assert c.get("person", id=half)["birth"] == "1986"
    c.post("person", {"id": half, "birth": "1968"})
    assert c.get("person", id=half)["birth"] == "1968"

    # 8 -- undo it, redo it
    assert c.post("undo")["ok"]
    assert c.get("person", id=half)["birth"] == "1986"
    assert c.post("redo")["ok"]
    assert c.get("person", id=half)["birth"] == "1968"

    # 9 -- close the browser and reopen: everything intact.
    #      A fresh connection to the file on disk is exactly that test.
    con = connect(tmp_path / "mine.helix", backup_daily=False)
    from helix.graph import build
    g = build.load(con)
    assert len(g.people) == 9      # me, 2 parents, 2 grandparents, a great-
    #                                grandfather, a sister, Rachel, Hannah
    assert {p.full_name for p in g.people.values()} > {"James Pargeter",
                                                       "Hannah Pargeter",
                                                       "Walter Pargeter"}
    con.close()

    # 10 -- export a 1000 x 1000 mm SVG
    out = tmp_path / "wall.svg"
    from helix.layout import registry
    from helix.layout.base import LayoutSettings
    from helix.layout.engines import radial  # noqa: F401
    from helix.render import svg as svgrender
    from helix.style.tokens import Style
    style = Style.load("panel1m")
    style.set("canvas.width_mm", 1000)
    style.set("canvas.height_mm", 1000)
    plan = registry.run("radial_rings", build.load(connect(tmp_path / "mine.helix")),
                        LayoutSettings(engine="radial_rings", subject_id=me,
                                       focus="bloodline"), style)
    out.write_text(svgrender.render(plan))
    assert out.stat().st_size > 2000
    assert 'width="1000mm"' in out.read_text()
    art = out.read_text()
    for who in ("James", "Hannah", "Walter"):
        assert who in art, f"{who} should be engraved on the chart"


# ====================================================== the rules, one by one ==
def test_remove_from_tree_never_deletes_a_person(app, tmp_path):
    """Rule 1. A wrong ancestor deleted at midnight is a real loss."""
    c = app
    me = add(c, "James", "Pargeter")
    c.post("subject", {"id": me})
    wrong = add(c, "Wrong", "Person", me, "father")

    c.post("person/retire", {"id": wrong})
    assert c.get("meta")["stats"]["people"] == 1          # off the chart
    assert not c.get("person", id=me)["parents"]           # and detached

    con = connect(tmp_path / "mine.helix", backup_daily=False)
    row = con.execute("SELECT active FROM person WHERE id=?", (wrong,)).fetchone()
    assert row is not None, "the person row was DELETED -- rule 1 broken"
    assert row["active"] == 0
    con.close()

    # and it comes back
    assert c.post("undo")["ok"]
    assert c.get("meta")["stats"]["people"] == 2
    assert names(c.get("person", id=me)["parents"]) == {"Wrong Person"}


def test_undo_takes_back_a_whole_action_not_a_third_of_one(app):
    """Adding a father writes a person, a name and two link rows. Ctrl-Z
    must take back the father, not leave a nameless ghost holding a link."""
    c = app
    me = add(c, "James", "Pargeter")
    add(c, "Michael", "Pargeter", me, "father")
    assert c.get("meta")["stats"]["people"] == 2

    c.post("undo")
    assert c.get("meta")["stats"]["people"] == 1
    assert c.get("person", id=me)["parents"] == []
    assert c.get("person", id=me)["families"] == []


def test_undo_is_at_least_a_hundred_deep(app):
    """Rule 2 says at least 100. Add 120 people and walk all the way back."""
    c = app
    me = add(c, "Root", "Person")
    for i in range(120):
        add(c, f"Child{i}", "Person", me, "child")
    assert c.get("meta")["stats"]["people"] == 121
    assert c.get("history")["depth"] >= 100

    for _ in range(120):
        assert c.post("undo")["ok"]
    assert c.get("meta")["stats"]["people"] == 1
    assert c.post("undo")["ok"]                      # the root itself
    assert c.post("undo")["ok"] is False             # and then nothing left


def test_a_new_edit_ends_the_redo_road(app):
    c = app
    me = add(c, "James", "Pargeter")
    add(c, "Michael", "Pargeter", me, "father")
    c.post("undo")
    assert c.get("history")["redo"] is not None
    add(c, "Susan", "Hallam", me, "mother")
    assert c.get("history")["redo"] is None, "redo should not survive a new edit"


def test_vague_dates_are_kept_and_echoed_in_words(app):
    """Rule 5, and the live echo the add dialogue shows while you type."""
    c = app
    assert c.get("date", q="abt 1834")["text"] == "about 1834"
    assert c.get("date", q="bef 1900")["text"] == "before 1900"
    assert c.get("date", q="bet 1820 and 1825")["text"] == \
        "between 1820 and 1825"
    assert c.get("date", q="Q3 1871")["text"] == "the third quarter of 1871"

    # nonsense is kept verbatim rather than rejected
    odd = c.get("date", q="one snowy Tuesday")
    assert odd["known"] is False
    assert "one snowy Tuesday" in odd["text"]
    pid = add(c, "Vague", "Person", birth="one snowy Tuesday")
    assert c.get("person", id=pid)["birth"] == "one snowy Tuesday"


def test_impossible_dates_warn_but_still_save(app):
    """Rule 4. People enter what the record says and fix it later."""
    c = app
    dad = add(c, "Michael", "Pargeter", birth="1962")
    r = c.post("person/new", {"given": "Hannah", "surname": "Pargeter",
                              "birth": "1930",
                              "attach": {"to": dad, "as": "child"}})
    assert r["warnings"], "should have flagged a child born before her father"
    assert "born before" in r["warnings"][0]
    assert c.get("person", id=r["id"])["birth"] == "1930", "saved anyway"


def test_the_duplicate_check_finds_a_near_match(app):
    """Duplicate people are the commonest way a tree goes wrong."""
    c = app
    me = add(c, "James", "Pargeter", birth="1992")
    hits = c.get("person/search", q="James Pargete")
    assert hits and hits[0]["id"] == me
    assert c.get("person/search", q="James Pargeter", exclude=me) == []
    assert c.get("person/search", q="Zebediah Quill") == []


def test_link_to_an_existing_person_makes_no_duplicate(app):
    """What "Did you mean this person?" does instead of a second record."""
    c = app
    me = add(c, "James", "Pargeter")
    sis = add(c, "Claire", "Pargeter")
    assert c.get("meta")["stats"]["people"] == 2
    c.post("person/link", {"id": sis, "attach": {"to": me, "as": "sibling"}})
    assert c.get("meta")["stats"]["people"] == 2, "link must not create anybody"
    assert names(c.get("person", id=me)["siblings"]) == {"Claire Pargeter"}


def test_children_with_no_partner_recorded_get_their_own_group(app):
    """The panel heads that group "with someone not recorded" and offers to
    name the other parent, so it needs a family with a null partner."""
    c = app
    dad = add(c, "Michael", "Pargeter")
    add(c, "James", "Pargeter", dad, "child")
    add(c, "Claire", "Pargeter", dad, "child")
    fams = c.get("person", id=dad)["families"]
    assert len(fams) == 1, "two children, one unnamed partner, one family"
    assert fams[0]["partner"] is None
    assert names(fams[0]["children"]) == {"James Pargeter", "Claire Pargeter"}


def test_detach_keeps_the_person(app):
    c = app
    me = add(c, "James", "Pargeter")
    dad = add(c, "Michael", "Pargeter", me, "father")
    uid = c.get("person", id=me)["families"] or None
    uid = c.get("person", id=dad)["families"][0]["union_id"]
    c.post("person/detach", {"id": me, "union_id": uid, "as": "child"})
    assert c.get("meta")["stats"]["people"] == 2
    assert c.get("person", id=me)["parents"] == []


def test_every_write_is_recorded_in_the_change_log(app, tmp_path):
    c = app
    me = add(c, "James", "Pargeter")
    add(c, "Michael", "Pargeter", me, "father")
    con = connect(tmp_path / "mine.helix", backup_daily=False)
    rows = con.execute("SELECT op,tbl,before,after,label FROM change_log "
                       "ORDER BY id").fetchall()
    assert len(rows) >= 6
    assert {r["tbl"] for r in rows} >= {"person", "person_name",
                                        "union_", "union_partner", "union_child"}
    assert all(r["label"] for r in rows), "every change needs a plain label"
    assert "union" not in " ".join(r["label"] for r in rows).lower(), \
        "the word union must never reach a label the user reads"
    con.close()


def test_a_bad_request_explains_itself(app):
    """Rule 8: every error message says what to do next, no stack traces."""
    c = app
    me = add(c, "James", "Pargeter")
    err = c.post_expecting_failure(
        "person/new", {"given": "X", "attach": {"to": me, "as": "wombat"}})
    assert "wombat" in err["error"] and "father" in err["error"]
    assert "Traceback" not in err["error"]


def test_a_shared_surname_alone_is_not_a_duplicate(app):
    """Offering James when somebody adds his sister Claire invites a wrong
    "link to them instead", which is worse than no suggestion at all."""
    c = app
    james = add(c, "James", "Pargeter", birth="1992")
    add(c, "Arthur", "Pargeter", birth="1935")
    assert [h["id"] for h in c.get("person/search", q="Claire Pargeter")] == []
    # a real near-miss still surfaces
    assert c.get("person/search", q="Jame Pargeter")[0]["id"] == james
    assert c.get("person/search", q="James Pargetter")[0]["id"] == james


def test_the_word_union_never_reaches_the_screen(app):
    """A hard rule from docs/DATA_ENTRY_UI.md. "Union" is the right word for
    the schema and the wrong word for somebody adding their aunt."""
    import re
    from pathlib import Path
    web = Path(__file__).resolve().parents[1] / "helix" / "web"

    visible = re.sub(r"<[^>]+>", " ", (web / "index.html").read_text())
    assert "union" not in visible.lower(), "index.html shows the word to the user"

    # and nothing the API hands back as prose says it either
    c = app
    me = add(c, "James", "Pargeter")
    add(c, "Michael", "Pargeter", me, "father")
    d = c.get("person", id=me)
    prose = " ".join(str(v) for k, v in d.items() if isinstance(v, str))
    assert "union" not in prose.lower()
    assert "union" not in str(c.get("history")).lower()
    assert "union" not in c.post("person/retire", {"id": me})["message"].lower()


# ══════════════════════ married, or not ═══════════════════════════════════
#
# Two people with a child between them are a family whether or not they ever
# married, and a program that only knows how to say "married" tells a small
# lie about them on every screen it has -- including the printed record,
# which is the one document in the house somebody will still be quoting in
# thirty years.
def test_a_couple_who_never_married_are_not_called_married(app):
    c = app
    her = add(c, "Heather", "Whitcombe", birth="1988", sex="F")
    c.post("subject", {"id": her})
    add(c, "Dean", "Pargeter", her, "partner", birth="1986", sex="M")
    fam = c.get("person", id=her)["families"]
    assert fam and fam[0]["married"] is True, "adding a partner means married"

    r = c.post("union", {"action": "set_kind", "union_id": fam[0]["union_id"],
                         "kind": "unmarried"})
    assert r["ok"]
    f = c.get("person", id=her)["families"][0]
    assert f["kind"] == "unmarried"
    assert f["married"] is False
    assert "married" not in f["word"]

    # and it goes back, like every other edit
    c.post("undo", {})
    assert c.get("person", id=her)["families"][0]["married"] is True


def test_a_kind_of_couple_helix_does_not_know_says_what_to_use(app):
    """Rule eight: every error says what to do next."""
    c = app
    a = add(c, "Heather", "Whitcombe", sex="F")
    add(c, "Dean", "Pargeter", a, "partner", sex="M")
    u = c.get("person", id=a)["families"][0]["union_id"]
    with pytest.raises(AssertionError) as e:
        c.post("union", {"action": "set_kind", "union_id": u, "kind": "engaged"})
    assert "unmarried" in str(e.value), "it must list the ones that do work"


def test_divorce_is_not_a_kind_of_couple(app):
    """A couple who married and divorced WERE married: the marriage is a
    fact with a date on it and it stays on the record. That is why the list
    of kinds has no entry for it."""
    kinds = {k["key"] for k in app.get("meta")["union_kinds"]}
    assert "unmarried" in kinds and "marriage" in kinds
    assert not any("divor" in k for k in kinds)


# ══════════════════════ everything added can be taken off ═════════════════
#
# Anything a person can add, they can take off again, and undo puts it back.
# Taking somebody OUT OF A FAMILY is not deleting them -- they stay in the
# file with everything known about them -- which is a distinction the panel
# has to make in words as well as in code.
def test_a_parent_hung_on_the_wrong_person_comes_off(app):
    c = app
    me = add(c, "James", "Whitcombe", birth="1990", sex="M")
    c.post("subject", {"id": me})
    dad = add(c, "Peter", "Whitcombe", me, "father", birth="1960", sex="M")
    add(c, "Susan", "Pargeter", me, "mother", birth="1962", sex="F")

    rows = c.get("person", id=me)["parents"]
    assert all(p["union_id"] for p in rows), "the panel needs the family to undo"
    u = next(p["union_id"] for p in rows if p["id"] == dad)

    c.post("union", {"action": "remove_partner", "union_id": u,
                     "person_id": dad})
    assert names(c.get("person", id=me)["parents"]) == {"Susan Pargeter"}
    # ...and Peter is still in the file, with everything known about him
    assert c.get("person", id=dad)["birth"] == "1960"
    c.post("undo", {})
    assert len(c.get("person", id=me)["parents"]) == 2


def test_a_child_in_the_wrong_family_comes_off(app):
    c = app
    me = add(c, "James", "Whitcombe", sex="M")
    c.post("subject", {"id": me})
    add(c, "Erica", "Vale", me, "partner", sex="F")
    kid = add(c, "Rosie", "Whitcombe", me, "child", birth="2015")
    fam = [f for f in c.get("person", id=me)["families"] if f["children"]][0]

    c.post("union/child", {"action": "detach", "union_id": fam["union_id"],
                           "person_id": kid})
    assert not any(f["children"] for f in c.get("person", id=me)["families"])
    assert c.get("person", id=kid)["birth"] == "2015", "still in the file"
    c.post("undo", {})
    assert any(f["children"] for f in c.get("person", id=me)["families"])


# ══════════════════════ a face over a lifetime ════════════════════════════
def test_the_new_photograph_becomes_the_one_shown_and_the_old_one_stays(app):
    """Somebody at twenty and the same person at eighty are two photographs
    of one person. Replacing the first with the second throws away half of
    what a family album is for."""
    import base64
    import struct
    import zlib

    def png(shade):
        def chunk(tag, data):
            c = tag + data
            return (struct.pack(">I", len(data)) + c
                    + struct.pack(">I", zlib.crc32(c)))
        return (b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 1, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(b"\x00" + bytes([shade]) * 6))
                + chunk(b"IEND", b""))

    c = app
    me = add(c, "Harriet", "Whitcombe", birth="1952", sex="F")
    ids = []
    for i, shade in enumerate((10, 120, 240)):
        url = "data:image/png;base64," + base64.b64encode(png(shade)).decode()
        ids.append(c.post("person/photo", {"id": me, "data": url,
                                           "filename": f"p{i}.png"})["media_id"])

    photos = c.get("person", id=me)["photos"]
    assert sum(1 for p in photos if p["portrait"]) == 1, "one at a time"
    assert len(photos) == 3, "the earlier ones are kept, not replaced"

    # WHEN, in any of the three forms a family actually has it.
    c.post("person/photo/taken", {"media_id": ids[0], "taken": "1972"})
    c.post("person/photo/taken", {"media_id": ids[1], "taken": "aged 12"})
    c.post("person/photo/taken", {"media_id": ids[2],
                                  "taken": "the summer before Kenya"})
    by_id = {p["media_id"]: p for p in c.get("person", id=me)["photos"]}
    assert by_id[ids[0]]["age"] == 20, "a year gives the age"
    assert by_id[ids[1]]["year"] == 1964, "an age gives the year"
    assert by_id[ids[2]]["when"] == "the summer before Kenya", \
        "and anything else is kept exactly as it was typed"

    # showing an older one demotes the newer, and undo swaps them back
    c.post("person/photo/portrait", {"id": me, "media_id": ids[0]})
    shown = [p for p in c.get("person", id=me)["photos"] if p["portrait"]]
    assert len(shown) == 1 and shown[0]["media_id"] == ids[0]
    c.post("undo", {})
    shown = [p for p in c.get("person", id=me)["photos"] if p["portrait"]]
    assert shown[0]["media_id"] == ids[2]


# ══════════════════════ the record book ═══════════════════════════════════
#
# The thing that goes in a ring binder and is read by somebody in thirty
# years who never met anybody in it.
def _book(app, **kw):
    import urllib.request
    q = "&".join(f"{k}={v}" for k, v in kw.items())
    with urllib.request.urlopen(f"{app.base}/print/records"
                                + (f"?{q}" if q else "")) as r:
        return r.read().decode()


def test_the_record_book_says_what_is_not_known(app):
    """A BLANK ON A FILED RECORD IS AMBIGUOUS FOREVER. Nobody can tell an
    unknown birthplace from one somebody got bored before filling in, and
    "Unknown" is also the only thing that says where the work still is."""
    c = app
    me = add(c, "Elias", "Whitcombe", birth="1928", sex="M")
    c.post("subject", {"id": me})
    html = _book(c)
    assert "Born in" in html and "Unknown" in html
    for field in ("Born", "Born in", "Died", "Died in", "Age",
                  "Occupation", "Education", "Father", "Mother"):
        assert f"<dt>{field}</dt>" in html, f"{field} is not on the record"


def test_the_record_book_carries_the_notes_and_the_facts(app):
    c = app
    me = add(c, "Elias", "Whitcombe", birth="1928", death="2009", sex="M")
    c.post("subject", {"id": me})
    c.post("person", {"id": me, "occupation": "Foundry pattern maker",
                      "education": "Left school at 14",
                      "birth_place": "Frome, Somerset",
                      "notes": "Everyone called him Tick."})
    wife = add(c, "Ada", "Boyce", me, "partner", birth="1931", sex="F")
    add(c, "Robert", "Whitcombe", me, "child", birth="1958", sex="M")
    html = _book(c)
    for want in ("Foundry pattern maker", "Left school at 14",
                 "Frome, Somerset", "Everyone called him Tick.",
                 "Ada Boyce", "Robert Whitcombe"):
        assert want in html, f"the record book left out {want!r}"


def test_the_record_book_has_no_bracketed_numbers_beside_names(app):
    """They were there so the binder could be followed without the program
    that made it, and they made every page read like a database dump.
    "Reuben Ashworth [2], Winifred Threlfall [3]" is not how anybody writes
    about their family."""
    import re
    c = app
    me = add(c, "Elias", "Whitcombe", birth="1928", sex="M")
    c.post("subject", {"id": me})
    add(c, "Ada", "Boyce", me, "partner", birth="1931", sex="F")
    add(c, "Robert", "Whitcombe", me, "child", birth="1958", sex="M")
    assert not re.search(r"\[\d+\]", _book(c))


def test_every_record_starts_its_own_page(app):
    """A binder is filed, added to and pulled apart: somebody wants the page
    for their grandmother, and if two other people are on the back of it
    they cannot have it. The FIRST one included -- it used to run on from
    the bottom of the contents."""
    c = app
    me = add(c, "Elias", "Whitcombe", birth="1928", sex="M")
    c.post("subject", {"id": me})
    add(c, "Ada", "Boyce", me, "partner", birth="1931", sex="F")
    html = _book(c)
    entries = html.count("<article class=entry>")
    assert entries == 2
    # the rule is on `.entry` itself, with no exception for the first
    assert "page-break-before:always" in html
    assert ".entry:first-of-type{page-break-before:auto" not in html


def test_the_record_book_is_ordered_oldest_first_not_from_the_root(app):
    """That order is right for a sidebar, where the question is "where is my
    sister", and wrong for a folder that outlives the person who made it."""
    c = app
    me = add(c, "James", "Whitcombe", birth="1990", sex="M")
    c.post("subject", {"id": me})
    dad = add(c, "Peter", "Whitcombe", me, "father", birth="1960", sex="M")
    add(c, "Elias", "Whitcombe", dad, "father", birth="1928", sex="M")
    html = _book(c)
    order = [html.index(f"</span> {n}</h2>") for n in
             ("Elias Whitcombe", "Peter Whitcombe", "James Whitcombe")]
    assert order == sorted(order), \
        "the record must read from the oldest known person downwards"


def test_the_record_book_never_says_your_uncle(app):
    """Every relation in the program is measured from one person, and in
    thirty years nobody reading this folder is that person."""
    c = app
    me = add(c, "James", "Whitcombe", birth="1990", sex="M")
    c.post("subject", {"id": me})
    dad = add(c, "Peter", "Whitcombe", me, "father", birth="1960", sex="M")
    add(c, "Robert", "Whitcombe", dad, "sibling", birth="1958", sex="M")
    html = _book(c)
    assert "your uncle" not in html and "your father" not in html
    assert "<dt>Father</dt>" in html, "it states the relation outright instead"


def test_a_record_with_no_photograph_says_so(app):
    c = app
    me = add(c, "Elias", "Whitcombe", birth="1928", sex="M")
    c.post("subject", {"id": me})
    assert "No photograph" in _book(c)


# ══════════════════ the same family, as somebody else's tree ══════════════
def _whitcombes(c):
    """A family with a whole in-law family hanging off one marriage."""
    me = add(c, "James", "Whitcombe", birth="1990", sex="M")
    c.post("subject", {"id": me})
    dad = add(c, "Peter", "Whitcombe", me, "father", birth="1960", sex="M")
    sis = add(c, "Alice", "Whitcombe", me, "sibling", birth="1993", sex="F")
    unc = add(c, "Robert", "Whitcombe", dad, "sibling", birth="1958", sex="M")
    mich = add(c, "Michaela", "Denton", unc, "partner", birth="1959", sex="F")
    add(c, "Gordon", "Denton", mich, "father", birth="1930", sex="M")
    add(c, "Ivy", "Marsh", mich, "mother", birth="1932", sex="F")
    add(c, "Colin", "Denton", mich, "sibling", birth="1962", sex="M")
    return {"me": me, "sis": sis, "unc": unc, "mich": mich}


def _rows(path, sql):
    import sqlite3
    con = sqlite3.connect(path)
    try:
        return con.execute(sql).fetchone()[0]
    finally:
        con.close()


def test_a_pruned_branch_is_gone_from_the_copy_not_hidden_in_it(app):
    """Rule seven says never SQL-DELETE a person, and its reason is that a
    wrong ancestor removed at midnight has to still be there in the morning.
    That reason does not reach here: the ORIGINAL is untouched and holds
    every one of them. A new document carrying hidden rows for a family it
    was deliberately not about is the same file with a flag set -- it would
    export them, count them, and offer them back on the first Ctrl-Z."""
    c = app
    ids = _whitcombes(c)
    r = c.post("library/copy-for", {"id": ids["sis"], "prune": True,
                                    "title": "Alice's family"})
    assert r["removed"] == 3, "Michaela's own parents and brother"
    path = r["path"]
    assert _rows(path, "SELECT COUNT(*) FROM person") == 5, \
        "the rows are deleted, not marked inactive"
    assert _rows(path, "SELECT COUNT(*) FROM person_name "
                       "WHERE surname='Marsh'") == 0
    # no family left with nobody in it, and no orphaned events
    assert _rows(path, "SELECT COUNT(*) FROM union_ WHERE id NOT IN "
                       "(SELECT union_id FROM union_partner) AND id NOT IN "
                       "(SELECT union_id FROM union_child)") == 0
    assert _rows(path, "SELECT COUNT(*) FROM event WHERE id NOT IN "
                       "(SELECT event_id FROM event_role "
                       "WHERE event_id IS NOT NULL)") == 0


def test_the_copy_does_not_touch_the_original(app, tmp_path):
    c = app
    ids = _whitcombes(c)
    before = c.get("meta")
    c.post("library/copy-for", {"id": ids["sis"], "prune": True,
                                "title": "Alice's family"})
    after = c.get("meta")
    assert after["stats"]["people"] == before["stats"]["people"] == 8
    assert after["subject"] == ids["me"], "and it is still your tree"
    assert {p["name"] for p in after["people"]} == \
           {p["name"] for p in before["people"]}


def test_the_copy_starts_with_no_history_of_its_own(app):
    """Without this the first Ctrl-Z in Alice's file undoes something her
    uncle did in his -- and the pruning would be the first thing offered
    back."""
    c = app
    ids = _whitcombes(c)
    r = c.post("library/copy-for", {"id": ids["sis"], "prune": True,
                                    "title": "Alice's family"})
    assert _rows(r["path"], "SELECT COUNT(*) FROM change_log") == 0


def test_the_person_who_married_in_stays(app):
    """Michaela married Alice's uncle: she is at every family gathering.
    What goes is her OWN family, who are no relation to Alice at all."""
    c = app
    ids = _whitcombes(c)
    r = c.post("library/copy-for", {"id": ids["sis"], "prune": True})
    assert _rows(r["path"], "SELECT COUNT(*) FROM person_name "
                            "WHERE given='Michaela'") == 1
    assert _rows(r["path"], "SELECT COUNT(*) FROM person_name "
                            "WHERE given='Colin'") == 0


def test_nothing_is_left_out_unless_it_is_asked_for(app):
    c = app
    ids = _whitcombes(c)
    r = c.post("library/copy-for", {"id": ids["sis"], "title": "All of them"})
    assert r["removed"] == 0
    assert _rows(r["path"], "SELECT COUNT(*) FROM person") == 8


# ══════════════════════ a whole date, not only a year ═════════════════════
#
# Somebody copying off a birth certificate types what is printed on it, and
# what is printed on it is "Friday, 1st March 1900" -- not "1900-03-01".
# Refused, they shrug and type the year, and a day and a month somebody had
# in front of them are lost for good.
@pytest.mark.parametrize("typed,shown", [
    ("12 March 1841", "12 Mar 1841"),
    ("1st March 1900", "1 Mar 1900"),
    ("22nd Jan 1888", "22 Jan 1888"),
    ("12th of March 1880", "12 Mar 1880"),
    ("Friday 12 March 1880", "12 Mar 1880"),
    ("March 12, 1880", "12 Mar 1880"),
    ("Sep 12 1880", "12 Sep 1880"),
    ("12/03/1841", "12 Mar 1841"),
    ("2014-03-12", "12 Mar 2014"),
    ("c. 1834", "abt 1834"),
    ("24 Feb 1723/24", "24 Feb 1723/24"),
    ("1841", "1841"),                     # and a bare year still means a year
    ("Mar 1841", "Mar 1841"),
])
def test_a_whole_date_can_be_typed_the_way_it_is_written(app, typed, shown):
    c = app
    pid = add(c, "Harriet", "Whitcombe", birth=typed)
    assert c.get("person", id=pid)["birth"] == shown
    # and the echo under the box agrees before it is saved
    assert c.get("date", q=typed)["text"]


def test_a_full_date_survives_being_saved_from_the_profile(app):
    c = app
    pid = add(c, "Harriet", "Whitcombe", birth="1841")
    c.post("person", {"id": pid, "birth": "12 March 1841",
                      "death": "3 Feb 1900"})
    d = c.get("person", id=pid)
    assert (d["birth"], d["death"]) == ("12 Mar 1841", "3 Feb 1900")
    assert d["age"] == "58", f"and the age is worked out to the day: {d['age']}"


def test_a_date_helix_cannot_read_is_still_kept(app):
    """Rule five. Unparseable is stored with the original string intact."""
    c = app
    pid = add(c, "Harriet", "Whitcombe", birth="the spring after the flood")
    assert c.get("person", id=pid)["birth"] == "the spring after the flood"
