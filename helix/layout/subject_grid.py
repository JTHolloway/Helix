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

WHAT THIS DOES INSTEAD. Two independent decisions, in this order.

RING comes from a breadth-first walk out from the subject: your parents are
one ring in, your grandparents two, your children one out. A spouse is
always the same ring as their partner, a sibling always the same as you.

ANGLE comes from a tidy tree (Reingold-Tilford), run once over the whole
chart. Nothing else allocates angle. See below for why that mattered.

THE BUG THIS FILE WAS REWRITTEN TO FIX
--------------------------------------
Angle used to be handed out in four places -- an `ascend` pass, a `descend`
pass, a sibling flanking loop and a fallback attach pass -- each with its own
heuristic and none aware of the others. On a real 142-person tree that gave
77 sibling arcs sweeping across unrelated people and 10 pairs sitting at
exactly the same angle. `docs/KNOWN_ISSUE_LAYOUT.md` has the measurements.

The cure is structural, not another heuristic: build ONE tree of blocks,
then separate sibling blocks using contours, which is the only step the old
code had no equivalent of and the reason things collided.

THE TREE
--------
A node is a COUPLE, which is the right unit -- it is what keeps a husband
beside his wife through every later step. A node owns a run of adjacent
slots on its own ring, one per member, and a list of child BLOCKS laid out
left to right around them:

    [ his parents ][ his siblings ][ HIM | HER ][ her siblings ][ her parents ]

Read that ordering carefully, because three of the four guarantees come out
of it and nothing else:

  * Him beside her, because the couple's slots are one run. A couple never
    gets separated by anything.
  * His siblings contiguous with him, because they sit immediately to his
    left and his own block ends at his slot. The sibling arc over that
    union therefore spans its own group and stops.
  * His parents' block entirely outside that group, so the cousins inside it
    can never land between two siblings.

Descendants hang below, and a collateral relative's block centres its couple
over their children in the ordinary tidy-tree way.

WHERE THIS DEPARTS FROM TEXTBOOK REINGOLD-TILFORD, AND WHY
----------------------------------------------------------
Two adaptations, both forced by the shape of a family chart.

1. Contours are indexed by RING, not by tree depth. In a family a block's
   depth and its ring come apart -- a cousin's block reaches back out to
   your own ring -- so separating by depth would let two people share an
   angle. Indexing the contour by the ring a person actually sits on is
   what makes "no two people overlap" true rather than approximately true.

2. A node is not centred over its children. In a drawn tree the parent is a
   separate mark above its children; here the couple occupies its own ring
   and is simply one more item in the left-to-right sequence. Centring it
   would pull each ancestor away from the edge of their own sibling group,
   which is exactly the adjacency the ordering above exists to create.

The contour merge itself -- push the right-hand block clear of everything to
its left, at every ring they share -- is unchanged, and that is where the
non-overlap guarantee comes from.

WHAT THIS STILL CANNOT DO
-------------------------
Two limits, both proved rather than assumed. Do not spend a session
rediscovering them.

1. A married-in spouse sits on their partner's ring, because that is what
   ring means. So in a sibling group whose middle children are married,
   their partners are inevitably between the outermost siblings. Nothing
   can place them elsewhere except exiling every spouse outside the group,
   which breaks up the couples this file exists to keep together. In the
   shipped sample that would mean separating seven marriages to tidy one
   arc. `tools/diagnose_layout.py` counts those separately from a genuine
   stranger under an arc, which is the thing that must stay at zero.

2. The Thread sweeps. A direct-line ancestor is adjacent to their parent
   and to their own brothers and sisters, which uses both sides of them;
   their child then sits beyond that sibling group, roughly a sibling
   group's width away. Ordinary parent-to-child links are unaffected --
   the median across the whole chart is about 6 degrees -- but the
   subject's own line can span a hundred and more.

   It is worth being precise about why, because the obvious fix is worse.
   A person on the line needs to touch three things: their parent, their
   siblings, and their child. A slot has two sides. Ordering the couple
   first instead, so the line runs radially, pushes each ancestor's
   sibling arc across the entire outward tree -- which is exactly the
   defect this file was written to remove, traded for a cosmetic gain on
   one highlighted path. Tight sibling arcs win.

