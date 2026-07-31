"""Family Rings: one cell per couple, one ring per generation.

The chart this program is for. Founders at the centre, present day at the
rim, and every relationship readable without a legend:

    MARRIAGE    two names in one cell, stacked inside the ring band. Not a
                tie line, not a bracket, not a chord -- the cell IS the
                marriage, and there is nothing to misread.
    CHILDREN    one stem leaving the cell, to an arc that spans exactly that
                couple's children, with a tick down to each.
    SIBLINGS    everyone under one arc, and nobody else. Their own husbands
                and wives are on the row below, not in the row the arc runs
                along, so the arc cannot pick up a stranger.
    COUSINS     two arcs hanging off one cell. Follow either stem inward one
                ring and you are standing on the couple they share.
    REMARRIAGE  a second partner takes the next row down, and the stem to
                each set of children leaves from that partner's own row. You
                can see which mother a child belongs to at a glance.

Everything above is geometry from `couple_grid.py`; this file only serialises
it. If you find yourself computing an angle here that the grid could have
given you, the layout is in the wrong place.

WHY THE RINGS ARE UNEVEN. Each is sized to hold its own content: a ring with
remarriages in it needs a taller band than one without, and the widest name
in a generation decides how much radius that generation gets. Fixed rings
would mean obstructed text, which is the one thing a chart may never do.
"""
from __future__ import annotations

import math
from dataclasses import replace

from .. import geometry as G
from ..base import LayoutSettings, build_grid
from ..common import (PolarLabelPlacer, add_border, add_title, colour_for,
                      dash_for, est_text_width, fill_template, label_lines,
                      place_radial_label)
from ..plan import Canvas, Element, FontSpec, PlanMeta, RenderPlan
from ..registry import register

TAU = math.tau
_CURVE = 120        # samples along a stem that has to curve round

# TANG_SHARE = 0.90, TRIED AND REVERTED.
#
# Whether a ring is set around the circle or along its branches is decided
# below by asking whether the longest name on it fits the AVERAGE cell on
# it. That average flatters a crowded ring badly -- on the sample file's
# 461-person chart ring three averages 30 mm a cell and its names are really
# 4 mm apart -- so the obvious repair is to ask what share of the names fit
# the room they have, counting each one's distance to its neighbour in its
# own row. Measured, that is WORSE, and not marginally: names shortened to
# initials 30 -> 0, but names left off the chart altogether 42 -> 80. A
# radial name costs its whole length in radius, and once every ring claims
# that depth there is no sheet left to grow them into, so the placer drops
# what it cannot fit. Initials are a worse name; no name is worse than that.
#
# The average is not measuring what it appears to measure. It is a proxy for
# "is this ring roomy compared with the others", calibrated by use, and it
# earns its keep. Anything replacing it has to be scored on names ACTUALLY
# READABLE -- full, then shortened, then dropped -- not on the honesty of
# the test.


def _wrapped(d: float) -> float:
    """An angular difference brought into -pi..pi."""
    return (d + math.pi) % TAU - math.pi


def _unwrap(seq: list[float]) -> list[float]:
    """Angles carried past the seam instead of jumping back across it.

    Two children either side of the start angle are neighbours. Sorted as
    plain numbers they are 359.7 degrees apart, and the arc joining them
    gets drawn round the whole disc.
    """
    out = [seq[0]]
    for a, b in zip(seq, seq[1:]):
        out.append(out[-1] + _wrapped(b - a))
    return out


def _near(t: float, to: float) -> float:
    """The turn of `t` that lies closest to `to`."""
    return to + _wrapped(t - to)


def _mean_angle(seq: list[float]) -> float:
    u = _unwrap(seq)
    return sum(u) / len(u)


def _seg_cross(p, q, r, s) -> bool:
    """Do two segments cross, other than at an end?"""
    d1 = (q[0] - p[0], q[1] - p[1])
    d2 = (s[0] - r[0], s[1] - r[1])
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(den) < 1e-12:
        return False
    t = ((r[0] - p[0]) * d2[1] - (r[1] - p[1]) * d2[0]) / den
    u = ((r[0] - p[0]) * d1[1] - (r[1] - p[1]) * d1[0]) / den
    return 0.0 < t < 1.0 and 0.0 < u < 1.0


def _ang_gap(a0: float, a1: float, b0: float, b1: float) -> float:
    """Angle between two spans going round the circle; zero if they meet."""
    def inside(x, lo, hi):
        return (x - lo) % TAU <= (hi - lo) % TAU + 1e-12

    if (inside(b0, a0, a1) or inside(b1, a0, a1)
            or inside(a0, b0, b1) or inside(a1, b0, b1)):
        return 0.0
    return min((b0 - a1) % TAU, (a0 - b1) % TAU)


def _stem_runs(graph, g, wraps: bool):
    """Every stem the chart will draw, in grid coordinates.

    One definition, used TWICE: once before the rings are sized, to work out
    how much room between them the elbows are going to need, and again when
    they are drawn. Written out separately the two disagreed, and the rings
    were sized for fewer lanes than the drawing then asked for.

    Yields (uid, gen_k, anchor, parents, head_t, run) where `head_t` is
    where the stem leaves its couple and `run` is one group of that
    marriage's children who are actually side by side.
    """
    for uid, union in graph.unions.items():
        # THE UNION A CHILD BELONGS TO, and only that one. Somebody adopted,
        # fostered, or whose parentage is in doubt is a child of two unions
        # in the file, and drawing an arc from each put them in two families
        # as a full sibling of both -- Essie Sell was under the McGiverns'
        # arc and the Sells', which is exactly the "wrong people on the same
        # branch" the owner kept finding. `schema.sql` is explicit: the
        # layout follows the union marked primary, and the others are drawn
        # as a chord across the disc.
        kids = [c for c in union.children
                if c in g.slots and g.slots[c].row == 0
                and (graph.people[c].child_of or uid) == uid]
        parents = [p for p in union.partners if p in g.slots]
        if not kids or not parents:
            continue
        gen_k = g.slots[kids[0]].gen
        # THE PARENT ON THE RING THE CHILDREN HANG FROM, first; then the row
        # of the partner this family belongs to, so a second marriage is
        # visibly a second marriage.
        #
        # When both partners were born into the tree their two families can
        # sit at different depths -- marry your second cousin once removed
        # and one of you is a ring further out than the other. Only one of
        # the two can hold the cell the children hang beneath, and picking
        # the other one sent the stem across every ring in between: on the
        # sample file John Fenwick sat two rings OUTSIDE his own children,
        # so his bracket started out beyond them, ran inward through three
        # other families' descent lines and ended in mid-air. The chord in
        # section 5 is what says he is married to her; the bracket says
        # whose cell the children are in, and that is hers.
        anchor = max(parents,
                     key=lambda p: (g.slots[p].gen == gen_k - 1, g.slots[p].row))

        # WHERE THE STEM LEAVES FROM. Between the two people whose family it
        # is -- literally between, when they have a leaf each, because that
        # is what says the children are the children of that MARRIAGE and not
        # of one of the partners alone.
        #
        # Clamping this to the anchor's own leaf, as an earlier attempt did,
        # dragged it to one partner's name: on the owner's chart the stem
        # under "PH | Kathleen Holloway" left from PH's end rather than from
        # between them, and the same everywhere a couple had a leaf each.
        # It does NOT have to be the exact middle, though, and insisting on
        # that is what put a right-angled detour on nine stems. A couple has
        # WIDTH; a stem may leave from anywhere across it, and leaving from
        # the side its children are on removes the detour altogether while
        # still, plainly, coming from the two of them.
        same = [p for p in parents if g.slots[p].cell == g.slots[anchor].cell]
        pair = [p for p in same if g.slots[p].row == 0]
        if len(same) > 1 and len(pair) == len(same):
            ts = sorted(g.slots[p].tc for p in pair)
            lo_h = ts[0] + (ts[-1] - ts[0]) * 0.2
            hi_h = ts[0] + (ts[-1] - ts[0]) * 0.8
        else:
            sl = g.slots[anchor]
            lo_h = sl.tc - (sl.t1 - sl.t0) * 0.20
            hi_h = sl.tc + (sl.t1 - sl.t0) * 0.20

        # ---- ONE ARC PER CONTIGUOUS RUN OF THEM, NEVER ONE ARC OVER ALL ---
        #
        # THE RULE, and it is absolute: an arc may only ever cover children
        # of this marriage. Not a cousin, not a spouse, not a half-brother by
        # the other marriage.
        #
        # Drawn as a single arc from the first child to the last, it covers
        # whoever the layout put in between -- and the layout cannot always
        # avoid putting somebody there, because a couple belongs to two
        # sibling groups at once and can only be nested in one. So the chart
        # stopped promising what the layout cannot deliver: the children are
        # split into runs that ARE side by side, and each run gets its own
        # arc and its own stem. Two arcs off one couple say "two of them are
        # over here and two over there", which is true; one arc across the
        # gap says they are all brothers and sisters with strangers among
        # them, which is not.
        #
        # This is what was drawing Paul's wife and his half-brother as his
        # siblings, and Rosie, James, Heather and Anthony -- two marriages --
        # as one family of four.
        #
        # Contiguity is judged LEAF BY LEAF, not cell by cell. A couple with
        # a leaf each puts the husband and the wife at two different angles
        # on the same ring, so a run measured in whole cells swallowed the
        # wife -- and the arc over "Peter and his brother Richard" ran over
        # Kathleen, who is Peter's WIFE. She sits under the marriage rule
        # below, which is the only line that should ever join them.
        #
        # And A RING IS A CIRCLE: on a chart that goes the whole way round,
        # the last leaf on a ring is the neighbour of the first. Judged as a
        # straight list the seam cut families in half, and the arc over the
        # halves was then drawn between 0.2 degrees and 359.9 -- the entire
        # disc, the long way.
        order = [p for _, p in
                 sorted((g.slots[p].tc, p) for p in g.by_gen.get(gen_k, [])
                        if not g.slots[p].row)]
        if wraps and len(order) > 2:
            # A CLOSED RING HAS NO BEGINNING, so start reading it at its
            # widest hole. Read from the seam instead, a family lying across
            # the seam is cut in half; read from anywhere else, an arc can
            # end up spanning the widest empty stretch on the ring to reach
            # its own last child -- six Pargeters got one arc 273 degrees
            # long when 232 the other way round would have held them all.
            # Rotating first makes both faults impossible, and there is no
            # seam left to special-case.
            tcs = [g.slots[p].tc for p in order]
            gaps = [(b - a, i + 1) for i, (a, b) in enumerate(zip(tcs, tcs[1:]))]
            gaps.append(((1.0 - tcs[-1]) + tcs[0], 0))
            k = max(gaps)[1]
            order = order[k:] + order[:k]
        ks = set(kids)
        runs, cur = [], []
        for pid in order:
            if pid in ks:
                cur.append(pid)
            elif cur:
                runs.append(cur)
                cur = []
        if cur:
            runs.append(cur)
        for run in runs or [kids]:
            # THE MIDDLE UNLESS SLIDING BUYS SOMETHING. A stem leaves from the
            # centre of the cell, square under the name, because anything else
            # reads as a name that is not quite over its own branch -- and
            # that was reported before it was measured.
            #
            # The one case where it may move is a run of children the middle
            # does not reach: then, and only then, it slides as far as the
            # side of the cell to save a bracket.
            ts = [g.slots[c].tc for c in run]
            lo_r, hi_r = min(ts), max(ts)
            mid_h = (lo_h + hi_h) / 2
            if lo_r - 1e-9 <= mid_h <= hi_r + 1e-9:
                head_t = mid_h                      # already over them
            else:
                head_t = min(max((lo_r + hi_r) / 2, lo_h), hi_h)
            yield uid, gen_k, anchor, parents, head_t, run


