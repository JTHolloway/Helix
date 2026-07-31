"""The door in and the door out.

Blocker 3. GEDCOM is the only format every genealogy program reads, so this
is what stops a decade of somebody's research being trapped in one SQLite
file — and what lets a cousin's tree arrive without being retyped.

THE TEST THAT MATTERS MOST IS THE ROUND TRIP. Export a real family, import
it into an empty file, and compare the two as multisets: every name, sex,
date, place, occupation and family. A writer and a reader that agree with
each other but not with the data would pass every smaller test here.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from helix.graph.build import load
from helix.io import gedcom
from helix.io.csv_import import guess_mapping, import_csv
from helix.io.gedcom import lexer
from helix.model.gendate import parse as parse_date
from helix.store.db import connect, set_setting

from test_records import Client, add                      # noqa: F401


# --------------------------------------------------------------- fixtures --
@pytest.fixture
def family(tmp_path):
    """A small real family, built the way a person builds one."""
    import threading

    from helix.server import make_server
    db = tmp_path / "f.helix"
    con = connect(db)
    set_setting(con, "project_title", "Export test")
    con.close()
    srv = make_server(str(db), port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    c = Client(f"http://127.0.0.1:{srv.server_port}")
    try:
        me = add(c, "James", "Holloway", birth="29 Apr 2003", sex="M")
        c.post("subject", {"id": me})
        dad = add(c, "David", "Holloway", me, "father", birth="1967", sex="M")
        mum = add(c, "Michaela", "Reed", me, "mother", birth="abt 1969", sex="F")
        add(c, "Anthony", "Holloway", me, "sibling", birth="1993", sex="M")
        gran = add(c, "Peter", "Holloway", dad, "father",
                   birth="8 Feb 1924", sex="M")
        add(c, "Kathleen", "Holloway", dad, "mother", birth="1928", sex="F")
        c.post("person", {"id": gran, "birth_place": "Walcot, Bath, Somerset",
                          "occupation": "Stonemason", "death": "2017",
                          "notes": "Always said his mother came from Cork."})
        c.post("person/heritage", {"id": gran,
                                   "heritage": [{"label": "Irish"}]})
        add(c, "Sarah", "Holloway", dad, "sibling", birth="1965", sex="F")
        yield c, {"me": me, "dad": dad, "mum": mum, "gran": gran}, db
    finally:
        srv.shutdown()
        srv.server_close()


def signature(g):
    """Every person as a tuple of everything worth keeping.

    A MULTISET AND NOT A DICT KEYED BY NAME. Four hundred people include two
    Albert Ashworths, and comparing by name matched one against the other
    and reported ten differences in a round trip that was in fact exact.
    """
    return Counter(
        (p.full_name, p.sex, p.birth.display, p.death.display, p.birth_place,
         p.death_place, p.occupation, p.education, (p.notes or "").strip())
        for p in g.people.values())


def families(g):
    return Counter(
        (tuple(sorted(g.people[x].full_name for x in u.partners if x in g.people)),
         tuple(sorted(g.people[x].full_name for x in u.children if x in g.people)))
        for u in g.unions.values())


# ------------------------------------------------------------ the round trip
def test_a_family_survives_a_trip_out_and_back(family, tmp_path):
    c, ids, db = family
    con = connect(db, create=False)
    out = tmp_path / "out.ged"
    rep = gedcom.export_file(con, out, title="Export test")
    assert rep["people"] == 7

    back = connect(tmp_path / "back.helix")
    got = gedcom.import_file(out, back)
    assert got["people"] == 7
    assert not got["problems"]

    a, b = load(connect(db, create=False)), load(back)
    assert signature(a) == signature(b)
    assert families(a) == families(b)


def test_the_big_file_survives_it_too(tmp_path):
    """Eight people prove the shape; four hundred prove it scales and that
    nothing is quietly dropped in the middle of a long file."""
    src = Path("big400.helix")
    if not src.exists():
        pytest.skip("big400.helix is not in this checkout")
    out = tmp_path / "big.ged"
    gedcom.export_file(connect(src, create=False), out)
    back = connect(tmp_path / "big.helix")
    rep = gedcom.import_file(out, back)
    a, b = load(connect(src, create=False)), load(back)
    assert len(b.people) == len(a.people) == rep["people"]
    assert signature(a) == signature(b)
    assert families(a) == families(b)


def test_exporting_twice_gives_the_same_file(family, tmp_path):
    """Deterministic xrefs. A diff between two exports should mean the data
    changed, not that the UUIDs came out of SQLite in a different order."""
    c, ids, db = family
    con = connect(db, create=False)
    a, b = tmp_path / "a.ged", tmp_path / "b.ged"
    gedcom.export_file(con, a)
    gedcom.export_file(con, b)
    # The header carries the moment it was written and the name it was
    # written under; everything below it must match line for line.
    strip = lambda p: [x for x in p.read_text().splitlines()   # noqa: E731
                       if not x.startswith(("1 DATE", "2 TIME", "1 FILE"))]
    assert strip(a) == strip(b)


# ------------------------------------------------------------- what it writes
def test_the_file_is_shaped_like_gedcom(family, tmp_path):
    c, ids, db = family
    out = tmp_path / "o.ged"
    gedcom.export_file(connect(db, create=False), out, title="Export test")
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "0 HEAD"
    assert lines[-1] == "0 TRLR"
    assert "1 CHAR UTF-8" in lines
    assert "2 VERS 5.5.1" in lines
    assert any(x.startswith("0 @I1@ INDI") for x in lines)
    assert any(x.startswith("0 @F1@ FAM") for x in lines)
    # `John /Smith/` -- the slashes ARE the surname
    assert "1 NAME James /Holloway/" in lines
    assert all(len(x) <= 255 for x in lines), "a line went over the 255 limit"
    assert all(x[0].isdigit() for x in lines if x)


def test_no_line_ever_goes_over_the_limit(tmp_path):
    """A long note is the case that breaks it, and a file with one 4000-
    character line fails to open in exactly the products people want."""
    db = tmp_path / "long.helix"
    con = connect(db)
    from helix.store.records import add_person, update_person
    pid = add_person(con, {"given": "Verbose", "surname": "Person"})["id"]
    note = ("A long sentence. " * 400).strip()
    update_person(con, {"id": pid, "notes": note})
    out = tmp_path / "long.ged"
    gedcom.export_file(con, out)
    lines = out.read_text().splitlines()
    assert max(len(x) for x in lines) <= 255
    assert any(x.startswith("2 CONC") for x in lines)
    back = connect(tmp_path / "b.helix")
    gedcom.import_file(out, back)
    g = load(back)
    p = next(iter(g.people.values()))
    # A note is stripped of its surrounding whitespace on the way in --
    # GEDCOM files from fixed-width exporters are full of trailing spaces
    # and importing them verbatim puts invisible junk in every note. What
    # must survive exactly is everything BETWEEN the ends.
    assert p.notes == note, "CONC lost or added a character"


def test_a_note_with_newlines_comes_back_with_them(tmp_path):
    """CONT is a newline and CONC is a join with no space. Swapped, a
    two-line note comes back as one line and a long name gains a space in
    the middle of it."""
    db = tmp_path / "n.helix"
    con = connect(db)
    from helix.store.records import add_person, update_person
    pid = add_person(con, {"given": "Multi", "surname": "Line"})["id"]
    update_person(con, {"id": pid, "notes": "First line.\nSecond line.\n\nFourth."})
    out = tmp_path / "n.ged"
    gedcom.export_file(con, out)
    back = connect(tmp_path / "nb.helix")
    gedcom.import_file(out, back)
    g = load(back)
    assert next(iter(g.people.values())).notes == \
        "First line.\nSecond line.\n\nFourth."


def test_a_vague_date_stays_vague(family, tmp_path):
    """Rule 2 with a wire format on the end of it. "about 1969" is stored
    as an interval and must go out as ABT 1969 -- not as 1969, which throws
    the doubt away, and not as BET 1966 AND 1972, which invents a precision
    nobody claimed."""
    c, ids, db = family
    out = tmp_path / "d.ged"
    gedcom.export_file(connect(db, create=False), out)
    text = out.read_text()
    assert "2 DATE ABT 1969" in text
    assert "2 DATE 8 FEB 1924" in text
    back = connect(tmp_path / "d.helix")
    gedcom.import_file(out, back)
    g = load(back)
    mum = next(p for p in g.people.values() if p.full_name == "Michaela Reed")
    assert mum.birth.display == "abt 1969"
    assert mum.birth.kind == "about"


def test_helix_extras_come_back_as_rows_not_notes(family, tmp_path):
    """Heritage has no word in GEDCOM. Written into a `_` tag, a foreign
    reader keeps it as a note -- which is the point of the underscore
    convention -- and Helix's own reader turns it back into a row."""
    c, ids, db = family
    out = tmp_path / "h.ged"
    gedcom.export_file(connect(db, create=False), out)
    assert "1 _HERITAGE Irish" in out.read_text()
    back = connect(tmp_path / "h.helix")
    gedcom.import_file(out, back)
    g = load(back)
    gran = next(p for p in g.people.values() if p.full_name == "Peter Holloway")
    assert gran.heritage == {"Irish": 1.0}


