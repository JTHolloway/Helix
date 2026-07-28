# Every option, and what it does

The complete style-token reference. A style is a JSON file; anything here can
be set in a preset, overridden on the command line, or driven live from the
interface. Values are millimetres unless stated.

Options marked **★** are specific to **Concentric Rings** (`radial_rings`),
the flagship design.

---

## labels — what the text says and how it sits

| Token | Default | What it does |
|---|---|---|
| `labels.show` | `true` | Master switch. Off gives a pure-structure chart. |
| `labels.lines` | `["{given_first} {surname}"]` | **A list, one entry per line.** This is how you get dates under the name. |
| `labels.line_scale` | `[1.0, 0.76, 0.7]` | Size multiplier per line. A date at the same weight as a name competes with it; at 76% it recedes and the name stays the thing you read first. |
| `labels.line_colour` | `[]` | Colour per line. Falls back to `type.colour`. |
| `labels.by_ring` | `{}` | Override the whole stack per generation. Keys are `"0"`, `"0-2"`, `"5+"`. |
| `labels.orientation` ★ | `radial` | `radial` \| `tangential` \| `auto`. See below. |
| `labels.flip_bottom` ★ | `true` | Turn text on the lower half so it never reads upside down. |
| `labels.min_gap_mm` | `0.5` | Clear space demanded around every label. |
| `labels.max_width_mm` ★ | `46` | Cap on how much ring width one long name may claim. |
| `labels.template` | — | Legacy single-line form. `labels.lines` supersedes it. |

### Available fields in a template

`{given}` `{given_first}` `{given_used}` `{initials}` `{surname}`
`{full_name}` `{short_name}` `{birth_year}` `{death_year}` `{lifespan}`
`{age}` `{occupation}` `{education}` `{birth_place}` `{sex}` `{n}`

`{n}` is the chart number, for use with a companion booklet.

### Choosing an orientation ★

| | How it reads | What it costs |
|---|---|---|
| `radial` | Along its own branch, outward from the ring. | A name costs only its **height** in angle, so this packs tightest. **Loses no names at any density tested.** |
| `tangential` | Around the ring, following the arc. | Far easier on the eye, but a name costs its full **width** in angle. On a crowded ring it will not fit. |
| `auto` | Tangential where the ring is roomy, radial where it is not, decided per person. | Gated at `TANGENTIAL_HEADROOM = 1.9` × the name's width. Still greedy: an early name taking a wide slot can crowd out a later one, so `auto` may drop a name or two where `radial` drops none. |

`radial` is the default precisely because it is lossless. Use `tangential` on
a sparse chart where legibility beats completeness.

> **Specified improvement.** Make `auto` two-pass: reserve every label
> radially first, then upgrade individual labels to tangential where the
> wider slot is still free. That would be lossless *and* use tangential
> wherever there is genuine room. The placer would need reservation release,
> which is why it is not built yet.

---

## layout — density and geometry

