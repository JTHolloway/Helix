"""A single-stroke engraving face, built into the program.

WHY THIS EXISTS. Laser and CNC software cannot see your fonts, so every
production file has to carry its text as geometry. There are two ways to do
that and only one of them is any good on plywood:

    OUTLINES    the shape of each letter, as two closed contours. Faithful to
                the typeface, and the machine has to fill between them --
                slow, and below about 3 mm the counters fill in and the word
                turns into a smudge.
    CENTRELINES one pass down the middle of each stroke. Three to five times
                faster on the machine, crisp at 2 mm, and it looks like
                engraving rather than like printing.

This is the second kind. It is drawn here rather than loaded because Helix
installs nothing: a face that arrives with the program cannot be the missing
piece that stops somebody cutting their chart on a Sunday.

`hershey/*.json` still wins if it is there -- see `textpath.load_face`. The
coordinate space is the same one the Hershey data uses, so the two are
interchangeable: baseline at y = 0, y increasing UPWARD, cap height 21,
x-height 14, descender -7. Each glyph is a list of strokes and each stroke a
list of [x, y] points, plus an advance width.

Curves are described as elliptical arcs and flattened when the face is built,
so the letters are actually round rather than round-ish, and the flattening
tolerance is in one place.
"""
from __future__ import annotations

import math

# cap 21, x-height 14, baseline 0, descender -7. One unit is cap/21.
CAP = 21.0
XH = 14.0
DESC = -7.0

# How finely an arc is flattened, in units. 0.35 of 21 is about a sixth of a
# millimetre at 10 mm type -- below what the beam can resolve.
_TOL = 0.35


def _arc(cx, cy, rx, ry, a0, a1):
    """An elliptical arc, in degrees, anticlockwise from a0 to a1."""
    span = abs(a1 - a0)
    r = max(rx, ry)
    # enough segments that the sagitta stays under the tolerance
    step = 2 * math.degrees(math.acos(max(-1.0, min(1.0, 1 - _TOL / max(r, 0.1)))))
    n = max(4, int(math.ceil(span / max(step, 4.0))))
    out = []
    for i in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * i / n)
        out.append([cx + rx * math.cos(a), cy + ry * math.sin(a)])
    return out


def _line(*pts):
    return [list(p) for p in pts]


# ---------------------------------------------------------------- glyphs --
#
# (advance, [stroke, ...]). Written at the size they are drawn, so a glyph
# can be checked by reading its numbers: "A" is two diagonals and a crossbar.
_G: dict[str, tuple[float, list]] = {}


def _put(ch, advance, *strokes):
    _G[ch] = (advance, [s for s in strokes if len(s) > 1])


# --- upper case -------------------------------------------------------------
_put("A", 16, _line((0, 0), (7, 21), (14, 0)), _line((3, 7), (11, 7)))
_put("B", 16, _line((0, 0), (0, 21), (8, 21)),
     _arc(8, 16.2, 5, 4.8, 90, -90) + _line((0, 11.4)),
     _arc(8.5, 5.7, 5.5, 5.7, 90, -90) + _line((0, 0)))
_put("C", 16, _arc(7.5, 10.5, 7.5, 10.5, 50, 310))
_put("D", 16, _line((0, 0), (0, 21), (6, 21)),
     _arc(6, 10.5, 8, 10.5, 90, -90) + _line((0, 0)))
_put("E", 14, _line((12, 21), (0, 21), (0, 0), (12, 0)), _line((0, 11), (9, 11)))
_put("F", 13, _line((12, 21), (0, 21), (0, 0)), _line((0, 11.5), (9, 11.5)))
_put("G", 17, _arc(7.5, 10.5, 7.5, 10.5, 50, 310) + _line((15, 8), (10, 8)))
_put("H", 16, _line((0, 0), (0, 21)), _line((14, 0), (14, 21)),
     _line((0, 11), (14, 11)))
