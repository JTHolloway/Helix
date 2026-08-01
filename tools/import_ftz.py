#!/usr/bin/env python3
"""Import a MyHeritage / Family Tree Builder .ftz file.

    python tools/import_ftz.py "My Tree.ftz" out.helix

An .ftz is a zip holding `node.ftt`, a tab-separated dump of the tree, plus
thumbnails. Two kinds of row share the file and are told apart by column
count:

    29 columns -> a PERSON
        0  id
        2  id of the family this person is a CHILD of (0 if unknown)
        12 surname          13 given names
        16 birth flag       17-19 birth year, month, day
        20 death flag       21-23 death year, month, day
        24 sex  (1 male, 2 female, 0 unknown)

    12 columns -> a FAMILY
        0  id               2  husband id        4  wife id

Only what Helix models is imported. Nothing is invented: a zero year becomes
an unknown date rather than a guess, and thumbnails are left alone.
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from helix.model.gendate import parse as gdparse      # noqa: E402
from helix.store.db import connect, new_id, set_setting  # noqa: E402

MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _date(year: str, month: str, day: str) -> str:
    try:
        y, m, d = int(year), int(month), int(day)
    except ValueError:
        return ""
    if not y:
        return ""
    if m and d:
        return f"{d} {MONTHS[m]} {y}"
    if m:
        return f"{MONTHS[m]} {y}"
    return str(y)


def read_ftz(path: Path):
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.endswith("node.ftt"))
        raw = z.read(name).decode("utf-8-sig", "replace")
    rows = [ln.split("\t") for ln in raw.strip().split("\n")[1:]]
    people = {r[0]: r for r in rows if len(r) == 29}
    families = {r[0]: r for r in rows if len(r) == 12}
    return people, families


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src")
    ap.add_argument("out", nargs="?", default="imported.helix")
    ap.add_argument("--subject", help="person id to centre the chart on")
    args = ap.parse_args()

    src, out = Path(args.src), Path(args.out)
    if out.exists():
        out.unlink()
    people, families = read_ftz(src)
    con = connect(out, backup_daily=False)

    ids: dict[str, str] = {}
    for ftz_id, r in people.items():
        pid = new_id()
        ids[ftz_id] = pid
        sex = {"1": "M", "2": "F"}.get(r[24], "U")
        con.execute("INSERT INTO person(id,sex) VALUES(?,?)", (pid, sex))
        given = (r[13] or "").strip()
        surname = (r[12] or "").strip()
        con.execute("INSERT INTO person_name(id,person_id,type,is_primary,given,"
                    "surname,sort_key) VALUES(?,?,'birth',1,?,?,?)",
                    (new_id(), pid, given, surname,
                     f"{surname.upper()}, {given}"))
        for typ, txt in (("birth", _date(r[17], r[18], r[19])),
                         ("death", _date(r[21], r[22], r[23]))):
            if not txt:
                continue
            d = gdparse(txt)
            eid = new_id()
            con.execute("INSERT INTO event(id,type,date_json,date_earliest,"
                        "date_latest,date_sort) VALUES(?,?,?,?,?,?)",
                        (eid, typ, d.to_json(),
                         d.earliest.isoformat() if d.earliest else None,
                         d.latest.isoformat() if d.latest else None,
                         d.sort_value))
            con.execute("INSERT INTO event_role(event_id,person_id,role) "
                        "VALUES(?,?,'principal')", (eid, pid))

    fam_ids: dict[str, str] = {}
    for ftz_id, r in families.items():
        uid = new_id()
        fam_ids[ftz_id] = uid
        con.execute("INSERT INTO union_(id,type) VALUES(?,'marriage')", (uid,))
        for seq, col in ((0, 2), (1, 4)):
            person = ids.get(r[col])
            if person:
                con.execute("INSERT INTO union_partner(union_id,person_id,seq)"
                            " VALUES(?,?,?)", (uid, person, seq))

    kids = 0
    for ftz_id, r in people.items():
        uid = fam_ids.get(r[2])
        if not uid:
            continue
        con.execute("INSERT INTO union_child(union_id,person_id,is_primary)"
                    " VALUES(?,?,1)", (uid, ids[ftz_id]))
        kids += 1

    # centre on whoever has the most ancestors recorded
    from helix.graph import build
    con.commit()
    graph = build.load(con)
    subject = max(graph.people, key=lambda p: len(graph.ancestors(p)))
    set_setting(con, "subject_person_id", args.subject or subject)
    set_setting(con, "project_title", src.stem.replace("_", " ").strip())
    con.commit()

    print(f"Imported {len(people)} people, {len(families)} families, "
          f"{kids} parent links -> {out}")
    print(f"  centred on {graph.people[subject].full_name} "
          f"({len(graph.ancestors(subject))} ancestors recorded)")


if __name__ == "__main__":
    main()
