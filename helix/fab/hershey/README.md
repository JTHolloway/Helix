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
