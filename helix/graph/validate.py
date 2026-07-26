"""Data validation.

Every rule states a plain-English problem and, where it can, what to do about
it. Never scold; always be specific; never cry wolf.

THE RULE THAT GOVERNS THIS FILE: compare INTERVALS, not midpoints.

A birth of "27 Nov 1741" and a death of "1741" are perfectly consistent -- an
infant who died the same year. Comparing their midpoints says the death came
first and raises a false alarm. A validator that cries wolf gets ignored, and
then it is worse than no validator at all.

So: only report something as impossible when it is impossible for EVERY date
in both intervals.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..model.gendate import GenDate

MAX_AGE = 110
MAX_MOTHER_AGE = 52
MIN_PARENT_AGE = 12


@dataclass
class Issue:
    severity: str          # error | warning | info
    code: str
    message: str
    person_id: Optional[str] = None


def _impossible_order(first: GenDate, second: GenDate) -> bool:
    """True only if `second` cannot possibly be at or after `first`."""
    if not first.known or not second.known:
        return False
    if first.earliest is None or second.latest is None:
        return False
    return second.latest < first.earliest


def _min_gap_years(a: GenDate, b: GenDate) -> Optional[float]:
    """Smallest possible (b - a) in years, given both intervals."""
    if not a.known or not b.known or a.latest is None or b.earliest is None:
        return None
    return (b.earliest.year + b.earliest.timetuple().tm_yday / 365.25) - \
           (a.latest.year + a.latest.timetuple().tm_yday / 365.25)


def _max_gap_years(a: GenDate, b: GenDate) -> Optional[float]:
    if not a.known or not b.known or a.earliest is None or b.latest is None:
        return None
    return (b.latest.year + b.latest.timetuple().tm_yday / 365.25) - \
           (a.earliest.year + a.earliest.timetuple().tm_yday / 365.25)


def validate(graph) -> list[Issue]:
    out: list[Issue] = []
    P = graph.people

    for pid, p in P.items():
        # --- death before birth -------------------------------------------
        if _impossible_order(p.birth, p.death):
            out.append(Issue("error", "death_before_birth",
                             f"{p.full_name} died before they were born "
                             f"({p.birth.display} then {p.death.display}). "
                             f"One of the two dates is wrong.", pid))

        # --- implausibly long life ----------------------------------------
        low = _min_gap_years(p.birth, p.death)
        if low is not None and low > MAX_AGE:
            out.append(Issue("warning", "long_life",
                             f"{p.full_name} would have been at least "
                             f"{int(low)}. Check the dates \u2014 an age on a "
                             f"death record is often a guess.", pid))

        # --- parent/child ordering ----------------------------------------
        for par in graph.parents(pid, primary_only=False):
            pp = P[par]
            if _impossible_order(pp.birth, p.birth):
                out.append(Issue("error", "child_before_parent",
                                 f"{p.full_name} was born before their parent "
                                 f"{pp.full_name}. Check whether the "
                                 f"generations have been linked correctly.",
                                 pid))
                continue
            gap_low = _min_gap_years(pp.birth, p.birth)
            gap_high = _max_gap_years(pp.birth, p.birth)
            if gap_low is not None and gap_low > MAX_MOTHER_AGE and pp.sex == "F":
                out.append(Issue("warning", "old_mother",
                                 f"{pp.full_name} would have been at least "
                                 f"{int(gap_low)} when {p.full_name} was born. "
                                 f"A generation may be missing between them.",
                                 pid))
            if gap_high is not None and 0 <= gap_high < MIN_PARENT_AGE:
                out.append(Issue("warning", "young_parent",
                                 f"{pp.full_name} would have been under "
                                 f"{MIN_PARENT_AGE} when {p.full_name} was "
                                 f"born.", pid))

        # --- structural ----------------------------------------------------
        if len(p.child_of_all) > 1 and not p.child_of:
            out.append(Issue("error", "no_primary_parents",
                             f"{p.full_name} has more than one set of parents "
                             f"but none is marked as the main one. Open them "
                             f"and choose which line the chart should follow.",
                             pid))
        if not p.birth.known and not p.death.known and not p.is_placeholder:
            out.append(Issue("info", "no_dates",
                             f"{p.full_name} has no dates at all. Even "
                             f"\u201cabt 1850\u201d would let them be placed "
                             f"on a chart.", pid))
        if p.confidence == 0 and not p.is_placeholder:
            out.append(Issue("info", "unproved",
                             f"{p.full_name} is recorded as unproved. Worth a "
                             f"look if a whole branch hangs off them.", pid))

    # --- cycles: a person who is their own ancestor -----------------------
    for pid in P:
        anc = graph.ancestors(pid)
        anc.pop(pid, None)
        if any(pid in graph.ancestors(a) for a in anc):
            out.append(Issue("error", "cycle",
                             f"{P[pid].full_name} appears to be their own "
                             f"ancestor. Two people have probably been merged "
                             f"who should not have been.", pid))
    return out
