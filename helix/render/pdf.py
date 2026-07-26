"""RenderPlan -> PDF, using nothing but the standard library.

Single responsibility: serialise finished geometry as PDF. No trigonometry.

WHY NO DEPENDENCY: this is the format people print, email and take to a
framer, so it must work on a machine where nothing has been installed. PDF is
a simple enough container that writing it directly is less trouble than
carrying reportlab, and it means `helix render tree.pdf` works out of the box.

WHAT IT DOES
  * Real physical size. The MediaBox is the canvas in points (mm x 72/25.4),
    so the page measures exactly what the piece will measure.
  * Curves are flattened to polylines at 0.12 mm, which is finer than any
    printer resolves and matches what a laser receives.
  * Text uses the base-14 fonts, which need no embedding. Widths come from
    the real AFM metrics so centred and right-aligned text lands correctly.
  * Content streams are Flate-compressed, so a 900-shape chart is ~200 kB
    rather than several megabytes.
"""
from __future__ import annotations

import zlib
from pathlib import Path

from ..layout.plan import RenderPlan
from .pathflatten import flatten

MM_TO_PT = 72.0 / 25.4
FLATTEN_MM = 0.12

# Base-14 AFM advance widths, 1/1000 em, for ASCII 32..126.
_HELV = [278,278,355,556,556,889,667,191,333,333,389,584,278,333,278,278,
         556,556,556,556,556,556,556,556,556,556,278,278,584,584,584,556,
         1015,667,667,722,722,667,611,778,722,278,500,667,556,833,722,778,
         667,778,722,667,611,722,667,944,667,667,611,278,278,278,469,556,
         333,556,556,500,556,556,278,556,556,222,222,500,222,833,556,556,
         556,556,333,500,278,556,500,722,500,500,500,334,260,334,584]
_TIMES = [250,333,408,500,500,833,778,180,333,333,500,564,250,333,250,278,
          500,500,500,500,500,500,500,500,500,500,278,278,564,564,564,444,
          921,722,667,667,722,611,556,722,722,333,389,722,611,889,722,722,
          556,722,667,556,611,722,722,944,722,722,611,333,278,333,469,500,
          333,444,500,444,500,444,333,500,500,278,278,500,278,778,500,500,
          500,500,333,389,278,500,500,722,500,500,444,480,200,480,541]

# Characters we routinely emit that are not plain ASCII.
_WINANSI = {"\u2013": 150, "\u2014": 151, "\u2018": 145, "\u2019": 146,
            "\u201c": 147, "\u201d": 148, "\u2026": 133, "\u00b7": 183,
            "\u2265": 62, "\u2264": 60, "\u2192": 45, "\u00d7": 215}


def _font_for(family: str) -> tuple[str, str]:
    """Map a style's typeface to a base-14 font and its metric table."""
    f = (family or "").lower()
    if "mono" in f or "courier" in f or "menlo" in f:
        return "Courier", "mono"
    if any(k in f for k in ("serif", "georgia", "garamond", "times", "iowan",
                            "palatino", "cormorant")) and "sans" not in f:
        return "Times", "times"
    return "Helvetica", "helv"


def _text_width(text: str, size: float, metric: str) -> float:
    if metric == "mono":
        return len(text) * size * 0.6
    table = _TIMES if metric == "times" else _HELV
    total = 0
    for ch in text:
        o = ord(ch)
        total += table[o - 32] if 32 <= o <= 126 else 500
    return total * size / 1000.0


def _esc(text: str) -> str:
    out = []
    for ch in text:
        o = ord(ch)
        if ch in _WINANSI:
            o = _WINANSI[ch]
        elif o > 255:
            o = 63                                    # '?'
        if o in (0x28, 0x29, 0x5C):                   # ( ) \
            out.append("\\" + chr(o))
        elif 32 <= o <= 126:
            out.append(chr(o))
        else:
            out.append(f"\\{o:03o}")
    return "".join(out)


def _rgb(colour: str | None, default=(0, 0, 0)):
    if not colour or colour == "none":
        return default
    c = colour.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) < 6:
        return default
    try:
        return tuple(int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return default


def write(plan: RenderPlan, path: str | Path, *, production: bool = False,
          title: str = "") -> str:
    """Write `plan` to a PDF at true physical size."""
    path = Path(path)
    W = plan.canvas.width_mm * MM_TO_PT
    H = plan.canvas.height_mm * MM_TO_PT
    body = _content(plan, plan.canvas.height_mm, production)
    stream = zlib.compress(body.encode("latin-1", "replace"), 9)

    fonts = {"F1": "Helvetica", "F2": "Helvetica-Bold", "F3": "Times-Roman",
             "F4": "Times-Bold", "F5": "Courier"}
    objs: list[bytes] = []

    def add(b: str | bytes) -> int:
        objs.append(b.encode("latin-1") if isinstance(b, str) else b)
        return len(objs)

    font_ids = {}
    for key, name in fonts.items():
        font_ids[key] = add(f"<< /Type /Font /Subtype /Type1 /BaseFont /{name} "
                            f"/Encoding /WinAnsiEncoding >>")
    res = "/Font << " + " ".join(f"/{k} {font_ids[k]} 0 R" for k in fonts) + " >>"

    content_id = add(b"<< /Length " + str(len(stream)).encode() +
                     b" /Filter /FlateDecode >>\nstream\n" + stream +
                     b"\nendstream")
    pages_id = len(objs) + 2
    page_id = add(f"<< /Type /Page /Parent {pages_id} 0 R "
                  f"/MediaBox [0 0 {W:.3f} {H:.3f}] "
                  f"/Resources << {res} >> /Contents {content_id} 0 R >>")
    add(f"<< /Type /Pages /Kids [{page_id} 0 R] /Count 1 >>")
    cat_id = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")
    info_id = add(f"<< /Producer (Helix) /Title ({_esc(title or plan.meta.engine)}) "
                  f"/Creator (Helix {plan.meta.engine}/{plan.meta.style}) >>")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, o in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root {cat_id} 0 R "
            f"/Info {info_id} 0 R >>\nstartxref\n{xref}\n%%EOF\n").encode()
    path.write_bytes(bytes(out))
    return str(path)