# --------------------------------------------------------- hostile input --
NASTY = """0 HEAD
1 SOUR Family Tree Maker
1 CHAR ANSEL
0 @I1@ INDI
1 NAME John /Smith/ Jr
1 SEX M
1 BIRT
2 DATE @#DJULIAN@ 12 MAR 1710
2 PLAC Walcot, Bath
1 OCCU Journeyman carpenter
1 RESI
2 DATE FROM 1841 TO 1851
1 FAMS @F1@
1 FAMC @F2@
0 @I2@ INDI
1 NAME Mary Anne /de la Mare/
1 SEX F
1 FAMS @F1@
0 @I3@ INDI
1 SEX U
1 FAMC @F1@
0 @I4@ INDI
1 NAME Cyclic /Ancestor/
1 FAMC @F1@
1 FAMS @F2@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
1 CHIL @I3@
1 CHIL @I4@
1 CHIL @I99@
1 MARR
2 DATE BET 1735 AND 1740
0 @F2@ FAM
1 CHIL @I1@
1 HUSB @I4@
0 @F3@ FAM
1 WIFE @I2@
0 TRLR
"""


@pytest.fixture
def nasty(tmp_path):
    p = tmp_path / "nasty.ged"
    p.write_bytes(NASTY.encode("latin-1"))
    return p


