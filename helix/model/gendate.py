"""Fuzzy genealogical dates.

Single responsibility: represent and parse a date that may be approximate,
bounded, or unknown, and never lose the user's original text.

This module must NOT touch the database, the layout engine, or any I/O.

Why this exists
---------------
Real records say "abt 1834", "bef 1900", "Q3 1871", "1723/24". A `datetime.date`
cannot hold any of those. Every downstream feature (sorting, radial position,
age calculation, validation) depends on getting this right, so it is the first
thing built and the most heavily tested.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from datetime import date
from typing import Literal, Optional

Kind = Literal[
    "exact", "about", "before", "after", "between",
    "quarter", "estimated", "calculated", "unknown",
]
Precision = Literal["day", "month", "quarter", "year", "decade", "century", "unknown"]
Calendar = Literal["gregorian", "julian", "dual"]

ABOUT_SLACK_YEARS = 3        # how far "abt 1834" reaches either side
OPEN_LOW = date(1000, 1, 1)  # sentinel bounds for before/after
OPEN_HIGH = date(2200, 12, 31)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
_QUARTER_MONTHS = {1: (1, 3), 2: (4, 6), 3: (7, 9), 4: (10, 12)}


def _eom(y: int, m: int) -> int:
    if m == 12:
        return 31
    return (date(y + (m // 12), (m % 12) + 1, 1) - __import__("datetime").timedelta(days=1)).day


@dataclass(frozen=True)
class GenDate:
    kind: Kind = "unknown"
    earliest: Optional[date] = None
    latest: Optional[date] = None
    precision: Precision = "unknown"
    calendar: Calendar = "gregorian"
    original: str = ""
    confidence: int = 2

    # ---------------------------------------------------------------- helpers
    @property
    def known(self) -> bool:
        return self.kind != "unknown" and (self.earliest is not None or self.latest is not None)

    @property
    def sort_value(self) -> Optional[float]:
        """Decimal-year midpoint. This is what the layout engine positions by."""
        lo, hi = self.earliest, self.latest
        if lo is None and hi is None:
            return None
        lo = lo or hi
        hi = hi or lo
        return (_dec(lo) + _dec(hi)) / 2.0

    @property
    def year(self) -> Optional[int]:
        sv = self.sort_value
        return None if sv is None else int(round(sv))

    @property
    def display(self) -> str:
        if self.kind == "unknown":
            return self.original or ""
        if self.kind == "between":
            return f"bet {_fmt(self.earliest, self.precision)} and {_fmt(self.latest, self.precision)}"
        if self.kind == "before":
            return f"bef {_fmt(self.latest, self.precision)}"
        if self.kind == "after":
            return f"aft {_fmt(self.earliest, self.precision)}"
        if self.kind == "quarter":
            q = (self.earliest.month + 2) // 3
            return f"Q{q} {self.earliest.year}"
        if self.precision == "decade" and self.earliest:
            return f"{self.earliest.year}s"
        prefix = {"about": "abt ", "estimated": "est ", "calculated": "calc "}.get(self.kind, "")
        if self.calendar == "dual" and self.earliest:
            y = self.earliest.year
            return f"{y-1}/{str(y)[-2:]}"
        if self.kind in ("about", "estimated", "calculated"):
            # show the CENTRE of the widened window, not its edge
            return f"{prefix}{self.year}"
        return prefix + _fmt(self.earliest, self.precision)

    @property
    def spoken(self) -> str:
        """The same date said out loud: `abt 1834` becomes "about 1834".

        `display` is the compact genealogical form and belongs on a chart.
        This is for the echo under a date field while somebody types, where
        the whole point is to show that the shorthand was understood. An
        unparseable date echoes back exactly what was typed -- it is being
        kept, and saying so is better than a red border.
        """
        if self.kind == "unknown":
            return f"kept as written: {self.original}" if self.original else ""
        if self.kind == "between":
            return (f"between {_fmt(self.earliest, self.precision)} and "
                    f"{_fmt(self.latest, self.precision)}")
        if self.kind == "before":
            return f"before {_fmt(self.latest, self.precision)}"
        if self.kind == "after":
            return f"after {_fmt(self.earliest, self.precision)}"
        if self.kind == "quarter":
            q = (self.earliest.month + 2) // 3
            return (f"the {['first', 'second', 'third', 'fourth'][q - 1]} "
                    f"quarter of {self.earliest.year}")
        if self.calendar == "dual" and self.earliest:
            y = self.earliest.year
            return f"{y-1}/{str(y)[-2:]} — the year began in March until 1752"
        if self.precision == "decade" and self.earliest:
            return f"some time in the {self.earliest.year}s"
        word = {"about": "about ", "estimated": "estimated ",
                "calculated": "calculated "}.get(self.kind, "")
        if self.kind in ("about", "estimated", "calculated"):
            return f"{word}{self.year}"
        return _fmt(self.earliest, self.precision)

    def overlaps(self, other: "GenDate") -> bool:
        a0, a1 = self.earliest or OPEN_LOW, self.latest or OPEN_HIGH
        b0, b1 = other.earliest or OPEN_LOW, other.latest or OPEN_HIGH
        return a0 <= b1 and b0 <= a1

    def definitely_before(self, other: "GenDate") -> bool:
        if self.latest is None or other.earliest is None:
            return False
        return self.latest < other.earliest

    # ------------------------------------------------------------ persistence
    def to_json(self) -> str:
        d = asdict(self)
        d["earliest"] = self.earliest.isoformat() if self.earliest else None
        d["latest"] = self.latest.isoformat() if self.latest else None
        return json.dumps(d, separators=(",", ":"))

    @staticmethod
    def from_json(s: Optional[str]) -> "GenDate":
        if not s:
            return GenDate()
        d = json.loads(s)
        for k in ("earliest", "latest"):
            d[k] = date.fromisoformat(d[k]) if d.get(k) else None
        return GenDate(**d)


def _dec(d: date) -> float:
    return d.year + (d.timetuple().tm_yday - 1) / 365.25


def _fmt(d: Optional[date], precision: Precision) -> str:
    if d is None:
        return "?"
    if precision == "day":
        return d.strftime("%d %b %Y").lstrip("0")
    if precision == "month":
        return d.strftime("%b %Y")
    return str(d.year)


# ============================================================== the parser ===
_RE_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_RE_DMY = re.compile(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})$")
_RE_DUAL = re.compile(r"^(?:(\d{1,2})\s+([a-z]+)\s+)?(\d{4})/(\d{1,2,4}|\d{1,4})$", re.I)
_RE_QTR = re.compile(r"^q([1-4])\s+(\d{4})$", re.I)
_RE_QTR2 = re.compile(r"^(\d{4})\s+q([1-4])$", re.I)
_RE_DMONY = re.compile(r"^(\d{1,2})\s+([a-z]+)\.?\s+(\d{4})$", re.I)
_RE_MONY = re.compile(r"^([a-z]+)\.?\s+(\d{4})$", re.I)
_RE_YEAR = re.compile(r"^(\d{3,4})$")
_RE_DECADE = re.compile(r"^(\d{3})0s$")
_RE_BETWEEN = re.compile(r"^(?:bet|between)\s+(.+?)\s+(?:and|-|to|–)\s+(.+)$", re.I)
_RE_RANGE = re.compile(r"^(\d{4})\s*[-–]\s*(\d{4})$")

_PREFIXES = [
    (("abt", "about", "circa", "ca", "c", "~", "approx"), "about"),
    (("est", "estimated"), "estimated"),
    (("calc", "calculated", "cal"), "calculated"),
    (("bef", "before", "<"), "before"),
    (("aft", "after", ">"), "after"),
]


def parse(text: Optional[str], *, day_first: bool = True, confidence: int = 2) -> GenDate:
    """Parse a date phrase. NEVER raises: unparseable input becomes kind='unknown'
    with `original` preserved, so the user's typing is never destroyed."""
    raw = (text or "").strip()
    if not raw:
        return GenDate(original="")
    s = raw.lower().strip().rstrip(".")
    s = re.sub(r"\s+", " ", s)

    # explicit ranges -------------------------------------------------------
    m = _RE_BETWEEN.match(s) or _RE_RANGE.match(s)
    if m:
        a, b = parse(m.group(1), day_first=day_first), parse(m.group(2), day_first=day_first)
        if a.known and b.known:
            return GenDate("between", a.earliest, b.latest,
                           _coarser(a.precision, b.precision), "gregorian", raw, confidence)

    # prefixes --------------------------------------------------------------
    kind: Kind = "exact"
    for words, k in _PREFIXES:
        for w in words:
            if s.startswith(w + " ") or (len(w) <= 2 and s.startswith(w) and s[len(w):len(w)+1].isdigit()):
                kind = k                        # type: ignore[assignment]
                s = s[len(w):].strip().lstrip(".").strip()
                break
        if kind != "exact":
            break

    try:
        base = _parse_core(s, day_first=day_first)
    except (ValueError, OverflowError):
        base = None
    if base is None:
        return GenDate(original=raw, confidence=confidence)

    lo, hi, prec, cal = base
    if kind in ("about", "estimated", "calculated"):
        try:
            lo = date(max(1, lo.year - ABOUT_SLACK_YEARS), lo.month, lo.day)
            hi = date(min(9998, hi.year + ABOUT_SLACK_YEARS), hi.month, hi.day)
        except ValueError:                       # 29 Feb in a non-leap year
            lo = date(max(1, lo.year - ABOUT_SLACK_YEARS), lo.month, 28)
            hi = date(min(9998, hi.year + ABOUT_SLACK_YEARS), hi.month, 28)
    elif kind == "before":
        lo, hi = OPEN_LOW, hi
    elif kind == "after":
        lo, hi = lo, OPEN_HIGH
    elif prec == "quarter":
        kind = "quarter"
    return GenDate(kind, lo, hi, prec, cal, raw, confidence)


