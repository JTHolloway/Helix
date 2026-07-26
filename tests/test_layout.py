"""Every registered design must produce a valid plan on real data."""
import pytest

from helix.layout import registry
from helix.layout.base import LayoutSettings, build_grid
from helix.layout.engines import experimental, linear, radial  # noqa: F401
from helix.style.tokens import Style

BUILT = [d.key for d in registry.all_designs()
         if d.key not in {"sugiyama", "hive", "sankey", "geo_map",
                          "constellation", "hourglass", "fan_180", "treemap"}]


@pytest.mark.parametrize("key", BUILT)
def test_design_renders(key, graph):
    style = Style.load()
    style.set("layout.engine", key)
    s = LayoutSettings(engine=key, subject_id=graph.subject_id,
                       max_generations=4)
    plan = registry.run(key, graph, s, style)
    assert plan.elements, f"{key} produced nothing"
    assert plan.canvas.width_mm > 0 and plan.canvas.height_mm > 0
    for el in plan.elements:
        assert el.layer in {"CUT", "SCORE", "ENGRAVE", "ENGRAVE_DEEP",
                            "GUIDE", "PRINT_ONLY"}
        if el.kind == "path":
            assert el.d, f"{key}: empty path"
            assert "nan" not in el.d.lower(), f"{key}: NaN leaked into geometry"


@pytest.mark.parametrize("key", BUILT)
def test_every_person_element_is_traceable(key, graph):
    """Hover, search and the what-if overlay all depend on provenance."""
    style = Style.load()
    s = LayoutSettings(engine=key, subject_id=graph.subject_id, max_generations=3)
    plan = registry.run(key, graph, s, style)
    tagged = {e.person_id for e in plan.elements if e.person_id}
    assert len(tagged) > 5


def test_grid_covers_everyone_once(graph):
    s = LayoutSettings(engine="radial_sunburst")
    g = build_grid(graph, s)
    assert len(g.slots) == len(g.order)
    assert len(set(g.order)) == len(g.order), "a person was placed twice"


def test_spread_axis_stays_in_range(graph):
    g = build_grid(graph, LayoutSettings(engine="radial_sunburst"))
    for sl in g:
        assert -0.001 <= sl.t0 <= 1.001
        assert -0.001 <= sl.t1 <= 1.001
        assert sl.t1 >= sl.t0


def test_missing_years_are_inferred_not_left_none(graph):
    """Chronological designs collapse if any year is None."""
    g = build_grid(graph, LayoutSettings(engine="timeline_lanes"))
    assert all(sl.year is not None for sl in g)


def test_unbuilt_designs_fail_helpfully():
    style = Style.load()
    s = LayoutSettings(engine="sugiyama")
    with pytest.raises(NotImplementedError) as e:
        registry.run("sugiyama", None, s, style)
    assert "DESIGN_CATALOGUE" in str(e.value)


def test_unknown_design_names_the_alternatives():
    with pytest.raises(KeyError) as e:
        registry.get("does_not_exist")
    assert "radial_sunburst" in str(e.value)
