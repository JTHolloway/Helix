"""Text -> outlines, and text along an arc.

WHY THIS MATTERS: laser and CNC software has no access to your fonts. A file
with live text either fails to import or silently substitutes something else.
Every exported production file must have text converted to geometry.

Two routes:
  (a) outline fonts via fontTools -- faithful, but engraves as two contours
      that the machine must fill, which is slow and muddy below about 3 mm.
  (b) single-line "stroke" fonts (Hershey) -- one centreline pass per letter.
      Three to five times faster, crisper, and legible far smaller. Use these
      for the ENGRAVE layer by default.
"""
from __future__ import annotations

import math
from pathlib import Path

HERSHEY_DIR = Path(__file__).with_name("hershey")


def glyph_outlines(text: str, font, x: float, y: float, rotate: float = 0.0):
    """Return a list of closed point-loops for `text`, in mm, ready for DXF.

    Implementation notes for the build agent:
      1. Load the TTF/OTF with fontTools.ttLib.TTFont.
      2. glyphset = font.getGlyphSet(); pen = SVGPathPen(glyphset).
      3. scale = size_mm / font['head'].unitsPerEm
      4. Advance x by hmtx advance * scale, applying GPOS kerning if present.
      5. Flatten the resulting path with render.pathflatten.flatten_d.
      6. Apply the element's rotation about (x, y) LAST.
    Fall back to the Hershey stroke font if the family cannot be resolved.
    """
    raise NotImplementedError(
        "Outline baking is Phase 5. Until then, export SVG and let your laser "
        "software convert text to paths, or switch the ENGRAVE layer to a "
        "Hershey single-line font."
    )


def hershey_paths(text: str, size_mm: float, x: float, y: float,
                  rotate: float = 0.0) -> list[str]:
    """Single-stroke engraving text. Returns SVG path strings.

    Hershey data ships in hershey/*.json as {char: [[[x,y],...], ...]} in the
    original 1967 NBS coordinate space (roughly 21 units cap height).
    """
    raise NotImplementedError("Phase 5. See hershey/README.md for the data format.")


def text_along_arc(text: str, font, cx: float, cy: float, radius: float,
                   theta_centre: float, flip: bool = False):
    """Place each glyph individually around a circle.

    Advance theta by (glyph_advance_mm / radius) radians per glyph, and rotate
    each glyph by (theta + pi/2) so its baseline sits tangent to the arc.
    If `flip`, reverse the run and add pi so it reads the right way up on the
    lower half of the disc.

    A textPath does NOT survive export to DXF, which is why this exists.
    """
    raise NotImplementedError("Phase 5.")