def _parse_core(s: str, *, day_first: bool):
    """Return (earliest, latest, precision, calendar) or None."""
    if m := _RE_ISO.match(s):
        y, mo, d = map(int, m.groups())
        try:
            dd = date(y, mo, d)
        except ValueError:
            return None
        return dd, dd, "day", "gregorian"

    if m := _RE_DMY.match(s):
        a, b, y = map(int, m.groups())
        d_, mo = (a, b) if day_first else (b, a)
        try:
            dd = date(y, mo, d_)
        except ValueError:
            return None
        return dd, dd, "day", "gregorian"

    # dual dating: 1723/24, 24 feb 1723/24  -> historically 1724
    if "/" in s and (m := re.match(r"^(?:(\d{1,2})\s+([a-z]+)\s+)?(\d{4})/(\d{1,2})$", s)):
        dd, mon, y1, y2s = m.groups()
        y = int(y1) + 1
        if dd and mon and mon[:3] in _MONTHS:
            try:
                x = date(y, _MONTHS[mon[:3]], int(dd))
                return x, x, "day", "dual"
            except ValueError:
                return None
        return date(y, 1, 1), date(y, 3, 24), "year", "dual"

    if (m := _RE_QTR.match(s)) or (m := _RE_QTR2.match(s)):
        g = m.groups()
        q, y = (int(g[0]), int(g[1])) if s.lower().startswith("q") else (int(g[1]), int(g[0]))
        m0, m1 = _QUARTER_MONTHS[q]
        return date(y, m0, 1), date(y, m1, _eom(y, m1)), "quarter", "gregorian"

    if m := _RE_DMONY.match(s):
        d_, mon, y = int(m.group(1)), m.group(2)[:3], int(m.group(3))
        if mon not in _MONTHS:
            return None
        try:
            dd = date(y, _MONTHS[mon], d_)
        except ValueError:
            return None
        return dd, dd, "day", "gregorian"

    if m := _RE_MONY.match(s):
        mon, y = m.group(1)[:3], int(m.group(2))
        if mon not in _MONTHS:
            return None
        mo = _MONTHS[mon]
        return date(y, mo, 1), date(y, mo, _eom(y, mo)), "month", "gregorian"

    if m := _RE_DECADE.match(s):
        y = int(m.group(1)) * 10
        if not _plausible_year(y):
            return None
        return date(y, 1, 1), date(y + 9, 12, 31), "decade", "gregorian"

    if m := _RE_YEAR.match(s):
        y = int(m.group(1))
        if not _plausible_year(y):
            return None
        return date(y, 1, 1), date(y, 12, 31), "year", "gregorian"

    return None