| Token | Default | What it does |
|---|---|---|
| `layout.engine` | `radial_sunburst` | Which design to run. |
| `layout.inner_radius_mm` | `70` | The hole in the middle. Leave ≥ 45 for a clock. |
| `layout.start_angle_deg` | `-90` | Where generation zero begins. `-90` is twelve o'clock. |
| `layout.sweep_deg` | `360` | Full circle, or `180` for a fan. |
| `layout.min_ring_pitch_mm` ★ | `25.4` | **Minimum gap between rings — one inch.** A hard floor: a band is `max(content needed, this)`. Rings closer than this read as clutter however well the text technically fits. |
| `layout.max_ring_pitch_mm` ★ | `0` (none) | Cap, so a sparse chart on a big panel does not end up with absurd voids. |
| `layout.ring_pad_mm` ★ | `5` | Breathing space at the outer edge of each band. |
| `layout.min_entry_gap_mm` ★ | `0` | **Density along a ring.** The arc each person is entitled to. Raise it and the ring staggers sooner, thinning out; leave at `0` and it uses the text height. |
| `couple.leaf` ★ | `auto` | **How a married couple is drawn.** `shared` stacks both names in one leaf — compact, and the marriage cannot be misread. `split` gives each partner their own leaf side by side with a tie between them, so each partner's own ancestry sits directly inside them; costs twice the width. `auto` splits only where sharing is genuinely ambiguous — both partners having parents on the chart — which on a real tree is the handful of places two families actually meet. |
| `layout.sibling_gap_cells` ★ | `0.10` | **How close brothers and sisters sit**, in cells (one cell = one couple). The first thing to turn if a family reads as scattered. Three siblings at `0.10` are a couple of cells apart; at `1.0` they are twice that and stop reading as one family. |
| `layout.family_gap_cells` ★ | `0.60` | Space between two FAMILIES. Wants to stay several times `sibling_gap_cells` — the contrast between the two is what makes a family read as a cluster rather than as part of the row. |
| `layout.max_cell_deg` ★ | `12` | **No couple may own more than this much of the disc.** A small family cannot fill a circle; stretched round it, three siblings end up forty degrees apart. Capped, the chart is drawn as a FAN of whatever angle it needs, centred, with the names the same size. Set `0` to always use the full sweep. |
| `layout.min_cells` ★ | `0` | Fewest cells the disc is divided into; `0` uses the layout's own floor. Raise it to thin a crowded chart, lower it to close a sparse one up. |
| `layout.sibling_gap_frac` ★ | `0` | Squeeze each sibling group toward its own centre by this fraction (0–0.6), so families read as clusters with air between them. `0.12` is a gentle, pleasant setting. |
| `layout.max_subrows` ★ | `3` | Cap on staggered rows per ring. |
| `layout.stagger` ★ | `auto` | `auto` \| `always` \| `never`. |
| `layout.subrow_step_mm` ★ | `font × 2.2` | Radial offset between staggered rows. |
| `layout.label_gap_mm` ★ | `1.4` | Gap between a branch end and its name. |
| `layout.weight_mode` | `leaves` | How angular space is shared: `leaves` \| `descendants` \| `equal` \| `sqrt`. |

### Who is on the chart — `--focus`

| Value | Who | Typical size |
|---|---|---|
| `bloodline` | **Everyone descended from any of your ancestors** — both sides of your family, siblings, half-siblings, aunts, uncles, cousins, nieces, nephews, and their children. Nobody else's in-laws. **Recommended.** | 150–250 |
| `thread_siblings` | Your direct line plus their brothers and sisters | 40–60 |
| `thread` | Your direct line only | 15–25 |
| `subtree` | Your line, their siblings, and those siblings' children | 60–100 |
| `all` | Every person in the file, related or not | everything |

### How the two sides of a family converge

Both sides have to meet at your parents' marriage without a line sweeping
across the middle of the disc. Three mechanisms do that:

1. **Family lines are ordered by pedigree path, not by size.** Your father is
   `0`, your mother `1`, your grandparents `00`, `01`, `10`, `11`. Sorting by
   that string puts every pair that merges side by side, because `00` and
   `01` are exactly the two people who married to produce `0`.
2. **Descent hugs the converging edge.** Within a family line, the child who
   carries the line toward a marriage is placed at the side facing the family
   they marry into. Adjacent sectors are not enough on their own: if your
   father sits at the far edge of his sector and your mother at the far edge
   of hers, the marriage is still a long chord.
3. **A married-in spouse gets a person-sized slot** beside their partner —
   not half of their partner's lineage. That single mistake was putting
   couples up to 160° apart.

Measured on the sample family, the widest marriage tie fell from **160° to
19°**. What remains long is genuine: a cousin marriage between two distant
branches really is a long-distance relationship, and the chart should say so.
| `layout.radius_gamma` | `0.5` | Chronological designs only. `0.5` is equal-area; `1.0` is linear in time. |
| `layout.time_scale` | `true` | Rings are years rather than generations. Rings ignores this — it is strictly one generation per ring. |

### How the stagger decides ★

On the **tightest real spacing**, not the average — the 20th-percentile gap
between neighbours on that ring. A ring can be half empty and still
unreadable if one couple had ten children, and that is exactly the case the
stagger exists for. Staggering a ring that does not need it is treated as
just as much a fault as failing to stagger one that does.

---

## canvas — the finished piece

| Token | Default | What it does |
|---|---|---|
| `canvas.width_mm` / `canvas.height_mm` | auto | Set them and the design fits the panel. Leave them and Rings sizes itself to its content. |
| `canvas.margin_mm` | `20` | Clear border. |
| `canvas.background` | `#FBF8F2` | Screen and print only; never cut. |

