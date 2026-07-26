# Design catalogue

Nineteen designs. Eleven are built and rendering; eight are specified and
registered, appearing in the gallery with a note.

The important idea: a design is not a hardcoded picture. It is a combination
of four independent choices, which is why there can be this many without
nineteen separate codebases.

```
design  =  layout engine   ×   router   ×   node glyph   ×   label policy
           (where people        (how links    (how a person   (what text,
            sit)                 are drawn)    is drawn)       and where)
```

Change the router on the sunburst and you get the Labyrinth, the Botanical or
the Circuit look without touching the layout. Change the glyph on the metro
map and it becomes a dot-and-line diagram. The combinations that are worth
naming are shipped as **styles** (`helix styles`).

---

## Radial family

### 1. Radial Sunburst — `radial_sunburst` ✅
Annular cells radiating outward, earliest ancestors innermost. The
architectural, unmistakable family-tree shape. This is the "blocky" one, and
blocky is a feature here: solid cell walls give a laser plenty to bite on and
the piece stays rigid.

**Good for** large families, engraving, a first view of everything.
**Laser** excellent. **Styles** `labyrinth`, `heirloom`, `circuit`.

### 2. Concentric Rings — `radial_rings` ✅ ★
**One ring per generation.** Thin arcs joined by radial branches, nothing
filled, nothing boxed. This is the circular-maze idea drawn as line-work.

Reading a family is always the same three moves — **out, along, out**:

- a **radial spoke** runs outward from the parent to the children's ring
- a **ring arc** at the inner edge of that ring spans only *that parent's
  children*
- a **radial branch** carries each child out from the arc
- the child's **name** is set along its own branch, starting where the
  branch ends

The rings are not drawn as circles. They *emerge* from the sibling arcs
lining up at the same radius, which is why it reads as a maze rather than a
target.

#### Rings are sized to the text, not the text to the rings

The band reserved for each generation is measured before anything is drawn:

```
band = (sub-rows − 1) × step  +  branch  +  gap  +  longest name  +  padding
```

The next ring starts where that band ends, and the canvas is sized to the
total. Text therefore cannot be obstructed by the ring outside it — the room
was reserved first. Ask for longer labels and the piece grows; ask for
initials and it shrinks.

#### What you can change

Rings has the deepest customisation surface of any design here. The full list
is in **`docs/OPTIONS.md`**; the ones that change the character of the piece:

| | |
|---|---|
| **What the text says** | `labels.lines` is a *list*, one template per line — name, dates underneath, occupation under that. `labels.line_scale` sets each line's size so the dates recede behind the name. `labels.by_ring` gives the inner ancestors full detail and the crowded rim just a name. |
| **Which way it reads** | `radial` along the branch (packs tightest, loses nothing), `tangential` around the ring (easiest to read), or `auto`. Never upside down, whichever you pick. |
| **Density along a ring** | `min_entry_gap_mm` sets the arc each person is entitled to. Raise it and the ring staggers sooner and thins out. |
| **Density between rings** | `min_ring_pitch_mm` — a hard floor, one inch by default — and `max_ring_pitch_mm` to stop a sparse chart drifting apart. |
| **Family grouping** | `sibling_gap_frac` squeezes each sibling group toward its own centre, so families read as clusters with air between them. |
| **Staggering** | `stagger: auto \| always \| never`, and `max_subrows`. |

#### Marriages, remarriage and half-siblings

Sibling arcs are drawn **per union**, never per person — a single arc across
"his children" would state that two marriages were one family of eight.

A parent with two families is drawn **once** — one person, one node — with
both families hanging from him on their own sibling arcs. The gap between
those arcs is bridged by a **dashed arc**, so the two groups read as one rail
with a broken section: joined, because they share a parent; broken, because
they do not share both. (`repeat_parents: true` offers the printed-pedigree
alternative, where the parent is drawn once per family instead.)

The dash marks **half-siblinghood, not a missing partner**. Record your
half-sister's mother or not, as you like — the half-relationship is a fact
about parentage either way, and typing her name never promotes a half-sister
to a full sister. Where a parent genuinely is unrecorded, a **hollow circle**
stands in their place, so the chart says somebody is missing rather than
inventing them.

Anyone whose ancestry is not recorded gets a **cap**: solid where the line
stops by choice, dotted where it is simply the edge of your research. Every
dotted cap is a question still worth asking.

Marriage ties are heavier arcs just inside the ring; unmarried and unrecorded
unions are dashed, so the chart never asserts a marriage the records do not
support. Lone parents, unknown partners and same-sex partnerships all render
with no special-casing, because the union model carries them natively.

A **key** in the bottom-left names every line style.

#### Both sides of the family meeting in the middle

