"""Search that understands a family.

WHY A SECOND SEARCH. `records.search` finds a person by name and is what the
box in the header is for. This is the other question — the one somebody asks
after ten years of research, when the file is four hundred people and the
work is not "where is Aunt Rose" but "which of these still has no death
date", "who was in Somerset before 1850", "who has nothing written about
them at all".

THE FILTERS ALREADY EXISTED, spread across four screens: the gaps ranking
knows who has no dates, the stats module knows who is living, the kinship
index knows who is a cousin. What did not exist was one box that takes them
together.

    surname:whitcombe born:<1850 place:somerset no:death
    living kin:cousins_1
    no:parents no:photo

THE GRAMMAR IS DELIBERATELY SMALL. `word:value` for a field, a bare word for
a name, and everything ANDs. There is no OR, no bracketing and no negation
beyond `no:`, because a query language nobody can remember is a query
language nobody uses — and because every one of these is a question a
genealogist actually asks out loud.
"""
from __future__ import annotations

import re
from typing import Optional

# What each `no:` means, so the list is in one place and the help text below
# is generated from it rather than drifting from it.
MISSING = {
    "birth": "no birth date",
    "death": "no death date",
    "dates": "no dates at all",
    "place": "no birthplace",
    "parents": "no parents recorded",
    "photo": "no photograph",
    "notes": "nothing written about them",
    "source": "nothing cited",
    "surname": "no surname",
    "occupation": "no occupation",
}

HELP = [
    ("whitcombe", "anybody of that name"),
    ("surname:whitcombe", "that surname exactly"),
    ("born:<1850", "born before 1850 — also >, and 1800-1850"),
    ("died:>1900", "died after 1900"),
    ("place:somerset", "any place recorded for them"),
    ("occupation:weaver", "what they did"),
    ("living", "probably still alive"),
    ("dead", "recorded as died"),
    ("no:death", "no death date — and no:parents, no:photo, no:source…"),
    ("kin:cousins_1", "by relation to whoever the chart is centred on"),
]


def _num(s: str) -> Optional[int]:
    try:
        return int(s)
    except ValueError:
        return None


def _year_test(expr: str):
    """`<1850`, `>1900`, `1800-1850` or `1841` as a predicate on a year."""
    expr = expr.strip()
    if m := re.fullmatch(r"<\s*(\d{3,4})", expr):
        lo = int(m.group(1))
        return lambda y: y is not None and y < lo
    if m := re.fullmatch(r">\s*(\d{3,4})", expr):
        hi = int(m.group(1))
        return lambda y: y is not None and y > hi
    if m := re.fullmatch(r"(\d{3,4})\s*[-–]\s*(\d{3,4})", expr):
        a, b = int(m.group(1)), int(m.group(2))
        return lambda y: y is not None and a <= y <= b
    if n := _num(expr):
        return lambda y: y == n
    return lambda y: False


def parse(q: str) -> list[tuple[str, str]]:
    """The query as (field, value) pairs. Bare words become `name`."""
    terms = []
    for tok in re.findall(r'(?:[\w:<>=-]+|"[^"]*")+', q or ""):
        tok = tok.strip('"')
        if not tok:
            continue
        if ":" in tok:
            f, _, v = tok.partition(":")
            terms.append((f.lower(), v))
        elif tok.lower() in ("living", "dead", "alive"):
            terms.append(("state", tok.lower()))
        else:
            terms.append(("name", tok))
    return terms


