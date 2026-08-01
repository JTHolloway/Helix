# Vendored front-end libraries

**This folder is intentionally empty, and that is the point.**

The interface uses no JavaScript libraries at all. Pan and zoom is ~70 lines
in `js/zoom.js`; SVG generation is ~80 lines in `js/canvas.js`. There is no
npm, no bundler, no build step, and nothing to go stale. Open `index.html`
through `helix serve` and it runs.

If you later need something here (a font, a mapping library for the `geo_map`
design), drop the file in and reference it with a relative path from
`index.html`. Do not add a package manager to this project without a very
good reason: a genealogy file is meant to still open in twenty years, and so
is the program that draws it.

## Typeface note

The interface asks for **Atkinson Hyperlegible** and falls back to the system
UI font if it is absent. To bundle it, put `AtkinsonHyperlegible-*.woff2`
here and add an `@font-face` block at the top of `css/app.css`. It is free
under the Braille Institute's open licence.