def test_a_hostile_file_imports_rather_than_failing(nasty, tmp_path):
    """Every one of these is ordinary in a real file and none of them is a
    reason to refuse somebody's family: a person with no name, a child
    listed twice, a pointer at nobody, a family with no husband."""
    con = connect(tmp_path / "x.helix")
    rep = gedcom.import_file(nasty, con)
    assert rep["people"] == 4
    assert rep["families"] == 3
    g = load(con)
    f1 = next(u for u in g.unions.values() if len(u.partners) == 2)
    assert len(f1.children) == 2, "a child listed twice was imported twice"
    assert any("@I99@" in w for w in rep["warnings"])
    assert any(p.full_name == "[Unknown]" for p in g.people.values())


def test_a_cyclic_pedigree_is_reported_and_does_not_hang(nasty, tmp_path):
    """Somebody who is their own great-grandfather. Nothing in the program
    expects it, and a naive walk follows it forever."""
    con = connect(tmp_path / "c.helix")
    rep = gedcom.import_file(nasty, con)
    assert any("own ancestor" in p for p in rep["problems"])
    # and the graph still answers questions rather than looping
    g = load(con)
    for pid in g.people:
        assert len(g.ancestors(pid)) < 50


def test_ansel_accents_come_out_as_letters(tmp_path):
    """Combining marks come BEFORE their letter in ANSEL and after it in
    Unicode. Read the naive way, "José" arrives as "Jos´e" and every
    accented name in the file is quietly wrong."""
    raw = b"0 HEAD\n1 CHAR ANSEL\n0 @I1@ INDI\n1 NAME Jos\xe2e /Garc\xe2ia/\n0 TRLR\n"
    p = tmp_path / "a.ged"
    p.write_bytes(raw)
    con = connect(tmp_path / "a.helix")
    rep = gedcom.import_file(p, con)
    assert rep["encoding"] == "ansel"
    g = load(con)
    assert next(iter(g.people.values())).full_name == "José García"


def test_an_ansi_header_means_windows_1252(tmp_path):
    """`1 CHAR ANSI` in a GEDCOM header has always meant Windows-1252 and
    never the ANSI standard. Read as ANSEL it mangles every file that says
    ANSI and means CP1252, which is most of them."""
    raw = "0 HEAD\n1 CHAR ANSI\n0 @I1@ INDI\n1 NAME Ren\xe9e /Fran\xe7ois/\n0 TRLR\n"
    p = tmp_path / "b.ged"
    p.write_bytes(raw.encode("cp1252"))
    con = connect(tmp_path / "b.helix")
    rep = gedcom.import_file(p, con)
    assert rep["encoding"] == "cp1252"
    g = load(con)
    assert next(iter(g.people.values())).full_name == "Renée François"


def test_a_name_with_no_slashes_still_finds_a_surname(tmp_path):
    """Web exporters write `John Smith` with no slashes at all. The last
    word is the best guess available, and the whole string is kept."""
    p = tmp_path / "s.ged"
    p.write_text("0 HEAD\n0 @I1@ INDI\n1 NAME John Smith\n0 TRLR\n")
    con = connect(tmp_path / "s.helix")
    gedcom.import_file(p, con)
    g = load(con)
    q = next(iter(g.people.values()))
    assert (q.given, q.surname) == ("John", "Smith")


