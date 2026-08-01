"""GEDCOM import and export.

GEDCOM is the only format every genealogy program can read, so this is the
door in and the door out. It is also a 1980s format with thirty years of
vendor-specific damage, so the parser must be forgiving.

STRUCTURE
  lexer.py   bytes -> (level, xref, tag, value) records
  parser.py  records -> Helix rows
  writer.py  Helix rows -> GEDCOM 5.5.1 or 7.0

THINGS THAT WILL BREAK A NAIVE PARSER
  * Encoding: ANSEL (5.5.1 default), UTF-8 with and without BOM, UTF-16LE,
    and Windows-1252 mislabelled as ANSEL. Sniff, do not trust the header.
  * CONT/CONC continuation lines; CONC joins with no space.
  * Custom tags beginning with an underscore (_MILT, _UID...). Keep them in
    `notes` rather than discarding: they often hold the only copy of a fact.
  * Names as "John /Smith/" with the surname in slashes; also nested NAME
    substructures in 7.0.
  * Dates: the whole GenDate grammar, plus @#DJULIAN@ and @#DHEBREW@ escapes.
  * FAM records with no HUSB or no WIFE; children listed twice.
  * Cyclic pedigrees from bad data -- detect and report, never hang.

RULE
  Import must be lossless enough to round-trip. Anything not modelled goes
  into `person.notes` with a `[GEDCOM]` prefix so nothing is silently lost.
"""
from .lexer import Rec, read, scan, sniff          # noqa: F401
from .parser import import_file                     # noqa: F401
from .writer import export as _export, gedcom_date  # noqa: F401


def export_file(con, path: str, *, version: str = "5.5.1",
                title: str = "", submitter: str = "",
                redact_living: bool = False) -> dict:
    """Write the whole family out. Returns a summary of what went.

    `redact_living` takes the private half off anybody who may still be
    alive: they keep their place in the tree, their surname and their sex,
    and lose their given names, their dates and everything written about
    them. See `writer._redact` for why the shape has to survive.
    """
    return _export(con, path, version=version, title=title,
                   submitter=submitter, redact_living=redact_living)