_put("I", 6, _line((3, 0), (3, 21)))
_put("J", 13, _line((10, 21), (10, 5)) + _arc(5, 5, 5, 5, 0, -180))
_put("K", 15, _line((0, 0), (0, 21)), _line((13, 21), (1, 9)), _line((4.5, 12), (14, 0)))
_put("L", 13, _line((0, 21), (0, 0), (12, 0)))
_put("M", 19, _line((0, 0), (0, 21), (8.5, 4), (17, 21), (17, 0)))
_put("N", 17, _line((0, 0), (0, 21), (14, 0), (14, 21)))
_put("O", 18, _arc(8, 10.5, 8, 10.5, 0, 360))
_put("P", 15, _line((0, 0), (0, 21), (7, 21)),
     _arc(7, 15.8, 6, 5.2, 90, -90) + _line((0, 10.6)))
_put("Q", 18, _arc(8, 10.5, 8, 10.5, 0, 360), _line((10, 5), (17, -3)))
_put("R", 16, _line((0, 0), (0, 21), (7, 21)),
     _arc(7, 15.8, 6, 5.2, 90, -90) + _line((0, 10.6)), _line((6, 10.6), (14, 0)))
_put("S", 15, _arc(7, 15.7, 6.4, 5.3, 65, 250) + _arc(7, 5.6, 6.6, 5.6, 110, -110))
_put("T", 14, _line((0, 21), (14, 21)), _line((7, 21), (7, 0)))
_put("U", 16, _line((0, 21), (0, 6)) + _arc(7, 6, 7, 6, 180, 360) + _line((14, 21)))
_put("V", 15, _line((0, 21), (7.5, 0), (15, 21)))
_put("W", 22, _line((0, 21), (5, 0), (11, 16), (17, 0), (22, 21)))
_put("X", 15, _line((0, 0), (14, 21)), _line((0, 21), (14, 0)))
_put("Y", 15, _line((0, 21), (7, 10), (14, 21)), _line((7, 10), (7, 0)))
_put("Z", 15, _line((0, 21), (14, 21), (0, 0), (14, 0)))

# --- lower case -------------------------------------------------------------
# The bowls of a b d g p q are one circle, the same circle as "o", with the
# stem set where the circle already ends. Drawn as half-arcs joined to the
# stem they came out looking like "cl" -- two marks that happen to be near
# each other, which is exactly what a name must never do.
_put("a", 14, _arc(6, 7, 6, 7, 0, 360), _line((12, 14), (12, 0)))
_put("b", 14, _line((0, 21), (0, 0)), _arc(6, 7, 6, 7, 0, 360))
_put("c", 13, _arc(6.5, 7, 6.5, 7, 55, 305))
_put("d", 14, _line((12, 21), (12, 0)), _arc(6, 7, 6, 7, 0, 360))
_put("e", 13, _line((0.4, 6.5), (13, 6.5)) + _arc(6.5, 7, 6.5, 7, 0, 305))
_put("f", 9, _arc(7.5, 18.5, 4.5, 4.5, 0, 130) + _line((3, 0)), _line((0, 13.5), (9, 13.5)))
_put("g", 14, _arc(6, 7, 6, 7, 0, 360),
     _line((12, 14), (12, -3)) + _arc(7, -3, 5, 4, 0, -150))
_put("h", 14, _line((0, 21), (0, 0)),
     _arc(6, 8, 6, 6, 180, 0) + _line((12, 0)))
_put("i", 6, _line((3, 14), (3, 0)), _line((3, 18), (3, 19.5)))
_put("j", 7, _line((4, 14), (4, -2)) + _arc(0, -2, 4, 4, 0, -95),
     _line((4, 18), (4, 19.5)))
_put("k", 13, _line((0, 21), (0, 0)), _line((11, 14), (1, 5)), _line((4, 7.6), (12, 0)))
_put("l", 6, _line((3, 21), (3, 0)))
_put("m", 21, _line((0, 14), (0, 0)), _arc(5, 8, 5, 6, 180, 0) + _line((10, 0)),
     _arc(15, 8, 5, 6, 180, 0) + _line((20, 0)))
_put("n", 14, _line((0, 14), (0, 0)), _arc(6, 8, 6, 6, 180, 0) + _line((12, 0)))
_put("o", 14, _arc(6.5, 7, 6.5, 7, 0, 360))
_put("p", 14, _line((0, 14), (0, -7)), _arc(6, 7, 6, 7, 0, 360))
_put("q", 14, _line((12, 14), (12, -7)), _arc(6, 7, 6, 7, 0, 360))
_put("r", 10, _line((0, 14), (0, 0)), _arc(5.5, 9, 5.5, 5, 180, 40))
_put("s", 12, _arc(5.5, 10.6, 5, 3.4, 60, 250) + _arc(5.5, 3.8, 5.3, 3.8, 110, -110))
_put("t", 9, _line((3, 21), (3, 3)) + _arc(6.5, 3, 3.5, 3, 180, 280),
     _line((0, 14), (8, 14)))
