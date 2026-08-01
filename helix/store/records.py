"""The record system: every write a person can make to their own family.

Single responsibility: turn "add my father" into the rows that means, and
record enough in `change_log` to take it back. It owns no HTTP and no HTML;
`server.py` is the only caller and does nothing but hand it a payload.

THE MODEL. You are always standing on somebody, and you add the next person
relative to them. Nobody types into a database; they say "my father had a
sister" and this module works out that a sister needs the union holding her
parents, creating it if this is the first anyone has heard of them.

WHAT THIS MODULE MUST NOT DO.

  * Never SQL-DELETE a person. `retire()` sets `active = 0` and takes their
    links off, so a wrong ancestor removed at midnight is still there in the
    morning. Undo of a person's creation does the same thing rather than
    deleting the row: the whole point is that nothing you type is ever gone.
  * Never say "union". That word is right for the schema and wrong for
    someone adding their aunt, so it stays on this side of the API. The
    labels this module writes into `change_log` are read back to the user in
    the undo toast, so they say "partner" and "father", not "union_partner".
  * Never reject a date. `abt 1834`, `bef 1900`, `Q3 1871` and outright
    nonsense are all stored; unparseable text is kept verbatim with
    kind='unknown'.
  * Never block a save on a validation warning. If a child was born before
    their parent, say so and save it anyway -- people enter what the record
    says and fix it later.

HOW UNDO WORKS. Every mutation goes through `Edit`, which writes one
`change_log` row per table row it touches, tagged with a batch id and a
plain-English label. Undo reverts the newest batch that has not been undone,
in reverse order, and marks it undone rather than deleting it, so redo can
walk forward again. Starting a new edit clears anything undone, which is what
every text editor does and what people expect.
"""
from __future__ import annotations

import difflib
import json
from typing import Any, Optional

from ..model.gendate import parse as parse_date
from .db import new_id

# Primary key columns per table. Undo needs to find one row again, and half
# these tables have composite keys.
KEYS: dict[str, tuple[str, ...]] = {
    "person": ("id",),
    "person_name": ("id",),
    "union_": ("id",),
    "union_partner": ("union_id", "person_id"),
    "union_child": ("union_id", "person_id"),
    "event": ("id",),
    "event_role": ("event_id", "person_id", "union_id", "role"),
    "place": ("id",),
    # Photographs. `media_link.event_id` is part of the key and is usually
    # NULL, which is why `_where` matches with IS rather than = -- a picture
    # of a person and not of an event is the ordinary case, and `= NULL` is
    # never true of anything.
    "media": ("id",),
    "media_link": ("media_id", "person_id", "event_id"),
    "person_heritage": ("person_id", "label"),
    # Where a fact came from. Written by the GEDCOM importer, which brings
    # a cousin's sources in with their tree -- an import that dropped them
    # would be turning cited research into hearsay.
    "source": ("id",),
    "citation": ("id",),
    # Tags. Absent until bulk edit needed them, which meant a tag was the
    # one thing in the file that could be added and not taken back --
    # writing them outside `Edit` left no `change_log` row, so Ctrl-Z
    # skipped over the tag and undid whatever came before it.
    "tag": ("id",),
    "person_tag": ("person_id", "tag_id"),
}

ATTACHMENTS = ("father", "mother", "partner", "child", "sibling")


# ================================================================== plumbing ==
def _where(keys: dict[str, Any]) -> tuple[str, tuple]:
    return " AND ".join(f"{k} IS ?" for k in keys), tuple(keys.values())


def _read(con, tbl: str, keys: dict) -> Optional[dict]:
    sql, vals = _where(keys)
    # Table names come from KEYS and this module's own calls, never from a
    # request body, so they cannot carry anything from outside.
    r = con.execute(f"SELECT * FROM {tbl} WHERE {sql}", vals).fetchone()
    return dict(r) if r else None


def _insert_row(con, tbl: str, row: dict) -> None:
    cols = ",".join(row)
    con.execute(f"INSERT INTO {tbl}({cols}) "
                f"VALUES({','.join('?' * len(row))})", tuple(row.values()))


def _update_row(con, tbl: str, keys: dict, row: dict) -> None:
    """Put a row back to a previous state, in place.

    It must be an UPDATE and not an INSERT OR REPLACE. REPLACE deletes the
    old row before inserting, and `person` is the target of ON DELETE CASCADE
    from every link table -- so restoring a person during undo silently took
    out the very links the same undo had just put back.
    """
    cols = {k: v for k, v in row.items() if k not in keys}
    if not cols:
        return
    sets = ",".join(f"{k}=?" for k in cols)
    sql, vals = _where(keys)
    con.execute(f"UPDATE {tbl} SET {sets} WHERE {sql}",
                (*cols.values(), *vals))


def _delete_row(con, tbl: str, keys: dict) -> None:
    sql, vals = _where(keys)
    con.execute(f"DELETE FROM {tbl} WHERE {sql}", vals)


class Edit:
    """One user action, however many rows it turns out to be.

    Used as a context manager so a half-finished action rolls back rather
    than leaving a person with no name.
    """

    def __init__(self, con, label: str):
        self.con = con
        self.label = label
        self.batch = new_id()

    def __enter__(self) -> "Edit":
        # A fresh edit ends the redo road, exactly as a text editor does.
        self.con.execute("DELETE FROM change_log WHERE undone=1")
        return self

    def __exit__(self, exc_type, *_):
        if exc_type is None:
            self.con.commit()
        else:
            self.con.rollback()
        return False

    # ---------------------------------------------------------------- writes
    def insert(self, tbl: str, row: dict) -> None:
        _insert_row(self.con, tbl, row)
        self._log("insert", tbl, {k: row.get(k) for k in KEYS[tbl]}, None, row)

    def update(self, tbl: str, keys: dict, changes: dict) -> None:
        before = _read(self.con, tbl, keys)
        if before is None:
            return
        sets = ",".join(f"{k}=?" for k in changes)
        sql, vals = _where(keys)
        self.con.execute(f"UPDATE {tbl} SET {sets} WHERE {sql}",
                         (*changes.values(), *vals))
        self._log("update", tbl, keys, before, _read(self.con, tbl, keys))

    def delete(self, tbl: str, keys: dict) -> None:
        before = _read(self.con, tbl, keys)
        if before is None:
            return
        _delete_row(self.con, tbl, keys)
        self._log("delete", tbl, keys, before, None)

    def _log(self, op, tbl, keys, before, after) -> None:
        self.con.execute(
            "INSERT INTO change_log(op,tbl,row_id,before,after,batch,label) "
            "VALUES(?,?,?,?,?,?,?)",
            (op, tbl, json.dumps(keys, sort_keys=True),
             json.dumps(before) if before is not None else None,
             json.dumps(after) if after is not None else None,
             self.batch, self.label))