3. Cousin marriage. When BOTH partners were born into the chart, neither
   of them married in, so each belongs in their own family's block and the
   two blocks are nowhere near each other. On the shipped sample that is 2
   couples out of 230, and only at `--focus all`. Merging the two blocks
   is the non-planar case the README already rules out; those marriages
   are meant to be drawn as a chord across the disc.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .base import Grid, LayoutSettings, Slot

# Blank slots left between two adjacent blocks. Below about half a slot two
# families read as one.
GAP = 0.6
# Blank slots at the 0/360 seam, so the first and last block do not fuse into
# each other on a disc.
SEAM = 2.0
# Fewest slots the disc is ever divided into. Without a floor, a nine-person
# direct-line chart gives every person a quadrant to themselves: the couples
# are still adjacent, but "adjacent" is 90 degrees and they no longer read as
# married. A sparse chart is drawn compact and centred instead.
MIN_SLOTS = 24.0


# ============================================================ the block tree ==
@dataclass
class _Node:
    """One couple, their slots, and the blocks arranged around them."""

    members: list[tuple[str, int]] = field(default_factory=list)   # (pid, ring)
    kids: list["_Node"] = field(default_factory=list)
    # False: the members sit at a fixed point in the sequence (`mem_index`),
    # which is what puts a direct-line ancestor on the edge of their own
    # sibling group. True: the members centre over their children, the
    # ordinary tidy-tree placement, used for everyone off the direct line.
    centre_members: bool = True
    mem_index: int = 0
    rel: float = 0.0            # x of this block inside its parent
    mem_rel: float = 0.0        # x of the members' run inside this block
    contour: dict[int, tuple[float, float]] = field(default_factory=dict)


def _mem_contour(node: _Node) -> dict[int, tuple[float, float]]:
    """The members' own footprint, one slot each, at their own rings."""
    out: dict[int, tuple[float, float]] = {}
    for i, (_pid, ring) in enumerate(node.members):
        lo, hi = float(i), float(i + 1)
        if ring in out:
            out[ring] = (min(out[ring][0], lo), max(out[ring][1], hi))
        else:
            out[ring] = (lo, hi)
    return out


def _merge(acc: dict, other: dict, dx: float) -> None:
    for ring, (lo, hi) in other.items():
        lo, hi = lo + dx, hi + dx
        if ring in acc:
            acc[ring] = (min(acc[ring][0], lo), max(acc[ring][1], hi))
        else:
            acc[ring] = (lo, hi)


def _clear(acc: dict, other: dict) -> float:
    """How far right `other` must move to clear `acc` on every shared ring.

    This one function is the whole non-overlap guarantee. Blocks that share
    no ring may nest into each other, which is the point of a tidy tree --
    a deep narrow family tucks in beside a shallow wide one instead of
    reserving a column it does not use.
    """
    need = 0.0
    for ring, (lo, _hi) in other.items():
        if ring in acc:
            need = max(need, acc[ring][1] + GAP - lo)
    return max(0.0, need)


