"""Helpers shared by every engine: labels, colour modes, confidence linework."""
from __future__ import annotations

import math
from typing import Optional

from .plan import Element, FontSpec, RenderPlan
from . import geometry as G

TEMPLATE_FIELDS = [
    "given", "given_first", "given_used", "initials", "surname", "full_name",
    "short_name", "birth_year", "death_year", "lifespan", "age", "occupation",
    "education", "birth_place", "sex", "n",
]


def fill_template(tpl: str, person, n: int = 0) -> str:
    vals = {
        "given": person.given, "given_first": person.given_first,
        "given_used": person.given_used or person.given_first,
        "initials": person.initials, "surname": person.surname,
        "full_name": person.full_name, "short_name": person.short_name,
        "birth_year": person.birth_year or "", "death_year": person.death_year or "",
        "lifespan": person.lifespan, "age": person.age,
        "occupation": person.occupation, "education": person.education,
        "birth_place": (person.birth_place or "").split(",")[0],
        "sex": person.sex, "n": n,
    }
    out = tpl
    for k, v in vals.items():
        out = out.replace("{" + k + "}", str(v))
    # tidy the debris left by empty fields
    lines = [" ".join(ln.split()).strip(" \u2013-,") for ln in out.split("\\n")]
    return "\n".join(ln for ln in lines if ln)


def template_for(style, gen: int) -> str:
    """The single-line template, for the designs that only want one line.
    `labels.lines` may be a list; take its first entry."""
    by = style.get("labels.by_ring", {}) or {}
    for spec, tpl in by.items():
        if _ring_match(spec, gen):
            return tpl[0] if isinstance(tpl, list) else tpl
    lines = style.get("labels.lines")
    if lines:
        return lines[0] if isinstance(lines, list) else lines
    return style.get("labels.template", "{given_first} {surname}")


def _ring_match(spec: str, gen: int) -> bool:
    spec = str(spec).strip()
    if spec.endswith("+"):
        return gen >= int(spec[:-1])
    if "-" in spec:
        a, b = spec.split("-", 1)
        return int(a) <= gen <= int(b)
    return spec.isdigit() and int(spec) == gen


# ------------------------------------------------------------------ colour --
def colour_for(person, slot, style, graph, crit: Optional[dict] = None) -> str:
    mode = style.get("colour.mode", "none")
    pal = style.get("colour.palette")
    base = style.get("cells.stroke", "#22201D")
    if mode == "none":
        return base
    if mode == "sex":
        return {"M": pal[3], "F": pal[2], "X": pal[5]}.get(person.sex, pal[0])
    if mode == "lineage":
        return _idx_colour(slot.lineage, pal)
    if mode == "surname":
        return _idx_colour(person.surname or "?", pal)
    if mode == "generation":
        return pal[slot.gen % len(pal)]
    if mode == "confidence":
        return [pal[6], pal[6], base, pal[2]][max(0, min(3, person.confidence))]
    if mode == "geography":
        return _idx_colour((person.birth_place or "?").split(",")[-1].strip(), pal)
    if mode == "occupation":
        return _idx_colour(_occ_group(person.occupation), pal)
    if mode == "lifespan":
        yrs = _lifespan_years(person)
        if yrs is None:
            return "#B8B0A4"
        t = min(1.0, max(0.0, yrs / 95.0))
        return _lerp_hex("#8C3A2E", "#3E6B70", t)
    if mode == "criticality" and crit:
        c = crit.get(person.id, 1)
        t = min(1.0, math.log1p(c) / math.log1p(max(crit.values() or [1])))
        return _lerp_hex("#D8D2C6", "#A3392B", t)
    return base


def _idx_colour(key: str, pal: list[str]) -> str:
    return pal[abs(hash(key)) % len(pal)]


