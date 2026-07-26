# START HERE

*If you are an AI assistant who has just been handed this folder, this file is
addressed to you. If you are a human, `QUICKSTART.txt` is friendlier.*

---

## Step 1 — Run this. It is the only command needed.

```bash
python3 bootstrap.py
```

No arguments, no installation, no network. It takes about six seconds and it
will:

- check the Python version (needs 3.11+)
- create `sample-family.helix` — a realistic 400-person family
- validate that data and report any problems
- render all 11 working designs to `samples/svg/` **and** `samples/pdf/`
- build `samples/index.html`, a visual contact sheet of every design
- run the 82-test suite if `pytest` is present, and say so plainly if not

If it prints `Ready`, everything works. **Do not ask the user to run any
setup commands.** There are none.

## Step 2 — Look at what you have

```bash
python3 -m helix.cli designs        # 19 designs, what each is for
python3 -m helix.cli styles         # 12 looks
python3 -m helix.cli stats sample-family.helix
open samples/index.html             # every design, side by side
```

## Step 3 — Read these, in this order

| File | Why |
|---|---|
| `docs/KNOWN_ISSUE_LAYOUT.md` | **Read first.** The radial layout does not read properly yet. Measurements, cause, and the algorithm that should replace it. |
| `BLOCKERS.md` | **Read second.** The three gaps that stop this being usable, with acceptance criteria. Build them in order. |
| `PROMPTS.md` | Ready-made prompts for each build stage. |
| `BUILD_INSTRUCTIONS.md` | **Read before writing any code.** States exactly what is finished, what is stubbed, the build order, and eight rules that must not be broken. |
| `docs/ARCHITECTURE.md` | How the pieces fit and which direction dependencies flow. |
| `docs/DESIGN_CATALOGUE.md` | All 19 designs. The 8 unbuilt ones are specified here. |
| `docs/OPTIONS.md` | Every style token, what it does, and worked examples. Read before adding an option — it is probably already specified. |
| `docs/KEEPING_YOUR_WORK.md` | The save, backup and archive model. Already built — do not add a Save button. |
| `docs/UX_GUIDE.md` | The standard any new interface work must meet. |

## Step 4 — Work

The build order is in `BUILD_INSTRUCTIONS.md`. In short:

1. **Phase 3 — `helix/io/gedcom/`, `helix/io/csv_import.py`.** Highest value
   by a distance: until people can import an existing tree, nothing else
   matters. Algorithms and traps are documented in the module docstrings.
2. **Phase 4 — `helix/fab/islands.py`, `kerf.py`.** Needs `shapely` and
   `pyclipper`. Full algorithms are in the docstrings.
3. **Phase 5 — `helix/fab/textpath.py`.** Text as outlines for the laser.
4. **Phase 6 onward** — clock fitting, analysis, DNA, more designs.

Every stub raises `NotImplementedError` with its algorithm written out. None
of them is a mystery; they are all just unwritten.

## Verifying your work

```bash
python3 -m pytest tests -q                  # must stay green
python3 bootstrap.py                        # must still print Ready
```

If you add a design, `tests/test_layout.py` picks it up automatically and will
check it produces valid, traceable, NaN-free geometry.

## Commands, in full

```bash
python3 -m helix.cli init      my.helix --title "My Family"
python3 -m helix.cli sample    my.helix --people 400
python3 -m helix.cli serve     my.helix              # the app
python3 -m helix.cli designs   [--json]
python3 -m helix.cli styles
python3 -m helix.cli render    my.helix -o out.pdf   # .svg .pdf .dxf .json
python3 -m helix.cli render    my.helix --design radial_rings --style rings \
                               --focus thread_siblings --diameter 700 -o wall.svg
python3 -m helix.cli samples   my.helix -o samples   # every design, SVG + PDF
python3 -m helix.cli render    my.helix --focus thread_siblings -o clean.svg
python3 -m helix.cli gallery   my.helix -o gallery   # SVG contact sheet only
python3 -m helix.cli check     my.helix              # validate the data
python3 -m helix.cli verify    my.helix              # is the file sound?
python3 -m helix.cli backup    my.helix              # copy it now
python3 -m helix.cli archive   my.helix              # portable zip to keep
python3 -m helix.cli stats     my.helix              # who the family depends on
```

`pip install -e .` is optional. It only gives you `helix …` instead of
`python3 -m helix.cli …`. Nothing requires it.

## If a chart looks cluttered

That is a data-density problem, not a bug, and there are three levers:

```bash
--focus thread_siblings      # your direct line plus their brothers and sisters
--max-generations 4          # each extra generation roughly doubles the people
--max-people 120             # hard cap; least-connected dropped first
```

`--focus all` on a real family is 400+ people and will not be readable on
anything under about a metre. `thread_siblings` is usually what someone
actually wants and is typically 40-60 people.

## Things that will trip you up

- **`helix/` is both the project folder and the package folder.** Run
  commands from the project root; `python3 -m helix.cli` then works with no
  `PYTHONPATH` set.
- **The core has zero dependencies, deliberately.** SVG and PDF export are
  written by hand. Do not add a library to do something already done.
- **`GenDate` is an interval, never a date.** Ages are `AgeRange`, never
  `int`. See rule 2 in `BUILD_INSTRUCTIONS.md`.
- **Compare intervals, not midpoints.** `helix/graph/validate.py` explains
  why, using the bug that made it necessary.
- **Children attach to unions, never to parents.**
- **`RenderPlan` is the only bridge between layout and output.** If an
  exporter starts doing trigonometry, something has gone wrong.
