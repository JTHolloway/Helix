"""When two people who married were already related.

WHY A FAMILY TREE NEEDS THIS. Cousins marrying cousins is not an oddity of
one family -- before the railways most people married somebody from the same
parish, and in a village of four hundred that means a shared
great-grandparent more often than not. It has three visible effects and the
program should be able to say all three:

  * A person descended from such a marriage inherits the SAME ancestor down
    two lines, so their family tree has fewer distinct people in it than the
    arithmetic says. That is pedigree collapse, and `stats.pedigree_collapse`
    already measures it.
  * The DNA percentages shift. Two people related twice over share more than
    either path alone predicts.
  * It is a fact about the family worth recording in itself: "they were
    second cousins" is the sort of thing that gets said at a wedding and
    written down nowhere.

WHAT IS COMPUTED HERE

  coefficient of inbreeding, F
      The chance that a person inherited the same copy of a gene twice over,
      once from each parent. Wright's formula, over every ancestor the two
      parents share:

          F = SUM over shared ancestors A of  (1/2)^(n1 + n2 + 1) * (1 + F_A)

      where n1 and n2 are the steps from each parent up to A. First cousins
      marrying gives their children F = 1/16 = 6.25%; second cousins, 1/64.

      F_A IS THE ANCESTOR'S OWN INBREEDING and it is included, which is what
      makes this Wright's formula rather than an approximation of it. In a
      village where cousins married for four generations the approximation
      is out by a fifth.

WHAT IS NOT DONE HERE. Nothing is inferred about anybody's health, and the
interface says so. F is a statement about a pedigree, and the pedigree is
usually incomplete: a file that stops at four generations cannot see the
shared great-great-grandparents that would raise it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Consanguinity:
    """How two people were related before they married."""
    a: str
    b: str
    related: bool = False
    label: str = ""            # "second cousins", in English
    up_a: int = 0
    up_b: int = 0
    ancestors: tuple = ()      # the ones they share at that distance
    coefficient: float = 0.0   # F for a child of the two

    def to_dict(self) -> dict:
        return {"a": self.a, "b": self.b, "related": self.related,
                "label": self.label, "up_a": self.up_a, "up_b": self.up_b,
                "ancestors": list(self.ancestors),
                "coefficient": round(self.coefficient, 6),
                "percent": pct(self.coefficient)}


def pct(f: float) -> str:
    """A coefficient as a percentage somebody can read.

    Two decimals, rounded half UP, for the reason `dna_display` gives: every
    value here is a sum of powers of a half, so 1/16 is exactly 6.25 and
    Python's default half-to-even prints it as "6.2".
    """
    if not f:
        return "0%"
    from decimal import ROUND_HALF_UP, Decimal
    x = Decimal(f) * 100
    if x < Decimal("0.01"):
        return "under 0.01%"
    q = x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{q}".rstrip("0").rstrip(".") + "%"


# `describe` names ONE person's relation -- "first cousin". Said of a
# couple it has to be plural, and two people who share both parents are
# "brother and sister" rather than "sibling".
_PAIR = {(1, 1): "brother and sister", (0, 1): "parent and child",
         (1, 0): "parent and child", (2, 1): "uncle and niece",
         (1, 2): "aunt and nephew"}


def _label(up_a: int, up_b: int) -> str:
    """What to call the pair, in English."""
    from ..graph.kinship import describe
    if (up_a, up_b) in _PAIR:
        return _PAIR[(up_a, up_b)]
    one = describe(up_a, up_b)
    if one.endswith("removed"):
        head, _, tail = one.partition(" ")
        return one.replace(" cousin ", " cousins ", 1)
    return one + "s" if not one.endswith("s") else one


def between(graph, a: str, b: str) -> Consanguinity:
    """Were these two already related? Nearest shared ancestor wins."""
    if a not in graph.people or b not in graph.people or a == b:
        return Consanguinity(a, b)
    A, B = graph.ancestors(a), graph.ancestors(b)
    shared = [(A[x] + B[x], A[x], B[x], x) for x in A if x in B]
    if not shared:
        return Consanguinity(a, b)
    best = min(x[0] for x in shared)
    near = [x for x in shared if x[0] == best]
    up_a, up_b = near[0][1], near[0][2]
    return Consanguinity(
        a, b, True, _label(up_a, up_b), up_a, up_b,
        tuple(x[3] for x in near), inbreeding_of_child(graph, a, b))


def inbreeding_of_child(graph, father: str, mother: str,
                        _depth: int = 0, _seen: Optional[dict] = None) -> float:
    """Wright's F for a child of these two.

    Recursive, because each shared ancestor contributes `(1 + F_A)` and F_A
    is the same question asked one generation up. `_depth` stops a file with
    a mis-linked parent -- somebody recorded as their own grandfather --
    from recursing until the stack gives out; the cycle itself is reported
    by the importer and by `graph.validate`.
    """
    if _depth > 6 or father not in graph.people or mother not in graph.people:
        return 0.0
    _seen = _seen if _seen is not None else {}
    key = tuple(sorted((father, mother)))
    if key in _seen:
        return _seen[key]
    _seen[key] = 0.0                                # guard against a cycle

    A, B = graph.ancestors(father), graph.ancestors(mother)
    total = 0.0
    for anc in A:
        if anc not in B:
            continue
        n1, n2 = A[anc], B[anc]
        # An ancestor's own inbreeding, which is what makes this Wright's
        # formula rather than an approximation of it.
        pars = [x for x in graph.parents(anc, primary_only=False)
                if x in graph.people][:2]
        f_anc = (inbreeding_of_child(graph, pars[0], pars[1],
                                     _depth + 1, _seen)
                 if len(pars) == 2 else 0.0)
        total += 0.5 ** (n1 + n2 + 1) * (1 + f_anc)
    _seen[key] = total
    return total


def inbreeding(graph, pid: str) -> dict:
    """F for one person, from their own parents.

    Zero is the ordinary answer and is reported as such rather than hidden:
    "0%" means the two parents share no ancestor in this file, which is
    information. It is not a claim that they were unrelated in fact -- a
    tree four generations deep cannot see a shared great-great-grandparent.
    """
    pars = [x for x in graph.parents(pid, primary_only=False)
            if x in graph.people][:2]
    if len(pars) < 2:
        return {"coefficient": None, "percent": "",
                "why": "Both parents have to be in the file to work it out.",
                "parents": [], "relation": None}
    rel = between(graph, pars[0], pars[1])
    f = rel.coefficient
    return {
        "coefficient": round(f, 6),
        "percent": pct(f),
        "parents": [{"id": x, "name": graph.people[x].full_name} for x in pars],
        "relation": rel.to_dict() if rel.related else None,
        "why": (f"Their parents were {rel.label}."
                if rel.related else
                "Their parents share no ancestor in this file."),
        "depth": max(len(graph.ancestors(pars[0])),
                     len(graph.ancestors(pars[1]))),
    }


def couples(graph, limit: int = 40) -> list[dict]:
    """Every marriage in the file where the two were already related.

    THE LIST A FAMILY HISTORIAN ACTUALLY WANTS. It is the shape of a place
    as much as of a family: a village where this happens six times is a
    village people did not leave.
    """
    out = []
    for u in graph.unions.values():
        pair = [x for x in u.partners if x in graph.people][:2]
        if len(pair) < 2:
            continue
        rel = between(graph, pair[0], pair[1])
        if not rel.related:
            continue
        kids = [c for c in u.children if c in graph.people]
        out.append({
            **rel.to_dict(),
            "union": u.id,
            "names": [graph.people[x].full_name for x in pair],
            "married": u.date.display,
            "children": len(kids),
            "ancestor_names": [graph.people[x].full_name
                               for x in rel.ancestors if x in graph.people],
        })
    out.sort(key=lambda r: -r["coefficient"])
    return out[:limit]


def summary(graph) -> dict:
    rows = couples(graph, limit=10 ** 6)
    fs = [inbreeding_of_child(graph, *[x for x in u.partners
                                       if x in graph.people][:2])
          for u in graph.unions.values()
          if len([x for x in u.partners if x in graph.people]) >= 2]
    fs = [x for x in fs if x]
    return {
        "related_couples": len(rows),
        "marriages": len(graph.unions),
        "mean_coefficient": round(sum(fs) / len(fs), 6) if fs else 0.0,
        "closest": rows[0] if rows else None,
    }
