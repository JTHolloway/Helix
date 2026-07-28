"""Shared layout preparation: scope, ordering, and the abstract slot grid.

Single responsibility: decide WHO is in the chart, WHICH generation they sit
in, and WHERE they fall along the spread axis (0..1). Engines then map that
abstract grid into their own coordinate world -- disc, timeline, metro map.

This is why adding a new design is ~80 lines rather than a rewrite: every
engine shares the same combinatorial work and differs only in geometry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LayoutSettings:
    engine: str = "radial_sunburst"
    subject_id: Optional[str] = None
    apexes: list[str] = field(default_factory=list)
    max_generations: Optional[int] = None
    weight_mode: str = "leaves"          # leaves | descendants | equal | sqrt
    order_by: str = "birth"              # birth | name | size
    include_partners: bool = True
    focus: str = "all"
    """all | thread | thread_siblings | subtree | bloodline

    bloodline is the one most people actually want: everyone descended from
    any of your ancestors. That is your parents' whole families, your
    grandparents' whole families, your siblings, half-siblings, aunts,
    uncles, cousins, nieces and nephews -- and nobody else's in-laws.
    """
    max_people: Optional[int] = None
    redact_living: bool = False
    privacy_age_cutoff: int = 100
    min_year: Optional[int] = None
    max_year: Optional[int] = None
    surname_filter: Optional[str] = None
    sibling_gap: float = 0.10
    """Blank space between two brothers or sisters, in cells.

    Small on purpose. Three siblings should read as three siblings, not as
    three unrelated families that happen to be near each other, and the arc
    over them should be short enough to take in at a glance.
    """
    family_gap: float = 0.60
    """Blank space between two families, in cells. Wants to be several times
    `sibling_gap`: the contrast between the two is what makes a family read
    as a cluster rather than as part of the row."""
    min_cells: float = 0.0
    """Fewest cells the disc is divided into. 0 uses the layout's own floor.
    Raise it to thin a crowded chart out, lower it to close a sparse one up."""
    cells: bool = False
    """One angular cell per COUPLE, partners stacked radially inside the ring.

    Halves the angular width a generation costs, takes married-in spouses out
    of the row the sibling arc runs along, and makes every parent-to-child
    link exactly one ring long. See `couple_grid.py`. Radial designs turn it
    on; the linear ones place by `t0`/`t1` alone and would draw a couple on
    top of itself.
    """


@dataclass
class Slot:
    pid: str
    gen: int = 0
    t0: float = 0.0          # spread-axis start, 0..1
    t1: float = 1.0          # spread-axis end
    order: int = 0
    lineage: str = ""        # apex id -- drives metro line identity + colour
    parent: Optional[str] = None
    partner_of: Optional[str] = None
    year: Optional[float] = None
    death_year: Optional[float] = None
    weight: float = 1.0
    on_thread: bool = False
    # A couple shares ONE angular cell and is stacked radially inside the ring
    # band: row 0 was born into the family at this generation, rows 1+ married
    # in. Two names in one cell is the marriage, so it needs no tie line, and
    # the row that carries the sibling arc holds only blood siblings.
    # Designs that ignore `row` still work -- they just draw a couple on top
    # of itself -- so `cells=False` on LayoutSettings keeps them one to a slot.
    row: int = 0
    cell: str = ""

    @property
    def tc(self) -> float:
        return (self.t0 + self.t1) / 2

    @property
    def span(self) -> float:
        return self.t1 - self.t0


@dataclass
class Grid:
    slots: dict[str, Slot] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)     # draw order
    roots: list[str] = field(default_factory=list)
    by_gen: dict[int, list[str]] = field(default_factory=dict)
    max_gen: int = 0
    year_min: float = 1800.0
    year_max: float = 2025.0
    lineages: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __iter__(self):
        for pid in self.order:
            yield self.slots[pid]


def build_grid(graph, s: LayoutSettings) -> Grid:
    """Lay the family out.

    With a subject chosen, generations are measured FROM THAT PERSON, which
    is the only way a married couple reliably lands on the same ring beside
    each other. Without one, fall back to descent depth from an apex.
    """
    if s.cells:
        from .couple_grid import build_couple_grid
        return build_couple_grid(graph, s)
    if s.subject_id and s.subject_id in graph.people and s.focus != "raw":
        from .subject_grid import build_subject_grid
        return build_subject_grid(graph, s)
    g = Grid()
    roots = s.apexes or _auto_apexes(graph, subject=s.subject_id)
    if not roots:
        g.warnings.append("No starting ancestors found. Add at least one person.")
        return g
    g.roots = roots
    g.lineages = list(roots)

    # ---- 1. scope: everyone descended from a root, following primary edges
    include: dict[str, str] = {}          # pid -> lineage (apex id)
    for r in roots:
        for pid in graph.descendants(r):
            include.setdefault(pid, r)

    # ---- 1b. focus: the single most effective cure for a cluttered chart -
    #
    # A full descendant tree doubles every generation. By generation six a
    # real family is 400+ people, and 400 names on a 600 mm disc is a grey
    # mat that nobody can read. Nearly always what someone actually wants is
    # THEIR line and the people standing next to it.
    include = _apply_focus(graph, s, include)

    # ---- 2. weights (post-order, memoised) -------------------------------
    weight: dict[str, float] = {}

    paths = pedigree_paths(graph, s.subject_id) if s.subject_id else {}

    def kids(pid: str) -> list[str]:
        out = [c for c in graph.children(pid)
               if c in include and graph.people[c].child_of in graph.people[pid].unions]
        return _order_children(graph, out, s.order_by, paths)

    def w(pid: str, depth: int = 0) -> float:
        if pid in weight:
            return weight[pid]
        if depth > 60:
            weight[pid] = 1.0
            return 1.0
        cs = kids(pid)
        if not cs:
            v = 1.0
        elif s.weight_mode == "descendants":
            v = 1.0 + sum(w(c, depth + 1) for c in cs)
        elif s.weight_mode == "equal":
            v = float(len(cs)) or 1.0
        elif s.weight_mode == "sqrt":
            v = max(1.0, sum(w(c, depth + 1) for c in cs) ** 0.5)
        else:                                     # leaves
            v = sum(w(c, depth + 1) for c in cs)
        weight[pid] = max(v, 1e-6)
        return weight[pid]

    total = sum(w(r) for r in roots) or 1.0

    # ---- 3. spread-axis assignment (recursive, O(n)) ----------------------
    counter = [0]

    def assign(pid: str, t0: float, t1: float, gen: int, lineage: str,
               parent: Optional[str]):
        if s.max_generations is not None and gen > s.max_generations:
            return
        if pid in g.slots:
            return                                 # pedigree collapse guard
        p = graph.people[pid]
        sl = Slot(pid=pid, gen=gen, t0=t0, t1=t1, order=counter[0],
                  lineage=lineage, parent=parent,
                  year=p.birth.sort_value, death_year=p.death.sort_value,
                  weight=weight.get(pid, 1.0))
        counter[0] += 1
        g.slots[pid] = sl
        g.order.append(pid)
        g.by_gen.setdefault(gen, []).append(pid)
        g.max_gen = max(g.max_gen, gen)
        cs = kids(pid)
        if not cs:
            return
        tot = sum(weight.get(c, 1.0) for c in cs) or 1.0
        cur = t0
        for c in cs:
            frac = weight.get(c, 1.0) / tot
            assign(c, cur, cur + (t1 - t0) * frac, gen + 1, lineage, pid)
            cur += (t1 - t0) * frac

    cur = 0.0
    for r in roots:
        frac = w(r) / total
        assign(r, cur, cur + frac, 0, r, None)
        cur += frac

    # ---- 4. married-in partners share their spouse's arc -----------------
    # A spouse with no recorded parents belongs BESIDE their partner, not in a
    # sector of their own. Splitting the span keeps every engine working with
    # no engine-specific code.
    if s.include_partners:
        # A married-in partner needs room for ONE PERSON, not for half of
        # their spouse's entire lineage.
        #
        # The first version split the spouse's span down the middle. On a
        # root ancestor whose descendants fill 40% of the disc, that put the
        # husband's centre and the wife's centre 160 degrees apart, and their
        # marriage was drawn as a line clean across the circle. The partner
        # gets a narrow slice beside their spouse's centre instead. It may
        # sit inside the spouse's span; that is harmless, because everyone
        # else in that span is on the next ring out.
        person_w = 1.0 / max(30.0, float(len(g.slots) or 30))
        for pid in list(g.order):
            sl = g.slots[pid]
            for sp in graph.partners(pid):
                if sp in g.slots or sp not in graph.people:
                    continue
                mid = sl.tc
                w = min(max(2.0 * person_w, (sl.t1 - sl.t0) * 0.06),
                        (sl.t1 - mid) * 0.9)
                w = max(w, 1e-4)
                # sit the couple either side of the spouse's centre, one
                # person-width apart: close enough to read as a couple, far
                # enough that their two names do not collide
                sl.t0, sl.t1 = mid - w, mid
                g.slots[sp] = Slot(
                    pid=sp, gen=sl.gen, t0=mid, t1=mid + w, order=counter[0],
                    lineage=sl.lineage, parent=None, partner_of=pid,
                    year=graph.people[sp].birth.sort_value,
                    death_year=graph.people[sp].death.sort_value, weight=1.0)
                counter[0] += 1
                g.order.append(sp)
                g.by_gen.setdefault(sl.gen, []).append(sp)

    # ---- 4b. tell the user if anyone was left off ------------------------
    missing = len(graph.people) - len(g.slots)
    if missing > 0:
        if s.focus != "all":
            g.warnings.append(
                f"{missing} people in the file are not on this chart, because "
                f"you asked for '{s.focus}'. That is working as intended \u2014 "
                f"choose 'all' to include everyone.")
        elif s.max_generations is not None:
            g.warnings.append(
                f"{missing} people are not on this chart because it stops at "
                f"{s.max_generations} generations.")
        else:
            g.warnings.append(
                f"{missing} people are not on this chart. They belong to "
                f"family lines that were not picked as starting points. "
                f"Choose different starting ancestors to include them.")

    # ---- 5. year fallbacks so time-based engines never collapse ----------
    _infer_years(graph, g)
    yrs = [sl.year for sl in g.slots.values() if sl.year]
    g.year_min = min(yrs) if yrs else 1800.0
    g.year_max = max(yrs + [sl.death_year for sl in g.slots.values()
                            if sl.death_year] or [2025.0])
    if g.year_max - g.year_min < 20:
        g.year_max = g.year_min + 20
    return g


def _apply_focus(graph, s: LayoutSettings, include: dict[str, str]) -> dict[str, str]:
    """Narrow the cast list. Returns a filtered {person: lineage} mapping."""
    if s.focus == "all" or not s.subject_id:
        if s.max_people and len(include) > s.max_people:
            return _trim_to(graph, include, s.max_people)
        return include

    line = set(graph.ancestors(s.subject_id))       # subject + every ancestor
    keep = set(line)

    if s.focus == "bloodline":
        # everyone descended from any of my ancestors: my blood relatives,
        # and nobody else's family
        for a in line:
            keep |= set(graph.descendants(a))
        out = {p: lin for p, lin in include.items() if p in keep}
        if s.max_people and len(out) > s.max_people:
            return _trim_to(graph, out, s.max_people)
        return out or include

    if s.focus in ("thread_siblings", "subtree"):
        for pid in line:
            keep |= set(graph.siblings(pid))        # the aunts and uncles
    if s.focus == "subtree":
        for pid in list(keep):
            keep |= set(graph.children(pid))        # and the cousins

    # keep the chain unbroken: every kept person needs their parents kept too
    for pid in list(keep):
        cur = pid
        for _ in range(80):
            pars = graph.parents(cur)
            if not pars:
                break
            keep.update(pars)
            cur = pars[0]

    out = {p: lin for p, lin in include.items() if p in keep}
    if s.max_people and len(out) > s.max_people:
        return _trim_to(graph, out, s.max_people)
    return out or include


def _trim_to(graph, include: dict[str, str], limit: int) -> dict[str, str]:
    """Drop the least connected people first, never orphaning anyone."""
    ranked = sorted(include, key=lambda p: -len(graph.descendants(p)))
    keep = set(ranked[:limit])
    for pid in list(keep):
        cur = pid
        for _ in range(80):
            pars = graph.parents(cur)
            if not pars:
                break
            keep.update(pars)
            cur = pars[0]
    return {p: lin for p, lin in include.items() if p in keep}


def pedigree_paths(graph, subject: str) -> dict[str, str]:
    """Each ancestor's position in the subject's pedigree, as a binary path.

    Father is '0', mother is '1', so the subject's four grandparents are
    '00', '01', '10', '11'. Sorting by that string puts every pair that
    MERGES side by side: '00' and '01' are the two people who married to
    produce '0'.

    This is what stops the chart drawing a marriage as a chord straight
    across the middle of the disc. Order the family lines by size, as the
    first version did, and your mother's side can land opposite your
    father's, with their marriage stretched over 180 degrees. Order them by
    pedigree and the two sides converge naturally.
    """
    paths = {subject: ""}
    frontier = [subject]
    depth = 0
    while frontier and depth < 40:
        depth += 1
        nxt = []
        for pid in frontier:
            pars = graph.parents(pid, primary_only=False)[:2]
            for i, par in enumerate(pars):
                if par not in paths:
                    paths[par] = paths[pid] + str(i)
                    nxt.append(par)
        frontier = nxt
    return paths


def _convergence_key(graph, apex: str, paths: dict[str, str]) -> str:
    """Sort key for a family line. Lines inside the subject's own pedigree
    sort by their pedigree path; anything else sorts next to the relative it
    connects through."""
    if apex in paths:
        return paths[apex]
    best = None
    for pid in graph.descendants(apex):
        if pid in paths and (best is None or len(paths[pid]) < len(best)):
            best = paths[pid]
    return (best + "~") if best is not None else "~~"


def _auto_apexes(graph, max_lineages: int = 12, subject: str | None = None) -> list[str]:
    """Pick sensible starting ancestors with no configuration required.

    THIS FUNCTION IS THE DIFFERENCE BETWEEN A CHART AND A MESS.

    "Everyone with no known parents" sounds like the right definition of an
    apex. It is not: it also catches every spouse who married in, because
    their own parents were never researched. On a real family that is over a
    hundred people, and a radial design then opens with a hundred separate
    root sectors, each a sliver a couple of degrees wide. That was the single
    biggest cause of clutter in this program.

    So: rank candidates by how much family hangs off them, and once a lineage
    is taken, mark its descendants AND their spouses as covered. A spouse who
    married into a line already on the chart is never a lineage of their own
    -- they are placed beside their partner instead, further down.
    """
    cands = graph.apexes() or list(graph.people)[:1]
    cands.sort(key=lambda a: (-len(graph.descendants(a)),
                              graph.people[a].birth.sort_value or 9e9))
    chosen: list[str] = []
    covered: set[str] = set()
    for a in cands:
        if a in covered:
            continue
        if any(pp in covered for pp in graph.partners(a)):
            covered.add(a)                     # married in: not a lineage
            continue
        chosen.append(a)
        covered |= set(graph.descendants(a))
        for d in list(covered):
            covered |= set(graph.partners(d))
        if len(chosen) >= max_lineages:
            break
    chosen = chosen or cands[:1]
    if subject and subject in graph.people:
        paths = pedigree_paths(graph, subject)
        chosen.sort(key=lambda a: _convergence_key(graph, a, paths))
    return chosen


def _order_children(graph, ids: list[str], mode: str,
                    paths: dict[str, str] | None = None) -> list[str]:
    if mode == "name":
        base = sorted(ids, key=lambda c: graph.people[c].sort_key)
    elif mode == "size":
        base = sorted(ids, key=lambda c: -len(graph.descendants(c)))
    else:
        base = sorted(ids, key=lambda c: (graph.people[c].birth.sort_value or 9e9,
                                          graph.people[c].short_name))
    if not paths:
        return base

    # CONVERGENCE. Sector adjacency alone is not enough: if your father sits
    # at the far edge of his family's sector and your mother at the far edge
    # of hers, their marriage is still drawn as a long chord. The child who
    # carries the line toward a marriage must hug the side facing the family
    # they marry into.
    #
    # A pedigree path ending in '0' (a father) marries the path ending in
    # '1', which sorts after it -- so that child belongs at the high edge.
    # A path ending in '1' belongs at the low edge.
    on_line = [c for c in base if c in paths and paths[c]]
    if not on_line:
        return base
    c = on_line[0]
    rest = [x for x in base if x is not c]
    return rest + [c] if paths[c].endswith("0") else [c] + rest


def _infer_years(graph, g: Grid) -> None:
    """Estimate missing birth years from neighbours so chronological designs
    still work on a half-researched tree. Inferred people are FLAGGED, never
    silently faked -- engines draw them with a distinct texture."""
    GEN = 28.0
    changed = True
    guard = 0
    while changed and guard < 8:
        changed = False
        guard += 1
        for sl in g.slots.values():
            if sl.year is not None:
                continue
            cands: list[float] = []
            if sl.parent and g.slots.get(sl.parent) and g.slots[sl.parent].year:
                cands.append(g.slots[sl.parent].year + GEN)
            kid_years = [g.slots[c].year for c in graph.children(sl.pid)
                         if c in g.slots and g.slots[c].year]
            if kid_years:
                cands.append(min(kid_years) - GEN)
            if cands:
                sl.year = sum(cands) / len(cands)
                changed = True
    base = 1800.0
    for sl in g.slots.values():
        if sl.year is None:
            sl.year = base + sl.gen * GEN
