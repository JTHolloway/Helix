"""One cell per couple, laid out as a descent tree.

WHY THIS EXISTS. `subject_grid.py` gives every person their own angular slot
and measures rings outward from the subject. That is honest, and it reads
badly, for three reasons that turned out to be the same reason:

  * A married-in spouse took a slot in the row, so a sibling group's arc ran
    over the siblings' own husbands and wives.
  * Half the angular width of the disc went on spouses, so every name was
    half as wide as it could have been.
  * A person on the direct line has to touch three things -- their parent,
    their brothers and sisters, and their child -- and a slot has two sides.
    So the line to your own great-grandparents swung a hundred degrees
    across the chart.

All three come from expressing every relationship as ANGULAR adjacency.

WHAT THIS DOES INSTEAD. The unit is the couple, and it owns one angular
cell. The partners are stacked RADIALLY inside the ring band:

        ring band for generation g
        ┌──────────────────────────┐
        │  Samuel Marlow    1791–  │   row 0 — born into this family
        │  Clara Salter     1786–  │   row 1 — married in
        └──────────────────────────┘
                    │                  one stem, to their children

Three things fall out of that, and they are exactly the three failures
above:

  1. Marriage needs no tie line, no chord and no bracket. Two names in one
     cell IS the marriage, and it cannot be misread.
  2. The row that carries the sibling arc holds only people born into that
     generation, so an arc over a sibling group covers its own group and
     nothing else -- spouses included, which the angular layout could not do.
  3. Parent and child are RADIAL neighbours, so they no longer compete for
     the two angular sides. The cell is centred over its children in the
     ordinary tidy-tree way and the line from a founder to you runs straight
     out along a radius.

Remarriage stacks: a second husband or wife takes row 2, and the stem down
to each set of children leaves from that partner's own row. You can see
which mother a child belongs to without a dash, a legend or a repeated
name.

RINGS ARE DEPTH FROM THE FOUNDERS, not distance from you. That is the
descendancy chart the spec asks for -- earliest ancestors at the centre,
present day at the rim -- and it is what makes every parent-to-child link
exactly one ring long. A cousin's line reaching the rim two rings before
yours is a true statement about how far each has been researched.

WHAT THIS CANNOT DO. If BOTH partners were born into the tree -- cousins
marrying -- only one of them can hold the cell, and the other keeps their
own place in their own family. They are joined by a chord across the disc.
A merged layout is not planar; the chord is the honest answer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .base import Grid, LayoutSettings, Slot
from .subject_grid import _scope

# Blank cells between two adjacent families. Under about a third of a cell
# two families read as one.
GAP = 0.45
# Blank cells at the 0/360 seam so the first and last family do not fuse.
SEAM = 1.5
# Fewest cells the disc is ever divided into, so a four-person chart does not
# give each couple a quadrant.
MIN_CELLS = 14.0


def _founder_rank(graph, pid: str, scope: set[str]) -> tuple:
    """How strong a claim this person has to hold a founding couple's cell.

    Descendants first, then how many of their children carry their surname.
    A founding couple with children only by each other ties on the first,
    and the second is what tells you whose family this is.
    """
    kids = [c for c in graph.children(pid) if c in scope]
    sur = (graph.people[pid].surname or "").lower()
    same = sum(1 for c in kids if (graph.people[c].surname or "").lower() == sur)
    return (len([x for x in graph.descendants(pid) if x in scope]), same,
            len(kids), pid)


@dataclass
class _Cell:
    """One couple and everything descended from them."""

    pid: str                                   # born into the family
    spouses: list[str] = field(default_factory=list)
    ring: int = 0
    kids: list["_Cell"] = field(default_factory=list)
    rel: float = 0.0                           # x inside the parent cell
    contour: dict[int, tuple[float, float]] = field(default_factory=dict)

    @property
    def members(self) -> list[str]:
        return [self.pid] + self.spouses


# ================================================================ the tidy ====
def _merge(acc: dict, other: dict, dx: float) -> None:
    for ring, (lo, hi) in other.items():
        lo, hi = lo + dx, hi + dx
        if ring in acc:
            acc[ring] = (min(acc[ring][0], lo), max(acc[ring][1], hi))
        else:
            acc[ring] = (lo, hi)


def _clear(acc: dict, other: dict) -> float:
    """How far right `other` must move to clear everything left of it.

    Reingold-Tilford's contour step, and the whole non-overlap guarantee.
    Contours are indexed by RING rather than by depth in the tree: with one
    cell per couple those happen to agree, but indexing by the ring a cell
    actually sits on keeps the guarantee true if they ever stop agreeing.
    """
    need = 0.0
    for ring, (lo, _hi) in other.items():
        if ring in acc:
            need = max(need, acc[ring][1] + GAP - lo)
    return max(0.0, need)


def _tidy(cell: _Cell) -> None:
    """Bottom-up: give every cell a position inside its parent, then centre
    the parent over its children. Centring is what makes the descent line
    radial, and it is safe here precisely because a couple is one cell."""
    for k in cell.kids:
        _tidy(k)
    acc: dict[int, tuple[float, float]] = {}
    for k in cell.kids:
        if not k.contour:
            continue
        k.rel = _clear(acc, k.contour)
        _merge(acc, k.contour, k.rel)
    if cell.kids and acc:
        lo = min(k.rel for k in cell.kids)
        hi = max(k.rel for k in cell.kids)
        mid = (lo + hi) / 2
    else:
        mid = 0.0
    cell.rel_self = mid                                    # type: ignore[attr-defined]
    _merge(acc, {cell.ring: (mid - 0.5, mid + 0.5)}, 0.0)
    cell.contour = acc


def _assign(cell: _Cell, x0: float, out: dict[str, float]) -> None:
    """Top-down: accumulate the shifts into absolute positions."""
    out[cell.pid] = x0 + getattr(cell, "rel_self", 0.0)
    for k in cell.kids:
        _assign(k, x0 + k.rel, out)


# =============================================================== building ====
def build_couple_grid(graph, s: LayoutSettings) -> Grid:
    g = Grid()
    subj = s.subject_id
    scope = _scope(graph, s, subj) if subj else set(graph.people)
    if not scope:
        g.warnings.append("Nobody to draw. Add at least one person.")
        return g

    born = lambda p: (graph.people[p].birth.sort_value or 9e9, p)   # noqa: E731

    def in_scope(xs):
        return [x for x in xs if x in scope]

    # ---- who married in --------------------------------------------------
    # Somebody with no parents on the chart who is married to somebody who
    # HAS them joined this family rather than founding it. Getting this
    # wrong is what once gave 130 root sectors: "everyone with no known
    # parents" includes every spouse in the file.
    has_parents = {p for p in scope
                   if in_scope(graph.parents(p, primary_only=False))}
    married_in: dict[str, str] = {}
    for p in sorted(scope, key=born):
        if p in has_parents or p in married_in:
            continue
        for q in in_scope(graph.partners(p)):
            if q in married_in or married_in.get(q) == p:
                continue
            if q in has_parents:
                married_in[p] = q
                break
            # NEITHER was born into the chart: a founding couple. One of them
            # still has to hold the cell, or the two of them sit apart at the
            # centre looking like unrelated founders. The line with more
            # descendants keeps it, and where that ties -- which it does for
            # a couple with children only by each other -- the one whose
            # surname their children carry. That is the line the chart is
            # about, and it is the name a reader will look for at the centre.
            if _founder_rank(graph, q, scope) > _founder_rank(graph, p, scope):
                married_in[p] = q
                break

    # ---- one cell per person born into the family ------------------------
    cells: dict[str, _Cell] = {}
    for p in sorted(scope, key=born):
        if p in married_in:
            continue
        spouses = [q for q in in_scope(graph.partners(p)) if married_in.get(q) == p]
        cells[p] = _Cell(pid=p, spouses=sorted(spouses, key=born))

    # ---- the descent forest ----------------------------------------------
    for c in cells.values():
        c.kids = []
    roots: list[_Cell] = []
    for p, c in cells.items():
        parent = next((x for x in in_scope(graph.parents(p, primary_only=True))
                       if x in cells), None)
        if parent is None:
            parent = next((x for x in in_scope(graph.parents(p, primary_only=False))
                           if x in cells), None)
            if parent is None:
                # a parent who married in still holds no cell of their own;
                # follow them to the partner whose family this is
                for x in in_scope(graph.parents(p, primary_only=False)):
                    if x in married_in and married_in[x] in cells:
                        parent = married_in[x]
                        break
        if parent is not None and parent != p:
            cells[parent].kids.append(c)
        else:
            roots.append(c)

    # Sort each family into birth order, and guard against a cycle: pedigree
    # collapse can make a person their own remote ancestor in a bad file.
    seen: set[str] = set()

    def walk(c: _Cell, ring: int) -> None:
        if c.pid in seen:
            c.kids = []
            return
        seen.add(c.pid)
        c.ring = ring
        c.kids.sort(key=lambda k: born(k.pid))
        for k in list(c.kids):
            walk(k, ring + 1)

    roots.sort(key=lambda c: born(c.pid))
    for r in roots:
        walk(r, 0)
    roots = [r for r in roots if r.pid in seen]
    orphans = [c for p, c in cells.items() if p not in seen]
    for c in orphans:                       # a cycle broke their only link
        walk(c, 0)
        roots.append(c)

    # ---- lay it out ------------------------------------------------------
    forest = _Cell(pid="", ring=-1, kids=roots)
    forest.contour = {}
    acc: dict[int, tuple[float, float]] = {}
    for r in roots:
        _tidy(r)
        r.rel = _clear(acc, r.contour)
        _merge(acc, r.contour, r.rel)
    xs: dict[str, float] = {}
    for r in roots:
        _assign(r, r.rel, xs)
    if not xs:
        g.warnings.append("Nobody could be placed on this chart.")
        return g

    # ---- cells -> the 0..1 spread axis -----------------------------------
    lo = min(xs.values()) - 0.5
    raw = (max(xs.values()) + 0.5) - lo
    width = max(raw + SEAM, MIN_CELLS)
    pad = (width - raw) / 2
    order = 0
    for p, x in sorted(xs.items(), key=lambda kv: kv[1]):
        c = cells[p]
        t0 = (x - 0.5 - lo + pad) / width
        t1 = (x + 0.5 - lo + pad) / width
        for row, pid in enumerate(c.members):
            person = graph.people[pid]
            g.slots[pid] = Slot(
                pid=pid, gen=c.ring, t0=t0, t1=t1, order=order,
                lineage=p, row=row, cell=p,
                parent=None,
                partner_of=None if row == 0 else p,
                year=person.birth.sort_value,
                death_year=person.death.sort_value)
            g.order.append(pid)
            order += 1

    for pid, sl in g.slots.items():
        sl.parent = next((x for x in graph.parents(pid, primary_only=True)
                          if x in g.slots), None)
        if sl.parent is None:
            sl.parent = next((x for x in graph.parents(pid, primary_only=False)
                              if x in g.slots), None)

    for sl in g.slots.values():
        g.by_gen.setdefault(sl.gen, []).append(sl.pid)
    g.max_gen = max(g.by_gen) if g.by_gen else 0
    g.roots = [r.pid for r in roots]
    g.lineages = [r.pid for r in roots]

    from .base import _infer_years
    _infer_years(graph, g)
    yrs = [sl.year for sl in g.slots.values() if sl.year]
    g.year_min = min(yrs) if yrs else 1800.0
    g.year_max = max(yrs) if yrs else 2025.0
    if g.year_max - g.year_min < 20:
        g.year_max = g.year_min + 20

    missing = len(graph.people) - len(g.slots)
    if missing > 0:
        g.warnings.append(
            f"{missing} people in the file are not on this chart, because you "
            f"asked for '{s.focus}'. Choose 'all' to include everyone.")
    return g