def test_a_malformed_line_is_reported_not_fatal(tmp_path):
    p = tmp_path / "m.ged"
    p.write_text("0 HEAD\nthis is not a gedcom line\n0 @I1@ INDI\n"
                 "1 NAME A /B/\n0 TRLR\n")
    con = connect(tmp_path / "m.helix")
    rep = gedcom.import_file(p, con)
    assert rep["people"] == 1
    assert any("not a GEDCOM line" in x for x in rep["problems"])


def test_an_import_is_one_undoable_step(nasty, tmp_path):
    """The single largest change anybody will ever make to their file, and
    it has to be as takeable-back as adding one cousin."""
    from helix.store import records
    con = connect(tmp_path / "u.helix")
    before = con.execute("SELECT COUNT(*) FROM person").fetchone()[0]
    gedcom.import_file(nasty, con)
    assert con.execute("SELECT COUNT(*) FROM person "
                       "WHERE COALESCE(active,1)=1").fetchone()[0] > before
    records.undo(con)
    assert con.execute("SELECT COUNT(*) FROM person "
                       "WHERE COALESCE(active,1)=1").fetchone()[0] == before
    # rule 7: never SQL-DELETE a person, even undoing an import
    assert con.execute("SELECT COUNT(*) FROM person").fetchone()[0] > before


def test_an_unknown_tag_is_kept_in_the_notes(tmp_path):
    """The rule from BLOCKERS.md, and the difference between an import and
    a lossy transcription."""
    p = tmp_path / "t.ged"
    p.write_text("0 HEAD\n0 @I1@ INDI\n1 NAME A /B/\n"
                 "1 _DNA 23andMe kit 4471\n2 _KIT V4\n0 TRLR\n")
    con = connect(tmp_path / "t.helix")
    rep = gedcom.import_file(p, con)
    assert rep["notes_kept"] == 1
    g = load(con)
    notes = next(iter(g.people.values())).notes
    assert "[GEDCOM]" in notes and "23andMe kit 4471" in notes and "V4" in notes


# ----------------------------------------------------------------- the lexer
def test_conc_joins_with_no_space_and_cont_with_a_newline():
    roots, problems = lexer.scan(
        "0 @I1@ INDI\n1 NOTE Hello\n2 CONC  world\n2 CONT next line\n")
    assert not problems
    assert roots[0].val("NOTE") == "Hello world\nnext line"


def test_a_level_that_jumps_is_attached_rather_than_dropped():
    roots, problems = lexer.scan("0 @I1@ INDI\n2 NAME A /B/\n")
    assert roots[0].first("NAME") is not None


# ------------------------------------------------------------ the spreadsheet
CSV = """Ref,First name,Last name,Gender,DOB,Born in,Died,Trade,Father,Mother,Spouse,Married,Comments,Hair
1,Thomas,Whitcombe,M,abt 1801,"Walcot, Bath",1867,Carpenter,,,2,1824,Bapt. 1801,brown
2,Sarah,Pearce,F,1803,"Bathwick, Bath",1880,,,,,,,fair
3,William,Whitcombe,M,12 Mar 1826,"Walcot, Bath",1891,Stonemason,1,2,,,,dark
4,Ann,Whitcombe,F,1828,"Walcot, Bath",,Servant,1,2,,,,
5,Eliza,Marlow,F,1829,Trowbridge,1902,Dressmaker,9,,,,From Wiltshire,
"""


@pytest.fixture
def sheet(tmp_path):
    p = tmp_path / "family.csv"
    p.write_text(CSV)
    return p


def test_the_columns_are_guessed_from_what_people_actually_write(sheet):
    m = guess_mapping(["Ref", "First name", "Last name", "Gender", "DOB",
                       "Born in", "Died", "Trade", "Father", "Hair"])
    assert m["First name"] == "given" and m["Last name"] == "surname"
    assert m["DOB"] == "birth_date" and m["Trade"] == "occupation"
    assert "Hair" not in m


def test_a_dry_run_writes_nothing_and_says_what_it_found(sheet):
    r = import_csv(sheet, None, dry_run=True)
    assert r["dry_run"] and r["rows"] == 5 and r["people"] == 5
    assert r["placeholders"] == 1            # father 9 is referenced, never listed
    assert r["unmapped"] == ["Hair"]


