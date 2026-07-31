"""Family statistics: the numbers that make people say 'I had no idea'.

  * average age at first marriage, by generation and by sex
  * average number of children, and how it collapses after 1880
  * infant mortality rate per decade
  * average lifespan excluding infant deaths (the honest figure -- raw means
    are dragged down catastrophically by infant mortality and mislead people
    into thinking nobody reached fifty)
  * longest and shortest lives; oldest mother; youngest father
  * migration distance per generation, if places are geocoded
  * surname frequency and extinction dates
  * pedigree collapse: distinct ancestors at generation n vs the 2^n maximum
"""
from __future__ import annotations

from statistics import median
from typing import Optional


def summary(graph) -> dict:
    people = graph.people.values()
    lifes = [(p.death.sort_value - p.birth.sort_value) for p in people
             if p.birth.sort_value and p.death.sort_value]
    adult = [x for x in lifes if x >= 5]
    return {
        "count": len(graph.people),
        "with_both_dates": len(lifes),
        "median_lifespan_all": round(median(lifes), 1) if lifes else None,
        "median_lifespan_excl_infants": round(median(adult), 1) if adult else None,
        "infant_deaths": sum(1 for x in lifes if x < 5),
        "infant_rate": round(sum(1 for x in lifes if x < 5) / len(lifes), 3) if lifes else None,
        "endogamy_cases": len(graph.endogamy()),
    }


