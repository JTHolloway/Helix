"""What the file says about the family as a whole.

  summary          people, how long they lived, cousins who married cousins
  records          the longest life, the largest family, the oldest parent
  by_decade        births and lifespan, by the decade somebody was born in
  surnames/places  what the family is made of and where it was
  pedigree_collapse  distinct ancestors at generation n against 2^n
  timeline         one life, with the family's events beside it

A figure is only shown with the number of people behind it, so one worked
out from three records cannot be mistaken for one worked out from three
hundred.
"""
from __future__ import annotations

from datetime import date
from statistics import median
from typing import Optional


def summary(graph) -> dict:
    people = list(graph.people.values())
    # Everybody who reached five. A median over every recorded death is
    # dragged down so far by infant mortality that it reports a family in
    # which nobody reached fifty, which is not what the records say.
    lifes = [x for x in (_lifespan(p) for p in people) if x is not None]
    adult = [x for x in lifes if x >= 5]
    return {
        "count": len(people),
        "living": sum(1 for p in people if _living(p)),
        "with_both_dates": len(adult),
        "median_lifespan": round(median(adult), 1) if adult else None,
        "marriages": len(graph.unions),
        "endogamy_cases": len(graph.endogamy()),
    }


def by_decade(graph) -> list[dict]:
    """Births and lifespan, by the decade somebody was born in.

    BY BIRTH DECADE AND NOT BY DEATH DECADE, so a cohort can be followed.
    Grouped by death, everybody lost to the 1918 influenza lands in one bar
    and nothing about the century is visible.
    """
    rows: dict[int, dict] = {}
    for p in graph.people.values():
        y = p.birth_year
        if not y:
            continue
        d = (y // 10) * 10
        r = rows.setdefault(d, {"decade": d, "born": 0, "lifespans": []})
        r["born"] += 1
        span = _lifespan(p)
        if span is not None:
            r["lifespans"].append(span)
    out = []
    for d in sorted(rows):
        r = rows[d]
        adult = [x for x in r.pop("lifespans") if x >= 5]
        r["known_lifespans"] = len(adult)
        r["median_lifespan"] = round(median(adult), 1) if adult else None
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


def _living(p) -> bool:
    """Is this person alive, as far as the file says?

    `living` when somebody has recorded it; otherwise a person with no death
    date who was born within the last 110 years. Nobody is assumed dead for
    want of a record.
    """
    if p.living is not None:
        return bool(p.living)
    if p.death.known:
        return False
    y = p.birth_year
    return bool(y and y >= date.today().year - 110)


def _age_now(p) -> Optional[float]:
    if p.birth.sort_value is None:
        return None
    today = date.today()
    return (today.year + (today.timetuple().tm_yday / 366.0)) - p.birth.sort_value


def _lifespan(p) -> Optional[float]:
    if p.birth.sort_value is None or p.death.sort_value is None:
        return None
    return p.death.sort_value - p.birth.sort_value


def _couple_children(graph) -> list[tuple]:
    """(children, union, partners) for every marriage with children."""
    out = []
    for u in graph.unions.values():
        kids = [c for c in u.children if c in graph.people]
        if kids:
            out.append((len(kids), u,
                        [x for x in u.partners if x in graph.people]))
    return out


def _marriage_years(graph, u) -> Optional[float]:
    """How long a marriage lasted, from its date to the first death.

    ENDED BY A DEATH, not by today. A marriage still going is measured to
    now and said to be current; one that ended is measured to the first
    death, because that is when it ended whatever happened afterwards. A
    marriage with no date cannot be measured at all and is left out rather
    than guessed at from the children.
    """
    if not u.date.known or u.date.sort_value is None:
        return None
    ends = [graph.people[p].death.sort_value for p in u.partners
            if p in graph.people and graph.people[p].death.sort_value]
    if ends:
        end = min(ends)
    else:
        alive = all(_living(graph.people[p]) for p in u.partners
                    if p in graph.people)
        if not alive:
            return None
        today = date.today()
        end = today.year + (today.timetuple().tm_yday / 366.0)
    span = end - u.date.sort_value
    return span if 0 <= span < 90 else None


def records(graph) -> list[dict]:
    """The handful of figures worth putting on a screen.

    Each one names WHO, not just a number, and a marriage names the couple:
    "eight children" is a fact about two people, and crediting it to one of
    them is the commonest thing a genealogy program gets wrong about its own
    data.
    """
    out: list[dict] = []
    people = list(graph.people.values())

    def add(what, who, value, detail="", ids=None):
        out.append({"what": what, "who": who, "value": value,
                    "detail": detail, "ids": ids or []})

    # ---- lives ----------------------------------------------------------
    lived = [(_lifespan(p), p) for p in people if _lifespan(p) is not None]
    if lived:
        span, p = max(lived, key=lambda t: t[0])
        add("Longest life", p.full_name, f"{span:.0f} years", p.lifespan, [p.id])
        # YOUNGEST DEATH, not "shortest life": the phrase people use, and
        # the one that does not read as a judgement on somebody who died at
        # two.
        span, p = min(lived, key=lambda t: t[0])
        add("Youngest at death", p.full_name,
            f"{span:.0f} years" if span >= 1 else "under a year",
            p.lifespan, [p.id])

    alive = [(_age_now(p), p) for p in people
             if _living(p) and _age_now(p) is not None]
    if alive:
        age, p = max(alive, key=lambda t: t[0])
        add("Oldest living", p.full_name, f"{age:.0f}", p.lifespan, [p.id])
        age, p = min(alive, key=lambda t: t[0])
        add("Youngest in the family", p.full_name,
            f"{age:.0f}" if age >= 1 else "under a year", p.lifespan, [p.id])

    # ---- children -------------------------------------------------------
    # THE COUPLE, NOT ONE PARENT. Eight children is a fact about two people.
    couples = _couple_children(graph)
    if couples:
        n, u, partners = max(couples, key=lambda t: t[0])
        names = " and ".join(graph.people[x].full_name for x in partners)
        add("Most children", names or "an unrecorded couple", str(n),
            "in one marriage", list(partners))

    # ...UNLESS ONE PERSON HAD MORE ACROSS SEVERAL MARRIAGES, which is the
    # exception the couple figure hides: a man widowed twice can father more
    # children than any single marriage in the file produced.
    per_person = [(len(graph.children(p.id)), p) for p in people]
    if per_person:
        tot, p = max(per_person, key=lambda t: t[0])
        best_couple = max((c[0] for c in couples), default=0)
        if tot > best_couple:
            add("Most children, one parent", p.full_name, str(tot),
                f"across {len(p.unions)} marriages", [p.id])

    # ---- marriages ------------------------------------------------------
    spans = [(_marriage_years(graph, u), u) for u in graph.unions.values()]
    spans = [(x, u) for x, u in spans if x is not None]
    if spans:
        yrs, u = max(spans, key=lambda t: t[0])
        pair = [x for x in u.partners if x in graph.people]
        names = " and ".join(graph.people[x].full_name for x in pair)
        still = all(_living(graph.people[x]) for x in pair)
        add("Longest marriage", names, f"{yrs:.0f} years",
            ("still going, from " if still else "from ") + u.date.display,
            list(pair))
        med = median([x for x, _ in spans])
        add("Marriages last", f"{len(spans)} measured", f"{med:.0f} years",
            "median, to the first death", [])

    # ---- becoming a parent ----------------------------------------------
    ages = []
    for p in people:
        if p.birth.sort_value is None:
            continue
        for kid in graph.children(p.id):
            k = graph.people.get(kid)
            if k and k.birth.sort_value:
                ages.append((k.birth.sort_value - p.birth.sort_value, p, k))
    plausible = [t for t in ages if 12 <= t[0] <= 70]
    if plausible:
        age, p, k = max(plausible, key=lambda t: t[0])
        add("Oldest parent", p.full_name, f"{age:.0f}",
            f"when {k.given_first} was born", [p.id, k.id])
        age, p, k = min(plausible, key=lambda t: t[0])
        add("Youngest parent", p.full_name, f"{age:.0f}",
            f"when {k.given_first} was born", [p.id, k.id])
        firsts = {}
        for a, par, kid in plausible:
            if par.id not in firsts or a < firsts[par.id]:
                firsts[par.id] = a
        if firsts:
            add("First child at", f"{len(firsts)} parents",
                f"{median(list(firsts.values())):.0f}", "median", [])

    # ---- the family as a whole ------------------------------------------
    sizes = [n for n, _, _ in couples]
    if sizes:
        add("Children per marriage", f"{len(sizes)} marriages",
            f"{median(sizes):.1f}", "median", [])
    gens = graph.stats().get("generations")
    if gens:
        add("Generations", "in the file", str(gens), "", [])
    return out


# Kept under the old name: `report` and the printed dossier both call it.
extremes = records


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
        "records": records(graph),
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


# ------------------------------------------------------ the whole family ----
def family_timeline(graph, *, within=None, kin=None) -> dict:
    """Every birth, marriage and death in the file, in order.

    THE FAMILY AS ONE STORY. A chart shows who was related to whom and says
    nothing about when; a person's own timeline shows one life. This is the
    third view: 1841, a marriage; 1843, a birth; 1849, a death — the shape
    of a household changing, and the years where nothing at all is recorded,
    which are usually the years worth looking into.
    """
    rows: list[dict] = []
    seen_union: set = set()

    def ok(pid) -> bool:
        return within is None or pid in within

    for p in graph.people.values():
        if not ok(p.id):
            continue
        rel = kin.label(p.id) if kin else ""
        if p.birth.known and p.birth.sort_value is not None:
            rows.append({"year": p.birth.sort_value, "kind": "birth",
                         "date": p.birth.display, "id": p.id,
                         "what": f"{p.full_name} was born"
                                 + (f" in {p.birth_place}" if p.birth_place else ""),
                         "relation": rel})
        if p.death.known and p.death.sort_value is not None:
            age = ""
            if p.birth.sort_value is not None:
                yrs = p.death.sort_value - p.birth.sort_value
                if 0 <= yrs < 120:
                    age = (f"aged {yrs:.0f}" if yrs >= 1 else "as an infant")
            rows.append({"year": p.death.sort_value, "kind": "death",
                         "date": p.death.display, "id": p.id,
                         "what": f"{p.full_name} died"
                                 + (f" in {p.death_place}" if p.death_place else ""),
                         "detail": age, "relation": rel})

    for u in graph.unions.values():
        if u.id in seen_union or not u.date.known or u.date.sort_value is None:
            continue
        seen_union.add(u.id)
        pair = [x for x in u.partners if x in graph.people and ok(x)]
        if not pair:
            continue
        names = " and ".join(graph.people[x].full_name for x in pair)
        rows.append({"year": u.date.sort_value, "kind": "marriage",
                     "date": u.date.display, "id": pair[0],
                     "what": f"{names} married"
                             + (f" at {u.place}" if u.place else ""),
                     "relation": ""})

    rows.sort(key=lambda r: (r["year"], {"birth": 0, "marriage": 1,
                                         "death": 2}[r["kind"]]))
    for r in rows:
        r["year"] = int(r["year"])

    # A DECADE WITH NOTHING IN IT IS A FINDING. Between two dense stretches
    # it is usually not a family that stopped happening; it is a register
    # nobody has looked at.
    years = [r["year"] for r in rows]
    gaps = []
    for a, b in zip(years, years[1:]):
        if b - a >= 10:
            gaps.append({"from": a, "to": b, "years": b - a})
    return {
        "events": rows,
        "span": [years[0], years[-1]] if years else None,
        "counts": {k: sum(1 for r in rows if r["kind"] == k)
                   for k in ("birth", "marriage", "death")},
        "quiet": gaps[:8],
    }


def anniversaries(graph, *, window: int = 31, kin=None) -> list[dict]:
    """Birthdays and anniversaries falling in the next few weeks.

    ONLY WHERE THE DAY IS KNOWN. A date recorded as "1841" has no day in it,
    and offering somebody a birthday the program invented would be worse
    than offering none. Living people first, then the ones to remember.
    """
    from datetime import date, timedelta
    today = date.today()
    out = []

    def add(when, what, pid, kind, living):
        if when is None:
            return
        try:
            nxt = when.replace(year=today.year)
        except ValueError:                     # 29 February
            nxt = when.replace(year=today.year, day=28)
        if nxt < today:
            try:
                nxt = nxt.replace(year=today.year + 1)
            except ValueError:
                return
        if (nxt - today) > timedelta(days=window):
            return
        out.append({"in_days": (nxt - today).days, "on": nxt.isoformat(),
                    "what": what, "id": pid, "kind": kind, "living": living,
                    "years": today.year - when.year})

    for p in graph.people.values():
        if p.birth.precision == "day" and p.birth.earliest:
            alive = _living(p)
            add(p.birth.earliest,
                f"{p.full_name}{'' if alive else ' would be'}", p.id,
                "birthday", alive)
    for u in graph.unions.values():
        if u.date.precision == "day" and u.date.earliest:
            pair = [x for x in u.partners if x in graph.people]
            if pair:
                add(u.date.earliest,
                    " and ".join(graph.people[x].full_name for x in pair),
                    pair[0], "anniversary",
                    all(_living(graph.people[x]) for x in pair))
    out.sort(key=lambda r: (r["in_days"], not r["living"]))
    return out
