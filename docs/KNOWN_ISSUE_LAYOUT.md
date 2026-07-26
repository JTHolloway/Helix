# Known issue: the radial layout is not good enough yet

**Status: unresolved. This is the most valuable thing left to fix, ahead of
the blockers.** It was iterated on several times and improved substantially
each time without ever becoming right. Do not assume the remaining problems
are small.

## What the owner sees

> "Many people lie on the same line when they shouldn't. The spouses seem
> cluttered and hard to follow."

Both complaints are correct and both are measurable.

## Measure it first

```bash
python3 tools/diagnose_layout.py my-family.helix
```

On the owner's real 142-person tree, with the layout as it currently stands:

| Check | Result |
|---|---|
| 1. People on the wrong ring | **0** — this part is now correct |
| 2. Sibling arcs sweeping past non-siblings | **77** |
| 3. Couples far apart | 0 (median 5°) |
| 4. People on top of each other | **10 pairs, minimum gap 0.00°** |

**Checks 2 and 4 are the bug.** All four must read zero.

## What is actually wrong

### Sibling arcs sweep across strangers

An arc is drawn from the first to the last child of a union. Nothing
guarantees those children are **contiguous** on their ring, so the arc runs
straight over whoever else happens to sit between them. Worst case on the
real data: a 107° arc covering eight unrelated people, including
Peter Holloway and Richard Holloway, who then appear to be siblings of the
four children it actually belongs to.

This is exactly the reported symptom. It is not a rendering bug — the arc is
drawn correctly between the endpoints it was given. The **allocation** is
wrong: sibling groups are not kept together.

### People land on identical angles

Minimum neighbour gap of 0.00° means two people occupy the same point.
Angular space is currently handed out in four different places —
`ascend`, `descend`, the sibling flanking loop, and the fallback attach pass —
each with its own heuristic and none aware of the others. They overlap.

## The fix

**Replace the ad-hoc allocation in `helix/layout/subject_grid.py` with a
single-pass tidy-tree algorithm.** The current code grew by patching one
symptom at a time and has reached the end of that approach.

Use **Reingold–Tilford**, or Walker's O(n) refinement of it, adapted to
polar coordinates:

1. Build one layout tree. Each node is a **couple** (already the right unit —
   keep that). A node's children are the couples formed by its children.
2. **First pass, bottom-up:** give every leaf a slot of one unit. Give every
   internal node the union of its children's extents, centred over them.
   Where two subtrees would overlap, push the right-hand one clear and
   record the shift — this is the part the current code has no equivalent of,
   and it is why things collide.
3. **Second pass, top-down:** accumulate the shifts into final positions.
4. Map to angle at the end. Nothing before this step should know about
   radians.

Guarantees that follow, which the present code cannot make:

- Every sibling group is **contiguous**, so an arc over it covers nobody else.
- No two people share an angle.
- Subtrees never overlap, so a family stays in one piece.

### Then

- Draw the sibling arc only over its own group. With contiguity guaranteed
  this is automatic, but assert it.
- Give spouses their own visual treatment. They currently take a narrow slice
  on their partner's ring, which is why they read as clutter. Consider a
  small radial offset so a couple reads as a pair rather than as two more
  names in the row.
- Consider dropping the fallback attach pass entirely. If the tidy tree
  covers every person in scope, nothing needs attaching afterwards, and that
  pass is the source of most of the collisions.

## Acceptance

```bash
python3 tools/diagnose_layout.py my-family.helix          # all four zero
python3 tools/diagnose_layout.py my-family.helix --focus all
python3 -m pytest tests -q                                # stays green
```

Then render `--design radial_rings --style panel1m --panel 1000x1000` and
**look at it**. Trace one family by eye from a grandparent down to a
grandchild. If that is not effortless, it is not fixed.

## A note on how this got missed

Every version of this was verified structurally — element counts, angular
separations, coordinates against canvas bounds — and never once looked at,
because the image viewer was unavailable throughout the session that built
it. Structural checks caught real bugs, several of them, but they cannot
tell you that a chart is hard to read. **Render it and look at it.**
