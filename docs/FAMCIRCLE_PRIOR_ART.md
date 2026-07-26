# FamCircle

A radial **descendancy** chart engine: founders at the centre, living generations
at the rim, a clock through the middle, and laser-ready output.

```bash
pip install -r requirements.txt
python -m famcircle.main                          # GUI, opens with a demo tree
python -m famcircle.main --gedcom mine.ged --render chart.svg
python -m famcircle.main --render cut.svg --laser --dxf cut.dxf
```

---

## 1. The bit that is actually hard

Most genealogy software draws an **ancestor** fan — you in the middle, ancestors
radiating out, exactly 2ⁿ slots per ring. It is trivial to lay out.

You asked for the other direction, which is a different problem:

| | Ancestor fan | Descendancy fan (this) |
|---|---|---|
| Slots per ring | exactly 2ⁿ | anything from 1 to 14 |
| Layout | fixed division | weight-proportional subdivision |
| Ring 8 | 256 slots | could be 3 or 3,000 |

**The core tension:** people grow roughly exponentially with generation, but the
circumference of ring *g* grows only *linearly* with radius. Arc length per
person collapses outward. By generation six, names are unreadable and
unengraveable.

**The fix — adaptive ring widths.** Rather than equal rings, solve for each
radius so the narrowest wedge keeps a legibility floor:

```
r_g = max(r_{g-1} + min_width,  arc_target / θ_min,g)
```

Radius then grows near-geometrically where the tree fans out hard and
near-linearly where it doesn't. Rings get visibly wider outward — which is also
physically right, because that's where all the text is.

Set `arc_target_mm` to the smallest arc you can engrave a name into (~26 mm for
a full name at 3.4 mm cap height). Everything else follows from that one number.

### Weighting modes (Layout tab)

| Mode | Wedge width ∝ | Use when |
|---|---|---|
| `leaves` | terminal descendants | honest but brutal — one prolific line eats the disc |
| `nodes` | total descendants | similar, slightly kinder |
| `uniform` | equal per sibling | prettiest, least true |
| `damped` | (Σ children)^0.72 | **default.** Big branches stay big, small ones stay readable |
| `generations` | subtree depth | emphasises long lines over wide ones |

Start on `damped`, push `damping_alpha` toward 1.0 for honesty, toward 0.4 for
balance.

---

## 2. The counterfactual — the feature you actually asked for

You wanted to see how one absence unmakes everyone downstream. Worth being
precise about the semantics, because the obvious implementation is wrong.

Your instinct is to reach for **dominators** — who is on every path. That's the
wrong model. Dominators assume OR semantics: a node survives if *any*
predecessor survives. Under that rule your father doesn't dominate you, because
there's a path through your mother.

Existence has **AND** semantics. You need *both* parents. So removal propagates
by a simple forward closure:

> a person ceases to exist if **any** recorded parent ceases to exist

Two consequences fall straight out, and they're both nice:

1. **Every ancestor of yours is individually load-bearing.** Not some. All of
   them. `bloodline()` is exactly the transitive ancestor set, and that's why
   drawing it as one heavy line is correct rather than decorative.
2. **Impact is well defined for everyone.** `impact(x)` = size of the forward
   closure. Shade the whole chart by it (`Shade wedges by → impact`) and you get
   a criticality heat map of your own existence.

In the GUI: click anyone → the panel tells you how many people they'd erase.
**What if removed** greys the chart down to survivors. The Report tab ranks your
direct line by how much of the tree hangs off each person.

Also implemented, since it's the same machinery:
- **Relationship calculator** — LCA depths → "second cousin once removed"
- **Wright's coefficient of inbreeding** `F = Σ (½)^(n₁+n₂+1)(1+F_A)` over
  common-ancestor path pairs
- **Consanguineous union detection** → drawn as chords across the disc

---

## 3. Storing the data properly

**Facts are events, not columns.** There is no `birth_date` field anywhere.
There is a birth *event*, with a date interval, a place, a source citation and a
confidence level.

