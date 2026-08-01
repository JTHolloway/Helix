# Making this easy to use

This is a specification, not an aspiration. The program is for someone who
wants a picture of their family, not for someone who wants to learn a tool.

## The one rule

**Nobody should have to understand how it works to use it.**

Words like *render plan*, *layout engine*, *slot*, *token*, *kerf* and
*octilinear* appear in the source and in this documentation. They must never
appear in the interface. The control that changes `layout.radius_gamma` is
labelled "Time squeeze" and reads out "equal area (recommended)".

## First run

The first time a file is opened with no people in it, show a single screen
with three large choices and nothing else:

1. **I have a file from Ancestry / MyHeritage / FamilySearch** → GEDCOM import
2. **I have a spreadsheet** → CSV import with a preview of the guessed columns
3. **I'm starting from nothing** → the guided path below

The guided path asks for one person at a time, in this order, because it is
the order a human actually knows things:

> You → your parents → your grandparents → "who else do you know about?"

Each screen asks for a name and, optionally, a year. Nothing is compulsory
except a name. After four people, show them their chart. Seeing something
appear is what makes a person continue.

## Two modes, and Simple is the default

**Simple mode** shows three numbered panels:

1. Choose a look — a visual gallery, not a dropdown
2. What to show — generations, labels, colour
3. Your bloodline — the Thread, and the what-if toggle

**Advanced mode** adds size, typography, connector style, angles and
fabrication. It is one click away and it remembers your choice.

A person should be able to produce a piece they are proud of without ever
opening Advanced.

## Rules for controls

- **Show pictures, not names.** Designs are chosen from thumbnails. Nobody
  can guess what "icicle" means, but everyone recognises the shape.
- **Say what it does, not what it is.** "Hide details of living people", not
  "Enable privacy redaction". "Rings are years, not generations", not
  "Chronological radius mapping".
- **Every slider has a readout in real units.** "2.9 mm", not "29".
- **Mark the good default.** The time-squeeze slider says "equal area
  (recommended)" at 50.
- **Update live.** Preview redraws about 120 ms after the last change. Never
  make someone press Apply to see what they just did.
- **Sensible things happen automatically.** Choose a radial design and the
  canvas becomes square. Choose a linear one and it becomes a landscape sheet.

## Never show an error, ever

Every failure produces a sentence naming the problem and a sentence naming
the fix.

| Bad | Good |
|---|---|
| `KeyError: 'radial_ringz'` | "There's no design called 'radial_ringz'. Did you mean Concentric Rings?" |
| `ValueError: could not parse date` | Store it as typed, show "Not recognised — try 1834, abt 1834, or bef 1900." |
| `sqlite3.OperationalError` | "Couldn't open that family file. It may be in use by another window." |
| *silently drops 200 labels* | "202 names didn't fit. Try fewer generations, a bigger size, or shorter labels." |

That last one is the pattern to imitate: the program noticed something the
user could not see, said so plainly, and offered three concrete fixes.

## Never lose anything

- **Autosave.** Edits in the person panel commit on Save; the file is SQLite,
  so there is no "unsaved document" state to lose.
- **Back up before anything destructive.** `store/db.backup()` keeps the last
  30 copies in `backups/`.
- **Undo everything.** The `change_log` table records before/after for every
  write. Wire Ctrl-Z to it.
- **Never delete.** "Remove" marks a record inactive. A wrong ancestor
  deleted in frustration at midnight is a real loss.
- **Keep what was typed.** An unparseable date is stored verbatim alongside
  `kind='unknown'`.

## Accessibility is not a feature

- **Atkinson Hyperlegible** is the interface typeface. It was drawn for low
  vision and costs nothing. The artwork uses whatever the style specifies —
  this applies to the tool, not the output.
- Every control reachable by keyboard; visible focus rings; `/` focuses
  search, `f` fits, `t` toggles the Thread, `c` toggles what-if, `Esc` clears.
- Colour is never the only signal: confidence is *also* dash pattern, living
  status is *also* an open circle.
- `prefers-reduced-motion` is respected.
- Touch targets ≥ 36 px.
- Real `<label>` elements, real `<dialog>`, real `aria-pressed`.

## Performance you can feel

- Under 2,000 people the plan is recomputed from scratch on every change.
  Above that, cache the grid and recompute only geometry.
- Debounce at 120 ms — long enough to avoid thrash, short enough that a
  slider feels connected to the picture.
- Show "Drawing…" only if a render exceeds 300 ms. A flash of a spinner is
  worse than no spinner.

## Answer the size question on screen

Someone choosing a design has already bought, or is about to buy, a physical
thing. The live preview exists to answer one question: **will this fit the
panel I have?**

So the size panel is in Simple mode, not Advanced, and it carries a badge
that is never ambiguous:

> **Fits your 1000 mm panel** — 375 people over 5 rings, 59 mm apart
> (2.3 inch). Every name fits.

or

> **Too full by 196 mm** — needs about 596 mm across; your panel is 400 mm.
> Fixes: fewer generations, "My direct line only", shorter labels, or a
> larger panel.

Panel sizes are offered as named presets (1 m square, common laser bed, A0,
A1) with a custom option, because almost nobody wants an arbitrary number.
Ring spacing reads out in both millimetres and inches.

## The moment that sells it

The what-if toggle. Hover any ancestor and everyone who would not exist
without them fades out, with a single line of text:

> Without **Susannah Marlow**, **108** people vanish from this chart —
> including you.

Get this one interaction right and the rest of the program is forgiven a
great deal.