def _elbow_lanes(graph, g, wraps: bool) -> dict[int, int]:
    """How many separate radii the elbows on each ring are going to need.

    An ELBOW is the tangential part of a stem: the bit that carries it round
    to children lying off to one side. Two of them at one radius, or one of
    them beside a sibling arc, and the eye joins them into a single line
    running from one family straight into the next. Keeping them apart costs
    radius, and the ring spacing has to be told about it BEFORE the rings
    are placed -- squeezed in afterwards they collapse back onto each other,
    which is what the `rings` preset was doing at four places.
    """
    spans: dict[int, list[tuple[float, float]]] = {}
    for _uid, gen_k, _a, _p, head_t, run in _stem_runs(graph, g, wraps):
        ts = [g.slots[c].tc for c in run]
        foot = min(max(head_t, min(ts)), max(ts))
        if abs(foot - head_t) > 1e-9:
            spans.setdefault(gen_k, []).append(
                (min(head_t, foot), max(head_t, foot)))
    out: dict[int, int] = {}
    for gen, xs in spans.items():
        lanes: list[list[tuple[float, float]]] = []
        for a, b in sorted(xs):
            for lane in lanes:
                if all(b < x or a > y for x, y in lane):
                    lane.append((a, b))
                    break
            else:
                lanes.append([(a, b)])
        out[gen] = len(lanes)
    return out


@register("radial_family", "Family Rings", "radial",
          "One cell per couple, one ring per generation, founders at the centre.",
          good_for="The whole family at once, when you want to trace who "
                   "married whom and which children are whose.",
          laser="good")
