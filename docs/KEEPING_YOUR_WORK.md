# Keeping your work

You may spend years on this. Here is exactly what happens to your research,
and what to do so that nothing can take it away.

---

## There is no Save button, and that is deliberate

Your family is stored in a **single file** — `my-family.helix` — which is an
ordinary SQLite database. Every change you make is written to it **the moment
you make it**. Not on a timer, not when you close the window.

So there is no unsaved state. You can close the browser, close the laptop,
lose power, or walk away for a year, and the file is exactly as you left it.
The interface shows **Saved** in the corner as a statement of fact; it never
says "unsaved", because that state does not exist.

The database is opened with `synchronous = FULL`, which means a write is on
the disk before the program is told it succeeded. This is slower than the
default, and worth it.

---

## Backups happen without you

**Automatically, once a day**, the first time you open your file, a dated copy
is written to a `backups/` folder beside it. Thirty are kept, so you can go
back about a month.

```
my-family.helix
backups/
  my-family-2026-07-26.helix
  my-family-2026-07-25.helix
  ...
```

Copies are taken through SQLite's own backup mechanism, so a backup is never
a half-written file even if something was mid-write.

**Manually, whenever you like:**

```bash
helix backup my-family.helix
```

Do this before anything you feel nervous about.

---

## Get it off your computer

Automatic backups sit next to the original, so they protect you from mistakes
but not from a dead disk or a stolen laptop.

```bash
helix archive my-family.helix
```

That writes **one zip** holding everything:

| Inside | What it is |
|---|---|
| `family.helix` | The database itself |
| `family.json` | **Every record as plain data.** The long-term guarantee |
| `people.csv` | One row per person, for a spreadsheet or another program |
| `renders/` | The charts as they looked when you made the archive |
| `README.txt` | How to read it all without Helix |

It is small — a few hundred kilobytes for a large family — so you can email it
to yourself. Do that once a month and put a copy in cloud storage. A decade of
work, one attachment, no excuse.

### Why the JSON matters

`family.json` is the answer to *"what if this program stops existing?"* It is
tables of plain records — people, names, families, events — readable by any
language on any machine, with no knowledge of Helix's internals. Vague dates
survive as intervals, so "about 1834" stays a range rather than hardening into
a false certainty.

---

## Bringing in a tree from elsewhere

```bash
python3 tools/import_ftz.py "My Tree.ftz" my-family.helix
```

Imports a MyHeritage / Family Tree Builder `.ftz` — people, families, parent
links, births and deaths. Zero years become unknown dates rather than
guesses, and nothing is invented. GEDCOM import is Blocker 3 in
`BLOCKERS.md`; until then, `.ftz` and the CSV route cover most cases.

## Putting it back

An archive is only a backup if the data can go back in.

```bash
helix restore my-family-archive-20260726.zip -o my-family.helix
```

It accepts any of three things:

| Give it | What happens |
|---|---|
| An archive `.zip` | Rebuilt from `family.json`, every table |
| A bare `family.json` | The same |
| A `.helix` backup | Copied and checked |

It refuses to overwrite an existing file unless you pass `--overwrite`, and
it verifies the result before telling you it worked. Restoring an archive
produces a byte-identical chart to the original — that is checked by a test
which renders both and compares.

```
  Restored 288 people into my-family.helix
  Archive was made 2026-07-26T16:46:14
    person           288
    person_name      288
    union_            80
    union_child      181
    ...
  No problems. Open it with:  helix serve my-family.helix
```

## Checking the file is sound

```bash
helix verify my-family.helix
```

```
  my-family.helix
  214 people, 33 families, 550 recorded facts
  schema version 2
  4 backups, newest my-family-2026-07-26.helix

  No problems found. Your file is sound.
```

It runs SQLite's integrity check, looks for broken links between records, and
finds people with no name. Run it after any crash, or before an archive.

---

## Opening an old file in a future version

The schema carries a version number, and upgrades run automatically when the
file is opened. A file created today will open in a version written years from
now, and its data will be migrated rather than discarded. Migrations are
append-only in `helix/store/db.py`, because somebody's file is sitting at
every version this program has ever had.

---

## Exporting, printing, cutting — whenever you like

Nothing needs preparing first. Your file is always current, so any export is
always up to date.

Formats follow the file extension. Everything comes out at **true physical
size**, so a printer, laser or CAD package will not resize it.

| Extension | Use it for | Notes |
|---|---|---|
| `.dxf` | **CAD and CAM** — Fusion 360, AutoCAD, FreeCAD, Rhino, SolidWorks, LightBurn | R12, the most widely readable revision ever published. Layers CUT / SCORE / ENGRAVE / ENGRAVE_DEEP / GUIDE. Units flagged as millimetres |
| `.svg` | Laser software, Illustrator, Inkscape, the web | Named layers, real mm |
| `.pdf` | Printing, framing, sending to someone | Page is the exact finished size |
| `.eps` | Older CAD, sign cutting, Illustrator | Vectors intact |
| `.json` | Scripting, or your own tooling | The full render plan |

```bash
helix render my.helix --style panel1m --panel 1000x1000 -o clock.dxf   # CAD
helix render my.helix --production -o cut.svg                          # laser
helix render my.helix -o wall.pdf                                      # print
helix render my.helix -o tree.eps
```

For designing a clock around the chart, take the **DXF** into your CAD
package: the bore, the ring geometry and the cut outline all arrive as real
millimetre polylines on separate layers, ready to be extruded, offset or
combined with a movement housing.

You can do this on day one with four people, or in five years with four
hundred. The chart is derived from the file every time — it is never stored,
so it is never stale.

---

## If the worst happens

| What went wrong | What to do |
|---|---|
| Deleted someone by mistake | Ctrl-Z. Records are marked inactive, never removed |
| Made a mess this session | Copy back the newest file from `backups/` |
| Corrupted file | `helix verify`, then fall back to `backups/` |
| Lost the computer | Unzip your newest archive |
| Helix no longer exists | Read `family.json` from your archive |
| Want to move to another program | `people.csv`, or GEDCOM export once built |

---

## A routine that works

1. Research and enter whenever you like. It saves itself.
2. Once a month: `helix archive`, and put the zip somewhere else.
3. Before a big reorganisation: `helix backup`.
4. Once a year: open your oldest archive and check you can still read it.

That fourth step is the one people skip, and it is the one that tells you
whether the other three are working.
