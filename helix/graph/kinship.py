"""How is this person related to me, as something a program can use.

`FamilyGraph.relationship` already answers this in English -- "second cousin
once removed" -- and English is exactly what you cannot sort, group, filter
or count with. Every feature that treats the file as an ARCHIVE rather than
as artwork needs the structure behind that sentence:

  * a sidebar that lists everyone by relation, closest first, needs a
    GROUP and a RANK
  * "don't draw the children of my great-aunts" needs a DEGREE and a
    REMOVAL to test against
  * a profile that says how distant somebody is needs a NUMBER
  * highlighting "everyone who is a cousin of the person I clicked" needs
    all of it, for every person at once

So it is computed once, here, and the four features read the same values.
Where they disagreed -- and an earlier attempt had the sidebar's idea of a
cousin and the filter's idea of a cousin drifting apart -- a person could
appear under "first cousins" and vanish when you allowed first cousins.

THE MEASUREMENT. Every blood relationship is one fact: the nearest ancestor
two people share, and how many steps each of them stands below it.

    up    steps from ME up to that shared ancestor
    down  steps from that ancestor down to THEM

    (1, 1) both one step below a shared parent .... brother or sister
    (2, 1) their parent is my grandparent ......... aunt or uncle
    (2, 2) our grandparents are the same .......... first cousin
    (3, 2) ....................................... first cousin once removed

which is the standard reading: the cousin DEGREE is one less than the
smaller of the two, and the REMOVAL is the difference between them.

MARRIED-IN IS NOT A DISTANCE. Your aunt's husband shares no ancestor with
you and the arithmetic above says "no relation", which is true and useless:
he is at every family gathering. He gets his own group, named for the
relative he is married to, and sorts next to them.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

# ------------------------------------------------------------------ groups --
#
# THE ORDER OF THE TABS, and it is a judgement rather than a formula. By raw
# path length a grandparent (2 steps) is nearer than a brother (2 steps, tie)
# and a great-grandparent (3) ties with an aunt (3), which is arithmetically
# true and not how anybody thinks about their family. Nobody puts their
# grandmother above their sister.
#
# So the familiar groups are listed deliberately, in the order people
# actually name them, and the long tail past third cousins falls back to the
# arithmetic. `key` is stable and is what the scoping settings store, so
# renaming a tab never silently changes which people a saved chart draws.
SELF = "self"
IMMEDIATE = "immediate"
GRANDPARENTS = "grandparents"
GRANDCHILDREN = "grandchildren"
AUNTS_UNCLES = "aunts_uncles"
NIECES_NEPHEWS = "nieces_nephews"
COUSINS_1 = "cousins_1"
GREAT_GRANDPARENTS = "great_grandparents"
GREAT_GRANDCHILDREN = "great_grandchildren"
COUSINS_1_REMOVED = "cousins_1_removed"
GREAT_AUNTS_UNCLES = "great_aunts_uncles"
COUSINS_2 = "cousins_2"
COUSINS_2_REMOVED = "cousins_2_removed"
COUSINS_3 = "cousins_3"
ANCESTORS_DISTANT = "ancestors_distant"
DESCENDANTS_DISTANT = "descendants_distant"
COUSINS_DISTANT = "cousins_distant"
MARRIED_IN = "married_in"
UNRELATED = "unrelated"

# rank, plural title, one line saying who is in it
_GROUPS: dict[str, tuple[int, str, str]] = {
    SELF: (0, "You", "Whose chart this is."),
    IMMEDIATE: (1, "Immediate family",
                "Parents, brothers and sisters, partners and children."),
    GRANDPARENTS: (2, "Grandparents", "Your parents' parents."),
    GRANDCHILDREN: (3, "Grandchildren", "Your children's children."),
    AUNTS_UNCLES: (4, "Aunts and uncles",
                   "Your parents' brothers and sisters."),
    NIECES_NEPHEWS: (5, "Nieces and nephews",
                     "Your brothers' and sisters' children."),
    COUSINS_1: (6, "First cousins", "You share a set of grandparents."),
    GREAT_GRANDPARENTS: (7, "Great-grandparents", "Three generations back."),
    GREAT_GRANDCHILDREN: (8, "Great-grandchildren",
                          "Three generations forward."),
    COUSINS_1_REMOVED: (9, "First cousins once removed",
                        "Your first cousins' children, and your parents' "
                        "first cousins."),
    GREAT_AUNTS_UNCLES: (10, "Great-aunts and great-uncles",
                         "Your grandparents' brothers and sisters."),
    COUSINS_2: (11, "Second cousins",
                "You share a set of great-grandparents."),
    COUSINS_2_REMOVED: (12, "Second cousins once removed",
                        "A generation either side of your second cousins."),
    COUSINS_3: (13, "Third cousins",
                "You share a set of great-great-grandparents."),
    ANCESTORS_DISTANT: (14, "Earlier ancestors",
                        "Four generations back and beyond."),
    DESCENDANTS_DISTANT: (15, "Later descendants",
                          "Four generations forward and beyond."),
    COUSINS_DISTANT: (16, "More distant cousins",
                      "Fourth cousins and beyond, and further removals."),
    MARRIED_IN: (17, "Married in",
                 "Husbands and wives of your blood relatives. No shared "
                 "ancestor, and no family is complete without them."),
    UNRELATED: (18, "No known relation",
                "In the file, but no path to you has been recorded yet."),
}


def group_title(key: str) -> str:
    return _GROUPS.get(key, (99, key, ""))[1]


def group_rank(key: str) -> int:
    return _GROUPS.get(key, (99, key, ""))[0]


def group_blurb(key: str) -> str:
    return _GROUPS.get(key, (99, key, ""))[2]


def all_groups() -> list[dict]:
    """Every group in tab order. The settings screen is built from this, so
    a group added here appears as a switch without any further wiring."""
    return [{"key": k, "title": t, "blurb": b, "rank": r}
            for k, (r, t, b) in sorted(_GROUPS.items(), key=lambda kv: kv[1][0])]


# ------------------------------------------------------------------- a kin --
@dataclass(frozen=True)
class Kin:
    """One person's relation to the subject.

    `up`/`down` are the two halves of the measurement. `degree` and
    `removed` are the cousin reading of them. `steps` is how far apart the
    two people are in the graph and is what "how distant are they" means.
    `through` is the relative a married-in person is married to.
    """

    pid: str
    group: str = UNRELATED
    label: str = "no known relationship"
    up: int = 0
    down: int = 0
    degree: int = -1          # cousin degree; -1 when not a cousin at all
    removed: int = 0
    steps: int = 99           # up + down: the plain distance
    blood: bool = False
    half: bool = False        # shares one parent, not two
    through: Optional[str] = None

    @property
    def rank(self) -> tuple:
        """Sort key inside the whole list: group first, then genuinely
        closer people, then the older of two equals."""
        return (group_rank(self.group), self.steps, self.up, self.down)

    def to_dict(self) -> dict:
        return {"id": self.pid, "group": self.group,
                "group_title": group_title(self.group),
                "label": self.label, "up": self.up, "down": self.down,
                "degree": self.degree, "removed": self.removed,
                "steps": self.steps, "blood": self.blood,
                "half": self.half, "through": self.through}


_ORDINALS = ["first", "second", "third", "fourth", "fifth", "sixth",
             "seventh", "eighth", "ninth", "tenth"]
_TIMES = {1: "once", 2: "twice", 3: "three times", 4: "four times"}


def _ordinal(n: int) -> str:
    return _ORDINALS[n - 1] if 1 <= n <= len(_ORDINALS) else f"{n}th"


def _greats(n: int, word: str) -> str:
    """'great-great-grandmother' without an off-by-one. `n` counts the
    generations, so 1 is a parent and 3 is a great-grandparent."""
    if n <= 1:
        return word
    if n == 2:
        return f"grand{word}"
    return "great-" * (n - 2) + f"grand{word}"


def describe(up: int, down: int, *, sex: str = "U", half: bool = False) -> str:
    """The English for one measurement, as specific as the sex allows.

    Sex is used where the language has a word for it and ignored where it
    does not -- there is no gendered word for a cousin, and inventing one
    would be worse than the neutral term.

    `half` is not cosmetic and is not optional. A half-brother shares one
    parent, so only half the ancestry above him is shared, and calling him
    a brother asserts a second parent nobody recorded. `schema.sql` and
    `FamilyGraph.sibling_kind` make the same distinction; this agrees with
    them rather than making its own.
    """
    if up == 0 and down == 0:
        return "you"
    if down == 0:                                   # straight up: my ancestor
        word = {"M": "father", "F": "mother"}.get(sex, "parent")
        return _greats(up, word)
    if up == 0:                                     # straight down
        word = {"M": "son", "F": "daughter"}.get(sex, "child")
        return _greats(down, word) if down > 1 else word
    if up == 1 and down == 1:
        word = {"M": "brother", "F": "sister"}.get(sex, "sibling")
        return f"half-{word}" if half else word
    if up == 1:                                     # my sibling's descendant
        word = {"M": "nephew", "F": "niece"}.get(sex, "nibling")
        return ("great-" * (down - 2) + word) if down > 2 else word
    if down == 1:                                   # my parent's sibling
        word = {"M": "uncle", "F": "aunt"}.get(sex, "aunt or uncle")
        return ("great-" * (up - 2) + word) if up > 2 else word
    lo, hi = sorted((up, down))
    deg, rem = lo - 1, hi - lo
    base = f"{_ordinal(deg)} cousin"
    if not rem:
        return base
    return f"{base} {_TIMES.get(rem, str(rem) + ' times')} removed"


def _group_for(up: int, down: int) -> str:
    if up == 0 and down == 0:
        return SELF
    if up <= 1 and down <= 1:                       # parent, child, sibling
        return IMMEDIATE
    if down == 0:
        return {2: GRANDPARENTS, 3: GREAT_GRANDPARENTS}.get(
            up, ANCESTORS_DISTANT)
    if up == 0:
        return {2: GRANDCHILDREN, 3: GREAT_GRANDCHILDREN}.get(
            down, DESCENDANTS_DISTANT)
    if down == 1:
        return AUNTS_UNCLES if up == 2 else GREAT_AUNTS_UNCLES
    if up == 1:
        return NIECES_NEPHEWS
    lo, hi = sorted((up, down))
    deg, rem = lo - 1, hi - lo
    if deg == 1:
        return COUSINS_1 if rem == 0 else (
            COUSINS_1_REMOVED if rem == 1 else COUSINS_DISTANT)
    if deg == 2:
        return COUSINS_2 if rem == 0 else (
            COUSINS_2_REMOVED if rem == 1 else COUSINS_DISTANT)
    if deg == 3 and rem == 0:
        return COUSINS_3
    return COUSINS_DISTANT


# ------------------------------------------------------------------- index --
class Kinship:
    """Everybody's relation to one subject, worked out once.

    Built in two passes over the whole file rather than by asking a
    relationship question per person, because the per-person form is
    quadratic: `FamilyGraph.relationship` walks both ancestor sets every
    time it is called, and a sidebar that lists four hundred people called
    it four hundred times. Here the subject's own ancestor set is walked
    once and everyone else is measured against it.
    """

    def __init__(self, graph, subject: Optional[str]):
        self.graph = graph
        self.subject = subject
        self.by_id: dict[str, Kin] = {}
        if not subject or subject not in graph.people:
            return
        self._build()

    # -- construction -------------------------------------------------------
    def _build(self) -> None:
        g, subj = self.graph, self.subject
        mine = g.ancestors(subj)                     # ancestor -> steps up

        # PASS ONE: everyone who descends from one of my ancestors. Taking
        # the SMALLEST up first means the nearest shared ancestor wins, which
        # is the whole definition -- read in any other order, a first cousin
        # can be reported as a fourth cousin through some older couple the
        # two families also share.
        for anc, up in sorted(mine.items(), key=lambda kv: kv[1]):
            for pid, down in g.descendants(anc).items():
                if pid in self.by_id:
                    continue
                self.by_id[pid] = self._make(pid, up, down)

        # PASS ONE AND A HALF: BROTHERS AND SISTERS WHOSE PARENTS ARE NOT IN
        # THE FILE.
        #
        # "My father had a brother" is a thing somebody types on their first
        # evening, long before they know either grandparent's name. It makes
        # a family with two children in it and NOBODY in the parents' row --
        # which is honest, and which pass one cannot see, because pass one
        # walks from person to person and there is no person there to walk
        # through. The uncle came out as "no known relation", and a chart
        # narrowed to blood relatives left him off.
        #
        # The union itself is the shared ancestor. It stands exactly where
        # the unnamed couple stands, so two children of it are one step
        # below a shared parent -- (1, 1), brother and sister -- and
        # everything downstream follows from that.
        #
        # ONLY where the union has no partners in the file. With a parent
        # present pass one has already measured everybody through them, and
        # measuring twice is how two answers start to disagree.
        empty = [u for u in g.unions.values()
                 if not any(x in g.people for x in u.partners)]
        if empty:
            up_of = {subj: 0, **mine}
            for u in empty:
                kids = [c for c in u.children if c in g.people]
                # How far up this family sits: one step above whichever of
                # its children the subject can already be measured from.
                base = min((up_of[c] for c in kids if c in up_of), default=None)
                if base is None:
                    continue
                for kid in kids:
                    for pid, down in g.descendants(kid).items():
                        if pid in self.by_id or pid == subj:
                            continue
                        self.by_id[pid] = self._make(pid, base + 1, down + 1)

        # PASS TWO: married in. Somebody with no shared ancestor who is
        # married to somebody who has one. Named for whoever they married,
        # so a cousin's wife reads as "married to your first cousin" and
        # not as a stranger in your file.
        for pid in g.people:
            if pid in self.by_id:
                continue
            best = None
            for mate in g.partners(pid):
                k = self.by_id.get(mate)
                if k and k.blood and (best is None or k.rank < best.rank):
                    best = k
            if best is not None:
                # The subject's OWN husband or wife is the one case where
                # the pattern breaks: "married to your you" is what it said
                # for a year, because the subject's own label is "you".
                if best.pid == subj:
                    sex = g.people[pid].sex if pid in g.people else "U"
                    label = {"M": "your husband",
                             "F": "your wife"}.get(sex, "married to you")
                else:
                    label = f"married to your {best.label}"
                self.by_id[pid] = Kin(
                    pid=pid, group=MARRIED_IN, label=label,
                    steps=best.steps + 1, blood=False, through=best.pid)
            else:
                self.by_id[pid] = Kin(pid=pid, group=UNRELATED,
                                      label="no known relationship",
                                      steps=99, blood=False)

    def _make(self, pid: str, up: int, down: int) -> Kin:
        g = self.graph
        sex = g.people[pid].sex if pid in g.people else "U"
        half = (up == 1 and down == 1
                and g.sibling_kind(self.subject, pid) == "half-sibling")
        lo, hi = sorted((up, down))
        return Kin(pid=pid, group=_group_for(up, down),
                   label=describe(up, down, sex=sex, half=half),
                   up=up, down=down,
                   degree=(lo - 1) if (up >= 2 and down >= 2) else -1,
                   removed=hi - lo, steps=up + down, blood=True, half=half)

    # -- reading ------------------------------------------------------------
    def of(self, pid: str) -> Kin:
        return self.by_id.get(pid) or Kin(pid=pid)

    def label(self, pid: str) -> str:
        return self.of(pid).label

    def groups(self) -> list[dict]:
        """The sidebar: every group that has anybody in it, in tab order,
        each holding its people closest-first then oldest-first.

        Empty groups are left out rather than shown empty. A tab that opens
        onto nothing is a promise the file cannot keep, and on a small
        family most of them would be empty.
        """
        buckets: dict[str, list[Kin]] = {}
        for k in self.by_id.values():
            buckets.setdefault(k.group, []).append(k)
        out = []
        for key, kins in sorted(buckets.items(),
                                key=lambda kv: group_rank(kv[0])):
            kins.sort(key=lambda k: (k.rank, _born(self.graph, k.pid),
                                     self.graph.people[k.pid].sort_key))
            out.append({"key": key, "title": group_title(key),
                        "blurb": group_blurb(key), "count": len(kins),
                        "people": [k.pid for k in kins]})
        return out

    def relatives_of(self, pid: str) -> dict[str, list[str]]:
        """Who is what TO SOMEBODY ELSE -- the highlight sets.

        Clicking a person should light up their brothers and sisters, their
        cousins and so on, not mine. That is a second measurement from a
        different origin, so it gets its own index rather than being read
        off this one.
        """
        other = Kinship(self.graph, pid)
        out: dict[str, list[str]] = {}
        for k in other.by_id.values():
            if k.pid == pid:
                continue
            out.setdefault(k.group, []).append(k.pid)
        return out


def _born(graph, pid: str) -> float:
    p = graph.people.get(pid)
    v = p.birth.sort_value if p else None
    return v if v is not None else 9e9


# ------------------------------------------------------------------ counting --
def siblings_of(graph, pid: str) -> list[str]:
    """Brothers and sisters through EITHER parent, so a half-sibling is a
    sibling here rather than a special case.

    Walks the FAMILY, not the parents: two children of a family whose
    parents are not recorded yet are still brother and sister, and "add a
    brother" on somebody with no parents creates the family that holds them.

    It lives here, in the module that owns the word "relation", and
    `server._person_detail` calls it. Written out twice the two drifted:
    the profile counted half-brothers and the sidebar did not.
    """
    fams = list(graph.people[pid].child_of_all)
    for par in graph.parents(pid, primary_only=False):
        fams.extend(graph.people[par].unions)
    out, seen = [], {pid}
    for uid in dict.fromkeys(fams):
        u = graph.unions.get(uid)
        if not u:
            continue
        for c in u.children:
            if c not in seen:
                seen.add(c)
                out.append(c)
    return out


def household(graph, pid: str) -> dict:
    """The numbers a profile page states about one person.

    Counted from the FILE, not from the drawn chart, and the difference
    matters: a chart narrowed to first cousins still has to be able to say
    "and four more children who are not shown", which it cannot do if the
    only numbers it has are the ones it drew.
    """
    sibs = siblings_of(graph, pid)
    kids = graph.children(pid)
    anc = graph.ancestors(pid)
    desc = graph.descendants(pid)
    full = [s for s in sibs if graph.sibling_kind(pid, s) == "sibling"]
    return {
        "siblings": len(sibs), "full_siblings": len(full),
        "half_siblings": len(sibs) - len(full),
        "children": len(kids),
        "partners": len(graph.partners(pid)),
        "ancestors_known": len(anc) - 1,
        "descendants_known": len(desc) - 1,
        "generations_back": max(anc.values()) if len(anc) > 1 else 0,
        "generations_forward": max(desc.values()) if len(desc) > 1 else 0,
    }


# ------------------------------------------------------------------ scoping --
@dataclass(frozen=True)
class KinFilter:
    """How far the chart spreads, and which relations it draws.

    Two controls, because they are two different questions and people ask
    them separately. HOW FAR: a distance, in cousin degrees and removals and
    generations. WHICH: named groups switched on and off, so "no cousins at
    all, but keep the great-aunts" is sayable.

    Everything is None or empty by default, which means everybody, which
    means a chart that has never touched this screen is the chart it always
    was.
    """

    groups: Optional[frozenset] = None     # None = every group allowed
    max_cousin_degree: Optional[int] = None   # 1 = first cousins, 0 = none
    max_removal: Optional[int] = None
    max_steps: Optional[int] = None
    max_up: Optional[int] = None           # generations back from you
    max_down: Optional[int] = None         # generations forward
    married_in: bool = True
    unrelated: bool = False

    @property
    def active(self) -> bool:
        return (self.groups is not None
                or self.max_cousin_degree is not None
                or self.max_removal is not None
                or self.max_steps is not None
                or self.max_up is not None or self.max_down is not None
                or not self.married_in or self.unrelated)

    def keep(self, k: Kin) -> bool:
        if k.group == SELF:
            return True                    # you are never filtered out
        if k.group == UNRELATED:
            return self.unrelated
        if k.group == MARRIED_IN:
            return self.married_in
        if self.groups is not None and k.group not in self.groups:
            return False
        if self.max_up is not None and k.up > self.max_up:
            return False
        if self.max_down is not None and k.down > self.max_down:
            return False
        if self.max_steps is not None and k.steps > self.max_steps:
            return False
        if k.degree >= 0:                  # a cousin of some degree
            if (self.max_cousin_degree is not None
                    and k.degree > self.max_cousin_degree):
                return False
            if self.max_removal is not None and k.removed > self.max_removal:
                return False
        return True

    def to_dict(self) -> dict:
        return {"groups": sorted(self.groups) if self.groups is not None else None,
                "max_cousin_degree": self.max_cousin_degree,
                "max_removal": self.max_removal, "max_steps": self.max_steps,
                "max_up": self.max_up, "max_down": self.max_down,
                "married_in": self.married_in, "unrelated": self.unrelated}

    @staticmethod
    def from_dict(d: Optional[dict]) -> "KinFilter":
        d = d or {}
        gr = d.get("groups")
        return KinFilter(
            groups=frozenset(gr) if gr else None,
            max_cousin_degree=_int_or_none(d.get("max_cousin_degree")),
            max_removal=_int_or_none(d.get("max_removal")),
            max_steps=_int_or_none(d.get("max_steps")),
            max_up=_int_or_none(d.get("max_up")),
            max_down=_int_or_none(d.get("max_down")),
            married_in=d.get("married_in", True) is not False,
            unrelated=bool(d.get("unrelated", False)))


def _int_or_none(v):
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


@dataclass
class Narrowed:
    """The result of narrowing a chart: who is left, and what was cut.

    `elided` is the point of the whole exercise. Take somebody's cousins off
    the chart and the chart must not pretend they never existed -- it says
    so, on their parent, with the number. A chart that silently drops people
    is worse than one that never had them, because you cannot tell the
    difference between a family of two and a family of nine you narrowed.
    """

    keep: set
    elided: dict                # person -> how many of their children are cut
    elided_below: dict          # person -> how many descendants in total
    elided_union: dict          # MARRIAGE -> how many of its children are cut
    kept_for_others: set        # on the chart only because somebody else needs
                                # them there: a link in a chain down to a
                                # survivor, or the other half of a couple


def narrow(graph, subject: Optional[str], filt: KinFilter,
           within: Optional[set] = None,
           index: Optional[Kinship] = None) -> Narrowed:
    """Apply a filter and keep the result CONNECTED.

    A chart is a tree and a tree cannot have a hole in the middle. Switch
    off "aunts and uncles" while leaving first cousins on and every cousin
    is left hanging from nobody -- so after the filter runs, anyone standing
    between a survivor and the subject is put back. They are listed in
    `added_for_the_chain` so the interface can say why somebody it was told
    to hide is still there.

    That is also the honest answer to a contradiction: you cannot draw your
    fourth cousin without drawing the ancestor the two of you share.
    """
    people = set(within if within is not None else graph.people)
    if not subject or subject not in graph.people or not filt.active:
        return Narrowed(people, {}, {}, {}, set())

    idx = index or Kinship(graph, subject)
    keep = {p for p in people if filt.keep(idx.of(p))}
    keep.add(subject)

    # ---- close it, and keep closing until it stops growing ---------------
    #
    # TWO RULES, and they feed each other, which is why this is a loop and
    # not two passes. Every survivor needs the chain of parents that joins
    # them to the subject, or the chart has a hole in the middle. Every
    # survivor also brings their partner, because a couple is one cell and
    # half a couple is not a smaller chart but a wrong one.
    #
    # Run once each, in either order, and the second rule feeds the first
    # with people the first has already been past: a great-uncle pulled in
    # as somebody's husband arrived after the chains were closed and stood
    # on the chart with neither parent on it. Run to a fixed point instead.
    # It terminates because the set only ever grows and the file is finite.
    added = set()
    for _round in range(40):
        before = len(keep)
        for pid in list(keep):
            cur, guard = pid, 0
            while guard < 120:
                guard += 1
                pars = [x for x in graph.parents(cur, primary_only=True)
                        if x in people]
                if not pars:
                    break
                for par in pars:
                    if par not in keep:
                        keep.add(par)
                        added.add(par)
                cur = pars[0]

        # A PARTNER OF SOMEBODY KEPT COMES TOO. A couple is one cell on
        # this chart -- two names, touching, and that IS the marriage -- so
        # half a couple is not a smaller chart, it is a wrong one. Say
        # "first cousins only" and a first cousin who married your second
        # cousin still brings their husband: he is there as somebody's
        # husband, not as a second cousin, and the alternative is a cell
        # with a hole in it.
        #
        # Switching married-in off is the deliberate way to say otherwise,
        # and then a partner nobody recorded is drawn as "Unknown", which is
        # what that mark has always been for.
        if filt.married_in:
            for pid in list(keep):
                for mate in graph.partners(pid):
                    if mate in people and mate not in keep:
                        keep.add(mate)
                        added.add(mate)
        if len(keep) == before:
            break

    # ---- what was cut, and from whom -------------------------------------
    #
    # PER MARRIAGE for the mark, per person for the profile, and they are
    # genuinely different numbers. A missing child has two parents, so
    # counting per person counts them twice -- "45 marks hiding 86 children"
    # on a chart that had cut 43 people. The mark belongs on the marriage
    # the children came from, which is also the one place on the chart where
    # there is somewhere to put it: the stem head.
    elided, below, per_union = {}, {}, {}
    for uid, u in graph.unions.items():
        if not any(p in keep for p in u.partners):
            continue
        gone = [c for c in u.children
                if c in people and c not in keep
                and (graph.people[c].child_of or uid) == uid]
        if gone:
            per_union[uid] = len(gone)
    for pid in keep:
        gone = [c for c in graph.children(pid) if c in people and c not in keep]
        if not gone:
            continue
        elided[pid] = len(gone)
        seen: set = set()
        for c in gone:
            seen |= {d for d in graph.descendants(c)
                     if d in people and d not in keep}
        below[pid] = len(seen)
    return Narrowed(keep, elided, below, per_union, added)


# ------------------------------------------------------------------- DNA ----
#
# HOW MUCH OF YOUR DNA SOMEBODY SHARES, from where they stand in the tree.
# This is the coefficient of relationship, and it falls straight out of the
# same two numbers everything else here reads.
#
#     you and a parent .......  50%     (1, 0)
#     you and a full sibling .  50%     (1, 1), two shared ancestors
#     you and a half sibling .  25%     (1, 1), one shared ancestor
#     you and a grandparent ..  25%     (2, 0)
#     you and an aunt ........  25%     (2, 1)
#     you and a first cousin .  12.5%   (2, 2)
#
# One rule produces all of them: halve for every step of the path, and
# double it when the path runs through a COUPLE both of whom you descend
# from, because there are then two paths and not one. That is exactly the
# difference between a brother and a half-brother.
#
# WHAT THIS IS NOT. It is an average, not a measurement. Beyond parents and
# children, inheritance is a lottery: real first cousins share anywhere from
# about 7% to 18%, and past third cousins two people can genuinely share
# none at all while being related exactly as the chart says. Every screen
# that shows this number has to say so, or it reads as a test result.
def shared_dna(graph, a: str, b: str, kin: Optional[Kin] = None) -> Optional[float]:
    """Expected share of autosomal DNA, 0..1.

    ZERO IS AN ANSWER, and it is the one somebody wants. A husband, a
    step-parent and a friend of the family share no ancestor, and the honest
    figure for all three is 0% -- not a blank, which reads as "the program
    could not work it out". `None` is kept for the one case where that is
    genuinely true: a person who is not in this file at all.
    """
    if a not in graph.people or b not in graph.people:
        return None
    if a == b:
        return 1.0
    k = kin if kin is not None else Kinship(graph, a).of(b)
    if not k.blood or k.steps >= 99:
        return 0.0
    if k.up == 0 or k.down == 0:            # a straight line up or down
        return 0.5 ** k.steps
    return _paths(graph, a, b, k.up, k.down) * 0.5 ** k.steps


def _paths(graph, a: str, b: str, up: int, down: int) -> int:
    """How many of the shared ancestors at this distance both descend from.

    Two, for a full sibling: mother and father. One, for a half sibling. It
    is the only thing that tells the two apart, and it is worth double the
    DNA.
    """
    A, B = graph.ancestors(a), graph.ancestors(b)
    shared = [x for x in A if x in B and A[x] == up and B[x] == down]
    return max(1, min(2, len(shared)))


def dna_display(share: Optional[float]) -> str:
    """A percentage somebody can read, and never more precision than the
    number deserves. 50%, 12.5%, 6.25%, 3.13%, 0.78% -- not 0.78125%.

    TWO DECIMALS AND NOT ONE, because every value here is 2^-n or twice it,
    and one decimal turns the exact 6.25 of a half-first-cousin into "6.2" --
    a number that is not right and does not look right either. Rounded to
    none at all, an earlier version made a first cousin "12%" and lost the
    half that is the whole point: 12.5 is a cousin and 12 is nothing in
    particular.

    HALF UP, not Python's half-to-even, for the same reason. `f"{3.125:.2f}"`
    is "3.12"; every table of cousin percentages ever printed says 3.13.
    """
    if share is None:
        return ""
    if not share:
        return "0%"
    pct = Decimal(share) * 100
    if pct < Decimal("0.01"):
        return "under 0.01%"
    q = pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{q}".rstrip("0").rstrip(".") + "%"


def bloodline(graph, pid: str, depth: int = 4) -> list[dict]:
    """Somebody's direct ancestry with the DNA share at every step.

    Half from each parent, a quarter from each grandparent, an eighth from
    each great-grandparent. The shape people already have in their heads,
    which is why it is worth drawing small on a profile: it says at a glance
    where somebody's DNA came from and which of those seats are empty.

    Positions are numbered as in an Ahnentafel -- 1 is the person, 2 their
    father, 3 their mother, 2n and 2n+1 the parents of n -- so an empty seat
    is a hole in the research with an address, not a missing item in a list.
    """
    out: list[dict] = []
    seats = {1: pid}
    for slot in range(1, 2 ** depth):
        gen = slot.bit_length() - 1
        here = seats.get(slot)
        row = {"slot": slot, "gen": gen, "share": 0.5 ** gen,
               "id": here, "name": "", "life": "", "sex": ""}
        if here and here in graph.people:
            p = graph.people[here]
            row.update(name=p.full_name, life=p.lifespan, sex=p.sex)
            pars = graph.parents(here, primary_only=True) or graph.parents(here)
            pars = [x for x in pars if x in graph.people]
            father = next((x for x in pars if graph.people[x].sex == "M"), None)
            mother = next((x for x in pars if graph.people[x].sex == "F"), None)
            rest = [x for x in pars if x not in (father, mother)]
            if father is None and rest:
                father = rest.pop(0)
            if mother is None and rest:
                mother = rest.pop(0)
            if father:
                seats[slot * 2] = father
            if mother:
                seats[slot * 2 + 1] = mother
        out.append(row)
    return out


# ------------------------------------------------------------- heritage ----
#
# WHERE SOMEBODY CAME FROM, carried down the tree the same way DNA is. An
# Irish grandmother makes you a quarter Irish; two of them make you half.
# Recorded on whoever is known to have it and inherited by everybody below.
#
# THIS IS A GENERALISATION AND THE INTERFACE MUST SAY SO. It assumes a
# person's heritage is exactly the average of their parents', which is a
# reasonable way to talk about a family and not a fact about anybody's
# genome. Where a parent is unrecorded that half is simply unaccounted for,
# which is the honest answer -- not something to normalise away, because the
# gap is the interesting part.
def heritage_of(graph, declared: dict, pid: str,
                depth: int = 12) -> dict[str, float]:
    """The mix somebody inherits, as {label: share}, shares summing to <= 1.

    `declared` is {person: {label: share}} -- what somebody has been told
    about directly. A person's OWN declaration wins outright over anything
    inherited: recording that your grandmother was Irish is a statement
    about her, not a guess to be averaged with her parents'.
    """
    seen: dict[str, dict[str, float]] = {}

    def walk(who: str, left: int) -> dict[str, float]:
        if who in seen:
            return seen[who]
        mine = declared.get(who)
        if mine:
            seen[who] = dict(mine)
            return seen[who]
        if left <= 0:
            seen[who] = {}
            return seen[who]
        seen[who] = {}                       # guard against a cycle in the file
        pars = [x for x in (graph.parents(who, primary_only=True)
                            or graph.parents(who)) if x in graph.people][:2]
        out: dict[str, float] = {}
        for par in pars:
            for label, share in walk(par, left - 1).items():
                out[label] = out.get(label, 0.0) + share / 2.0
        seen[who] = out
        return out

    got = walk(pid, depth)
    return {k: v for k, v in sorted(got.items(), key=lambda kv: -kv[1])
            if v > 0.0005}


def heritage_display(mix: dict[str, float]) -> list[dict]:
    """Ready to show: label, percentage, and what is unaccounted for.

    The remainder is named rather than hidden. "62% Irish" with nothing else
    on the line reads as a rounding error; "62% Irish, 38% not recorded"
    reads as research still to do, which is what it is.
    """
    out = [{"label": k, "share": v, "pct": round(v * 100, 1)}
           for k, v in mix.items()]
    known = sum(x["share"] for x in out)
    if known < 0.999:
        out.append({"label": "not recorded", "share": 1 - known,
                    "pct": round((1 - known) * 100, 1), "gap": True})
    return out


# --------------------------------------------------- any two people ---------
#
# "HOW ARE THESE TWO RELATED?" is the question a family history is asked
# more often than any other, and until this the program could only answer it
# about one person -- whoever the chart was centred on. Everything needed
# was already here; what was missing was the path.
#
# THE PATH IS THE ANSWER, not the label. "Second cousins once removed" is a
# fact nobody repeats. "Up to Elias Whitcombe, who was your
# great-grandfather and her great-great-grandfather" is what gets said at a
# funeral, and it is also the only form somebody can check against their own
# research.
@dataclass(frozen=True)
class Step:
    """One person on the path between two others.

    `life` is not decoration. Four Alice Whitcombes in one parish is the
    ordinary case, not the odd one, and a path that names two of them
    without dates cannot be checked against anybody's own research.
    """
    pid: str
    name: str
    move: str = "up"          # up | top | down | married
    note: str = ""
    life: str = ""

    def to_dict(self) -> dict:
        return {"id": self.pid, "name": self.name, "move": self.move,
                "note": self.note, "life": self.life}


@dataclass(frozen=True)
class Relation:
    """How two people are related, and the way through."""
    a: str
    b: str
    related: bool = False
    label: str = "no known relationship"
    a_of_b: str = ""           # what A is TO B: "her second cousin"
    b_of_a: str = ""
    kin: Optional[Kin] = None
    ancestors: tuple = ()
    path: tuple = ()
    dna: Optional[float] = None

    def to_dict(self) -> dict:
        return {"a": self.a, "b": self.b, "related": self.related,
                "label": self.label, "a_of_b": self.a_of_b,
                "b_of_a": self.b_of_a,
                "kin": self.kin.to_dict() if self.kin else None,
                "ancestors": list(self.ancestors),
                "path": [s.to_dict() for s in self.path],
                "dna": self.dna, "dna_display": dna_display(self.dna)}


def _walk_up(graph, start: str, target: str, limit: int = 40) -> list[str]:
    """The chain of people from `start` up to `target`, both included.

    Breadth-first over parents, so the SHORTEST way up wins. In a file where
    cousins married, two people share an ancestor by more than one route and
    the near one is the one that describes the relation.
    """
    if start == target:
        return [start]
    seen, queue = {start: None}, [start]
    while queue:
        cur = queue.pop(0)
        for par in graph.parents(cur, primary_only=False):
            if par in seen or par not in graph.people:
                continue
            seen[par] = cur
            if par == target:
                chain, node = [], par
                while node is not None:
                    chain.append(node)
                    node = seen[node]
                return list(reversed(chain))
            if len(seen) < limit * 60:
                queue.append(par)
    return []


def relate(graph, a: str, b: str, index: Optional["Kinship"] = None) -> Relation:
    """How A and B are related, with the way through spelt out.

    Reads `Kinship` for the measurement rather than deciding for itself what
    a cousin is -- rule nine. What it adds is the route: up from A to the
    ancestor they share, and down from there to B.
    """
    if a not in graph.people or b not in graph.people:
        return Relation(a, b)
    name = lambda p: graph.people[p].full_name if p in graph.people else "?"
    life = lambda p: graph.people[p].lifespan if p in graph.people else ""
    step = lambda p, move, note="": Step(p, name(p), move, note, life(p))
    if a == b:
        return Relation(a, b, True, "the same person", "", "",
                        path=(step(a, "top"),), dna=1.0)

    idx = index or Kinship(graph, a)
    k = idx.of(b)                       # what B is to A
    back = Kinship(graph, b).of(a)      # and what A is to B
    dna = shared_dna(graph, a, b, k)

    if k.blood and k.steps < 99:
        A, B = graph.ancestors(a), graph.ancestors(b)
        shared = sorted(x for x in A if x in B
                        and A[x] == k.up and B[x] == k.down)
        top = shared[0] if shared else None
        path: list[Step] = []
        if top:
            # Two shared ancestors at the same distance means a COUPLE, and
            # a couple is the ordinary case -- it is exactly what tells a
            # full sibling from a half one, and worth twice the DNA. Said on
            # the one line where the path turns round.
            both = (f"and {name(shared[1])} — the couple they both descend from"
                    if len(shared) > 1 else "the nearest ancestor they share")
            if top in (a, b):
                both = ""          # a straight line down: nobody "shares" it
            up = _walk_up(graph, a, top)
            down = _walk_up(graph, b, top)
            for pid in up:
                path.append(step(pid, "top" if pid == top else "up",
                                 both if pid == top else ""))
            for pid in reversed(down[:-1]):     # the shared one is already on
                path.append(step(pid, "down"))
        return Relation(a, b, True, k.label, back.label, k.label, k,
                        tuple(shared[:2]), tuple(path), dna)

    if k.group == MARRIED_IN and k.through:
        thr = relate(graph, a, k.through, idx)
        path = list(thr.path) + [step(b, "married",
                                      f"married {name(k.through)}")]
        return Relation(a, b, True, k.label, back.label, k.label, k,
                        thr.ancestors, tuple(path), 0.0)

    return Relation(a, b, False, "no known relationship", back.label,
                    k.label, k, (), (), dna)