def radial_family(graph, s: LayoutSettings, style) -> RenderPlan:
    # ---- 0. the knobs worth turning --------------------------------------
    #
    # All of these are style tokens, so a preset can carry a whole look and
    # the control panel can offer them as sliders. See docs/OPTIONS.md.
    sib = float(style.get("layout.sibling_gap_cells", 0.10))
    fam = float(style.get("layout.family_gap_cells", 0.60))
    # `sibling_gap_frac` is the older, gentler control and still works: it
    # squeezes a sibling group toward its own centre, which is the same
    # intention said a different way.
    squeeze = float(style.get("layout.sibling_gap_frac", 0.0) or 0.0)
    if squeeze:
        sib *= max(0.0, 1.0 - min(squeeze, 0.95))
    g = build_grid(graph, replace(
        s, cells=True, sibling_gap=sib, family_gap=max(sib, fam),
        couple_leaf=str(style.get("couple.leaf", "auto")),
        min_cells=float(style.get("layout.min_cells", 0))))

    W = style.get("canvas.width_mm", 600)
    H = style.get("canvas.height_mm", W) if style.chose("canvas.height_mm") else W
    margin = style.get("canvas.margin_mm", 20)
    sheet_w, sheet_h = W, H       # the material. The chart may use less.
    cx, cy = W / 2, H / 2
    col = style.get("cells.stroke", "#22201D")
    lw = style.get("connectors.width_mm", 0.4)
    size = style.get("type.size_mm", 2.9)
    base_inner = float(style.get("layout.inner_radius_mm", 95))
    full = math.radians(style.get("layout.sweep_deg", 360))
    base_start = math.radians(style.get("layout.start_angle_deg", -90))
    sweep, start, inner = full, base_start, base_inner
    # Which way a radial name reads. "outward" always runs from the
    # middle out, the way the family grows -- you turn the chart, not
    # your head. "upright" never sets a name upside down on the page,
    # at the cost of half of them reading inward.
    face = str(style.get("labels.face", "outward")).lower()
    # And WHICH WAY UP. `radial` sets every name along its own branch,
    # reading outward; `tangential` sets them all around the ring;
    # `auto` picks per ring, which reads well but means neighbouring
    # rings can run in different directions -- and on the left and
    # lower parts of the disc a tangential name has to be turned to
    # stay upright, so it ends up reading the opposite way to its
    # neighbour. Radial is the default because it is CONSISTENT.
    orient = str(style.get("labels.orientation", "radial")).lower()

    if not g.slots:
        plan = RenderPlan(canvas=Canvas(W, H, style.get("canvas.background", "#FBF8F2")),
                          meta=PlanMeta(engine="radial_family",
                                        warnings=list(g.warnings)))
        return plan

    # ---- 0b. the padding belongs to the sweep, not to the content ---------
    #
    # The grid leaves a gap at the 0/360 seam so the first family and the last
    # do not fuse, and pads a sparse chart out so that one couple cannot own a
    # quadrant of it. Both of those are ANGLES, and the chart is about to
    # choose its own angle -- so take the padding off the content and put it
    # back on the sweep, where one decision controls it. Left in both places,
    # a small family drew across 60% of its own fan and left the rest blank.
    t_lo = min(sl.t0 for sl in g)
    t_hi = max(sl.t1 for sl in g)
    span = max(t_hi - t_lo, 1e-9)
    for sl in g:
        sl.t0 = (sl.t0 - t_lo) / span
        sl.t1 = (sl.t1 - t_lo) / span
    # The fan is always centred on the same bearing a full disc would have
    # been -- founders at the top, the family opening downward. Measure that
    # from the WHOLE turn, before the padding comes off, or shrinking the
    # sweep swings the whole chart round the sheet with it.
    mid = base_start + full / 2
    full *= span              # a whole turn, less the seam the grid asked for

    # ---- 1. how tall each ring has to be ---------------------------------
    #
    # Reserve the space a name needs BEFORE drawing anything, so nothing is
    # ever squeezed on top of anything else. How much it needs depends on
    # which way it is set, so the two decisions have to be made together:
    #
    #   tangential  reads around the ring. Costs its WIDTH in arc and only
    #               its height in radius, so the band is thin. Far easier to
    #               read, and the right answer wherever there is room.
    #   radial      reads along its own branch. Costs its LENGTH in radius,
    #               so the band has to be as deep as the longest name in that
    #               generation -- but it fits where tangential cannot.
    #
    # Decide per ring, because the inner rings are roomy and the rim is not.
    rows_in: dict[int, int] = {}
    widest: dict[int, float] = {}
    cells_in: dict[int, int] = {}
    seen_cell: set[tuple[int, str]] = set()
    for sl in g:
        rows_in[sl.gen] = max(rows_in.get(sl.gen, 1), sl.row + 1)
        person = graph.people[sl.pid]
        for text, sz, _ in label_lines(style, person, sl.gen, sl.order):
            widest[sl.gen] = max(widest.get(sl.gen, 0.0),
                                 est_text_width(text, sz))
        key = (sl.gen, sl.cell or sl.pid)
        if key not in seen_cell:
            seen_cell.add(key)
            cells_in[sl.gen] = cells_in.get(sl.gen, 0) + 1

    # ---- 1a. the partner nobody recorded ---------------------------------
    #
    # Every set of children has two parents. A union with children and only
    # one partner recorded is not somebody who had children alone, it is
    # somebody whose partner is not known YET -- and drawing one name with a
    # blank beside it reads as though there never was one.
    #
    # So the chart says "Unknown", dashed, in the row below. It is never
    # written to the file and never becomes a person: the existing
    # `unknown_partner` mark on the older design set that rule and this
    # follows it. The gap is a gap in the research, and a chart should show
    # it rather than hide it.
    unknown_at: dict[str, str] = {}
    for uid, u in graph.unions.items():
        if len([p for p in u.partners if p in g.slots]) >= 2:
            continue
        here = [p for p in u.partners if p in g.slots]
        kids_here = [c for c in u.children if c in g.slots]
        if not here or not kids_here:
            continue
        cid = g.slots[here[0]].cell or here[0]
        unknown_at.setdefault(cid, here[0])
    for cid, pid in unknown_at.items():
        gen = g.slots[pid].gen
        rows_in[gen] = max(rows_in.get(gen, 1),
                           max(g.slots[q].row for q in g.slots
                               if (g.slots[q].cell or q) == cid) + 2)

    # How much room a name really has: the distance to the NEXT couple along
    # the ring, not the width of its own cell. Every cell is one unit wide by
    # construction, so cell width says only how many cells the chart has --
    # it called a founder couple alone on the innermost ring "starved" when
    # the entire ring was theirs, and the chart grew a hole to fix it.
    centres: dict[int, list[float]] = {}
    for cid, mem in {(sl.gen, sl.cell or sl.pid): sl for sl in g}.items():
        centres.setdefault(cid[0], []).append(mem.tc)
    thin_in: dict[int, float] = {}
    for gen, ts in centres.items():
        ts.sort()
        thin_in[gen] = min((b - a for a, b in zip(ts, ts[1:])), default=1.0)

    # A row has to be as deep as the LABEL that goes in it, not as deep as
    # one line of type: a name with its dates under it is two lines, and
    # sizing rows by one printed the wife's name through her husband's.
    lab_h: dict[int, float] = {}
    for sl in g:
        h = sum(sz * 1.16 for _, sz, _ in
                label_lines(style, graph.people[sl.pid], sl.gen, sl.order))
        lab_h[sl.gen] = max(lab_h.get(sl.gen, 0.0), h)
    # 1.5, not 1.12: the label may be three lines deep (name, dates,
    # place) and the row under it has to start clear of the last of them,
    # with room left over for the rule that marks the marriage.
    # A RADIAL name runs along the radius, so the room a stacked row needs
    # is the name's LENGTH, not its height. Spacing rows by height while
    # setting them radially printed a wife straight through her husband --
    # the two rows of a couple overlapped by most of a name.
    # And `auto` is not an exception. Which way a ring is set is decided per
    # ring in 1a and, for one name that will not fit, per NAME by the placer;
    # a row pitch worked out from the global setting was right for a chart
    # told "radial" and wrong for the same chart told "auto", where a stacked
    # couple on a ring that came out radial had a name's length of overlap,
    # the marriage rule landed past the next ring, and the stem for their
    # children started a hundred millimetres outside the band it belongs to.
    def _pitch(gen: int, radial: bool) -> float:
        deep = radial and rows_in[gen] > 1
        return max(lab_h.get(gen, size * 1.16) * 1.5,
                   widest.get(gen, 0.0) + size * 1.3 if deep else 0.0)

    # A first guess only. The fit in 1a settles which rings end up radial and
    # replaces this with the pitch those rings actually need.
    base_pitch = {gen: _pitch(gen, orient == "radial") for gen in rows_in}
    stem = max(size * 2.2, style.get("layout.min_ring_gap_mm", 6.0))
    gens = sorted(rows_in)

    # How far apart two lines have to be before the eye stops joining them
    # up. One number, used by every rule and every elbow, because "far
    # enough apart" is one question however many places it gets asked. It
    # goes with the TYPE, not with the millimetre: two millimetres reads as
    # a gap on a postcard and as one thick line on a metre panel, and the
    # type size is the one thing that already tracks how big the chart is
    # meant to be looked at.
    lane_gap = max(2.4, lw * 4.0, size * 1.1)
    # And how many of those the gap above each ring has to hold. Reserved
    # here, before any radius is chosen, because there is no squeezing an
    # elbow in afterwards: it collapses onto the sibling arc beside it and
    # the two read as one line over two families.
    lanes_for = _elbow_lanes(graph, g, full >= TAU - 1e-9)
    lane_room = {gen: (lanes_for.get(gen + 1, 0) + 1) * lane_gap
                 if lanes_for.get(gen + 1) else 0.0 for gen in gens}

    # ---- 1a. how far round to go, and how big the hole is ----------------
    #
    # These are ONE decision, not two, and the old code made them separately
    # and got both wrong. A small family spread over a full disc puts three
    # siblings forty degrees apart; drawn as a narrow fan it wastes most of
    # the sheet; and the hole in the middle has to be big enough that the
    # OLDEST ring -- which is the innermost, where there is least room -- can
    # hold its couples without crowding.
    #
    # So lay the chart out at several sweep angles and keep the best. Two
    # things decide "best", in this order:
    #
    #   1. NO STARVED CELL. Measure the TIGHTEST cell on the chart, not the
    #      average: the average is flattered by a narrow fan, where three
    #      cells share a rim a metre long and a fourth is a sliver. Once
    #      every cell clears `min_cell_arc_mm` this stops counting, because
    #      arc beyond legible is worth less than the two below.
    #   2. NAMES THAT READ AROUND THE RING. A ring whose cells are too narrow
    #      for a name has to set it radially instead, along its own branch --
    #      legible, but harder work, and it costs the ring a lot of depth.
    #   3. BIG. Of the angles that tie, take the one whose RINGS cover most
    #      sheet. Not the one with the largest radius: a thirty-degree needle
    #      has an enormous radius and draws a chart the width of a ruler.
    #      Area counts the hole in the middle for nothing, so it cannot be
    #      gamed by pushing everything out to the rim.
    #
    # On a square sheet a small family comes out as a fan of the angle it
    # actually needs and a four-hundred-person family comes out as the full
    # disc, which is what each of them wants.
    cap = float(style.get("layout.max_cell_deg", 12.0))
    widest_cell = max(sl.t1 - sl.t0 for sl in g)
    # 0 means "work it out from the type": about three characters of arc,
    # which is the point below which a name has nowhere to go.
    min_arc = float(style.get("layout.min_cell_arc_mm", 0) or 0) or size * 3.2
    panel = bool(style.chose("canvas.width_mm"))
    # A name is centred on its cell, so the one on the end of a fan hangs
    # half its width out past the edge of the sector. Pay for that in the
    # fit, not afterwards, or the chart reports itself over the panel.
    over = 0.5 * max(widest.values(), default=0.0)
    # what reaches past the outermost ring, radially
    pad_r = (size * 2.6) if orient == "radial" else size * 0.9

    def solve(sweep: float, tighten: float = 1.0, deep: bool = True) -> dict:
        """Lay the whole chart out at one sweep and hole size, and report.

        Returns everything the drawing needs, so the search can try a shape
        and keep the winner rather than working it out a second time.
        """
        start = mid - sweep / 2                   # same bisector as the disc
        # The hole has to be big enough that the innermost ring's own
        # circumference can hold its couples, and no bigger. Size it from
        # the COUNT of them, not from the narrowest: one thin cell is thin
        # because that branch is small, and inflating the whole chart to
        # widen it leaves a hole you could lose a plate in.
        #
        # It works downward too. A descendancy chart starts from one couple,
        # so its innermost ring holds a single cell and wants a much smaller
        # hole than the style's default -- which is why `tighten` is a search
        # variable rather than a constant: rings 63 mm apart became 88 mm.
        inner = max(base_inner * tighten, cells_in[gens[0]] * min_arc / sweep
                    if sweep > 0 else 0.0)
        inner = min(inner, min(W, H) * 0.34)      # never eat the whole sheet

        def radii(bands):
            r, out = inner, {}
            for gen in gens:
                out[gen] = r
                r += bands[gen]
            return out, r - stem

        def box(r_out):
            """The bounding box of the sector, with the label overhang.

            `pad_r` is what sticks out past the last ring: a radial name runs
            outward from its row, and the marriage rule sits past the end of
            that. Leaving it out fitted the rings to the sheet and then drew
            the last name over the edge.
            """
            r_out = r_out + pad_r
            p = math.atan2(over, max(r_out, 1e-6)) if sweep < full - 1e-9 else 0.0
            return _sector_bounds(inner, r_out, start - p, start + sweep + p)

        def fill(bands):
            """Grow to the sheet, and never overrun it.

            Measured on the SECTOR the chart actually occupies, not on a
            disc. A quarter-circle fan fits about twice the radius into the
            same square; a full circle behaves exactly as before, because
            its sector box IS the disc.
            """
            if not panel:
                return bands
            for _ in range(8):
                _, r_now = radii(bands)
                if r_now <= inner:
                    break
                x0, y0, x1, y1 = box(r_now)
                k = min((W - 2 * margin) / max(x1 - x0, 1e-6),
                        (H - 2 * margin) / max(y1 - y0, 1e-6))
                # Only ever stop with room to spare. `abs(k - 1) < tol`
                # stopped on either side of the mark, and a fifth of a per
                # cent of a 1200 mm panel is 2 mm -- which the chart then
                # reported itself over by, correctly.
                if 1.0 <= k < 1.002:
                    break
                grow = ((inner + (r_now - inner) * k) - inner) / (r_now - inner)
                bands = {gen: bands[gen] * grow for gen in gens}
            return bands

        # A first guess, then grow to fill the sheet, then let any ring that
        # cannot read around the circle claim the depth a radial name needs.
        pitch = dict(base_pitch)      # each candidate settles its own
        band = {gen: rows_in[gen] * pitch[gen] + stem + lane_room[gen]
                for gen in gens}
        tang = {gen: True for gen in gens}
        for _ in range(4):
            band = fill(band)
            ring_try, _ = radii(band)
            changed = False
            for gen in gens:
                arc = (sweep * ring_try[gen]) / max(cells_in.get(gen, 1), 1)
                fits = arc >= widest.get(gen, 0.0) * 1.08
                # The band has to be sized for the way the names will ACTUALLY
                # be set. Sizing for tangential and then drawing radially left
                # the ring a name-length too shallow, and the marriage rule --
                # which sits past the end of the name -- fell outside the cut.
                if orient in ("radial", "tangential"):
                    fits = orient == "tangential"
                # And the ROW PITCH with it. A radial name is as deep as it
                # is long, so a ring with a couple stacked in it needs a
                # name-length per row, not a line-height per row. Worked out
                # once from the global setting, `auto` charts overlapped the
                # two rows of every stacked couple on any ring that came out
                # radial -- and their marriage rule and their children's stem
                # went with it, out past the ring beyond.
                pit = _pitch(gen, deep and not fits)
                floor = rows_in[gen] * pit + stem + lane_room[gen]
                if not fits:
                    # the name, plus the marriage rule that sits past its end
                    floor = max(floor, widest.get(gen, 0.0) + stem
                                + size * 1.2 + lane_room[gen])
                if (tang[gen] != fits or band[gen] < floor - 0.01
                        or abs(pitch[gen] - pit) > 0.01):
                    changed = True
                tang[gen], pitch[gen] = fits, pit
                band[gen] = max(band[gen], floor)
            if not changed:
                break
        band = fill(band)
        ring_r, R = radii(band)

        # The tightest cell anywhere, in millimetres of arc. This is the one
        # number that says whether a name can be got into its own cell.
        tight = min(sweep * thin_in[gen] * ring_r[gen] for gen in gens)
        return {"sweep": sweep, "start": start, "inner": inner, "band": band,
                "ring_r": ring_r, "R": R, "tangential": tang, "box": box(R),
                "pitch": pitch,
                "read": tight / min_arc if min_arc > 0 else 1.0,
                "tang": sum(tang.values()) / len(gens),
                # How much of the sheet the RINGS cover. The hole in the
                # middle counts for nothing, which is what stops a narrow
                # fan winning by pushing everything out to the rim.
                "area": 0.5 * sweep * (R * R - inner * inner),
                # HOW FAR OVER THE SHEET, in millimetres. Nothing used to
                # ask: `fill` shrinks a chart to the panel but cannot go
                # below the depth its own rings need, so a chart that
                # genuinely did not fit was returned anyway and no
                # candidate that DID fit was preferred to it.
                "over": (max(0.0, (box(R)[2] - box(R)[0]) + 2 * margin - sheet_w,
                             (box(R)[3] - box(R)[1]) + 2 * margin - sheet_h)
                         if panel else 0.0)}

    # The cap is the user's own upper bound on how wide one couple may get:
    # it is what keeps three brothers close together instead of a third of a
    # circle apart. The search may go tighter than it, never wider.
    cap_sweep = full
    if cap > 0 and widest_cell > 0:
        cap_sweep = min(full, math.radians(cap) / widest_cell)

    # A sweep of anything but a whole turn is the user saying "draw this arc
    # and no more" -- honour it exactly. (Every preset sets `sweep_deg`, so
    # asking whether it was set says nothing; asking what it says does.)
    tries = [cap_sweep]
    if panel and full >= 2 * math.pi - 1e-9:
        tries += [math.radians(d) for d in range(30, 361, 10)
                  if math.radians(d) < cap_sweep - 1e-9]
    holes = [1.0, 0.62, 0.38] if panel else [1.0]
    best = None
    for sw in tries:
        for hole in holes:
            # `deep` gives a ring set radially a full name-length per row so
            # a stacked couple cannot overlap. It costs depth, and on a
            # small sheet there may not be any -- so try it, and let a
            # shallow candidate that FITS beat a deep one that does not.
            for deep in (True, False):
                got = solve(sw, hole, deep)
                key = (-round(got["over"], 1),
                       round(min(got["read"], 1.0), 2), round(got["tang"], 3),
                       round(got["area"], 0))
                if best is None or key > best[0]:
                    best = (key, got)
                if got["over"] <= 0.0:
                    break
    fit = best[1]
    sweep, start, inner = fit["sweep"], fit["start"], fit["inner"]
    band, ring_r, R = fit["band"], fit["ring_r"], fit["R"]
    tangential, pitch = fit["tangential"], fit["pitch"]

    # Put the sector where it belongs. A fan is not centred on the middle of
    # its own bounding box, so centring it as if it were leaves the chart
    # sitting off to one side with the empty half of the disc still paid for.
    #
    # And the sheet is a MAXIMUM, not a shape to fill. A fan that needs
    # 760 x 440 gets a 760 x 440 canvas, cut from the metre panel with the
    # rest left on the roll -- rather than a metre square with a third of it
    # blank, which is what "the chart looks sparse" actually was.
    bx0, by0, bx1, by1 = fit["box"]
    pad_t = (math.atan2(over, max(R, 1e-6))
             if sweep < full - 1e-9 else 0.0)      # the label overhang, in angle
    need_w, need_h = (bx1 - bx0) + 2 * margin, (by1 - by0) + 2 * margin
    W = min(W, need_w) if panel else need_w
    H = min(H, need_h) if panel else need_h
    cx, cy = (W - (bx1 - bx0)) / 2 - bx0, (H - (by1 - by0)) / 2 - by0

    def row_r(sl) -> float:
        return ring_r[sl.gen] + sl.row * pitch[sl.gen]

    def theta(t: float) -> float:
        return start + t * sweep

    def rule_r(sl) -> float:
        """The radius of the rule that means "married", for this row.

        Past the end of the name, in the gap before the next row. Defined
        once and used by BOTH the rule and the stem, because the stem for a
        couple with a leaf each has to START on that rule -- it is the line
        their children come from. Computed separately, the stem began inside
        it and crossed it at right angles, which is the one shape a chart
        must never make: two lines that mean different things, crossing.
        """
        return row_r(sl) + reach(sl.gen) + size * 0.55

    def reach(gen: int) -> float:
        """How far a name actually extends along the radius.

        Its HEIGHT if it is set around the ring, its LENGTH if it is set
        along the branch. The marriage rule is placed past this, and using
        the height for a radial name put the rule straight through it.
        """
        if want_orient(gen) == "radial":
            return widest.get(gen, 0.0)
        return lab_h.get(gen, 0.0)

    # A chart that goes the whole way round has no ends: the last leaf on a
    # ring is the neighbour of the first, and every span has to be measured
    # the short way across the seam rather than the long way back.
    wraps = sweep >= TAU - 1e-9

    def band_top(gen: int) -> float:
        """The furthest out a ring's own linework may reach.

        Past this it is in the band where the NEXT ring's sibling arcs live,
        and a rule that lands beside one of those touches it. Fred Sell's
        marriage rule came within a millimetre of the arc over Winnie and
        Theresa McGivern, which on the sheet made him one of them.
        """
        nxt = ring_r.get(gen + 1)
        if nxt is None:
            return math.inf
        return max(r_top(gen), nxt - stem * 0.55 - lane_gap * 1.6)

    def r_top(gen: int) -> float:
        """Where a ring's own ink ends and the clear gap begins.

        How far the names actually reach, which depends on WHICH WAY THEY
        ARE SET: a ring set radially is as deep as a name is long, and
        sizing it from the label height alone said the clear gap started a
        whole name earlier than it does.

        Not the depth the ring was allotted in 1a. That grows to fill the
        sheet, so it says the ink runs right up to the next ring and leaves
        no gap at all -- and elbows placed from it were pushed out over the
        names of the ring they were meant to be clearing.
        """
        rows = max(1, rows_in.get(gen, 1))
        return (ring_r[gen] + (rows - 1) * pitch[gen]
                + reach(gen) + size * 1.4)

    def want_orient(gen: int) -> str:
        if orient in ('radial', 'tangential'):
            return orient
        return 'tangential' if tangential[gen] else 'radial'

    plan = RenderPlan(
        canvas=Canvas(W, H, style.get("canvas.background", "#FBF8F2"), "circle"),
        meta=PlanMeta(engine="radial_family", style=style.get("id", ""),
                      people=len(g.slots), generations=g.max_gen + 1,
                      year_min=int(g.year_min), year_max=int(g.year_max),
                      warnings=list(g.warnings),
                      # WHERE THE MIDDLE IS. A fan is recentred on the box
                      # round its own sector, so it is not the middle of the
                      # sheet, and anything measuring the chart in radius and
                      # angle has to be told. Assuming the sheet centre made
                      # `tools/ink_check.py` report radii forty millimetres
                      # out on any chart that was not a full disc.
                      extra={"centre_mm": [cx, cy], "outer_r_mm": R,
                             "start_rad": start, "sweep_rad": sweep,
                             "ring_r_mm": {str(k): v for k, v in ring_r.items()}}))
    # What the chart NEEDS is the box round its sector, not the diameter of
    # the disc it was cut from -- a fan asked for a metre of sheet it was
    # never going to touch, and then reported itself over the panel by it.
    # Both directions, separately: a fan on a 600x900 sheet is not over the
    # panel because it is 700 mm wide, if the 700 is the way the 900 runs.
    short = max(need_w - sheet_w, need_h - sheet_h, 0.0)
    plan.meta.extra["fit"] = {
        "required_mm": round(max(need_w, need_h), 1),
        "chart_mm": [round(need_w, 1), round(need_h, 1)],
        "panel_mm": round(min(sheet_w, sheet_h), 1),
        "fits": short <= 0.5,
        "shortfall_mm": round(short, 1),
        "sweep_deg": round(math.degrees(sweep), 1),
        "inner_mm": round(inner, 1),
        "cell_arc_mm": round(fit["read"] * min_arc, 1),
        "ring_pitch_mm": round(min(band.values()), 1),
        "min_pitch_mm": round(min(pitch.values()) + stem, 1),
        "pitch_ok": True,
        "people": len(g.slots),
    }

    # The direct line, picked out in colour. It is a highlight and not a
    # relationship -- every line it recolours is drawn either way -- so it is
    # a setting, and turning it off leaves the chart complete rather than
    # missing something. `thread.enabled`, off by default in `plain`.
    thr = _thread(graph, s) if style.get("thread.enabled", True) else set()
    tcol = style.get("thread.colour", "#9B3A2E")
    tw = style.get("thread.stroke_width_mm", 1.2)

    cells: dict[str, list] = {}
    for sl in g:
        cells.setdefault(sl.cell or sl.pid, []).append(sl)

    # ---- 2. the families, and where they come together --------------------
    #
    # At the inner rings a two-hundred-name chart is a dozen separate
    # families. Every marriage joins two of them, and by the outermost ring
    # there is one. Nothing in the linework says so -- a stem to a couple
    # looks the same whether the partner brought a documented line with them
    # or married in from nowhere.
    #
    # So tint the ground. Each family gets a wedge running outward from its
    # founders, and where a marriage brings two families together the two
    # wedges TAPER INTO ONE CELL and continue as a single wedge in the blend
    # of their two colours. That is the shape of the family, drawn once, in
    # the one place on the chart where nothing else is competing for the
    # ink: behind everything, on the layer the cutter never sees.
    if style.get("family.wedges", True) and len(gens) > 1:
        _wedges(plan, graph, g, cells, gens, ring_r, rows_in, pitch, stem,
                cx, cy, theta, style)

    # ---- 3. the couple cells ---------------------------------------------
    #
    # A hairline under every row but the last: it reads as "and", which is
    # exactly what it means, and it stops two names in one cell running
    # together when the type is small.
    rule_top: dict[str, float] = {}      # the outermost rule drawn in a cell
    # AND WHERE EACH ONE IS, by the pair it joins. A stem starts on the rule
    # that means "these two married" -- that rule is the line their children
    # come from. Started at the outermost rule in the CELL instead, the stem
    # for the first marriage of somebody who married twice began at the
    # radius of the second one and hung a couple of millimetres above its
    # own, attached to nothing.
    rule_at: dict[frozenset, float] = {}

    for cid, members in cells.items():
        members.sort(key=lambda x: (x.row, x.tc))
        split = len(members) > 1 and all(m.row == 0 for m in members)
        if split:
            # TWO leaves, one per partner, so each ancestry sits inside the
            # partner it belongs to. The marriage is the tie between them --
            # the one place this design has to draw a line for it.
            #
            # WHERE SOMEBODY MARRIED TWICE there are three names in the cell
            # and two rules. Drawn at one radius they meet end to end at the
            # person they have in common and read as ONE line under all three
            # -- the shape of a sibling arc, saying the two spouses were
            # brother and sister.
            #
            # Offsetting the second one radially fixed the meaning and looked
            # wrong: two ties at two heights under one cell, for no reason the
            # chart ever explains. So they sit at the SAME radius and a short
            # radial divider is drawn across the person they share. One tie
            # each side of the divider, both level, and the tick says where
            # one marriage stops and the next begins.
            step = 0.0
            for k, (a, b) in enumerate(zip(members, members[1:])):
                # BELOW the names, in the gap, never through them. At half
                # the label height this ran straight through "Kathleen
                # Holloway" -- the rule that means "married" was striking out
                # the name it was about.
                r = rule_r(a) + k * step
                rule_top[cid] = max(rule_top.get(cid, 0.0), r)
                rule_at[frozenset((a.pid, b.pid))] = r
                plan.add(Element(kind="path", layer="ENGRAVE",
                                 d=G.short_arc(cx, cy, r, theta(a.tc),
                                               theta(b.tc)),
                                 stroke=style.get("lines.marriage_colour", col),
                                 stroke_width=lw * 0.9, fill="none",
                                 person_id=a.pid, line_id=cid,
                                 role="marriage", z=8))
                if k:
                    # the divider, across the name the two marriages share
                    plan.add(Element(
                        kind="path", layer="ENGRAVE",
                        d=G.polyline([G.polar(cx, cy, r - size * 0.5,
                                              theta(a.tc)),
                                      G.polar(cx, cy, r + size * 0.5,
                                              theta(a.tc))]),
                        stroke=style.get("lines.marriage_colour", col),
                        stroke_width=lw * 0.9, fill="none",
                        person_id=a.pid, line_id=cid,
                        role="marriage_divider", z=8))
            continue
        t0, t1 = theta(members[0].t0), theta(members[0].t1)
        mid = (t0 + t1) / 2
        for k, sl in enumerate(members[:-1]):
            # in the GAP between two names, never through one of them: a rule
            # at the middle of the row pitch struck the dates out.
            gap = max(pitch[sl.gen] - reach(sl.gen), size * 0.9)
            floor_r = row_r(sl) + reach(sl.gen) + size * 0.3
            r = max(floor_r, min(row_r(sl) + reach(sl.gen) + gap * 0.45,
                                 band_top(sl.gen)))
            rule_top[cid] = max(rule_top.get(cid, 0.0), r)
            rule_at[frozenset((sl.pid, members[k + 1].pid))] = r
            # Wide enough that a stem leaving from the side its children are
            # on still starts ON the rule -- the head may slide a fifth of
            # the cell either way -- and no wider, because a rule that
            # overhangs the names it joins reads as something else.
            half = (t1 - t0) * 0.24
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=G.arc_path(cx, cy, r, mid - half, mid + half),
                             stroke=style.get("lines.marriage_colour", col),
                             stroke_width=lw * 0.6, fill="none",
                             person_id=sl.pid, role="marriage", z=8))

    # ---- 4. one stem per family, one arc per sibling group ----------------
    #
    # ONE line for each fact, and never two. The direct line is not drawn as
    # a second path laid over the first -- it is the SAME stem, arc and tick,
    # in a different colour. A highlight drawn on top of the linework is
    # exactly the doubled-up clutter this chart exists to avoid.
    # Nothing is drawn in this pass. Every stem is worked out first, because
    # the tangential part of one -- the ELBOW, which carries it round to
    # children lying off to one side -- has to be given a radius no other
    # line on that ring is using, and that cannot be settled one family at a
    # time. See 4b.
    jobs: list[dict] = []
    seen_kids: set[str] = set()
    for uid, gen_k, anchor, parents, head_t, run in _stem_runs(graph, g, wraps):
        if gen_k - 1 not in ring_r:
            continue
        r_arc = ring_r[gen_k] - stem * 0.55

        # WHATEVER the cell looks like, the stem starts outside every rule
        # drawn in it. Worked out per case it was right for a couple with a
        # leaf each and wrong for a stacked one and for a partner nobody
        # recorded, and a stem crossing the rule that means "married" is two
        # lines meaning different things, crossing.
        # ...and never past the end of its OWN RING. On a sheet too small to
        # give a radial ring a name-length per row, the rules in a deep cell
        # land beyond the ring outside it, and a stem starting from them
        # began a hundred millimetres out with its elbow among somebody
        # else's names. A ring's linework stays in its own band.
        gen_a = g.slots[anchor].gen
        r_from = rule_at.get(frozenset(parents))
        if r_from is None:
            # Nobody to marry, or a partner who is not on the chart. The
            # dashed rule that names the partner nobody recorded is drawn at
            # exactly this radius, so the stem starts on that instead.
            r_from = rule_r(g.slots[anchor])
        # ...but never INSIDE the anchor's own name. A stacked couple's rule
        # sits BETWEEN their two names, so starting the stem on it would run
        # it straight up through the outer one.
        r_from = max(min(r_from, band_top(gen_a)), rule_r(g.slots[anchor]))

        line = (all(p in thr for p in parents[:1])
                and any(c in thr for c in run))
        # Carried past the seam rather than jumped back across it, so a span
        # is measured the way it is drawn.
        rt = _unwrap([theta(g.slots[c].tc) for c in run])
        lo, hi = min(rt), max(rt)
        head = _near(theta(head_t), (lo + hi) / 2)
        # the stem reaches THIS run; a run beyond the couple's own leaf gets
        # the elbow, which is what the elbow is for
        jobs.append(dict(gen=gen_k, uid=uid, anchor=anchor, run=run,
                         r_from=r_from, r_arc=r_arc, head=head,
                         foot=min(max(head, lo), hi), lo=lo, hi=hi,
                         colour=tcol if line else col,
                         width=tw if line else lw))
        for c in run:
            if c in seen_kids:
                continue
            seen_kids.add(c)
            tc = theta(g.slots[c].tc)
            person = graph.people[c]
            on = c in thr and line
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=G.polyline([G.polar(cx, cy, r_arc, tc),
                                           G.polar(cx, cy, ring_r[gen_k], tc)]),
                             stroke=tcol if on else colour_for(person, g.slots[c],
                                                               style, graph),
                             stroke_width=tw if on else lw,
                             dash=dash_for(person, style),
                             fill="none", person_id=c, union_id=uid,
                             role="thread" if on else "branch", z=10))


    # ---- 5. a cousin marriage, drawn as a chord --------------------------
    #
    # When both partners were born into the tree only one can hold the cell.
    # The chord says so, and it is the one relationship on this chart that
    # cannot be read off adjacency.
    if style.get("lines.marriage", True):
        for union in graph.unions.values():
            ps = [p for p in union.partners if p in g.slots]
            if len(ps) != 2:
                continue
            a, b = ps
            if g.slots[a].cell == g.slots[b].cell:
                continue                       # already one cell: nothing to draw
            ta, tb = theta(g.slots[a].tc), theta(g.slots[b].tc)
            ra, rb = row_r(g.slots[a]), row_r(g.slots[b])
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=G.polyline(_chord(cx, cy, ra, ta, rb, tb)),
                             stroke=style.get("lines.marriage_colour", "#8A6F4E"),
                             stroke_width=lw * 0.8, fill="none",
                             dash=style.get("lines.marriage_dash", "1.6,1.2"),
                             person_id=a, role="married_across", z=7))

    # ---- 6. names ---------------------------------------------------------
    placer = PolarLabelPlacer()
    # THE STEMS GO DOWN FIRST -- not drawn, reserved. A stem leaves its couple
    # along a radius and crosses the whole gap to the next ring; the placer
    # knew nothing about it and set a neighbour's dates in the corridor, so
    # the line went through the type. Booking the corridor before any name is
    # placed makes the names move instead, which is the right way round: a
    # name can go somewhere else, a descent line cannot.
    #
    # ORDER OF PRECEDENCE, and it is deliberate. The name of a partner nobody
    # recorded goes down FIRST: it sits in the couple's own cell, exactly
    # where their stem starts, so a corridor booked ahead of it simply
    # deleted it. Then the corridors. Then every other name, which moves.
    for cid, pid in unknown_at.items():
        sl = g.slots[pid]
        deep = max(g.slots[q].row for q in g.slots if (g.slots[q].cell or q) == cid)
        r_row = ring_r[sl.gen] + (deep + 1) * pitch[sl.gen]
        t0, t1 = theta(sl.t0), theta(sl.t1)
        r_dash = ring_r[sl.gen] + deep * pitch[sl.gen] + reach(sl.gen) + size * 0.55
        half = abs(t1 - t0) * 0.24      # as wide as the stem head may slide
        plan.add(Element(kind="path", layer="ENGRAVE",
                         d=G.arc_path(cx, cy, r_dash, theta(sl.tc) - half,
                                      theta(sl.tc) + half),
                         stroke=style.get("lines.marriage_colour", col),
                         stroke_width=lw * 0.6, fill="none",
                         dash=style.get("lines.marriage_dash", "1.6,1.2"),
                         person_id=pid, role="unknown_partner", z=8))
        place_radial_label(
            plan, placer, graph.people[pid],
            [(style.get("labels.unknown", "Unknown"),
              size * 0.92, style.get("type.colour", col))],
            theta(sl.tc), r_row, cx, cy, style,
            flip=_flip(theta(sl.tc)) and face == "upright", face=face,
            orientation=want_orient(sl.gen),
            arc_available=sweep * (sl.t1 - sl.t0) * r_row)

    for job in jobs:
        placer.take(job["head"], job["r_from"],
                    max(job["r_arc"] - job["r_from"], 0.0), lw * 3.0)
    for sl in sorted(g, key=lambda x: (x.gen, x.tc, x.row)):
        person = graph.people[sl.pid]
        t = theta(sl.tc)
        arc = abs(sl.t1 - sl.t0) * sweep * max(row_r(sl), 1e-3)
        lines = label_lines(style, person, sl.gen, sl.order)
        # PER RING, not per name. Offered `auto` here the placer is greedy:
        # it tries tangential for every name, the roomy cells take the wide
        # slots first and their neighbours are left with none -- 27 names
        # shortened to initials and 9 dropped altogether, against 2 and 0
        # when the ring decides once for all of them.
        place_radial_label(plan, placer, person, lines, t, row_r(sl), cx, cy,
                           style, flip=_flip(t) and face == "upright",
                           face=face,
                           orientation=want_orient(sl.gen),
                           arc_available=arc)

    plan.meta.extra["labels_hidden"] = placer.dropped

    # ---- 4b. a lane of its own for every elbow ----------------------------
    #
    # LAST, after the names, because an elbow has to go round where they
    # ACTUALLY LANDED. `reach` is one estimate for a whole ring and the
    # placer works name by name: on a ring the fit called tangential, a name
    # that will not fit is set radially instead and runs a whole name-length
    # further out than the estimate said. Nine elbows were routed straight
    # through nine names on exactly that difference.
    ink_top: dict[int, float] = {}
    for el in plan.elements:
        if el.kind != "text" or not el.text:
            continue
        sz = el.font.size_mm if el.font else size
        w, h = est_text_width(el.text, sz), sz * 1.15
        anc = el.font.anchor if el.font else "middle"
        dx = {"start": 0.0, "middle": -w / 2, "end": -w}.get(anc, -w / 2)
        a = math.radians(el.rotate)
        ca, sa = math.cos(a), math.sin(a)
        far = max(math.hypot(el.x + lx * ca - ly * sa - cx,
                             el.y + lx * sa + ly * ca - cy)
                  for lx, ly in ((dx, -h / 2), (dx + w, -h / 2),
                                 (dx + w, h / 2), (dx, h / 2)))
        base = math.hypot(el.x - cx, el.y - cy)
        own = [k for k, rr in ring_r.items() if rr <= base + 0.5]
        if own:
            k = max(own, key=lambda i: ring_r[i])
            ink_top[k] = max(ink_top.get(k, 0.0), far)

    # TWO LINES THAT TOUCH ARE ONE LINE. That sentence is the whole of this
    # section, and it is the fault the owner kept finding and I kept saying
    # was fixed.
    #
    # An elbow used to be drawn at `r_arc` -- the exact radius of the sibling
    # arcs on that ring. Every check passed, because every check asked
    # whether two arcs OVERLAP. These did not overlap. They ABUTTED, end to
    # end, at the same radius, and on the sheet that is a single unbroken
    # line running from one family straight into the next:
    #
    #   * Paul, Derek and Gorden's arc ran on into the stem carrying Barry
    #     Viney, their HALF-brother by a different mother -- four children on
    #     one branch, which is what the owner photographed;
    #   * the arc over Peter and his brother Richard ran on into the stem
    #     bringing Kathleen down from her own parents, putting a man and his
    #     WIFE on one parental branch;
    #   * James and Rosie's stem met Anthony and Heather's, drawing two
    #     marriages as one family of four.
    #
    # So an elbow now travels in the clear band between the two rings, in a
    # lane no other elbow on that ring is using, and drops out to `r_arc`
    # only at the point it is joining. A radial line crossing an arc at right
    # angles reads as a junction, which is what it is. Two arcs at one radius
    # read as a claim about a family, which is not.
    ring_floor: dict[int, float] = {}
    for job in jobs:
        ring_floor[job["gen"]] = max(
            ring_floor.get(job["gen"], 0.0),
            r_top(job["gen"] - 1), job["r_from"],
            ink_top.get(job["gen"] - 1, 0.0) + size * 0.4) 
    ring_floor = {k: v + lane_gap for k, v in ring_floor.items()}

    ring_lanes: dict[int, list[list[tuple[float, float]]]] = {}
    for job in sorted(jobs, key=lambda j: (j["gen"], min(j["head"], j["foot"]))):
        if abs(job["foot"] - job["head"]) < 1e-9:
            job["lane"] = -1                    # straight out; no elbow at all
            continue
        a, b = sorted((job["head"], job["foot"]))
        clear = lane_gap / max(job["r_arc"], 1.0)
        ring = ring_lanes.setdefault(job["gen"], [])
        for k, lane in enumerate(ring):
            if all(_ang_gap(a, b, x, y) > clear for x, y in lane):
                lane.append((a, b))
                job["lane"] = k
                break
        else:
            ring.append([(a, b)])
            job["lane"] = len(ring) - 1

    # WHERE THE SPOKES ARE. A stem's spoke is the radial part, running from
    # its couple straight out to its children; an elbow crossing the band has
    # to get past every one of them that lies in its way. Where a family's
    # children are directly outside them -- the ordinary case -- the whole
    # stem is a spoke, and there are a great many of them.
    spokes: dict[int, list[tuple[float, str]]] = {}
    for job in jobs:
        spokes.setdefault(job["gen"], []).append((job["head"], job["uid"]))
        if job["lane"] >= 0:
            spokes[job["gen"]].append((job["foot"], job["uid"]))

    for job in jobs:
        r_arc, head, foot = job["r_arc"], job["head"], job["foot"]
        if job["lane"] < 0:
            d_stem = G.polyline([G.polar(cx, cy, job["r_from"], head),
                                 G.polar(cx, cy, r_arc, head)])
        else:
            # AN ELBOW HUGS THE RING IT LEAVES, not the one it is going to.
            # Stacked inward from `r_arc` the first lane sat two millimetres
            # off the sibling arcs, and at metre scale two lines two
            # millimetres apart are one thick line -- the fault back again,
            # passing the check by a fraction of a millimetre. Run out from
            # just above the parents instead and the whole gap between the
            # rings separates an elbow from any arc it must not touch.
            #
            # Lanes are `lane_gap` apart where there is room and evenly
            # spread across whatever there is where there is not. Two must
            # never land on one radius: letting them collapse when the band
            # is tight brought the fault straight back on the inner rings.
            # ONE BASE PER RING, so two lanes on it are exactly `lane_gap`
            # apart. Worked out per job from that job's own start radius, two
            # reaches on one ring came out 0.7 mm apart and read as one line
            # -- the very fault the lanes exist to prevent.
            floor_r = ring_floor[job["gen"]]
            # ALWAYS INSIDE THE ARC IT FEEDS. Where a sheet is too small for
            # the family on it, a ring's names run out over the ring beyond
            # and there is no clear band left; taking the floor at face value
            # then put the elbow a hundred millimetres OUTSIDE the arc it was
            # joining, with a line dragged back in to reach it. Crowding is a
            # crowded chart's problem. Inside-out is a broken one.
            floor_r = min(floor_r, r_arc - lane_gap * 1.1)
            # ---- AND IT IS A BRACKET: OUT, ROUND, OUT --------------------
            #
            # Right angles, and the tangential part at ONE radius. Tried as
            # an eased curve it flowed better on its own and read worse on
            # the chart: the rest of the linework is radii and arcs, and a
            # curve among them says "something different is happening here"
            # when nothing is. Consistency is the whole promise -- the shape
            # of a line has to mean the same thing everywhere.
            r_lane = min(floor_r + job["lane"] * lane_gap,
                         r_arc - lane_gap)
            # ---- WHY SOME OF THESE CROSS, AND WHAT IS DONE ABOUT IT -------
            #
            # A chart is a tree. A family is not: every marriage between two
            # lines that are BOTH documented is a cycle, and a tree can nest
            # one of the two, never both. Whichever loses is drawn in the
            # other's cell, and the line back to its own parents has to span
            # whatever the layout put in between.
            #
            # There is no planar way out, and it was worth proving rather
            # than believing. Both orderings were tried and measured:
            # `couple_grid.LEAN` and `couple_grid.FLANK`, with the numbers.
            # And there is no clear band to route through -- every radius
            # between two rings carries the spokes of the couples on the
            # inner one, so a tangential line has to cross them.
            #
            # So the crossing stays and is made to READ as a crossing. The
            # tangential run is drawn at two thirds weight, in two pieces
            # that meet exactly: no gap, nothing dashed, but where it passes
            # a descent line the heavier line is plainly the one that
            # continues. It is the oldest convention in draughting and it
            # needs no legend.
            # ---- AND IT JUMPS WHAT IT CANNOT AVOID -----------------------
            #
            # The ordering search in `couple_grid` is asked first, and where
            # it can put a family beside the one it married into it does. Some
            # it cannot, and those reaches still pass a descent line. Rather
            # than a gap -- which reads as a line that stops -- the reach
            # arches over: continuous ink, a small semicircle, the oldest
            # "these two do not join" mark there is.
            hop = []
            if style.get("lines.reach_jump", True):
                mid_t = (head + foot) / 2
                hop = sorted(x for x in (_near(t, mid_t)
                                         for t, u2 in spokes.get(job["gen"], ())
                                         if u2 != job["uid"])
                             if min(head, foot) < x < max(head, foot))
            if not hop:
                d_reach = G.arc_path(cx, cy, r_lane, head, foot)
            else:
                # A SEMICIRCLE, near enough: as wide as it is tall, and tall
                # enough to read at the weight the line is drawn. Sized from
                # the type, so it scales with the chart.
                bump = min(size * 0.9, lane_gap * 0.6)
                w = min(bump * 1.7 / max(r_lane, 1.0),
                        abs(foot - head) / (2 * len(hop) + 2))
                pts, step = [], (foot - head) / 160
                for i in range(161):
                    t = head + i * step
                    lift = max((max(0.0, 1.0 - ((t - c) / w) ** 2) ** 0.5
                                for c in hop), default=0.0)
                    # INWARD. Arching outward lifted the reach into the
                    # next lane out and the two read as one line; the
                    # band on the inside is clear by a whole lane gap.
                    pts.append(G.polar(cx, cy, r_lane - bump * lift, t))
                d_reach = G.polyline(pts)
            plan.add(Element(
                kind="path", layer="ENGRAVE", d=d_reach,
                stroke=job["colour"], stroke_width=job["width"] * 0.62,
                fill="none", person_id=job["anchor"],
                union_id=job["uid"], role="reach", z=9))
            d_stem = (G.polyline([G.polar(cx, cy, job["r_from"], head),
                                  G.polar(cx, cy, r_lane, head)])
                      + G.polyline([G.polar(cx, cy, r_lane, foot),
                                    G.polar(cx, cy, r_arc, foot)]))
        plan.add(Element(kind="path", layer="ENGRAVE", d=d_stem,
                         stroke=job["colour"], stroke_width=job["width"],
                         fill="none", person_id=job["anchor"],
                         union_id=job["uid"], role="stem", z=10))
        if len(job["run"]) > 1:
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=G.arc_path(cx, cy, job["r_arc"],
                                          job["lo"], job["hi"]),
                             stroke=job["colour"], stroke_width=job["width"],
                             fill="none", union_id=job["uid"],
                             role="siblings", z=10))

    # ---- 7. the line the machine cuts ------------------------------------
    #
    # Without this the file engraves beautifully and never comes off the
    # sheet.
    #
    # A full disc is cut as a disc. A FAN is cut as a plaque -- the canvas,
    # inset -- and not as the sector, because the key and the title sit
    # outside the sector, and a cut line that leaves engraving on the wrong
    # side of it does not warn you, it just loses that part of the piece.
    # The canvas is already the chart's own box rather than the whole sheet,
    # so the plaque is not wasteful; it is the shape the chart actually is.
    if style.get("production.cut_outline", True):
        inset = margin * 0.35
        d = (G.circle_path(cx, cy, R + margin * 0.45)
             if sweep >= full - 1e-9 and abs(W - H) < 1
             else G.rounded_rect(inset, inset, W - 2 * inset, H - 2 * inset,
                                 min(W, H) * 0.03))
        plan.add(Element(kind="path", layer="CUT", d=d, fill="none",
                         stroke=style.get("production.cut_colour", "#B03A2E"),
                         stroke_width=style.get("production.hairline_mm", 0.05),
                         role="outline", z=99))

    # The border is the edge of the DISC. A fan has no disc, and drawing one
    # anyway put a circle round a centre that is off the sheet -- found by
    # the pre-flight check for engraving outside the cut line, on the very
    # first production render.
    disc = sweep >= full - 1e-9 and abs(W - H) < 1
    if disc:
        add_border(plan, style, cx, cy, R + margin * 0.4)
    add_title(plan, style, cx if disc else W / 2, cy if disc else margin * 1.6)
    # On a full disc the key goes in the hole, where there is room and where
    # the cut line will reach it. On a fan it goes in the corner of the
    # plaque, which the cut line also reaches.
    _key(plan, style, W, H, margin, lw, col,
         at=(cx, cy) if disc else None, maxw=inner * 1.7 if disc else 0.0)
    return plan


