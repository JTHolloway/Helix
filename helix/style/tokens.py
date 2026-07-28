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
               "start_angle_deg": -90, "sweep_deg": 360, "sector_gap_deg": 2,
               "radius_gamma": 0.5, "time_scale": True, "weight_mode": "leaves",
               "cell_pad_deg": 0.12, "min_ring_mm": 8},
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
               "orientation": "auto", "show": True},
    "thread": {"enabled": True, "colour": "#A3392B", "stroke_width_mm": 1.4,
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
                   "text_to_paths": True, "hairline_mm": 0.05},
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