def _occ_group(occ: str) -> str:
    o = (occ or "").lower()
    groups = {
        "land": ["farm", "agric", "shepherd", "labourer", "husband"],
        "craft": ["smith", "carpent", "mason", "wheelwright", "cooper", "tailor"],
        "sea": ["mariner", "sailor", "fisher", "naval"],
        "trade": ["merchant", "grocer", "draper", "shop", "innkeeper", "baker"],
        "industry": ["miner", "weaver", "mill", "engineer", "factory", "railway"],
        "service": ["servant", "cook", "maid", "butler", "nurse"],
        "profession": ["clerk", "solicitor", "doctor", "teacher", "clergy", "rev"],
        "military": ["soldier", "army", "sergeant", "private", "officer"],
    }
    for g, keys in groups.items():
        if any(k in o for k in keys):
            return g
    return "other" if o else "unknown"


def _lifespan_years(person) -> Optional[float]:
    if person.birth.sort_value and person.death.sort_value:
        return person.death.sort_value - person.birth.sort_value
    return None


def _lerp_hex(a: str, b: str, t: float) -> str:
    ai = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    bi = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{int(ai[i] + (bi[i] - ai[i]) * t):02X}" for i in range(3))


# ------------------------------------------------------------- confidence --
def dash_for(person, style) -> Optional[str]:
    if not style.get("cells.stroke_by_confidence", True):
        return None
    return {0: "0.8,1.2", 1: "2,1.4"}.get(person.confidence)


def opacity_for(person) -> float:
    return {0: 0.55, 1: 0.8}.get(person.confidence, 1.0)


# ----------------------------------------------------------------- labels --
def add_label(plan: RenderPlan, text: str, x: float, y: float, style,
              *, rotate: float = 0.0, size: Optional[float] = None,
              anchor: str = "middle", person_id: Optional[str] = None,
              colour: Optional[str] = None, weight: Optional[int] = None,
              layer: str = "ENGRAVE", z: int = 60,
              role: str = "label") -> None:
    if not text:
        return
    fs = size or style.get("type.size_mm", 3.0)
    lines = text.split("\n")
    lh = fs * 1.18
    y0 = y - (len(lines) - 1) * lh / 2
    for i, ln in enumerate(lines):
        plan.add(Element(
            kind="text", layer=layer, text=ln, x=x, y=y0 + i * lh, rotate=rotate,
            fill=colour or style.get("type.colour", "#22201D"),
            font=FontSpec(family=style.get("type.family"), size_mm=fs,
                          weight=weight or style.get("type.weight", 400),
                          letter_spacing=style.get("type.tracking", 0.0),
                          anchor=anchor),
            person_id=person_id, role=role, z=z))