def _wedges(plan, graph, g, cells, gens, ring_r, rows_in, pitch, stem,
            cx, cy, theta, style) -> None:
    """Tint the ground under each family, so you can see them come together.

    A family here is a founding couple and everyone descended from them. Its
    wedge covers, ring by ring, the angular ground its people stand on --
    narrow at the founders, widening outward as the family grows.

    A marriage between two of them is not drawn. It does not have to be:
    from that ring outward the two families share their descendants, so both
    wedges cover the same ground and the two tints LIE ON TOP OF EACH OTHER.
    The blend is the marriage. By the rim of a pedigree every wedge on the
    chart has converged on one cell, which is the person it was drawn for.

    Nothing here states a relationship the linework does not. It is the same
    facts at a distance you can read across a room, which is what a metre of
    plywood on a wall is for. It never reaches the cutter: `PRINT_ONLY`.
    """
    ring_of = {cid: m[0].gen for cid, m in cells.items()}
    cell_of = {sl.pid: (sl.cell or sl.pid) for sl in g}

    def parent_cells(cid):
        out = []
        for sl in cells[cid]:
            uid = graph.people[sl.pid].child_of
            u = graph.unions.get(uid) if uid else None
            if not u:
                continue
            for p in u.partners:
                pc = cell_of.get(p)
                if pc is not None and ring_of.get(pc) == ring_of[cid] - 1:
                    out.append(pc)
        return list(dict.fromkeys(out))

    kids: dict[str, list[str]] = {}
    for cid in sorted(cells):
        for pc in parent_cells(cid):
            kids.setdefault(pc, []).append(cid)

    cone: dict[str, set] = {}
    for r in reversed(gens):             # inward, so children answer first
        for cid in sorted(c for c in cells if ring_of[c] == r):
            out = {cid}
            for k in kids.get(cid, ()):
                out |= cone[k]
            cone[cid] = out

    # WHICH families get a wedge. The founders -- unless a founder's
    # descendants ARE the chart, which is the whole of a descendancy chart,
    # and one tint over all of it says nothing. Where that happens, drop down
    # to that couple's children and let their branches be the families.
    #
    # Nearly all, not most. On a pedigree BOTH of the subject's lines cover
    # about seventy per cent of the chart, because they share everything from
    # the marriage outward -- that overlap is the thing being drawn, and a
    # threshold that split it took the tint off the founders entirely.
    total = len(cells)
    share = float(style.get("family.wedge_max_share", 0.95))
    least = int(style.get("family.wedge_min_cells", 3))
    most = int(style.get("family.wedge_max", 10))
    queue = [c for c in sorted(cells) if not parent_cells(c)]
    pick: list[str] = []
    while queue:
        cid = queue.pop()
        if len(cone[cid]) > share * total and kids.get(cid):
            queue += kids[cid]
        else:
            pick.append(cid)
    keep = [f for f in sorted(set(pick), key=lambda k: (-len(cone[k]), k))
            if len(cone[f]) >= least][:most]
    if not keep:
        return

    pal = list(style.get("colour.palette"))[1:]     # [0] is the ink colour
    alpha = float(style.get("family.wedge_opacity", 0.13))

    def edges(r):
        """Ring bands that TOUCH, so a family is one wedge and not a ladder.

        The step where one ring is wider than the next is the point: it says
        the family was this wide here and that wide there.
        """
        r0 = ring_r[r] - stem * 0.5
        out = ring_r.get(r + 1)
        return r0, (out - stem * 0.5 if out is not None
                    else ring_r[r] + rows_in[r] * pitch[r])

    for i, f in enumerate(keep):
        fill = pal[i % len(pal)]
        for r in gens:
            here = [cells[c] for c in cone[f] if ring_of[c] == r]
            if not here:
                continue
            r0, r1 = edges(r)
            spans = sorted((min(m.t0 for m in c), max(m.t1 for m in c))
                           for c in here)
            # One shape per contiguous RUN. Taking the outermost pair instead
            # painted straight over whoever happened to sit in the gap, which
            # on a chart with two families interleaved is most of it.
            runs = [list(spans[0])]
            for lo, hi in spans[1:]:
                if lo <= runs[-1][1] + 0.02:
                    runs[-1][1] = max(runs[-1][1], hi)
                else:
                    runs.append([lo, hi])
            for lo, hi in runs:
                plan.add(Element(
                    kind="path", layer="PRINT_ONLY",
                    d=G.annular_sector(cx, cy, r0, r1, theta(lo), theta(hi)),
                    fill=fill, stroke="none", opacity=alpha,
                    person_id=cells[f][0].pid if f in cells else "",
                    role="family", z=-10))


