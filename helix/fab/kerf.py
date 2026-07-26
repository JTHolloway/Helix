"""Kerf compensation.

The beam removes material, so a 50 mm hole cut on the line comes out about
50.2 mm and a 50 mm disc comes out about 49.8 mm. For decorative charts this
rarely matters; for anything that must FIT -- a clock bore, a two-material
inlay, interlocking tiles -- it matters completely.

ALGORITHM (Phase 4, needs pyclipper or shapely):
  offset = kerf_mm / 2
  outer boundaries  -> buffer(+offset)
  inner holes       -> buffer(-offset)
  Use mitre joins with a limit of 2.0 so corners stay sharp; round joins
  visibly soften small text counters.

Always confirm with a test strip: cut five 20 mm squares at different offsets,
measure with callipers, and pick the one that reads 20.0.
"""
from __future__ import annotations


def compensate(plan, kerf_mm: float, *, layers=("CUT",)):
    raise NotImplementedError(
        "Kerf compensation is Phase 4 and needs pyclipper:\n"
        "    pip install pyclipper\n"
        "Most laser software (LightBurn: Cut Settings > Kerf Offset) can do "
        "this at the machine instead."
    )
