# Build instructions

For the agent or developer completing this program. Read this file first.

## The honest status of this package

Roughly 60% is finished, tested, working code. The rest is stubs that raise
`NotImplementedError` with the full algorithm written in the docstring. That
is deliberate: the hard architectural decisions are made and proven, and the
remaining work is legible and self-contained.

### Finished and working

| Module | Status |
|---|---|
| `model/gendate.py` | Complete. Parses 15 date formats, never raises. |
| `store/schema.sql`, `store/db.py` | Complete. |
| `graph/build.py`, `thread.py`, `validate.py` | Complete. |
| `layout/plan.py`, `geometry.py`, `scales.py`, `base.py`, `common.py`, `registry.py` | Complete. |
| `layout/engines/radial.py` | 5 designs, all rendering. |
| `layout/engines/linear.py` | 6 designs, all rendering. |
| `render/svg.py`, `render/pathflatten.py` | Complete. |
| `style/tokens.py` + 12 presets | Complete. |
| `cli.py`, `server.py` | Complete. |
| `store/archive.py` | Complete. Backup, verify, portable archive. |
| `web/` | Complete and usable. |
| `tools/make_sample.py` | Complete. |

### Stubs, in build order

1. **Phase 3 — Getting data in.** `io/gedcom/*`, `io/csv_import.py`.
   Nothing else matters if people cannot import their existing tree. The
   `guess_mapping` function in `csv_import.py` already works.
2. **Phase 4 — Making it cuttable.** `fab/islands.py`, `fab/kerf.py`.
   Both need `shapely`/`pyclipper`. Algorithms are fully written in the
   docstrings.
3. **Phase 5 — Text as geometry.** `fab/textpath.py`, `render/pdf.py`.
   Until this is done, production SVG still works if the user converts text
   to paths in their laser software.
4. **Phase 6 — The clock.** `fab/clock.py`. Dimensions are already correct.
5. **Phase 7 — Analysis.** `analysis/gaps.py`, `stats.by_decade`, `geo.py`.
6. **Phase 8 — DNA.** `analysis/dna.py`.
7. **Phase 9-10 — More designs.** `layout/engines/experimental.py` holds
   eight registered-but-unbuilt designs. Each is one file, ~120 lines.

## Density is the main quality risk

The commonest way this program produces something bad is not a crash — it is
a chart so full that nobody can read it. Two things guard against that and
both must be preserved:

1. **`_auto_apexes` in `layout/base.py`.** "Everyone with no known parents"
   includes every spouse who married in, which on real data is 100+ people
   and yields 100+ root sectors. The function ranks lineages by descendant
   count and marks spouses of covered people as covered. Getting this wrong
   is what made the first version unreadable.
2. **`LayoutSettings.focus`.** `thread_siblings` is the sane default for a
   wall piece: the subject's line plus their brothers and sisters, typically
   40–60 people. `all` should be opt-in.

3. **`PolarLabelPlacer` for radial text.** Axis-aligned boxes over-reject
   rotated labels catastrophically. Never test radial text with an AABB.
4. **Rings are sized to their content** (`radial_rings` reserves the longest
   name in each generation before choosing the next radius). Do not
   "optimise" this into fixed rings; obstructed text is the result.

`LabelPlacer` then reports `labels_hidden`. **Never let that number be
non-zero without telling the user** — a silently truncated chart is worse
than a warning.

## Two traps already hit, do not re-introduce them

**The server threads every request.** `ThreadingHTTPServer` hands each request
to its own thread, and a SQLite connection made on the main thread cannot be
used from them. Every database-backed endpoint failed with a thread error and
nothing caught it, because the endpoints that were tested only touched the
in-memory graph. The connection is opened with `check_same_thread=False` and
all access is serialised through `ST.lock`. Keep it that way, and **test new
endpoints against a running server**, not just as function calls.

**Arcs between two angles must take the short way round.** `arc_path` draws in
the direction implied by `t1 - t0`, so a couple sitting either side of the
start angle — one at 5°, one at 355° — got their marriage drawn the whole way
round the circle. Use `geometry.short_arc` for any tie between two people.

## Rules that must not be broken

1. **`RenderPlan` is the only interface between layout and output.** Layout
   engines compute geometry; renderers serialise it. If an exporter starts
   doing trigonometry, the architecture has failed. There is one plan format
   and four consumers of it.

2. **`GenDate` is an interval, never a `date`.** Ages are `AgeRange`, never
   an `int`. A chart that prints "aged 47" from two `abt` dates tells a lie
   that gets repeated for a hundred years.

3. **Never link a child directly to a parent.** Children attach to a *union*.
   This is what makes half-siblings, remarriage, adoption and unknown
   partners work rather than being special cases bolted on later.

4. **Facts are events, not columns.** There is no `birth_date` column on
   `person`. Everything is a typed event with roles and citations, because a
   person can have two conflicting baptism records and both must survive.

5. **Never destroy what the user typed.** Unparseable dates are stored with
   `kind='unknown'` and the original string intact.

6. **Never `eval()` a style rule.** `style/tokens.py` uses a whitelisted AST
   walk. Style files get shared between people.

7. **Back up before any destructive operation.** `store/db.backup()`.
   Genealogy data is irreplaceable.

8. **Every error message says what to do next.** No stack traces reach the
   user. See `fab/preflight.py` for the standard.

## Adding a design (the common task)

```python
from ..registry import register
from ..base import build_grid
from ..plan import Element, RenderPlan, Canvas, PlanMeta

@register("my_design", "My Design", "radial",
          "One sentence a non-technical person understands.",
          good_for="When to choose this one.", laser="good")
def my_design(graph, settings, style) -> RenderPlan:
    g = build_grid(graph, settings)     # gen, spread position, lineage, years
    plan = RenderPlan(canvas=Canvas(600, 600))
    for slot in g:
        person = graph.people[slot.pid]
        # slot.gen, slot.t0..slot.t1 (0..1), slot.year, slot.lineage
        plan.add(Element(kind="path", layer="ENGRAVE", d=...,
                         person_id=slot.pid, role="cell"))
    return plan
```

That is the whole contract. `build_grid` has already done scoping, ordering,
weighting, married-in partner placement and missing-year inference. Use
`common.place_label` for text so collision handling comes free.

## Testing

```bash
pip install -e ".[dev]"
pytest
python tools/make_sample.py /tmp/s.helix --people 400
helix gallery /tmp/s.helix -o /tmp/gal      # every design must render
```

Golden-file SVG snapshots live in `tests/golden/`. Regenerate deliberately,
never casually — a diff there means the geometry changed.
