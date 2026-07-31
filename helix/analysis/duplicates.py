"""The same person, entered twice.

WHY THIS EXISTS NOW AND NOT BEFORE. Entering a family by hand, the duplicate
check on the add dialogue catches almost everything: it runs while you type
and offers "did you mean this person?" before you have saved. Importing
somebody else's tree, it catches nothing at all — four hundred people arrive
in one step, and the great-grandmother you already had is now in the file
twice under two spellings of her surname.

So this is a whole-file sweep, run after an import or whenever somebody
asks: find every pair that might be one person, score how sure it is, and
say WHY. Never merge anything on its own — which of two records is right is
a judgement about somebody's research, and a program that quietly merged two
great-uncles would be unusable the first time it was wrong.

HOW IT SCORES
  A pair is a candidate only if the names are close. Then evidence is added
  and removed:

    + the same birth year, or overlapping vague birth intervals
    + the same birthplace
    + the same parents, or a shared parent
    + the same partner
    - a birth year more than three years apart, which is nearly conclusive
    - a recorded death before the other one's birth
    - a shared parent AND different birth years: brothers are often named
      for the same grandfather, and two John Whitcombes with one father are
      more likely brothers than one man written twice

  BLOCKED BY SURNAME, not compared pairwise. Four hundred people is 80,000
  pairs and a fuzzy match on each is slow enough that nobody runs it twice;
  grouped by the first letter of a normalised surname it is a few hundred.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

# Spellings that are one name. Not an attempt at a thesaurus -- these are the
# ones that turn up in every English parish register, and a nickname index
# that guessed would be worse than none.
NICKNAMES = {
    "william": {"will", "bill", "billy", "willie", "wm"},
    "elizabeth": {"eliza", "betty", "bess", "beth", "lizzie", "liz", "betsy"},
    "margaret": {"maggie", "meg", "peggy", "margery", "marge"},
    "mary": {"molly", "polly", "may", "mai"},
    "james": {"jim", "jimmy", "jas"},
    "john": {"jack", "johnny", "jno"},
    "robert": {"rob", "bob", "robin", "bert"},
    "richard": {"dick", "rick", "richd"},
    "thomas": {"tom", "tommy", "thos"},
    "charles": {"charlie", "chas", "charley"},
    "henry": {"harry", "hal", "hen"},
    "edward": {"ted", "ned", "eddie", "edwd"},
    "sarah": {"sally", "sadie"},
    "catherine": {"kate", "katherine", "kathleen", "cathy", "kitty", "katie"},
    "anne": {"ann", "annie", "nancy", "nan"},
    "frances": {"fanny", "fran"},
    "george": {"geo", "georgie"},
    "joseph": {"joe", "joseph", "jos"},
    "samuel": {"sam", "sammy", "saml"},
    "alexander": {"alex", "sandy"},
    "susannah": {"susan", "susanna", "sue", "susie"},
}
_ALIAS: dict[str, str] = {}
for _full, _short in NICKNAMES.items():
    _ALIAS[_full] = _full
    for _s in _short:
        _ALIAS[_s] = _full


def norm(s: str) -> str:
    """Strip accents, case and punctuation. "de la Mare" and "Delamare" are
    the same family and land under the same key."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z]", "", s.lower())


def soundex(s: str) -> str:
    """Russell soundex, four characters. Spelling was not fixed before the
    twentieth century -- Whitcombe, Whitcomb, Witcombe and Whitcume are one
    family -- and searching by letter finds three of the four."""
    s = norm(s).upper()
    if not s:
        return ""
    codes = {**dict.fromkeys("BFPV", "1"), **dict.fromkeys("CGJKQSXZ", "2"),
             **dict.fromkeys("DT", "3"), "L": "4",
             **dict.fromkeys("MN", "5"), "R": "6"}
    out, last = s[0], codes.get(s[0], "")
    for ch in s[1:]:
        c = codes.get(ch, "")
        if c and c != last:
            out += c
        if ch not in "HW":
            last = c
    return (out + "000")[:4]


def _given_key(given: str) -> set[str]:
    """Every form of a first name that should match every other."""
    first = norm((given or "").split()[0] if given else "")
    if not first:
        return set()
    full = _ALIAS.get(first, first)
    return {first, full} | NICKNAMES.get(full, set())


@dataclass
class Pair:
    a: str
    b: str
    score: float
    why: list[str] = field(default_factory=list)
    against: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"a": self.a, "b": self.b, "score": round(self.score, 3),
                "why": self.why, "against": self.against}


def _years_agree(p, q) -> Optional[bool]:
    """True if the birth intervals overlap, False if they cannot be the same
    person, None if one of them has no date.

    INTERVALS, NOT MIDPOINTS. Rule 2. "about 1834" and "1836" describe one
    person perfectly well; compared as numbers they are two years apart and
    the pair is thrown away.
    """
    if not (p.birth.known and q.birth.known):
        return None
    if p.birth.overlaps(q.birth):
        return True
    a, b = p.birth_year, q.birth_year
    if a and b and abs(a - b) <= 3:
        return True
    return False