Why this matters: a columnar schema forces a migration every time you want a new
fact type. An event schema doesn't, it handles blanks natively, and it lets you
keep **two conflicting birth dates from two sources** instead of silently
choosing. Genealogy is full of that.

### Dates are intervals, not dates

This is the thing that quietly ruins amateur family databases. Real dates look
like `ABT 1834`, `BEF 1900`, `BET 1820 AND 1825`, `12 MAR 1745/6`.

Every date here stores:
- `raw` — exactly as written in the source, never destroyed
- `jd_early`, `jd_late` — Julian Day Number bounds
- `qualifier` — why it's fuzzy

Ages become interval arithmetic and display honestly as **"aged 34–36"** rather
than a fabricated 35.

⚠️ **The 1752 calendar change.** Britain dropped 11 days and moved new year from
25 March to 1 January. Dates between 1 Jan and 24 March before 1752 are often
written `1745/6`. Handled — but if you transcribe those as plain `1745` you will
be a year out, and only in that eleven-week window, which is exactly the kind of
bug you find four years later.

### Schema shape

```
individuals ─┬─ names (multiple: birth, married, aka, spelling variants)
             └─ events ─┬─ places (normalised — "Bath, Somerset" appears 400×)
                        └─ citations ── sources
families ────┬─ family_partners
             └─ family_children (link type: birth / adopted / step / foster)
```

**IDs are UUIDs, not sequence numbers.** When your cousin sends their database
and you merge, sequential IDs collide catastrophically. UUIDs don't.

**Put the `.fctree` file in git.** This is a decade-long project. In 2031 you
will want to know why you changed a great-grandmother's birth year.

---

## 4. Finding the information (UK, starting from Bath)

### Do this first, this month

**Interview the oldest living relatives. Record audio.** This is the only
irreplaceable source and it is on a timer. Everything else will still be in an
archive in twenty years. Ask about: nicknames, which sibling emigrated, who
fell out with whom, what the father *actually* did for work. Photograph every
document and photo album while you're there — including the backs.

### Free, and where the spine of the tree comes from

| Source | Covers | Note |
|---|---|---|
| **FreeBMD** | England & Wales births/marriages/deaths 1837–1992 | Free index. Gives the GRO reference to order from |
| **GRO online index** | Births & deaths | **Births show mother's maiden name** — this is how you jump a generation. Deaths show age. PDF certificates ~£3 |
| **FamilySearch** | Global, enormous | Free. Huge parish register digitisation |
| **FreeReg / FreeCen** | Parish registers, census transcripts | Volunteer-made, patchy but free |
| **Probate Search (gov.uk)** | Wills, E&W 1858–present | Free index, ~£1.50 per will. Wills name children, so they break brick walls |
| **National Archives Discovery** | Everything else | Catalogue across 2,500 archives |

### Census — the backbone

England & Wales, **1841–1921** (1921 released 2022). 1931 was destroyed by fire;
the **1939 Register** fills the gap. Census gives you whole households in one
row, plus birthplace and occupation — which is exactly the data your chart's
extra fields want.

### Pre-1837 — parish registers

Civil registration starts 1837. Before that it's baptisms, marriages and burials
in parish registers. For your area: **Somerset Heritage Centre** (Taunton) and
**Bath Record Office**. Bishop's Transcripts are the backup copy when the
original register is lost — always check both.

### Paid, but often free through your library

**Ancestry Library Edition and FindMyPast are free in many UK libraries** with a
council library card. Worth checking Bath & North East Somerset before paying
for a subscription. British Newspaper Archive is paid and worth it for
obituaries, inquests and court reports — the colour that turns names into
people.

### DNA

AncestryDNA or MyHeritage, then upload the raw file to **GEDmatch** for
cross-platform cousin matching. Two honest warnings:

- DNA finds cousins you can't find on paper, and it breaks brick walls.
- It also occasionally reveals that a paper line is wrong — an
  unexpected parentage a few generations back. It's common. Decide in advance
  how you'd want to handle it, and be careful about testing living relatives
  without telling them what might surface.

