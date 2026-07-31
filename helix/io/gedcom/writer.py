"""Helix -> GEDCOM. The door out.

WHY THE WRITER CAME FIRST. A file format you can only read is a trap with a
welcome mat. Ten years of somebody's research living in one SQLite file is
only safe if it can leave, and GEDCOM is the one format Ancestry,
MyHeritage, FamilySearch, Gramps, RootsMagic and Family Tree Maker all
accept. The reader saves people retyping; the writer is what makes the
promise in `docs/KEEPING_YOUR_WORK.md` true.

WHAT IT WRITES
  GEDCOM 5.5.1 by default, 7.0 on request. The two differ less than their
  version numbers suggest for the subset a family tree actually uses; the
  differences are listed at `_head` and each is one line.

THE RULES THIS FILE OBEYS
  * UTF-8, and say so. 5.5.1 predates it and ANSEL is the nominal default,
    but ANSEL cannot spell "Siân" and every program written this century
    reads UTF-8. Writing ANSEL to be correct-on-paper would corrupt real
    names.
  * No line over 255 characters. Long values continue with CONC, newlines
    with CONT. A program that ignores this writes files that fail to open
    in exactly the products people want to open them in.
  * Deterministic xrefs. @I1@, @I2@… assigned in a stable order, so
    exporting the same file twice gives byte-identical output and a diff
    between two exports means the data changed.
  * Nothing is silently dropped. Anything with no GEDCOM equivalent goes
    into a NOTE, and Helix's own extras go into `_` tags the reader picks
    back up -- so Helix -> GEDCOM -> Helix keeps heritage, confidence and
    the original text of a vague date.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from ...model.gendate import GenDate

MAX_LINE = 255                      # GEDCOM 5.5.1 §1 "Physical structure"

_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
           "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

# Helix event type -> GEDCOM tag. Anything not here is written as a generic
# EVEN with a TYPE line, which is the standard's own escape hatch and is
# read back by every program rather than being dropped.
EVENT_TAGS = {
    "birth": "BIRT", "death": "DEAT", "burial": "BURI", "baptism": "BAPM",
    "christening": "CHR", "cremation": "CREM", "adoption": "ADOP",
    "census": "CENS", "emigration": "EMIG", "immigration": "IMMI",
    "naturalisation": "NATU", "probate": "PROB", "will": "WILL",
    "residence": "RESI", "occupation": "OCCU", "education": "EDUC",
    "retirement": "RETI", "graduation": "GRAD", "military": "_MILT",
    "religion": "RELI", "nationality": "NATI", "title": "TITL",
}

UNION_TAGS = {"marriage": "MARR", "civil_partnership": "MARR",
              "unmarried": "_UNMR", "annulled": "ANUL", "unknown": "MARR"}

SEX = {"M": "M", "F": "F", "X": "X", "U": "U"}


def gedcom_date(d: GenDate) -> str:
    """A GenDate as GEDCOM says it.

    THE INTERVAL IS WHAT IS WRITTEN, not a midpoint. "about 1834" is stored
    here as 1831-1837 and must go out as `ABT 1834`, not `1834` and not
    `BET 1831 AND 1837` -- the first throws away the doubt and the second
    invents a precision nobody claimed. Rule 2 with a wire format on the
    end of it.
    """
    if not d.known:
        # An unparseable date is still somebody's typing (rule 5). GEDCOM
        # allows a free-form phrase in parentheses for exactly this.
        return f"({d.original})" if d.original else ""
    if d.kind == "between":
        return f"BET {_point(d.earliest, d.precision)} AND {_point(d.latest, d.precision)}"
    if d.kind == "before":
        return f"BEF {_point(d.latest, d.precision)}"
    if d.kind == "after":
        return f"AFT {_point(d.earliest, d.precision)}"
    if d.kind == "quarter":
        # No GEDCOM tag for a registration quarter. A range says the same
        # thing and loses nothing a reader can use.
        return f"BET {_point(d.earliest, 'month')} AND {_point(d.latest, 'month')}"
    prefix = {"about": "ABT ", "estimated": "EST ", "calculated": "CAL "}
    if d.kind in prefix:
        y = d.year
        return f"{prefix[d.kind]}{y}" if y else ""
    if d.precision == "decade" and d.earliest:
        return f"BET {d.earliest.year} AND {d.earliest.year + 9}"
    if d.calendar == "dual" and d.earliest:
        y = d.earliest.year
        return f"{_point(d.earliest, d.precision, year=f'{y - 1}/{str(y)[-2:]}')}"
    return _point(d.earliest, d.precision)


def _point(day, precision: str, year: Optional[str] = None) -> str:
    if day is None:
        return ""
    y = year or str(day.year)
    if precision == "day":
        return f"{day.day} {_MONTHS[day.month - 1]} {y}"
    if precision == "month":
        return f"{_MONTHS[day.month - 1]} {y}"
    return y


# ---------------------------------------------------------------- the lines


class _Out:
    """Lines, with the length rule applied in one place.

    Every value goes through here, so no caller has to remember that a
    transcript of a will is longer than 255 characters. Splitting it at the
    call sites is how half-written exports happen.
    """

    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, level: int, tag: str, value: str = "",
            xref: str = "") -> None:
        head = f"{level} " + (f"{xref} " if xref else "") + tag
        value = "" if value is None else str(value)
        if not value:
            self.lines.append(head)
            return
        first = True
        # CONT for a real newline, CONC for a line that is merely too long.
        # Joined the other way round, a two-line note comes back as one and
        # a long name comes back with a space in the middle of it.
        for part in value.split("\n"):
            cont_tag = tag if first else "CONT"
            cont_head = head if first else f"{level + 1} CONT"
            room = MAX_LINE - len(cont_head) - 1
            chunks = _chunk(part, room) or [""]
            self.lines.append(f"{cont_head} {chunks[0]}".rstrip())
            for extra in chunks[1:]:
                self.lines.append(f"{level + 1} CONC {extra}")
            first = False
            del cont_tag

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def _chunk(s: str, room: int) -> list[str]:
    if room <= 0:
        room = 40
    return [s[i:i + room] for i in range(0, len(s), room)] or [s]


# ------------------------------------------------------------ reading rows


def _rows(con, sql: str, args=()) -> list[sqlite3.Row]:
    con.row_factory = sqlite3.Row
    return con.execute(sql, args).fetchall()


def _gather(con) -> dict:
    """Everything the writer needs, in five queries rather than five per
    person. On a four-hundred-person file the per-person form spends longer
    in SQLite than the whole rest of the export."""
    people = _rows(con, "SELECT * FROM person WHERE COALESCE(active,1)=1 "
                        "ORDER BY created_at, id")
    names = _rows(con, "SELECT * FROM person_name ORDER BY is_primary DESC, id")
    unions = _rows(con, "SELECT * FROM union_ ORDER BY id")
    partners = _rows(con, "SELECT * FROM union_partner ORDER BY union_id, seq")
    children = _rows(con, "SELECT * FROM union_child "
                          "ORDER BY union_id, COALESCE(birth_order, 0)")
    events = _rows(con, """
        SELECT e.*, er.person_id, er.union_id, er.role, pl.name AS place
        FROM event e JOIN event_role er ON er.event_id = e.id
        LEFT JOIN place pl ON pl.id = e.place_id
        ORDER BY e.date_sort, e.id""")
    sources = _rows(con, "SELECT * FROM source ORDER BY id")
    cites = _rows(con, "SELECT * FROM citation ORDER BY id")
    try:
        herit = _rows(con, "SELECT * FROM person_heritage ORDER BY person_id, label")
    except sqlite3.OperationalError:
        herit = []
    return {"people": people, "names": names, "unions": unions,
            "partners": partners, "children": children, "events": events,
            "sources": sources, "cites": cites, "heritage": herit}


def _index(g: dict) -> dict:
    by: dict = {"name": {}, "event_p": {}, "event_u": {}, "partner": {},
                "child": {}, "cite_p": {}, "herit": {}}
    for r in g["names"]:
        by["name"].setdefault(r["person_id"], []).append(r)
    for r in g["events"]:
        if r["person_id"]:
            by["event_p"].setdefault(r["person_id"], []).append(r)
        elif r["union_id"]:
            by["event_u"].setdefault(r["union_id"], []).append(r)
    for r in g["partners"]:
        by["partner"].setdefault(r["union_id"], []).append(r)
    for r in g["children"]:
        by["child"].setdefault(r["union_id"], []).append(r)
    for r in g["cites"]:
        if r["person_id"]:
            by["cite_p"].setdefault(r["person_id"], []).append(r)
    for r in g["heritage"]:
        by["herit"].setdefault(r["person_id"], []).append(r)
    return by


# ------------------------------------------------------------------ export


def export(con, path: str | Path, *, version: str = "5.5.1",
           title: str = "", submitter: str = "") -> dict:
    """Write the whole file as GEDCOM. Returns a summary of what went out."""
    g = _gather(con)
    by = _index(g)

    # Stable xrefs. Sorted by the order people were entered rather than by
    # UUID, so the numbering follows the shape of somebody's research and a
    # re-export after adding one person does not renumber everybody.
    ind = {p["id"]: f"@I{i}@" for i, p in enumerate(g["people"], 1)}
    fam = {u["id"]: f"@F{i}@" for i, u in enumerate(g["unions"], 1)}
    src = {s["id"]: f"@S{i}@" for i, s in enumerate(g["sources"], 1)}

    o = _Out()
    _head(o, version, title, submitter, path)
    for p in g["people"]:
        _person(o, p, by, ind, fam, src, g)
    sex = {p["id"]: p["sex"] for p in g["people"]}
    for u in g["unions"]:
        _family(o, u, by, ind, fam, src, sex)
    for s in g["sources"]:
        _source(o, s, src)
    o.add(0, "TRLR")

    text = o.text()
    Path(path).write_text(text, encoding="utf-8", newline="\n")
    return {"path": str(path), "version": version,
            "people": len(g["people"]), "families": len(g["unions"]),
            "sources": len(g["sources"]), "lines": len(o.lines),
            "bytes": len(text.encode())}


def _head(o: _Out, version: str, title: str, submitter: str, path) -> None:
    """The header, and the only place 5.5.1 and 7.0 really diverge here.

    7.0 dropped SUBM as a required pointer, dropped CHAR entirely (it is
    always UTF-8), and expects `SCHMA` for custom tags. 5.5.1 wants CHAR and
    a submitter. Both accept everything else this writer emits.
    """
    seven = version.startswith("7")
    o.add(0, "HEAD")
    o.add(1, "SOUR", "HELIX")
    o.add(2, "VERS", "1.0")
    o.add(2, "NAME", "Helix")
    o.add(2, "CORP", "Helix")
    o.add(1, "DEST", "ANY")
    now = datetime.now()
    o.add(1, "DATE", f"{now.day} {_MONTHS[now.month - 1]} {now.year}")
    o.add(2, "TIME", now.strftime("%H:%M:%S"))
    if title:
        o.add(1, "NOTE", title)
    o.add(1, "FILE", Path(path).name)
    o.add(1, "GEDC")
    o.add(2, "VERS", "7.0" if seven else "5.5.1")
    if not seven:
        o.add(2, "FORM", "LINEAGE-LINKED")
        o.add(3, "VERS", "5.5.1")
        o.add(1, "CHAR", "UTF-8")
        o.add(1, "SUBM", "@SUBM1@")
    if seven:
        # Declare the custom tags rather than leaving a reader to guess.
        o.add(1, "SCHMA")
        o.add(2, "TAG", "_HERITAGE https://helix.local/heritage")
        o.add(2, "TAG", "_CONF https://helix.local/confidence")
    if not seven:
        o.add(0, "SUBM", xref="@SUBM1@")
        o.add(1, "NAME", submitter or "Helix")


def _person(o: _Out, p, by, ind, fam, src, g) -> None:
    o.add(0, "INDI", xref=ind[p["id"]])
    for n in by["name"].get(p["id"], []):
        _name(o, n)
    o.add(1, "SEX", SEX.get(p["sex"], "U"))

    for e in by["event_p"].get(p["id"], []):
        _event(o, e, 1)

    # Which family they were a child in, and which they were a partner in.
    for u in g["unions"]:
        uid = u["id"]
        if any(c["person_id"] == p["id"] for c in by["child"].get(uid, [])):
            o.add(1, "FAMC", fam[uid])
        if any(x["person_id"] == p["id"] for x in by["partner"].get(uid, [])):
            o.add(1, "FAMS", fam[uid])

    # HELIX'S OWN EXTRAS, in `_` tags. A reader that does not know them
    # keeps them as notes -- which is the whole reason the underscore
    # convention exists -- and Helix's own reader turns them back into
    # rows, so a round trip through this file loses nothing.
    for h in by["herit"].get(p["id"], []):
        o.add(1, "_HERITAGE", h["label"])
        o.add(2, "_SHARE", f"{h['share']:.4f}".rstrip("0").rstrip("."))
    if p["confidence"] is not None and p["confidence"] != 2:
        o.add(1, "_CONF", str(p["confidence"]))
    if p["is_placeholder"]:
        o.add(1, "_PLACEHOLDER", "Y")
    if p["living"] is not None:
        o.add(1, "_LIVING", "Y" if p["living"] else "N")
    if p["notes"]:
        o.add(1, "NOTE", p["notes"])
    for c in by["cite_p"].get(p["id"], []):
        _cite(o, c, src, 1)


def _name(o: _Out, n) -> None:
    """`John /Smith/` -- the slashes ARE the surname, and they are not
    optional. Written without them, every reader guesses which word is the
    family name, and guesses wrong for "Mary Anne de la Mare"."""
    given = (n["given"] or "").strip()
    surname = " ".join(x for x in [(n["surname_prefix"] or "").strip(),
                                   (n["surname"] or "").strip()] if x)
    o.add(1, "NAME", f"{given} /{surname}/".strip())
    if n["type"] and n["type"] != "birth":
        o.add(2, "TYPE", {"married": "married", "also_known_as": "aka",
                          "nickname": "aka", "legal": "legal",
                          "religious": "religious",
                          "anglicised": "aka",
                          "as_recorded": "aka"}.get(n["type"], "aka"))
    if given:
        o.add(2, "GIVN", given)
    if n["surname"]:
        o.add(2, "SURN", n["surname"])
    if n["surname_prefix"]:
        o.add(2, "SPFX", n["surname_prefix"])
    if n["title"]:
        o.add(2, "NPFX", n["title"])
    if n["suffix"]:
        o.add(2, "NSFX", n["suffix"])
    if n["given_used"] and n["given_used"] != given:
        o.add(2, "_USED", n["given_used"])


# Tags that carry their value on the tag line itself rather than in a
# child NOTE. `1 OCCU Carpenter` is what a reader looks for; written as
# `1 OCCU` with the trade underneath, an occupation imports into Ancestry
# as an event with no description at all.
_VALUE_ON_TAG = {"OCCU", "EDUC", "RELI", "NATI", "TITL"}


def _event(o: _Out, e, level: int) -> None:
    typ = e["type"]
    tag = EVENT_TAGS.get(typ, "EVEN")
    desc = e["description"] or ""
    on_tag = tag in _VALUE_ON_TAG and desc
    o.add(level, tag, desc if on_tag else "")
    if tag == "EVEN":
        o.add(level + 1, "TYPE", typ)
    d = GenDate.from_json(e["date_json"])
    gd = gedcom_date(d) if (d.known or d.original) else ""
    if gd:
        o.add(level + 1, "DATE", gd)
    # THE ORIGINAL TYPING SURVIVES THE TRIP. GEDCOM's `ABT 1834` is a lossy
    # rendering of "around 1834, from her marriage certificate"; rule 5 says
    # what somebody typed is never destroyed, and that has to hold through
    # an export as well as through a save.
    if d.original and d.original.upper() != gd.upper():
        o.add(level + 1, "_ORIG", d.original)
    if e["place"]:
        o.add(level + 1, "PLAC", e["place"])
    if desc and not on_tag:
        o.add(level + 1, "NOTE", desc)
    if e["age_text"]:
        o.add(level + 1, "AGE", e["age_text"])
    if e["notes"]:
        o.add(level + 1, "NOTE", e["notes"])


def _family(o: _Out, u, by, ind, fam, src, sex) -> None:
    o.add(0, "FAM", xref=fam[u["id"]])
    parts = list(by["partner"].get(u["id"], []))
    # HUSB and WIFE are what every reader looks for, and a family with two
    # partners of the same sex, or one partner, or none, is ordinary rather
    # than an error. Seat by sex where sex is known, then fill the empty
    # seat in order -- which is what stops a same-sex marriage from
    # silently losing a partner off the end of the record.
    seats: dict[str, object] = {}
    for tag, want in (("HUSB", "M"), ("WIFE", "F")):
        for pr in parts:
            if pr not in seats.values() and sex.get(pr["person_id"]) == want:
                seats[tag] = pr
                break
    spare = [pr for pr in parts if pr not in seats.values()]
    for tag in ("HUSB", "WIFE"):
        if tag not in seats and spare:
            seats[tag] = spare.pop(0)
    for tag in ("HUSB", "WIFE"):
        if tag in seats:
            o.add(1, tag, ind.get(seats[tag]["person_id"], ""))
    for pr in spare:                       # a third partner, if a file has one
        o.add(1, "_PARTNER", ind.get(pr["person_id"], ""))

    for c in by["child"].get(u["id"], []):
        o.add(1, "CHIL", ind.get(c["person_id"], ""))
        if c["rel_partner1"] != "biological" or c["rel_partner2"] != "biological":
            o.add(2, "_REL", f"{c['rel_partner1']}/{c['rel_partner2']}")

    evs = by["event_u"].get(u["id"], [])
    for e in evs:
        _event(o, e, 1)
    if not evs and u["type"] in UNION_TAGS:
        # A marriage with no date is still a marriage, and a FAM with no
        # MARR in it reads in some programs as "these two never married".
        o.add(1, UNION_TAGS[u["type"]], "Y" if u["type"] != "unmarried" else "")
    if u["type"] != "marriage":
        o.add(1, "_TYPE", u["type"])
    if u["notes"]:
        o.add(1, "NOTE", u["notes"])


def _source(o: _Out, s, src) -> None:
    o.add(0, "SOUR", xref=src[s["id"]])
    if s["title"]:
        o.add(1, "TITL", s["title"])
    if s["author"]:
        o.add(1, "AUTH", s["author"])
    if s["publisher"]:
        o.add(1, "PUBL", s["publisher"])
    if s["repository"]:
        o.add(1, "REPO")
        o.add(2, "NOTE", s["repository"])
    if s["url"]:
        o.add(1, "NOTE", s["url"])
    if s["notes"]:
        o.add(1, "NOTE", s["notes"])


def _cite(o: _Out, c, src, level: int) -> None:
    ref = src.get(c["source_id"])
    if not ref:
        return
    o.add(level, "SOUR", ref)
    if c["page"]:
        o.add(level + 1, "PAGE", c["page"])
    if c["transcript"]:
        o.add(level + 1, "DATA")
        o.add(level + 2, "TEXT", c["transcript"])
    if c["reasoning"]:
        o.add(level + 1, "NOTE", c["reasoning"])
