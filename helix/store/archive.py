"""Keeping your work safe for years.

Single responsibility: make sure a decade of research cannot be lost, and
cannot be trapped inside this program.

Three separate promises, because they fail in different ways:

  SAVED      Every edit is committed to SQLite the moment it is made. There
             is no unsaved state and therefore no Save button to forget.
  BACKED UP  A dated copy is taken automatically once a day and before
             anything destructive. Thirty are kept.
  PORTABLE   `helix archive` writes a zip holding the database, a plain JSON
             dump of every record, CSV tables, and the current renders. The
             JSON is the long-term guarantee: readable in any language, on
             any machine, in twenty years, with or without Helix.
"""
from __future__ import annotations

import csv
import io
import json
import shutil
import sqlite3
import zipfile
from datetime import date, datetime
from pathlib import Path

TABLES = ["person", "person_name", "union_", "union_partner", "union_child",
          "place", "event", "event_role", "source", "citation", "media",
          "media_link", "tag", "person_tag", "person_heritage",
          "research_task", "dna_match",
          "settings"]


def daily_backup(path: str | Path, keep: int = 30) -> Path | None:
    """Take one backup per day, automatically. Returns the path, or None if
    today's copy already exists."""
    path = Path(path)
    if not path.exists():
        return None
    d = path.parent / "backups"
    d.mkdir(exist_ok=True)
    stamp = date.today().isoformat()
    dest = d / f"{path.stem}-{stamp}{path.suffix}"
    if dest.exists():
        return None
    _copy_consistent(path, dest)
    olds = sorted(d.glob(f"{path.stem}-*{path.suffix}"))
    for old in olds[:-keep]:
        old.unlink()
    return dest


def _copy_consistent(src: Path, dest: Path) -> None:
    """Copy through SQLite's own backup API so the copy is never a
    half-written file, even if something is mid-write."""
    try:
        s = sqlite3.connect(src)
        d = sqlite3.connect(dest)
        with d:
            s.backup(d)
        d.close()
        s.close()
    except Exception:
        shutil.copy2(src, dest)


def verify(con) -> list[str]:
    """Check the file is sound. Empty list means all well."""
    problems: list[str] = []
    for row in con.execute("PRAGMA integrity_check"):
        if row[0] != "ok":
            problems.append(f"Database integrity: {row[0]}")
    for row in con.execute("PRAGMA foreign_key_check"):
        problems.append(f"Broken link in {row[0]} (row {row[1]}) "
                        f"pointing at {row[2]}")
    n = con.execute("SELECT COUNT(*) FROM person").fetchone()[0]
    orphan = con.execute(
        "SELECT COUNT(*) FROM person p WHERE NOT EXISTS "
        "(SELECT 1 FROM person_name n WHERE n.person_id = p.id)").fetchone()[0]
    if orphan:
        problems.append(f"{orphan} of {n} people have no name record")
    return problems


def to_json(con) -> dict:
    """Every row in the file, as plain data.

    This is the format that outlives the program. No schema knowledge is
    needed to read it: it is tables of dictionaries.
    """
    out: dict = {
        "format": "helix-archive",
        "version": 1,
        "exported": datetime.now().isoformat(timespec="seconds"),
        "note": "Plain dump of every record. Readable without Helix.",
        "tables": {},
    }
    for t in TABLES:
        try:
            rows = con.execute(f"SELECT * FROM {t}").fetchall()
        except sqlite3.OperationalError:
            continue
        out["tables"][t] = [dict(r) for r in rows]
    return out


