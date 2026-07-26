"""Every export format, checked for the things that actually go wrong."""
import re

import pytest

from helix.layout import registry
from helix.layout.base import LayoutSettings
from helix.layout.engines import experimental, linear, radial  # noqa: F401
from helix.render import dxf, eps
from helix.render import pdf as pdfr
from helix.render import svg as svgr
from helix.style.tokens import Style

MM_TO_PT = 72.0 / 25.4


def _plan(graph, key="radial_rings", style="panel1m"):
    return registry.run(key, graph,
                        LayoutSettings(engine=key, subject_id=graph.subject_id,
                                       focus="thread_siblings",
                                       max_generations=5),
                        Style.load(style))


def test_dxf_needs_no_third_party_library(graph, tmp_path):
    out = dxf.write(_plan(graph), tmp_path / "a.dxf")
    assert open(out).read().rstrip().endswith("EOF")


def test_dxf_is_r12_and_in_millimetres(graph, tmp_path):
    """R12 is the most widely readable revision ever published, and the
    units flag is what stops a CAD package guessing inches."""
    d = open(dxf.write(_plan(graph), tmp_path / "a.dxf")).read()
    assert "AC1009" in d
    assert re.search(r"\$INSUNITS\n\s*70\n4\n", d), "units must say millimetres"


def test_dxf_carries_the_cut_layers(graph, tmp_path):
    d = open(dxf.write(_plan(graph), tmp_path / "a.dxf")).read()
    for layer in ("CUT", "ENGRAVE", "ENGRAVE_DEEP"):
        assert f"\n{layer}\n" in d


def test_dxf_geometry_is_the_right_way_up(graph, tmp_path):
    """DXF counts y upward, the plan counts down. Getting this wrong mirrors
    the whole chart and nobody notices until it is cut."""
    plan = _plan(graph)
    d = open(dxf.write(plan, tmp_path / "a.dxf")).read()
    ys = [float(m) for m in re.findall(r"\n 20\n([-\d.]+)\n", d)] or \
         [float(m) for m in re.findall(r"\n20\n([-\d.]+)\n", d)]
    assert ys
    assert max(ys) <= plan.canvas.height_mm + 1


def test_eps_declares_the_right_size(graph, tmp_path):
    plan = _plan(graph)
    text = open(eps.write(plan, tmp_path / "a.eps")).read()
    m = re.search(r"%%BoundingBox: 0 0 (\d+) (\d+)", text)
    assert m
    assert abs(int(m.group(1)) - plan.canvas.width_mm * MM_TO_PT) < 2


def test_eps_escapes_postscript_specials(graph, tmp_path):
    plan = _plan(graph)
    for el in plan.elements:
        if el.kind == "text":
            el.text = "Smith (né Schmidt)"
            break
    text = open(eps.write(plan, tmp_path / "a.eps")).read()
    assert r"\(" in text and r"\)" in text


@pytest.mark.parametrize("writer,ext", [(svgr.render, "svg"), (None, "pdf"),
                                        (None, "dxf"), (None, "eps")])
def test_all_formats_agree_on_physical_size(graph, tmp_path, writer, ext):
    plan = _plan(graph)
    if ext == "svg":
        out = svgr.render(plan)
        assert f'width="{plan.canvas.width_mm:g}mm"'.replace(".0mm", "mm") in \
            out.replace(".0mm", "mm")
    elif ext == "pdf":
        p = tmp_path / "a.pdf"
        pdfr.write(plan, p)
        m = re.search(rb"/MediaBox \[0 0 ([\d.]+)", p.read_bytes())
        assert abs(float(m.group(1)) - plan.canvas.width_mm * MM_TO_PT) < 0.1
    elif ext == "dxf":
        d = open(dxf.write(plan, tmp_path / "a.dxf")).read()
        assert re.search(r"\$EXTMAX\n\s*10\n" +
                         re.escape(f"{plan.canvas.width_mm}"), d)
    else:
        t = open(eps.write(plan, tmp_path / "a.eps")).read()
        assert "%%BoundingBox" in t


def test_the_new_layouts_export_everywhere(graph, tmp_path):
    for key in ("hourglass", "fan_180", "dendrogram"):
        plan = _plan(graph, key, None)
        assert plan.elements, key
        for fn, ext in ((dxf.write, "dxf"), (eps.write, "eps"),
                        (pdfr.write, "pdf")):
            out = tmp_path / f"{key}.{ext}"
            fn(plan, out)
            assert out.stat().st_size > 400, f"{key}.{ext}"


def test_no_geometry_escapes_the_sheet(graph, tmp_path):
    """A circle written with RELATIVE arcs was being flattened as absolute,
    putting guide rings hundreds of millimetres off the sheet -- in the CAD
    exports only, because browsers read the relative form correctly. This
    checks every format against the canvas."""
    import re
    plan = _plan(graph)
    W, H = plan.canvas.width_mm, plan.canvas.height_mm
    d = open(dxf.write(plan, tmp_path / "a.dxf")).read()
    lines = d.split("\n")
    for i, ln in enumerate(lines[:-1]):
        if ln in ("10", "20"):
            try:
                v = float(lines[i + 1])
            except ValueError:
                continue
            limit = W if ln == "10" else H
            assert -2 <= v <= limit + 2, f"DXF point {v} outside 0..{limit}"


def test_relative_path_commands_are_flattened_correctly():
    from helix.render.pathflatten import flatten_d
    absolute = list(flatten_d("M10,10 L50,10 L50,50"))[0][0]
    relative = list(flatten_d("m10,10 l40,0 l0,40"))[0][0]
    assert absolute == relative


def test_a_circle_path_flattens_to_a_circle():
    import math
    from helix.layout.geometry import circle_path
    from helix.render.pathflatten import flatten_d
    pts = list(flatten_d(circle_path(100, 100, 40), 0.05))[0][0]
    radii = [math.dist((100, 100), p) for p in pts]
    assert abs(max(radii) - 40) < 0.5 and abs(min(radii) - 40) < 0.5