def find(graph, *, limit: int = 60, threshold: float = 0.55) -> list[dict]:
    """Every pair that might be one person, most likely first."""
    people = [p for p in graph.people.values()]
    # Blocked by the sound of the surname, so a four-hundred-person file is
    # a few hundred comparisons instead of eighty thousand.
    blocks: dict[str, list] = {}
    for p in people:
        key = soundex(p.surname) or "?"
        blocks.setdefault(key, []).append(p)

    parents = {p.id: set(graph.parents(p.id, primary_only=False)) for p in people}
    partners = {p.id: set(graph.partners(p.id)) for p in people}

    out: list[Pair] = []
    for group in blocks.values():
        if len(group) < 2:
            continue
        for i, p in enumerate(group):
            for q in group[i + 1:]:
                pair = _compare(graph, p, q, parents, partners)
                if pair and pair.score >= threshold:
                    out.append(pair)
    out.sort(key=lambda x: -x.score)
    return [x.to_dict() for x in out[:limit]]


def _compare(graph, p, q, parents, partners) -> Optional[Pair]:
    gp, gq = _given_key(p.given), _given_key(q.given)
    if not gp or not gq:
        # No given name on one of them. Only worth reporting if everything
        # else matches, which the placeholder rule below covers.
        if not (p.is_placeholder or q.is_placeholder):
            return None
    sur = difflib.SequenceMatcher(None, norm(p.surname), norm(q.surname)).ratio()
    if sur < 0.72 and norm(p.surname) != norm(q.surname):
        return None

    why: list[str] = []
    against: list[str] = []
    score = 0.0

    if gp & gq:
        shared = sorted(gp & gq)[0]
        score += 0.42
        if norm(p.given) == norm(q.given):
            why.append(f"the same name, {p.given} {p.surname}")
        else:
            why.append(f"{p.given} and {q.given} are the same name ({shared})")
    else:
        first = difflib.SequenceMatcher(
            None, norm(p.given), norm(q.given)).ratio()
        if first < 0.8:
            return None
        score += 0.28
        why.append(f"{p.given} and {q.given} are spelled almost the same")
    score += 0.18 * sur
    if norm(p.surname) != norm(q.surname):
        why.append(f"{p.surname} and {q.surname} sound the same")

    # MIDDLE NAMES THAT DISAGREE ARE EVIDENCE AGAINST, not merely weaker
    # evidence for. "Thomas Frederick" and "Thomas William" are two men and
    # were reported as one; "Clara" and "Clara Sarah" are one person with
    # the middle name recorded once, which is a different thing entirely.
    mp = {norm(x) for x in (p.given or "").split()[1:]}
    mq = {norm(x) for x in (q.given or "").split()[1:]}
    if mp and mq and not (mp & mq):
        score -= 0.45
        against.append(f"different middle names — {p.given} and {q.given}")

    agree = _years_agree(p, q)
    if agree is True:
        score += 0.30
        why.append(f"both born {p.birth.display or q.birth.display}")
    elif agree is False:
        score -= 0.55
        against.append(f"born {p.birth.display} and {q.birth.display} — "
                       f"too far apart to be one person")

    # A DEATH IS THE HARDEST FACT IN A FAMILY FILE. Two records that agree
    # on a vague birth and disagree on the year of death are two people:
    # `abt 1750` covers seven years and matches anybody, but nobody dies in
    # 1797 and again in 1847.
    if p.death.known and q.death.known:
        if p.death.overlaps(q.death):
            score += 0.22
            why.append(f"both died {p.death.display or q.death.display}")
        else:
            score -= 0.55
            against.append(f"died {p.death.display} and {q.death.display} — "
                           f"one person does not do both")
    if p.birth_place and p.birth_place == q.birth_place:
        score += 0.18
        why.append(f"both born in {p.birth_place}")

    shared_parents = parents[p.id] & parents[q.id]
    if shared_parents:
        names = ", ".join(sorted(graph.people[x].full_name
                                 for x in shared_parents))
        if agree is False:
            # BROTHERS ARE NAMED FOR THE SAME GRANDFATHER. Two John
            # Whitcombes with one father and different birth years are far
            # more likely to be brothers than one man written twice --
            # often because the first died as an infant and the name was
            # used again, which is the commonest false positive there is.
            score -= 0.35
            against.append(f"they share a parent ({names}) but were born "
                           f"years apart — more likely brothers or sisters")
        else:
            score += 0.28
            why.append(f"the same parents ({names})")
    if partners[p.id] & partners[q.id]:
        names = ", ".join(sorted(graph.people[x].full_name
                                 for x in partners[p.id] & partners[q.id]))
        score += 0.25
        why.append(f"both married to {names}")

    if p.death.known and q.birth.known and p.death.definitely_before(q.birth):
        score -= 0.6
        against.append("one died before the other was born")
    if p.is_placeholder or q.is_placeholder:
        score += 0.12
        why.append("one of them is a placeholder somebody referred to")
    if p.id in parents[q.id] or q.id in parents[p.id]:
        return None                        # a parent is never their own child

    return Pair(p.id, q.id, min(1.0, max(0.0, score)), why, against)