def _sector_bounds(r0: float, r1: float, a0: float, a1: float):
    """Bounding box of an annular sector, relative to its own centre.

    A full disc is its own bounding box and there is nothing to think about.
    A FAN is not: a 168 degree fan drawn on a disc-sized square wastes most
    of the sheet, and on a fixed panel it could use nearly twice the radius.
    The box is the four corners plus whichever axis crossings fall inside the
    sweep -- those are where an arc bulges past its own endpoints.
    """
    pts = [(r * math.cos(a), r * math.sin(a))
           for a in (a0, a1) for r in (r0, r1)]
    lo, hi = min(a0, a1), max(a0, a1)
    k = math.ceil(lo / (math.pi / 2))
    while k * (math.pi / 2) <= hi:
        a = k * (math.pi / 2)
        pts.append((r1 * math.cos(a), r1 * math.sin(a)))
        k += 1
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _flip(t: float) -> bool:
    """Radial text on the left half reads upside down unless it is turned."""
    d = math.degrees(t) % 360
    return 90 < d < 270


def _chord(cx, cy, r0, t0, r1, t1, bow: float = 0.45):
    """A shallow curve between two points, bowed toward the centre so it
    reads as a tie rather than as a branch."""
    x0, y0 = G.polar(cx, cy, r0, t0)
    x1, y1 = G.polar(cx, cy, r1, t1)
    pts = [(x0, y0)]
    n = 24
    for i in range(1, n):
        f = i / n
        r = (r0 + (r1 - r0) * f) * (1 - bow * math.sin(math.pi * f))
        t = t0 + (t1 - t0) * f
        pts.append(G.polar(cx, cy, max(r, 1.0), t))
    pts.append((x1, y1))
    return pts


