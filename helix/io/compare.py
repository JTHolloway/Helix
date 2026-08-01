"""Two files of the same family, fact by fact.

THE SITUATION THIS EXISTS FOR. A cousin sends a GEDCOM. It has four hundred
people in it, most of whom you already have, some of whom you do not, and a
dozen dates that disagree with yours. Imported blind it doubles your file and
buries your own research under somebody else's; left unopened it is four
hundred people you will never look at.

So: what is in theirs and not in yours, what is in yours and not in theirs,
and — the one that matters — where the two of you disagree about the same
person. THE DISAGREEMENTS ARE THE VALUABLE PART. Two dates for one birth mean
one of you has seen a record the other has not, and that is the single most
productive thing a family historian can be shown.

NOTHING IS CHANGED HERE. This module reads two files and returns a report.
Acting on it is the import, which is a separate deliberate step, because a
merge that happens as a side effect of looking is how somebody loses ten
years of work.
"""
from __future__ import annotations

from typing import Optional


def _key(p) -> tuple:
    """What makes two records the same person, roughly.

    Surname and given first name, lowercased, plus the birth year if either
    has one. Deliberately coarse -- this is the FIRST pass, and `analysis.
    duplicates` does the careful matching with nicknames and soundex. What
    is wanted here is a fast, obvious pairing so the report is about facts
    and not about identity.
    """
    return ((p.surname or "").strip().lower(),
            (p.given or "").strip().lower().split(" ")[0],
            p.birth_year or 0)


def _loose(p) -> tuple:
    return ((p.surname or "").strip().lower(),
            (p.given or "").strip().lower().split(" ")[0])


# The facts worth comparing, and what to call each. Not everything in the
# schema: a comparison of four hundred people has to fit on a screen, and
# these are the ones people argue about.
FIELDS = [
    ("birth", "Born", lambda p: p.birth.display),
    ("birth_place", "Born in", lambda p: p.birth_place),
    ("death", "Died", lambda p: p.death.display),
    ("death_place", "Died in", lambda p: p.death_place),
    ("occupation", "Occupation", lambda p: p.occupation),
    ("education", "Education", lambda p: p.education),
]


