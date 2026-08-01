"""Radius and position scales.

Single responsibility: map a generation number or a year to a coordinate.
"""
from __future__ import annotations

import math
from typing import Optional, Sequence


def r_generation(gen: int, ring_widths: Sequence[float], r0: float) -> float:
    return r0 + sum(ring_widths[:gen])


def ring_widths(counts: Sequence[int], r0: float, R: float,
                min_ring: float = 6.0) -> list[float]:
    """Choose ring widths so arc length per person stays roughly constant.

    Outer rings hold more people and have more circumference, so they can be
    thinner without losing legibility. Naive equal rings waste the middle of
    the disc and crush the rim.
    """
    n = len(counts)
    if n == 0:
        return []
    demand = [max(1, c) ** 0.5 for c in counts]
    total = sum(demand)
    avail = max(0.0, R - r0)
    widths = [max(min_ring, avail * d / total) for d in demand]
    scale = avail / sum(widths)
    return [w * scale for w in widths]


def r_time(t: float, t0: float, t1: float, r0: float, R: float,
           gamma: float = 0.5) -> float:
    """Map a year to a radius.

    gamma = 1.0  linear in time
    gamma = 0.5  EQUAL AREA -- every year gets the same amount of disc.
                 Because area grows as r^2, a linear scale crushes the recent,
                 populous generations into the crowded rim. This is the single
                 most useful correction in the whole layout system.
    """
    if t1 <= t0:
        return (r0 + R) / 2
    f = min(1.0, max(0.0, (t - t0) / (t1 - t0)))
    if abs(gamma - 1.0) < 1e-6:
        return r0 + f * (R - r0)
    p = 1.0 / max(1e-6, gamma) if gamma < 1 else gamma
    if abs(gamma - 0.5) < 1e-6:
        return math.sqrt(r0 * r0 + f * (R * R - r0 * r0))
    return r0 + (R - r0) * (f ** gamma)


def x_time(t: float, t0: float, t1: float, x0: float, x1: float) -> float:
    if t1 <= t0:
        return (x0 + x1) / 2
    f = min(1.0, max(0.0, (t - t0) / (t1 - t0)))
    return x0 + f * (x1 - x0)


def nice_ticks(t0: float, t1: float, target: int = 10) -> list[int]:
    """Round decade/half-century/century ticks across a date span."""
    span = max(1.0, t1 - t0)
    for step in (5, 10, 20, 25, 50, 100, 200, 250, 500):
        if span / step <= target:
            break
    start = int(math.floor(t0 / step) * step)
    return list(range(start, int(math.ceil(t1 / step) * step) + 1, step))
