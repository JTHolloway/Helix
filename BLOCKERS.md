# What must be built before this is a usable product

## Done already

**The layout.** It used to sweep sibling arcs across unrelated people and put
people on identical angles. `helix/layout/subject_grid.py` now uses a
single-pass tidy tree and all four numbers in `tools/diagnose_layout.py` read
zero. `docs/KNOWN_ISSUE_LAYOUT.md` records what it still deliberately cannot
do.

**The chart.** `helix/layout/couple_grid.py` + the `radial_family` design:
one cell per couple, one ring per generation, founders at the centre.
Marriage, siblings, cousins and remarriage are all readable off the geometry
without a legend. `python3 tools/diagnose_layout.py <file> --cells`.

**Blocker 1, below.** You can enter a family in the app. The ten-step
sequence at the end of `docs/DATA_ENTRY_UI.md` runs start to finish in the
browser; `tests/test_records.py` drives the same sequence over HTTP.

**The ancestry half is built.** Kinship as structure, a relatives sidebar,
narrowing a chart by relation (which re-lays it out rather than hiding
branches), profiles with photographs and facts, and printouts. See
`docs/ANCESTRY.md`. It is not one of the three blockers below — those were
about making the program usable at all — but it is what makes the file worth
keeping between renders.

**Start at Blocker 3.**

---

Two gaps still stop Helix being usable on somebody else's data. Everything
else is polish. **Build these in order and do not skip ahead.** Each has
acceptance criteria that can be checked by running a command.

---

## Blocker 1 — Entering your family in the app  ✅ DONE

**Files:** `helix/server.py`, `helix/web/js/inspector.js`,
`helix/web/js/main.js`, plus a new `helix/web/js/edit.js`

**Full specification: `docs/DATA_ENTRY_UI.md`.** Build it from that document.
It gives the screens, the button-to-database mapping, every endpoint with its
payload, the navigation, and a ten-step acceptance sequence.

Built in `helix/store/records.py` (every write, and undo), the endpoints in
`helix/server.py`, and `helix/web/js/edit.js` + `inspector.js` on the front.
`tests/test_records.py` drives it against a running server.

Two things from the Navigation list are **not** built: back/forward through
visited people with browser history, and a "recently edited" list. Neither
blocks entering a family.

The model in one line: **you are always standing on somebody, and you add the
next person relative to them.** Add father / Add mother / Add partner / Add
child / Add brother or sister. The word "union" must never reach the screen.

**Done when** the ten-step sequence at the end of `docs/DATA_ENTRY_UI.md`
can be completed entirely in the browser, and survives a restart. It can:

```bash
python3 -m pytest tests/test_records.py -q      # 15 tests, over real HTTP
```

**Persistence is already built** — see `docs/KEEPING_YOUR_WORK.md`. Every
write commits immediately, daily backups are automatic, migrations run on
open, and `helix archive` writes a portable zip. You are adding the create
and delete endpoints on top of a save model that already works, so do not
build a Save button, an autosave timer, or a document-dirty flag. There is
no unsaved state.

---

## Blocker 2 — Laser output needs a manual step  ✅ DONE

**Files:** `helix/fab/strokefont.py` (new), `textpath.py`, `islands.py`,
`preflight.py`

```bash
python3 -m helix.cli render my.helix --production -o cut.svg
```
now prints the island report and the pre-flight, and the file has **no
`<text>` elements** in it.

**The face is built in.** `strokefont.py` is a single-stroke engraving face —
one centreline pass per letter, three to five times faster on the machine
than filled outlines and crisp at 2 mm. It is drawn in the repository rather
than loaded, because Helix installs nothing and a missing font must never be
the reason a chart will not cut. Drop a Hershey JSON into `fab/hershey/` and
it wins; the coordinate space is the same.

**Text becomes geometry on the PLAN**, in `textpath.bake`, before any writer
sees it — so SVG, PDF, EPS and DXF all get it and none of them has to know
what a letter is. Colour, layer and `person_id` all survive, so hover and
search still work on a production file.

**Islands need no geometry library.** It is a nesting question: count how many
closed CUT loops contain each one, and even depth greater than zero is a piece
that would fall out. Even-odd ray casting, exact for the polylines this
program emits. `islands.check()` returns a report; `auto_bridge` is
deliberately still unbuilt, because where a tab goes is a judgement about how
the finished piece looks.

**Pre-flight gained two real checks** and lost a stub: the island report, and
"engraving outside the cut line", which found two live bugs on its first run
— the key sitting in a corner the round cut never reached, and a border circle
drawn around a centre that is off the sheet when the chart is a fan.

`kerf.py` is still unbuilt and is not a blocker: every laser package does kerf
offset at the machine, and doing it here without callipers on a test strip
would be a guess.

---

## Blocker 3 — No way in or out for anyone else's data

**Files:** `helix/io/gedcom/`, `helix/io/csv_import.py`

Lower priority than it looks, and deliberately ranked third. If you are
entering your own family by hand (Blocker 1), you never need to import
anything. It matters for three narrower reasons:

- **Backup and portability.** A GEDCOM export means your work is not trapped
  in one program. This alone justifies building the *writer* early.
- **A cousin sends you their tree.** Import saves weeks of retyping.
- **Ancestry, MyHeritage and FamilySearch** all export GEDCOM, so anyone
  arriving with an existing tree needs it.

Build the **writer first** — it is far simpler, and it makes the file format
honest. The reader can follow.

The module docstrings list the traps: ANSEL encoding, CONT/CONC continuation,
custom `_TAGS`, `John /Smith/` name slashes, `@#DJULIAN@` escapes, families
with no HUSB, children listed twice, cyclic pedigrees.

**Done when:**
```bash
helix export my.helix out.ged        # opens in Ancestry without complaint
helix import family.ged new.helix    # 500+ people, no invented errors
```
Anything not modelled goes into `person.notes` prefixed `[GEDCOM]`. Never
discard silently.

---

## After the blockers

`BUILD_INSTRUCTIONS.md` has the full phase list. In short: clock fitting,
research-gap ranking, DNA, and the eight designs specified in
`docs/DESIGN_CATALOGUE.md` but not yet built.

## What must not regress

```bash
python3 -m pytest tests -q       # 295 tests, all green
python3 bootstrap.py             # must still print "Ready"
```

The tests encode decisions that were arrived at the hard way — interval date
comparison, per-union sibling arcs, polar label collision, half-sibling
naming. If one starts failing, read it before changing it.
