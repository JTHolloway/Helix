"""Bytes on disk -> (level, xref, tag, value) records.

Separate from the parser because the two fail differently. Everything in
this file is about a thirty-year-old format having been written by two dozen
programs that each disagreed slightly: encodings that lie, lines that
continue, blank lines, byte-order marks, CRLF, and levels that skip. None of
that is about families, and mixing it into the parser is how a GEDCOM reader
turns into something nobody dares change.

THE ENCODING IS SNIFFED, NEVER TRUSTED. The header says CHAR ANSEL more
often than the file is ANSEL: Family Tree Maker wrote Windows-1252 under
that header for years, and half the "ANSEL" files in circulation are really
UTF-8. So: look for a BOM, try the declared encoding, and fall back through
UTF-8, CP1252 and ANSEL until one decodes without loss. Getting this wrong
does not raise -- it silently replaces every accented letter in somebody's
family with a question mark.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

# 0 @I1@ INDI  /  1 NAME John /Smith/  /  2 DATE 12 MAR 1841
_LINE = re.compile(r"^\s*(\d+)\s+(?:(@[^@]*@)\s+)?([A-Za-z0-9_]+)(?:\s(.*))?$")

# ANSEL's combining diacritics sit in the high range and come BEFORE the
# letter they modify, which is the opposite of Unicode. Only the letters
# that actually turn up in European names are mapped; anything else falls
# through unchanged rather than being replaced with a question mark.
_ANSEL_COMBINING = {
    0xE0: "̉", 0xE1: "̀", 0xE2: "́", 0xE3: "̂",
    0xE4: "̃", 0xE5: "̄", 0xE6: "̆", 0xE7: "̇",
    0xE8: "̈", 0xE9: "̌", 0xEA: "̊", 0xEB: "︠",
    0xEC: "︡", 0xED: "̕", 0xEE: "̋", 0xEF: "̐",
    0xF0: "̧", 0xF1: "̨", 0xF2: "̣", 0xF3: "̤",
    0xF4: "̥", 0xF5: "̳", 0xF6: "̲", 0xF7: "̦",
    0xF8: "̜", 0xF9: "̮", 0xFA: "︢", 0xFB: "︣",
    0xFE: "̓",
}
_ANSEL_SINGLE = {
    0xA1: "Ł", 0xA2: "Ø", 0xA3: "Đ", 0xA4: "Þ", 0xA5: "Æ", 0xA6: "Œ",
    0xA9: "♭", 0xAA: "®", 0xAB: "±", 0xB0: "ʼ", 0xB1: "ł", 0xB2: "ø",
    0xB3: "đ", 0xB4: "þ", 0xB5: "æ", 0xB6: "œ", 0xB9: "£", 0xBA: "ð",
    0xC0: "°", 0xC1: "ℓ", 0xC3: "©", 0xC5: "♯", 0xCF: "ʻ",
}


def ansel_decode(raw: bytes) -> str:
    """ANSEL to Unicode, well enough for names.

    Combining marks come before their letter in ANSEL and after it in
    Unicode, so the two have to be swapped as they are read. Written the
    naive way, "José" comes out as "Jos´e".
    """
    out: list[str] = []
    pending: list[str] = []
    for b in raw:
        if b in _ANSEL_COMBINING:
            pending.append(_ANSEL_COMBINING[b])
        elif b in _ANSEL_SINGLE:
            out.append(_ANSEL_SINGLE[b])
            out.extend(pending)
            pending = []
        elif b < 0x80:
            out.append(chr(b))
            out.extend(pending)
            pending = []
        else:
            out.append(chr(b))              # unknown high byte: keep, do not lose
            out.extend(pending)
            pending = []
    out.extend(pending)
    import unicodedata
    return unicodedata.normalize("NFC", "".join(out))


def sniff(raw: bytes) -> tuple[str, str]:
    """Return (text, encoding_used).

    Order matters and each step is here because a real file needed it:
    a BOM is definitive; UTF-8 that decodes cleanly is UTF-8 whatever the
    header says; CP1252 decodes almost anything, so it comes after the
    declared encoding and before ANSEL.
    """
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", "replace"), "utf-8-sig"
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        enc = "utf-16"
        return raw.decode(enc, "replace"), enc

    declared = ""
    head = raw[:2000].decode("latin-1", "replace").upper()
    m = re.search(r"^\s*\d+\s+CHAR\s+(\S+)", head, re.M)
    if m:
        declared = m.group(1).strip()

    try:                                    # UTF-8 first: it either is or is not
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    if declared in ("ANSEL", "ANSI"):
        # ANSI in a GEDCOM header has always meant Windows-1252, never the
        # ANSI standard. Trying ANSEL first mangles every file that says
        # ANSI and means CP1252, which is most of them.
        if declared == "ANSI":
            return raw.decode("cp1252", "replace"), "cp1252"
        return ansel_decode(raw), "ansel"
    for enc in ("cp1252", "latin-1"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return ansel_decode(raw), "ansel"


@dataclass
class Rec:
    level: int
    tag: str
    value: str = ""
    xref: str = ""
    line_no: int = 0
    children: list = None                   # type: ignore[assignment]

    def __post_init__(self):
        if self.children is None:
            self.children = []

    # -- reading a record ---------------------------------------------------
    def first(self, tag: str) -> Optional["Rec"]:
        for c in self.children:
            if c.tag == tag:
                return c
        return None

    def all(self, *tags: str) -> list["Rec"]:
        return [c for c in self.children if c.tag in tags]

    def val(self, tag: str, default: str = "") -> str:
        c = self.first(tag)
        return c.value if c else default

    def walk(self) -> Iterator["Rec"]:
        yield self
        for c in self.children:
            yield from c.walk()


def scan(text: str) -> tuple[list[Rec], list[str]]:
    """Flat lines -> a list of top-level records, with CONT/CONC folded in.

    Returns (records, problems). PROBLEMS ARE COLLECTED, NEVER RAISED: a
    file with one malformed line in four hundred thousand still holds
    somebody's family, and refusing the whole import over it helps nobody.
    """
    problems: list[str] = []
    roots: list[Rec] = []
    stack: list[Rec] = []
    last: Optional[Rec] = None

    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue
        m = _LINE.match(line)
        if not m:
            if len(problems) < 50:
                problems.append(f"Line {n} is not a GEDCOM line: {line[:60]!r}")
            continue
        level = int(m.group(1))
        xref = (m.group(2) or "").strip()
        tag = m.group(3).upper()
        value = m.group(4) or ""

        # CONT is a newline, CONC is a join with no space at all. Getting
        # CONC wrong inserts a space into the middle of every long name.
        if tag in ("CONT", "CONC") and last is not None:
            last.value += ("\n" if tag == "CONT" else "") + value
            continue

        rec = Rec(level, tag, value, xref, n)
        if level == 0:
            roots.append(rec)
            stack = [rec]
        else:
            # A level that jumps -- 0 then 2 -- is common in hand-edited
            # files. Attach to the deepest thing that can legally hold it
            # rather than dropping the line.
            while len(stack) > level:
                stack.pop()
            if not stack:
                if len(problems) < 50:
                    problems.append(
                        f"Line {n}: level {level} with nothing above it; "
                        f"attached to the previous record.")
                if roots:
                    stack = [roots[-1]]
                else:
                    continue
            stack[-1].children.append(rec)
            stack.append(rec)
        last = rec
    return roots, problems


def read(path: str | Path) -> tuple[list[Rec], dict]:
    raw = Path(path).read_bytes()
    text, enc = sniff(raw)
    roots, problems = scan(text)
    return roots, {"encoding": enc, "problems": problems,
                   "records": len(roots), "bytes": len(raw)}
