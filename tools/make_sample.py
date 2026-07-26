#!/usr/bin/env python3
"""Generate a realistic sample family so the program has something to draw
before you have entered a single ancestor of your own.

  python tools/make_sample.py sample.helix --people 400

Deliberately includes the awkward cases that break naive family tree code:
missing dates, a cousin marriage, an adoption, remarriage, and infant deaths.
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from helix.model.gendate import parse as gdparse          # noqa: E402
from helix.store.db import connect, new_id, set_setting    # noqa: E402

SURNAMES = ["Whitcombe", "Hallam", "Pargeter", "Boyce", "Threlfall", "Kentish",
            "Marlow", "Vasey", "Ashworth", "Cadogan", "Rennick", "Salter",
            "Dunmore", "Fenwick", "Oakley", "Brayfield"]
MALE = ["John", "Thomas", "William", "George", "Henry", "Samuel", "Edward",
        "Arthur", "Frederick", "Albert", "Walter", "Charles", "Ernest", "Percy",
        "Reuben", "Isaac", "Nathaniel", "Joseph"]
FEMALE = ["Elizabeth", "Mary", "Sarah", "Ann", "Martha", "Emily", "Alice",
          "Florence", "Edith", "Hannah", "Charlotte", "Beatrice", "Clara",
          "Susannah", "Harriet", "Lydia", "Winifred", "Esther"]
PLACES = [("Walcot, Bath, Somerset", 51.39, -2.36),
          ("Bathwick, Bath, Somerset", 51.38, -2.35),
          ("Frome, Somerset", 51.23, -2.32),
          ("Bradford-on-Avon, Wiltshire", 51.35, -2.25),
          ("Bristol, Gloucestershire", 51.45, -2.59),
          ("Trowbridge, Wiltshire", 51.32, -2.21),
          ("Keynsham, Somerset", 51.41, -2.50),
          ("Chippenham, Wiltshire", 51.46, -2.12)]
OCCS = ["Agricultural labourer", "Stonemason", "Wool comber", "Carpenter",
        "Domestic servant", "Grocer", "Railway porter", "Cordwainer",
        "Dressmaker", "Blacksmith", "Coal miner", "Schoolmistress",
        "Clerk", "Innkeeper", "Wheelwright", "Nurse", "Engine fitter"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out", nargs="?", default="sample.helix")
    ap.add_argument("--people", type=int, default=400)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--start-year", type=int, default=1690)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    out = Path(args.out)
    if out.exists():
        out.unlink()
    con = connect(out)

    places = {}
    for name, lat, lon in PLACES:
        pid = new_id()
        places[name] = pid
        con.execute("INSERT INTO place(id,name,type,lat,lon) VALUES(?,?,?,?,?)",
                    (pid, name, "parish", lat, lon))

    src = new_id()
    con.execute("INSERT INTO source(id,title,repository,type,quality) "
                "VALUES(?,?,?,?,?)",
                (src, "Sample data (not a real source)", "generated",
                 "website", 0))

    people: list[str] = []
    meta: dict[str, dict] = {}

    def add_person(sex, surname, year, gen, confidence=2, living=None,
                   placeholder=False):
        pid = new_id()
        given = " ".join(rng.sample(MALE if sex == "M" else FEMALE,
                                    rng.choice([1, 1, 2])))
        con.execute("INSERT INTO person(id,sex,confidence,living,is_placeholder)"
                    " VALUES(?,?,?,?,?)",
                    (pid, sex, confidence, living, int(placeholder)))
        con.execute(
            "INSERT INTO person_name(id,person_id,type,is_primary,given,"
            "surname,sort_key) VALUES(?,?,?,1,?,?,?)",
            (new_id(), pid, "birth", given, surname, f"{surname.upper()}, {given}"))
        # birth
        if rng.random() > 0.06:                      # 6% have no birth date
            txt = str(year) if rng.random() > 0.4 else \
                f"{rng.randint(1,28)} {rng.choice(['Jan','Mar','May','Jul','Sep','Nov'])} {year}"
            if confidence <= 1:
                txt = f"abt {year}"
            _event(con, pid, "birth", txt, rng.choice(list(places.values())), src)
        # death
        alive = year > 1955 and rng.random() < 0.75
        if not alive:
            if rng.random() < 0.13:
                age = rng.randint(0, 5)              # infant mortality
            else:
                age = int(rng.gauss(66, 16))
            age = max(0, min(101, age))
            _event(con, pid, "death", str(year + age),
                   rng.choice(list(places.values())), src)
        else:
            con.execute("UPDATE person SET living=1 WHERE id=?", (pid,))
        if rng.random() < 0.55:
            _event(con, pid, "occupation", None, None, src,
                   desc=rng.choice(OCCS))
        people.append(pid)
        meta[pid] = {"sex": sex, "surname": surname, "year": year, "gen": gen}
        return pid

    def add_union(a, b, year):
        uid = new_id()
        con.execute("INSERT INTO union_(id,type) VALUES(?,?)", (uid, "marriage"))
        for i, x in enumerate((a, b)):
            con.execute("INSERT INTO union_partner(union_id,person_id,seq) "
                        "VALUES(?,?,?)", (uid, x, i))
        eid = new_id()
        d = gdparse(str(year))
        con.execute("INSERT INTO event(id,type,date_json,date_earliest,"
                    "date_latest,date_sort,place_id) VALUES(?,?,?,?,?,?,?)",
                    (eid, "marriage", d.to_json(),
                     d.earliest.isoformat() if d.earliest else None,
                     d.latest.isoformat() if d.latest else None, d.sort_value,
                     rng.choice(list(places.values()))))
        con.execute("INSERT INTO event_role(event_id,union_id,role) "
                    "VALUES(?,?,?)", (eid, uid, "principal"))
        return uid

    # --- build the pedigree ------------------------------------------------
    founders = []
    for i in range(3):
        sn = SURNAMES[i]
        m = add_person("M", sn, args.start_year + rng.randint(0, 8), 0)
        f = add_person("F", SURNAMES[rng.randrange(3, len(SURNAMES))],
                       args.start_year + rng.randint(0, 8), 0)
        founders.append((m, f))

    frontier = []
    for m, f in founders:
        frontier.append((m, f, args.start_year + 24))

    gen = 0
    while len(people) < args.people and gen < 9:
        gen += 1
        nxt = []
        for m, f, yr in frontier:
            uid = add_union(m, f, yr)
            nkids = rng.choice([2, 3, 3, 4, 5, 6, 7])
            kids = []
            for k in range(nkids):
                if len(people) >= args.people * 1.15:
                    break
                sex = rng.choice("MF")
                by = yr + 1 + k * rng.randint(1, 3)
                conf = 3 if gen >= 5 else rng.choice([1, 2, 2, 2, 3])
                kid = add_person(sex, meta[m]["surname"], by, gen, conf)
                con.execute("INSERT INTO union_child(union_id,person_id,"
                            "is_primary,birth_order) VALUES(?,?,1,?)",
                            (uid, kid, k))
                kids.append(kid)
            for kid in kids:
                if meta[kid]["year"] > 1990:
                    continue
                if rng.random() < 0.62:
                    my = meta[kid]["year"] + rng.randint(20, 30)
                    sp_sex = "F" if meta[kid]["sex"] == "M" else "M"
                    sp = add_person(sp_sex, rng.choice(SURNAMES),
                                    my - rng.randint(20, 27), gen)
                    a, b = (kid, sp) if meta[kid]["sex"] == "M" else (sp, kid)
                    nxt.append((a, b, my))
        frontier = nxt

    # --- awkward but real cases -------------------------------------------
    # a cousin marriage: two people from different branches with a shared line
    mids = [p for p in people if 3 <= meta[p]["gen"] <= 5]
    if len(mids) > 6:
        a = next((p for p in mids if meta[p]["sex"] == "M"), None)
        b = next((p for p in reversed(mids) if meta[p]["sex"] == "F"), None)
        if a and b and a != b:
            add_union(a, b, max(meta[a]["year"], meta[b]["year"]) + 24)
    # An adoption: a second, non-primary parentage. Both adoptive parents
    # must be plausibly older than the child, or we would be shipping sample
    # data that fails our own validator.
    child = None
    for cand in people:
        if meta[cand]["gen"] >= 3 and meta[cand]["year"] > 1800:
            child = cand
            break
    if child:
        for r in con.execute("SELECT id FROM union_"):
            u = r[0]
            partners = [x[0] for x in con.execute(
                "SELECT person_id FROM union_partner WHERE union_id=?", (u,))]
            already = [x[0] for x in con.execute(
                "SELECT person_id FROM union_child WHERE union_id=?", (u,))]
            if child in already or child in partners or len(partners) < 2:
                continue
            if all(meta[x]["year"] <= meta[child]["year"] - 18 for x in partners):
                con.execute(
                    "INSERT INTO union_child(union_id,person_id,is_primary,"
                    "rel_partner1,rel_partner2) VALUES(?,?,0,'adopted','adopted')",
                    (u, child))
                break

    # Pick a subject who is genuinely descended from the founders, so the
    # Thread and the what-if analysis have something to show.
    kids = {r[0] for r in con.execute("SELECT person_id FROM union_child")}
    deep = [p for p in people if p in kids]
    youngest = max(deep or people, key=lambda p: meta[p]["year"])
    set_setting(con, "subject_person_id", youngest)
    set_setting(con, "project_title", "Sample Family")
    con.commit()
    print(f"Wrote {out}  ({len(people)} people, subject = "
          f"{meta[youngest]['surname']} b.{meta[youngest]['year']})")


def _event(con, pid, typ, datetext, place_id, src, desc=None):
    from helix.store.db import new_id as nid
    d = gdparse(datetext) if datetext else None
    eid = nid()
    con.execute("INSERT INTO event(id,type,date_json,date_earliest,date_latest,"
                "date_sort,place_id,description) VALUES(?,?,?,?,?,?,?,?)",
                (eid, typ, d.to_json() if d else None,
                 d.earliest.isoformat() if d and d.earliest else None,
                 d.latest.isoformat() if d and d.latest else None,
                 d.sort_value if d else None, place_id, desc))
    con.execute("INSERT INTO event_role(event_id,person_id,role) VALUES(?,?,?)",
                (eid, pid, "principal"))
    con.execute("INSERT INTO citation(id,source_id,event_id) VALUES(?,?,?)",
                (nid(), src, eid))


if __name__ == "__main__":
    main()
