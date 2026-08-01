# Architecture

## The shape of it

```
 SQLite (.helix)
      │  store/  — rows in, rows out. No domain logic.
      ▼
 FamilyGraph
      │  graph/  — parents, children, ancestors, the Thread, validation.
      ▼
 Grid  (abstract: generation × spread position × lineage × year)
      │  layout/base.py — scoping, ordering, weighting, partner placement.
      ▼
 RenderPlan  ◄── Style (JSON tokens)
      │  layout/engines/ — 20 designs. THE ONLY PLACE TRIGONOMETRY HAPPENS.
      ▼
 ┌────────┬────────┬────────┬────────┐
 │ screen │  SVG   │  DXF   │  PDF   │   render/ — serialisation only.
 └────────┴────────┴────────┴────────┘
```

## Why it is arranged this way

**One plan, four outputs.** The on-screen render and the laser file come from
the same geometry. What you see is provably what you cut — not a preview of
it. This is why `canvas.js` deliberately mirrors `render/svg.py` line for
line rather than being cleverer.

**The Grid is the abstraction that pays for itself.** Every engine receives
`(generation, position 0..1, lineage, year)` and maps it into its own world.
A disc, a timeline, a metro map and a circle-packing all consume the same
structure. Adding a design is ~120 lines and touches nothing else.

**Styles are data.** A style is a JSON file with inheritance (`extends`) and
optional conditional rules. Users can share them, and they cannot execute
code — rules are evaluated through a whitelisted AST walk, never `eval()`.

**Designs are combinations, not hardcoded pictures.**
`layout × router × glyph × label policy`. Eleven built engines and five
routers give far more than sixteen looks.

## The four decisions that matter most

1. **`GenDate` is an interval.** Not a date. Everything downstream — sorting,
   radial position, age, validation — depends on this being right, which is
   why it is the first file and the most tested.

2. **Children attach to unions, not to parents.** Half-siblings, remarriage,
   adoption and unknown partners all fall out of the model instead of being
   special cases.

3. **Facts are events with roles and citations.** No `birth_date` column
   anywhere. A person can have two conflicting baptism records and both must
   survive with their sources.

4. **Contingency is descendant closure, not dominators.** Descent is an
   AND-join: a child needs *both* parents, so removing anyone removes exactly
   their descendants. The dominator-tree version in `graph/thread.py` answers
   a different, weaker question and is retained only for that.

## Dependency rules

- `model/` imports nothing from Helix.
- `store/` imports `model/`.
- `graph/` imports `model/`. Never `store/` except in `load()`.
- `layout/` imports `graph/` and `style/`. Never `store/`, never `render/`.
- `render/` imports `layout/plan`. **Never** imports an engine.
- `fab/` imports `layout/plan` and `render/pathflatten`.
- `web/` talks only to the JSON API.

If `render/` ever needs to know what a `Person` is, something has gone wrong.