def _thread(graph, s) -> set:
    from ...graph.thread import thread
    if not s.subject_id:
        return set()
    return set(thread(graph, s.subject_id).members)


def _key(plan, style, W, H, margin, lw, col, at=None, maxw=0.0):
    """Four lines. A chart that outlives its maker has to say what its own
    marks mean.

    Bottom left by default. `at` CENTRES it somewhere else instead, which is
    what a full disc does: the corner of the sheet is outside the round cut
    line, so a key in the corner is a key in the offcut -- and the hole in
    the middle is empty and inside the cut. `maxw` is how wide it may be
    there; the type shrinks to fit, and if that would take it below legible
    the key is left off and said so.
    """
    if not style.get("lines.key", True):
        return
    size = style.get("type.size_mm", 2.9) * 0.72
    rows = [("cell", "two names in one cell — married"),
            ("arc", "an arc over brothers and sisters"),
            ("stem", "a stem from a couple to their children"),
            ("chord", "a marriage between two people already on the chart")]
    need = max(est_text_width(t, size) for _, t in rows) + 12
    if maxw > 0 and need > maxw:
        size *= maxw / need
        if size < style.get("type.min_size_mm", 2.2) * 0.62:
            plan.meta.extra["key_dropped"] = True
            return
        need = maxw
    if at:
        x, y = at[0] - need / 2, at[1] - size * 1.7 * (len(rows) - 1) / 2
    else:
        x, y = margin, H - margin - 14
    for i, (kind, text) in enumerate(rows):
        yy = y + i * size * 1.7
        if kind == "arc":
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=f"M {x:.3f},{yy:.3f} L {x + 7:.3f},{yy:.3f}",
                             stroke=col, stroke_width=lw, fill="none",
                             role="key", z=90))
        elif kind == "chord":
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=f"M {x:.3f},{yy:.3f} L {x + 7:.3f},{yy:.3f}",
                             stroke=style.get("lines.marriage_colour", "#8A6F4E"),
                             stroke_width=lw * 0.8, dash="1.6,1.2",
                             fill="none", role="key", z=90))
        elif kind == "cell":
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=f"M {x:.3f},{yy:.3f} L {x + 7:.3f},{yy:.3f}",
                             stroke=style.get("lines.marriage_colour", col),
                             stroke_width=lw * 0.55, fill="none",
                             role="key", z=90))
        else:
            plan.add(Element(kind="path", layer="ENGRAVE",
                             d=f"M {x + 3.5:.3f},{yy - 2:.3f} "
                               f"L {x + 3.5:.3f},{yy + 2:.3f}",
                             stroke=col, stroke_width=lw, fill="none",
                             role="key", z=90))
        plan.add(Element(kind="text", layer="ENGRAVE", text=text,
                         x=x + 10, y=yy + size * 0.35, fill=col,
                         font=FontSpec(size_mm=size, anchor="start"),
                         role="key", z=90))
