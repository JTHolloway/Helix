"""Design tokens: styles are data, not code.

Single responsibility: load, merge and query a style. Contains no geometry.
A style is a JSON file; `Style.get("cells.stroke_width_mm", 0.3)` is the only
way any other module is allowed to learn a visual value.
"""
from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PRESETS = Path(__file__).with_name("presets")

DEFAULTS: dict[str, Any] = {
    "id": "default",
    "name": "Default",
    "canvas": {"width_mm": 600, "height_mm": 600, "margin_mm": 20,
               "background": "#FBF8F2", "shape": "circle"},
    "layout": {"engine": "radial_family", "inner_radius_mm": 90,
               # HOW CLOSE FAMILY IS, and it is the only thing on the chart
               # that says so without a line. There are three distances and
               # they have to be TOLD APART at a glance, because each means
               # something different:
               #
               #   married   two names in one cell, touching. No gap at all.
               #   siblings  `sibling_gap_cells` -- close, but a visible
               #             step out from touching.
               #   a new     `family_gap_cells` -- unmistakably wider. This
               #   family    is the boundary between one household and the
               #             next, and it is what lets you see where a
               #             family ends without following a single line.
               #
               # On a 142-name chart that is 6.0, 6.8 and 10.3 degrees --
               # gaps of 0, 0.8 and 4.3 -- so the three read apart at a
               # glance. Turn `family_gap_cells` up for a bigger step; the
               # only cost is cell width, and past about 0.9 a long name in
               # a narrow cell starts being shortened to initials.
               #
               # Getting the NUMBERS apart was not enough on its own: the
               # gap is applied to a whole block, so two sisters sitting
               # close -- rightly -- put their children the same distance
               # apart on the ring outside, and two first cousins ended up
               # spaced exactly like brother and sister. `couple_grid._clear`
               # now applies the sibling gap only on the ring where the two
               # blocks ARE siblings.
               "sibling_gap_cells": 0.16, "family_gap_cells": 0.75,
               # No couple may own more than this much of the disc. A sparse
               # family is drawn as a fan of the angle it needs rather than
               # stretched round the full circle.
               "max_cell_deg": 12.0, "min_cells": 0,
               # The narrowest a couple's cell may get before the chart is
               # doing them a disservice. Drives both the angle the chart
               # chooses and the size of the hole in the middle.
               "min_cell_arc_mm": 0,
               "start_angle_deg": -90, "sweep_deg": 360, "sector_gap_deg": 2,
               "radius_gamma": 0.5, "time_scale": True, "weight_mode": "leaves",
               "cell_pad_deg": 0.12, "min_ring_mm": 8},
    "couple": {
               # shared | split | auto. Shared stacks both names in
               # one leaf; split gives each partner their own leaf so
               # their own ancestry sits inside them. Auto splits only
               # where sharing would be ambiguous -- both partners
               # having parents on the chart.
               "leaf": "auto"},
    # The tinted ground behind each family: which branch is which, and where
    # two of them married. It answers a question the linework cannot -- a
    # stem to a couple looks the same whether the partner brought a
    # documented line with them or married in from nowhere -- but it is a
    # READING aid, not part of the chart. It lives on PRINT_ONLY so no
    # cutter ever sees it, and it is OFF by default so a rendered file is
    # the chart and nothing else. The control panel turns it on.
    "family": {"wedges": False, "wedge_opacity": 0.13,
               "wedge_min_cells": 3, "wedge_max": 10,
               "wedge_max_share": 0.95},
    "cells": {"shape": "annular_sector", "fill": "none", "stroke": "#22201D",
              "stroke_width_mm": 0.3, "stroke_by_confidence": True,
              "radial_depth_mm": 9},
    "connectors": {"style": "orthogonal", "width_mm": 0.4, "colour": "#22201D",
                   "corner_radius_mm": 2.0, "opacity": 1.0},
    "nodes": {"glyph": "none", "size_mm": 1.6, "fill": "#FBF8F2",
              "stroke": "#22201D", "stroke_width_mm": 0.35},
    "type": {"family": "Georgia, 'Iowan Old Style', serif", "size_mm": 3.0,
             "min_size_mm": 2.2, "weight": 400, "tracking": 0.0,
             "colour": "#22201D", "case": "as_typed"},
    "labels": {"template": "{given_first} {surname}", "by_ring": {},
               "orientation": "auto", "show": True,
               # inward | outward | upright. WHICH WAY UP every name is set.
               #
               #   inward   tops of the letters point toward the centre, so
               #            the BOTTOM half of the disc reads the right way
               #            up and the top half is upside down. The default:
               #            the newest generations are at the bottom rim and
               #            that is the half you read first.
               #   outward  tops point away from the centre, so the TOP half
               #            reads the right way up. The same chart, turned.
               #   upright  no name is ever upside down, at the cost of the
               #            two halves reading in opposite directions.
               #
               # The first two are consistent all the way round: you turn
               # the chart, not your head.
               "face": "inward"},
    # The direct line, picked out in colour. It is a HIGHLIGHT: it recolours
    # lines the chart draws anyway, so it has to be findable across a metre
    # of sheet without becoming the loudest thing on it. At three and a half
    # times the weight of the linework it was -- every place it crossed
    # another family's line shouted, and the chart read as a red diagram with
    # a family tree behind it.
    "thread": {"enabled": True, "colour": "#A3392B", "stroke_width_mm": 0.9,
               "layer": "ENGRAVE_DEEP", "node_marker": "diamond", "halo_mm": 0.0},
    "ornament": {"time_rings": True, "time_ring_colour": "#C9C0B0",
                 "era_bands": False, "border": True, "clock": False,
                 "legend": True, "title": ""},
    "colour": {"mode": "none",
               "palette": ["#22201D", "#9C6B3F", "#3E6B70", "#A3392B",
                           "#6B7B4F", "#7A5C8E", "#B08A3E", "#4A6E9C",
                           "#8C5A4A", "#5C8A78", "#9E4F6E", "#6E6E6E"]},
    "production": {"mode": "print", "material": "birch_ply_3mm", "kerf_mm": 0.18,
                   "min_web_mm": 1.2, "bridge_width_mm": 1.5,
                   "text_to_paths": True, "hairline_mm": 0.05,
                   # Engraved strokes are a centreline the beam
                   # follows, not a drawn line -- but the preview
                   # has to be visible, and a hairline is not.
                   "engrave_stroke_mm": 0.25,
                   "cut_outline": True, "cut_colour": "#B03A2E"},
    "rules": [],
}

