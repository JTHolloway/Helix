"""Turn SVG path data into polylines.

Single responsibility: parse the small subset of SVG path syntax that this
program emits (M, L, H, V, A, C, Z, all absolute) and sample it to a tolerance.
Deliberately not a general SVG parser.
"""
from __future__ import annotations

import math
import re

TOKEN = re.compile(r"([MLHVACZmlhvacz])|(-?\d*\.?\d+(?:[eE][-+]?\d+)?)")


def flatten(el, tol: float = 0.05):
    """Yield (points, closed) for one element."""
    if el.kind == "rect":
        yield ([(el.x, el.y), (el.x + el.w, el.y),
                (el.x + el.w, el.y + el.h), (el.x, el.y + el.h)], True)
        return
    if not el.d:
        return
    yield from flatten_d(el.d, tol)


def flatten_d(d: str, tol: float = 0.05):
    """Absolute AND relative commands. Helix emits absolute, but a style or
    a hand-edited plan may not, and silently mis-drawing is worse than
    refusing."""
    cmds = _lex(d)
    pts: list[tuple[float, float]] = []
    cur = (0.0, 0.0)
    start = (0.0, 0.0)
    i = 0
    while i < len(cmds):
        op = cmds[i]
        if not isinstance(op, str):
            i += 1
            continue
        i += 1

        def take(n):
            nonlocal i
            vals = cmds[i:i + n]
            i += n
            return vals

        rel = op.islower()
        ox, oy = cur if rel else (0.0, 0.0)

        if op in "Mm":
            if pts:
                yield (pts, False)
                pts = []
            x, y = take(2)
            cur = start = (x + ox, y + oy)
            pts = [cur]
        elif op in "Ll":
            x, y = take(2)
            cur = (x + ox, y + oy)
            pts.append(cur)
        elif op in "Hh":
            x, = take(1)
            cur = (x + ox, cur[1])
            pts.append(cur)
        elif op in "Vv":
            y, = take(1)
            cur = (cur[0], y + oy)
            pts.append(cur)
        elif op in "Cc":
            x1, y1, x2, y2, x, y = take(6)
            pts.extend(_bezier(cur, (x1 + ox, y1 + oy), (x2 + ox, y2 + oy),
                               (x + ox, y + oy), tol)[1:])
            cur = (x + ox, y + oy)
        elif op in "Aa":
            rx, ry, rot, laf, sf, x, y = take(7)
            end = (x + ox, y + oy)
            pts.extend(_arc(cur, rx, ry, rot, laf, sf, end, tol)[1:])
            cur = end
        elif op in "Zz":
            if pts:
                yield (pts, True)
                pts = []
            cur = start
    if pts:
        yield (pts, False)


def _lex(d: str):
    out = []
    for m in TOKEN.finditer(d):
        out.append(m.group(1) if m.group(1) else float(m.group(2)))
    return out


def _bezier(p0, p1, p2, p3, tol):
    chord = math.dist(p0, p3) + math.dist(p0, p1) + math.dist(p1, p2) + math.dist(p2, p3)
    n = max(4, min(120, int(math.sqrt(chord / max(tol, 1e-4)) * 2)))
    out = []
    for k in range(n + 1):
        t = k / n
        u = 1 - t
        out.append((u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                    u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]))
    return out


def _arc(p0, rx, ry, rot, laf, sf, p1, tol):
    """SVG elliptical arc -> polyline (endpoint parameterisation, W3C F.6.5)."""
    if rx == 0 or ry == 0 or p0 == p1:
        return [p0, p1]
    phi = math.radians(rot)
    dx2, dy2 = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1 = math.cos(phi) * dx2 + math.sin(phi) * dy2
    y1 = -math.sin(phi) * dx2 + math.cos(phi) * dy2
    rx, ry = abs(rx), abs(ry)
    lam = x1 * x1 / (rx * rx) + y1 * y1 / (ry * ry)
    if lam > 1:
        rx *= math.sqrt(lam)
        ry *= math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    c = math.sqrt(max(0.0, num / den)) * (-1 if laf == sf else 1)
    cx1, cy1 = c * rx * y1 / ry, -c * ry * x1 / rx
    cx = math.cos(phi) * cx1 - math.sin(phi) * cy1 + (p0[0] + p1[0]) / 2
    cy = math.sin(phi) * cx1 + math.cos(phi) * cy1 + (p0[1] + p1[1]) / 2
    th0 = math.atan2((y1 - cy1) / ry, (x1 - cx1) / rx)
    th1 = math.atan2((-y1 - cy1) / ry, (-x1 - cx1) / rx)
    dth = th1 - th0
    if sf == 0 and dth > 0:
        dth -= 2 * math.pi
    if sf == 1 and dth < 0:
        dth += 2 * math.pi
    n = max(4, min(240, int(abs(dth) * max(rx, ry) / max(tol, 1e-4) ** 0.5)))
    out = []
    for k in range(n + 1):
        t = th0 + dth * k / n
        x = math.cos(phi) * rx * math.cos(t) - math.sin(phi) * ry * math.sin(t) + cx
        y = math.sin(phi) * rx * math.cos(t) + math.cos(phi) * ry * math.sin(t) + cy
        out.append((x, y))
    return out
