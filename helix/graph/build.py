"""Load the database into an in-memory graph.

Single responsibility: turn rows into objects and answer relationship
questions. No layout, no rendering, no SQL outside this package.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..model.gendate import GenDate, age_at


@dataclass
class Person:
    id: str
    given: str = ""
    given_used: str = ""
    surname: str = ""
    surname_prefix: str = ""
    suffix: str = ""
    sex: str = "U"
    birth: GenDate = field(default_factory=GenDate)
    death: GenDate = field(default_factory=GenDate)
    birth_place: str = ""
    death_place: str = ""
    occupation: str = ""
    education: str = ""
    confidence: int = 2
    is_placeholder: bool = False
    living: Optional[bool] = None
    tags: list[str] = field(default_factory=list)

    # graph edges (filled by FamilyGraph)
    child_of: Optional[str] = None          # primary union id
    child_of_all: list[str] = field(default_factory=list)
    unions: list[str] = field(default_factory=list)

    @property
    def given_first(self) -> str:
        return (self.given_used or self.given or "").split(" ")[0]

    @property
    def initials(self) -> str:
        parts = [p[0] for p in (self.given or "").split() if p]
        return "".join(parts) + (self.surname[:1] if self.surname else "")

    @property
    def full_name(self) -> str:
        bits = [self.given, self.surname_prefix, self.surname, self.suffix]
        return " ".join(b for b in bits if b).strip() or "[Unknown]"

    @property
    def short_name(self) -> str:
        return f"{self.given_first} {self.surname}".strip() or "[Unknown]"

    @property
    def sort_key(self) -> str:
        """Filing order: surname first, uppercased so that de la Mare and
        DELAMARE land together rather than either side of the alphabet."""
        return f"{(self.surname or '~').upper()}, {(self.given or '').upper()}"

    @property
    def birth_year(self) -> Optional[int]:
        return self.birth.year

    @property
    def death_year(self) -> Optional[int]:
        return self.death.year

    @property
    def lifespan(self) -> str:
        b = self.birth_year or ""
        d = self.death_year or ("" if self.death.known or self.living is False else "")
        if not b and not d:
            return ""
        return f"{b}\u2013{d}"

    @property
    def age(self) -> str:
        return age_at(self.birth, self.death).display


@dataclass
class Union:
    id: str
    partners: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    type: str = "marriage"
    date: GenDate = field(default_factory=GenDate)
    place: str = ""


class FamilyGraph:
    """The whole family in memory. Rebuild on every edit; it is cheap."""

    def __init__(self, people: dict[str, Person], unions: dict[str, Union],
                 subject_id: Optional[str] = None):
        self.people = people
        self.unions = unions
        self.subject_id = subject_id
        self._dom: Optional[dict[str, str]] = None

    # ------------------------------------------------------------- structure
    def parents(self, pid: str, primary_only: bool = True) -> list[str]:
        p = self.people.get(pid)
        if not p:
            return []
        uids = [p.child_of] if primary_only and p.child_of else p.child_of_all
        out: list[str] = []
        for u in uids:
            if u and u in self.unions:
                out.extend(self.unions[u].partners)
        return out

    def children(self, pid: str) -> list[str]:
        out: list[str] = []
        for u in self.people[pid].unions:
            out.extend(self.unions[u].children)
        return out

    def partners(self, pid: str) -> list[str]:
        out: list[str] = []
        for u in self.people[pid].unions:
            out.extend(x for x in self.unions[u].partners if x != pid)
        return out

    def siblings(self, pid: str, full: bool = False) -> list[str]:
        p = self.people[pid]
        if not p.child_of:
            return []
        sibs = [c for c in self.unions[p.child_of].children if c != pid]
        return sibs

    def apexes(self) -> list[str]:
        """People with no known parents: the natural centres of a chart."""
        return [pid for pid, p in self.people.items() if not p.child_of_all]

    # ------------------------------------------------------------ traversal
    def ancestors(self, pid: str, max_gen: Optional[int] = None) -> dict[str, int]:
        seen = {pid: 0}
        frontier = [pid]
        g = 0
        while frontier and (max_gen is None or g < max_gen):
            g += 1
            nxt = []
            for x in frontier:
                for par in self.parents(x, primary_only=False):
                    if par not in seen:
                        seen[par] = g
                        nxt.append(par)
            frontier = nxt
        return seen

    def descendants(self, pid: str, max_gen: Optional[int] = None) -> dict[str, int]:
        seen = {pid: 0}
        frontier = [pid]
        g = 0
        while frontier and (max_gen is None or g < max_gen):
            g += 1
            nxt = []
            for x in frontier:
                for kid in self.children(x):
                    if kid not in seen:
                        seen[kid] = g
                        nxt.append(kid)
            frontier = nxt
        return seen

    def generation_of(self, pid: str, roots: list[str]) -> int:
        """Depth below the nearest root, following primary edges only."""
        d, cur, guard = 0, pid, 0
        rootset = set(roots)
        while cur not in rootset and guard < 200:
            pars = self.parents(cur)
            if not pars:
                break
            cur = pars[0]
            d += 1
            guard += 1
        return d

    def mrca(self, a: str, b: str) -> Optional[tuple[str, int, int]]:
        A, B = self.ancestors(a), self.ancestors(b)
        common = set(A) & set(B)
        if not common:
            return None
        best = min(common, key=lambda x: (A[x] + B[x], A[x]))
        return best, A[best], B[best]

    def relationship(self, a: str, b: str) -> str:
        """Plain-English relationship, e.g. 'second cousin once removed'."""
        if a == b:
            return "the same person"
        A, B = self.ancestors(a), self.ancestors(b)
        if b in A:
            return _direct(A[b], "ancestor")
        if a in B:
            return _direct(B[a], "descendant")
        m = self.mrca(a, b)
        if not m:
            return "no known relationship"
        _, da, db = m
        if da == 1 and db == 1:
            return self.sibling_kind(a, b)
        lo, hi = sorted((da, db))
        deg = lo - 1
        removed = hi - lo
        if deg == 0:
            return _direct(hi - 1, "aunt/uncle" if da > db else "niece/nephew")
        names = ["first", "second", "third", "fourth", "fifth", "sixth",
                 "seventh", "eighth", "ninth", "tenth"]
        base = f"{names[deg-1] if deg <= 10 else str(deg)+'th'} cousin"
        if removed == 0:
            return base
        r = {1: "once", 2: "twice", 3: "three times"}.get(removed, f"{removed} times")
        return f"{base} {r} removed"

    def sibling_kind(self, a: str, b: str) -> str:
        """'sibling' or 'half-sibling'.

        The distinction is not cosmetic. A half-sibling shares one parent, so
        only half the ancestry above them is shared, and a chart that calls
        them a full sibling is asserting a second parent nobody recorded.
        """
        pa = set(self.parents(a, primary_only=False))
        pb = set(self.parents(b, primary_only=False))
        shared = pa & pb
        if not shared:
            return "no known relationship"
        if len(shared) >= 2 or (pa == pb and len(pa) >= 2):
            return "sibling"
        return "half-sibling"

    def half_siblings(self, pid: str) -> list[str]:
        """Everyone sharing exactly one parent with `pid`."""
        out: list[str] = []
        for par in self.parents(pid, primary_only=False):
            for c in self.children(par):
                if c != pid and c not in out and \
                        self.sibling_kind(pid, c) == "half-sibling":
                    out.append(c)
        return out

    def endogamy(self) -> list[str]:
        """People reachable by more than one distinct ancestral path
        (pedigree collapse). Their existence is why the chart is a DAG."""
        return [pid for pid, p in self.people.items() if len(p.child_of_all) > 1]

    # ------------------------------------------------------------- summary
    def stats(self) -> dict:
        yrs = [p.birth_year for p in self.people.values() if p.birth_year]
        return {
            "people": len(self.people),
            "unions": len(self.unions),
            "earliest_year": min(yrs) if yrs else None,
            "latest_year": max(yrs) if yrs else None,
            "apexes": len(self.apexes()),
            "with_birth_year": len(yrs),
        }


def _direct(n: int, kind: str) -> str:
    if kind == "ancestor":
        return {1: "parent", 2: "grandparent", 3: "great-grandparent"}.get(
            n, f"{n-2}x great-grandparent")
    if kind == "descendant":
        return {1: "child", 2: "grandchild", 3: "great-grandchild"}.get(
            n, f"{n-2}x great-grandchild")
    great = "great-" * max(0, n - 1)
    return great + kind


# ============================================================ loading =======
def load(con, subject_id: Optional[str] = None) -> FamilyGraph:
    from ..model.gendate import GenDate as GD

    places = {r["id"]: r["name"] for r in con.execute("SELECT id,name FROM place")}
    people: dict[str, Person] = {}
    for r in con.execute("SELECT * FROM v_person"):
        people[r["id"]] = Person(
            id=r["id"], given=r["given"] or "", given_used=r["given_used"] or "",
            surname=r["surname"] or "", surname_prefix=r["surname_prefix"] or "",
            suffix=r["suffix"] or "", sex=r["sex"],
            birth=GD.from_json(r["birth_json"]), death=GD.from_json(r["death_json"]),
            confidence=r["confidence"], is_placeholder=bool(r["is_placeholder"]),
            living=None if r["living"] is None else bool(r["living"]),
        )

    for r in con.execute(
        "SELECT er.person_id pid, e.type t, e.description d, p.name pl "
        "FROM event e JOIN event_role er ON er.event_id=e.id "
        "LEFT JOIN place p ON p.id=e.place_id "
        "WHERE e.type IN ('birth','death','occupation','education')"
    ):
        p = people.get(r["pid"])
        if not p:
            continue
        if r["t"] == "birth":
            p.birth_place = r["pl"] or ""
        elif r["t"] == "death":
            p.death_place = r["pl"] or ""
        elif r["t"] == "occupation":
            p.occupation = r["d"] or ""
        elif r["t"] == "education":
            p.education = r["d"] or ""

    unions: dict[str, Union] = {}
    for r in con.execute("SELECT * FROM union_"):
        unions[r["id"]] = Union(id=r["id"], type=r["type"])
    for r in con.execute("SELECT * FROM union_partner ORDER BY seq"):
        if r["union_id"] in unions:
            unions[r["union_id"]].partners.append(r["person_id"])
            if r["person_id"] in people:
                people[r["person_id"]].unions.append(r["union_id"])
    for r in con.execute("SELECT * FROM union_child ORDER BY birth_order"):
        u = unions.get(r["union_id"])
        p = people.get(r["person_id"])
        if not u or not p:
            continue
        u.children.append(r["person_id"])
        p.child_of_all.append(r["union_id"])
        if r["is_primary"]:
            p.child_of = r["union_id"]
    for u in unions.values():
        u.children.sort(key=lambda c: (people[c].birth.sort_value or 9e9,
                                       people[c].short_name))
    for r in con.execute(
        "SELECT er.union_id uid, e.date_json dj, p.name pl FROM event e "
        "JOIN event_role er ON er.event_id=e.id LEFT JOIN place p ON p.id=e.place_id "
        "WHERE e.type='marriage' AND er.union_id IS NOT NULL"
    ):
        u = unions.get(r["uid"])
        if u:
            u.date = GD.from_json(r["dj"])
            u.place = r["pl"] or ""
    for r in con.execute(
        "SELECT pt.person_id pid, t.name n FROM person_tag pt JOIN tag t ON t.id=pt.tag_id"
    ):
        if r["pid"] in people:
            people[r["pid"]].tags.append(r["n"])

    if subject_id is None:
        from ..store.db import get_setting
        subject_id = get_setting(con, "subject_person_id")
    return FamilyGraph(people, unions, subject_id)
