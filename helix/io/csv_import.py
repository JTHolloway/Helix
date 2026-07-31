"""Spreadsheet import -- the realistic first step for most people.

Almost everyone starts with a spreadsheet from a relative. This importer is
deliberately tolerant: it guesses columns, reports what it guessed, and lets
the user correct the mapping before anything is written.

EXPECTED (all optional except a name)
  id, given, surname, sex, birth_date, birth_place, death_date, death_place,
  occupation, education, father_id, mother_id, spouse_id, marriage_date, notes

BEHAVIOUR
  * Header matching is fuzzy and case-insensitive: "DOB", "Born", "birth
    date", "b." all map to birth_date.
  * Rows referencing an unknown father_id create a PLACEHOLDER person rather
    than failing, so a partial spreadsheet still imports.
  * Every date goes through model.gendate.parse, so "abt 1834" survives.
  * A dry run reports counts and problems and writes nothing.
"""
from __future__ import annotations

import csv
from pathlib import Path

ALIASES = {
    "given": ["given", "first", "forename", "firstname", "first name", "christian"],
    "surname": ["surname", "last", "lastname", "last name", "family name"],
    "sex": ["sex", "gender", "m/f"],
    "birth_date": ["birth", "birth date", "born", "dob", "b", "date of birth"],
    "birth_place": ["birth place", "birthplace", "born in", "pob"],
    "death_date": ["death", "death date", "died", "dod", "d"],
    "death_place": ["death place", "deathplace", "died in"],
    "occupation": ["occupation", "job", "trade", "profession"],
    "education": ["education", "school", "university"],
    "father_id": ["father", "father id", "fatherid", "dad"],
    "mother_id": ["mother", "mother id", "motherid", "mum", "mom"],
    "spouse_id": ["spouse", "spouse id", "husband", "wife", "partner"],
    "marriage_date": ["marriage", "married", "marriage date"],
    "notes": ["notes", "note", "comment", "comments"],
    "id": ["id", "ref", "key", "person id", "#"],
}