def _tidy(node: _Node) -> None:
    """Pass one, bottom-up: give every block a position inside its parent."""
    for k in node.kids:
        _tidy(k)

    acc: dict[int, tuple[float, float]] = {}
    mem = _mem_contour(node)

    seq: list[Optional[_Node]] = list(node.kids)
    if not node.centre_members:
        seq.insert(min(node.mem_index, len(seq)), None)   # None == the members

    for item in seq:
        shape = mem if item is None else item.contour
        if not shape:
            continue
        dx = _clear(acc, shape)
        if item is None:
            node.mem_rel = dx
        else:
            item.rel = dx
        _merge(acc, shape, dx)

    if node.centre_members and mem:
        if not acc:
            node.mem_rel = 0.0
        elif any(r in acc for r in mem):
            # A child of this couple sits on the SAME ring as the couple.
            # Real data does this: with pedigree collapse, the walk out from
            # the subject can reach a woman as somebody's sister before it
            # reaches her as somebody's mother, and the shorter path wins.
            # Centring would then drop the parents into the middle of their
            # own children's arc, and they would read as two more siblings.
            # Stand them outside it instead.
            node.mem_rel = (min(v[0] for v in acc.values())
                            - len(node.members) - GAP)
        else:
            lo = min(v[0] for v in acc.values())
            hi = max(v[1] for v in acc.values())
            node.mem_rel = (lo + hi) / 2 - len(node.members) / 2
        _merge(acc, mem, node.mem_rel)

    node.contour = acc


def _assign(node: _Node, x0: float, out: dict[str, float]) -> None:
    """Pass two, top-down: accumulate the shifts into absolute positions."""
    base = x0 + node.mem_rel
    for i, (pid, _ring) in enumerate(node.members):
        out[pid] = base + i
    for k in node.kids:
        _assign(k, x0 + k.rel, out)