Your mother's side and your father's side each run outward from the centre
and must converge on their marriage without a line crossing the disc. Family
lines are therefore ordered by **pedigree path** rather than by size, descent
is steered to hug the edge facing the family it marries into, and a
married-in spouse is given a person-sized slot beside their partner rather
than half a sector. On the sample family that took the widest marriage tie
from 160° down to 19°.

Use `--focus bloodline` for the full picture: everyone descended from any of
your ancestors — both sides, siblings, half-siblings, aunts, uncles, cousins,
nieces, nephews and their children, and nobody else's in-laws.

#### Fitting a real panel

Give it a finished size and the arithmetic runs the other way. On a
1000 × 1000 mm square of ply:

```bash
helix render my.helix --design radial_rings --style panel1m \
             --panel 1000x1000 --ring-pitch 25.4 -o panel.svg
```

- **Minimum ring pitch** is enforced as a floor — an inch by default, because
  rings closer than that read as clutter however well the text technically
  fits. A band is `max(content needed, minimum pitch)`.
- **Spare radius is shared out evenly**, so a small family on a big panel
  spreads to fill it rather than huddling in the middle inside a wide blank
  margin.
- **If it genuinely will not fit**, you get the shortfall in millimetres —
  *"too full by 196 mm; needs about 596 mm across, your panel is 400 mm"* —
  rather than a silently squashed chart.

A metre square comfortably holds a full 375-person family at five
generations, with about 59 mm between rings. That is more than twice the
minimum, so there is plenty of room to raise the text size.

#### Staggered rows when a ring gets tight

When a ring is crowded, people alternate between two or three sub-rows at
slightly different radii. Neighbours alternate, so same-row neighbours sit
*two* apart and can be packed twice as tightly without their names touching.
Ten siblings across a full circle need one row; the same ten squeezed into a
30° wedge deep in a large tree get two rows of five, low-high-low-high.

Tracing is unaffected, because every child still hangs off the same sibling
arc — only the branch lengths alternate.

The decision is made on the **tightest real spacing** (the 20th-percentile
gap), not the average. A ring can be half empty and still unreadable if one
couple had ten children, and that is precisely the case the stagger exists
for. Staggering a ring that does not need it is treated as just as much a
fault as failing to stagger one that does.

#### Why the labels stopped disappearing

Collision testing for radial text happens in **polar coordinates**, not with
bounding boxes. A 35 mm name at 45° has a bounding box 25 mm square, so an
axis-aligned test rejects neighbours that in reality clear each other easily —
that alone was discarding about a quarter of the names. In polar terms the
test is exact: two radial labels clash only if their angular bands *and*
their radial bands overlap.

**Good for** the circular-maze look; a clock face; anything where the paths
should be the subject. **Laser** excellent — uniform thin strokes, quick to
engrave, no fills to muddy. **Style** `rings`.

### 3. Radial Roots — `radial_organic` ✅
Tapering Bézier curves that thicken toward the centre like a root system.
Line weight is proportional to how many descendants flow through it. People
are dots — filled if they have died, open if they are living.

**Good for** elegant posters, a delicate natural look. **Laser** good.
**Styles** `nordic`, `botanical`.

### 4. Radial Lifelines — `radial_lifeline` ✅
Every person is a bar running from the year they were born to the year they
died. Bar **length is lifespan**. Suddenly you can see infant mortality as a
band of stubs, an epidemic as a ring of truncated bars, and a matriarch who
outlived three of her children as a bar spanning half the disc.

The single most information-dense design here, and the one that most reliably
makes people emotional.

**Good for** anything where you want the data to say something.
**Laser** excellent. **Style** `lifelines`.

### 5. Time Spiral — `radial_spiral` ✅
One continuous Archimedean spiral of years; everyone sits on it at the moment
they were born, with branches linking parent to child across the coils.

**Good for** long thin lineages; emphasising time over structure.
**Laser** good.

### 6. Half Fan — `fan_180` ✅
The traditional pedigree fan: you at the centre, ancestors spreading outward
over a half circle. Positions come from Ahnentafel numbering, so a missing
grandparent leaves a visible hole exactly where they belong — and that hole is
the point, because it is the next thing to research.

**Good for** a mantelpiece; conventional framing. **Laser** excellent.

---

## Linear family

### 7. Transit Map — `metro_map` ✅ ★
The classic flat underground diagram. Routes run at 0°, 45° and 90° only;
stations are perpendicular ticks; interchanges are white-filled rings; labels
stay horizontal so they can always be read. Time runs left to right along a
year axis, so the diagram is chronologically honest as well as pretty.

This is the strongest answer to "something that isn't a circle". It handles
many unrelated families gracefully — each simply gets its own colour — and it
scales to a very large sheet without becoming a scribble.

**Good for** a wall piece people will actually read; families with several
distinct branches. **Laser** good. **Style** `tubemap`.

