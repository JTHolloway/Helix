"""Material presets. Numbers are starting points from real jobs -- always cut
a test strip, because every machine, lens and sheet differs."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Material:
    key: str
    name: str
    thickness_mm: float
    kerf_mm: float           # beam width removed; halve it for offsetting
    min_web_mm: float        # thinnest surviving bridge between two cuts
    min_text_mm: float       # smallest legible engraved cap height
    engrave_note: str
    cost_note: str


MATERIALS: dict[str, Material] = {m.key: m for m in [
    Material("birch_ply_3mm", "3 mm birch plywood", 3.0, 0.18, 1.2, 2.2,
             "Pale, high contrast. Grain can blotch; mask with transfer tape.",
             "Cheap and forgiving. Use for every prototype."),
    Material("mdf_5mm", "5 mm MDF", 5.0, 0.22, 1.6, 2.5,
             "Very even engrave, dark edges. Smells; needs good extraction.",
             "Cheapest. Edges look industrial rather than heirloom."),
    Material("acrylic_3mm_cast", "3 mm cast acrylic", 3.0, 0.15, 1.0, 2.0,
             "Cast frosts white when engraved -- excellent contrast. "
             "Extruded acrylic does not; buy cast.",
             "Flame-polished edges look superb backlit."),
    Material("walnut_veneer_ply_4mm", "4 mm walnut veneer ply", 4.0, 0.20, 1.4, 2.4,
             "Dark, warm, gift-grade. Engrave shallow or you cut through veneer.",
             "The one to use for the final piece."),
    Material("slate_coaster", "Slate", 6.0, 0.0, 4.0, 3.0,
             "Engrave only -- cannot be cut. Comes out chalk white.",
             "Wonderful for coasters and small keepsakes."),
    Material("anodised_alu_1mm", "1 mm anodised aluminium", 1.0, 0.0, 2.0, 1.6,
             "Fibre or CO2-with-marking-spray only. Extremely fine detail.",
             "Best small-text performance of anything here."),
    Material("card_1mm", "1 mm card", 1.0, 0.10, 0.8, 2.0,
             "Scorches easily; low power, high speed, air assist on.",
             "Always proof on this first. Costs pennies."),
]}


def get(key: str) -> Material:
    if key not in MATERIALS:
        raise KeyError(f"Unknown material '{key}'. "
                       f"Choose from: {', '.join(MATERIALS)}")
    return MATERIALS[key]