Setting a panel changes the arithmetic: spare radius is shared out evenly so
the rings breathe, and if the content will not fit you get the shortfall in
millimetres rather than a quietly squashed chart.

---

## nodes, connectors, cells, type

| Token | Default | What it does |
|---|---|---|
| `nodes.branch_mm` ★ | `4` | Length of the branch from sibling arc to person. |
| `nodes.size_mm` | `1.6` | Dot radius, for the designs that draw dots. |
| `nodes.fill` / `nodes.stroke` | | Node colours. |
| `connectors.width_mm` | `0.4` | **One line weight for the whole structure.** |
| `connectors.colour` | `#22201D` | |
| `connectors.style` | `orthogonal` | `orthogonal` \| `organic` \| `straight` \| `circuit` \| `none`. Rings always uses arcs and spokes. |
| `connectors.corner_radius_mm` | `2` | |
| `cells.shape` | `annular_sector` | `none` for Rings — it draws no cells at all. |
| `cells.stroke_by_confidence` | `true` | Unproved facts become dashed. |
| `type.family` | serif stack | The artwork's typeface. |
| `type.size_mm` | `3.0` | Base size; `line_scale` multiplies it. |
| `type.min_size_mm` | `2.2` | Floor. Below ~2.2 mm nothing reads on wood. |
| `type.colour` | `#22201D` | |
| `type.tracking` | `0` | Letter spacing. |

---

## marriage ★

| Token | Default | What it does |
|---|---|---|
| `marriage.show` | `true` | Draw a tie joining spouses. Without it two spouses are simply two names that happen to sit next to each other. |
| `marriage.colour` | connector colour | |
| `marriage.width_mm` | `width × 1.6` | Heavier than a branch, so a couple reads as a unit. |
| `marriage.inset_mm` | `1.2` | How far inside the ring the tie sits. |
| `marriage.informal_dash` | `"1.6,1.4"` | Unmarried and unrecorded unions are dashed, so the chart does not assert a marriage the records do not support. |

**Arcs are drawn per union, not per person.** If a man marries twice and has
children by both wives, each marriage gets its own sibling arc and its own
tie. A single arc across "his children" would silently state that two
families were one — and that is exactly why the database links a child to a
union rather than to a parent.

## lines ★ — what the dashes mean

Dashes only communicate if they are consistent and explained. Helix uses one
scheme throughout and prints a key on the chart.

| Line | Meaning |
|---|---|
| **Solid** | Descent, and a recorded marriage or civil partnership |
| **Dashed, fine** | Unmarried or unrecorded union |
| **Dashed, open** | Half-siblings — only one parent shared |
| **Dashed bridge** | Joins two sibling groups that share one parent |
| **Dotted** | The same person, if `repeat_parents` is on |
| **Hollow circle** | A parent who exists but was never recorded |
| **Solid cap** | The line ends here by choice — not your family to follow |
| **Dotted cap** | The line ends here *for now* — still to research |
| **Fine dots** | Uncertain — recorded but not yet proved |

### What the half-sibling dash keys off

**Half-siblinghood, not a missing partner.** You may well record your
half-sister's mother — you simply do not follow her family any further. The
half-relationship is a fact about parentage and it exists whether or not she
is on the chart. Keying the dash off "partner missing" would mean that typing
her name silently promoted your half-sister to a full sister.

The union the **subject** belongs to is the reference and stays solid: your
own brothers and sisters are the baseline, not the exception. Elsewhere in
the tree, where the subject is not involved, the earliest union is treated as
the main one.

### Where lines stop

Two very different facts otherwise look identical: *"this line is not mine to
follow"* and *"I have not got any further yet."* Anyone with no recorded
parents gets a cap — solid for a deliberate stop, dotted for the research
frontier. Tag a person `line_stops_here` to force the solid form. Every
dotted cap on the chart is a question still worth asking.

