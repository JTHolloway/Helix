#!/usr/bin/env python3
"""Measure what is wrong with a radial layout, rather than guessing.

    python tools/diagnose_layout.py my-family.helix

Reports the four things that make a ring chart unreadable:

  1. people on the wrong ring for their generation
  2. sibling arcs that sweep past people who are not siblings
  3. couples drawn far apart
  4. people placed on top of each other

Run it before and after any layout change. Numbers going down is the only
evidence that a change helped.
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from helix.graph import build                      # noqa: E402
from helix.layout.base import LayoutSettings, build_grid   # noqa: E402
from helix.store.db import connect                 # noqa: E402


def true_generations(g, subject):
    """Generation relative to the subject: parent +1, child -1, spouse and
    sibling 0. This is the answer the layout must agree with."""
    out = {subject: 0}
    frontier = [subject]
    for _ in range(20):
        nxt = []
        for x in frontier:
            for p in g.parents(x, primary_only=False):
                if p not in out:
                    out[p] = out[x] + 1; nxt.append(p)
            for c in g.children(x):
                if c not in out:
                    out[c] = out[x] - 1; nxt.append(c)
            for s in g.partners(x) + g.siblings(x):
                if s not in out:
                    out[s] = out[x]; nxt.append(s)
        frontier = nxt
    return out


def cells_report(g, grid, name, args) -> None:
    """The four things that matter when a couple owns one cell.

    Different questions from the one-slot layout, because the layout makes
    different promises. "Which ring is this person on relative to you" stops
    being the point once rings are depth from the founders; "is every
    parent-to-child link exactly one ring" takes its place, and it is a
    stronger thing to be able to say.
    """
    S = grid.slots
    print(f"{args.db}  subject {name[g.subject_id]}  focus {args.focus}  "
          f"[couple cells]")
    cells = {}
    for sl in S.values():
        cells.setdefault(sl.cell or sl.pid, []).append(sl)
    print(f"{len(S)} people in {len(cells)} cells on {grid.max_gen + 1} rings\n")

    # 1 ---------------------------------------------------- generation steps
    bad = [(name[p], S[p].gen, name[sl.parent], S[sl.parent].gen)
           for p, sl in S.items()
           if sl.row == 0 and sl.parent in S
           and S[sl.parent].gen != sl.gen - 1]
    print(f"1. CHILD NOT ONE RING OUT   {len(bad)}")
    for b in bad[:5]:
        print(f"     {b[0]} on ring {b[1]}, parent {b[2]} on ring {b[3]}")

    # 2 ------------------------------------------------------- sibling arcs
    strangers = 0
    worst = []
    for uid, u in g.unions.items():
        kids = [c for c in u.children if c in S and g.people[c].child_of == uid]
        if len(kids) < 2:
            continue
        ks = set(kids)
        # Per contiguous RUN, because that is what the chart draws: a couple
        # whose children are not side by side gets one arc per run, never one
        # arc across the gap. Measuring the whole span counted strangers as
        # swept who have no arc over them at all.
        ring = sorted((S[p].tc, p) for p in grid.by_gen.get(S[kids[0]].gen, [])
                      if S[p].row == 0)
        runs, cur = [], []
        for tc, pid in ring:
            if pid in ks:
                cur.append(tc)
            elif cur:
                runs.append(cur)
                cur = []
        if cur:
            runs.append(cur)
        if not runs:
            runs = [sorted(S[c].tc for c in kids)]
        odd = [p for p in grid.by_gen.get(S[kids[0]].gen, [])
               if p not in ks and S[p].row == 0
               and any(r[0] <= S[p].tc <= r[-1] for r in runs)]
        strangers += len(odd)
        if odd:
            worst.append((max(r[-1] - r[0] for r in runs) * 360,
                          [name[c] for c in kids[:3]],
                          [name[o] for o in odd[:4]]))
    worst.sort(reverse=True)
    print(f"\n2. ARC SWEEPS PAST OTHERS   {strangers}   "
          f"(anyone at all under a sibling arc who is not one of them)")
    for span, kids, odd in worst[:4]:
        print(f"     {span:5.0f}deg arc  siblings {kids}  swept {odd}")

    # 3 ----------------------------------------------------------- marriages
    split = []
    for u in g.unions.values():
        ps = [x for x in u.partners if x in S]
        if len(ps) == 2 and S[ps[0]].cell != S[ps[1]].cell:
            split.append((abs(S[ps[0]].tc - S[ps[1]].tc) * 360,
                          [name[x] for x in ps]))
    split.sort(reverse=True)
    total = sum(1 for u in g.unions.values()
                if len([x for x in u.partners if x in S]) == 2)
    print(f"\n3. COUPLES NOT IN ONE CELL  {len(split)}   of {total} marriages "
          f"drawn  (the rest need no line at all)")
    for d, ps in split[:4]:
        print(f"     {d:5.0f}deg apart, drawn as a chord: {ps}")

    # 4 ---------------------------------------------------------- collisions
    coll = 0
    for gen, ppl in grid.by_gen.items():
        seen = sorted({S[p].cell or p: S[p].tc for p in ppl}.items(),
                      key=lambda kv: kv[1])
        for (_, a), (_, b) in zip(seen, seen[1:]):
            if abs(a - b) * 360 < 0.5:
                coll += 1
    print(f"\n4. CELLS ON TOP OF EACH OTHER  {coll}   (closer than 0.5deg)")

    # 5 ------------------------------------------------- scattered children
    #
    # A couple is centred over their children, and one arc is drawn across
    # them. Both of those assume the children are SIDE BY SIDE. When they are
    # not, the arc spans whatever got in between and the stem cannot reach
    # all of it -- which is what "branches that stem from nothing" looks
    # like. This is the layout fault behind it, not the drawing.
    loose = []
    for u in g.unions.values():
        kids = [c for c in u.children if c in S and S[c].row == 0]
        if len(kids) < 2:
            continue
        gen = S[kids[0]].gen
        mine = {S[c].cell or c for c in kids}
        lo = min(S[c].tc for c in kids)
        hi = max(S[c].tc for c in kids)
        between = {S[p].cell or p for p in grid.by_gen.get(gen, [])
                   if lo < S[p].tc < hi and (S[p].cell or p) not in mine
                   and not S[p].row}
        if between:
            loose.append(((hi - lo) * 360, len(between),
                          [name[c] for c in kids[:3]]))
    loose.sort(reverse=True)
    print(f"\n5. CHILDREN NOT SIDE BY SIDE  {len(loose)}   "
          f"(somebody else's cell sits in the middle of a sibling group)")
    for d, n, ks in loose[:4]:
        print(f"     {d:5.0f}deg apart, {n} cell(s) in between: {ks}")

    # 6 ---------------------------------------------------- discontinuities
    #
    # It is one family, so every person must be reachable from every other by
    # following lines that are actually DRAWN. Anything else is a chart with
    # a piece of somebody's family floating unattached.
    adj: dict = {}

    def link(a, b):
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)

    bycell: dict = {}
    for pid in S:
        bycell.setdefault(S[pid].cell or pid, []).append(pid)
    for m in bycell.values():
        for a, b in zip(m, m[1:]):
            link(a, b)
    for u in g.unions.values():
        ps = [p for p in u.partners if p in S]
        for c in u.children:
            if c in S and ps:
                link(ps[0], c)
        for a, b in zip(ps, ps[1:]):
            link(a, b)
    seen_p, comps = set(), []
    for p in S:
        if p in seen_p:
            continue
        stack, comp = [p], set()
        while stack:
            q = stack.pop()
            if q in comp:
                continue
            comp.add(q)
            seen_p.add(q)
            stack += [x for x in adj.get(q, ()) if x not in comp]
        comps.append(comp)
    comps.sort(key=len, reverse=True)
    print(f"\n6. SEPARATE PIECES  {len(comps)}   "
          f"(should be 1 -- it is one family)")
    for c in comps[1:4]:
        print(f"     {len(c)} people adrift: "
              f"{[name[x] for x in list(c)[:4]]}")

    print("\nAll six should be ZERO -- except 6, which should be ONE.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("db")
    ap.add_argument("--focus", default="bloodline")
    ap.add_argument("--cells", action="store_true",
                    help="measure the couple-cell layout (radial_family) "
                         "instead of the one-slot-per-person one")
    args = ap.parse_args()

    g = build.load(connect(args.db, create=False, backup_daily=False))
    name = {p: g.people[p].full_name.strip() for p in g.people}
    subj = g.subject_id
    if not subj:
        raise SystemExit("No subject set on this file.")
    grid = build_grid(g, LayoutSettings(engine="radial_rings", cells=args.cells,
                                        subject_id=subj, focus=args.focus))
    if args.cells:
        return cells_report(g, grid, name, args)
    S = grid.slots
    truth = true_generations(g, subj)
    print(f"{args.db}  subject {name[subj]}  focus {args.focus}")
    print(f"{len(S)} of {len(g.people)} people placed on "
          f"{grid.max_gen + 1} rings\n")

    # 1 -------------------------------------------------------------- rings
    offs = collections.Counter(S[p].gen + truth[p] for p in S if p in truth)
    mode = offs.most_common(1)[0][0] if offs else 0
    wrong = [p for p in S if p in truth and S[p].gen + truth[p] != mode]
    print(f"1. WRONG RING              {len(wrong)}")
    for p in wrong[:8]:
        print(f"     {name[p]:<26} ring {S[p].gen}, should be {mode - truth[p]}")

    # 2 --------------------------------------------------------- arc sweeps
    #
    # Two different things used to be counted together here, and only one of
    # them is a defect.
    #
    # A STRANGER under a sibling arc is the bug this file was written to
    # catch: the arc runs over people who have nothing to do with that
    # family, and they read as siblings of it. This must be zero.
    #
    # A sibling's OWN SPOUSE under the arc is unavoidable. A married-in
    # partner sits on their partner's ring -- that is what a ring means --
    # so in any sibling group whose middle children are married, their
    # partners lie between the outermost siblings. The only way to clear
    # them out is to exile every spouse beyond the group, which separates
    # the couples. In this file's sample that would mean breaking up seven
    # marriages to tidy one arc. It is counted, and kept separate.
    #
    # Only a union's PRIMARY children are checked. A person may be a child of
    # several unions -- adopted, fostered, or parentage in doubt -- and
    # `store/schema.sql` is explicit that the layout follows the one marked
    # primary and that the others are drawn as a chord across the disc. An
    # adopted son sits with the family that raised him, so the union he was
    # born into cannot also have him contiguous, and should not be asked to.
    strangers, spouses, worst = 0, 0, []
    for uid, u in g.unions.items():
        kids = [c for c in u.children
                if c in S and g.people[c].child_of == uid]
        if len(kids) < 2:
            continue
        kidset = set(kids)
        angs = sorted(S[c].tc for c in kids)
        intr = [p for p in grid.by_gen.get(S[kids[0]].gen, [])
                if p not in kidset and angs[0] <= S[p].tc <= angs[-1]]
        odd = [p for p in intr if not any(x in kidset for x in g.partners(p))]
        strangers += len(odd)
        spouses += len(intr) - len(odd)
        if odd:
            worst.append(((angs[-1] - angs[0]) * 360, len(odd),
                          [name[c] for c in kids[:3]],
                          [name[i] for i in odd[:4]]))
    worst.sort(reverse=True)
    print(f"\n2. ARC SWEEPS PAST OTHERS  {strangers}   "
          f"(a sibling arc covering people unrelated to that family)")
    for span, n, kids, intr in worst[:5]:
        print(f"     {span:5.0f}deg arc over {n} outsiders")
        print(f"       siblings   {kids}")
        print(f"       swept past {intr}")
    print(f"   ({spouses} of the people under an arc are a sibling's own "
          f"husband or wife.\n    Not a defect -- see the note in this file. "
          f"Not counted above.)")

    # 3 ------------------------------------------------------------ couples
    far = []
    for u in g.unions.values():
        ps = [x for x in u.partners if x in S]
        if len(ps) == 2:
            far.append((abs(S[ps[0]].tc - S[ps[1]].tc) * 360,
                        [name[x] for x in ps]))
    far.sort(reverse=True)
    over = [x for x in far if x[0] > 20]
    med = sorted(x[0] for x in far)[len(far) // 2] if far else 0
    print(f"\n3. COUPLES FAR APART       {len(over)}   "
          f"(median separation {med:.0f}deg)")
    for d, ps in far[:4]:
        print(f"     {d:5.0f}deg  {ps}")

    # 4 --------------------------------------------------------- collisions
    coll = 0
    for gen, ppl in grid.by_gen.items():
        order = sorted(ppl, key=lambda p: S[p].tc)
        for a, b in zip(order, order[1:]):
            if abs(S[a].tc - S[b].tc) * 360 < 0.5:
                coll += 1
    print(f"\n4. PEOPLE ON TOP OF EACH OTHER  {coll}   (closer than 0.5deg)")
    print("\nAll four should be ZERO on a chart that reads properly.")


if __name__ == "__main__":
    main()
