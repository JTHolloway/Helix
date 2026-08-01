"""Research gap ranking -- 'what should I look for next?'

This turns the chart into a to-do list, which is the difference between a
poster and a working research tool.

SCORE for each missing fact:
    score = descendants_affected
          * source_availability(year, country, record_type)
          * (1 / effort)

  descendants_affected  people whose line is blocked by this gap. A missing
                        1790 birth that blocks 400 descendants beats a missing
                        1890 occupation that blocks nobody.
  source_availability   England & Wales: civil registration from Jul 1837,
                        censuses 1841-1921, parish registers from 1538 with
                        a large gap during the Commonwealth (1642-1660).
                        Scotland: statutory from 1855, far richer.
                        Ireland: much destroyed in 1922 -- weight down.
  effort                free online (1) < paid index (2) < record office
                        visit (5) < overseas archive (10).

OUTPUT
  A ranked list of questions: "Who were Sarah Pargeter's parents? The line
  stops here -- 47 people descend from Sarah with nothing beyond. Try the
  1881 census."

  COMPUTED ON EVERY READ, and not written to `research_task`. The rows there
  are for what somebody has DECIDED to chase -- with a status, a repository
  and a result -- and they stay put until they are answered. This list is
  derived from the state of the file, so a gap that gets filled in leaves it
  the same second. Stored, it would be a to-do list of things already done.

WHY THE SCORE IS THREE FACTORS AND NOT ONE. Ranked by reach alone the list
opens with a 1600s couple whose records burned; ranked by findability alone
it opens with a great-aunt's middle name. The product is what puts a
findable, cheap, high-reach question at the top -- which is the only kind
worth doing on a Saturday morning.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------- the tables

# What it costs to answer a question of each kind. Free online is 1; a day
# in a county record office is 5; writing to an archive abroad is 10.
EFFORT = {
    "parents":     2.0,     # index search, sometimes a certificate
    "spouse":      2.0,
    "birth":       1.6,
    "death":       1.6,
    "marriage":    2.0,
    "birth_place": 1.2,     # usually already on a record you have
    "death_place": 1.4,
    "occupation":  1.2,     # census, free to search
    "name":        1.0,     # ask a relative
    "photo":       1.0,     # a shoebox, not an archive
    "story":       1.0,     # a telephone call, and it expires
}

# How much a gap of each kind is worth answering, before reach and
# findability are applied. Parents open a whole line; an occupation adds
# colour to one person.
WEIGHT = {
    "parents":     3.0,
    "spouse":      1.4,
    "birth":       1.5,
    "death":       0.9,
    "marriage":    0.8,
    "birth_place": 1.1,
    "death_place": 0.5,
    "occupation":  0.4,
    "name":        1.8,
    "photo":       0.6,
    "story":       1.2,
}

QUESTION = {
    "parents":     "Who were {name}'s parents?",
    "spouse":      "Who did {name} marry?",
    "birth":       "When was {name} born?",
    "death":       "When did {name} die?",
    "marriage":    "When did {name} marry?",
    "birth_place": "Where was {name} born?",
    "death_place": "Where did {name} die?",
    "occupation":  "What did {name} do for a living?",
    "name":        "What was {name}'s full name?",
    "photo":       "Is there a photograph of {name}?",
    "story":       "What does anyone remember about {name}?",
}


def _findable(year: Optional[int], kind: str, country: str) -> float:
    """How likely a record is to exist and be reachable, 0..1.

    Deliberately coarse. The point is to sort a list, not to promise
    anything: a 0.9 means 'the register almost certainly survives', not
    'you will find them'.
    """
    c = (country or "england").lower()

    # Nothing to date it by. Assume the middling case rather than dropping
    # the gap off the list -- an undated ancestor is usually the one most
    # worth chasing.
    if year is None:
        return 0.45

    # Living memory. No public record yet, but somebody can be asked, and
    # that source is the one with a deadline on it.
    if year >= 1975:
        return 0.85 if kind in ("story", "photo", "name", "occupation") else 0.5
    if year >= 1930:
        # Closure rules: births 100 years, marriages 75, deaths 50.
        if kind in ("story", "photo"):
            return 0.9
        if kind == "birth" and year >= 1926:
            return 0.35

    if c.startswith("scot"):
        if year >= 1855:
            return 0.95            # statutory registers, images online
        if year >= 1553:
            return 0.6             # old parish registers, patchy but indexed
        return 0.15

    if c.startswith("ire") or c.startswith("north"):
        # The Public Record Office burned in 1922 and took most of the
        # nineteenth-century censuses and a great deal of Church of Ireland
        # material with it.
        if year >= 1864:
            return 0.7             # civil registration survives
        if year >= 1845:
            return 0.5             # non-Catholic marriages from 1845
        return 0.2

    if c.startswith("us") or c.startswith("america"):
        if 1850 <= year <= 1950:
            return 0.85            # federal census, named individuals
        if year >= 1790:
            return 0.45
        return 0.2

    # England & Wales, and the default.
    if kind in ("birth", "death", "marriage") and year >= 1837:
        return 0.95                # civil registration from July 1837
    if kind in ("occupation", "birth_place") and 1841 <= year <= 1921:
        return 0.9                 # the censuses say both, and are indexed
    if year >= 1837:
        return 0.8
    if 1813 <= year < 1837:
        return 0.8                 # Rose's Act: printed, ruled registers
    if 1660 <= year < 1813:
        return 0.62
    if 1642 <= year < 1660:
        return 0.2                 # Civil War and Commonwealth: the great gap
    if 1538 <= year < 1642:
        return 0.4                 # registers begin, survival is luck
    return 0.08


def _year_near(graph, pid: str, depth: int = 2) -> Optional[int]:
    """A year to judge findability by -- theirs, or borrowed from close kin.

    Somebody with no dates at all is exactly the person a gap list should be
    pointing at, so refusing to score them would defeat the purpose. A
    parent's year minus thirty is a poor estimate and a perfectly good sort
    key.
    """
    p = graph.people.get(pid)
    if not p:
        return None
    for y in (p.birth_year, p.death_year):
        if y:
            return y
    if depth <= 0:
        return None
    for kid in graph.children(pid):
        y = _year_near(graph, kid, depth - 1)
        if y:
            return y - 30
    for par in graph.parents(pid, primary_only=False):
        y = _year_near(graph, par, depth - 1)
        if y:
            return y + 30
    for sp in graph.partners(pid):
        y = _year_near(graph, sp, 0)
        if y:
            return y
    return None


def _country(graph, pid: str, fallback: str) -> str:
    """Guess where to look, from whatever place is recorded."""
    p = graph.people.get(pid)
    words = " ".join(filter(None, [getattr(p, "birth_place", ""),
                                   getattr(p, "death_place", "")])).lower()
    for needle, name in (("scotland", "scotland"), ("ireland", "ireland"),
                         ("wales", "england"), ("united states", "usa"),
                         ("u.s.", "usa"), ("usa", "usa"), ("canada", "usa"),
                         ("australia", "australia"), ("england", "england")):
        if needle in words:
            return name
    return fallback


@dataclass
class Gap:
    """One question worth asking, about one person."""
    pid: str
    kind: str
    question: str
    reach: int                       # people whose line this gap blocks
    score: float
    findable: float
    effort: float
    year: Optional[int] = None
    country: str = "england"
    name: str = ""
    life: str = ""
    why: str = ""
    where: list[str] = field(default_factory=list)
    # Filled in by the server, which is the only place that knows who is
    # asking. TWO PEOPLE CALLED "HARRIS" and nothing else recorded is
    # exactly the case this list is for, and two identical lines is exactly
    # how not to present it.
    relation: str = ""

    def to_dict(self) -> dict:
        return {"pid": self.pid, "kind": self.kind, "question": self.question,
                "reach": self.reach, "score": round(self.score, 3),
                "findable": round(self.findable, 2), "effort": self.effort,
                "year": self.year, "country": self.country, "name": self.name,
                "life": self.life, "relation": self.relation,
                "why": self.why, "where": self.where}


# Where to actually go and look. Named repositories, not "search online",
# because rule 8 says every message says what to do next and a research
# prompt with no next step is a nag.
def _where(kind: str, year: Optional[int], country: str) -> list[str]:
    c = (country or "england").lower()
    y = year or 1850
    out: list[str] = []
    if c.startswith("scot"):
        out.append("ScotlandsPeople — statutory registers from 1855, "
                   "old parish registers before that")
    elif c.startswith("ire"):
        out.append("IrishGenealogy.ie — civil registration images, free")
        if y < 1900:
            out.append("The National Archives of Ireland census "
                       "fragments and Griffith's Valuation")
    elif c.startswith("us"):
        out.append("FamilySearch — US federal census 1850–1950, free")
    else:
        if kind in ("birth", "death", "marriage") and y >= 1837:
            out.append("GRO index (gro.gov.uk) — birth and death indexes "
                       "with mother's maiden name, free to search")
            out.append("FreeBMD — the same indexes, transcribed")
        if 1841 <= y <= 1921 and kind in ("occupation", "birth_place",
                                          "parents", "spouse", "birth"):
            out.append(f"The {_census_near(y)} census — names everyone in the "
                       "household with ages and birthplaces")
        if y < 1841:
            out.append("Parish registers for the relevant parish — "
                       "FamilySearch, then the county record office")
        if y < 1858 and kind in ("death", "parents"):
            out.append("Wills proved in the church courts before 1858 "
                       "(TNA PROB 11 for the PCC)")
    if kind in ("story", "photo", "name"):
        out.insert(0, "Ask the oldest relative who knew them. "
                      "Record the conversation.")
    # NEVER AN EMPTY LIST. Rule 8 -- every message says what to do next --
    # applies to a research prompt as much as to an error: a question with
    # nowhere to look is a nag. The branches above cover the common cases
    # and miss the corners (a twentieth-century birthplace fell through
    # every one of them), so this is the floor rather than a decoration.
    if not out:
        if y >= 1921:
            out.append("The birth, marriage or death certificate itself — "
                       "it names places, occupations and an informant the "
                       "index does not")
            out.append("Ask a relative who might remember, and write down "
                       "what they say")
        else:
            out.append("FamilySearch and FreeBMD — free, and the widest "
                       "index to start from")
            out.append("The county record office for wherever they lived")
    return out[:3]


def _census_near(year: int) -> int:
    cens = [1841, 1851, 1861, 1871, 1881, 1891, 1901, 1911, 1921]
    return min(cens, key=lambda c: abs(c - year))


def _is_dead(graph, p) -> bool:
    """Would a death record exist? Assume so if born before 1930 or if
    anyone recorded a death at all."""
    if p.living is True:
        return False
    if p.death_year or p.death.kind not in ("unknown", "none", ""):
        return True
    b = p.birth_year
    return bool(b and b < 1930)


def _gaps_for(graph, pid: str, reach: dict[str, int], country: str,
              placeholders: set[str], married_in: bool = False) -> list[Gap]:
    p = graph.people[pid]
    n = max(1, reach.get(pid, 1))
    year = _year_near(graph, pid)
    c = _country(graph, pid, country)
    out: list[Gap] = []

    def add(kind: str, why: str) -> None:
        f = _findable(year, kind, c)
        e = EFFORT.get(kind, 2.0)
        score = n * WEIGHT.get(kind, 1.0) * f / e
        out.append(Gap(pid=pid, kind=kind,
                       question=QUESTION[kind].format(name=p.short_name),
                       reach=n, score=score, findable=f, effort=e, year=year,
                       country=c, name=p.full_name, life=p.lifespan, why=why,
                       where=_where(kind, year, c)))

    # WHOSE LINES ARE WORTH FOLLOWING is decided by who the chart belongs
    # to, and only by that.
    #
    # A person who married into the family is at every gathering and is not
    # somebody whose parents you are researching. Their line is a different
    # family's line -- real, and somebody else's. Asked for it anyway, the
    # panel filled with "who were her mother's parents?" about people whose
    # surnames nobody in the family carries, and the questions that matter
    # were pushed off the end.
    #
    # This is not a preference dressed up as a rule: it is what the root
    # person MEANS. Move the root to a grandchild and the same woman is a
    # grandmother, her line is the direct line, and her parents become the
    # first question on the list -- with no setting to find and nothing to
    # switch on. `copy_for` is the whole of that idea, and this is the half
    # of it that lives here.
    if not graph.parents(pid, primary_only=False) and not married_in:
        add("parents", f"The line stops here. {n} "
                       f"{'person' if n == 1 else 'people'} descend from "
                       f"{p.given_first or 'them'} with nothing beyond.")
    if not p.given or not p.surname or pid in placeholders:
        # A PERSON WITH HALF A NAME IS THE MOST FINDABLE GAP THERE IS.
        # "Erica", married to a first cousin, is one telephone call away;
        # a surname on its own three hundred years back is a parish
        # register. Both are worth asking, and the first is worth asking
        # first, which is what the reach and the era already do -- this
        # only makes sure the question names what is missing.
        got = ("Only a first name is recorded" if p.given and not p.surname
               else "Only a surname is recorded" if p.surname and not p.given
               else "No name is recorded at all")
        add("name", f"{got}. Every index is filed under the part that is "
                    f"missing, so they cannot be looked up until it is "
                    f"known.")
    if not p.birth_year:
        add("birth", "No birth year, so nothing else can be dated "
                     "against them.")
    if _is_dead(graph, p) and not p.death_year:
        add("death", "No death recorded — the certificate usually names "
                     "an occupation and an informant, often a relative.")
    if not p.birth_place:
        add("birth_place", "No birthplace, which is what tells you which "
                           "parish to search.")
    if p.birth_year and not p.occupation and 1780 <= p.birth_year <= 1960:
        add("occupation", "No occupation — the censuses give one for "
                          "everybody over five.")
    if not graph.partners(pid) and graph.children(pid):
        add("spouse", "Has children but no partner recorded.")
    if not p.notes and (p.death_year or 0) >= 1940:
        add("story", "Within living memory and nothing written down. "
                     "This is the source that expires.")
    return out


def rank(graph, con=None, *, country: str = "england", limit: int = 40,
         within: Optional[set] = None, subject: Optional[str] = None,
         index=None) -> list[dict]:
    """The questions worth asking next, best first.

    `con` is accepted and unused for now: nothing here reads the database,
    and a gap list that needs one could not be shown beside a chart built
    from a file that is open read-only.
    """
    people = list(graph.people)
    if within is not None:
        people = [p for p in people if p in within]
    pool = set(people)

    # How many people are standing behind each gap. Descendants, plus the
    # person themselves, so an isolated great-uncle still scores 1 rather
    # than 0 and vanishes.
    reach: dict[str, int] = {}
    for pid in people:
        d = graph.descendants(pid)
        reach[pid] = sum(1 for x in d if x in pool)

    # HOW MUCH IT MATTERS TO *YOU*. "Blocks my own line" counts for more
    # than "blocks a cousin's line", which is what somebody means when they
    # ask where to look next. Married-in people are scored by how close the
    # relative they married is -- your mother's husband's family is a real
    # question and a fourth cousin's wife's family is not.
    boost: dict[str, float] = {}
    married: set = set()
    kin = index
    if subject and subject in graph.people:
        if kin is None:
            from ..graph.kinship import Kinship
            kin = Kinship(graph, subject)
        for pid in people:
            k = kin.of(pid)
            if k.group == "married_in":
                # THEIR OWN LINE IS SOMEBODY ELSE'S RESEARCH -- see
                # `_gaps_for`, which asks nothing about their parents at
                # all. What is left is what a chart of THIS family still
                # wants about them: a birth year, a photograph. Worth
                # asking, and never above a direct ancestor's.
                married.add(pid)
                boost[pid] = 0.5
            elif k.group == "unrelated":
                # Nobody has joined them to the family yet. Whatever is
                # missing about them, the missing LINK is the question, and
                # a list of birthplaces is not the way to it.
                boost[pid] = 0.35
            elif k.blood and k.down == 0:            # a direct ancestor
                boost[pid] = 3.0 if k.up <= 4 else 2.0
            elif k.blood and k.steps < 99:
                boost[pid] = max(0.8, 1.8 - 0.12 * k.steps)

    placeholders = {pid for pid, p in graph.people.items()
                    if p.is_placeholder}

    out: list[Gap] = []
    for pid in people:
        for g in _gaps_for(graph, pid, reach, country, placeholders,
                           married_in=pid in married):
            g.score *= boost.get(pid, 1.0)
            out.append(g)

    out.sort(key=lambda g: (-g.score, g.year or 9999, g.name))
    return [g.to_dict() for g in out[:limit]]


def for_person(graph, pid: str, *, country: str = "england") -> list[dict]:
    """The same question list, narrowed to one person's profile."""
    if pid not in graph.people:
        return []
    reach = {pid: sum(1 for _ in graph.descendants(pid))}
    placeholders = {q for q, p in graph.people.items() if p.is_placeholder}
    gs = _gaps_for(graph, pid, reach, country, placeholders)
    gs.sort(key=lambda g: -g.score)
    return [g.to_dict() for g in gs]


def summary(gaps: list[dict]) -> dict:
    """One line for the top of the panel."""
    if not gaps:
        return {"count": 0,
                "headline": "Nothing obvious left to look up. "
                            "Add a generation and ask again."}
    top = gaps[0]
    kinds: dict[str, int] = {}
    for g in gaps:
        kinds[g["kind"]] = kinds.get(g["kind"], 0) + 1
    ends = kinds.get("parents", 0)
    bits = []
    if ends:
        bits.append(f"{ends} line{'s' if ends != 1 else ''} "
                    f"stop{'' if ends != 1 else 's'} at a person with no "
                    f"known parents")
    if kinds.get("story"):
        bits.append(f"{kinds['story']} within living memory with nothing "
                    f"written down")
    head = "; ".join(bits) or f"{len(gaps)} things still to find out"
    return {"count": len(gaps), "kinds": kinds, "headline": head,
            "next": top["question"]}