def search(graph, con, q: str, *, kin=None, limit: int = 200) -> dict:
    """Everybody the query describes, with why each matched."""
    terms = parse(q)
    if not terms:
        return {"query": q, "terms": [], "people": [], "total": 0,
                "help": [{"q": a, "what": b} for a, b in HELP]}

    # The three things that need a query of their own, asked once rather
    # than per person: photographs, citations and places.
    have_photo = {r["person_id"] for r in con.execute(
        "SELECT DISTINCT person_id FROM media_link WHERE person_id IS NOT NULL")}
    have_cite = {r["person_id"] for r in con.execute(
        "SELECT DISTINCT person_id FROM citation WHERE person_id IS NOT NULL")}
    for r in con.execute(
        "SELECT DISTINCT er.person_id pid FROM citation c "
        "JOIN event_role er ON er.event_id=c.event_id "
        "WHERE er.person_id IS NOT NULL"
    ):
        have_cite.add(r["pid"])
    places: dict = {}
    for r in con.execute(
        "SELECT er.person_id pid, pl.name nm FROM event e "
        "JOIN event_role er ON er.event_id=e.id "
        "JOIN place pl ON pl.id=e.place_id WHERE er.person_id IS NOT NULL"
    ):
        places.setdefault(r["pid"], []).append((r["nm"] or "").lower())
    occs: dict = {}
    for r in con.execute(
        "SELECT er.person_id pid, e.description d FROM event e "
        "JOIN event_role er ON er.event_id=e.id "
        "WHERE e.type='occupation' AND er.person_id IS NOT NULL"
    ):
        occs.setdefault(r["pid"], []).append((r["d"] or "").lower())

    out = []
    for pid, p in graph.people.items():
        why = []
        ok = True
        for field, val in terms:
            v = val.lower().strip()
            hit = ""
            if field == "name":
                hit = v in p.full_name.lower() and f"name has “{val}”"
            elif field == "surname":
                hit = (p.surname or "").lower() == v and f"surname {p.surname}"
            elif field == "given":
                hit = v in (p.given or "").lower() and f"given name {p.given}"
            elif field in ("born", "birth"):
                hit = _year_test(val)(p.birth_year) and f"born {p.birth.display}"
            elif field in ("died", "death"):
                hit = _year_test(val)(p.death_year) and f"died {p.death.display}"
            elif field == "place":
                got = [x for x in places.get(pid, []) if v in x]
                got += [x for x in (p.birth_place.lower(),
                                    p.death_place.lower()) if v in x]
                hit = bool(got) and f"a place matching “{val}”"
            elif field == "occupation":
                hit = (any(v in x for x in occs.get(pid, []))
                       or v in (p.occupation or "").lower()) and \
                      f"occupation {p.occupation or val}"
            elif field == "state":
                alive = p.living is True or (not p.death.known
                                             and (p.birth_year or 0) > 1925)
                hit = ((alive and v in ("living", "alive"))
                       or (not alive and v == "dead")) and v
            elif field == "kin":
                k = kin.of(pid) if kin else None
                hit = bool(k and k.group == v) and (k.label if k else "")
            elif field == "no":
                hit = _is_missing(graph, p, v, have_photo, have_cite) and \
                      MISSING.get(v, f"no {v}")
            else:
                hit = v in p.full_name.lower() and f"matched “{val}”"
            if not hit:
                ok = False
                break
            why.append(hit if isinstance(hit, str) else str(hit))
        if ok:
            out.append({"id": pid, "name": p.full_name, "life": p.lifespan,
                        "sex": p.sex, "why": why})

    out.sort(key=lambda r: (graph.people[r["id"]].sort_key))
    return {"query": q, "terms": [{"field": f, "value": v} for f, v in terms],
            "total": len(out), "people": out[:limit],
            "help": [{"q": a, "what": b} for a, b in HELP]}


def _is_missing(graph, p, what: str, have_photo: set, have_cite: set) -> bool:
    if what == "birth":
        return not p.birth.known
    if what == "death":
        return not p.death.known
    if what == "dates":
        return not p.birth.known and not p.death.known
    if what == "place":
        return not (p.birth_place or "").strip()
    if what == "parents":
        return not graph.parents(p.id, primary_only=False)
    if what == "photo":
        return p.id not in have_photo
    if what == "notes":
        return not (p.notes or "").strip()
    if what == "source":
        return p.id not in have_cite
    if what == "surname":
        return not (p.surname or "").strip()
    if what == "occupation":
        return not (p.occupation or "").strip()
    return False