### Living people and GDPR

Standard practice: privatise anyone possibly living. `Redact anyone probably
still living` handles this on both chart and GEDCOM export. If you're sharing
the file with relatives, turn it on.

### Companion tools

**Gramps** (free, open source) is a genuinely excellent research database.
Reasonable division of labour: research in Gramps, export GEDCOM, visualise
here. FamCircle reads and writes GEDCOM 5.5.1 for exactly this.

---

## 5. Laser cutting for real

### Engrave, don't cut

The instinct is to cut the wedges out. Don't — at least not first. Cut through
every wedge and each ring segment becomes a **loose island** that drops out of
the sheet mid-job. `Analysis → Structural check` runs a union-find over the cut
geometry and tells you how many disconnected pieces you've made.

An engrave-only design on a solid disc is stronger, faster, cheaper, and the
right answer for a chart this dense.

### Kerf

The beam removes 0.1–0.2 mm. Cut on the line and every part is undersized.
Handled: disc boundary grows by half a kerf, the clock shaft hole shrinks by
half a kerf so the shaft is snug.

**Cut a 20 mm test square and measure it with calipers before anything else.**
Every machine, lens, material and even sheet varies.

### Layer conventions

Exports use the LightBurn / RDWorks colour convention so the file imports with
the right operation per layer instead of you retagging 4,000 objects:

| Colour | Layer | Operation |
|---|---|---|
| 🔴 `#FF0000` | DISC_CUT, CLOCK_CUT | cut through |
| 🔵 `#0000FF` | BLOODLINE | deep engrave — deliberately heavier |
| ⚫ `#000000` | TEXT_NAME | engrave |
| ⬛ `#404040` | TEXT_DETAIL | engrave, lower power |
| 🟢 `#00FF00` | WEDGES, CONNECTORS | light score |
| ⚪ `#808080` | RULES | barely a mark |

### Order of operations

1. **Mask the surface.** Engraving smoke stains bare ply badly.
2. **Engrave first**, while the sheet is still held flat and registered by its
   own uncut edges.
3. Score.
4. Clock hole.
5. **Disc outline last.** Once the outside is cut the part can shift.

### Two tests that save a sheet of walnut

- **Print the SVG on paper at 100% and lay it on the blank.** Every legibility
  problem is obvious on paper and invisible on screen.
- **Engrave the six smallest names onto a 60×60 offcut and read them from a
  metre away.** That's the real test, not a zoomed screenshot.

### Engraving time

Outlined text fills every counter and is slow. **Single-line ("stroke")
engraving fonts are 5–10× faster** and the correct choice past ~200 names. Drop
a Hershey-format JSON next to the app and tick the box in the Laser tab — format
documented in `text_arc.py`.

### Too big for the bed

An 8-generation chart runs 700–900 mm. Tiling emits either **pie wedges** with
dowel holes or **rectangular panels** with overlap, plus three asymmetric
registration marks so reassembly is unambiguous.

### The clock

- Standard quartz movement: 8 mm shaft, 56 mm square body, ~16 mm deep.
- Buy by **threaded shaft length** — it must clear material + washer + nut.
  `Suggest hand lengths` computes both.
- **Hands must sweep over flat surface only.** A cut-through wedge catches a
  hand as it passes. Keep the inner rings engrave-only.
- Happy accident: the earliest generations are the most sparsely documented, so
  the innermost rings hold the fewest people — exactly where you need clear
  space.

---

## 6. Things you didn't ask for that you probably want

Ranked by how much I'd actually do them.

### Strong

**Labyrinth mode.** You said "maze". Lean all the way in: close the gaps between
non-bloodline wedges so they become walls, leaving your direct line as the
*only* continuous open path from rim to centre. The object becomes a puzzle
whose solution is your ancestry. Structurally it also helps — closed gaps are
material.

