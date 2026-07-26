"""Styles are shared between people, so they must never execute code."""
import pytest

from helix.style.tokens import Style


def test_all_presets_load():
    for p in Style.list_presets():
        s = Style.load(p["id"])
        assert s.get("canvas.width_mm") > 0
        assert s.get("layout.engine")


def test_inheritance():
    child = Style.load("rings")
    assert child.get("layout.engine") == "radial_rings"
    assert child.get("cells.shape") == "none"


def test_unknown_style_lists_the_real_ones():
    with pytest.raises(FileNotFoundError) as e:
        Style.load("nonsense")
    assert "labyrinth" in str(e.value)


def test_missing_key_falls_back_to_default():
    assert Style.load().get("nothing.like.this", 7) == 7
    assert Style.load().get("cells.stroke_width_mm") > 0


def test_rules_cannot_execute_code():
    s = Style.load()
    s.data["rules"] = [{"when": "__import__('os').system('echo pwned')",
                        "set": {"cells.stroke": "#FF0000"}}]
    assert s.overrides_for({"gen": 1}) == {}     # rejected, not run


def test_rules_do_work_for_legitimate_expressions():
    s = Style.load()
    s.data["rules"] = [{"when": "gen > 3 and living", "set": {"cells.stroke": "#F00"}}]
    assert s.overrides_for({"gen": 5, "living": True}) == {"cells.stroke": "#F00"}
    assert s.overrides_for({"gen": 1, "living": True}) == {}


def test_chose_distinguishes_set_from_defaulted():
    """A design that wants a wide page must not be silently squared off by
    a global default nobody asked for."""
    assert not Style.load().chose("canvas.width_mm")
    assert Style.load("tubemap").chose("canvas.width_mm")
    s = Style.load()
    s.set("canvas.width_mm", 900)
    assert s.chose("canvas.width_mm")


def test_inherited_choices_are_inherited():
    child = Style.load("tubemap")
    assert child.chose("colour.palette")
    assert child.get("canvas.width_mm") == 1189