# ═══════════════════════════ who lived together ═══════════════════════════
#
# "WHO WAS LIVING IN THIS HOUSE IN 1861" is how the records are organised and
# is not a shape this program can draw. A census return is a household, not a
# family: it has a lodger, a servant, a widowed mother-in-law and a visitor
# on the night, and the tree does not hold any of them in one place.
#
# It is assembled from what IS in the file: everybody with an event at the
# same place within a few years of each other. Approximate on purpose — it is
# a research aid pointing at "these six were in Frome in the 1860s, look at
# them together", not a claim about one address.
def households(graph, con, *, window: int = 5, min_people: int = 2,
               limit: int = 60) -> list[dict]:
    rows = []
    for r in con.execute(
        "SELECT er.person_id pid, pl.name place, e.date_sort yr, e.type "
        "FROM event e JOIN event_role er ON er.event_id=e.id "
        "JOIN place pl ON pl.id=e.place_id "
        "WHERE er.person_id IS NOT NULL AND e.date_sort IS NOT NULL "
        "ORDER BY pl.name, e.date_sort"
    ):
        if r["pid"] in graph.people:
            rows.append((r["place"], int(r["yr"]), r["pid"], r["type"]))

    out: dict = {}
    for place, yr, pid, typ in rows:
        # Bucketed to the window, so 1859 and 1862 land together on a
        # five-year window and 1861 and 1871 do not.
        key = (place, yr // window * window)
        got = out.setdefault(key, {"place": place, "from": yr, "to": yr,
                                   "people": {}, "kinds": set()})
        got["from"] = min(got["from"], yr)
        got["to"] = max(got["to"], yr)
        got["people"].setdefault(pid, typ)
        got["kinds"].add(typ)

    made = []
    for (place, _b), h in out.items():
        if len(h["people"]) < min_people:
            continue
        ids = sorted(h["people"], key=lambda p: (graph.people[p].birth_year or 9999))
        made.append({
            "place": place,
            "from": h["from"], "to": h["to"],
            "span": (str(h["from"]) if h["from"] == h["to"]
                     else f"{h['from']}–{h['to']}"),
            "count": len(ids),
            "kinds": sorted(h["kinds"]),
            "people": [{"id": p, "name": graph.people[p].full_name,
                        "life": graph.people[p].lifespan,
                        "why": h["people"][p]} for p in ids],
            # WHETHER THEY ARE ONE FAMILY OR SEVERAL is the interesting part:
            # two surnames in one house in 1861 is a marriage, a lodger or a
            # servant, and all three are worth a look.
            "surnames": sorted({graph.people[p].surname for p in ids
                                if graph.people[p].surname}),
        })
    made.sort(key=lambda h: (-h["count"], h["from"]))
    return made[:limit]


# ═══════════════════════ an address book, for the living ══════════════════
#
# A genealogy program is full of the dead and the people who use it are
# surrounded by the living: the aunt with the photographs, the cousin who
# has the family Bible. There was nowhere to put a telephone number, so it
# went on a different piece of paper and was lost.
#
# Kept as ordinary events, like everything else, so they export, back up and
# undo with the rest of the file and need no schema change.
CONTACT_KINDS = [
    ("phone", "Telephone"), ("email", "Email"), ("address", "Address"),
    ("website", "Website"),
]


def address_book(graph, con) -> list[dict]:
    """Everybody living, with whatever way there is of reaching them."""
    kinds = {k for k, _ in CONTACT_KINDS}
    by: dict = {}
    for r in con.execute(
        "SELECT er.person_id pid, e.type, e.description d FROM event e "
        "JOIN event_role er ON er.event_id=e.id "
        "WHERE er.person_id IS NOT NULL"
    ):
        if r["type"] in kinds and (r["d"] or "").strip():
            by.setdefault(r["pid"], []).append((r["type"], r["d"].strip()))

    out = []
    for pid, p in graph.people.items():
        alive = p.living is True or (not p.death.known
                                     and (p.birth_year or 0) > 1925)
        if not alive and pid not in by:
            continue
        out.append({
            "id": pid, "name": p.full_name, "life": p.lifespan,
            "living": alive,
            "contacts": [{"kind": k, "label": dict(CONTACT_KINDS)[k],
                          "value": v} for k, v in by.get(pid, [])],
        })
    out.sort(key=lambda r: (not r["contacts"], graph.people[r["id"]].sort_key))
    return out