def _content(plan: RenderPlan, height_mm: float, production: bool) -> str:
    """Build the page content stream. y is flipped: PDF counts up from the
    bottom, our plan counts down from the top."""
    def X(v):
        return v * MM_TO_PT

    def Y(v):
        return (height_mm - v) * MM_TO_PT

    ops: list[str] = []
    if not production:
        r, g, b = _rgb(plan.canvas.background, (1, 1, 1))
        ops.append(f"{r:.3f} {g:.3f} {b:.3f} rg 0 0 "
                   f"{X(plan.canvas.width_mm):.2f} {Y(0):.2f} re f")

    for el in plan.sorted_elements():
        if production and el.layer == "PRINT_ONLY":
            continue
        if el.opacity < 0.25:
            continue

        if el.kind == "text":
            ops.append(_text_ops(el, X, Y))
            continue

        ops.append("q")
        stroke = el.stroke
        fill = el.fill if el.fill and el.fill != "none" else None
        if stroke and stroke != "none":
            r, g, b = _rgb(stroke)
            ops.append(f"{r:.3f} {g:.3f} {b:.3f} RG")
            ops.append(f"{max(0.05, (el.stroke_width or 0.3)) * MM_TO_PT:.3f} w")
            ops.append("1 J 1 j")
        if fill:
            r, g, b = _rgb(fill)
            ops.append(f"{r:.3f} {g:.3f} {b:.3f} rg")
        if el.dash:
            segs = " ".join(f"{float(x) * MM_TO_PT:.2f}"
                            for x in el.dash.replace(",", " ").split())
            ops.append(f"[{segs}] 0 d")

        if el.kind == "circle":
            ops.append(_circle(X(el.x), Y(el.y), el.r * MM_TO_PT))
        elif el.kind == "rect":
            ops.append(f"{X(el.x):.3f} {Y(el.y + el.h):.3f} "
                       f"{el.w * MM_TO_PT:.3f} {el.h * MM_TO_PT:.3f} re")
        else:
            for pts, closed in flatten(el, FLATTEN_MM):
                if len(pts) < 2:
                    continue
                ops.append(f"{X(pts[0][0]):.3f} {Y(pts[0][1]):.3f} m")
                ops.extend(f"{X(x):.3f} {Y(y):.3f} l" for x, y in pts[1:])
                if closed:
                    ops.append("h")

        painted = bool(stroke and stroke != "none")
        if fill and painted:
            ops.append("B")
        elif fill:
            ops.append("f")
        elif painted:
            ops.append("S")
        else:
            ops.append("n")
        ops.append("Q")
    return "\n".join(ops)


def _circle(cx: float, cy: float, r: float) -> str:
    """Four cubic Béziers. k = 0.5523 is the classic circle approximation."""
    k = r * 0.5522847498
    return (f"{cx + r:.3f} {cy:.3f} m "
            f"{cx + r:.3f} {cy + k:.3f} {cx + k:.3f} {cy + r:.3f} {cx:.3f} {cy + r:.3f} c "
            f"{cx - k:.3f} {cy + r:.3f} {cx - r:.3f} {cy + k:.3f} {cx - r:.3f} {cy:.3f} c "
            f"{cx - r:.3f} {cy - k:.3f} {cx - k:.3f} {cy - r:.3f} {cx:.3f} {cy - r:.3f} c "
            f"{cx + k:.3f} {cy - r:.3f} {cx + r:.3f} {cy - k:.3f} {cx + r:.3f} {cy:.3f} c h")


def _text_ops(el, X, Y) -> str:
    import math
    f = el.font
    size_mm = f.size_mm if f else 3.0
    size = size_mm * MM_TO_PT
    base, metric = _font_for(f.family if f else "sans-serif")
    bold = bool(f and f.weight and f.weight >= 600)
    key = {("Helvetica", False): "F1", ("Helvetica", True): "F2",
           ("Times", False): "F3", ("Times", True): "F4",
           ("Courier", False): "F5", ("Courier", True): "F5"}[(base, bold)]

    text = el.text or ""
    w = _text_width(text, size, metric)
    anchor = (f.anchor if f else "middle")
    dx = {"start": 0.0, "end": -w, "middle": -w / 2}.get(anchor, -w / 2)
    dy = -size * 0.34                                   # central baseline

    r, g, b = _rgb(el.fill, (0, 0, 0))
    x, y = X(el.x), Y(el.y)
    a = math.radians(-(el.rotate or 0.0))               # PDF y is up: negate
    cos, sin = math.cos(a), math.sin(a)
    tx = x + dx * cos - dy * sin
    ty = y + dx * sin + dy * cos
    return (f"q BT {r:.3f} {g:.3f} {b:.3f} rg /{key} {size:.3f} Tf "
            f"{cos:.5f} {sin:.5f} {-sin:.5f} {cos:.5f} {tx:.3f} {ty:.3f} Tm "
            f"({_esc(text)}) Tj ET Q")
