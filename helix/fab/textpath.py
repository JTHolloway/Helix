"""Text -> geometry. What makes `--production` a file you can actually cut.

WHY THIS MATTERS: laser and CNC software has no access to your fonts. A file
with live text in it either fails to import or silently substitutes something
else, and you find out after forty minutes of cutting. Every production
export must carry its text as geometry.

Two routes:
  (a) outline fonts -- faithful to the typeface, but each letter engraves as
      two closed contours that the machine has to fill. Slow, and below about
      3 mm the counters fill in and the word turns into a smudge. Needs
      fontTools, which Helix does not require, so it is offered and not
      assumed.
  (b) single-line "stroke" fonts -- one centreline pass per letter. Three to
      five times faster on the machine, crisp at 2 mm, and it looks like
      engraving instead of like printing. This is the default, and it is
      built in: `strokefont.py`.

Drop a Hershey JSON into `hershey/` and it wins over the built-in face. The
format is in `hershey/README.md`; both the old flat form and the richer form
`strokefont.face()` returns are read.

COORDINATES. Faces are drawn with y UP and the baseline at zero, which is how
type has always been described and how the Hershey data is stored. Plans are
in SVG coordinates, y DOWN. The flip happens once, here, in `_place`.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from . import strokefont

HERSHEY_DIR = Path(__file__).with_name("hershey")

_CACHE: dict[str, dict] = {}


def load_face(name: str = "") -> dict:
    """The stroke face to engrave with.

    A JSON in `hershey/` wins if there is one -- that is how somebody swaps in
    a Hershey script for a cartouche. Otherwise the built-in face, which is
    always there, because a program that installs nothing cannot have a
    missing font be the reason a chart does not cut.
    """
    key = name or "*"
    if key in _CACHE:
        return _CACHE[key]
    found = None
    if HERSHEY_DIR.is_dir():
        files = sorted(HERSHEY_DIR.glob("*.json"))
        if name:
            files = [p for p in files if name.lower() in p.stem.lower()] or files
        for p in files:
            try:
                found = _normalise(json.loads(p.read_text()))
                break
            except (ValueError, KeyError, TypeError):
                continue          # a broken face is not a reason to stop
    face = found or strokefont.face()
    _CACHE[key] = face
    return face


def _normalise(raw: dict) -> dict:
    """Accept both file shapes.

    The README documents the flat one, `{"A": [[[x,y],...], ...]}`, which has
    no advance widths -- so they are measured from the ink and padded, which
    is what the Hershey data itself does.
    """
    if "glyphs" in raw:
        return raw
    glyphs = {}
    for ch, strokes in raw.items():
        xs = [p[0] for s in strokes for p in s] or [0.0]
        glyphs[ch] = {"advance": max(xs) - min(0.0, min(xs)) + 4.0,
                      "strokes": [[list(p) for p in s] for s in strokes]}
    return {"name": "hershey", "cap": 21.0, "xheight": 14.0, "descender": -7.0,
            "glyphs": glyphs, "fold": dict(strokefont._FOLD)}


def _glyph(face: dict, ch: str):
    g = face["glyphs"].get(ch)
    if g is not None:
        return [(ch, g)]
    sub = face.get("fold", {}).get(ch)
    if sub is not None:
        return [x for c in sub for x in _glyph(face, c)]
    # Never silently drop a character: a name with a box in it is a bug you
    # can see, and a name quietly missing a letter is one you cannot.
    box = face["glyphs"].get("?")
    return [("?", box)] if box else []


def measure(text: str, size_mm: float, face: dict | None = None) -> float:
    """Width of `text` when engraved, in millimetres."""
    face = face or load_face()
    k = size_mm / face.get("cap", 21.0)
    return sum(g["advance"] for ch in text for _, g in _glyph(face, ch)) * k


def stroke_paths(text: str, size_mm: float, x: float, y: float,
                 rotate: float = 0.0, anchor: str = "middle",
                 face: dict | None = None) -> list[str]:
    """Single-stroke engraving text, as SVG path strings in plan coordinates.

    `x, y` and `anchor` mean what they mean on an SVG <text>: the anchor point
    and which end of the line sits on it. `rotate` is degrees clockwise about
    that point, as in the transform the renderers already write, so a label
    converted to strokes lands exactly where the live text was.

    Vertically it matches `dominant-baseline: central`, which is what every
    renderer here sets -- the middle of the cap height on the anchor, not the
    baseline. Getting this wrong shifts every name up by half a line and the
    error is invisible until it is cut.
    """
    face = face or load_face()
    k = size_mm / face.get("cap", 21.0)
    run = [g for ch in text for _, g in _glyph(face, ch)]
    width = sum(g["advance"] for g in run) * k
    dx = {"start": 0.0, "middle": -width / 2, "end": -width}.get(anchor, -width / 2)
    dy = face.get("cap", 21.0) / 2 * k          # central, not baseline

    ca, sa = math.cos(math.radians(rotate)), math.sin(math.radians(rotate))

    def place(px, py):
        # face space (y up, baseline 0) -> anchored, then rotated about x, y
        u, v = dx + px * k, dy - py * k
        return (x + u * ca - v * sa, y + u * sa + v * ca)

    out: list[str] = []
    pen = 0.0
    for g in run:
        for s in g["strokes"]:
            pts = [place(pen + p[0], p[1]) for p in s]
            out.append("M" + " L".join(f"{a:.4g},{b:.4g}" for a, b in pts))
        pen += g["advance"]
    return out


def hershey_paths(text: str, size_mm: float, x: float, y: float,
                  rotate: float = 0.0) -> list[str]:
    """The name this had before there was a face built in. Same thing."""
    return stroke_paths(text, size_mm, x, y, rotate)


def to_strokes(el, face: dict | None = None) -> list[str]:
    """Convert one text Element to path data. Returns [] if it is not text."""
    if el.kind != "text" or not el.text:
        return []
    f = el.font
    return stroke_paths(el.text, f.size_mm if f else 3.0, el.x, el.y,
                        el.rotate or 0.0,
                        (f.anchor if f else "middle"), face)


def bake(plan, style=None, *, hairline_mm: float = 0.0):
    """Replace every text element on the plan with engravable geometry.

    Plan in, plan out -- the same plan, so every writer benefits and none of
    them has to know how a letter is made. This is the step that makes
    `--production` a file you can send to the machine without opening it in
    LightBurn first and hoping nothing reflowed.

    Each label becomes one path per stroke, inheriting the label's colour,
    layer and provenance, so hover, search and the person-to-element mapping
    all survive the conversion.
    """
    face = load_face(str((style.get("type.engrave_face", "")) if style else ""))
    if style is not None and not style.get("production.text_to_paths", True):
        return plan
    # NOT the hairline. A single-stroke letter is a path the beam
    # follows; the width is only how thick it looks on screen, and
    # at 0.05 mm the pre-flight rightly called every name invisible.
    width = hairline_mm or (style.get("production.engrave_stroke_mm", 0.25)
                            if style is not None else 0.25)
    kept, made = [], 0
    for el in plan.elements:
        if el.kind != "text" or not el.text:
            kept.append(el)
            continue
        for d in to_strokes(el, face):
            kept.append(_as_path(el, d, width))
            made += 1
    plan.elements = kept
    plan.meta.extra["text_to_paths"] = {"face": face.get("name", "?"),
                                        "strokes": made}
    return plan


def _as_path(el, d: str, width: float):
    from ..layout.plan import Element
    return Element(kind="path", layer=el.layer, d=d, fill="none",
                   stroke=el.fill or "#000000",
                   stroke_width=max(width, 0.05), opacity=el.opacity,
                   person_id=el.person_id, union_id=el.union_id,
                   role=el.role, line_id=el.line_id, z=el.z)


def glyph_outlines(text: str, size_mm: float, x: float, y: float,
                   rotate: float = 0.0, family: str = "",
                   anchor: str = "middle"):
    """Filled letter shapes from a real TTF/OTF, for when faithful beats fast.

    Optional: it needs fontTools, which Helix does not require. If it is not
    installed the caller gets the stroke face instead and a note saying why,
    rather than a traceback -- an export must not fail because of a font.
    """
    try:
        from fontTools.pens.svgPathPen import SVGPathPen   # noqa: F401
        from fontTools.ttLib import TTFont                 # noqa: F401
    except ImportError:
        return stroke_paths(text, size_mm, x, y, rotate, anchor), (
            "Outline text needs fontTools (pip install fonttools). Engraved "
            "with the built-in single-stroke face instead, which cuts three "
            "to five times faster anyway.")
    raise NotImplementedError(
        "Outline baking from a system font is not built. Use the stroke face, "
        "which is the right answer for engraving, or convert to paths in your "
        "laser software.")


def text_along_arc(text: str, cx: float, cy: float, radius: float,
                   theta_centre: float, size_mm: float, flip: bool = False,
                   face: dict | None = None) -> list[str]:
    """Place each glyph individually around a circle.

    A `textPath` does not survive export to DXF, which is why this exists: the
    letters are laid out here, one at a time, and come out as plain geometry.
    """
    face = face or load_face()
    k = size_mm / face.get("cap", 21.0)
    run = [g for ch in text for _, g in _glyph(face, ch)]
    width = sum(g["advance"] for g in run) * k
    t = theta_centre - (width / max(radius, 1e-6)) / 2 * (-1 if flip else 1)
    out: list[str] = []
    for g in run:
        w = g["advance"] * k
        step = w / max(radius, 1e-6)
        mid = t + step / 2 * (-1 if flip else 1)
        deg = math.degrees(mid) + (90 if not flip else -90)
        out += stroke_paths_glyph(g, size_mm, cx + radius * math.cos(mid),
                                  cy + radius * math.sin(mid), deg, face)
        t += step * (-1 if flip else 1)
    return out


def stroke_paths_glyph(g, size_mm, x, y, rotate, face) -> list[str]:
    """One already-resolved glyph, centred on (x, y). Used by the arc setter."""
    k = size_mm / face.get("cap", 21.0)
    dx, dy = -g["advance"] * k / 2, face.get("cap", 21.0) / 2 * k
    ca, sa = math.cos(math.radians(rotate)), math.sin(math.radians(rotate))
    out = []
    for s in g["strokes"]:
        pts = []
        for p in s:
            u, v = dx + p[0] * k, dy - p[1] * k
            pts.append((x + u * ca - v * sa, y + u * sa + v * ca))
        out.append("M" + " L".join(f"{a:.4g},{b:.4g}" for a, b in pts))
    return out