# ================================================================== building ==
def build_subject_grid(graph, s: LayoutSettings) -> Grid:
    subj = s.subject_id
    g = Grid()
    if not subj or subj not in graph.people:
        g.warnings.append("Choose whose chart this is first.")
        return g

    scope = _scope(graph, s, subj)
    ring_of = _rings_from_subject(graph, scope, subj)
    _settle_sibling_rings(graph, scope, ring_of)

    used: set[str] = set()
    partner_of: dict[str, str] = {}
    placed_ring: dict[str, int] = {}
    # Birth order, with the id as a tiebreak. The tiebreak is not cosmetic:
    # two siblings with the same year -- or with no year at all, which is
    # most of a half-researched tree -- would otherwise be ordered by
    # whatever `set` iteration handed over, and that differs in every
    # process. The chart came out subtly different on every run.
    def born(p: str) -> tuple[float, str]:
        return (graph.people[p].birth.sort_value or 9e9, p)

    def kids_of(pid: str) -> list[str]:
        """Children, deduplicated but kept in a stable order."""
        return sorted(dict.fromkeys(graph.children(pid)), key=born)

    def ring(pid: str, fallback: int) -> int:
        """The ring this person sits on.

        Prefer the walk out from the subject. Someone with no path to the
        subject at all -- a whole unconnected family, which `--focus all`
        is full of -- falls back to their position in their own block.

        Record it: the contour separates blocks by the ring used HERE, so
        anything that later disagrees about which ring a person is on puts
        two people at one angle. That is what it did.
        """
        r = ring_of.get(pid, fallback)
        placed_ring[pid] = r
        return r

    def married_in(pid: str) -> bool:
        """True if this person joined the family rather than being born into
        it. Someone with parents on the chart belongs in their own sibling
        group; claiming them as a spouse instead drags them across the disc
        and stretches their brothers' and sisters' arc over everyone in
        between. That is what produced a 193 degree sibling arc."""
        return not any(x in scope for x in graph.parents(pid, primary_only=False))

    def take_spouses(pid: str) -> list[str]:
        """Partners who married in: they get a person-sized slot beside their
        partner, never a share of their partner's lineage."""
        out = []
        for x in graph.partners(pid):
            if x in scope and x not in used and married_in(x):
                used.add(x)
                partner_of[x] = pid
                out.append(x)
        return out

    def siblings_of(pid: str) -> list[str]:
        """Brothers and sisters through either parent, so half-siblings are
        siblings here rather than a special case."""
        out, seen = [], set()
        for par in graph.parents(pid, primary_only=False):
            for c in graph.children(par):
                if c != pid and c in scope and c not in used and c not in seen:
                    seen.add(c)
                    out.append(c)
        return sorted(out, key=born)

    def descend(pid: str, fallback: int,
                spouse_first: bool = False) -> Optional[_Node]:
        """Someone off the direct line, their partners, and everyone below.

        `spouse_first` puts the married-in partner on the far side of this
        person, away from the middle of their sibling group. It costs
        nothing and it pulls the brothers and sisters a little closer
        together, so the arc over them is as tight as the family allows.
        """
        if pid in used or pid not in scope:
            return None
        used.add(pid)
        r = ring(pid, fallback)
        sps = [(sp, ring(sp, r)) for sp in take_spouses(pid)]
        run = (list(reversed(sps)) + [(pid, r)] if spouse_first
               else [(pid, r)] + sps)
        node = _Node(members=run, centre_members=True)
        node.kids = row(kids_of(pid), r - 1)
        return node

    def row(people: list[str], fallback: int) -> list[_Node]:
        """A group of brothers and sisters, left to right, each with their own
        family below them and their spouse facing outward."""
        n = len(people)
        out = []
        for i, p in enumerate(people):
            k = descend(p, fallback, spouse_first=(i * 2 < n))
            if k:
                out.append(k)
        return out

    def ancestors_of(child: str, r: int) -> Optional[_Node]:
        """The couple who are `child`'s parents, everything behind them, and
        their brothers and sisters flanking on their own side."""
        if s.max_generations is not None and r > s.max_generations:
            return None
        # The primary union only. Pooling every parent-union and taking the
        # first two can pair a father from one union with a mother from
        # another, i.e. two people who were never a couple.
        pars = [x for x in graph.parents(child, primary_only=True)
                if x in scope and x not in used][:2]
        if not pars:
            pars = [x for x in graph.parents(child, primary_only=False)
                    if x in scope and x not in used][:1]
        if not pars:
            return None
        a = pars[0]
        b = pars[1] if len(pars) > 1 else None
        used.add(a)
        if b:
            used.add(b)
            partner_of[b] = a

        a_sp = take_spouses(a)          # `b` is already taken, so never here
        b_sp = take_spouses(b) if b else []

        run = [x for x in reversed(a_sp)] + [a]
        if b:
            run += [b] + b_sp
        node = _Node(members=[(x, ring(x, r)) for x in run],
                     centre_members=False)

        kids: list[_Node] = []
        up_a = ancestors_of(a, r + 1)
        if up_a:
            kids.append(up_a)
        # `a` closes the run, so their brothers and sisters butt up against
        # them and the arc over that union covers nobody standing outside it.
        kids += row(siblings_of(a), r)
        node.mem_index = len(kids)
        if b:
            kids += row(siblings_of(b), r)
            up_b = ancestors_of(b, r + 1)
            if up_b:
                kids.append(up_b)
        node.kids = kids
        return node

    # ---- the subject's own block: parents inward, siblings and children out
    used.add(subj)
    root = _Node(members=[(subj, ring(subj, 0))], centre_members=False)
    for sp in take_spouses(subj):
        root.members.append((sp, ring(sp, 0)))
    kids: list[_Node] = []
    up = ancestors_of(subj, 1)
    if up:
        kids.append(up)
    kids += row(siblings_of(subj), 0)
    root.mem_index = len(kids)
    kids += row(kids_of(subj), -1)
    root.kids = kids

    # ---- anyone in scope the walk did not reach gets their own block, laid
    #      out by the same pass. There is no second allocator: the old
    #      "attach beside the nearest relative" fallback is what put two
    #      people on one angle.
    blocks = [root]
    for pid in sorted(scope, key=lambda p: (-ring_of.get(p, 0), born(p))):
        if pid in used:
            continue
        top = pid
        for _ in range(40):                     # climb to the head of the line
            nxt = next((x for x in graph.parents(top, primary_only=False)
                        if x in scope and x not in used and x != top), None)
            if not nxt:
                break
            top = nxt
        blk = descend(top, ring_of.get(top, 0))
        if blk:
            blocks.append(blk)

    forest = _Node(members=[], kids=blocks, centre_members=True)
    _tidy(forest)
    xs: dict[str, float] = {}
    _assign(forest, 0.0, xs)

    # ---- units -> the 0..1 spread axis -----------------------------------
    if not xs:
        g.warnings.append("Nobody could be placed on this chart.")
        return g
    lo = min(xs.values())
    raw = max(xs.values()) + 1.0 - lo
    width = max(raw + SEAM, MIN_SLOTS)
    pad = (width - raw) / 2          # centre a chart too sparse to fill the disc
    for pid, x in sorted(xs.items(), key=lambda kv: kv[1]):
        r = placed_ring.get(pid, ring_of.get(pid, 0))
        p = graph.people[pid]
        t0 = (x - lo + pad) / width
        g.slots[pid] = Slot(pid=pid, gen=r, t0=t0, t1=t0 + 1.0 / width,
                            order=len(g.order), lineage=subj,
                            parent=None, partner_of=partner_of.get(pid),
                            year=p.birth.sort_value,
                            death_year=p.death.sort_value)
        g.order.append(pid)

    for pid, sl in g.slots.items():
        sl.parent = next((x for x in graph.parents(pid, primary_only=True)
                          if x in g.slots), None)
        if sl.parent is None:
            sl.parent = next((x for x in graph.parents(pid, primary_only=False)
                              if x in g.slots), None)

    # rings are numbered from the earliest generation outward, so the oldest
    # ancestors sit innermost and the youngest people at the rim
    top = max((sl.gen for sl in g.slots.values()), default=0)
    for sl in g.slots.values():
        sl.gen = top - sl.gen
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


