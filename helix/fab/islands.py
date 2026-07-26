"""Island detection and automatic bridging.

THE PROBLEM this solves: any closed cut path creates a piece that falls out
of the sheet. The inside of an 'O', the middle of a ring, a fully enclosed
cell -- all of them drop onto the honeycomb and are lost. Nothing warns you
until the job finishes.

ALGORITHM (Phase 4, needs shapely):
  1. Collect every polygon from the CUT layer via render.pathflatten.
  2. Build a shapely MultiPolygon; the sheet is the outer boundary.
  3. supported = unary_union of everything connected to the outer boundary;
     islands = the polygons not in that union.
  4. For each island, find the shortest segment to any supported geometry
     using shapely.ops.nearest_points.
  5. Insert a bridge of `bridge_width_mm` by splitting the two cut lines at
     that segment and removing a gap -- i.e. subtract a small rectangle from
     the cut path so the material stays joined.
  6. Re-run until no islands remain, capping at 200 bridges.

Bridges are drawn on their own BRIDGE sublayer so the user can move them:
the automatic choice is topologically valid but rarely the prettiest.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Island:
    index: int
    area_mm2: float
    centroid: tuple[float, float]
    nearest: tuple[float, float]


def check(plan) -> list[Island]:
    raise NotImplementedError(
        "Island detection is Phase 4 and needs shapely:\n"
        "    pip install shapely\n"
        "Until then, inspect the CUT layer by eye for fully enclosed shapes."
    )


def auto_bridge(plan, width_mm: float = 1.5, max_bridges: int = 200):
    raise NotImplementedError("Phase 4. See the algorithm in this module's docstring.")
