# Prompts for the build chat

Copy these one at a time into a new chat with this folder attached. Each one
ends in something runnable, so you can see progress rather than take it on
trust.

---

## 1 — Orientation (always start here)

> This zip is a genealogy and laser-cutting program called Helix. Read
> `START_HERE.md`, then run `python3 bootstrap.py`. Confirm it prints
> "Ready", tell me how many tests pass, and summarise in your own words what
> is already built and what is stubbed. Do not write any code yet.

---

## 1b — Fix the layout (do this before the blockers)

> Read `docs/KNOWN_ISSUE_LAYOUT.md` in full, then run
> `python3 tools/diagnose_layout.py <my file>` and show me the four numbers.
> Replace the angular allocation in `helix/layout/subject_grid.py` with a
> single-pass tidy-tree algorithm (Reingold-Tilford or Walker) adapted to
> polar coordinates, as that document specifies. Sibling groups must come out
> contiguous and no two people may share an angle. Show me the diagnostic
> again afterwards — all four numbers must be zero — then render the rings
> design on a 1000x1000 panel and describe what you see when you trace one
> family from a grandparent down to a grandchild.

---

## 2 — Blocker 1: entering a family in the app

This is the one that turns Helix from a demo into something usable. Do it
first, and expect it to take several rounds.

> Read `BLOCKERS.md` and then `docs/DATA_ENTRY_UI.md` in full. Implement the
> record system exactly as specified there: the person panel with children
> grouped under the partner they belong to, the add-person dialogue, and all
> the endpoints listed. Two hard rules — the word "union" must never appear
> in the interface, and "Remove from tree" must mark a record inactive rather
> than SQL-deleting it. Start with the endpoints and an integration test that
> drives them; show me that test passing before you touch the front end.

Then:

> Now build the front end for it. Follow the panel layout in
> `docs/DATA_ENTRY_UI.md`. Include the duplicate check on the name field and
> the live echo of vague dates ("abt 1834" → "about 1834"). Show me the
> ten-step acceptance sequence from the end of that document, working.

Then:

> Add undo and redo from the `change_log` table, wired to Ctrl-Z and Ctrl-Y,
> at least 100 steps deep. Add the plain list view described under
> Navigation — every person, sortable by surname, birth year, or how complete
> their record is.

---

## 3 — Blocker 2: laser-ready output

> Read Blocker 2 in `BLOCKERS.md` and `helix/fab/textpath.py`. Implement
> `glyph_outlines` with fontTools and `hershey_paths` for single-line
> engraving fonts. Then `helix render --production` must emit an SVG with no
> `<text>` elements at all. Add a test asserting that. Then implement
> `helix/fab/islands.py` and `kerf.py` using shapely and pyclipper, following
> the algorithms in their docstrings.

---

## 4 — Blocker 3: GEDCOM, writer first

> Read Blocker 3 in `BLOCKERS.md`. Implement the GEDCOM **writer** first, in
> `helix/io/gedcom/writer.py`, with a `helix export` command — this is the
> backup route, so it matters even if I never import anything. Then implement
> the reader, following the traps listed in the module docstring. Write tests
> covering ANSEL encoding, CONT/CONC, `John /Smith/` name slashes, a FAM with
> no HUSB, and a cyclic pedigree.

---

## 5 — First-run experience

> Read `docs/UX_GUIDE.md`. Build the first-run flow: when a file has no
> people in it, show three choices — import a GEDCOM, import a spreadsheet,
> or start from nothing — and for the third, walk the person through you →
> parents → grandparents, one screen at a time, showing them their chart as
> soon as four people exist.

---

## 6 — Anything else

> Restore my family file from an archive and confirm it is intact:
> `helix restore <archive>.zip -o restored.helix` then `helix verify`.

> Read `docs/ROADMAP.md` and implement item N. Keep all existing tests green
> and add tests for the new behaviour.

For a new design specifically:

> Read `docs/DESIGN_CATALOGUE.md` and implement the `<key>` design in
> `helix/layout/engines/`. Follow the contract in `BUILD_INSTRUCTIONS.md`:
> consume the Grid from `build_grid`, emit Elements, use
> `common.place_radial_label` or `common.place_label` for text. It should be
> about 120 lines and touch nothing outside its own file.

---

## Useful follow-ups

> Run `python3 -m pytest tests -q` and `python3 bootstrap.py` and show me
> both outputs.

> Render the Concentric Rings design on a 1000×1000 mm panel with my direct
> line plus siblings, and tell me the fit report.

> I think X is cluttered. Read `docs/OPTIONS.md` and suggest which settings
> to change, with the reasoning.

---

## Things worth saying to the build chat

- **"Do not add dependencies without asking."** The core is deliberately
  stdlib-only; SVG and PDF are written by hand.
- **"If a test fails, read it before changing it."** Several encode decisions
  arrived at the hard way.
- **"Show me the command output, not a description of it."**
