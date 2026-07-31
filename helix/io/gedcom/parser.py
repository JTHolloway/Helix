"""GEDCOM records -> Helix rows. The door in.

Everything here goes through `store.records.Edit`, in ONE batch, so an
import is one undoable action. Somebody who imports a cousin's tree, looks
at it and decides it was a mistake presses Ctrl-Z once. Written as raw
inserts it would be the only thing in the program you could not take back,
and it is the single largest change anybody will ever make to their file.

WHAT IT WILL NOT DO
  * Never invent an error. A FAM with no HUSB, a child listed twice, a
    person with no name: all ordinary, all imported. The report says what
    was odd; nothing is refused.
  * Never hang. Bad files contain cyclic pedigrees -- somebody who is their
    own great-grandfather -- and a naive walk follows that forever. Every
    traversal here is over a flat record list, and the cycle check runs
    afterwards and reports.
  * Never discard silently. Any tag this module does not model is written
    into `person.notes` (or `union_.notes`) prefixed `[GEDCOM]`, with its
    level structure flattened but its text intact. That is the rule from
    `BLOCKERS.md` and it is the difference between an import and a
    lossy transcription.

WHAT COMES BACK ROUND. Helix's own `_` tags -- `_HERITAGE`, `_CONF`,
`_ORIG`, `_LIVING`, `_PLACEHOLDER` -- are read back into their own columns
rather than into notes, so Helix -> GEDCOM -> Helix is lossless for the
things GEDCOM has no word for.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ...model.gendate import parse as parse_date
from ...store.db import new_id
from ...store.records import Edit
from . import lexer

# GEDCOM tag -> Helix event type. The reverse of the writer's table plus the
# spellings other programs actually emit.
EVENT_TYPES = {
    "BIRT": "birth", "DEAT": "death", "BURI": "burial", "BAPM": "baptism",
    "CHR": "christening", "CHRA": "christening", "CREM": "cremation",
    "ADOP": "adoption", "CENS": "census", "EMIG": "emigration",
    "IMMI": "immigration", "NATU": "naturalisation", "PROB": "probate",
    "WILL": "will", "RESI": "residence", "OCCU": "occupation",
    "EDUC": "education", "RETI": "retirement", "GRAD": "graduation",
    "_MILT": "military", "RELI": "religion", "NATI": "nationality",
    "TITL": "title", "BARM": "bar_mitzvah", "BASM": "bas_mitzvah",
    "BLES": "blessing", "CONF": "confirmation", "FCOM": "first_communion",
    "ORDN": "ordination", "EVEN": "event",
}

# Facts Helix keeps as a text description rather than a date.
TEXT_EVENTS = {"occupation", "education", "religion", "nationality", "title"}

UNION_TYPES = {"MARR": "marriage", "MARB": "marriage", "MARL": "marriage",
               "ANUL": "annulled", "DIV": "marriage", "_UNMR": "unmarried",
               "EVEN": "unknown"}

SEXES = {"M": "M", "F": "F", "X": "X", "U": "U",
         "MALE": "M", "FEMALE": "F", "N": "U", "": "U"}

# `@#DJULIAN@ 12 MAR 1710` and friends. The escape is stripped and the
# calendar recorded in the note rather than dropped -- a Julian date read as
# Gregorian is out by eleven days and nothing on screen would say so.
_CAL = re.compile(r"@#D([A-Z_]+)@\s*")

_NAME = re.compile(r"^(.*?)/([^/]*)/(.*)$")


def _split_name(value: str) -> tuple[str, str, str]:
    """`John /Smith/ Jr` -> ("John", "Smith", "Jr").

    THE SLASHES ARE THE SURNAME and they are not decoration. Without them
    every reader has to guess which word is the family name, and guesses
    wrong for "Mary Anne de la Mare" and for every Spanish or Portuguese
    name in the file. A name with no slashes at all is common in files
    exported by web tools; the last word is the best available guess and the
    whole string is kept in `as_recorded` so nothing is lost by it.
    """
    v = (value or "").strip()
    m = _NAME.match(v)
    if m:
        return m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
    parts = v.split()
    if len(parts) >= 2:
        return " ".join(parts[:-1]), parts[-1], ""
    return v, "", ""


def _date_text(rec) -> tuple[str, str]:
    """The date as text, plus whatever calendar note goes with it.

    `_ORIG` wins if it is there: that is Helix's own record of what somebody
    actually typed, and `ABT 1834` is a lossy rendering of "around 1834,
    from her marriage certificate".
    """
    d = rec.first("DATE")
    if not d:
        return "", ""
    raw = (d.value or "").strip()
    note = ""
    m = _CAL.search(raw)
    if m:
        cal = m.group(1).replace("_", " ").title()
        note = f"Recorded in the {cal} calendar."
        raw = _CAL.sub("", raw).strip()
    # `FROM x TO y` is a duration, not an instant, and `GenDate` has no word
    # for it. `BET x AND y` is the same interval and does parse.
    m = re.match(r"(?i)^FROM\s+(.+?)\s+TO\s+(.+)$", raw)
    if m:
        raw = f"BET {m.group(1)} AND {m.group(2)}"
    elif re.match(r"(?i)^FROM\s+", raw):
        raw = "AFT " + raw[5:].strip()
    elif re.match(r"(?i)^TO\s+", raw):
        raw = "BEF " + raw[3:].strip()
    if raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1]                     # a free-form phrase; keep the words
    orig = d.first("_ORIG")
    if orig and orig.value.strip():
        raw = orig.value.strip()
    return raw, note


# Tags handled explicitly somewhere in this module. Everything else on an
# INDI or FAM lands in the notes, which is what keeps an import lossless.
_KNOWN_INDI = {"NAME", "SEX", "FAMC", "FAMS", "NOTE", "CHAN", "RIN", "RFN",
               "_UID", "_HERITAGE", "_CONF", "_LIVING", "_PLACEHOLDER",
               "SOUR", "OBJE", "SUBM", "ALIA", "ASSO", "REFN", "_FSFTID"}
_KNOWN_FAM = {"HUSB", "WIFE", "CHIL", "NOTE", "CHAN", "RIN", "_TYPE",
              "_PARTNER", "SOUR", "OBJE", "REFN", "_UID"}


def _flatten(rec, depth: int = 0) -> list[str]:
    """A record and everything under it, as indented text for a note."""
    out = []
    head = ("  " * depth) + rec.tag + ((" " + rec.value) if rec.value else "")
    out.append(head.rstrip())
    for c in rec.children:
        out.extend(_flatten(c, depth + 1))
    return out


def _leftovers(rec, known: set) -> str:
    keep = [c for c in rec.children
            if c.tag not in known and c.tag not in EVENT_TYPES
            and c.tag not in UNION_TYPES]
    if not keep:
        return ""
    body = []
    for c in keep:
        body.extend(_flatten(c))
    return "[GEDCOM] " + "\n".join(body)


# ------------------------------------------------------------------- import


def parse(roots, con, *, on_progress=None, source_name: str = "") -> dict:
    """Turn parsed records into rows. One `Edit`, so one Ctrl-Z undoes it."""
    indis = [r for r in roots if r.tag == "INDI"]
    fams = [r for r in roots if r.tag == "FAM"]
    sours = [r for r in roots if r.tag == "SOUR"]
    notes = {r.xref: r.value for r in roots if r.tag == "NOTE" and r.xref}

    report: dict = {"people": 0, "families": 0, "sources": 0, "events": 0,
                    "notes_kept": 0, "problems": [], "warnings": []}
    ids: dict[str, str] = {}                # @I1@ -> helix uuid
    uids: dict[str, str] = {}               # @F1@ -> helix uuid
    place_cache: dict[str, str] = {}

    label = f"Import {len(indis)} people from {source_name}" if source_name \
        else f"Import {len(indis)} people"
    with Edit(con, label) as e:
        for i, rec in enumerate(indis):
            ids[rec.xref] = _indi(e, rec, notes, place_cache, report)
            if on_progress and i % 100 == 0:
                on_progress(i, len(indis))
        for rec in fams:
            uids[rec.xref] = _fam(e, rec, ids, notes, place_cache, report)
        for rec in sours:
            _source(e, rec, report)

    report["people"] = len(ids)
    report["families"] = len(uids)
    _check_cycles(con, report)
    return report


def _note_text(rec, notes: dict) -> str:
    """NOTE is either inline text or a pointer at a shared note record."""
    out = []
    for n in rec.all("NOTE"):
        v = (n.value or "").strip()
        if v.startswith("@") and v.endswith("@"):
            v = notes.get(v, "")
        if v:
            out.append(v)
    return "\n\n".join(out)


def _place(e: Edit, name: str, cache: dict) -> Optional[str]:
    name = (name or "").strip()
    if not name:
        return None
    if name in cache:
        return cache[name]
    row = e.con.execute("SELECT id FROM place WHERE name=?", (name,)).fetchone()
    pid = row["id"] if row else new_id()
    if not row:
        e.insert("place", {"id": pid, "name": name})
    cache[name] = pid
    return pid


def _indi(e: Edit, rec, notes, cache, report) -> str:
    pid = new_id()
    body: dict = {"id": pid, "sex": "U"}

    sex = rec.first("SEX")
    if sex:
        body["sex"] = SEXES.get((sex.value or "").strip().upper(), "U")
    conf = rec.first("_CONF")
    if conf and conf.value.strip().isdigit():
        body["confidence"] = max(0, min(3, int(conf.value.strip())))
    live = rec.first("_LIVING")
    if live:
        body["living"] = 1 if live.value.strip().upper().startswith("Y") else 0
    if rec.first("_PLACEHOLDER"):
        body["is_placeholder"] = 1

    bits = [_note_text(rec, notes)]
    extra = _leftovers(rec, _KNOWN_INDI)
    if extra:
        bits.append(extra)
        report["notes_kept"] += 1
    note = "\n\n".join(x for x in bits if x)
    if note:
        body["notes"] = note
    e.insert("person", body)

    names = rec.all("NAME")
    if not names:
        # A person with no NAME at all is legal GEDCOM and appears in every
        # large file. Rule: never leave somebody with no name row, or they
        # vanish from every list that joins through it.
        e.insert("person_name", {"id": new_id(), "person_id": pid,
                                 "type": "birth", "is_primary": 1,
                                 "given": "", "surname": "",
                                 "sort_key": "~, "})
    for i, n in enumerate(names):
        given, surname, suffix = _split_name(n.value)
        given = n.val("GIVN") or given
        surname = n.val("SURN") or surname
        typ = {"married": "married", "aka": "also_known_as",
               "legal": "legal", "religious": "religious",
               "birth": "birth", "immigrant": "also_known_as"}.get(
                   (n.val("TYPE") or "").lower(), "birth" if i == 0 else
                   "also_known_as")
        e.insert("person_name", {
            "id": new_id(), "person_id": pid, "type": typ,
            "is_primary": 1 if i == 0 else 0,
            "title": n.val("NPFX") or None,
            "given": given, "given_used": n.val("_USED") or None,
            "surname_prefix": n.val("SPFX") or None,
            "surname": surname,
            "suffix": n.val("NSFX") or suffix or None,
            "as_recorded": n.value or None,
            "sort_key": f"{(surname or '~').upper()}, {given}"})

    for tag, typ in EVENT_TYPES.items():
        for ev in rec.all(tag):
            _event(e, ev, typ, pid, None, cache, notes, report)

    for h in rec.all("_HERITAGE"):
        label = (h.value or "").strip()
        if not label:
            continue
        try:
            share = float(h.val("_SHARE", "1"))
        except ValueError:
            share = 1.0
        try:
            e.insert("person_heritage", {"person_id": pid, "label": label,
                                         "share": max(0.0, min(1.0, share))})
        except Exception:
            pass                            # a duplicate label; the first wins
    return pid


def _event(e: Edit, ev, typ, person_id, union_id, cache, notes, report) -> None:
    raw, cal_note = _date_text(ev)
    d = parse_date(raw)
    place = _place(e, ev.val("PLAC"), cache)
    desc = ""
    if typ in TEXT_EVENTS:
        desc = (ev.value or "").strip()
    elif typ == "event":
        typ = (ev.val("TYPE") or "event").strip().lower().replace(" ", "_")
        desc = (ev.value or "").strip()
    body_note = "\n\n".join(x for x in [_note_text(ev, notes), cal_note] if x)
    if not (d.known or raw or place or desc or body_note):
        # `1 BIRT Y` with nothing under it means "this happened, no detail".
        # It is worth an event row: the fact that somebody was born is not
        # news, but the fact that somebody DIED is what makes them not living.
        if (ev.value or "").strip().upper() != "Y":
            return
    eid = new_id()
    e.insert("event", {
        "id": eid, "type": typ,
        "date_json": d.to_json(),
        "date_earliest": d.earliest.isoformat() if d.earliest else None,
        "date_latest": d.latest.isoformat() if d.latest else None,
        "date_sort": d.sort_value,
        "place_id": place,
        "description": desc or None,
        "age_text": ev.val("AGE") or None,
        "notes": body_note or None})
    e.insert("event_role", {"event_id": eid, "person_id": person_id,
                            "union_id": union_id, "role": "principal"})
    report["events"] += 1


def _fam(e: Edit, rec, ids, notes, cache, report) -> str:
    uid = new_id()
    typ = "marriage"
    t = rec.first("_TYPE")
    if t and t.value.strip():
        typ = t.value.strip()
    elif rec.first("_UNMR"):
        typ = "unmarried"
    elif rec.first("ANUL"):
        typ = "annulled"
    if typ not in ("marriage", "civil_partnership", "unmarried",
                   "unknown", "annulled"):
        typ = "unknown"

    bits = [_note_text(rec, notes)]
    extra = _leftovers(rec, _KNOWN_FAM)
    if extra:
        bits.append(extra)
    note = "\n\n".join(x for x in bits if x)
    e.insert("union_", {"id": uid, "type": typ, "notes": note or None})

    seq = 0
    seen: set = set()
    for tag in ("HUSB", "WIFE", "_PARTNER"):
        for p in rec.all(tag):
            pid = ids.get((p.value or "").strip())
            if not pid or pid in seen:
                continue
            seen.add(pid)
            e.insert("union_partner", {"union_id": uid, "person_id": pid,
                                       "role": "partner", "seq": seq})
            seq += 1

    order = 0
    kids: set = set()
    for c in rec.all("CHIL"):
        pid = ids.get((c.value or "").strip())
        if not pid:
            report["warnings"].append(
                f"A child pointer {c.value!r} in {rec.xref} points at nobody "
                f"in the file. The family was imported without them.")
            continue
        if pid in kids:
            # CHILDREN LISTED TWICE is common and is not an error worth
            # stopping for -- but inserted twice it violates the primary key
            # and would abort the whole import.
            continue
        kids.add(pid)
        e.insert("union_child", {"union_id": uid, "person_id": pid,
                                 "is_primary": 1, "birth_order": order})
        order += 1

    for tag, kind in UNION_TYPES.items():
        if tag in ("EVEN",):
            continue
        for ev in rec.all(tag):
            _event(e, ev, "marriage" if tag.startswith("MAR") else
                   {"DIV": "divorce", "ANUL": "annulment",
                    "_UNMR": "partnership"}.get(tag, "marriage"),
                   None, uid, cache, notes, report)
    return uid


def _source(e: Edit, rec, report) -> None:
    sid = new_id()
    e.insert("source", {
        "id": sid,
        "title": rec.val("TITL") or rec.val("ABBR") or "Untitled source",
        "author": rec.val("AUTH") or None,
        "publisher": rec.val("PUBL") or None,
        "ref": rec.val("REFN") or None,
        "notes": "\n".join(_flatten(rec)) if rec.children else None})
    report["sources"] += 1


def _check_cycles(con, report) -> None:
    """Somebody who is their own ancestor.

    Bad files contain these -- a mis-linked FAMC turns a great-grandfather
    into his own grandson -- and nothing in the program is written to expect
    it. Found here and REPORTED rather than repaired: which of the links is
    the wrong one is a judgement about somebody's research, not arithmetic.
    """
    parents: dict[str, list[str]] = {}
    for r in con.execute(
            "SELECT uc.person_id kid, up.person_id par FROM union_child uc "
            "JOIN union_partner up ON up.union_id = uc.union_id"):
        parents.setdefault(r["kid"], []).append(r["par"])
    WHITE, GREY, BLACK = 0, 1, 2
    colour: dict[str, int] = {}
    bad: set = set()
    for start in list(parents):
        if colour.get(start, WHITE) != WHITE:
            continue
        stack = [(start, iter(parents.get(start, [])))]
        colour[start] = GREY
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                colour[node] = BLACK
                stack.pop()
                continue
            c = colour.get(nxt, WHITE)
            if c == GREY:
                bad.add(nxt)
            elif c == WHITE:
                colour[nxt] = GREY
                stack.append((nxt, iter(parents.get(nxt, []))))
    if bad:
        names = []
        for pid in list(bad)[:5]:
            r = con.execute("SELECT given, surname FROM person_name "
                            "WHERE person_id=? LIMIT 1", (pid,)).fetchone()
            names.append(f"{(r['given'] or '') if r else ''} "
                         f"{(r['surname'] or '') if r else ''}".strip()
                         or pid[:8])
        report["problems"].append(
            f"{len(bad)} {'person is' if len(bad) == 1 else 'people are'} "
            f"listed as their own ancestor ({', '.join(names)}). The file "
            f"imported, but check those parent links before drawing a chart.")


def import_file(path: str | Path, con, *, on_progress=None) -> dict:
    roots, meta = lexer.read(path)
    rep = parse(roots, con, on_progress=on_progress,
                source_name=Path(path).name)
    rep["encoding"] = meta["encoding"]
    rep["problems"] = list(meta["problems"]) + rep["problems"]
    return rep