_ALLOWED_NODES = (ast.Expression, ast.BoolOp, ast.UnaryOp, ast.Compare, ast.Name,
                  ast.Load, ast.Constant, ast.And, ast.Or, ast.Not, ast.Eq,
                  ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn)


@dataclass
class Style:
    data: dict
    explicit: set = field(default_factory=set)
    """Dotted paths the user or preset actually chose.

    This matters more than it looks. Without it, a global default of
    600x600 mm silently overrides a wide design's own sensible page size,
    and an arc diagram that wants a 1189 mm sheet comes out square and
    cramped. `chose()` lets an engine tell "nobody said" from "somebody
    said 600".
    """

    # ------------------------------------------------------------ loading
    @staticmethod
    def load(name_or_path: str | Path | None = None) -> "Style":
        d = json.loads(json.dumps(DEFAULTS))       # deep copy
        chosen: set[str] = set()
        if name_or_path:
            p = Path(name_or_path)
            if not p.exists():
                p = PRESETS / f"{name_or_path}.json"
            if not p.exists():
                avail = ", ".join(sorted(x.stem for x in PRESETS.glob("*.json")))
                raise FileNotFoundError(
                    f"No style called '{name_or_path}'. Built-in styles: {avail}"
                )
            child = json.loads(p.read_text())
            if child.get("extends"):
                parent = Style.load(child["extends"])
                d = _merge(d, parent.data)
                chosen |= parent.explicit
            d = _merge(d, child)
            chosen |= _paths(child)
        return Style(d, chosen)

    def chose(self, path: str) -> bool:
        """True if this value was deliberately set, rather than defaulted."""
        return path in self.explicit

    @staticmethod
    def list_presets() -> list[dict]:
        """Resolve inheritance when listing, so a preset that gets its engine
        from `extends` is not reported as having none."""
        out = []
        for p in sorted(PRESETS.glob("*.json")):
            try:
                st = Style.load(p.stem)
                out.append({"id": p.stem,
                            "name": st.get("name", p.stem),
                            "blurb": st.get("blurb", ""),
                            "engine": st.get("layout.engine", ""),
                            "laser": st.get("laser", "good")})
            except Exception:
                continue
        return out

    # ------------------------------------------------------------ querying
    def get(self, path: str, default=None):
        cur: Any = self.data
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return _default_for(path, default)
            cur = cur[part]
        return cur

    def set(self, path: str, value) -> None:
        parts = path.split(".")
        cur = self.data
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = value
        self.explicit.add(path)

    def colour(self, i: int) -> str:
        pal = self.get("colour.palette", DEFAULTS["colour"]["palette"])
        return pal[i % len(pal)]

    # ------------------------------------------------------------ rules
    def overrides_for(self, ctx: dict) -> dict[str, Any]:
        """Evaluate `rules` against one person's context. Uses a whitelisted
        AST walk, never eval(), so a shared style file can never run code."""
        out: dict[str, Any] = {}
        for rule in self.get("rules", []) or []:
            try:
                if _safe_eval(rule.get("when", "False"), ctx):
                    out.update(rule.get("set", {}))
            except Exception:
                continue
        return out


def _paths(d: dict, prefix: str = "") -> set[str]:
    """Every dotted leaf path present in a style document."""
    out: set[str] = set()
    for k, v in d.items():
        p = f"{prefix}{k}"
        if isinstance(v, dict):
            out |= _paths(v, p + ".")
        else:
            out.add(p)
    return out


def _default_for(path: str, fallback):
    cur: Any = DEFAULTS
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return fallback
        cur = cur[part]
    return cur


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _safe_eval(expr: str, ctx: dict) -> bool:
    tree = ast.parse(expr, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"unsupported expression: {type(node).__name__}")
    return bool(eval(compile(tree, "<rule>", "eval"), {"__builtins__": {}}, dict(ctx)))