class LabelPlacer:
    """Greedy collision suppressor.

    Charts fail at the label layer, not the geometry layer. Rather than let
    1,800 names pile into an unreadable mat, we place the most important
    labels first and progressively DEMOTE the rest: full text -> short name
    -> initials -> nothing. The count of demotions is reported to the user so
    they know to make the piece bigger or show fewer generations.
    """

    def __init__(self, cell_mm: float = 8.0, min_gap_mm: float = 0.6):
        self.cell = cell_mm
        self.gap = min_gap_mm
        self.grid: dict[tuple[int, int], list[tuple[float, float, float, float]]] = {}
        self.placed = 0
        self.demoted = 0
        self.dropped = 0

    def _cells(self, box):
        x0, y0, x1, y1 = box
        for i in range(int(x0 // self.cell), int(x1 // self.cell) + 1):
            for j in range(int(y0 // self.cell), int(y1 // self.cell) + 1):
                yield (i, j)

    def free(self, box) -> bool:
        x0, y0, x1, y1 = box
        x0 -= self.gap; y0 -= self.gap; x1 += self.gap; y1 += self.gap
        for c in self._cells((x0, y0, x1, y1)):
            for b in self.grid.get(c, ()):
                if not (x1 < b[0] or x0 > b[2] or y1 < b[1] or y0 > b[3]):
                    return False
        return True

    def take(self, box) -> None:
        for c in self._cells(box):
            self.grid.setdefault(c, []).append(box)
        self.placed += 1

    @staticmethod
    def box_for(text: str, x: float, y: float, size: float, rotate: float,
                anchor: str) -> tuple[float, float, float, float]:
        lines = text.split("\n")
        w = max(est_text_width(ln, size) for ln in lines) if lines else 0.0
        h = size * 1.2 * len(lines)
        if abs(rotate) > 1e-6:
            import math as _m
            a = _m.radians(rotate)
            w2 = abs(w * _m.cos(a)) + abs(h * _m.sin(a))
            h2 = abs(w * _m.sin(a)) + abs(h * _m.cos(a))
            w, h = w2, h2
        if anchor == "start":
            x0 = x
        elif anchor == "end":
            x0 = x - w
        else:
            x0 = x - w / 2
        return (x0, y - h / 2, x0 + w, y + h / 2)


class PolarLabelPlacer:
    """Collision testing for text set along a radius.

    An axis-aligned box is hopeless for rotated text: a 35 mm name at 45
    degrees has a bounding box 25 mm square, so it appears to collide with
    everything nearby and the placer throws away labels that would have been
    perfectly fine. On a radial chart that was discarding a quarter of the
    names for no reason.

    In polar terms the test is exact and trivial. Radial text occupies:
        an ANGULAR band of (text height / radius) radians
        a RADIAL band of [start, start + text length]
    Two such labels collide only if BOTH bands overlap.
    """

    def __init__(self, min_gap_mm: float = 0.5):
        self.gap = min_gap_mm
        self.items: list[tuple[float, float, float, float]] = []
        self.placed = 0
        self.demoted = 0
        self.dropped = 0

    @staticmethod
    def _norm(t: float) -> float:
        while t < 0:
            t += 2 * math.pi
        while t >= 2 * math.pi:
            t -= 2 * math.pi
        return t

    def _box(self, theta: float, r0: float, length: float, height: float):
        r1 = r0 + length
        half = (height / 2 + self.gap) / max(r0, 1e-3)
        return (self._norm(theta - half), self._norm(theta + half),
                r0 - self.gap, r1 + self.gap)

    def free(self, theta, r0, length, height) -> bool:
        a0, a1, ra, rb = self._box(theta, r0, length, height)
        for b0, b1, rc, rd in self.items:
            if rb < rc or ra > rd:
                continue
            if _ang_overlap(a0, a1, b0, b1):
                return False
        return True

    def take(self, theta, r0, length, height) -> None:
        self.items.append(self._box(theta, r0, length, height))
        self.placed += 1


def _ang_overlap(a0, a1, b0, b1) -> bool:
    """Overlap test that survives the wrap at zero."""
    def spans(x0, x1):
        return [(x0, x1)] if x0 <= x1 else [(x0, 2 * math.pi), (0.0, x1)]
    for s0, s1 in spans(a0, a1):
        for t0, t1 in spans(b0, b1):
            if s0 < t1 and t0 < s1:
                return True
    return False


TANGENTIAL_HEADROOM = 1.9    # how much spare arc before 'auto' turns a name
                             # to follow the ring instead of the branch


def label_lines(style, person, gen: int, order: int) -> list[tuple[str, float, str]]:
    """Build the stacked lines of one label.

    `labels.lines` is a list of templates, one per line, so a chart can read

        Elizabeth Hallam
        1802-1871
        Dressmaker

    Each line may carry its own size multiplier and colour, because a date
    set at the same weight as a name competes with it; at 75% it recedes and
    the name stays the thing you read first.

    `labels.by_ring` overrides the whole stack per generation, so the inner
    ancestors can be given full detail while the crowded rim gets a name.
    """
    spec = _lines_spec(style, gen)
    base = style.get("type.size_mm", 2.8)
    scales = style.get("labels.line_scale", [1.0, 0.78, 0.7]) or []
    colours = style.get("labels.line_colour", []) or []
    default_col = style.get("type.colour", "#22201D")
    out: list[tuple[str, float, str]] = []
    for i, tpl in enumerate(spec):
        txt = fill_template(tpl, person, order).replace("\n", " ").strip()
        if not txt:
            continue
        scale = scales[i] if i < len(scales) else (scales[-1] if scales else 1.0)
        col = colours[i] if i < len(colours) else default_col
        out.append((txt, max(style.get("type.min_size_mm", 2.2), base * scale), col))
    return out


def _lines_spec(style, gen: int) -> list[str]:
    by = style.get("labels.by_ring", {}) or {}
    for spec, val in by.items():
        if _ring_match(spec, gen):
            return val if isinstance(val, list) else [val]
    val = style.get("labels.lines")
    if val:
        return val if isinstance(val, list) else [val]
    return [style.get("labels.template", "{given_first} {surname}")]


def place_radial_label(plan, placer: PolarLabelPlacer, person,
                       lines: list[tuple[str, float, str]],
                       theta: float, r_start: float, cx: float, cy: float,
                       style, *, flip: bool, orientation: str = "radial",
                       arc_available: float = 0.0, face: str = "upright") -> bool:
    """Place a stacked label, demoting it if the full version will not fit.

    Orientation:
      radial      set along its own branch, reading outward. Packs tightest,
                  because a name then costs only its HEIGHT in angle.
      tangential  set along the ring, reading around the circle. Much easier
                  on the eye, but costs its full WIDTH in angle, so it only
                  works where there is room.
      auto        tangential where it fits, radial where it does not. This is
                  the sensible default: the roomy inner rings read naturally
                  and the crowded rim still fits.
    """
    if not lines:
        return False

    # Build the ladder of things to try, best first. 'auto' means TRY
    # tangential and fall back to radial for that person -- decided at
    # placement time, not guessed from an average beforehand, so auto can
    # never place fewer names than plain radial would.
    short = person.short_name
    fallbacks = [lines]
    if len(lines) > 1:
        fallbacks.append(lines[:1])                      # drop the extra lines
    if short and short != lines[0][0]:
        fallbacks.append([(short, lines[0][1], lines[0][2])])
    if person.initials:
        fallbacks.append([(person.initials, lines[0][1], lines[0][2])])

    if orientation == "tangential":
        modes = ["tangential"]
    elif orientation == "auto":
        # Tangential reads far better but costs the full WIDTH of the name in
        # angle instead of its height, so it is only offered where the ring
        # is genuinely roomy. Without this gate the placer is greedy: the
        # first few names take the wide slots and starve their neighbours,
        # and 'auto' ends up placing fewer names than plain radial.
        widest = max(est_text_width(t, sz) for t, sz, _ in lines)
        roomy = arc_available > widest * TANGENTIAL_HEADROOM
        modes = ["tangential", "radial"] if roomy else ["radial"]
    else:
        modes = ["radial"]

    attempts = []
    for i, var in enumerate(fallbacks):
        for m in modes:
            attempts.append((i, var, m))
    attempts.sort(key=lambda a: (a[0], modes.index(a[2])))

    for i, var, mode in attempts:
        total_h = sum(sz * 1.16 for _, sz, _ in var)
        max_len = max(est_text_width(t, sz) for t, sz, _ in var)
        if mode == "tangential":
            ang_extent, rad_extent = max_len, total_h
        else:
            ang_extent, rad_extent = total_h, max_len
        if not placer.free(theta, r_start, rad_extent, ang_extent):
            continue
        placer.take(theta, r_start, rad_extent, ang_extent)
        if i:
            placer.demoted += 1
        _emit(plan, person, var, theta, r_start, cx, cy, style, flip, face,
              mode, total_h)
        return True
    placer.dropped += 1
    return False


def _upright(rot: float, anchor: str) -> tuple[float, str]:
    """Never set text upside down.

    Whatever the orientation, if the computed rotation lands in the range
    that would have the reader tilting their head past vertical, turn it
    through 180 degrees and swap the anchor so the text occupies exactly the
    same space while reading left to right.
    """
    a = rot % 360
    if 90 < a < 270:
        a = (a + 180) % 360
        anchor = {"start": "end", "end": "start"}.get(anchor, anchor)
    return a, anchor


def _emit(plan, person, var, theta, r_start, cx, cy, style, flip, face,
          orientation, total_h):
    """`face` decides what a RADIAL name does on the left half of the disc.

    upright   turn it through 180 so it is never upside down on the page.
              Conventional, but it means names read outward on one side of
              the chart and inward on the other.
    outward   always read from the middle outward, the way the family grows.
              Half of them are then upside down if you hold the chart still,
              which is the point: you turn the chart, not your head.
    """
    from . import geometry as _G
    run = 0.0
    for txt, size, col in var:
        h = size * 1.16
        if orientation == "tangential":
            # lines stack outward along the radius; text follows the arc
            r = r_start + run + h * 0.5
            x, y = _G.polar(cx, cy, r, theta)
            # `outward` reads the ring as if you were standing OUTSIDE it
            # looking in: the tops of the letters point away from the centre,
            # all the way round. `_upright` instead turns a name through 180
            # wherever it would be upside down on the page, which keeps it
            # readable without moving the chart but means the top half and
            # the bottom half read in opposite directions.
            if face == "outward":
                # -90, not +90. The tops of the letters point INWARD, which
                # is how you read a chart held the right way up: the names
                # along the bottom of the disc are the right way round and
                # you turn it to follow a line up the far side.
                rot, anchor = _G.deg(theta) - 90, "middle"
            else:
                rot, anchor = _upright(_G.deg(theta) + 90, "middle")
            add_label(plan, txt, x, y, style, rotate=rot, size=size,
                      anchor=anchor, person_id=person.id, colour=col)
        else:
            # lines stack sideways, i.e. angularly; text follows the branch
            off = (-total_h / 2 + run + h / 2) / max(r_start, 1e-3)
            t = theta + (-off if flip else off)
            x, y = _G.polar(cx, cy, r_start, t)
            if face == "outward":
                rot, anchor = _G.deg(t), "start"
            else:
                rot, anchor = _upright(_G.deg(t) + (180 if flip else 0),
                                       "end" if flip else "start")
            add_label(plan, txt, x, y, style, rotate=rot, size=size,
                      anchor=anchor, person_id=person.id, colour=col)
        run += h


def place_label(plan, placer: "LabelPlacer | None", person, text: str,
                x: float, y: float, style, *, rotate: float = 0.0,
                size: float | None = None, anchor: str = "middle",
                colour: str | None = None, layer: str = "ENGRAVE",
                z: int = 60) -> bool:
    """Try to place a label, demoting it if it will not fit. Returns True if
    anything was drawn."""
    fs = size or style.get("type.size_mm", 3.0)
    minfs = style.get("type.min_size_mm", 2.2)
    if placer is None:
        add_label(plan, text, x, y, style, rotate=rotate, size=fs,
                  anchor=anchor, person_id=person.id, colour=colour,
                  layer=layer, z=z)
        return True
    candidates = [text]
    short = person.short_name
    if short and short != text:
        candidates.append(short)
    if person.initials:
        candidates.append(person.initials)
    for i, cand in enumerate(candidates):
        s2 = fs if i == 0 else max(minfs, fs * (0.92 ** i))
        box = placer.box_for(cand, x, y, s2, rotate, anchor)
        if placer.free(box):
            placer.take(box)
            if i:
                placer.demoted += 1
            add_label(plan, cand, x, y, style, rotate=rotate, size=s2,
                      anchor=anchor, person_id=person.id, colour=colour,
                      layer=layer, z=z)
            return True
    placer.dropped += 1
    return False


def est_text_width(text: str, size_mm: float) -> float:
    """Cheap advance-width estimate; good enough for collision decisions.
    The exact width comes from fontTools only when baking outlines for laser."""
    return len(text) * size_mm * 0.52


def add_border(plan, style, cx, cy, R):
    if not style.get("ornament.border", True):
        return
    plan.add(Element(kind="path", layer="ENGRAVE", d=G.circle_path(cx, cy, R),
                     stroke=style.get("ornament.time_ring_colour", "#C9C0B0"),
                     stroke_width=0.5, fill="none", role="ornament", z=5))


def add_title(plan, style, x, y):
    t = style.get("ornament.title", "")
    if t:
        add_label(plan, t, x, y, style, size=style.get("type.size_mm", 3) * 2.2,
                  weight=600, z=90)