# ============================================================== undo and redo ==
def _revert(con, r) -> None:
    tbl, keys = r["tbl"], json.loads(r["row_id"])
    if r["op"] == "insert":
        if tbl == "person":
            con.execute("UPDATE person SET active=0 WHERE id=?", (keys["id"],))
        else:
            _delete_row(con, tbl, keys)
    elif r["op"] == "delete":
        _insert_row(con, tbl, json.loads(r["before"]))
    else:
        _update_row(con, tbl, keys, json.loads(r["before"]))


def _reapply(con, r) -> None:
    tbl, keys = r["tbl"], json.loads(r["row_id"])
    if r["op"] == "insert":
        if tbl == "person":
            con.execute("UPDATE person SET active=1 WHERE id=?", (keys["id"],))
        else:
            _insert_row(con, tbl, json.loads(r["after"]))
    elif r["op"] == "delete":
        _delete_row(con, tbl, keys)
    else:
        _update_row(con, tbl, keys, json.loads(r["after"]))


def undo(con) -> dict:
    row = con.execute("SELECT batch,label FROM change_log WHERE undone=0 "
                      "ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return {"ok": False, "message": "Nothing to undo."}
    rows = con.execute("SELECT * FROM change_log WHERE batch=? AND undone=0 "
                       "ORDER BY id DESC", (row["batch"],)).fetchall()
    for r in rows:
        _revert(con, r)
    con.execute("UPDATE change_log SET undone=1 WHERE batch=?", (row["batch"],))
    con.commit()
    return {"ok": True, "label": row["label"], "message": f"Undid: {row['label']}"}


def redo(con) -> dict:
    row = con.execute("SELECT batch,label FROM change_log WHERE undone=1 "
                      "ORDER BY id ASC LIMIT 1").fetchone()
    if not row:
        return {"ok": False, "message": "Nothing to redo."}
    rows = con.execute("SELECT * FROM change_log WHERE batch=? AND undone=1 "
                       "ORDER BY id ASC", (row["batch"],)).fetchall()
    for r in rows:
        _reapply(con, r)
    con.execute("UPDATE change_log SET undone=0 WHERE batch=?", (row["batch"],))
    con.commit()
    return {"ok": True, "label": row["label"], "message": f"Redid: {row['label']}"}


def history(con, limit: int = 120) -> dict:
    """What Ctrl-Z and Ctrl-Y would do next, for labelling the buttons."""
    nxt = con.execute("SELECT label FROM change_log WHERE undone=0 "
                      "ORDER BY id DESC LIMIT 1").fetchone()
    fwd = con.execute("SELECT label FROM change_log WHERE undone=1 "
                      "ORDER BY id ASC LIMIT 1").fetchone()
    depth = con.execute("SELECT COUNT(DISTINCT batch) n FROM change_log "
                        "WHERE undone=0").fetchone()["n"]
    return {"undo": nxt["label"] if nxt else None,
            "redo": fwd["label"] if fwd else None,
            "depth": depth}


# ================================================================== people ====
def _place_id(e: Edit, name: str) -> Optional[str]:
    name = (name or "").strip()
    if not name:
        return None
    r = e.con.execute("SELECT id FROM place WHERE name=? LIMIT 1",
                      (name,)).fetchone()
    if r:
        return r["id"]
    pid = new_id()
    e.insert("place", {"id": pid, "name": name, "as_recorded": name})
    return pid


def set_event(e: Edit, person_id: str, typ: str, text: Optional[str],
              place: str = "", desc: Optional[str] = None) -> None:
    """Record a dated fact. Whatever was typed is kept: an unparseable date
    is stored with kind='unknown' and the original string intact.

    `desc` is for the facts that are a piece of TEXT rather than a date --
    an occupation, a school. They are events like everything else, so they
    can be dated and cited later without a schema change, and clearing one
    to empty deletes nothing: the row stays with a blank description, which
    is the difference between "not recorded" and "recorded as nothing".

    NONE MEANS LEAVE IT ALONE, and the distinction is not pedantic. An empty
    string is somebody clearing a field; None is a request that never
    mentioned it. Written the same way, saving a birthplace on its own sent
    an empty date with it and wiped the birth date that was already there --
    which is the one thing this module must never do.
    """
    d = parse_date(text or "")
    place_id = _place_id(e, place)
    row = e.con.execute(
        "SELECT e.id FROM event e JOIN event_role r ON r.event_id=e.id "
        "WHERE r.person_id=? AND e.type=? LIMIT 1", (person_id, typ)).fetchone()
    fields = {} if text is None else {
        "date_json": d.to_json(),
        "date_earliest": d.earliest.isoformat() if d.earliest else None,
        "date_latest": d.latest.isoformat() if d.latest else None,
        "date_sort": d.sort_value,
    }
    if place_id:
        fields["place_id"] = place_id
    if desc is not None:
        fields["description"] = desc.strip() or None
    if row:
        if fields:
            e.update("event", {"id": row["id"]}, fields)
        return
    if (not d.known and not (text or "").strip() and not place_id
            and not (desc or "").strip()):
        return
    eid = new_id()
    e.insert("event", {"id": eid, "type": typ, **fields})
    e.insert("event_role", {"event_id": eid, "person_id": person_id,
                            "union_id": None, "role": "principal"})


def create_person(e: Edit, *, given="", surname="", sex="U", birth="",
                  death="", birth_place="", notes="") -> str:
    pid = new_id()
    sex = sex if sex in ("M", "F", "X", "U") else "U"
    e.insert("person", {"id": pid, "sex": sex, "notes": notes or None,
                        "active": 1})
    e.insert("person_name", {
        "id": new_id(), "person_id": pid, "type": "birth", "is_primary": 1,
        "given": given.strip(), "surname": surname.strip(),
        "sort_key": f"{surname.strip().upper()}, {given.strip()}"})
    if birth or birth_place:
        set_event(e, pid, "birth", birth, birth_place)
    if death:
        set_event(e, pid, "death", death)
    return pid


# ════════════════════════ facts, one at a time ═══════════════════════════
#
# `update_person` writes the five facts the panel has boxes for. This is the
# other half: ANY fact, with a date, a place, a note and a confidence, added,
# corrected or taken off. It is what makes the schema's own vocabulary
# reachable -- a will, an apprenticeship, an emigration, a census, a divorce
# -- without a new field per idea.
#
# WHY THE LIST IS A SUGGESTION AND NOT A RULE. `event.type` is a free string
# in the schema and stays one: somebody researching a family of watermen
# needs "apprenticed to the Company of Watermen" and will not wait for a
# release. The list below is what the panel offers first, in the order a life
# happens; anything else typed in is kept.
FACT_KINDS = [
    ("birth", "Born"), ("baptism", "Baptised"), ("census", "Census"),
    ("residence", "Lived at"), ("occupation", "Occupation"),
    ("education", "Education"), ("apprenticeship", "Apprenticeship"),
    ("military", "Military service"), ("emigration", "Emigrated"),
    ("immigration", "Arrived"), ("naturalisation", "Naturalised"),
    ("religion", "Religion"), ("marriage", "Married"),
    ("divorce", "Divorced"), ("death", "Died"), ("burial", "Buried"),
    ("cremation", "Cremated"), ("probate", "Probate"), ("will", "Will"),
    ("other", "Something else"),
]

# What each confidence means, in words. A number on its own invites somebody
# to average them, which is exactly what a confidence is not for.
CONFIDENCE = [
    (0, "Unproved — a guess, or somebody's say-so"),
    (1, "Likely — indirect evidence, not seen"),
    (2, "Recorded — seen in an index or a transcript"),
    (3, "Proved — the original record, or a certificate"),
]


def event_op(con, body: dict) -> dict:
    """POST /api/event. Add, change or take off one fact.

    Attaches to a PERSON or to a FAMILY -- a marriage and a divorce are facts
    about two people, and putting them on one of them is how a divorce ends
    up recorded twice and disagreeing with itself.
    """
    action = body.get("action", "save")
    typ = (body.get("type") or "other").strip().lower().replace(" ", "_")
    pid, uid = body.get("id"), body.get("union_id")
    who = display_name(con, pid) if pid else "this family"
    label = {"save": f"Record a fact for {who}",
             "remove": f"Take a fact off {who}"}.get(action, "Edit a fact")

    with Edit(con, label) as e:
        if action == "remove":
            eid = body["event_id"]
            for r in con.execute("SELECT * FROM event_role WHERE event_id=?",
                                 (eid,)).fetchall():
                e.delete("event_role", {"event_id": eid,
                                        "person_id": r["person_id"],
                                        "union_id": r["union_id"],
                                        "role": r["role"]})
            for r in con.execute("SELECT id FROM citation WHERE event_id=?",
                                 (eid,)).fetchall():
                e.delete("citation", {"id": r["id"]})
            e.delete("event", {"id": eid})
            return {"ok": True, "removed": eid}

        d = parse_date(body.get("date") or "")
        fields = {
            "type": typ,
            "date_json": d.to_json(),
            "date_earliest": d.earliest.isoformat() if d.earliest else None,
            "date_latest": d.latest.isoformat() if d.latest else None,
            "date_sort": d.sort_value,
            "place_id": _place_id(e, body.get("place", "")),
            "description": (body.get("note") or "").strip() or None,
            "confidence": max(0, min(3, int(body.get("confidence", 2)))),
        }
        eid = body.get("event_id")
        if eid:
            e.update("event", {"id": eid}, fields)
        else:
            eid = new_id()
            e.insert("event", {"id": eid, **fields})
            e.insert("event_role", {"event_id": eid, "person_id": pid,
                                    "union_id": uid, "role": "principal"})
    return {"ok": True, "event_id": eid}


# ═══════════════════════ where a fact came from ══════════════════════════
#
# THE LINE BETWEEN RESEARCH AND HEARSAY. `source` and `citation` have been in
# the schema from the first commit and only the GEDCOM importer ever wrote to
# them -- so the record book could ask "where did this come from?" and the
# program had no way to be told.
#
# A SOURCE IS THE THING ITSELF and is written down once: the 1861 census, a
# parish register, a headstone, an aunt. A CITATION is one use of it, with
# the page. Kept apart because the alternative is typing "1861 Census of
# England and Wales" forty times and spelling it four ways.
def source_op(con, body: dict) -> dict:
    """POST /api/source. Add, correct or remove a source."""
    action = body.get("action", "save")
    with Edit(con, {"save": "Record a source",
                    "remove": "Remove a source"}.get(action, "Edit a source")) as e:
        if action == "remove":
            sid = body["source_id"]
            for r in con.execute("SELECT id FROM citation WHERE source_id=?",
                                 (sid,)).fetchall():
                e.delete("citation", {"id": r["id"]})
            e.delete("source", {"id": sid})
            return {"ok": True, "removed": sid}

        title = (body.get("title") or "").strip()
        if not title:
            raise ValueError(
                "A source needs a title — what the record IS. "
                "\"1861 Census of England and Wales\" or "
                "\"Parish register, St Mary, Frome\" will do.")
        fields = {k: (body.get(k) or "").strip() or None
                  for k in ("author", "repository", "ref", "url", "notes")}
        fields["title"] = title
        fields["type"] = (body.get("type") or "record").strip()
        fields["quality"] = max(0, min(3, int(body.get("quality", 2))))
        sid = body.get("source_id")
        if sid:
            e.update("source", {"id": sid}, fields)
        else:
            sid = new_id()
            e.insert("source", {"id": sid, **fields})
    return {"ok": True, "source_id": sid}


def cite_op(con, body: dict) -> dict:
    """POST /api/cite. Say that a source backs up a particular fact."""
    action = body.get("action", "add")
    with Edit(con, "Cite a source" if action == "add"
              else "Take a source off a fact") as e:
        if action == "remove":
            e.delete("citation", {"id": body["citation_id"]})
            return {"ok": True}
        keys = {k: body.get(k) for k in
                ("person_id", "event_id", "union_id", "name_id")}
        if not any(keys.values()):
            raise ValueError("Choose the fact this source is evidence for.")
        got = con.execute(
            "SELECT id FROM citation WHERE source_id=? AND person_id IS ? "
            "AND event_id IS ? AND union_id IS ? AND name_id IS ?",
            (body["source_id"], keys["person_id"], keys["event_id"],
             keys["union_id"], keys["name_id"])).fetchone()
        cid = got["id"] if got else new_id()
        fields = {"source_id": body["source_id"], **keys,
                  "page": (body.get("page") or "").strip() or None,
                  "transcript": (body.get("transcript") or "").strip() or None,
                  "confidence": max(0, min(3, int(body.get("confidence", 2))))}
        if got:
            e.update("citation", {"id": cid}, fields)
        else:
            e.insert("citation", {"id": cid, **fields})
    return {"ok": True, "citation_id": cid}


def history_list(con, limit: int = 200) -> list[dict]:
    """What has been done to this file, newest first.

    NOT JUST CTRL-Z. `change_log` has held every edit from the beginning and
    the only way to see it was one step at a time. "What did I change last
    Tuesday" is a question anybody asks of ten years of research, and the
    answer was in the file all along.

    Grouped by batch, because one batch is one thing a person did: adding a
    father is six rows and one action, and a list of six rows is a list of
    the program's business rather than theirs.
    """
    out = []
    for r in con.execute(
        "SELECT batch, label, MAX(undone) undone, MAX(id) hi, "
        "       COUNT(*) n, MAX(ts) ts "
        "FROM change_log GROUP BY batch ORDER BY hi DESC LIMIT ?", (limit,)
    ):
        out.append({"batch": r["batch"], "label": r["label"],
                    "undone": bool(r["undone"]), "rows": r["n"],
                    "at": r["ts"]})
    return out


def what_changed(con, batch: str, *, limit: int = 400) -> dict:
    """Who and what a single batch actually touched.

    "IMPORTED 463 PEOPLE" IS NOT A REPORT. It is a number, and the question
    anybody has after an import is which of them are already in the file
    under a different spelling, which surnames arrived, and whether the
    thing they meant to bring in came. Four hundred and sixty-three could
    equally be the wrong file.

    Read back out of `change_log` rather than counted a second time on the
    way in. The record system is already the only thing that writes, so
    this cannot drift from what happened -- and a batch that Ctrl-Z can
    take back whole is exactly the unit worth showing.
    """
    rows = con.execute(
        "SELECT op, tbl, row_id FROM change_log WHERE batch=? ORDER BY id",
        (batch,)).fetchall()
    if not rows:
        raise ValueError(
            "There is nothing recorded under that change. It may have been "
            "made before this file kept a history.")
    head = con.execute(
        "SELECT label, MIN(ts) ts, COUNT(*) n FROM change_log WHERE batch=?",
        (batch,)).fetchone()

    tables: dict = {}
    for r in rows:
        tables[r["tbl"]] = tables.get(r["tbl"], 0) + 1

    # WHICH PERSON DOES THIS ROW BELONG TO. Counting `person` rows alone
    # would have said "0 people" for correcting forty birthplaces, because
    # a birthplace is an `event` and rule 4 means there is no birth column
    # on `person` to touch. Every table that can be traced back to somebody
    # is traced; a `place` or a `source` row belongs to no one and is left
    # out of the count rather than guessed at.
    made: list[str] = []                # order kept: an import reads in file order
    touched: set[str] = set()

    def note(pid, is_new):
        if not pid:
            return
        if is_new:
            made.append(pid)
        else:
            touched.add(pid)

    for r in rows:
        try:
            key = json.loads(r["row_id"])
        except Exception:
            continue
        tbl, new_row = r["tbl"], r["op"] == "insert"
        if tbl == "person":
            note(key.get("id"), new_row)
        elif tbl in ("person_name", "person_tag", "person_heritage",
                     "media_link", "union_partner", "union_child",
                     "event_role"):
            note(key.get("person_id"), False)
        elif tbl == "event":
            # An event's own row does not say whose it is. `event_role` does,
            # and one event can belong to two people -- a marriage.
            for x in con.execute("SELECT person_id FROM event_role WHERE "
                                 "event_id=? AND person_id IS NOT NULL",
                                 (key.get("id"),)):
                note(x["person_id"], False)

    new = set(made)
    edited = touched - new

    from ..graph import build as gbuild
    g = gbuild.load(con)

    def who(pid):
        p = g.people.get(pid)
        return {"id": pid,
                "name": p.full_name if p else "(no longer on the chart)",
                "life": p.lifespan if p else "",
                "surname": p.surname if p else "",
                "parents": len(g.parents(pid)) if p else 0}

    added_ids = list(dict.fromkeys(made))
    people = [who(p) for p in added_ids[:limit]]
    changed = [who(p) for p in sorted(
        edited, key=lambda x: g.people[x].sort_key
        if x in g.people else "~")][:limit]

    surnames: dict = {}
    years = []
    for x in people:
        if x["surname"]:
            surnames[x["surname"]] = surnames.get(x["surname"], 0) + 1
        p = g.people.get(x["id"])
        if p and p.birth_year:
            years.append(p.birth_year)
    # THE ONES WITH NOBODY ABOVE THEM. After an import these are where the
    # two trees have to be joined by hand, and they are the only part of a
    # four-hundred-person import that needs a decision.
    loose = [x for x in people if not x["parents"]]

    return {
        "batch": batch, "label": head["label"], "at": head["ts"],
        "rows": head["n"], "tables": tables,
        "added": len(added_ids), "edited": len(edited),
        "people": people, "truncated": len(added_ids) > len(people),
        "changed": changed,
        "surnames": sorted(surnames.items(), key=lambda kv: (-kv[1], kv[0])),
        "years": [min(years), max(years)] if years else None,
        "loose": loose[:40], "loose_total": len(loose),
    }


def revert_to(con, batch: str) -> dict:
    """Undo everything back to just after that batch.

    ONE STEP AT A TIME, through `undo`, so every guarantee it makes still
    holds -- rather than a second reverting path that has to be kept in step
    with the first and will not be.
    """
    order = [r["batch"] for r in con.execute(
        "SELECT batch, MAX(id) hi FROM change_log WHERE undone=0 "
        "GROUP BY batch ORDER BY hi DESC")]
    if batch not in order:
        raise ValueError("That change has already been taken back.")
    steps = order.index(batch) + 1
    done = []
    for _ in range(steps):
        r = undo(con)
        if not r.get("ok"):
            break
        done.append(r.get("label") or r.get("message", ""))
    return {"ok": True, "steps": len(done), "undone": done,
            "message": (f"Took back {len(done)} "
                        f"{'change' if len(done) == 1 else 'changes'}. "
                        f"Ctrl-Y puts them back one at a time.")}


def update_person(con, body: dict) -> dict:
    """POST /api/person. Edit somebody already in the file.

    Goes through `Edit` like everything else. It used to write its rows
    inline, which meant a corrected date left no trace in `change_log` --
    so Ctrl-Z silently took back whatever you did BEFORE it, usually
    deleting a person you had just added.
    """
    pid = body["id"]
    with Edit(con, f"Edit {display_name(con, pid)}") as e:
        if "given" in body or "surname" in body:
            r = con.execute("SELECT id,given,surname FROM person_name "
                            "WHERE person_id=? AND is_primary=1 LIMIT 1",
                            (pid,)).fetchone()
            given = body.get("given", r["given"] if r else "") or ""
            surname = body.get("surname", r["surname"] if r else "") or ""
            fields = {"given": given.strip(), "surname": surname.strip(),
                      "sort_key": f"{surname.strip().upper()}, {given.strip()}"}
            if r:
                e.update("person_name", {"id": r["id"]}, fields)
            else:
                e.insert("person_name", {"id": new_id(), "person_id": pid,
                                         "type": "birth", "is_primary": 1,
                                         **fields})
        # `.get(k)` and not `.get(k, "")`: a key that is absent means "do
        # not touch this", and an empty string means "clear it". Sent the
        # same way, saving somebody's birthplace wiped their birth date.
        if "birth" in body or "birth_place" in body:
            set_event(e, pid, "birth", body.get("birth"),
                      body.get("birth_place", ""))
        if "death" in body or "death_place" in body:
            set_event(e, pid, "death", body.get("death"),
                      body.get("death_place", ""))
        # WHAT SOMEBODY KNEW ABOUT THEM. Not decoration: these are the
        # things people actually remember and the reason for keeping a file
        # at all -- where she was born, what he did, where they went to
        # school. Each is an event with a date of its own in the schema, so
        # "carpenter, from 1911" stays sayable later; today the app writes
        # the description and leaves the date blank rather than inventing
        # one.
        for typ in ("occupation", "education"):
            if typ in body:
                set_event(e, pid, typ, "", desc=body[typ])
        changes = {}
        if "sex" in body and body["sex"] in ("M", "F", "X", "U"):
            changes["sex"] = body["sex"]
        if "notes" in body:
            changes["notes"] = body["notes"]
        if changes:
            e.update("person", {"id": pid}, changes)
    return {"ok": True, "id": pid, "warnings": warnings_for(con, pid)}


#: What can sensibly be set on many people at once. Deliberately short.
#: A birth date is a fact about one person and setting it on forty is
#: always wrong; a surname spelling, a place, a confidence level or a tag
#: is a correction that genuinely applies to a whole branch at once.
BULK_FIELDS = [
    ("surname", "Surname"),
    ("birth_place", "Born in"),
    ("death_place", "Died in"),
    ("occupation", "Occupation"),
    ("sex", "Recorded as"),
    ("confidence", "How sure you are"),
    ("living", "Living or dead"),
    ("tag", "Tag"),
]

#: How each one reads back once it is done. "Born in set on 5 people" is what
#: a template gets you and it is not English.
_BULK_SAID = {
    "surname": "Surname changed on",
    "birth_place": "Birthplace set on",
    "death_place": "Place of death set on",
    "occupation": "Occupation set on",
    "sex": "Recorded-as set on",
    "confidence": "Confidence set on",
    "living": "Living or dead set on",
    "tag": "Tagged",
}


def bulk_edit(con, body: dict) -> dict:
    """POST /api/person/bulk. One field, several people, one Ctrl-Z.

    WHY THIS EXISTS. A census page gives forty people the same parish and a
    transcription gives a whole branch the same misspelt surname, and doing
    either one person at a time is forty dialogues and forty undo steps. It
    is also the point at which somebody gives up and edits the database.

    ONE `Edit`, so the whole thing is one entry in the history and one
    Ctrl-Z takes all of it back -- not forty presses, thirty-nine of which
    leave the file half corrected.

    It refuses rather than guesses. An unknown field, an empty list of
    people, or a field that only makes sense on one person is an error that
    says what to do instead.
    """
    field = (body.get("field") or "").strip()
    ids = [x for x in (body.get("ids") or []) if x]
    value = body.get("value")
    known = dict(BULK_FIELDS)
    if field not in known:
        raise ValueError(
            f"'{field}' cannot be set on several people at once. These can: "
            + ", ".join(f"{lab.lower()} ({k})" for k, lab in BULK_FIELDS)
            + ". Anything else is a fact about one person — open them and "
              "edit it there.")
    if not ids:
        raise ValueError("Nobody was chosen. Tick the people to change first.")
    if value is None:
        raise ValueError(f"No value was given for {known[field].lower()}.")

    live = {r["id"] for r in con.execute(
        "SELECT id FROM person WHERE id IN (%s)"
        % ",".join("?" * len(ids)), ids)}
    missing = [x for x in ids if x not in live]
    ids = [x for x in ids if x in live]
    if not ids:
        raise ValueError("None of those people are in this file any more.")

    said = _BULK_SAID.get(field, f"{known[field]} set on")
    label = f"{said} {len(ids)} {'person' if len(ids) == 1 else 'people'}"
    done, skipped = [], []
    with Edit(con, label) as e:
        for pid in ids:
            if field == "surname":
                r = con.execute("SELECT id,given FROM person_name WHERE "
                                "person_id=? AND is_primary=1 LIMIT 1",
                                (pid,)).fetchone()
                sur = str(value).strip()
                if r:
                    e.update("person_name", {"id": r["id"]},
                             {"surname": sur,
                              "sort_key": f"{sur.upper()}, {r['given'] or ''}"})
                else:
                    e.insert("person_name",
                             {"id": new_id(), "person_id": pid, "type": "birth",
                              "is_primary": 1, "given": "", "surname": sur,
                              "sort_key": f"{sur.upper()}, "})
            elif field in ("birth_place", "death_place"):
                # The date is NOT passed, so `set_event` leaves whatever is
                # recorded alone. Sending "" here wiped the birth date beside
                # the place once already; rule 10 is not a style preference.
                set_event(e, pid, field.split("_")[0], None, str(value).strip())
            elif field == "occupation":
                set_event(e, pid, "occupation", "", desc=str(value).strip())
            elif field == "sex":
                if value not in ("M", "F", "X", "U"):
                    raise ValueError(
                        "Recorded as must be M, F, X or U (U is 'not "
                        "recorded').")
                e.update("person", {"id": pid}, {"sex": value})
            elif field == "confidence":
                try:
                    n = int(value)
                except (TypeError, ValueError):
                    n = -1
                if not 0 <= n <= 3:
                    raise ValueError(
                        "How sure you are runs from 0 (a guess) to 3 (seen "
                        "the record).")
                e.update("person", {"id": pid}, {"confidence": n})
            elif field == "living":
                e.update("person", {"id": pid},
                         {"living": 1 if value in (True, 1, "1", "yes") else 0})
            elif field == "tag":
                name = str(value).strip()
                if not name:
                    raise ValueError("A tag needs a word.")
                t = con.execute("SELECT id FROM tag WHERE name=? LIMIT 1",
                                (name,)).fetchone()
                tid = t["id"] if t else new_id()
                if not t:
                    e.insert("tag", {"id": tid, "name": name})
                if con.execute("SELECT 1 FROM person_tag WHERE person_id=? "
                               "AND tag_id=?", (pid, tid)).fetchone():
                    skipped.append(pid)
                    continue
                e.insert("person_tag", {"person_id": pid, "tag_id": tid})
            done.append(pid)

    if done:
        msg = (f"{said} {len(done)} "
               f"{'person' if len(done) == 1 else 'people'}. "
               f"Ctrl-Z takes the whole change back.")
    else:
        # NOTHING HAPPENED, so do not promise an undo that has nothing to
        # take back. The commonest way here is running the same tag twice.
        msg = "Nothing to change — they all had that already."
    if skipped and done:
        msg += f" {len(skipped)} already had it."
    if missing:
        msg += (f" {len(missing)} could not be found and "
                f"{'was' if len(missing) == 1 else 'were'} left alone.")
    return {"ok": True, "changed": len(done), "skipped": len(skipped),
            "missing": len(missing), "message": msg}


def set_heritage(con, body: dict) -> dict:
    """POST /api/person/heritage. Where this person's family came from.

    A whole list at a time, because that is how somebody thinks about it --
    "she was half Irish and half Scottish" is one statement, not two. Shares
    are normalised only when they overshoot: somebody who says "Irish" and
    nothing else means all of it, and somebody who says "Irish 50" means
    half and does not want the other half invented for them.
    """
    pid = body["id"]
    want: dict[str, float] = {}
    for row in body.get("heritage") or []:
        label = (row.get("label") or "").strip()
        if not label:
            continue
        try:
            share = float(row.get("share", 1.0))
        except (TypeError, ValueError):
            share = 1.0
        want[label] = max(0.0, min(1.0, share))
    if want and not body.get("shares_given"):
        each = 1.0 / len(want)
        want = {k: each for k in want}
    total = sum(want.values())
    if total > 1.0001:
        want = {k: v / total for k, v in want.items()}

    with Edit(con, f"Set heritage for {display_name(con, pid)}") as e:
        have = {r["label"]: r["share"] for r in con.execute(
            "SELECT label, share FROM person_heritage WHERE person_id=?", (pid,))}
        for label in have:
            if label not in want:
                e.delete("person_heritage", {"person_id": pid, "label": label})
        for label, share in want.items():
            if label in have:
                if abs(have[label] - share) > 1e-9:
                    e.update("person_heritage",
                             {"person_id": pid, "label": label},
                             {"share": share})
            else:
                e.insert("person_heritage", {"person_id": pid, "label": label,
                                             "share": share})
    return {"ok": True, "id": pid}


def retire(con, pid: str) -> dict:
    """"Remove from tree". Marks the person inactive and takes their links
    off. Never a SQL DELETE -- see this module's docstring."""
    name = display_name(con, pid)
    with Edit(con, f"Remove {name} from the tree") as e:
        e.update("person", {"id": pid}, {"active": 0})
        for r in con.execute("SELECT union_id FROM union_partner WHERE person_id=?",
                             (pid,)).fetchall():
            e.delete("union_partner", {"union_id": r["union_id"], "person_id": pid})
        for r in con.execute("SELECT union_id FROM union_child WHERE person_id=?",
                             (pid,)).fetchall():
            e.delete("union_child", {"union_id": r["union_id"], "person_id": pid})
    return {"ok": True, "id": pid, "message": f"{name} is off the chart. "
            f"Nothing was deleted -- press Ctrl-Z to put them back."}


def merge(con, body: dict) -> dict:
    """POST /api/person/merge. Two records, one person.

    The commonest thing that goes wrong in a family file, and now the
    commonest thing that goes wrong the moment you import somebody else's
    tree: the great-grandmother you already had arrives again under a
    different spelling.

    KEEP is the record that survives; GONE is folded into it and retired.
    Nothing is deleted -- `retire` semantics, so one Ctrl-Z puts both back
    exactly as they were, and the row for the person who was merged away is
    still in the file with everything that was ever known about them.

    THE SURVIVOR NEVER LOSES A FACT. A blank field on KEEP takes GONE's
    value; a field they both have keeps KEEP's and puts GONE's into the
    notes, because the whole reason two records exist is that somebody
    recorded two different things and the disagreement is evidence.
    """
    keep, gone = body["keep"], body["gone"]
    if keep == gone:
        raise ValueError("That is the same person twice.")
    kn, gn = display_name(con, keep), display_name(con, gone)

    with Edit(con, f"Merge {gn} into {kn}") as e:
        krow = _read(con, "person", {"id": keep}) or {}
        grow = _read(con, "person", {"id": gone}) or {}

        # -- the facts. An event type the survivor has no row for moves
        #    across; one they both have leaves a note saying what the other
        #    record said, because two dates for one birth is a conflict to
        #    resolve later and not something to throw away today.
        have = {r["type"] for r in con.execute(
            "SELECT DISTINCT e.type FROM event e "
            "JOIN event_role r ON r.event_id=e.id WHERE r.person_id=?", (keep,))}
        carried, conflicts = [], []
        for r in con.execute(
                "SELECT e.id, e.type, e.date_json, e.description, pl.name place "
                "FROM event e JOIN event_role r ON r.event_id=e.id "
                "LEFT JOIN place pl ON pl.id=e.place_id "
                "WHERE r.person_id=?", (gone,)).fetchall():
            if r["type"] not in have:
                e.update("event_role",
                         {"event_id": r["id"], "person_id": gone,
                          "union_id": None, "role": "principal"},
                         {"person_id": keep})
                carried.append(r["type"])
                have.add(r["type"])
            else:
                from ..model.gendate import GenDate
                d = GenDate.from_json(r["date_json"])
                said = " ".join(x for x in [d.display, r["place"] or "",
                                            r["description"] or ""] if x)
                if said.strip():
                    conflicts.append(f"{r['type']}: {said.strip()}")

        # -- the links. A union either record was in becomes the survivor's.
        for tbl in ("union_partner", "union_child"):
            for r in con.execute(f"SELECT * FROM {tbl} WHERE person_id=?",
                                 (gone,)).fetchall():
                exists = con.execute(
                    f"SELECT 1 FROM {tbl} WHERE union_id=? AND person_id=?",
                    (r["union_id"], keep)).fetchone()
                e.delete(tbl, {"union_id": r["union_id"], "person_id": gone})
                if not exists:
                    row = dict(r)
                    row["person_id"] = keep
                    e.insert(tbl, row)

        # -- photographs, heritage and tags come across too
        for r in con.execute("SELECT * FROM media_link WHERE person_id=?",
                             (gone,)).fetchall():
            e.delete("media_link", {"media_id": r["media_id"],
                                    "person_id": gone,
                                    "event_id": r["event_id"]})
            if not con.execute("SELECT 1 FROM media_link WHERE media_id=? "
                               "AND person_id=? AND event_id IS ?",
                               (r["media_id"], keep, r["event_id"])).fetchone():
                row = dict(r)
                row["person_id"] = keep
                # only one portrait, and the survivor's own wins
                if row.get("is_portrait") and con.execute(
                        "SELECT 1 FROM media_link WHERE person_id=? "
                        "AND is_portrait=1", (keep,)).fetchone():
                    row["is_portrait"] = 0
                e.insert("media_link", row)
        try:
            for r in con.execute("SELECT * FROM person_heritage WHERE person_id=?",
                                 (gone,)).fetchall():
                e.delete("person_heritage", {"person_id": gone,
                                             "label": r["label"]})
                if not con.execute("SELECT 1 FROM person_heritage WHERE "
                                   "person_id=? AND label=?",
                                   (keep, r["label"])).fetchone():
                    e.insert("person_heritage", {"person_id": keep,
                                                 "label": r["label"],
                                                 "share": r["share"]})
        except Exception:
            pass

        # -- the name. Kept as an also-known-as rather than dropped: the
        #    other spelling is what a record office index will have.
        gname = con.execute("SELECT * FROM person_name WHERE person_id=? "
                            "AND is_primary=1 LIMIT 1", (gone,)).fetchone()
        if gname and gn != kn:
            e.insert("person_name", {
                "id": new_id(), "person_id": keep, "type": "also_known_as",
                "is_primary": 0, "given": gname["given"],
                "surname": gname["surname"],
                "sort_key": f"{(gname['surname'] or '~').upper()}, "
                            f"{gname['given'] or ''}"})

        # -- what only the other record knew
        changes = {}
        if not (krow.get("notes") or "").strip() and (grow.get("notes") or "").strip():
            changes["notes"] = grow["notes"]
        elif (grow.get("notes") or "").strip():
            changes["notes"] = (krow["notes"] or "") + \
                f"\n\n[Merged from {gn}] {grow['notes']}"
        if krow.get("sex") in (None, "U") and grow.get("sex") not in (None, "U"):
            changes["sex"] = grow["sex"]
        if conflicts:
            note = changes.get("notes", krow.get("notes") or "")
            changes["notes"] = (note + "\n\n" if note.strip() else "") + \
                f"[Merged from {gn}] The other record said — " + \
                "; ".join(conflicts)
        if changes:
            e.update("person", {"id": keep}, changes)

        e.update("person", {"id": gone}, {"active": 0})

    return {"ok": True, "id": keep, "merged": gone,
            "carried": carried, "conflicts": conflicts,
            "message": f"{gn} and {kn} are now one person" +
                       (f", and {len(conflicts)} thing"
                        f"{'s' if len(conflicts) != 1 else ''} the other "
                        f"record said {'are' if len(conflicts) != 1 else 'is'} "
                        f"in their notes" if conflicts else "") +
                       ". Press Ctrl-Z to undo it."}


def display_name(con, pid: str) -> str:
    r = con.execute("SELECT given,surname FROM person_name WHERE person_id=? "
                    "AND is_primary=1 LIMIT 1", (pid,)).fetchone()
    if not r:
        return "this person"
    return " ".join(x for x in (r["given"], r["surname"]) if x) or "this person"


# ================================================================ the links ===
def _new_union(e: Edit, kind: str = "marriage") -> str:
    """A new family.

    THE DEFAULT IS A MARRIAGE because that is what "add a partner" means to
    the person clicking it. A couple who never married is said so
    deliberately, on the family, and is never guessed at from silence --
    guessing would be a claim about two real people made by a default.
    """
    uid = new_id()
    e.insert("union_", {"id": uid, "type": _union_kind(kind), "active": 1})
    return uid


def _union_kind(kind: str) -> str:
    from ..graph.build import UNION_KIND
    k = (kind or "").strip() or "marriage"
    if k not in UNION_KIND:
        raise ValueError(
            f"'{kind}' is not a kind of family Helix knows. Choose one of: "
            + ", ".join(sorted(UNION_KIND)) + ".")
    return k


def _role_for(con, pid: str) -> str:
    r = con.execute("SELECT sex FROM person WHERE id=?", (pid,)).fetchone()
    return {"M": "husband", "F": "wife"}.get(r["sex"] if r else "U", "partner")


def add_partner(e: Edit, uid: str, pid: str) -> None:
    if _read(e.con, "union_partner", {"union_id": uid, "person_id": pid}):
        return
    seq = e.con.execute("SELECT COUNT(*) n FROM union_partner WHERE union_id=?",
                        (uid,)).fetchone()["n"]
    e.insert("union_partner", {"union_id": uid, "person_id": pid,
                               "role": _role_for(e.con, pid), "seq": seq})


def add_child(e: Edit, uid: str, pid: str, rel: str = "biological") -> None:
    if _read(e.con, "union_child", {"union_id": uid, "person_id": pid}):
        return
    # The layout follows the union marked primary; a second one is a chord.
    has_primary = e.con.execute(
        "SELECT 1 FROM union_child WHERE person_id=? AND is_primary=1",
        (pid,)).fetchone()
    e.insert("union_child", {"union_id": uid, "person_id": pid,
                             "rel_partner1": rel, "rel_partner2": rel,
                             "is_primary": 0 if has_primary else 1})


def parents_union(e: Edit, pid: str) -> str:
    """The union holding this person's parents, created if this is the first
    anyone has heard of them. This is what makes "add my father" a single
    click when the mother is not recorded either."""
    r = e.con.execute("SELECT union_id FROM union_child WHERE person_id=? "
                      "ORDER BY is_primary DESC LIMIT 1", (pid,)).fetchone()
    if r:
        return r["union_id"]
    # SCAFFOLDING, not a claim. Adding "my father" says nothing about
    # whether his parents married, so this one is left unstated.
    uid = _new_union(e, "unknown")
    add_child(e, uid, pid)
    return uid


def _childless_union(e: Edit, pid: str) -> str:
    """A union to hang a child on when no partner has been named. Reuses one
    the person is already the only partner in, so adding two children with
    "the other parent not recorded" does not invent two families."""
    for r in e.con.execute("SELECT union_id FROM union_partner WHERE person_id=?",
                           (pid,)).fetchall():
        n = e.con.execute("SELECT COUNT(*) n FROM union_partner WHERE union_id=?",
                          (r["union_id"],)).fetchone()["n"]
        if n == 1:
            return r["union_id"]
    uid = _new_union(e, "unknown")
    add_partner(e, uid, pid)
    return uid


def attach(e: Edit, pid: str, to: str, how: str,
           union_id: Optional[str] = None) -> str:
    """Wire `pid` to `to` as father / mother / partner / child / sibling.

    The client never reasons about unions; it says "father" and this works
    out that a father is a partner in the union holding the standing person's
    parents, and creates that union if it does not exist yet.
    """
    if how not in ATTACHMENTS:
        raise ValueError(f"Cannot attach somebody as '{how}'. "
                         f"Use one of: {', '.join(ATTACHMENTS)}.")
    if how in ("father", "mother"):
        uid = union_id or parents_union(e, to)
        add_partner(e, uid, pid)
        add_child(e, uid, to)
        return uid
    if how == "partner":
        uid = union_id or _childless_union(e, to)
        add_partner(e, uid, to)
        add_partner(e, uid, pid)
        return uid
    if how == "child":
        uid = union_id or _childless_union(e, to)
        add_partner(e, uid, to)
        add_child(e, uid, pid)
        return uid
    uid = union_id or parents_union(e, to)      # sibling
    add_child(e, uid, pid)
    return uid


_LABEL = {"father": "Add a father", "mother": "Add a mother",
          "partner": "Add a partner", "child": "Add a child",
          "sibling": "Add a brother or sister"}


def add_person(con, body: dict) -> dict:
    """POST /api/person/new. Creates the person and wires them up in one
    undoable step."""
    at = body.get("attach") or {}
    to, how = at.get("to"), at.get("as")
    if to and how:
        label = _LABEL.get(how, "Add a person") + f" for {display_name(con, to)}"
    else:
        label = "Add a person"
    with Edit(con, label) as e:
        pid = create_person(
            e, given=body.get("given", ""), surname=body.get("surname", ""),
            sex=body.get("sex", "U"), birth=body.get("birth", ""),
            death=body.get("death", ""),
            birth_place=body.get("birth_place", ""),
            notes=body.get("notes", ""))
        uid = attach(e, pid, to, how, at.get("union")) if to and how else None
    return {"ok": True, "id": pid, "union_id": uid,
            "warnings": warnings_for(con, pid)}


def link_person(con, body: dict) -> dict:
    """POST /api/person/link. Same wiring, no new person -- this is what
    "Did you mean this person?" does instead of creating a duplicate."""
    at = body.get("attach") or {}
    to, how = at.get("to"), at.get("as")
    pid = body["id"]
    if not (to and how):
        raise ValueError("Say who to link this person to, and how.")
    with Edit(con, f"Link {display_name(con, pid)} as "
                   f"{how} of {display_name(con, to)}") as e:
        uid = attach(e, pid, to, how, at.get("union"))
    return {"ok": True, "id": pid, "union_id": uid,
            "warnings": warnings_for(con, pid)}


def detach(con, body: dict) -> dict:
    """POST /api/person/detach. Takes one link off and keeps the person."""
    pid, uid = body["id"], body["union_id"]
    how = body.get("as", "child")
    tbl = "union_partner" if how == "partner" else "union_child"
    with Edit(con, f"Detach {display_name(con, pid)}") as e:
        e.delete(tbl, {"union_id": uid, "person_id": pid})
    return {"ok": True}


def union_op(con, body: dict) -> dict:
    """POST /api/union. Create a family, or add or remove a partner."""
    action = body.get("action", "create")
    with Edit(con, {"create": "Add a family",
                    "add_partner": "Add a partner",
                    "set_kind": "Change what kind of couple this is",
                    "remove_partner": "Remove a partner"}.get(action, "Edit a family")) as e:
        if action == "create":
            uid = _new_union(e, body.get("kind", "marriage"))
            for p in body.get("partners", []):
                add_partner(e, uid, p)
            return {"ok": True, "union_id": uid}
        uid = body["union_id"]
        if action == "add_partner":
            add_partner(e, uid, body["person_id"])
        elif action == "remove_partner":
            e.delete("union_partner", {"union_id": uid,
                                       "person_id": body["person_id"]})
        elif action == "set_kind":
            # MARRIED OR NOT is a fact about two people, and undoable like
            # every other. Set the wrong one and Ctrl-Z puts it back.
            e.update("union_", {"id": uid},
                     {"type": _union_kind(body.get("kind", "marriage"))})
        else:
            raise ValueError(f"Unknown action '{action}'.")
    return {"ok": True, "union_id": uid}


def union_child_op(con, body: dict) -> dict:
    """POST /api/union/child. Attach or detach a child, with the kind of
    relationship -- adopted and fostered children are ordinary here."""
    uid, pid = body["union_id"], body["person_id"]
    action = body.get("action", "attach")
    with Edit(con, ("Attach" if action == "attach" else "Detach")
              + f" {display_name(con, pid)}") as e:
        if action == "attach":
            add_child(e, uid, pid, body.get("rel", "biological"))
        elif action == "detach":
            e.delete("union_child", {"union_id": uid, "person_id": pid})
        else:
            raise ValueError(f"Unknown action '{action}'.")
    return {"ok": True}


# ================================================== soft validation & search ==
def warnings_for(con, pid: str) -> list[str]:
    """Things worth mentioning, never things worth refusing. Compares
    INTERVALS, not midpoints: a child born "1741" to a parent born "1741" is
    only impossible if it is impossible for every date in both."""
    from ..graph import build as gbuild
    out: list[str] = []
    g = gbuild.load(con)
    p = g.people.get(pid)
    if not p:
        return out
    for par in g.parents(pid, primary_only=False):
        q = g.people.get(par)
        if not q or not (p.birth.known and q.birth.known):
            continue
        if p.birth.latest and q.birth.earliest and p.birth.latest < q.birth.earliest:
            out.append(f"{p.full_name} would have been born before "
                       f"{q.full_name}. Check the dates?")
    for kid in g.children(pid):
        q = g.people.get(kid)
        if not q or not (p.birth.known and q.birth.known):
            continue
        if q.birth.latest and p.birth.earliest and q.birth.latest < p.birth.earliest:
            out.append(f"{q.full_name} would have been born before "
                       f"{p.full_name}. Check the dates?")
    if p.birth.known and p.death.known and p.death.latest and p.birth.earliest \
            and p.death.latest < p.birth.earliest:
        out.append(f"{p.full_name} would have died before they were born. "
                   f"Check the dates?")
    return out


def search(con, q: str, *, limit: int = 8, exclude: str = "") -> list[dict]:
    """Name match, for the duplicate check on the add dialogue. Duplicate
    people are the commonest way a tree goes wrong, so this runs while you
    type rather than after you save."""
    q = (q or "").strip().lower()
    if not q:
        return []
    rows = con.execute(
        "SELECT n.person_id id, n.given, n.surname FROM person_name n "
        "JOIN person p ON p.id=n.person_id "
        "WHERE n.is_primary=1 AND p.active=1").fetchall()
    # A shared surname is not a duplicate. Scoring the whole string alone
    # offered "James Pargeter" to somebody adding his sister Claire, because
    # the surname is most of the characters -- and a wrong "link to them
    # instead" is worse than no suggestion at all. So the given name has to
    # agree too, unless the whole thing is nearly identical.
    qgiven = q.split()[0] if q.split() else q
    scored = []
    for r in rows:
        if r["id"] == exclude:
            continue
        name = " ".join(x for x in (r["given"], r["surname"]) if x)
        low = name.lower()
        if not low:
            continue
        whole = difflib.SequenceMatcher(None, q, low).ratio()
        given = max((difflib.SequenceMatcher(None, qgiven, tok).ratio()
                     for tok in low.split()), default=0.0)
        score = max(whole, 0.9 if q in low else 0.0)
        if score >= 0.85 or (score >= 0.6 and given >= 0.7):
            scored.append((score, r["id"], name))
    scored.sort(key=lambda t: (-t[0], t[2]))
    out = []
    from ..graph import build as gbuild
    g = gbuild.load(con) if scored else None
    for score, pid, name in scored[:limit]:
        p = g.people.get(pid)
        out.append({"id": pid, "name": name,
                    "life": p.lifespan if p else "",
                    "score": round(score, 3)})
    return out
