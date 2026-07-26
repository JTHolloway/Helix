"""Clock movement fitting.

Turning the chart into a working clock is the detail that makes people pick
it up. The geometry is unforgiving, so it is worth getting exactly right.

STANDARD QUARTZ MOVEMENT
  Shaft diameter      6.0-8.0 mm  (8.0 covers almost everything)
  Shaft length        must exceed material thickness + 5 mm for the nut
  Body                56 x 56 x 16 mm typical -- recess or stand the piece off
  Hand length         over 150 mm needs a HIGH TORQUE movement
  Hanger              keyhole slot, 4 mm wide, 8 mm tall, 12 mm above centre

WHAT THIS MODULE ADDS TO THE PLAN
  bore        circle on CUT, radius = shaft_d/2 + kerf/2
  recess      optional square on ENGRAVE_DEEP for the body
  hour marks  12 ticks on ENGRAVE, or the decade labels already on the chart
  keyhole     on the back plate if a two-layer sandwich is being made

DESIGN RULE
  Reserve inner_radius_mm >= 45 for any clock, and align generation sectors to
  clock hours (multiples of 30 degrees) so the hands never obscure a name
  the user cares about. `snap_sectors_to_hours()` does this by nudging the
  start angle to the nearest 30-degree boundary.
"""
from __future__ import annotations

SHAFT_D_MM = 8.0
MIN_INNER_RADIUS_MM = 45.0
HIGH_TORQUE_ABOVE_MM = 150.0


def add_clock(plan, style, cx: float, cy: float) -> None:
    raise NotImplementedError(
        "Clock fitting is Phase 6. The numbers above are correct and tested; "
        "in the meantime, cut a bore of 8.0 mm diameter at the exact centre."
    )


def snap_sectors_to_hours(start_angle_deg: float) -> float:
    return round(start_angle_deg / 30.0) * 30.0
