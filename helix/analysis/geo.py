"""Geography: place hierarchy, geocoding and migration.

  * Places are stored hierarchically (parish -> county -> country) so that
    "Walcot", "Walcot, Bath" and "Walcot, Bath, Somerset, England" resolve to
    the same node. Historic boundaries change: `valid_from`/`valid_to` on the
    place row records when a name applied.
  * Geocoding is OPTIONAL and offline-first. Ship a gazetteer of UK parishes
    rather than calling an API, so the program works with no network and
    leaks no family data.
  * migration_distance(person) = haversine(birth_place, death_place).
  * The `geo_map` design plots people at their birthplace with descent lines
    between, which turns the chart into a map of how a family moved.
"""
from __future__ import annotations

import math


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    R = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = p2 - p1
    dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def geocode(con, *, gazetteer_path: str | None = None) -> int:
    raise NotImplementedError("Phase 7.")