def test_a_spreadsheet_imports_with_its_families(sheet, tmp_path):
    con = connect(tmp_path / "csv.helix")
    r = import_csv(sheet, con, dry_run=False)
    assert r["people"] == 5 and r["families"] >= 2
    g = load(con)
    will = next(p for p in g.people.values() if p.full_name == "William Whitcombe")
    parents = sorted(g.people[x].full_name for x in g.parents(will.id, False))
    assert parents == ["Sarah Pearce", "Thomas Whitcombe"]
    assert will.occupation == "Stonemason"
    assert will.birth.display == "12 Mar 1826"
    # a column with nowhere to go is kept, not dropped
    assert "[CSV] Hair: dark" in (will.notes or "")


def test_a_parent_who_is_never_listed_becomes_somebody_to_fill_in(sheet, tmp_path):
    """Half a spreadsheet is still worth importing, and the placeholder is
    visible in every list as somebody to go and find."""
    con = connect(tmp_path / "p.helix")
    import_csv(sheet, con, dry_run=False)
    g = load(con)
    eliza = next(p for p in g.people.values() if p.full_name == "Eliza Marlow")
    dad = g.parents(eliza.id, False)
    assert len(dad) == 1
    assert g.people[dad[0]].is_placeholder


def test_a_vague_spreadsheet_date_survives(sheet, tmp_path):
    con = connect(tmp_path / "v.helix")
    import_csv(sheet, con, dry_run=False)
    g = load(con)
    tom = next(p for p in g.people.values() if p.full_name == "Thomas Whitcombe")
    assert tom.birth.kind == "about" and tom.birth.display == "abt 1801"


# ------------------------------------------------------------------ the date
@pytest.mark.parametrize("text,want", [
    ("12 Mar 1841", "12 MAR 1841"),
    ("Mar 1841", "MAR 1841"),
    ("1841", "1841"),
    ("abt 1834", "ABT 1834"),
    ("bef 1900", "BEF 1900"),
    ("aft 1750", "AFT 1750"),
    ("between 1841 and 1845", "BET 1841 AND 1845"),
    ("est 1700", "EST 1700"),
])
def test_every_kind_of_date_has_a_gedcom_spelling(text, want):
    assert gedcom.gedcom_date(parse_date(text)) == want


def test_an_unparseable_date_goes_out_as_a_phrase_and_comes_back(tmp_path):
    """Rule 5: never destroy what the user typed, and that has to hold
    through an export as well as through a save."""
    d = parse_date("the summer his brother came home")
    assert gedcom.gedcom_date(d) == "(the summer his brother came home)"
    con = connect(tmp_path / "ph.helix")
    from helix.store.records import add_person
    add_person(con, {"given": "Vague", "surname": "Date",
                     "birth": "the summer his brother came home"})
    out = tmp_path / "ph.ged"
    gedcom.export_file(con, out)
    back = connect(tmp_path / "ph2.helix")
    gedcom.import_file(out, back)
    g = load(back)
    p = next(iter(g.people.values()))
    assert p.birth.original == "the summer his brother came home"


# ------------------------------------------------------------- over the wire
def test_import_and_export_work_in_the_app(family, tmp_path):
    """Against a running server, for the reason in `test_records.py`: every
    database-backed endpoint in this program once failed because a SQLite
    connection made on the main thread cannot be used from a request one."""
    import base64
    import urllib.request

    c, ids, db = family
    with urllib.request.urlopen(f"{c.base}/api/gedcom") as r:
        text = r.read().decode()
        assert r.headers["Content-Disposition"].endswith('.ged"')
    assert text.startswith("0 HEAD") and text.rstrip().endswith("0 TRLR")

    data = "data:text/plain;base64," + base64.b64encode(
        NASTY.encode("latin-1")).decode()
    dry = c.post("import", {"filename": "cousin.ged", "data": data,
                            "dry_run": True})
    assert dry["people"] == 4 and dry["dry_run"] is True
    assert c.get("meta")["stats"]["people"] == 7, "a dry run wrote to the file"

    real = c.post("import", {"filename": "cousin.ged", "data": data,
                             "dry_run": False})
    assert real["people"] == 4
    assert c.get("meta")["stats"]["people"] == 11
    c.post("undo", {})
    assert c.get("meta")["stats"]["people"] == 7


def test_a_file_that_is_not_a_tree_says_so_rather_than_failing(family):
    """Rule 8: every error says what to do next."""
    c, ids, db = family
    out = c.post_expecting_failure(
        "import", {"filename": "holiday.jpg", "data": "data:,x",
                   "dry_run": True})
    assert "GEDCOM" in out["error"] and ".jpg" in out["error"]