**Blank slots for unknown ancestors.** Deliberately engrave empty wedges where a
parent should be, with a `?`. A visible, permanent inventory of what you haven't
found. Far more evocative than an absence, and it turns the object into a
research prompt instead of a finished statement.

**Research heat map + auto to-do list.** Already in — `Shade wedges by →
completeness`, and the **Research to-do list** button ranks gaps by how much of
the tree depends on that person. High-impact ancestor with no sources = best
possible use of next Saturday.

**Historical event rings.** Faint concentric bands for 1914–18, 1918 flu,
1939–45, the 1832 cholera epidemic, Napoleonic wars. Instantly readable: *these
are the men in the ring the Somme cut through*. Nothing else conveys that as
fast.

**Longevity bars.** Radial bar length ∝ lifespan. Child mortality before 1900
becomes visible as a ring of stubs, and the change after 1900 is stark.

**Two-proband convergence.** Highlight your bloodline and a partner's in
different weights. Where they converge (or don't) makes a genuinely good
wedding or anniversary gift.

### Good

- **Migration colouring** — wedge shade by birthplace. Watch the rural Somerset
  parishes drain into Bath and Bristol across the 1800s.
- **Confidence rendering** — dashed wedge for unproven facts. Already in
  (`Dash wedges with weak evidence`). Your chart shows its own reliability.
- **Per-person QR codes** in the outer ring, linking to a private page with
  photos, documents and sources. The disc becomes an index to the real archive.
- **Stacked multi-layer build** — each generation cut from a different veneer
  and stacked on standoffs. Solves the island problem completely and looks
  extraordinary.
- **Time-lapse export** — animate the disc filling in by year, 1750 → now.
- **Chronological/spiral radius mode** — already in. Radius ∝ birth year rather
  than generation index. Rings blur but it becomes an honest timeline.
- **Occupation glyphs** — a small engraved symbol per trade. Reads faster than
  text and costs almost no arc length.
- **Photo halftone engraving** for the four or five people you have portraits
  of, in the innermost ring.

### Nice

- Surname colour bands · twin/multiple markers · emigration arcs to a small
  inset map · a tactile/Braille edition · self-contained interactive HTML export
  to send relatives · a printed numbered key so tiny outer wedges carry just an
  index (already implemented as automatic fallback under 10 mm arc).

---

## 7. Module map

| File | What's in it |
|---|---|
| `dates.py` | Interval dates, GEDCOM parsing, 1752 dual dating, age arithmetic |
| `model.py` | Event-sourced data model |
| `db.py` | SQLite schema, FTS5 search |
| `gedcom_io.py` | GEDCOM 5.5.1 import/export |
| `graph.py` | DAG, generations, **counterfactual**, relationships, Wright's F |
| `layout.py` | **Radial engine** — weighting, adaptive rings, chords |
| `style.py` | Materials and styles |
| `text_arc.py` | Per-glyph polar text, outlines, stroke fonts |
| `render_svg.py` | Layered SVG (preview *and* laser source) |
| `export_laser.py` | Kerf, structure, tiling, DXF writer |
| `clock.py` | Movement geometry, hand clearance |
| `gui.py` | PySide6 app |

Generation assignment uses **longest path**, not shortest. If one line is
documented four generations deeper than another, shortest-path would place a
person inside their own cousin's ring.

Married-in spouses have no recorded parents, so a naive topological sort strands
them all at generation 0 — half your chart in the innermost ring. They're pulled
to their partner's generation and drawn as a band, not a founding line.

## 8. Known limits

- DXF export is geometry only (no text) — use SVG for engraving.
- Complex-outline kerf compensation needs `pyclipper`; circles are exact without it.
- No photo/media manager yet — `photo_path` exists, nothing reads it.
- Stroke fonts need a Hershey JSON supplied; loader and format are ready.
- The DAG becomes a tree by picking one primary parent per person. Cousin
  marriages therefore appear as chords rather than merged wedges. That's a
  deliberate choice — a true merged layout is not planar.