def compare(mine, theirs, *, mine_name: str = "yours",
            theirs_name: str = "theirs", limit: int = 400) -> dict:
    """Two loaded graphs, read against each other."""
    mine_by, theirs_by = {}, {}
    for g, d in ((mine, mine_by), (theirs, theirs_by)):
        for pid, p in g.people.items():
            d.setdefault(_key(p), []).append(pid)

    def agreement(a, b) -> int:
        """How many of the comparable facts these two already share.

        WHY THE PAIRING NEEDS THIS. Three Clara Vaseys in one file is the
        ordinary case, not the odd one, and a key of name-plus-birth-year
        cannot tell them apart when none of them has a birth year. Paired by
        first-come the report invented a conflict -- one Clara's death date
        against another's -- which is the single thing that would make
        somebody stop trusting it.
        """
        n = 0
        for _key, _label, read in FIELDS:
            va, vb = (read(a) or "").strip(), (read(b) or "").strip()
            if va and va == vb:
                n += 2
            elif va and vb:
                n -= 1                       # a disagreement is evidence too
        return n

    paired: list[tuple[str, str]] = []
    used_mine, used_theirs = set(), set()

    def take(mine_ids, theirs_ids):
        """Pair up two pools of candidates, best agreement first."""
        scored = sorted(
            ((agreement(mine.people[m], theirs.people[t]), m, t)
             for m in mine_ids for t in theirs_ids),
            key=lambda x: -x[0])
        for _score, m, t in scored:
            if m in used_mine or t in used_theirs:
                continue
            paired.append((m, t))
            used_mine.add(m)
            used_theirs.add(t)

    for k, ids in mine_by.items():
        if k in theirs_by:
            take(ids, theirs_by[k])

    # Second pass on name alone, for the ordinary case where one file has a
    # birth year and the other does not.
    loose_mine, loose_theirs = {}, {}
    for pid, p in mine.people.items():
        if pid not in used_mine:
            loose_mine.setdefault(_loose(p), []).append(pid)
    for pid, p in theirs.people.items():
        if pid not in used_theirs:
            loose_theirs.setdefault(_loose(p), []).append(pid)
    for k, ids in loose_mine.items():
        if k in loose_theirs:
            take(ids, loose_theirs[k])

    # ---- where the two of you disagree, which is the valuable part
    conflicts, agreed, gained = [], 0, []
    for mid, tid in paired:
        a, b = mine.people[mid], theirs.people[tid]
        rows = []
        for key, label, read in FIELDS:
            va, vb = (read(a) or "").strip(), (read(b) or "").strip()
            if not va and not vb:
                continue
            if va == vb:
                agreed += 1
                continue
            rows.append({"field": key, "label": label,
                         "mine": va, "theirs": vb,
                         # A blank on one side is not a disagreement, it is
                         # something to gain -- and the two want different
                         # buttons.
                         "kind": "gain" if not va else
                                 "loss" if not vb else "clash"})
        if rows:
            (conflicts if any(r["kind"] == "clash" for r in rows)
             else gained).append({
                "mine": {"id": mid, "name": a.full_name, "life": a.lifespan},
                "theirs": {"id": tid, "name": b.full_name, "life": b.lifespan},
                "rows": rows})

    only_theirs = [tid for tid in theirs.people if tid not in used_theirs]
    only_mine = [mid for mid in mine.people if mid not in used_mine]

    brief = lambda g, pid: {
        "id": pid, "name": g.people[pid].full_name,
        "life": g.people[pid].lifespan,
        "parents": [g.people[x].full_name for x in
                    g.parents(pid, primary_only=False) if x in g.people],
    }

    return {
        "mine_name": mine_name, "theirs_name": theirs_name,
        "counts": {
            "mine": len(mine.people), "theirs": len(theirs.people),
            "matched": len(paired), "agreed": agreed,
            "conflicts": len(conflicts), "gains": len(gained),
            "only_theirs": len(only_theirs), "only_mine": len(only_mine),
        },
        # THE DISAGREEMENTS FIRST. Two dates for one birth mean one of you
        # has seen a record the other has not, and that is the single most
        # productive thing a family historian can be shown.
        "conflicts": conflicts[:limit],
        "gains": gained[:limit],
        "only_theirs": [brief(theirs, x) for x in
                        sorted(only_theirs,
                               key=lambda x: theirs.people[x].sort_key)][:limit],
        "only_mine": [brief(mine, x) for x in
                      sorted(only_mine,
                             key=lambda x: mine.people[x].sort_key)][:limit],
        "headline": _headline(len(paired), len(conflicts), len(gained),
                              len(only_theirs)),
    }


def _headline(matched: int, clashes: int, gains: int, new: int) -> str:
    bits = []
    if matched:
        bits.append(f"{matched} of the same people")
    if clashes:
        bits.append(f"{clashes} where you disagree")
    if gains:
        bits.append(f"{gains} where one of you knows more")
    if new:
        bits.append(f"{new} you have not got")
    return "; ".join(bits) or "Nothing in common — is this the same family?"


def compare_files(mine_path, theirs_path, *, theirs_name: str = "") -> dict:
    """Compare an open family file with a GEDCOM or another `.helix`."""
    import tempfile
    from pathlib import Path

    from ..graph.build import load
    from ..store.db import connect

    theirs_path = Path(theirs_path)
    if theirs_path.suffix.lower() in (".ged", ".gedcom"):
        from . import gedcom
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d) / "theirs.helix"
            con = connect(tmp)
            gedcom.import_file(str(theirs_path), con)
            theirs = load(con)
            con.close()
            return compare(load(connect(mine_path, create=False)), theirs,
                           theirs_name=theirs_name or theirs_path.name)
    return compare(load(connect(mine_path, create=False)),
                   load(connect(theirs_path, create=False)),
                   theirs_name=theirs_name or theirs_path.name)