_put("u", 14, _line((0, 14), (0, 6)) + _arc(6, 6, 6, 6, 180, 360) + _line((12, 14)),
     _line((12, 8), (12, 0)))
_put("v", 13, _line((0, 14), (6.5, 0), (13, 14)))
_put("w", 19, _line((0, 14), (4.5, 0), (9.5, 10), (14.5, 0), (19, 14)))
_put("x", 13, _line((0, 0), (12, 14)), _line((0, 14), (12, 0)))
_put("y", 13, _line((0, 14), (6.5, 0)), _line((13, 14), (4, -7)))
_put("z", 12, _line((0, 14), (11, 14), (0, 0), (11, 0)))

# --- digits -----------------------------------------------------------------
_put("0", 15, _arc(7, 10.5, 7, 10.5, 0, 360))
_put("1", 15, _line((2.5, 17), (7, 21), (7, 0)))
_put("2", 15, _arc(7, 15.5, 6.5, 5.5, 175, -50) + _line((0, 0), (13.5, 0)))
_put("3", 15, _arc(6.8, 15.8, 6, 5.2, 160, -95),
     _arc(6.8, 5.6, 6.8, 5.6, 105, -170))
_put("4", 15, _line((10, 0), (10, 21), (0, 6.5), (14, 6.5)))
_put("5", 15, _line((13, 21), (2.5, 21), (1.6, 11.6)),
     _arc(7, 6, 7, 6, 105, -125))
_put("6", 15, _arc(7, 6.5, 6.8, 6.5, 0, 360),
     _arc(9, 9.5, 9, 11.5, 100, 175))
_put("7", 15, _line((0, 21), (14, 21), (5, 0)))
_put("8", 15, _arc(7, 16, 5.6, 5, 0, 360), _arc(7, 5.9, 6.6, 5.9, 0, 360))
_put("9", 15, _arc(7, 14.5, 6.8, 6.5, 0, 360),
     _arc(5, 11.5, 9, 11.5, -80, -5))

# --- punctuation ------------------------------------------------------------
_put(" ", 9)
_put(".", 7, _line((2.5, 0), (3.5, 0), (3.5, 1), (2.5, 1), (2.5, 0)))
_put(",", 7, _line((4, 1), (3, 1), (3, 0), (4, 0), (4, -2), (2, -3.6)))
_put(":", 7, _line((2.5, 0), (3.5, 0), (3.5, 1), (2.5, 1), (2.5, 0)),
     _line((2.5, 9), (3.5, 9), (3.5, 10), (2.5, 10), (2.5, 9)))
_put(";", 8, _line((2.5, 9), (3.5, 9), (3.5, 10), (2.5, 10), (2.5, 9)),
     _line((4, 1), (3, 1), (3, 0), (4, 0), (4, -2), (2, -3.6)))
_put("-", 11, _line((1.5, 9), (9.5, 9)))
_put("–", 14, _line((1, 9), (13, 9)))          # en dash, for date ranges
_put("—", 20, _line((1, 9), (19, 9)))          # em dash
_put("’", 6, _line((3, 21), (2, 17)))          # right single quote
_put("'", 5, _line((2.5, 21), (2.5, 16)))
_put('"', 8, _line((2, 21), (2, 16)), _line((6, 21), (6, 16)))
_put("(", 8, _arc(8.5, 10.5, 8, 12, 140, 220))
_put(")", 8, _arc(-0.5, 10.5, 8, 12, 40, -40))
_put("[", 8, _line((6, 22), (2, 22), (2, -2), (6, -2)))
_put("]", 8, _line((2, 22), (6, 22), (6, -2), (2, -2)))
_put("/", 11, _line((0, -2), (10, 22)))
_put("\\", 11, _line((0, 22), (10, -2)))
_put("?", 13, _arc(6, 15.6, 5.6, 5.4, 180, -55) + _line((6, 6)),
     _line((5.5, 0), (6.5, 0), (6.5, 1), (5.5, 1), (5.5, 0)))