def people_csv(con) -> str:
    """One row per person, in the form a spreadsheet or another genealogy
    program can read."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "given", "surname", "sex", "birth", "birth_place",
                "death", "death_place", "father", "mother", "confidence"])
    for r in con.execute("""
        SELECT p.id, n.given, n.surname, p.sex, p.confidence,
          (SELECT e.date_json FROM event e JOIN event_role er ON er.event_id=e.id
            WHERE er.person_id=p.id AND e.type='birth' LIMIT 1) bj,
          (SELECT pl.name FROM event e JOIN event_role er ON er.event_id=e.id
            LEFT JOIN place pl ON pl.id=e.place_id
            WHERE er.person_id=p.id AND e.type='birth' LIMIT 1) bp,
          (SELECT e.date_json FROM event e JOIN event_role er ON er.event_id=e.id
            WHERE er.person_id=p.id AND e.type='death' LIMIT 1) dj,
          (SELECT pl.name FROM event e JOIN event_role er ON er.event_id=e.id
            LEFT JOIN place pl ON pl.id=e.place_id
            WHERE er.person_id=p.id AND e.type='death' LIMIT 1) dp
        FROM person p LEFT JOIN person_name n
          ON n.person_id=p.id AND n.is_primary=1
        ORDER BY n.surname, n.given"""):
        from ..model.gendate import GenDate
        parents = [x[0] for x in con.execute(
            "SELECT up.person_id FROM union_child uc "
            "JOIN union_partner up ON up.union_id=uc.union_id "
            "WHERE uc.person_id=? ORDER BY up.seq", (r["id"],))]
        w.writerow([r["id"], r["given"] or "", r["surname"] or "", r["sex"],
                    GenDate.from_json(r["bj"]).display, r["bp"] or "",
                    GenDate.from_json(r["dj"]).display, r["dp"] or "",
                    parents[0] if parents else "",
                    parents[1] if len(parents) > 1 else "", r["confidence"]])
    return buf.getvalue()


# Insert order matters: a row cannot reference a row that does not exist yet.
RESTORE_ORDER = ["settings", "place", "person", "person_name", "union_",
                 "union_partner", "union_child", "source", "event",
                 "event_role", "citation", "media", "media_link", "tag",
                 "person_heritage",
                 "person_tag", "research_task", "dna_match"]


def restore(src: str | Path, out_db: str | Path, *,
            overwrite: bool = False) -> dict:
    """Rebuild a family file from an archive.

    Accepts either the zip written by `archive()`, a bare `family.json`, or a
    `.helix` database. This is what makes the archive a real backup rather
    than a hopeful gesture: the data can be put back.

    Returns a summary of what was restored.
    """
    from .db import connect
    src, out_db = Path(src), Path(out_db)
    if out_db.exists() and not overwrite:
        raise FileExistsError(
            f"{out_db} already exists. Choose another name, or pass "
            f"--overwrite if you really mean to replace it."
        )

    # a plain database copy needs no rebuilding
    if src.suffix == ".helix":
        _copy_consistent(src, out_db)
        con = connect(out_db)
        return {"source": "database", "tables": {},
                "people": con.execute(
                    "SELECT COUNT(*) FROM person").fetchone()[0],
                "problems": verify(con)}

    if src.suffix == ".zip":
        with zipfile.ZipFile(src) as z:
            names = z.namelist()
            if "family.json" not in names:
                raise ValueError(
                    f"{src.name} does not look like a Helix archive: it has "
                    f"no family.json. Contents: {', '.join(names[:6])}"
                )
            data = json.loads(z.read("family.json"))
            photos = [n for n in names
                      if n.startswith("media/") and not n.endswith("/")]
    else:
        data = json.loads(src.read_text())
        photos = []

    if data.get("format") != "helix-archive":
        raise ValueError(
            f"{src.name} is not a Helix archive (format is "
            f"{data.get('format', 'missing')})."
        )

    if out_db.exists():
        out_db.unlink()
    con = connect(out_db)
    tables = data.get("tables", {})
    counts: dict[str, int] = {}
    con.execute("PRAGMA foreign_keys = OFF")       # rows arrive out of order
    for t in RESTORE_ORDER:
        rows = tables.get(t) or []
        if not rows:
            continue
        cols = list(rows[0].keys())
        have = {r[1] for r in con.execute(f"PRAGMA table_info({t})")}
        cols = [c for c in cols if c in have]
        if not cols:
            continue
        q = (f"INSERT OR REPLACE INTO {t} ({','.join(cols)}) "
             f"VALUES ({','.join('?' * len(cols))})")
        con.executemany(q, [[r.get(c) for c in cols] for r in rows])
        counts[t] = len(rows)
    con.commit()
    con.execute("PRAGMA foreign_keys = ON")
    problems = verify(con)

    # AND THE PHOTOGRAPHS BACK BESIDE THE FILE. The `media` rows restored
    # above name files by content hash; without this they name nothing, and
    # a restored family would open with every portrait missing and no way
    # to tell whether it ever had one.
    restored_photos = 0
    if photos:
        from .album import album_dir
        d = album_dir(out_db, create=True)
        with zipfile.ZipFile(src) as z:
            for n in photos:
                name = Path(n).name
                if not name or name.startswith("."):
                    continue
                (d / name).write_bytes(z.read(n))
                restored_photos += 1

    return {"source": "archive",
            "exported": data.get("exported"),
            "tables": counts,
            "people": counts.get("person", 0),
            "photos": restored_photos,
            "problems": problems}


README = """HELIX ARCHIVE
=============

This zip is a complete, self-contained copy of a family tree. Keep it
somewhere that is not your computer.

  family.helix     The database itself. Open it with Helix, or with any
                   SQLite tool -- it is an ordinary SQLite file.
  family.json      Every record as plain data. THIS IS THE ONE THAT MATTERS
                   in the long run: it can be read by any language on any
                   machine, with or without Helix.
  people.csv       One row per person, for a spreadsheet or another
                   genealogy program.
  renders/         The charts as they looked when this archive was made.

To put this back into Helix:

    helix restore <this-file>.zip -o my-family.helix

If Helix has vanished and you need the data back, family.json holds
everything. Each table is a list of records; people are in "person" and
"person_name", families in "union_", "union_partner" and "union_child", and
facts in "event" and "event_role". Dates are stored as intervals, so
"about 1834" survives as a range rather than a false certainty.
"""


def archive(db_path: str | Path, out_path: str | Path | None = None,
            renders: list[Path] | None = None) -> Path:
    """Write a portable zip holding everything."""
    from .db import connect
    db_path = Path(db_path)
    stamp = datetime.now().strftime("%Y%m%d")
    out_path = Path(out_path) if out_path else \
        db_path.parent / f"{db_path.stem}-archive-{stamp}.zip"
    con = connect(db_path, create=False)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", README)
        z.write(db_path, "family.helix")
        z.writestr("family.json",
                   json.dumps(to_json(con), indent=1, default=str))
        z.writestr("people.csv", people_csv(con))
        # THE PHOTOGRAPHS TOO. The `media` rows name files that live beside
        # the database, so a zip holding only the rows is a zip of two
        # hundred captions with nothing under them -- and the whole promise
        # of an archive is that it is the copy you can keep somewhere else.
        from .album import album_dir
        adir = album_dir(db_path)
        if adir.is_dir():
            for f in sorted(adir.iterdir()):
                if f.is_file():
                    z.write(f, f"media/{f.name}")
        for r in renders or []:
            if Path(r).exists():
                z.write(r, f"renders/{Path(r).name}")
    return out_path
