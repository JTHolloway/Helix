"""Blocker 2: a production file you can send straight to the machine.

    helix render my.helix --production -o cut.svg

has to come out with no live text in it, an island report, and a pre-flight
that passes. Everything here is one of those three, or one of the ways they
were got wrong on the way.
"""
from __future__ import annotations

import math

import pytest

from helix.fab import islands, strokefont, textpath
from helix.fab.preflight import preflight
from helix.layout import registry
from helix.layout.base import LayoutSettings
from helix.layout.engines import family  # noqa: F401
from helix.layout.plan import Canvas, Element, FontSpec, PlanMeta, RenderPlan
from helix.style.tokens import Style


def _plan(graph, focus="bloodline", w=800, h=800, **tokens):
    style = Style.load("panel1m")
    style.set("canvas.width_mm", w)
    style.set("canvas.height_mm", h)
    for k, v in tokens.items():
        style.set(k.replace("__", "."), v)
    plan = registry.run("radial_family", graph,
                        LayoutSettings(engine="radial_family", focus=focus,
                                       subject_id=graph.subject_id), style)
    return plan, style


# ------------------------------------------------------------ the face --
def test_the_face_covers_what_a_name_is_made_of():
    face = textpath.load_face()
    for ch in ("ABCDEFGHIJKLMNOPQRSTUVWXYZ"
               "abcdefghijklmnopqrstuvwxyz"
               "0123456789 .,-'()?&/"):
        assert ch in face["glyphs"], f"no glyph for {ch!r}"


@pytest.mark.parametrize("word", ["Æthelred", "Kraków", "Straße", "Œuvre",
                                  "Ffion", "O’Doherty", "van der Zée"])
def test_a_name_never_loses_a_letter(word):
    """A name with a box in it is a bug you can see. A name quietly missing a
    letter is one you cannot, and it is somebody's name."""
    paths = textpath.stroke_paths(word, 4.0, 0, 0)
    assert paths, f"{word} engraved to nothing"
    # every character has to contribute at least one stroke, except the space
    assert len(paths) >= len(word.replace(" ", ""))


def test_the_letters_are_where_the_text_was():
    """Converted text has to land where the live text was, or every name on
    the chart shifts by half a line and nobody sees it until it is cut."""
    el = Element(kind="text", text="Reuben Marlow", x=100.0, y=50.0,
                 font=FontSpec(size_mm=6.0, anchor="middle"))
    pts = [p for d in textpath.to_strokes(el)
           for p in _points(d)]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    width = textpath.measure("Reuben Marlow", 6.0)
    assert abs((min(xs) + max(xs)) / 2 - 100.0) < width * 0.06
    assert abs((min(ys) + max(ys)) / 2 - 50.0) < 6.0 * 0.35
    assert width * 0.9 < max(xs) - min(xs) < width * 1.1


def test_anchors_mean_what_they_mean_on_svg():
    for anchor, want in (("start", 0.0), ("middle", -0.5), ("end", -1.0)):
        el = Element(kind="text", text="Marlow", x=0.0, y=0.0,
                     font=FontSpec(size_mm=5.0, anchor=anchor))
        xs = [p[0] for d in textpath.to_strokes(el) for p in _points(d)]
        w = textpath.measure("Marlow", 5.0)
        assert abs(min(xs) - want * w) < w * 0.08, anchor


def test_rotation_turns_about_the_anchor():
    a = Element(kind="text", text="Vasey", x=40.0, y=40.0, rotate=0.0,
                font=FontSpec(size_mm=5.0, anchor="middle"))
    b = Element(kind="text", text="Vasey", x=40.0, y=40.0, rotate=90.0,
                font=FontSpec(size_mm=5.0, anchor="middle"))
    for el in (a, b):
        pts = [p for d in textpath.to_strokes(el) for p in _points(d)]
        cx = (min(p[0] for p in pts) + max(p[0] for p in pts)) / 2
        cy = (min(p[1] for p in pts) + max(p[1] for p in pts)) / 2
        assert math.hypot(cx - 40, cy - 40) < 2.0