def _plausible_year(y: int) -> bool:
    """`date` cannot represent year 0, and a genealogy has no business
    before about 800 AD. Reject rather than raise: '0000' in a badly
    exported GEDCOM means 'unknown', not 'the year zero'."""
    return 800 <= y <= 2200


def _coarser(a: Precision, b: Precision) -> Precision:
    order = ["day", "month", "quarter", "year", "decade", "century", "unknown"]
    return order[max(order.index(a), order.index(b))]        # type: ignore[return-value]


# =============================================================== ages ========
@dataclass(frozen=True)
class AgeRange:
    low: Optional[int]
    high: Optional[int]

    @property
    def display(self) -> str:
        if self.low is None and self.high is None:
            return ""
        if self.low is not None and self.high is not None:
            return str(self.low) if self.low == self.high else f"{self.low}\u2013{self.high}"
        if self.low is not None:
            return f"\u2265 {self.low}"
        return f"\u2264 {self.high}"


def age_at(birth: GenDate, event: GenDate) -> AgeRange:
    """Age as an INTERVAL. Never return a bare int: an age derived from two
    'about' dates, printed as an exact number, is a lie the chart repeats
    for a hundred years."""
    if not birth.known or not event.known:
        return AgeRange(None, None)
    b0, b1 = birth.earliest or OPEN_LOW, birth.latest or OPEN_HIGH
    e0, e1 = event.earliest or OPEN_LOW, event.latest or OPEN_HIGH
    lo = max(0, int((_dec(e0) - _dec(b1))))
    hi = int((_dec(e1) - _dec(b0)))
    if hi < 0:
        return AgeRange(None, None)
    return AgeRange(lo, max(lo, hi))
