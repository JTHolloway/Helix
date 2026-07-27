# The radial layout: fixed, and what it still cannot do

**Status: resolved.** The ad-hoc angular allocation was replaced with a
single-pass tidy tree in `helix/layout/subject_grid.py`. All four diagnostic
numbers read zero, on every focus mode, and `tests/test_layout.py` now
asserts the guarantees so they cannot rot quietly.

This file is kept because the three limits at the bottom are real, were
arrived at the hard way, and each one looks like a bug until you know why it
is not.

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

## The three things it still cannot do

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

Then render `--design radial_rings --style panel1m --panel 1000x1000` and
**look at it**. Trace one family from a grandparent down to a grandchild. If
that is not effortless, it is not fixed.

## A note on how this got missed the first time

Every version was verified structurally — element counts, angular
separations, coordinates against canvas bounds — and never once looked at,
because the image viewer was unavailable throughout the session that built
it. Structural checks caught real bugs, several of them, but they cannot
tell you that a chart is hard to read. **Render it and look at it.**
