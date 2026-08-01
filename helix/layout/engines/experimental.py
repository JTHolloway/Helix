"""Designs that are specified but not yet built.

Each is registered so it appears in the gallery greyed out, with a clear note
about what it will do. Implementing one is a self-contained job: read the
Grid, emit Elements. Nothing else in the program needs to change.
"""
from __future__ import annotations

from ..registry import register


def _todo(name: str, phase: str):
    def fn(graph, s, style):
        raise NotImplementedError(
            f"{name} is planned for {phase}. See docs/DESIGN_CATALOGUE.md for "
            f"the full specification."
        )
    # What tells the gallery to show it as a plan rather than as a picture
    # you can click. Without it the interface offered twenty designs and
    # six of them threw.
    fn.todo = True
    fn.phase = phase
    return fn


register("sugiyama", "Layered Network", "network",
         "Proper layered graph drawing with crossing minimisation. The only "
         "design that handles heavy cousin marriage without spaghetti.",
         good_for="Tangled trees where simple layouts fail.", laser="good"
         )(_todo("Layered Network", "Phase 9"))

register("hive", "Hive Plot", "network",
         "One straight axis per family line; links arc between axes. "
         "Endogamy becomes obvious and measurable.",
         good_for="Analysing intermarriage between a few families.",
         laser="good")(_todo("Hive Plot", "Phase 9"))

register("sankey", "River of Descent", "network",
         "Ribbons whose width is the number of descendants flowing forward "
         "through time. Lines that die out visibly narrow to nothing.",
         good_for="Emotional impact; showing which branches thrived.",
         laser="poor")(_todo("River of Descent", "Phase 9"))

register("geo_map", "Map View", "spatial",
         "People plotted at their birthplace on a real coastline, with "
         "descent lines showing how the family migrated.",
         good_for="Families that moved. Turns the chart into a story of place.",
         laser="excellent")(_todo("Map View", "Phase 9"))

register("constellation", "Star Chart", "spatial",
         "Force-directed positions drawn as a night sky: people are stars, "
         "lineages are constellations, brightness is descendant count.",
         good_for="A poster that does not look like a family tree at all.",
         laser="good")(_todo("Star Chart", "Phase 10"))

register("treemap", "Treemap", "linear",
         "Nested rectangles sized by descendant count. Squarified layout.",
         good_for="Dense data on a rectangular sheet with no wasted area.",
         laser="excellent")(_todo("Treemap", "Phase 10"))
