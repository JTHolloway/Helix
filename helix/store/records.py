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


def display_name(con, pid: str) -> str:
    r = con.execute("SELECT given,surname FROM person_name WHERE person_id=? "
                    "AND is_primary=1 LIMIT 1", (pid,)).fetchone()
    if not r:
        return "this person"
    return " ".join(x for x in (r["given"], r["surname"]) if x) or "this person"


# ================================================================ the links ===
def _new_union(e: Edit) -> str:
    uid = new_id()
    e.insert("union_", {"id": uid, "type": "unknown", "active": 1})
    return uid


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
    uid = _new_union(e)
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
    uid = _new_union(e)
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
                    "remove_partner": "Remove a partner"}.get(action, "Edit a family")) as e:
        if action == "create":
            uid = _new_union(e)
            for p in body.get("partners", []):
                add_partner(e, uid, p)
            return {"ok": True, "union_id": uid}
        uid = body["union_id"]
        if action == "add_partner":
            add_partner(e, uid, body["person_id"])
        elif action == "remove_partner":
            e.delete("union_partner", {"union_id": uid,
                                       "person_id": body["person_id"]})
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
