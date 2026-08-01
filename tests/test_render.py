"""Output must be dimensionally correct: a laser will not argue with you."""
import re

from helix.layout import registry
from helix.layout.base import LayoutSettings
from helix.layout.engines import linear, radial  # noqa: F401
from helix.render import svg as svgrender
from helix.render.pathflatten import flatten_d
from helix.style.tokens import Style


def _plan(graph, key="radial_sunburst"):
    style = Style.load()
    return registry.run(key, graph,
                        LayoutSettings(engine=key, subject_id=graph.subject_id,
                                       max_generations=4), style)


def test_svg_carries_real_millimetres(graph):
    """The single most common cause of a ruined job is a file that arrives
    at 25.4x scale. width/height must be in mm AND match the viewBox."""
    plan = _plan(graph)
    out = svgrender.render(plan)
    w = re.search(r'width="([\d.]+)mm"', out)
    vb = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', out)
    assert w and vb
    assert abs(float(w.group(1)) - plan.canvas.width_mm) < 0.01
    assert abs(float(vb.group(1)) - plan.canvas.width_mm) < 0.01


def test_svg_has_named_layers(graph):
    out = svgrender.render(_plan(graph))
    assert 'inkscape:label="ENGRAVE"' in out


def test_production_drops_screen_only_elements(graph):
    plan = _plan(graph, "timeline_lanes")
    assert len(svgrender.render(plan, production=True)) < len(svgrender.render(plan))


def test_interactive_mode_tags_people(graph):
    out = svgrender.render(_plan(graph), interactive=True)
    assert "data-p=" in out


def test_no_nan_or_inf_reaches_the_file(graph):
    """Word boundaries matter here: 'dominant-baseline' contains 'nan'."""
    bad = re.compile(r"\b(nan|inf|infinity|-nan)\b", re.I)
    for key in ("radial_rings", "metro_map", "radial_lifeline", "circle_pack"):
        out = svgrender.render(_plan(graph, key))
        m = bad.search(out)
        assert not m, f"{key}: {out[max(0, m.start()-80):m.end()+20]}"


def test_path_flattening_round_trips():
    segs = list(flatten_d("M10,10 L50,10 A20,20 0 0,1 50,50 L10,50 Z"))
    assert len(segs) == 1
    pts, closed = segs[0]
    assert closed and len(pts) > 10
    assert all(abs(x) < 1e4 and abs(y) < 1e4 for x, y in pts)


def test_escapes_dangerous_text(graph):
    plan = _plan(graph)
    for el in plan.elements:
        if el.kind == "text":
            el.text = '<script>alert("x")</script>'
            break
    out = svgrender.render(plan)
    assert "<script>" not in out
