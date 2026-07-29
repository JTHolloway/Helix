"""One cell per couple, both parental lines running back and meeting.

WHAT THE CHART SAYS. Your father's family runs back through the rings on one
side, your mother's on the other. They meet at the cell that is their
marriage, and you and your brothers and sisters are in the next ring out.
Earliest ancestors at the centre, present day at the rim.

WHY THE UNIT IS THE COUPLE. Every earlier version gave each person their own
angular slot, and every one of them read badly for the same reason: it tried
to say everything with ANGULAR adjacency, and a slot has two sides. Somebody
on the direct line has to touch their parent, their brothers and sisters, and
their child. Two sides, three neighbours -- so one always lost.

A couple owns one cell, and the partners stack RADIALLY inside the ring band:

        ┌──────────────────────────┐
        │  Samuel Marlow    1791–  │   row 0 — born into this family
        │  ────                    │   the rule that means married
        │  Clara Salter     1786–  │   row 1 — married in
        └──────────────────────────┘
                    │                  one stem, to their children

That buys the second dimension back, and with it:

  * MARRIAGE needs no line at all. Not a tie, not a bracket, not a chord.
    Two names in one cell IS the marriage.
  * A SIBLING ARC runs along the row that holds only people born into that
    generation, so it covers its own group and nobody -- spouses included,
    which the angular layout had no way to avoid.
  * PARENT and CHILD are radial neighbours, so they stop competing with
    siblings for the two angular sides. Every parent-to-child link is
    exactly one ring long and the direct line runs out along a radius.

HOW THE TWO LINES MEET. A couple's cell is flanked by the two families it
joins, with their own children in the middle and one ring further out:

    [ his parents ][ his brothers ][ HIM | HER ][ her sisters ][ her parents ]
                                   [    their children    ]

So each parent's brothers and sisters butt straight up against the cell, the
arc over them ends there, and the two lines visibly converge on the marriage
from opposite sides. Every generation back repeats it.

REMARRIAGE stacks in the same cell: a second wife takes row 2, and each
marriage keeps its own stem out to its own children. Half-brothers and
half-sisters are two arcs off one cell -- one line each, nothing crossing.
The couple sits over ALL their children, both families included, so neither
stem has to sweep round to reach a group parked beyond the other.

WHAT THIS STILL CANNOT DO. If two people already on the chart marry each
other -- cousins -- only one of them can hold the cell. The other keeps their
own place in their own family and the two are joined by a chord. A merged
layout is not planar; the chord is the honest answer, and it is in the key.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .base import Grid, LayoutSettings, Slot
from .subject_grid import _scope

# Blank cells at the 0/360 seam so the first and last family do not fuse.
SEAM = 1.5
# Fewest cells the disc is ever divided into, so a four-person chart does not
# give each couple a quadrant.
MIN_CELLS = 14.0


@dataclass
class _Cell:
    """A couple and the blocks arranged around them.

    `members` empty means a GROUP: a container with no names of its own,
    used to hold one union's children so they stay together.
    """

    members: list[str] = field(default_factory=list)
    depth: int = 0                             # generations back from the subject
    kids: list["_Cell"] = field(default_factory=list)
    # Which child block this cell sits directly over. That is what keeps the
    # descent radial: a couple is centred on their own children, not on
    # everything hanging off them.
    split: bool = False                        # a leaf each, not one shared
    over: int = -1
    over_n: int = 1                            # how many of them are children
    rel: float = 0.0
    x: float = 0.0
    contour: dict[int, tuple[float, float]] = field(default_factory=dict)

    @property
    def width(self) -> float:
        """How many cells wide this leaf is.

        A SHARED leaf is one cell however many names are stacked in it. A
        SPLIT couple is one cell per partner, side by side, which costs
        twice the width and buys the one thing shared cannot give: each
        partner's own ancestry sitting directly inside them.
        """
        return float(len(self.members)) if self.split else 1.0


# ================================================================ the tidy ====
def _merge(acc: dict, other: dict, dx: float) -> None:
    for ring, (lo, hi) in other.items():
        lo, hi = lo + dx, hi + dx
        if ring in acc:
            acc[ring] = (min(acc[ring][0], lo), max(acc[ring][1], hi))
        else:
            acc[ring] = (lo, hi)


def _clear(acc: dict, other: dict, gap: float) -> float:
    """How far right `other` must move to clear everything left of it.

    Reingold-Tilford's contour step, and the whole non-overlap guarantee.
    Indexed by RING rather than by depth in the tree, because a cousin's
    block reaches back out to your own ring and separating by depth would
    let two cells share an angle.

    Nesting is allowed and wanted: a couple's children are narrower than the
    two families flanking them, and they tuck in underneath. What is NOT
    allowed is two cells on one ring at one angle, which is what the ring
    index prevents.
    """
    need = 0.0
    for ring, (lo, _hi) in other.items():
        if ring in acc:
            need = max(need, acc[ring][1] + gap - lo)
    return max(0.0, need)


def _cells_in(cell: _Cell) -> int:
    """How many leaves a block holds, counted before it is placed.

    Used only to decide which of a couple's two ancestral lines sits nearer
    them: the one that has to be reached ACROSS should be the narrow one.
    """
    return (1 if cell.members else 0) + sum(_cells_in(k) for k in cell.kids)


def _span(cell: _Cell) -> tuple[float, float]:
    lo = min(v[0] for v in cell.contour.values()) + cell.rel
    hi = max(v[1] for v in cell.contour.values()) + cell.rel
    return lo, hi


def _tidy(cell: _Cell, sib: float, fam: float) -> None:
    """Bottom-up: place every block inside its parent, and sit the couple
    over the children they belong to.

    Done in three passes rather than one, because the couple's own slot has
    to be reserved IN the sequence. Adding it afterwards let it land on
    somebody already standing on that ring -- an aunt, in the case that
    found this -- because nothing had reserved the space it was about to
    take.

    The couple centres over ALL their children, both marriages included. A
    second family placed beyond the first would leave the stem down to it
    sweeping most of a quadrant; centred, the two stems are short, roughly
    symmetric, and never cross.
    """
    for k in cell.kids:
        _tidy(k, sib, fam)

    # A container with no names of its own holds ONE union's children, so the
    # blocks inside it are brothers and sisters and belong close together.
    # Everywhere else is a boundary between families and wants air.
    gap = sib if not cell.members else fam

    o0 = cell.over if cell.members else -1
    o1 = o0 + cell.over_n - 1
    acc: dict[int, tuple[float, float]] = {}

    # 1 -- everything to the left of the couple's own children
    for k in cell.kids[:max(o0, 0)]:
        if k.contour:
            k.rel = _clear(acc, k.contour, gap)
            _merge(acc, k.contour, k.rel)

    # 2 -- the children, then the couple centred over them
    if o0 >= 0:
        run = [k for k in cell.kids[o0:o1 + 1] if k.contour]
        inner: dict[int, tuple[float, float]] = {}
        for k in run:
            k.rel = _clear(acc, k.contour, gap) if not inner else \
                _clear(inner, k.contour, gap)
            if inner:
                k.rel = max(k.rel, _clear(acc, k.contour, gap))
            _merge(inner, k.contour, k.rel)
        if run:
            lo = min(_span(k)[0] for k in run)
            hi = max(_span(k)[1] for k in run)
            x = (lo + hi) / 2
            shift = 0.0
            if cell.depth in acc:
                shift = max(0.0, acc[cell.depth][1] + fam
                            - (x - cell.width / 2))
            if shift:
                for k in run:
                    k.rel += shift
                x += shift
                inner = {}
                for k in run:
                    _merge(inner, k.contour, k.rel)
            cell.x = x
            _merge(acc, inner, 0.0)
            _merge(acc, {cell.depth: (x - cell.width / 2,
                                  x + cell.width / 2)}, 0.0)
        else:
            o0 = -1

    # 3 -- everything to the right
    for k in cell.kids[max(o1 + 1, 0):]:
        if k.contour:
            k.rel = _clear(acc, k.contour, gap)
            _merge(acc, k.contour, k.rel)

    if cell.members and o0 < 0:
        # no children of their own: stand clear of whatever is here
        half = cell.width / 2
        x = half if not acc else max(v[1] for v in acc.values()) + fam + half
        cell.x = x
        _merge(acc, {cell.depth: (x - half, x + half)}, 0.0)
    elif not cell.members:
        cell.x = 0.0
    cell.contour = acc


def _assign(cell: _Cell, x0: float, out: dict[str, float]) -> None:
    """Top-down: accumulate the shifts into absolute positions."""
    if cell.members:
        out[cell.members[0]] = x0 + cell.x
    for k in cell.kids:
        _assign(k, x0 + k.rel, out)


# =============================================================== building ====
def build_couple_grid(graph, s: LayoutSettings) -> Grid:
    g = Grid()
    subj = s.subject_id
    if not subj or subj not in graph.people:
        g.warnings.append("Choose whose chart this is first.")
        return g
    scope = _scope(graph, s, subj)

    born = lambda p: (graph.people[p].birth.sort_value or 9e9, p)   # noqa: E731
    used: set[str] = set()
    cell_of: dict[str, _Cell] = {}

    def in_scope(xs):
        return [x for x in xs if x in scope]

    def take_spouses(pid: str) -> list[str]:
        """Partners who married in. Somebody with parents on the chart of
        their own belongs in their own family; claiming them here would drag
        them across the disc and leave their brothers and sisters an arc
        with a hole in it."""
        out = []
        for q in in_scope(graph.partners(pid)):
            if q in used:
                continue
            if in_scope(graph.parents(q, primary_only=False)):
                continue                     # born into the chart; not a spouse
            used.add(q)
            out.append(q)
        return out

    def has_line(pid: str) -> bool:
        """Is this person's own ancestry drawn on the chart?

        That is the whole question a shared leaf turns on. Somebody who
        married in from off the chart brings no line inward, so stacking
        their name under their partner's cannot be misread. Somebody whose
        parents ARE here does bring one, and it has to be visibly theirs.
        """
        return bool(in_scope(graph.parents(pid, primary_only=False)))

    def line_first(pids: list[str]) -> list[str]:
        """Whoever brings a line back goes at the TOP of the leaf.

        A cell is anchored on its first member and the stem inward reads as
        that person's. Ordering father-then-mother regardless meant that a
        wife with three recorded generations behind her sat on row 1, under
        a husband who married in from nowhere, and her whole ancestry
        appeared to be his. Three couples on the owner's own tree.
        """
        return sorted(pids, key=lambda p: not has_line(p))

    def wants_split(members: list[str]) -> bool:
        """Shared is better until it becomes ambiguous.

        The moment more than one person in a leaf has parents on the chart,
        the leaf holds two ancestries with nothing to say which is whose.
        Splitting puts each line directly inside the partner it belongs to.
        Everywhere else shared wins: it is half the width, and a marriage
        drawn as two names in one cell cannot be misread.
        """
        mode = (s.couple_leaf or "auto").lower()
        if mode == "split":
            return len(members) > 1
        if mode == "shared":
            return False
        if len(members) < 2:
            return False
        # ONE line in a leaf is fine, because `line_first` has already put
        # the person it belongs to on top of it. Splitting on that as well
        # was tried and cost more than it bought: a split leaf puts the
        # spouse back on row 0 at their own angle, where they can land under
        # another couple's sibling arc -- which is the one thing this layout
        # exists to prevent.
        return sum(1 for m in members if has_line(m)) > 1

    def new_cell(anchor: str, depth: int, extra: list[str] = ()) -> _Cell:
        used.add(anchor)
        members = [anchor]
        for x in extra:
            if x not in used:
                used.add(x)
                members.append(x)
        members += take_spouses(anchor)
        for x in list(members[1:]):
            members += [y for y in take_spouses(x) if y not in members]
        c = _Cell(members=members, depth=depth, split=wants_split(members))
        for m in members:
            cell_of[m] = c
        return c

    def child_groups(cell: _Cell, depth: int) -> list[_Cell]:
        """One group per marriage, so half-brothers and half-sisters come out
        as two arcs off one cell rather than one arc over both families."""
        groups: list[_Cell] = []
        seen: set[str] = set()
        for m in cell.members:
            for uid in graph.people[m].unions:
                if uid in seen:
                    continue
                seen.add(uid)
                kids = sorted({c for c in graph.unions[uid].children
                               if c in scope and c not in used}, key=born)
                blocks = [descend(k, depth) for k in kids]
                blocks = [b for b in blocks if b]
                if blocks:
                    groups.append(_Cell(members=[], depth=depth, kids=blocks))
        return groups

    def descend(pid: str, depth: int) -> Optional[_Cell]:
        """Somebody off the direct line, their marriages, and everyone below."""
        if pid in used or pid not in scope:
            return None
        cell = new_cell(pid, depth)
        groups = child_groups(cell, depth - 1)
        cell.kids = groups
        cell.over = 0 if groups else -1
        cell.over_n = len(groups)
        return cell

    # ---- both lines running back, meeting at the marriage ----------------
    #
    # A couple's cell is flanked by the two families it joins: his behind him
    # on one side, hers behind her on the other, with their own children in
    # the middle and one ring further out.
    #
    #    [ his parents ][ his brothers ][ HIM | HER ][ her sisters ][ her parents ]
    #                                   [   their children   ]
    #
    # WHICH WAY ROUND MATTERS, and getting it wrong is what put a mother 89
    # degrees from her own brother. `pid` is not in the block this builds --
    # he is in the couple's cell outside it -- so his brothers and sisters
    # have to end up at the edge of the block NEAREST that cell, or the arc
    # over "him and his brothers" has to sweep across everything between.
    # Built one fixed way round, the block on the right came out as
    #
    #    [ her grandparents ][ her uncles ][ HER SISTERS ]   <- couple is left
    #
    # and the arc from her parents down to her and her sister crossed two
    # whole families. Mirrored, it is
    #
    #    [ HER SISTERS ][ her uncles ][ her grandparents ]
    #
    # and the arc is as short as it can be. 25 sweeping arcs on the owner's
    # tree, all of them this.
    def ancestry(pid: str, depth: int, side: int = -1) -> Optional[_Cell]:
        """The cell of `pid`'s parents, and everything behind them.

        `side` is which way this block lies from the couple that `pid` is in:
        -1 to its left, +1 to its right. It decides only the order of the
        blocks inside, never their content.
        """
        if s.max_generations is not None and depth > s.max_generations:
            return None
        pars = line_first([x for x in in_scope(graph.parents(pid, primary_only=True))
                           if x not in used])
        if not pars:
            return None
        cell = new_cell(pars[0], depth, extra=list(pars[1:2]))
        ups: list[_Cell] = []
        up_a = ancestry(cell.members[0], depth + 1, side)
        if up_a:
            ups.append(up_a)
        groups = child_groups(cell, depth - 1)
        for m in cell.members[1:]:
            up_b = ancestry(m, depth + 1, side)
            if up_b:
                ups.append(up_b)
                break
        # BOTH of this couple's own lines are on this same side, and only one
        # of them can be next to the couple. Whichever is further away has to
        # reach its own children across the other, so put the NARROWER of the
        # two in between: the reach is then as short as it can be. On the
        # owner's tree that is the difference between an arc crossing seven
        # cells and one crossing two.
        if len(ups) > 1:
            ups.sort(key=_cells_in, reverse=True)
        # Siblings nearest the couple; the generations behind them, further
        # away. The cell sits over the siblings either way.
        cell.kids = (ups + groups) if side < 0 else (groups + ups[::-1])
        cell.over = (len(ups) if side < 0 else 0) if groups else -1
        cell.over_n = len(groups)
        return cell

    me = descend(subj, 0)
    root = me
    pars = line_first([x for x in in_scope(graph.parents(subj, primary_only=True))
                       if x not in used])
    if pars and me is not None:
        parents_cell = new_cell(pars[0], 1, extra=list(pars[1:2]))
        kids: list[_Cell] = []
        up_a = ancestry(parents_cell.members[0], 2, side=-1)
        if up_a:
            kids.append(up_a)
        # my generation: me and my brothers and sisters, then any half
        # brothers and sisters, one group per marriage so each keeps its
        # own arc and the two never cross
        groups: list[_Cell] = []
        seen_u: set[str] = set()
        for m in parents_cell.members:
            for uid in graph.people[m].unions:
                if uid in seen_u:
                    continue
                seen_u.add(uid)
                kids_here = sorted({c for c in graph.unions[uid].children
                                    if c in scope}, key=born)
                blocks = []
                for k in kids_here:
                    if k == subj:
                        blocks.append(me)
                    else:
                        blk = descend(k, 0)
                        if blk:
                            blocks.append(blk)
                if blocks:
                    groups.append(_Cell(members=[], depth=0, kids=blocks))
        parents_cell.over = len(kids) if groups else -1
        parents_cell.over_n = len(groups)
        kids += groups
        for m in parents_cell.members[1:]:
            up_b = ancestry(m, 2, side=+1)
            if up_b:
                kids.append(up_b)
                break
        parents_cell.kids = kids
        root = parents_cell

    # ---- anyone the walk did not reach gets their own block ---------------
    blocks = [root]
    for pid in sorted(scope, key=born):
        if pid in used:
            continue
        top = pid
        for _ in range(40):
            nxt = next((x for x in in_scope(graph.parents(top, primary_only=False))
                        if x not in used and x != top), None)
            if not nxt:
                break
            top = nxt
        b = descend(top, 0)
        if b:
            blocks.append(b)

    # ---- lay it out ------------------------------------------------------
    acc: dict[int, tuple[float, float]] = {}
    xs: dict[str, float] = {}
    sib = max(0.0, float(s.sibling_gap))
    fam = max(sib, float(s.family_gap))
    for b in blocks:
        _tidy(b, sib, fam)
        b.rel = _clear(acc, b.contour, fam)
        _merge(acc, b.contour, b.rel)
    for b in blocks:
        _assign(b, b.rel, xs)
    if not xs:
        g.warnings.append("Nobody could be placed on this chart.")
        return g

    # ---- cells -> the 0..1 spread axis, oldest ring innermost -------------
    depths = {p: cell_of[p].depth for p in xs}
    top_depth = max(depths.values())
    lo = min(xs.values()) - 0.5
    raw = (max(xs.values()) + 0.5) - lo
    width = max(raw + SEAM, float(s.min_cells or MIN_CELLS))
    pad = (width - raw) / 2
    order = 0
    for anchor, x in sorted(xs.items(), key=lambda kv: kv[1]):
        cell = cell_of[anchor]
        ring = top_depth - cell.depth
        half = cell.width / 2
        for i, pid in enumerate(cell.members):
            p = graph.people[pid]
            if cell.split:
                # a leaf each, side by side on one ring
                a = x - half + i
                t0, t1 = (a - lo + pad) / width, (a + 1 - lo + pad) / width
                row = 0
            else:
                t0 = (x - half - lo + pad) / width
                t1 = (x + half - lo + pad) / width
                row = i
            g.slots[pid] = Slot(
                pid=pid, gen=ring, t0=t0, t1=t1, order=order,
                lineage=anchor, row=row, cell=anchor,
                partner_of=None if i == 0 else anchor,
                year=p.birth.sort_value, death_year=p.death.sort_value)
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
    g.roots = [p for p, sl in g.slots.items() if sl.gen == 0 and sl.row == 0]
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
