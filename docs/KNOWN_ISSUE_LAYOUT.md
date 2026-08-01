# The radial layout: two rewrites, and what each bought

**Status: resolved, twice.** First the ad-hoc angular allocation was replaced
with a single-pass tidy tree in `helix/layout/subject_grid.py`. Then the unit
changed from the person to the COUPLE, in `helix/layout/couple_grid.py`, and
three limits that the first rewrite had proved unavoidable stopped existing.

Read it in that order. The second rewrite only makes sense once you know
exactly what the first one could not do, and why.

## What the owner saw

> "Many people lie on the same line when they shouldn't. The spouses seem
> cluttered and hard to follow."

Both complaints were correct and both were measurable.

## Measure it

```bash
python3 tools/diagnose_layout.py my-family.helix
```

On the shipped 461-person sample, at `--focus bloodline`:

| Check | Was | Now |
|---|---|---|
| 1. People on the wrong ring | 0 | **0** |
| 2. Sibling arcs sweeping past strangers | 60 | **0** |
| 3. Couples far apart | 0 | **0** |
| 4. People on top of each other | 28 | **0** |

`--focus all` was worse and improved further: 508 stranger-sweeps and 176
collisions, both now zero.

## What was wrong

Angle was handed out in four places — `ascend`, `descend`, the sibling
flanking loop and the fallback attach pass — each with its own heuristic and
none aware of the others. Nothing kept a sibling group contiguous, so an arc
drawn from the first to the last child ran straight over whoever happened to
sit between them. Nothing stopped two allocators handing out the same angle,
so people landed on top of each other.

It was not a rendering bug. Each arc was drawn correctly between the
endpoints it was given; the endpoints were wrong.

## What replaced it

One tree, laid out once. A node is a couple, and it owns a run of adjacent
slots with its child blocks arranged around them:

```
[ his parents ][ his siblings ][ HIM | HER ][ her siblings ][ her parents ]
```

Sibling blocks are separated by a contour merge — push the right-hand block
clear of everything to its left, at every ring they share. That is the step
the old code had no equivalent of, and it is where the guarantees come from.

Two adaptations from textbook Reingold–Tilford, both explained in the module
docstring: contours are indexed by **ring** rather than tree depth, and a
node is **not centred over its children**, because the couple occupies its
own ring and is one more item in the sequence rather than a mark above it.

## Then the design changed, and the three limits went away

Everything above is still true of `subject_grid.py`, which the other radial
designs use. But the three limits below were all the same limit wearing
three hats: **every relationship was being expressed as angular adjacency,
and a slot has only two sides.** A person on the direct line needs to touch
their parent, their brothers and sisters, and their child. Two sides, three
neighbours. Something had to give, and which one gave was the only choice
available.

`couple_grid.py` gives the disc a second dimension to work in. A COUPLE owns
one angular cell, and the two partners are stacked **radially** inside the
ring band:

```
    ┌──────────────────────────┐
    │  Samuel Marlow    1791–  │   row 0 — born into this family
    │  ────                    │   the rule that means "married"
    │  Clara Salter     1786–  │   row 1 — married in
    └──────────────────────────┘
                │                  one stem, to their children
```

Three consequences, which are exactly the three limits, undone:

1. **Marriage needs no line at all.** Not a tie, not a bracket, not a chord.
   The cell is the marriage. 40 of the 40 marriages on the sample are drawn
   this way and nothing is drawn between them.
2. **The row an arc runs along holds only blood siblings**, because spouses
   are on the row below. So the arc covers its own group and *nobody* --
   which the angular layout could not promise, because a married-in partner
   sits on their partner's ring by definition.
3. **Parent and child are radial neighbours**, so they stop competing with
   siblings for the two angular sides. The cell is centred over its children
   in the ordinary tidy-tree way and every parent-to-child link is exactly
   one ring long. The Thread runs out along a radius and can be traced with
   a finger.

Measured on the same 461-person sample, at `--focus bloodline`:

| | one slot per person | one cell per couple |
|---|---|---|
| Child not exactly one ring out | — | **0** |
| Anyone at all under a sibling arc | 22 (irreducible) | **0** |
| Couples not drawn as one thing | 0, via 40 tie lines | **0**, via no lines |
| Two cells at the same angle | 0 | **0** |

```bash
python3 tools/diagnose_layout.py my-family.helix --cells
```

The one thing that survives is cousin marriage: when both partners were born
into the tree only one can hold the cell, and the other keeps their place in
their own family. 2 of 230 on the sample, at `--focus all` only. They are
drawn as a chord, which is in the key.

## What the OLDER layout still cannot do

**1. A sibling's own husband or wife sits under the arc.** A married-in
spouse is on their partner's ring — that is what a ring means. So in a
sibling group whose middle children are married, their partners lie between
the outermost siblings. The only way to clear them out is to exile every
spouse beyond the group, which separates the couples. On the sample that
would mean breaking up seven marriages to tidy one arc. The diagnostic
counts these separately and they are **not** the defect; a stranger under an
arc is, and that must stay at zero.

**2. The Thread sweeps.** Ordinary parent-to-child links are tight — the
median across the whole chart is about 6°. The subject's own direct line is
not: it can span 120° or more. A person on the line must touch their parent,
their siblings and their child, and a slot has two sides. Ordering the couple
first so the line runs radially pushes every ancestor's sibling arc across
the entire outward tree, which is the defect this rewrite removed. Tight
sibling arcs win; do not trade them back for a neater highlight.

**3. Cousin marriage separates a couple.** When both partners were born into
the chart, neither married in, so each belongs in their own family's block.
2 couples out of 230 on the sample, only at `--focus all`. Merging those
blocks is the non-planar case the README already rules out — they are meant
to be drawn as a chord.

## Acceptance

```bash
python3 tools/diagnose_layout.py my-family.helix              # all four zero
python3 tools/diagnose_layout.py my-family.helix --focus all  # all four zero
python3 -m pytest tests -q                                    # stays green
```

And for the couple-cell layout, which is the default:

```bash
python3 tools/diagnose_layout.py my-family.helix --cells
python3 tools/diagnose_layout.py my-family.helix --cells --focus all
```

Then render `--design radial_family --style panel1m --panel 1000x1000` and
**look at it**. Trace one family from a grandparent down to a grandchild,
then follow the red Thread from a founder out to yourself. If either is not
effortless, it is not fixed.

## A note on how this got missed the first time

Every version was verified structurally — element counts, angular
separations, coordinates against canvas bounds — and never once looked at,
because the image viewer was unavailable throughout the session that built
it. Structural checks caught real bugs, several of them, but they cannot
tell you that a chart is hard to read. **Render it and look at it.**
