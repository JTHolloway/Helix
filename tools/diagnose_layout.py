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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("db")
    ap.add_argument("--focus", default="bloodline")
    args = ap.parse_args()

    g = build.load(connect(args.db, create=False, backup_daily=False))
    name = {p: g.people[p].full_name.strip() for p in g.people}
    subj = g.subject_id
    if not subj:
        raise SystemExit("No subject set on this file.")
    grid = build_grid(g, LayoutSettings(engine="radial_rings",
                                        subject_id=subj, focus=args.focus))
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
    sweeps, worst = 0, []
    for uid, u in g.unions.items():
        kids = [c for c in u.children if c in S]
        if len(kids) < 2:
            continue
        angs = sorted(S[c].tc for c in kids)
        intr = [p for p in grid.by_gen.get(S[kids[0]].gen, [])
                if p not in kids and angs[0] <= S[p].tc <= angs[-1]]
        sweeps += len(intr)
        if intr:
            worst.append(((angs[-1] - angs[0]) * 360, len(intr),
                          [name[c] for c in kids[:3]],
                          [name[i] for i in intr[:4]]))
    worst.sort(reverse=True)
    print(f"\n2. ARC SWEEPS PAST OTHERS  {sweeps}   "
          f"(a sibling arc covering people who are not siblings)")
    for span, n, kids, intr in worst[:5]:
        print(f"     {span:5.0f}deg arc over {n} outsiders")
        print(f"       siblings   {kids}")
        print(f"       swept past {intr}")

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
