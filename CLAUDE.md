# Helix — instructions for Claude Code

A genealogy program that renders family trees as laser-cuttable charts.
Python 3.11+, **zero required dependencies**, 295 tests.

## Read this before anything else

**The layout is a couple-cell descent tree.** `helix/layout/couple_grid.py`
gives each COUPLE one angular cell and stacks the partners radially inside
the ring band. That is what lets the chart say, without a legend, who is
married to whom, which children are whose, and who is a cousin of whom.
`docs/KNOWN_ISSUE_LAYOUT.md` has the reasoning and the measurements.

Measure before and after any change there:

```bash
python3 tools/diagnose_layout.py <file> --cells      # all four must be zero
```

`helix/layout/subject_grid.py` is the older one-slot-per-person layout,
still used by the other radial designs. Its own three limits are recorded in
the same document; they are the reason the couple grid exists.

**Blockers 1 and 2 are done.** The record system (`helix/store/records.py`
is the only thing that writes, and it is what makes Ctrl-Z work), and laser
output: `--production` converts every name to single-stroke geometry with the
built-in face in `helix/fab/strokefont.py`, reports islands, and runs a
pre-flight that passes. **Next up is Blocker 3 in `BLOCKERS.md`** — GEDCOM,
writer first.

## Do this first, before anything else

```bash
python3 bootstrap.py
```

No arguments, installs nothing, no network. Takes ~7 seconds and must print
**Ready**. It builds a sample family, renders every design to SVG and PDF,
and runs the tests. If it does not print Ready, stop and report why.

Then read, in this order:

1. **`docs/KNOWN_ISSUE_LAYOUT.md`** — the layout defect, with measurements
   and the algorithm that should replace the current allocation. **Highest
   priority.**
2. **`BLOCKERS.md`** — the three things that must be built, in order, each
   with runnable acceptance criteria.
3. **`docs/DATA_ENTRY_UI.md`** — full spec for Blocker 1. Screens, endpoints,
   payloads, a ten-step acceptance sequence.
4. **`docs/ARCHITECTURE.md`** — how the pieces fit, which way dependencies flow.
5. **`docs/OPTIONS.md`** — every style token. Check here before adding an
   option; it is probably already specified.

`PROMPTS.md` holds the prompts the user will give you, in order.

## Verify constantly

```bash
python3 -m pytest tests -q      # 295 tests, must stay green
python3 bootstrap.py            # must still print Ready
```

**If a test fails, read it before changing it.** Several encode bugs found the
hard way and each names the failure it prevents.

## The eight rules that must not be broken

1. **`RenderPlan` is the only bridge between layout and output.** Layout
   engines compute geometry; renderers serialise it. If an exporter starts
   doing trigonometry, the architecture has failed.
2. **`GenDate` is an interval, never a `date`.** Ages are `AgeRange`, never
   `int`. Compare intervals, not midpoints — see `graph/validate.py`.
3. **Children attach to a UNION, never to a parent.** This is what makes
   half-siblings, remarriage and adoption work instead of being special cases.
4. **Facts are events with roles and citations.** There is no `birth_date`
   column on `person`.
5. **Never destroy what the user typed.** Unparseable dates are stored with
   `kind='unknown'` and the original string intact.
6. **Never `eval()` a style rule.** `style/tokens.py` uses a whitelisted AST
   walk; style files get shared between people.
7. **Never SQL-DELETE a person.** Mark inactive; `store/records.retire()`
   is how. Undo of a person's creation does the same rather than deleting.
8. **Every error message says what to do next.** No stack traces reach the
   user. `fab/preflight.py` is the standard.

## Traps already hit — do not re-introduce them

- **The server threads every request.** A SQLite connection made on the main
  thread cannot be used from a request thread. It is opened with
  `check_same_thread=False` and all access goes through `ST.lock`. **Test new
  endpoints against a running server**, not as function calls — that is how
  this one hid.
- **Arcs must take the short way round.** Use `geometry.short_arc` for any tie
  between two people. `arc_path` follows `t1 - t0`, so a couple either side of
  the start angle got their marriage drawn right across the disc.
- **Emit absolute SVG path commands.** `pathflatten` handles relative now, but
  a relative circle once flattened into garbage geometry hundreds of
  millimetres off the sheet — in the CAD exports only, because browsers read
  it correctly.
- **A married-in spouse gets a person-sized slot**, not half their partner's
  lineage. That put couples 160° apart.
- **`_auto_apexes` must exclude people who married in.** "Everyone with no
  known parents" includes every spouse, which gave 130 root sectors and an
  unreadable chart.

## Adding a design

```python
@register("my_design", "My Design", "radial", "One plain sentence.",
          good_for="When to choose it.", laser="good")
def my_design(graph, settings, style) -> RenderPlan:
    g = build_grid(graph, settings)      # gen, spread 0..1, lineage, years
    plan = RenderPlan(canvas=Canvas(600, 600))
    for slot in g:
        plan.add(Element(kind="path", layer="ENGRAVE", d=...,
                         person_id=slot.pid, role="cell"))
    return plan
```

That is the whole contract. `build_grid` has already done scoping, ordering,
weighting, married-in placement and missing-year inference. Use
`common.place_radial_label` or `common.place_label` so collision handling
comes free. `tests/test_layout.py` will pick the design up automatically.

## Do not

- Add a dependency without asking. SVG, PDF, DXF and EPS are all written by
  hand so the program works on a machine with nothing installed.
- Add a Save button, an autosave timer, or a document-dirty flag. Every write
  commits immediately; there is no unsaved state. See
  `docs/KEEPING_YOUR_WORK.md`.
- Let the word "union" appear in the user interface. It is right for the
  schema and wrong for someone adding their aunt.
- Describe command output instead of showing it.
- **Trust a structural check to tell you a chart looks right.** It cannot.
  Render it, open it, and trace a family by eye. Every layout bug in this
  program survived a passing test suite.

## Layout of the repository

```
helix/model/     dates that can be vague. Everything depends on this
helix/store/     schema, connection, backup, archive, restore
helix/graph/     the family as a graph; the Thread; validation
helix/layout/    19 designs sharing one abstract grid
helix/render/    svg, pdf, dxf, eps — all hand-written
helix/fab/       materials, preflight, kerf, islands, clock
helix/web/       the interface. No build step, no npm
tools/           sample generator, .ftz importer
docs/            specifications. Read before writing
```

The flagship design is `radial_family` (Family Rings), and it is the
default. One cell per couple, one ring per generation, founders at the
centre. If you have to choose where to spend care, spend it there.

`radial_rings` is the older one-slot-per-person layout and still works; the
difference, and why the newer one can promise things the older one cannot,
is in `docs/KNOWN_ISSUE_LAYOUT.md`.