def guess_mapping(header: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for col in header:
        k = col.strip().lower().replace("_", " ")
        for field, names in ALIASES.items():
            if k in names and field not in out.values():
                out[col] = field
                break
    return out


def sniff_rows(path: str | Path) -> tuple[list[str], list[dict]]:
    """Header and rows, with the delimiter and encoding worked out.

    A spreadsheet from a relative arrives as a tab-separated file called
    `.csv`, as a semicolon-separated file from a European Excel, and as
    UTF-8 with a byte-order mark that turns the first column name into
    `\\ufeffName` and stops it matching anything.
    """
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("latin-1", "replace")
    sample = text[:8000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel                                   # a single column
    r = csv.DictReader(text.splitlines(), dialect=dialect)
    rows = [dict(x) for x in r]
    return list(r.fieldnames or []), rows


def import_csv(path: str | Path, con, *, mapping=None,
               dry_run: bool = True) -> dict:
    """Bring a spreadsheet in. Reports first, writes only if asked.

    THE DRY RUN IS THE POINT. Nobody's first spreadsheet has the columns
    this program would have chosen, and an import that guesses wrong and
    writes anyway leaves four hundred people to unpick by hand. `dry_run`
    reports what it guessed and what it would create, and writes nothing.

    A row that names a father nobody has heard of creates a PLACEHOLDER
    rather than failing -- half a spreadsheet is still worth importing, and
    the placeholder is visible in every list as somebody to go and fill in.
    """
    from ..store.db import new_id
    from ..store.records import Edit, set_event

    header, rows = sniff_rows(path)
    mapping = mapping or guess_mapping(header)
    unmapped = [c for c in header if c not in mapping]

    def get(row: dict, field: str) -> str:
        for col, f in mapping.items():
            if f == field:
                return (row.get(col) or "").strip()
        return ""

    # Pass one: work out who exists, without writing. A father referenced
    # before the row that defines him is the ordinary case in a spreadsheet
    # sorted by birth date, so the identity of every row has to be settled
    # before any link is made.
    keyed: dict[str, dict] = {}
    order: list[str] = []
    for i, row in enumerate(rows):
        key = get(row, "id") or f"__row{i}"
        keyed[key] = row
        order.append(key)

    wanted: set = set()
    for row in rows:
        for f in ("father_id", "mother_id", "spouse_id"):
            v = get(row, f)
            if v and v not in keyed:
                wanted.add(v)

    report = {
        "file": str(path), "columns": header, "mapping": mapping,
        "unmapped": unmapped, "rows": len(rows),
        "people": len(order), "placeholders": len(wanted),
        "families": 0, "problems": [], "dry_run": dry_run,
    }
    if not any(f in mapping.values() for f in ("given", "surname")):
        report["problems"].append(
            "No name column was recognised. Name one of your columns "
            f"'given' and one 'surname' — the ones found were: "
            f"{', '.join(header[:8])}.")
        return report
    if unmapped:
        report["problems"].append(
            f"{len(unmapped)} column(s) were not recognised and will be kept "
            f"in each person's notes: {', '.join(unmapped[:6])}.")
    if dry_run:
        return report

    ids: dict[str, str] = {}
    with Edit(con, f"Import {len(order)} people from {Path(path).name}") as e:
        for key in order + sorted(wanted):
            row = keyed.get(key)
            pid = new_id()
            ids[key] = pid
            if row is None:                       # referenced but never defined
                e.insert("person", {"id": pid, "sex": "U",
                                    "is_placeholder": 1,
                                    "notes": f"[CSV] Referenced as {key} by "
                                             f"another row, but never listed."})
                e.insert("person_name", {"id": new_id(), "person_id": pid,
                                         "type": "birth", "is_primary": 1,
                                         "given": "", "surname": "",
                                         "sort_key": "~, "})
                continue
            given, surname = get(row, "given"), get(row, "surname")
            sex = (get(row, "sex") or "U")[:1].upper()
            leftover = [f"{c}: {row[c]}" for c in unmapped
                        if (row.get(c) or "").strip()]
            note = "\n".join(x for x in [get(row, "notes"),
                                         ("[CSV] " + "; ".join(leftover))
                                         if leftover else ""] if x)
            e.insert("person", {"id": pid,
                                "sex": sex if sex in "MFXU" else "U",
                                "notes": note or None})
            e.insert("person_name", {
                "id": new_id(), "person_id": pid, "type": "birth",
                "is_primary": 1, "given": given, "surname": surname,
                "sort_key": f"{(surname or '~').upper()}, {given}"})
            set_event(e, pid, "birth", get(row, "birth_date"),
                      get(row, "birth_place"))
            set_event(e, pid, "death", get(row, "death_date"),
                      get(row, "death_place"))
            for typ, field in (("occupation", "occupation"),
                               ("education", "education")):
                if get(row, field):
                    set_event(e, pid, typ, "", desc=get(row, field))

        # Pass two: the families. A union per (father, mother) pair, and a
        # separate one per recorded spouse, so a child with two parents and
        # a couple with no children both come out right.
        unions: dict[tuple, str] = {}

        def union_for(a: str, b: str) -> str:
            k = tuple(sorted(x for x in (a, b) if x))
            if k in unions:
                return unions[k]
            uid = new_id()
            e.insert("union_", {"id": uid, "type": "marriage"})
            for seq, pid in enumerate(k):
                e.insert("union_partner", {"union_id": uid, "person_id": pid,
                                           "role": "partner", "seq": seq})
            unions[k] = uid
            return uid

        for key in order:
            row = keyed[key]
            kid = ids[key]
            fa, mo = ids.get(get(row, "father_id")), ids.get(get(row, "mother_id"))
            if fa or mo:
                uid = union_for(fa or "", mo or "")
                e.insert("union_child", {"union_id": uid, "person_id": kid,
                                         "is_primary": 1})
            sp = ids.get(get(row, "spouse_id"))
            if sp:
                uid = union_for(kid, sp)
                if get(row, "marriage_date"):
                    eid = new_id()
                    from ..model.gendate import parse as pdate
                    d = pdate(get(row, "marriage_date"))
                    e.insert("event", {
                        "id": eid, "type": "marriage", "date_json": d.to_json(),
                        "date_earliest": d.earliest.isoformat() if d.earliest else None,
                        "date_latest": d.latest.isoformat() if d.latest else None,
                        "date_sort": d.sort_value})
                    e.insert("event_role", {"event_id": eid, "person_id": None,
                                            "union_id": uid,
                                            "role": "principal"})
        report["families"] = len(unions)
    return report