| Token | Default | What it does |
|---|---|---|
| `lines.half_dash` | `"3,2"` | Link and arc for a union with one known partner. |
| `lines.same_person_dash` | `"0.8,1.6"` | The arc joining a repeated parent's instances. |
| `lines.same_person_colour` | connector colour | |
| `lines.unknown_dash` | `"0.8,1.6"` | The hollow unrecorded-parent mark. |
| `lines.mark_unknown_partner` | `true` | Draw that mark at all. |
| `lines.unknown_offset_mm` | `5.0` | How far it sits from the recorded parent. |
| `lines.repeat_scale` | `0.82` | Size of a repeated parent's second name. |
| `lines.repeat_colour` | `#8A8073` | Lighter, so it reads as a cross-reference. |
| `lines.mark_line_ends` | `true` | Cap people whose ancestry is not recorded. |
| `lines.frontier_dash` | `"0.6,1.2"` | The cap for a line still to be researched. |
| `lines.cap_mm` | `2.2` | Cap width. |
| `lines.half_sibling_tie` | `true` | Bridge the gap between two sibling groups that share a parent, with a dashed arc at the same radius. |
| `lines.half_tie_colour` | connector colour | |
| `layout.repeat_parents` | `false` | Off: one person, one node — both families hang from them, joined by the half-sibling tie. On: the parent is drawn once per family instead, with a dotted *same person* arc. |
| `ornament.line_key` | `true` | Print the key, bottom left. |

### One person, one node ★

A man with children by two women is **one man**, and by default he is drawn
once. Both families hang from that single node, each on its own sibling arc.

What then needs saying is the relationship *between* those families, and a
dashed arc bridges the gap between the two arcs at the same radius. The three
read as one rail with a broken section: continuous, because the children
share a parent; broken, because they do not share both.

`layout.repeat_parents: true` switches to the alternative treatment used in
printed pedigrees — the parent drawn once per family, instances joined by a
dotted *same person* arc. Useful on very wide charts where the two families
would otherwise sit far apart.

## colour, thread, ornament, production

| Token | Default | What it does |
|---|---|---|
| `colour.mode` | `none` | `none` \| `sex` \| `lineage` \| `surname` \| `generation` \| `confidence` \| `geography` \| `occupation` \| `lifespan` \| `criticality`. |
| `colour.palette` | 12 colours | |
| `thread.enabled` | `true` | Highlight your direct line. |
| `thread.colour` | `#A3392B` | |
| `thread.stroke_width_mm` | `1.4` | |
| `thread.layer` | `ENGRAVE_DEEP` | Cut it deeper so it catches the light. |
| `ornament.time_rings` | `true` | Faint generation guides. |
| `ornament.border` | `true` | |
| `ornament.title` | `""` | |
| `ornament.clock` | `false` | Reserve a movement bore. |
| `production.material` | `birch_ply_3mm` | Drives the pre-flight limits. |
| `production.kerf_mm` | `0.18` | |
| `production.text_to_paths` | `true` | Required for the laser. |

---

## Conditional rules

A style may carry rules evaluated per person:

```json
"rules": [
  { "when": "gen > 4 and not living", "set": { "type.size_mm": 2.4 } },
  { "when": "confidence < 2", "set": { "cells.stroke": "#9A9282" } }
]
```

Expressions run through a whitelisted AST walk, **never `eval()`** — style
files get shared between people, and a style must never be able to run code.

---

## Worked examples

**A metre of ply, names and dates, rings an inch apart**

```bash
helix render my.helix --design radial_rings --style panel1m \
    --panel 1000x1000 --ring-pitch 25.4 --focus thread_siblings -o panel.svg
```

**Sparse and airy — few people, big gaps, names following the rings**

```json
{ "extends": "rings",
  "layout": { "min_ring_pitch_mm": 45, "min_entry_gap_mm": 14,
              "sibling_gap_frac": 0.2 },
  "labels": { "orientation": "tangential",
              "lines": ["{given_first} {surname}", "{lifespan}"] } }
```

**Dense reference chart — everyone, initials only, tight rings**

```json
{ "extends": "rings",
  "layout": { "min_ring_pitch_mm": 14, "max_subrows": 3 },
  "labels": { "lines": ["{initials}"], "orientation": "radial" },
  "type": { "size_mm": 2.3 } }
```

**Full detail on the inner rings, names only at the rim**

```json
{ "labels": {
    "lines": ["{given_first} {surname}"],
    "by_ring": {
      "0-2": ["{given} {surname}", "{lifespan}", "{birth_place}"],
      "3-4": ["{given_first} {surname}", "{lifespan}"],
      "5+":  ["{given_first} {surname}"] } } }
```
