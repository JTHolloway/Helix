# Helix — instructions for Claude Code

A genealogy program that renders family trees as laser-cuttable charts, and
keeps everything you know about the people on them. Python 3.11+, **zero
required dependencies**, 589 tests.

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

**All three blockers are done.** The record system (`helix/store/records.py`
is the only thing that writes, and it is what makes Ctrl-Z work), and laser
output: `--production` converts every name to single-stroke geometry with the
built-in face in `helix/fab/strokefont.py`, reports islands, and runs a
pre-flight that passes. Blocker 3 is built too: `helix/io/gedcom/` reads and writes GEDCOM (the
round trip through 463 people is exact) and `helix/io/csv_import.py` takes a
relative's spreadsheet. `BLOCKERS.md` lists what is left, none of it
blocking.

**The root person is the whole document.** Every relation is measured from
one person, so changing the root is not a preference — it is a different
document about the same family. `desktop/library.copy_for` is that idea made
into a feature: a copy of the file with somebody else at the centre, offering
by name to leave out the branches that are no relation to them. Nothing
reaches back into the original. It is also why nobody is told to research an
in-law's parents: move the root and the same question appears on its own.

**It is also an ancestry program now, not only a chart generator.**
`helix/graph/kinship.py` is the keystone: it turns "how are we related" into
structure — steps up, steps down, cousin degree, removal, a stable group key
— and seven features read it rather than each deciding for themselves what a
cousin is. The relatives sidebar, narrowing a chart by relation, the profile
panel with its photograph and facts, the highlighting, where a family came
from, how much DNA two people are expected to share, and what is worth
looking up next (`helix/analysis/gaps.py`). Read **`docs/ANCESTRY.md`**
before touching any of it.

Two rules from there that reach into the layout:

* **Narrowing happens BEFORE the grid is built**, never after. Hiding a
  branch afterwards leaves the chart arranged around a family that is no
  longer on it. Removed from the cast list instead, the ordering search runs
  again on what is left.
* **A narrowed chart says what it left off.** You cannot tell a family of two
  from a family of nine you narrowed down, so every marriage that lost
  children carries a pruned-branch mark with the number.

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
5. **`docs/ANCESTRY.md`** — the kinship model, narrowing, profiles,
   photographs and printing. The half of the program that keeps a family
   rather than drawing one.
6. **`docs/OPTIONS.md`** — every style token. Check here before adding an
   option; it is probably already specified.
7. **`docs/DESKTOP.md`** — Helix as an application you double-click, and
   where a person's family files live on their own computer.
8. **`docs/DECISIONS.md`** — why the program is the way it is: the faults
   found, the measurements taken, the things tried that did not work. It
   lives there so the code can be read for what it does.

`PROMPTS.md` holds the prompts the user will give you, in order.

## Verify constantly

```bash
python3 -m pytest tests -q      # 589 tests, must stay green
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
9. **One module decides what a cousin is.** `graph/kinship.py`. The sidebar,
   the filter, the profile and the highlighting all read it. Written out
   twice they drift, and somebody appears under "first cousins" and vanishes
   when you allow first cousins.
10. **An absent field is not an empty one.** A request that never mentions a
    key means "leave this alone"; an empty string means "clear it". Read the
    same way, saving a birthplace wiped the birth date beside it.

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
- **A highlight rule must not set `fill` on linework.** The chart's paths are
  drawn with `fill:none` and mean it; one rule setting both stroke and fill
  turned the whole disc into a solid red shape.
- **Nothing in the browser is compiled until it runs.** A syntax error in one
  front-end module takes the WHOLE interface down — every module, because one
  that fails to parse stops the import graph — and sails through a green test
  run. `tests/test_web.py` parses every module with node. Keep it passing.
- **A design says for itself whether it is built.** Six of the twenty are
  specified and not implemented; `DesignInfo.built` is what keeps them out of
  the gallery instead of letting somebody click one into an error.
- **The window opens on `radial_family`.** It opened on `radial_rings` for a
  long time, so the flagship — the design every layout document describes,
  and the only one that draws the pruned-branch marks — was something you had
  to go and find.

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
helix/layout/    20 designs sharing one abstract grid
helix/render/    svg, pdf, dxf, eps — all hand-written
helix/fab/       materials, preflight, kerf, islands, clock
helix/web/       the interface. No build step, no npm
helix/desktop/   the application window and where family files live
helix/io/        GEDCOM in and out; spreadsheet import
tools/           sample generator, .ftz importer
docs/            specifications. Read before writing
```

The flagship design is `radial_family` (Family Rings), and it is the
default. One cell per couple, one ring per generation, founders at the
centre. If you have to choose where to spend care, spend it there.

`radial_rings` is the older one-slot-per-person layout and still works; the
difference, and why the newer one can promise things the older one cannot,
is in `docs/KNOWN_ISSUE_LAYOUT.md`.
