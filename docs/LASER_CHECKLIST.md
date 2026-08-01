# Before you cut

Ten checks. The first nine take five minutes; skipping them costs a sheet of
walnut and forty minutes of machine time.

### 1. Check the units at the far end
Open the exported SVG in Inkscape or LightBurn and **measure something you
know**. Helix writes real millimetres into both the `width` attribute and the
`viewBox`, but importers have opinions. A file that arrives at 25.4× or
1/25.4 scale is the single most common failure, and it is invisible until the
job starts.

### 2. Text must be outlines
Your laser software does not have your fonts. Either export with
`--production` (which will bake outlines once Phase 5 lands) or convert to
paths in the laser software: Inkscape → Path → Object to Path, LightBurn →
Convert to Path. **Check afterwards** that nothing reflowed.

### 3. Map the layers
Helix writes named layers: `CUT`, `SCORE`, `ENGRAVE`, `ENGRAVE_DEEP`,
`GUIDE`. Assign each to a machine operation deliberately. `GUIDE` should be
switched off, never cut.

### 4. Look for islands
Any fully closed cut path drops a piece out of the sheet. Inner rings, letter
counters, enclosed cells. Look at the CUT layer alone and ask of each closed
shape: *is this meant to fall out?* Add bridges where it is not.

### 5. Cut a kerf test strip
Five 20 mm squares at different offsets, measured with callipers. Two minutes
of material, and it is the difference between a clock bore that fits and one
that does not. Typical: 0.15–0.22 mm on 3 mm ply.

### 6. Proof at half scale on card
1 mm card costs pennies. It will show you immediately that the generation-six
labels are unreadable, which no amount of zooming on screen will.

### 7. Check the smallest text against the material
| Material | Smallest legible |
|---|---|
| Birch ply 3 mm | 2.2 mm |
| MDF 5 mm | 2.5 mm |
| Cast acrylic | 2.0 mm |
| Anodised aluminium | 1.6 mm |
| Card | 2.0 mm |

Below these, the engrave fills in and you get a grey smudge. Helix's
pre-flight checks this for you.

### 8. Leave a margin
At least 10 mm of material outside the artwork on every side. Sheets are
rarely square and beds are rarely aligned.

### 9. Get the cut order right
**Engrave → score → interior cuts → perimeter last.** Cut the perimeter first
and the piece shifts, ruining everything after it. Most software does this by
default; confirm rather than assume.

### 10. Archive what you actually cut
Keep the exported SVG *and* the style JSON *and* the `.helix` file together,
with the date. In two years someone will ask for another one.

---

## Time and cost, roughly

A 600 mm disc with 400 names on 3 mm birch ply: **40–70 minutes** of machine
time, most of it engraving text. Halve the label content and you roughly
halve the time.

## Materials worth knowing

- **3 mm birch ply** — cheap, forgiving, pale, high contrast. Prototype on it.
  Mask with transfer tape to stop scorch marks around the engrave.
- **4 mm walnut veneer ply** — the gift material. Engrave shallow: go too
  deep and you cut through the veneer into pale core, which looks terrible.
- **3 mm cast acrylic** — frosts white when engraved, superb contrast,
  spectacular edge-lit. It must be **cast**, not extruded; extruded does not
  frost.
- **Slate** — engrave only, comes out chalk white, wonderful for coasters.
- **Anodised aluminium** — finest detail of anything here. Needs a fibre
  laser or CO2 with marking spray.

## If it goes wrong

- **Scorch marks around engraving** → mask with transfer tape, or increase
  speed and reduce power.
- **Engraving too pale** → more passes at low power beats one hot pass, which
  chars.
- **Text filled in and illegible** → text too small for the material, or
  outline text where you wanted single-line. Switch the engrave layer to a
  Hershey stroke font.
- **Piece warped** → thin webs between cuts. Increase the minimum web width,
  or cut interior detail before the perimeter.
- **Parts fell out** → islands. See check 4.
