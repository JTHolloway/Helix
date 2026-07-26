"""Layout anchored on one person, not on whichever ancestor happened to be
picked as a root.

WHY THIS EXISTS. The descendant-oriented grid in `base.py` measures a
person's ring by how far they sit below an apex ancestor. On a real family
that is wrong, and visibly so:

    David Holloway   generation 2, angle  43 deg
    Michaela Reed    generation 4, angle 256 deg

They are married and born two years apart. David was two steps below one
apex; Michaela, whose own parents were recorded, was four steps below a
different apex on the other side of the disc. So a married couple came out
two rings apart and most of a circle away from each other, and the chart
said nothing true about the family.

WHAT THIS DOES INSTEAD.

    Generation is measured FROM THE SUBJECT. Your parents are one ring in,
    your grandparents two, your children one out. A spouse is always the
    same generation as their partner, a sibling always the same as you.

    Angle comes from the pedigree. Your father's side takes one half of the
    disc and your mother's the other, recursively, so every couple meets at
    the boundary between the two blocks they created. Siblings, their
    families and married-in partners share the angular span of the person
    they attach to -- they sit on different rings, so there is no conflict.

The result: couples adjacent, families whole, both sides converging on you.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .base import Grid, LayoutSettings, Slot


def build_subject_grid(graph, s: LayoutSettings) -> Grid:
    subj = s.subject_id
    g = Grid()
    if not subj or subj not in graph.people:
        g.warnings.append("Choose whose chart this is first.")
        return g

    scope = _scope(graph, s, subj)
    demand = _Demand(graph, scope)
    # One person's worth of angle. Without this a person's own slot scales
    # with the size of their block, so the subject's father -- who owns half
    # the disc -- got a slot 40% of a semicircle wide and his wife landed
    # 74 degrees away from him.
    # One person's worth of angle. Sized against the busiest generation as
    # well as the pedigree depth: a wide family needs finer units than a
    # deep one, and using only the pedigree left the outer rings overlapping.
    widest = 1
    for pid in scope:
        widest = max(widest, len([c for c in graph.children(pid) if c in scope]))
    demand.unit = 1.0 / max(16.0, demand.above(subj), len(scope) / 3.0)
    counter = [0]

    def place(pid: str, t0: float, t1: float, gen: int,
              parent: Optional[str], partner_of: Optional[str] = None):
        if pid in g.slots:
            return
        p = graph.people[pid]
        g.slots[pid] = Slot(pid=pid, gen=gen, t0=t0, t1=t1, order=counter[0],
                            lineage=subj, parent=parent, partner_of=partner_of,
                            year=p.birth.sort_value,
                            death_year=p.death.sort_value)
        counter[0] += 1
        g.order.append(pid)
        g.by_gen.setdefault(gen, []).append(pid)
        g.max_gen = max(g.max_gen, gen)

    def spouses_of(pid: str) -> list[str]:
        return [x for x in graph.partners(pid)
                if x in scope and x not in g.slots]

    def descend(pid: str, t0: float, t1: float, gen: int,
                parent: Optional[str]):
        """A person and everything below them, on rings further out."""
        kids = [c for c in graph.children(pid) if c in scope]
        span = t1 - t0
        mid = (t0 + t1) / 2
        own = min(span * 0.9, demand.unit)
        place(pid, mid - own / 2, mid + own / 2, gen, parent)
        cur = mid + own / 2
        for sp in spouses_of(pid):
            w = min(demand.unit, max(1e-5, (t1 - cur) * 0.9))
            place(sp, cur, cur + w, gen, None, partner_of=pid)
            cur += w
        if not kids:
            return
        tot = sum(demand.below(k) for k in kids) or 1
        cur = t0
        for k in sorted(kids, key=lambda c: (graph.people[c].birth.sort_value
                                             or 9e9)):
            w = span * demand.below(k) / tot
            descend(k, cur, cur + w, gen - 1, pid)
            cur += w

    def ascend(members: list[str], t0: float, t1: float, gen: int):
        """A COUPLE and everything behind them.

        The unit of a pedigree is not a person, it is a couple. They sit
        together at the centre of their block, and the block then splits in
        two: his parents behind him, hers behind her. Recursing on couples
        rather than individuals is what keeps every husband beside his wife
        while each of them still sits in front of their own family.

        Laying out individuals instead put David at 217 degrees and his own
        parents at 30, because his block's centre was nowhere near him.
        """
        members = [m for m in members if m in scope and m not in g.slots]
        if not members:
            return
        mid = (t0 + t1) / 2
        width = min(demand.unit, (t1 - t0) / max(1, len(members)) * 0.9)
        start = mid - width * len(members) / 2
        for i, m in enumerate(members):
            place(m, start + i * width, start + (i + 1) * width, gen,
                  None, partner_of=members[0] if i else None)

        # any further partner sits immediately alongside
        cur = start + width * len(members)
        for m in list(members):
            for sp in spouses_of(m):
                w = min(demand.unit, max(1e-5, (t1 - cur) * 0.9))
                place(sp, cur, cur + w, gen, None, partner_of=m)
                cur += w

        # --- brothers and sisters, flanking, with their own families -------
        for m in members:
            sibs = [x for x in graph.siblings(m) if x in scope
                    and x not in g.slots]
            sibs.sort(key=lambda x: (graph.people[x].birth.sort_value or 9e9))
            me = graph.people[m].birth.sort_value or 9e9
            lo = start
            hi = cur
            for x in sibs:
                w = min(demand.below(x) * demand.unit, demand.unit * 8)
                if (graph.people[x].birth.sort_value or 9e9) <= me and lo - w > t0:
                    descend(x, lo - w, lo, gen, None)
                    lo -= w
                elif hi + w < t1:
                    descend(x, hi, hi + w, gen, None)
                    hi += w

        # --- inner rings: one block per partner's parents ------------------
        if s.max_generations is not None and gen >= s.max_generations:
            return
        blocks = []
        for m in members:
            pars = [p for p in graph.parents(m, primary_only=False)
                    if p in scope][:2]
            if pars:
                blocks.append(pars)
        if not blocks:
            return
        tot = sum(max(demand.above(p) for p in blk) for blk in blocks) or 1
        cur2 = t0
        for blk in blocks:
            w = (t1 - t0) * max(demand.above(p) for p in blk) / tot
            ascend(blk, cur2, cur2 + w, gen + 1)
            cur2 += w

    ascend([subj], 0.0, 1.0, 0)

    # descendants of the subject go outward from the subject's own span
    sl = g.slots.get(subj)
    if sl:
        kids = [c for c in graph.children(subj) if c in scope]
        if kids:
            tot = sum(demand.below(k) for k in kids) or 1
            cur, span = sl.t0, max(sl.span, demand.unit * len(kids))
            for k in sorted(kids, key=lambda c: (graph.people[c].birth.sort_value or 9e9)):
                w = span * demand.below(k) / tot
                descend(k, cur, cur + w, -1, subj)
                cur += w

    # Anyone in scope the recursion did not reach -- a cousin's spouse, an
    # uncle's grandchild -- is attached beside the nearest relative who WAS
    # placed. Repeated until nothing more can be attached, because each pass
    # gives the next one something to hang on to.
    used: dict[str, int] = {}          # how many have already hung off each

    def beside(anchor_slot, gen, parent, partner_of, key):
        """Attach next to an anchor, stepping along so that two people never
        land on the same angle. Stacking them made their sibling arc
        collapse to nothing and the pair looked unrelated."""
        n = used.get(key, 0)
        used[key] = n + 1
        w = demand.unit * 0.9
        t0 = anchor_slot.t1 + n * w
        return t0, t0 + w, gen, parent, partner_of

    for _ in range(12):
        added = 0
        for pid in list(scope):
            if pid in g.slots:
                continue
            partner = next((x for x in graph.partners(pid) if x in g.slots), None)
            parent = next((x for x in graph.parents(pid, primary_only=False)
                           if x in g.slots), None)
            child = next((x for x in graph.children(pid) if x in g.slots), None)
            sib = next((x for x in graph.siblings(pid) if x in g.slots), None)
            if partner:
                a = g.slots[partner]
                place(pid, *beside(a, a.gen, None, partner, f"p{partner}"))
            elif parent:
                a = g.slots[parent]
                place(pid, *beside(a, a.gen - 1, parent, None, f"c{parent}"))
            elif sib:
                a = g.slots[sib]
                place(pid, *beside(a, a.gen, a.parent, None, f"s{a.parent}{a.gen}"))
            elif child:
                a = g.slots[child]
                place(pid, *beside(a, a.gen + 1, None, None, f"u{child}"))
            else:
                continue
            added += 1
        if not added:
            break

    # Families with no connection to the subject at all. They cannot be
    # anchored on a pedigree that does not include them, so they are given
    # their own sector after the main tree rather than dropped.
    stranded = [p for p in scope if p not in g.slots]
    if stranded:
        lo = min((sl.t0 for sl in g.slots.values()), default=0.0)
        seen: set[str] = set()
        cur = lo - demand.unit
        for pid in stranded:
            if pid in seen or pid in g.slots:
                continue
            comp = _component(graph, pid, scope, g.slots)
            seen |= comp
            base = min((graph.people[x].birth.sort_value or 9e9) for x in comp)
            for x in sorted(comp, key=lambda y: (graph.people[y].birth.sort_value
                                                 or 9e9)):
                gen_x = int(round(((graph.people[x].birth.sort_value or base)
                                   - base) / 28.0))
                place(x, cur, cur + demand.unit * 0.9, -gen_x, None)
                cur -= demand.unit

    # rings are numbered from the earliest generation outward, so the oldest
    # ancestors sit innermost and the youngest people at the rim
    top = max((sl.gen for sl in g.slots.values()), default=0)
    for sl in g.slots.values():
        sl.gen = top - sl.gen
    g.by_gen = {}
    for sl in g.slots.values():
        g.by_gen.setdefault(sl.gen, []).append(sl.pid)
    g.max_gen = max(g.by_gen) if g.by_gen else 0
    g.roots = [p for p, sl in g.slots.items() if sl.gen == 0]
    g.lineages = [subj]

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


def _component(graph, start: str, scope: set[str], placed) -> set[str]:
    """Everyone reachable from `start` who has not been placed."""
    out, stack = set(), [start]
    while stack:
        x = stack.pop()
        if x in out or x in placed or x not in scope:
            continue
        out.add(x)
        stack.extend(graph.parents(x, primary_only=False))
        stack.extend(graph.children(x))
        stack.extend(graph.partners(x))
        stack.extend(graph.siblings(x))
    return out


def _scope(graph, s: LayoutSettings, subj: str) -> set[str]:
    """Who belongs on the chart."""
    line = set(graph.ancestors(subj))
    keep = set(line)
    if s.focus in ("thread_siblings", "subtree", "bloodline", "all"):
        for a in line:
            keep |= set(graph.siblings(a))
    if s.focus in ("subtree", "bloodline", "all"):
        for a in list(line):
            keep |= set(graph.descendants(a))
    if s.focus == "all":
        keep |= set(graph.people)
    for pid in list(keep):
        keep |= set(graph.partners(pid))
    keep |= set(graph.descendants(subj))
    return keep


class _Demand:
    """How much angular room each block needs, in units of one person."""

    def __init__(self, graph, scope: set[str]):
        self.g = graph
        self.scope = scope
        self._below: dict[str, float] = {}
        self._above: dict[str, float] = {}
        self.unit = 1.0

    def below(self, pid: str, depth: int = 0) -> float:
        if pid in self._below:
            return self._below[pid]
        if depth > 40:
            return 1.0
        self._below[pid] = 1.0
        kids = [c for c in self.g.children(pid) if c in self.scope]
        n = 1.0 + len([x for x in self.g.partners(pid) if x in self.scope])
        v = max(n, sum(self.below(k, depth + 1) for k in kids))
        self._below[pid] = v
        return v

    def above(self, pid: str, depth: int = 0) -> float:
        if pid in self._above:
            return self._above[pid]
        if depth > 40:
            return 1.0
        self._above[pid] = 1.0
        pars = [p for p in self.g.parents(pid, primary_only=False)
                if p in self.scope][:2]
        here = 1.0 + len([x for x in self.g.partners(pid) if x in self.scope])
        here += sum(self.below(x, depth + 1)
                    for x in self.g.siblings(pid) if x in self.scope)
        v = max(here, sum(self.above(p, depth + 1) for p in pars))
        self._above[pid] = v
        return v
