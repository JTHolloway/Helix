# Hershey single-line fonts

Drop the public-domain Hershey vector font data here as JSON:

```json
{ "A": [ [[0,0],[4,21],[8,0]], [[2,7],[6,7]] ], "B": [ ... ] }
```

Each character maps to a list of strokes; each stroke is a list of `[x, y]`
points in the original NBS coordinate space (cap height ≈ 21 units, baseline
at y = 0, y increasing upward).

Sources: the `hersheydata` module bundled with Inkscape's *Hershey Text*
extension, or the original `jhf` files, converted with `tools/convert_hershey.py`.

Recommended set:
- `hershey_sans_1stroke.json` — the default engraving face
- `hershey_serif_medium.json` — for the Heirloom style
- `hershey_script.json` — for cartouches and titles only

## There is already a face

`helix/fab/strokefont.py` ships one, drawn in the repository, and it is what
`--production` uses unless a JSON turns up here. That is deliberate: Helix
installs nothing, and a missing font must never be the reason somebody's chart
will not cut.

A file here **wins over it**, which is how you swap in a Hershey script for a
cartouche or a serif for the Heirloom style. Either shape is read — the flat
one above, or the richer one `strokefont.face()` returns, which carries
advance widths and a fold table for accented letters instead of measuring
them from the ink.