def _rings_from_subject(graph, scope: set[str], subj: str) -> dict[str, int]:
    """Ring relative to the subject: parent +1, child -1, spouse and sibling 0.

    Breadth-first, so everyone lands on the ring their SHORTEST relationship
    to the subject implies. Depth below some apex ancestor is the wrong
    measure and is what put a married couple two rings apart.
    """
    out = {subj: 0}
    frontier = [subj]
    while frontier:
        nxt = []
        for x in frontier:
            for p in graph.parents(x, primary_only=False):
                if p in scope and p not in out:
                    out[p] = out[x] + 1
                    nxt.append(p)
            for c in graph.children(x):
                if c in scope and c not in out:
                    out[c] = out[x] - 1
                    nxt.append(c)
            for y in graph.partners(x) + graph.siblings(x):
                if y in scope and y not in out:
                    out[y] = out[x]
                    nxt.append(y)
        frontier = nxt
    return out


def _settle_sibling_rings(graph, scope: set[str], ring_of: dict[str, int]) -> None:
    """Brothers and sisters share a ring.

    The walk out from the subject measures each person by their shortest
    relationship to them, and where the tree folds back on itself -- cousins
    marrying, a line documented twice -- two children of one union can be
    reached by paths of different length. One of them then sits a ring out
    from the rest of their family, which is wrong on its face and leaves
    their sibling arc spanning two rings, where "contiguous" means nothing.

    Rare: none in the shipped sample, one group in a few hundred elsewhere.
    Cheap enough to settle anyway. Only primary children are moved; an
    adopted child is laid out with the family that raised them.
    """
    for _ in range(4):
        moved = False
        for uid, u in graph.unions.items():
            kids = [c for c in u.children if c in scope and c in ring_of
                    and graph.people[c].child_of == uid]
            if len(kids) < 2:
                continue
            rings = [ring_of[c] for c in kids]
            if len(set(rings)) == 1:
                continue
            # the ring most of them already agree on; ties go inward
            best = min(set(rings), key=lambda r: (-rings.count(r), r))
            for c in kids:
                if ring_of[c] != best:
                    ring_of[c] = best
                    moved = True
        if not moved:
            return


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