def by_decade(graph) -> list[dict]:
    """Births, deaths and lifespan by the decade somebody was born in.

    BY BIRTH DECADE AND NOT BY DEATH DECADE. Grouped by death, everybody who
    died in the 1918 influenza appears in one bar and nothing about the
    century is visible; grouped by birth, a cohort can be followed and the
    collapse in infant mortality after 1900 is the shape of the whole chart.
    """
    rows: dict[int, dict] = {}
    for p in graph.people.values():
        y = p.birth_year
        if not y:
            continue
        d = (y // 10) * 10
        r = rows.setdefault(d, {"decade": d, "born": 0, "died_young": 0,
                                "lifespans": []})
        r["born"] += 1
        if p.birth.sort_value and p.death.sort_value:
            span = p.death.sort_value - p.birth.sort_value
            r["lifespans"].append(span)
            if span < 5:
                r["died_young"] += 1
    out = []
    for d in sorted(rows):
        r = rows[d]
        spans = r.pop("lifespans")
        adult = [x for x in spans if x >= 5]
        r["known_lifespans"] = len(spans)
        r["median_lifespan"] = round(median(spans), 1) if spans else None
        # THE HONEST FIGURE. A raw mean is dragged down catastrophically by
        # infant mortality and tells people nobody reached fifty, which is
        # not what the records say: it is what dying at two years old does
        # to an average.
        r["median_reaching_five"] = round(median(adult), 1) if adult else None
        out.append(r)
    return out


def surnames(graph, limit: int = 15) -> list[dict]:
    """Which names the family is made of, and when each one arrives."""
    rows: dict[str, dict] = {}
    for p in graph.people.values():
        s = (p.surname or "").strip()
        if not s:
            continue
        r = rows.setdefault(s, {"surname": s, "count": 0,
                                "first": None, "last": None})
        r["count"] += 1
        y = p.birth_year
        if y:
            r["first"] = y if r["first"] is None else min(r["first"], y)
            r["last"] = y if r["last"] is None else max(r["last"], y)
    return sorted(rows.values(), key=lambda r: -r["count"])[:limit]


def places(graph, limit: int = 15) -> list[dict]:
    """Where the family was, by how many people were born there.

    Counted from what is written down rather than from a gazetteer: Helix
    installs nothing, and a place list that needs a geocoding service is a
    place list that stops working on a train.
    """
    rows: dict[str, dict] = {}
    for p in graph.people.values():
        for place, kind in ((p.birth_place, "born"), (p.death_place, "died")):
            if not (place or "").strip():
                continue
            r = rows.setdefault(place, {"place": place, "born": 0, "died": 0,
                                        "first": None, "last": None})
            r[kind] += 1
            y = p.birth_year
            if y:
                r["first"] = y if r["first"] is None else min(r["first"], y)
                r["last"] = y if r["last"] is None else max(r["last"], y)
    return sorted(rows.values(),
                  key=lambda r: -(r["born"] + r["died"]))[:limit]


def extremes(graph) -> list[dict]:
    """The handful of facts people actually repeat at Christmas."""
    out: list[dict] = []
    lived = [(p.death.sort_value - p.birth.sort_value, p)
             for p in graph.people.values()
             if p.birth.sort_value and p.death.sort_value]
    if lived:
        span, p = max(lived, key=lambda t: t[0])
        out.append({"what": "Longest life", "who": p.full_name,
                    "id": p.id, "value": f"{span:.0f} years",
                    "detail": p.lifespan})
    kids = [(len(graph.children(p.id)), p) for p in graph.people.values()]
    n, p = max(kids, key=lambda t: t[0]) if kids else (0, None)
    if p and n:
        out.append({"what": "Most children", "who": p.full_name, "id": p.id,
                    "value": f"{n}", "detail": p.lifespan})
    # The oldest and youngest parent, worked out from intervals rather than
    # midpoints -- a mother "about 1834" is not evidence she was 47.
    ages = []
    for p in graph.people.values():
        if not p.birth.sort_value:
            continue
        for kid in graph.children(p.id):
            k = graph.people.get(kid)
            if k and k.birth.sort_value:
                ages.append((k.birth.sort_value - p.birth.sort_value, p, k))
    plausible = [t for t in ages if 12 <= t[0] <= 70]
    if plausible:
        age, p, k = max(plausible, key=lambda t: t[0])
        out.append({"what": "Oldest parent", "who": p.full_name, "id": p.id,
                    "value": f"{age:.0f} when {k.given_first} was born"})
        age, p, k = min(plausible, key=lambda t: t[0])
        out.append({"what": "Youngest parent", "who": p.full_name, "id": p.id,
                    "value": f"{age:.0f} when {k.given_first} was born"})
    return out


def pedigree_collapse(graph, pid: Optional[str], depth: int = 8) -> list[dict]:
    """Distinct ancestors at each generation against the 2^n maximum.

    Everybody has 1024 ten-generation ancestors on paper and far fewer in
    fact, because cousins married cousins. The gap is not an error in the
    file — it is the shape of a real family, and it is the number that makes
    people understand what "we are all related" means.
    """
    if not pid or pid not in graph.people:
        return []
    anc = graph.ancestors(pid)
    out = []
    for gen in range(1, depth + 1):
        got = sum(1 for v in anc.values() if v == gen)
        if not got:
            break
        out.append({"generation": gen, "known": got, "possible": 2 ** gen,
                    "share": round(got / 2 ** gen, 3)})
    return out


def report(graph, subject: Optional[str] = None) -> dict:
    return {
        "summary": summary(graph),
        "by_decade": by_decade(graph),
        "surnames": surnames(graph),
        "places": places(graph),
        "extremes": extremes(graph),
        "collapse": pedigree_collapse(graph, subject or graph.subject_id),
    }


# --------------------------------------------------------------- a life ----
def timeline(graph, pid: str) -> dict:
    """One person's life, with the family's events beside it.

    A BIRTH DATE ON ITS OWN IS A NUMBER. "Born 1826; his sister Ann born
    1828; his father died 1841, when he was 15; married 1850" is a life, and
    every part of it is already in the file — it only has to be put in
    order. This is what turns a database row into somebody you can picture.
    """
    if pid not in graph.people:
        return {"events": []}
    me = graph.people[pid]
    born = me.birth.sort_value
    rows: list[dict] = []

    def add(when, what, who=None, kind="family"):
        if when is None:
            return
        # An older brother's birth is part of the story and belongs on the
        # line, but "age -5" is not an age. Before somebody was born there
        # is a year and no age, and the panel says so.
        age = int(when - born) if born is not None else None
        rows.append({"year": int(when), "what": what, "kind": kind,
                     "id": who, "age": age if age is not None and age >= 0
                     else None})

    add(me.birth.sort_value, f"{me.given_first} was born"
        + (f" in {me.birth_place}" if me.birth_place else ""), pid, "self")
    if me.death.known:
        add(me.death.sort_value, f"{me.given_first} died"
            + (f" in {me.death_place}" if me.death_place else ""), pid, "self")

    for sib in graph.siblings(pid):
        s = graph.people.get(sib)
        if s and s.birth.known:
            add(s.birth.sort_value, f"{s.full_name} was born", sib, "sibling")
    for par in graph.parents(pid, primary_only=False):
        q = graph.people.get(par)
        if q and q.death.known:
            add(q.death.sort_value, f"{q.full_name} died", par, "parent")
    for uid in me.unions:
        u = graph.unions.get(uid)
        if not u:
            continue
        others = [x for x in u.partners if x != pid and x in graph.people]
        who = graph.people[others[0]].full_name if others else "somebody"
        if u.date.known:
            add(u.date.sort_value, f"Married {who}",
                others[0] if others else None, "marriage")
        for kid in u.children:
            k = graph.people.get(kid)
            if k and k.birth.known:
                add(k.birth.sort_value, f"{k.full_name} was born", kid, "child")

    rows.sort(key=lambda r: (r["year"], r["kind"] != "self"))
    return {"id": pid, "name": me.full_name, "events": rows,
            "span": [rows[0]["year"], rows[-1]["year"]] if rows else None}