_put("!", 6, _line((3, 21), (3, 5)),
     _line((2.5, 0), (3.5, 0), (3.5, 1), (2.5, 1), (2.5, 0)))
_put("&", 19, _line((17, 4.5), (14, 1), (10, 0), (5, 0), (1, 3), (1, 8),
                    (5, 12), (9, 15), (10, 17.5), (9, 20), (6.5, 20.8),
                    (4.5, 19), (4.5, 16.5), (6, 13.5), (16.5, 0)))
_put("*", 11, _line((5, 21), (5, 13)), _line((1.5, 19), (8.5, 15)),
     _line((8.5, 19), (1.5, 15)))
_put("+", 15, _line((1, 10), (13, 10)), _line((7, 4), (7, 16)))
_put("=", 15, _line((1, 12), (13, 12)), _line((1, 7), (13, 7)))
_put("#", 16, _line((4, 0), (6, 21)), _line((10, 0), (12, 21)),
     _line((1, 7), (14, 7)), _line((2, 14), (15, 14)))
_put("%", 19, _line((1, 0), (18, 21)), _arc(4.5, 16.5, 4, 4.5, 0, 360),
     _arc(14.5, 4.5, 4, 4.5, 0, 360))
_put("@", 21, _arc(10, 10.5, 4.5, 4.5, -40, 250)
     + _line((15, 8)) + _arc(10, 10.5, 10, 10.5, 0, 320))
_put("_", 15, _line((0, -4), (14, -4)))
_put("·", 7, _line((2.5, 8), (3.5, 8), (3.5, 9), (2.5, 9), (2.5, 8)))

# Accented letters are folded to their base letter rather than dropped: a
# name is more wrong without its letters than without its accents, and
# silently losing a character is the one thing this must not do.
_FOLD = {
    "À": "A", "Á": "A", "Â": "A", "Ã": "A", "Ä": "A",
    "Å": "A", "Ç": "C", "È": "E", "É": "E", "Ê": "E",
    "Ë": "E", "Ì": "I", "Í": "I", "Î": "I", "Ï": "I",
    "Ñ": "N", "Ò": "O", "Ó": "O", "Ô": "O", "Õ": "O",
    "Ö": "O", "Ø": "O", "Ù": "U", "Ú": "U", "Û": "U",
    "Ü": "U", "Ý": "Y",
    "à": "a", "á": "a", "â": "a", "ã": "a", "ä": "a",
    "å": "a", "ç": "c", "è": "e", "é": "e", "ê": "e",
    "ë": "e", "ì": "i", "í": "i", "î": "i", "ï": "i",
    "ñ": "n", "ò": "o", "ó": "o", "ô": "o", "õ": "o",
    "ö": "o", "ø": "o", "ù": "u", "ú": "u", "û": "u",
    "ü": "u", "ý": "y", "ÿ": "y",
        # Ligatures, and the letters English lost. Two letters is closer to
    # somebody's name than one box is.
    "Æ": "AE", "æ": "ae", "Œ": "OE", "œ": "oe", "ß": "ss",
    "Þ": "Th", "þ": "th", "Ð": "D", "ð": "d",
    "Ł": "L", "ł": "l", "Š": "S", "š": "s",
    "Ž": "Z", "ž": "z", "Ć": "C", "ć": "c",
    "Č": "C", "č": "c", "Ś": "S", "ś": "s",
    "Ź": "Z", "ź": "z", "Ż": "Z", "ż": "z",
    "Ą": "A", "ą": "a", "Ę": "E", "ę": "e",
    "Ń": "N", "ń": "n", "Ā": "A", "ā": "a",
    "Ē": "E", "ē": "e", "Ū": "U", "ū": "u",
    "’": "’", "–": "–", "—": "—",
    "−": "-", "‑": "-", " ": " ", " ": " ",
"‘": "'", "“": '"', "”": '"', "…": "...",
    " ": " ",
}


def face() -> dict:
    """The built-in face, in the same shape as a `hershey/*.json` file."""
    return {"name": "helix-stroke", "cap": CAP, "xheight": XH,
            "descender": DESC,
            "glyphs": {ch: {"advance": adv, "strokes": strokes}
                       for ch, (adv, strokes) in _G.items()},
            "fold": dict(_FOLD)}
