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


def add_clock(plan, style, cx: float, cy: float) -> list[str]:
    """Cut the bore a clock movement needs, at the exact centre.

    A FAMILY TREE THAT IS ALSO A CLOCK is the commonest thing anybody asks
    this program for, and it needs one hole and two warnings. The hole is
    8 mm: every quartz movement sold for a wooden face has a shaft that
    diameter, and the ones that do not come with a bush that takes it there.

    Returns whatever the person needs to be told before they press go. It
    returns rather than raising, because a chart with a clock in it is still
    a chart -- the warnings belong beside the piece, not in place of it.
    """
    from ..layout.plan import Element

    warn: list[str] = []
    d = float(style.get("fab.clock_shaft_mm", SHAFT_D_MM))
    r = d / 2.0
    inner = float(style.get("layout.inner_radius_mm", 0) or 0)
    if inner and inner < MIN_INNER_RADIUS_MM:
        warn.append(
            f"The hole in the middle is {inner:.0f} mm across and a movement "
            f"needs {MIN_INNER_RADIUS_MM:.0f} mm of clear board round the "
            f"shaft. Widen 'Hole in the middle' to at least "
            f"{MIN_INNER_RADIUS_MM:.0f} mm, or the hands will foul the "
            f"innermost names.")
    span = max(float(plan.canvas.width_mm), float(plan.canvas.height_mm))
    if span > HIGH_TORQUE_ABOVE_MM * 2:
        warn.append(
            f"At {span:.0f} mm across the hands are long and heavy. Ask for "
            f"a high-torque movement — an ordinary one stalls at about "
            f"{HIGH_TORQUE_ABOVE_MM:.0f} mm of hand.")

    # ON THE CUT LAYER, and drawn as two arcs rather than one circle: a full
    # circle written as a single arc command has coincident start and end
    # points, which some controllers read as a zero-length move and skip.
    for a0, a1 in ((0.0, 180.0), (180.0, 360.0)):
        import math
        x0, y0 = cx + r * math.cos(math.radians(a0)), cy + r * math.sin(math.radians(a0))
        x1, y1 = cx + r * math.cos(math.radians(a1)), cy + r * math.sin(math.radians(a1))
        plan.add(Element(
            kind="path", layer="CUT",
            d=f"M {x0:.4f},{y0:.4f} A {r:.4f},{r:.4f} 0 0 1 {x1:.4f},{y1:.4f}",
            stroke="#D22", stroke_width=0.1, fill="none",
            role="clock_bore", z=95))
    plan.meta.extra["clock"] = {"shaft_mm": d, "warnings": warn}
    return warn


def snap_sectors_to_hours(start_angle_deg: float) -> float:
    return round(start_angle_deg / 30.0) * 30.0