def _points(d):
    from helix.render import pathflatten
    return [p for pts, _ in pathflatten.flatten_d(d) for p in pts]


# ------------------------------------------------------- what --production does
def test_production_leaves_no_live_text(graph):
    """The acceptance criterion, exactly."""
    plan, style = _plan(graph)
    assert any(e.kind == "text" for e in plan.elements), "nothing to convert"
    textpath.bake(plan, style)
    assert not [e for e in plan.elements if e.kind == "text"]
    assert plan.meta.extra["text_to_paths"]["strokes"] > 0


def test_production_svg_has_no_text_tag(graph, tmp_path):
    from helix.cli import _write
    plan, style = _plan(graph)
    out = tmp_path / "cut.svg"
    _write(plan, out, production=True, style=style)
    assert "<text" not in out.read_text()


@pytest.mark.parametrize("ext", [".svg", ".pdf", ".eps", ".dxf"])
def test_every_writer_gets_the_same_baked_plan(graph, tmp_path, ext):
    """Baking happens once, on the plan, before any writer sees it. Done in
    the writers instead, four of them have to agree about what a letter is."""
    from helix.cli import _write
    plan, style = _plan(graph)
    out = tmp_path / f"cut{ext}"
    _write(plan, out, production=True, style=style)
    assert out.stat().st_size > 0
    assert not [e for e in plan.elements if e.kind == "text"]


def test_baking_keeps_who_each_mark_belongs_to(graph):
    """Hover, search and the person-to-element mapping all key off
    `person_id`. Losing it in the conversion breaks the app, silently, only
    in production files."""
    plan, style = _plan(graph)
    before = {e.person_id for e in plan.elements
              if e.kind == "text" and e.person_id}
    textpath.bake(plan, style)
    after = {e.person_id for e in plan.elements if e.person_id}
    assert before and before <= after


def test_text_to_paths_can_be_turned_off(graph):
    plan, style = _plan(graph)
    style.set("production.text_to_paths", False)
    textpath.bake(plan, style)
    assert [e for e in plan.elements if e.kind == "text"]


# --------------------------------------------------------------- islands --
def _loop(cx, cy, r, layer="CUT"):
    pts = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
           for a in range(0, 360, 10)]
    d = "M" + " L".join(f"{x:.4f},{y:.4f}" for x, y in pts) + " Z"
    return Element(kind="path", layer=layer, d=d, fill="none", stroke="#000")


def _sheet(*els):
    plan = RenderPlan(canvas=Canvas(200, 200), meta=PlanMeta(engine="test"))
    for e in els:
        plan.add(e)
    return plan


def test_an_island_is_a_piece_that_would_fall_out():
    """Piece, hole in it, and something inside the hole. The something is on
    the floor when the job finishes and nothing else warns you."""
    rep = islands.check(_sheet(_loop(100, 100, 90),
                               _loop(100, 100, 60),
                               _loop(100, 100, 30)))
    assert rep.loops == 3
    assert len(rep.islands) == 1
    assert rep.islands[0].depth == 2
    assert abs(rep.islands[0].area_mm2 - math.pi * 30 ** 2) < math.pi * 30 ** 2 * 0.05
    assert "fall out" in rep.summary()


def test_a_hole_is_not_an_island():
    """Depth 1 is waste and is meant to drop through. Calling it a defect
    would put a warning on every ring chart ever drawn."""
    rep = islands.check(_sheet(_loop(100, 100, 90), _loop(100, 100, 40)))
    assert rep.ok, rep.summary()


def test_a_hole_in_an_island_is_not_a_second_island():
    """Depth alternates. Four nested loops give one island, not two."""
    rep = islands.check(_sheet(_loop(100, 100, 90), _loop(100, 100, 70),
                               _loop(100, 100, 50), _loop(100, 100, 30)))
    assert len(rep.islands) == 1


