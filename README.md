# Helix

A family tree you can hang on a wall, hold in your hand, or hang a clock in.

Helix keeps a genealogy in one small file, draws it in nineteen different
visual languages — a circular maze, an underground map, a timeline of
lifespans — and exports files a laser cutter will accept without argument.

It also traces **the Thread**: the unbroken line of people you are descended
from, and answers the question that makes everyone go quiet — *if this one
person had never been born, how many of us disappear?*

---

## Start here (one command, nothing to install)

```bash
python3 bootstrap.py
```

That builds a sample 400-person family, renders every design to SVG and PDF,
runs the tests, and tells you what to do next. It takes about six seconds and
needs no arguments, no installation and no internet.

Then:

```bash
python3 -m helix.cli serve sample-family.helix     # opens your browser
```

That is a working program.

### If a chart looks cluttered

It almost certainly is: a real family is 400+ people by the fifth generation,
and 400 names will not fit legibly on a 600 mm disc. Density is a setting:

```bash
--focus bloodline         everyone you're related to by blood  ~170   ← default
--focus thread_siblings   your line plus their siblings        ~45
--focus thread            your direct line only                ~20
--focus all               every person in the file             400+
--max-generations 4       each generation roughly doubles the population
--max-people 120          hard cap; least-connected dropped first
```

Helix always reports how many names it had to leave off. If that number is
not zero, the chart is over-full. Change designs from the gallery on the left; the
picture updates as you move the controls. Nothing you do in the interface can
damage your data.

When you are ready to use your own family, either import a GEDCOM from
Ancestry / FamilySearch / MyHeritage, or start from scratch:

```bash
helix init my-family.helix --title "The Whitcombes"
helix serve my-family.helix
```

## The rest of the commands

```bash
helix designs                     # every design, with what each is good for
helix styles                      # built-in looks
helix gallery my.helix -o out     # render EVERY design, side by side, in a web page
helix render my.helix --style tubemap -o tree.svg
helix render my.helix --design radial_lifeline --diameter 700 -o clock.svg
helix check my.helix              # find impossible dates and broken links
helix stats my.helix              # who your family structurally depends on
```

## What is in this box

| Folder | What it holds |
|---|---|
| `helix/model/` | Dates that can be vague. The foundation of everything. |
| `helix/store/` | The SQLite schema and connection. Your archive. |
| `helix/graph/` | The family as a graph; the Thread; validation. |
| `helix/layout/` | Nineteen designs, sharing one abstract grid. |
| `helix/render/` | SVG, DXF, PDF. All fed by one `RenderPlan`. |
| `helix/fab/` | Materials, kerf, islands, clock fitting, pre-flight. |
| `helix/style/` | Twelve looks, stored as JSON. Styles are data, not code. |
| `helix/web/` | The interface. No build step, no npm. |
| `docs/` | How to research a family, how to record it, how to cut it. |
| `samples/` | Every design already rendered: `pdf/` for printing, `svg/` for the laser, `index.html` to compare. |

`pip install -e .` is optional — it only shortens `python3 -m helix.cli` to
`helix`.

## Read these next

- **`START_HERE.md`** — if you are an AI assistant or developer picking this
  up. One command, then the build order.
- **`BLOCKERS.md`** — the three things that must be built before this is
  usable on a real family.
- **`PROMPTS.md`** — prompts to hand a build chat, one stage at a time.
- **`BUILD_INSTRUCTIONS.md`** — exactly what is finished and what is not.
- **`docs/DESIGN_CATALOGUE.md`** — all nineteen designs and what each is for.
- **`docs/OPTIONS.md`** — every customisation option, with worked examples.
- **`docs/KEEPING_YOUR_WORK.md`** — how your research is saved, backed up and
  kept readable for decades. Read this once.
- **`docs/RESEARCH_HANDBOOK.md`** — how to actually find your ancestors,
  starting free, in the right order.
- **`docs/DATA_ENTRY_RULES.md`** — ten rules that will save you a year of
  rework. Read before entering your second person.
- **`docs/LASER_CHECKLIST.md`** — the ten things to check before you cut
  anything you care about.
- **`docs/ROADMAP.md`** — twenty-five ideas already specified, ranked.

## Bringing in an existing tree

```bash
python3 tools/import_ftz.py "My Tree.ftz" my-family.helix   # MyHeritage
```

## Requirements

Python 3.11+. The core needs nothing else. Optional extras:
`ezdxf` (DXF), `shapely` + `pyclipper` (kerf and islands), `fonttools`
(text outlines), `reportlab` (PDF).

Everything runs on your own machine. Nothing is uploaded anywhere.