### 8. Timeline Lanes — `timeline_lanes` ✅
A year axis across the page. Every person is a horizontal bar spanning their
life, stacked in generation bands. The clearest possible view of **who
overlapped with whom** — you can point at 1918 and see exactly who was alive.

**Good for** long thin posters; understanding the family as history rather
than as structure. **Laser** excellent. **Style** `timeline`.

### 9. Classic Tree — `dendrogram` ✅
The familiar left-to-right tree, drawn properly: aligned generations, elbow
connectors, tidy sibling groups, no crossings within a branch.

**Good for** reference printing, checking your data, sharing with relatives
who want something conventional. **Laser** excellent.
**Styles** `blueprint`, `proofsheet`.

### 10. Proportional Bands — `icicle` ✅
Stacked bands whose width is proportional to descendant count. A sunburst
unrolled flat. Lines that flourished are wide; lines that died out taper to
a sliver.

**Good for** seeing at a glance which branches thrived. **Laser** excellent.

### 11. Treemap — `treemap` ⏳ *Phase 10*
Nested rectangles sized by descendant count, squarified. Uses every square
millimetre of a rectangular sheet.

### 12. Hourglass — `hourglass` ✅
Ancestors fanning upward, descendants fanning downward, you at the waist.
The most natural shape when you are the point of the exercise: your whole
ancestry above, your children and their children below.

**Good for** a chart centred on one living person. **Laser** excellent.

---

## Network family

### 13. Arc Diagram — `arc_diagram` ✅
Everyone on one baseline in date order; every parent-child link is a
semicircle above it. Cousin marriages and pedigree collapse show up as
unmistakable loops that nothing else reveals so plainly.

**Good for** spotting endogamy. **Laser** good.

### 14. Nested Families — `circle_pack` ✅
Each family is a circle; its children are circles inside it. Nesting depth is
descent. No dates at all — pure shape.

**Good for** grasping the shape of a family instantly. **Laser** good.
**Style** `nested`.

### 15. Layered Network — `sugiyama` ⏳ *Phase 9*
Proper layered graph drawing: generations as layers, then barycentric
crossing minimisation. The only design that handles a heavily intermarried
tree without turning into spaghetti. Worth building for families from small
villages, where everyone is everyone's cousin.

### 16. Hive Plot — `hive` ⏳ *Phase 9*
One straight axis per family line; links arc between axes. Turns "are we
inbred?" from an anxiety into a measurement.

### 17. River of Descent — `sankey` ⏳ *Phase 9*
Ribbons whose width is the number of descendants flowing forward through
time. Branches that died out visibly narrow to nothing. The most emotionally
direct design in the catalogue — and the worst for laser cutting, because the
ribbons are filled areas.

---

## Spatial family

### 18. Map View — `geo_map` ⏳ *Phase 9*
People plotted at their birthplace on a real coastline, with descent lines
between generations. A family that moved from Somerset to Bristol to London
becomes a story about place rather than a diagram about people.

Needs geocoded places. Ship an offline UK parish gazetteer rather than
calling an API — no network, no data leaving the machine.

**Laser** excellent: a coastline cuts beautifully.

### 19. Star Chart — `constellation` ⏳ *Phase 10*
Force-directed positions rendered as a night sky. People are stars,
brightness is descendant count, lineages are constellations with drawn
figures. Deliberately does not look like a family tree.

---

## Keeping a chart readable

Every design here will turn into a grey mat if you point it at 400 people on
a 600 mm disc. Density is a setting, not a property of the design:

| Lever | Effect |
|---|---|
| `--focus thread_siblings` | Your direct line plus their brothers and sisters. Typically 40–60 people. **Start here.** |
| `--focus thread` | The direct line alone. 15–25 people. Very clean. |
| `--max-generations 4` | Each extra generation roughly doubles the population. |
| `--max-people 120` | Hard cap; the least connected are dropped first. |
| Shorter label template | `{given_first} {surname}` beats `{given} {surname} {lifespan}` by a mile. |
| Bigger piece | Legibility scales with circumference, so radius, not area. |

Helix reports how many labels it had to leave off. If that number is not
zero, the chart is over-full and one of the levers above is the answer.

## Choosing

| If you want… | Use |
|---|---|
| The circular maze | `radial_rings` + `rings` |
| The classic thing, done well | `radial_sunburst` + `labyrinth` |
| Something people will stand and read | `metro_map` + `tubemap` |
| A clock | `radial_rings` + `rings` |
| To feel something | `radial_lifeline` + `lifelines` |
| To understand your own history | `timeline_lanes` + `timeline` |
| To check your data | `dendrogram` + `proofsheet` |
| A gift | `radial_organic` + `botanical` |
| To find out if you are inbred | `arc_diagram` |