def test_only_the_cut_layer_can_strand_anything():
    """An engraved circle inside an engraved circle is a drawing, not a
    piece."""
    rep = islands.check(_sheet(_loop(100, 100, 90, "ENGRAVE"),
                               _loop(100, 100, 60, "ENGRAVE"),
                               _loop(100, 100, 30, "ENGRAVE")))
    assert rep.ok and rep.loops == 0


def test_the_real_chart_strands_nothing(graph):
    plan, style = _plan(graph)
    rep = islands.check(plan)
    assert rep.ok, rep.summary()


def test_islands_are_reported_with_somewhere_to_bridge():
    rep = islands.check(_sheet(_loop(100, 100, 90),
                               _loop(100, 100, 60),
                               _loop(100, 100, 30)))
    i = rep.islands[0]
    assert 25 < math.hypot(i.nearest[0] - 100, i.nearest[1] - 100) < 65
    assert i.gap_mm > 0


# -------------------------------------------------------------- pre-flight --
@pytest.mark.parametrize("focus", ["thread", "bloodline"])
def test_preflight_passes_on_a_production_render(graph, focus):
    """The third acceptance criterion. Warnings are allowed -- 'bigger than
    your bed' is information, not a defect -- but nothing may FAIL."""
    plan, style = _plan(graph, focus=focus)
    textpath.bake(plan, style)
    bad = [f for f in preflight(plan, style) if f.level == "fail"]
    assert not bad, "; ".join(f"{f.title}: {f.detail}" for f in bad)


def test_preflight_catches_engraving_outside_the_cut(graph):
    """Found on the first production render: the key was in a corner the
    round cut line did not reach, so it would have stayed in the offcut."""
    plan, style = _plan(graph)
    plan.add(Element(kind="path", layer="ENGRAVE", d="M-500,-500 L-490,-490",
                     stroke="#000", role="stray"))
    bad = [f for f in preflight(plan, style)
           if f.level == "fail" and "outside" in f.title]
    assert bad, "a mark half a metre off the sheet was not noticed"


def test_a_cut_line_is_not_a_hairline_defect(graph):
    """Its width is the convention that says 'follow this', not a line
    weight. Warning about it sent the operator looking for a problem that was
    the file working correctly."""
    plan, style = _plan(graph)
    textpath.bake(plan, style)
    fine = [f for f in preflight(plan, style) if f.title == "Very fine lines"]
    assert not fine, fine[0].detail if fine else ""


def test_the_chart_has_something_to_cut(graph):
    plan, _ = _plan(graph)
    assert [e for e in plan.elements if e.layer == "CUT"], (
        "the file would engrave beautifully and never come off the sheet")


def test_everything_engraved_is_inside_the_cut(graph):
    """Whatever shape the outline takes, nothing may be left in the offcut."""
    from helix.render import pathflatten
    plan, style = _plan(graph)
    textpath.bake(plan, style)
    cuts = [pts for e in plan.elements if e.layer == "CUT"
            for pts, closed in pathflatten.flatten(e) if closed]
    assert cuts
    for e in plan.elements:
        if e.layer in ("CUT", "PRINT_ONLY"):
            continue
        for pts, _ in pathflatten.flatten(e):
            for p in pts[:1]:
                assert any(islands._point_in(p, c) for c in cuts), (
                    f"{e.role} at {p} is outside the cut line")


def test_the_key_survives_being_moved_into_the_hole(graph):
    """On a disc it is centred in the hole and the type shrinks to fit. If it
    cannot fit it is left off -- and says so, rather than being cut in half
    by the ring beside it."""
    plan, _ = _plan(graph, focus="all", w=1000, h=1000)
    key = [e for e in plan.elements if e.role == "key"]
    assert key or plan.meta.extra.get("key_dropped")


def test_the_built_in_face_is_the_documented_shape():
    """`hershey/*.json` must be able to replace it, so it has to be the same
    shape as one."""
    f = strokefont.face()
    assert f["cap"] == 21.0 and f["descender"] < 0
    for ch, g in f["glyphs"].items():
        assert g["advance"] > 0, ch
        for s in g["strokes"]:
            assert len(s) >= 2 and all(len(p) == 2 for p in s), ch
