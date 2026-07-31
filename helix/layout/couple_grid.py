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
# TWO EXPERIMENTS, both of which measured worse. Left here as constants so the
# next person re-runs them rather than re-invents them; `tools/ink_check.py`
# and the elbow count in the commit message are the numbers to beat.
#
# LEAN   how far a couple leans over their own children toward the child of
#        theirs who is drawn somewhere else -- the one they have a long line
#        to. 0 is dead centre, 1 hard against the edge. It shortens that line
#        and costs a bracket on the other side: 9 brackets and 270 degrees of
#        detour at 0, 10 and 266 at 0.5. No gain, and one more name shortened.
# FLANK  put the couple BETWEEN its two ancestral lines instead of beyond
#        both, so each partner has their own behind them. Reads beautifully
#        in the abstract and is worse on the sheet, because the couple's own
#        children stop being at the edge of the block nearest the descendant
#        it hangs from: crossings 5 -> 12, detour 270 -> 359 degrees.
LEAN = 0.0
FLANK = False


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
    uid: str = ""                              # which marriage a group holds
    over: int = -1
    over_n: int = 1                            # how many of them are children
    # +1 or -1: which side the ONE child of this couple who is not in this
    # block lies on. The couple leans that way over their children, because
    # the line to that child is the only long one they have.
    lean: int = 0
    # WHICH WAY ROUND THE LEAVES GO, when the search has an opinion. `outward`
    # decides it greedily from where each partner's kin ended up, which is
    # right on its own but cannot see that swapping the leaves AND moving a
    # block would clear a crossing that neither does alone. The search sets
    # this; 0 means "no opinion, let `outward` choose".
    flip: int = 0
    # WHERE A COUPLE WITH NO CHILDREN OF THEIR OWN HERE SITS. `over` cannot
    # say it: there is no group of children for them to be over, because
    # their one child is out in the cell this whole block hangs from. They
    # used to go after everything, hard against one end, which put the two
    # families behind them BOTH on one side and gave whichever ended up
    # further away a bracket right across the other. `seat` is how many of
    # `kids` go before them.
    seat: int = -1
    ups_n: int = 0                             # how many kids are ancestral
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


def _clear(acc: dict, other: dict, gap: float, fam: float = 0.0,
           near: int = -1) -> float:
    """How far right `other` must move to clear everything left of it.

    Reingold-Tilford's contour step, and the whole non-overlap guarantee.
    Indexed by RING rather than by depth in the tree, because a cousin's
    block reaches back out to your own ring and separating by depth would
    let two cells share an angle.

    Nesting is allowed and wanted: a couple's children are narrower than the
    two families flanking them, and they tuck in underneath. What is NOT
    allowed is two cells on one ring at one angle, which is what the ring
    index prevents.

    `near` is THE ONE RING ON WHICH THESE TWO BLOCKS ARE SIBLINGS. There,
    and only there, they get the close sibling gap; on every other ring they
    are cousins, or cousins' children, and get the gap between families. One
    gap for the whole contour meant two sisters sitting close -- rightly --
    put their children the same distance apart on the ring outside, and two
    first cousins were spaced exactly like brother and sister.
    """
    need = 0.0
    for ring, (lo, _hi) in other.items():
        if ring in acc:
            g = gap if (near < 0 or ring == near) else max(gap, fam)
            need = max(need, acc[ring][1] + g - lo)
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
    #
    # Close ON THEIR OWN RING and nowhere else, though: two sisters belong
    # side by side, their children are cousins and belong apart. `near` says
    # which ring that is -- the depth the blocks in this container sit at.
    gap = sib if not cell.members else fam
    near = (cell.kids[0].depth if not cell.members and cell.kids else -1)

    o0 = cell.over if cell.members else -1
    o1 = o0 + cell.over_n - 1
    acc: dict[int, tuple[float, float]] = {}
    # A couple with no children of their own in this block still has to sit
    # SOMEWHERE among the families behind them, and `seat` says how many of
    # them go first. Unset means last, which is where they always used to go.
    cut = (max(o0, 0) if o0 >= 0
           else (max(0, min(cell.seat, len(cell.kids))) if cell.seat >= 0
                 else len(cell.kids)))

    # 1 -- everything to the left of the couple's own children
    for k in cell.kids[:cut]:
        if k.contour:
            k.rel = _clear(acc, k.contour, gap, fam, near)
            _merge(acc, k.contour, k.rel)

    # 1b -- and the couple themselves, when that is all the seat they get
    if cell.members and o0 < 0:
        half = cell.width / 2
        x = half if not acc else max(v[1] for v in acc.values()) + fam + half
        cell.x = x
        _merge(acc, {cell.depth: (x - half, x + half)}, 0.0)

    # 2 -- the children, then the couple centred over them
    if o0 >= 0:
        run = [k for k in cell.kids[o0:o1 + 1] if k.contour]
        inner: dict[int, tuple[float, float]] = {}
        for k in run:
            k.rel = _clear(acc, k.contour, gap, fam, near) if not inner \
                else _clear(inner, k.contour, gap, fam, near)
            if inner:
                k.rel = max(k.rel, _clear(acc, k.contour, gap, fam, near))
            _merge(inner, k.contour, k.rel)
        if run:
            lo = min(_span(k)[0] for k in run)
            hi = max(_span(k)[1] for k in run)
            # OVER THEIR CHILDREN, and toward the one who is not here. A stem
            # reaches the nearest END of a run of children side by side, so
            # leaning costs that stem nothing -- and it comes straight off the
            # long line to the child out in the cell this block hangs from.
            # Kathleen's parents sat in the middle of the seven children still
            # at home and 103 degrees from her; leaning halves that.
            mid = (lo + hi) / 2
            x = mid + (hi - lo) / 2 * LEAN * cell.lean
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
    for k in cell.kids[max(o1 + 1, 0) if o0 >= 0 else cut:]:
        if k.contour:
            k.rel = _clear(acc, k.contour, gap, fam, near)
            _merge(acc, k.contour, k.rel)

    if not cell.members:
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

    def _families(pid: str) -> int:
        """How many of this person's marriages put children on the chart."""
        return sum(1 for uid in graph.people[pid].unions
                   if any(c in scope for c in graph.unions[uid].children))

    def _married(a: str, b: str) -> bool:
        return bool(set(graph.people[a].unions) & set(graph.people[b].unions))

    def pairs_adjacent(members: list[str]) -> list[str]:
        """Arrange leaves so every married pair is side by side.

        A leaf with three names in it is somebody and their two spouses, and
        [him, HER, the other him] is the only order where both marriages are
        neighbours: each rule joins two adjacent leaves and each family's
        stem leaves from between the right two. Any other order draws a rule
        between two people who never met.
        """
        if len(members) < 3:
            return list(members)
        deg = {m: sum(1 for n in members if n != m and _married(m, n))
               for m in members}
        rest = sorted(members, key=lambda m: (deg[m], members.index(m)))
        out, left = [rest[0]], [m for m in members if m != rest[0]]
        while left:
            nxt = next((m for m in left if _married(out[-1], m)), left[0])
            out.append(nxt)
            left.remove(nxt)
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
        # TWO MARRIAGES THAT BOTH HAD CHILDREN cannot share a leaf. Stacked,
        # a great-grandmother's two husbands sit under her with both families
        # hanging off the same leaf, and which children are whose stops being
        # something you can see -- it becomes something you work out from
        # which row a stem left. Given a leaf each, the order reads
        #
        #     [ first husband ][ HER ][ second husband ]
        #
        # with a rule between each married pair and each family's stem
        # leaving from between the right two.
        #
        # A single marriage is different and stays stacked, however many
        # children it had: there is only one family, so there is nothing to
        # tell apart. That is the owner's own distinction -- Doreen, who had
        # two, against Heather, who had one.
        if any(_families(m) > 1 for m in members):
            return True
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
                    groups.append(_Cell(members=[], depth=depth,
                                        kids=blocks, uid=uid))
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
        # `pid`'s OWN brothers and sisters go nearest `pid`; a half-brother
        # from the same parent's other marriage belongs beyond them. One
        # group per marriage already, but ordered by which spouse came first
        # they interleaved: the arc over Paul, Gorden and Derek ran straight
        # over Barry, who is their half-brother by a different father and has
        # an arc of his own. Two arcs for two marriages is the whole point of
        # keeping them separate; they must not overlap.
        mine = graph.people[pid].child_of
        groups.sort(key=lambda blk: blk.uid != mine, reverse=side < 0)
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
        # Putting the couple BETWEEN its two lines was tried, because that is
        # what a marriage is -- the place two lines meet -- and it reads
        # beautifully in the abstract:
        #
        #   [ her family ][ HER | HIM ][ his family ]
        #
        # It is worse. The couple's own children stop being at the edge of the
        # block nearest the descendant it hangs from, so THAT arc needs a
        # bracket, and on the owner's tree the crossings went from five to
        # twelve and the detour from 270 degrees to 359. Both lines on one
        # side, narrower one nearest, stands.
        if FLANK and len(ups) > 1 and groups:
            cell.kids = ([ups[1]] + groups + [ups[0]] if side < 0
                         else [ups[0]] + groups + [ups[1]])
            cell.over = 1
        else:
            cell.kids = (ups + groups) if side < 0 else (groups + ups[::-1])
            cell.over = (len(ups) if side < 0 else 0) if groups else -1
        cell.over_n = len(groups)
        cell.ups_n = len(ups)
        # AND WHEN THERE ARE NO CHILDREN HERE, BETWEEN THE TWO LINES.
        #
        # This is FLANK, which measured badly and is off -- for the case it
        # was written for. Putting a couple between their two families when
        # they have children in this block moves those children off the edge
        # nearest the descendant the block hangs from, and the stem down to
        # them then needs a bracket: crossings 5 -> 12 on the owner's tree.
        #
        # With NO children here there is nothing to move off the edge, and
        # the objection evaporates. What is left is the whole point of the
        # shape -- his family behind him, hers behind her, the two meeting at
        # the marriage -- and both families reach their own child without
        # crossing the other. On the smallest chart that has the case at all,
        # two families of three, it is the difference between two brackets
        # sweeping 116 degrees each and no bracket at all.
        cell.seat = 1 if (len(ups) > 1 and not groups) else len(cell.kids)
        # WHICH WAY THIS COUPLE LEANS OVER THEIR CHILDREN. `pid` is one of
        # them and is NOT in this block -- he is out in the cell this block
        # hangs from -- so the line to him is the long one, and every
        # millimetre the couple moves his way comes straight off it.
        #
        # It costs nothing at the other end: a stem only has to reach the
        # NEAREST END of a run of children side by side, not their middle, so
        # leaning does not lengthen anything.
        cell.lean = 1 if side < 0 else -1
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
    sib = max(0.0, float(s.sibling_gap))
    fam = max(sib, float(s.family_gap))

    def place() -> dict[str, float]:
        acc: dict[int, tuple[float, float]] = {}
        out: dict[str, float] = {}
        for b in blocks:
            _tidy(b, sib, fam)
            b.rel = _clear(acc, b.contour, fam)
            _merge(acc, b.contour, b.rel)
        for b in blocks:
            _assign(b, b.rel, out)
        return out

    # ---- IS THIS THE BEST ORDER? -----------------------------------------
    #
    # Everything above builds ONE arrangement, following the walk out from
    # the subject. Nothing asked whether a different order of the same blocks
    # would read better, and one of them always does: the number of branches
    # that cross depends entirely on which side of a couple each family sits.
    #
    # The fault that made this necessary: Kathleen's parents' branch, holding
    # all seven of her brothers and sisters, ran straight through Thomas and
    # Florence's branch down to Peter -- her husband. Two families crossing
    # at the very point they marry, which reads as though she married her own
    # cousin. Swapping the two blocks either side of that couple fixes it and
    # costs nothing, and nothing in the code was looking.
    #
    # HOW MANY CROSS, from the positions alone: a family whose children are
    # not beside them needs a bracket, and that bracket crosses the descent
    # line of every couple it passes on its own ring. Count those. It needs
    # no drawing and no geometry, so it is cheap enough to run inside a
    # search.
    def cost(xs: dict[str, float]) -> tuple[int, float]:
        # PER LEAF, not per cell. `xs` gives one x to a whole cell, so a
        # couple with a leaf each collapsed to a single point and the run
        # detection below could never see anybody standing between two of a
        # union's children -- the cost came out zero on a chart with five
        # crossings on it, and the search never ran.
        # EVERY PERSON, not every anchor. `_assign` records one x per CELL,
        # under its first member, so looking people up in it directly missed
        # every married-in partner -- including Kathleen, whose crossing this
        # search exists to find. The cost came out zero on a chart with five
        # crossings and the search never ran once.
        at: dict[str, float] = {}
        for p, c in cell_of.items():
            if not c.members or c.members[0] not in xs:
                continue
            base = xs[c.members[0]]
            if c.split and len(c.members) > 1:
                order = pairs_adjacent(c.members)
                if c.flip < 0:
                    order = order[::-1]
                at[p] = base - c.width / 2 + order.index(p) + 0.5
            else:
                at[p] = base
        xs = at
        depth = {p: cell_of[p].depth for p in xs}
        rows: dict[int, list] = {}
        for p, x in xs.items():
            rows.setdefault(depth[p], set()).add(round(x, 6))
        rows = {d: sorted(v) for d, v in rows.items()}

        # WHERE EVERY STEM LEAVES AND LANDS, worked out the same way the
        # engine will draw it. This has to mirror `family._stem_runs`; where
        # the two disagree the search optimises something the chart does not
        # do.
        #
        # ONE ENTRY PER MARRIAGE, not per cell. Modelled per cell, a man who
        # married twice had both his stems at one point, so the reach of one
        # marriage could never be seen to cross the stem of the other -- and
        # that is the commonest crossing on the chart. Lorain and David's
        # children crossed Michaela and David's for exactly this reason and
        # the search could not see it.
        stems = []
        for uid, u in graph.unions.items():
            kids = [c for c in u.children
                    if c in xs and graph.people[c].child_of == uid]
            ps = [p for p in u.partners if p in xs]
            if not kids or not ps:
                continue
            d_kid = depth[kids[0]]
            # THE PARENT ON THE RING THE CHILDREN HANG FROM. Mirrors the
            # anchor rule in `family._stem_runs`: when both partners were
            # born into the tree their families can sit at different depths,
            # and only the one directly inside the children can carry the
            # bracket.
            head_p = max(ps, key=lambda p: (depth[p] == d_kid + 1, ))
            c = cell_of[head_p]
            same = [p for p in ps if cell_of[p] is c]
            if c.split and len(same) > 1:
                ts = sorted(xs[p] for p in same)
                lo_h = ts[0] + (ts[-1] - ts[0]) * 0.2
                hi_h = ts[0] + (ts[-1] - ts[0]) * 0.8
            else:
                base = xs[head_p]
                lo_h, hi_h = base - c.width * 0.20, base + c.width * 0.20
            mid_h = (lo_h + hi_h) / 2
            kset = {round(xs[k], 6) for k in kids}
            runs, cur = [], []
            for x in rows.get(d_kid, ()):
                if x in kset:
                    cur.append(x)
                elif cur:
                    runs.append(cur)
                    cur = []
            if cur:
                runs.append(cur)
            for run in runs or [sorted(kset)]:
                lo_r, hi_r = run[0], run[-1]
                head = (mid_h if lo_r - 1e-9 <= mid_h <= hi_r + 1e-9
                        else min(max((lo_r + hi_r) / 2, lo_h), hi_h))
                stems.append((d_kid, head, min(max(head, lo_r), hi_r), uid))

        # A reach travels the gap between two rings. Everything else in that
        # gap is a radial line -- another family's stem, or the drop at the
        # far end of another family's reach -- so anything whose angle falls
        # strictly inside the reach is a line it has to pass through.
        cross, reach = 0, 0.0
        for d, h, f, uid in stems:
            if abs(f - h) < 1e-9:
                continue                        # straight out; no bracket
            a, b = min(h, f), max(h, f)
            reach += b - a
            for d2, h2, f2, uid2 in stems:
                if d2 != d or uid2 == uid:
                    continue
                if a + 1e-6 < h2 < b - 1e-6:
                    cross += 1
                if abs(f2 - h2) > 1e-9 and a + 1e-6 < f2 < b - 1e-6:
                    cross += 1
        return cross, round(reach, 4)

    def every(c: _Cell, out: list) -> list:
        out.append(c)
        for k in c.kids:
            every(k, out)
        return out

    def options(cell: _Cell):
        """Re-orderings of one cell's blocks that keep its own children in a
        run -- the couple has to stay over them."""
        n = len(cell.kids)
        if n < 2:
            return
        o0 = cell.over if cell.members and cell.over >= 0 else 0
        o1 = o0 + cell.over_n - 1 if cell.members and cell.over >= 0 else n - 1
        for i in range(n - 1):
            if (i + 1 < o0) or (i > o1) or (o0 <= i and i + 1 <= o1):
                k = list(cell.kids)
                k[i], k[i + 1] = k[i + 1], k[i]
                yield k, cell.over, cell.flip
        # ...reverse the leaves of a couple, so each partner faces their own
        # family. On its own it moves a name by one leaf and changes nothing;
        # combined with moving the block wedged between them it is what puts
        # a wife back beside her own brothers and sisters.
        if cell.split and len(cell.members) > 1:
            yield list(cell.kids), cell.over, -cell.flip if cell.flip else -1
        # ...and the one that matters: take the block wedged between the
        # couple and the family beyond it, and put it on the other side.
        if cell.members and cell.over > 0:
            k = list(cell.kids)
            moved = k.pop(o0 - 1)
            k.insert(o1, moved)
            yield k, cell.over - 1, cell.flip
        if cell.members and 0 <= cell.over and o1 < n - 1:
            k = list(cell.kids)
            moved = k.pop(o1 + 1)
            k.insert(o0, moved)
            yield k, cell.over + 1, cell.flip

    best = cost(place())

    # ---- THE HINGES, TRIED EXHAUSTIVELY ----------------------------------
    #
    # A hinge is a couple with a documented family behind EACH of them: the
    # place two lines meet. There are only a few on any chart -- three on the
    # owner's -- and they are where the crossings come from, because each has
    # to decide which line sits nearer and which way round its own two leaves
    # go. Those two choices are not independent: reversing the leaves alone
    # moves a name by one leaf and changes nothing, and moving the block alone
    # puts the wrong partner beside the wrong family. Only TOGETHER do they
    # put a wife back beside her own brothers and sisters.
    #
    # A hill-climb cannot find that -- neither half is an improvement on its
    # own -- so the hinges are enumerated instead: four arrangements each,
    # every combination, best kept. Few enough that it is cheap and complete.
    # A HINGE IS ANY CELL WITH A REAL CHOICE TO MAKE. Two ancestral lines to
    # order, or two sets of children to put on one side or the other, or a
    # pair of leaves that could go either way round. Each of those is free --
    # nothing in the family says which -- and each changes what crosses.
    #
    # It was only the couples where two documented lines meet. That missed
    # every REMARRIAGE, and a remarriage has the most obvious choice of the
    # lot: David's children by Lorain and his children by Michaela sat on
    # sides that made their two stems cross, when swapping them costs
    # nothing. Anything with a choice is enumerated now.
    #
    # AND THE ORDER OF BROTHERS AND SISTERS. A container holds one union's
    # children, and which of them sits at which end decides how far the one
    # who married out has to reach back. Margret Reed's parents had to cross
    # three families to reach her because she was at the wrong end of her own
    # sibling group, and nothing was free to move her.
    # AND A COUPLE WITH NO CHILDREN OF THEIR OWN ON THE CHART STILL HAS TWO
    # LINES TO ORDER. `over` is -1 for them -- there is no group of children
    # for the couple to sit over, because their one child is out in the cell
    # this whole block hangs from -- and requiring `over >= 0` quietly
    # excluded exactly the couples where two families meet and nothing else
    # is going on. Margret Reed's is one: her parents and Paul's are both
    # behind her, the Murraycarrs were put on the far side, and their arc
    # back to her crossed three Reed families. One swap fixes it, and the
    # search was not allowed to try it.
    def pick_hinges() -> list[_Cell]:
        h = [c for c in every(root, [])
             if (c.members
                 and (c.ups_n > 1 or c.over_n > 1
                      or (c.split and len(c.members) > 1)))
             or (not c.members and len(c.kids) > 1)]
        h.sort(key=lambda c: -(c.ups_n + c.over_n + len(c.kids)))
        return h[:32]

    def variants(c: _Cell):
        if not c.members:
            # A CONTAINER of one union's children: any of them may take
            # either end, and the one who married out wants the end nearest
            # the family they married into.
            n = len(c.kids)
            seen = {tuple(id(k) for k in c.kids)}
            yield list(c.kids), c.over, c.flip, c.seat
            for k in (c.kids[::-1], *(
                    [c.kids[i]] + c.kids[:i] + c.kids[i + 1:] for i in range(n)),
                    *(c.kids[:i] + c.kids[i + 1:] + [c.kids[i]]
                      for i in range(n))):
                key = tuple(id(x) for x in k)
                if key not in seen:
                    seen.add(key)
                    yield list(k), c.over, c.flip, c.seat
            return
        # FOUR FREE DECISIONS, none of them any use alone:
        #   which of two ancestral lines sits nearer the couple
        #   which side each family's children go on
        #   whether the couple sits beyond both lines or BETWEEN them
        #   which way round the couple's own two leaves go
        # WHERE THIS CELL'S ANCESTRAL BLOCKS ACTUALLY ARE. They are contiguous
        # and lie on one side of the couple's own children, but WHICH side
        # depends on which way the block was built: `ups + groups` on the
        # left, `groups + ups` reversed on the right. Derived as
        # `over - ups_n` it was right for the left-hand case and negative for
        # the right-hand one, so half the couples on any chart never had
        # their two lines swapped at all.
        n = len(c.kids)
        if c.over < 0:
            ulo, uhi = 0, n                  # no children here: all ancestry
        elif c.over > 0:
            ulo, uhi = 0, c.over
        else:
            ulo, uhi = c.over_n, n
        base = [(list(c.kids), c.over)]
        if uhi - ulo >= 2 and c.ups_n >= 2:
            sw = list(c.kids)
            sw[ulo:uhi] = sw[ulo:uhi][::-1]
            base.append((sw, c.over))
        if c.over >= 0 and c.over_n > 1:
            for kids, over in list(base):
                k = list(kids)
                k[over:over + c.over_n] = k[over:over + c.over_n][::-1]
                base.append((k, over))
        for kids, over in list(base):
            if over > 0:
                k = list(kids)
                k.insert(over - 1 + c.over_n, k.pop(over - 1))
                base.append((k, over - 1))
        # ...and WHERE AMONG THEM THE COUPLE SITS, when they have no children
        # here to be over. Between their two families is the right answer
        # nearly always -- it is the shape the whole layout is named for --
        # but it costs them adjacency to the one child of theirs who IS drawn
        # elsewhere, so on some trees an end is better. Offered as a choice
        # rather than fixed, the search keeps whichever measures.
        seats = (range(len(c.kids) + 1) if c.over < 0 and len(c.kids) > 1
                 else (c.seat,))
        for kids, over in base:
            for flip in ((1, -1) if c.split and len(c.members) > 1
                         else (c.flip,)):
                for seat in seats:
                    yield kids, over, flip, seat
    # HOW GOOD IS THE ANSWER? Coordinate descent finds a local best, and a
    # local best is worth nothing unless you know how deep the well is. So:
    # shuffle every free choice on the chart -- sibling order in every group,
    # every leaf flip, every seat -- and run the whole search again from
    # there. Twenty-five random starts on the owner's tree began between 9
    # and 11 crossings with 51 to 59 cells of reach, and all twenty-five
    # ended on exactly 4 and 30.39. The four that are left are what the
    # family is, not where the search gave up; clearing them means giving it
    # a move it does not have, and the two obvious candidates are written up
    # above and below this function.
    #
    # ROUND AND ROUND THE HINGES until nothing moves. Every arrangement of
    # every hinge was tried as a product first, which is exponential and
    # took twenty seconds on a 142-name chart -- and a chart with new
    # families added to it is the whole point. One hinge at a time, holding
    # the rest still, repeated to convergence: the same answer on every tree
    # tried, in time that grows with the number of hinges rather than as a
    # power of it.
    def sweep_hinges() -> None:
        nonlocal best
        hinges = pick_hinges()
        if not hinges or not best[0]:
            return
        for _sweep in range(6):
            shifted = False
            for c in hinges:
                if not best[0]:
                    break
                keep = (list(c.kids), c.over, c.flip, c.seat)
                best_here = best
                for kids, over, flip, seat in list(variants(c)):
                    c.kids, c.over, c.flip, c.seat = (list(kids), over,
                                                      flip, seat)
                    got = cost(place())
                    if got < best_here:
                        best_here = got
                        keep = (list(kids), over, flip, seat)
                        shifted = True
                c.kids, c.over, c.flip, c.seat = keep
                best = best_here
            if not shifted or not best[0]:
                break

    # WHOSE FAMILY A MARRIED COUPLE HANGS FROM was written as a move too,
    # and removed. The idea is sound: a couple's cell hangs beneath one
    # family, his or hers, and when both are documented the walk takes
    # whichever it reached first -- so the other family may have to reach
    # right across the chart to draw its own child. Lifting the cell into the
    # other partner's sibling group would settle that by measurement instead
    # of by walk order.
    #
    # It can never fire, and the reason is structural: the walk marks a
    # spouse USED the moment it takes them into a cell, so the family they
    # were born into never forms a group containing them. There is no second
    # home to move to. Nought candidates on all three sample files at every
    # focus setting. Fixing that class means changing the WALK -- letting
    # both families claim a couple and choosing afterwards -- not adding
    # another move to this search.
    #
    # What did fix the case it was written for was letting a couple with no
    # children of their own on the chart be a hinge at all; see `pick_hinges`.
    sweep_hinges()

    if best[0]:
        for _round in range(8):
            moved = False
            pool: list = []
            for b in blocks:
                every(b, pool)
            for cell in sorted(pool, key=lambda c: (c.depth, len(c.kids))):
                if best[0] == 0:
                    break
                keep = (list(cell.kids), cell.over, cell.flip)
                for kids, over, flip in list(options(cell)):
                    cell.kids, cell.over, cell.flip = kids, over, flip
                    got = cost(place())
                    if got < best:
                        best, keep = got, (kids, over, flip)
                        moved = True
                cell.kids, cell.over, cell.flip = keep
            if not moved or best[0] == 0:
                break

    xs = place()
    # ON THE RECORD, so the engine's drawing can be checked against it. The
    # scale goes with the numbers: the search measures in cells and the chart
    # in fractions of a turn, and without the divisor the two cannot be
    # compared at all.
    g.search = {"crossings": best[0], "reach_cells": best[1]}
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
    g.search["cells_per_turn"] = width
    # ---- which way round a SPLIT leaf goes -------------------------------
    #
    # A split couple takes two leaves side by side, and the one that is NOT a
    # brother or sister of the group around them has to be on the outside.
    # Put them on the inside and the arc drawn over "Paul, Derek and Gorden"
    # runs straight over Paul's wife, who reads as a fourth sibling. Reported
    # on the owner's own tree, and it is the one thing a chart may never do:
    # say somebody is a sibling when they are a spouse.
    #
    # Which side is "outside" is not known until every cell has an x, so it
    # is decided here rather than when the cell was built.
    def _kin_x(pid: str, cell) -> Optional[float]:
        """Where this person's brothers and sisters are, on average, if any of
        them are drawn somewhere other than this same leaf."""
        uid = graph.people[pid].child_of
        u = graph.unions.get(uid) if uid else None
        if not u:
            return None
        at = [xs[cell_of[c].members[0]] for c in u.children
              if c != pid and c in cell_of and cell_of[c] is not cell
              and cell_of[c].members[0] in xs]
        return sum(at) / len(at) if at else None

    def outward(anchor: str) -> list[str]:
        """Which way round the leaves of a split cell go.

        ONE rule, for any number of leaves: every member stands on the side
        their own brothers and sisters are on. Marriages have to stay
        adjacent, so there are only two orders to choose between -- the
        marriage-adjacent one and its reverse -- and this takes whichever
        satisfies more of them.

        What it prevents, generally: two sibling arcs on the same ring
        OVERLAPPING. Michaela's arc to her brother ran 84.9 to 130.5 degrees
        and David's to his ran 64.6 to 97.6, half a millimetre apart in
        radius, so the two drew as ONE continuous ring passing through the
        pair -- reading as though the husband and wife were also brother and
        sister. Any interleaved pair of groups does that; ordering each
        partner toward their own kin is what stops it happening at all.
        """
        cell = cell_of[anchor]
        if not cell.split or len(cell.members) < 2:
            return cell.members
        order = pairs_adjacent(cell.members)
        if cell.flip:
            return order[::-1] if cell.flip < 0 else order
        here = xs[anchor]

        def score(seq: list[str]) -> float:
            n, good = len(seq), 0.0
            for i, pid in enumerate(seq):
                mid = _kin_x(pid, cell)
                if mid is None:
                    continue
                # nearer kin pull harder: a group just off the end matters
                # more than one on the far side of the chart
                w = 1.0 / (1.0 + abs(mid - here))
                good += w if (mid > here) == (i > (n - 1) / 2) else -w
            return good

        rev = order[::-1]
        return order if score(order) >= score(rev) else rev

    order = 0
    for anchor, x in sorted(xs.items(), key=lambda kv: kv[1]):
        cell = cell_of[anchor]
        ring = top_depth - cell.depth
        half = cell.width / 2
        for i, pid in enumerate(outward(anchor)):
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
