"""Where a person's family files live, and how the program finds them again.

WHY THIS EXISTS. Run from a terminal, Helix is handed a path and that is the
whole of its storage question. Run as an application somebody double-clicks,
there is no path: the program has to know where its files are, put new ones
somewhere sensible, remember which one was open last, and never lose track
of a decade of research because somebody moved a folder.

THE LIBRARY IS A PLAIN FOLDER OF PLAIN FILES, and that is a decision.

  Documents/Helix/
      Whitcombe.helix             the family. An ordinary SQLite file.
      Whitcombe-media/            the photographs, beside it.
      backups/                    thirty dated copies, taken automatically.
      Whitcombe-archive-*.zip     whatever `Export → Archive` has written.

  Not a hidden application-support directory, not a proprietary bundle, and
  not a database of databases. Somebody who has kept a family tree for ten
  years wants to be able to find it, copy it to a memory stick, put it in
  Dropbox and hand it to their daughter. A file they cannot see is a file
  they cannot look after, and this program's whole promise is that the work
  outlives the program (`docs/KEEPING_YOUR_WORK.md`).

WHAT IS HIDDEN is only the preference: which folder is the library and which
file was open last. That goes in the platform's own config location, because
it is Helix's business and not the person's.

  Windows   %APPDATA%\\Helix\\settings.json
  macOS     ~/Library/Application Support/Helix/settings.json
  Linux     ~/.config/helix/settings.json
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

APP = "Helix"
SUFFIX = ".helix"


# ------------------------------------------------------------------ places


def config_dir() -> Path:
    """Where Helix keeps its own preference file. Never the family's data."""
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")
        return Path(base) / APP
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / APP.lower()


def default_library() -> Path:
    """Documents/Helix, or the home folder if there is no Documents.

    VISIBLE ON PURPOSE. macOS would rather this went in Application Support
    and Windows in AppData; both are places people do not look, cannot find
    with Finder or Explorer, and are wiped by "reset this app". A genealogy
    file is the single most irreplaceable thing on somebody's computer and
    it belongs where they keep the rest of their irreplaceable things.
    """
    docs = Path.home() / "Documents"
    if not docs.is_dir():
        # OneDrive redirects Documents on a lot of Windows machines.
        alt = Path.home() / "OneDrive" / "Documents"
        docs = alt if alt.is_dir() else Path.home()
    return docs / APP


# ------------------------------------------------------------- preferences


def _settings_path() -> Path:
    return config_dir() / "settings.json"


def load_settings() -> dict:
    try:
        return json.loads(_settings_path().read_text())
    except Exception:
        return {}


def save_settings(d: dict) -> None:
    p = _settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, indent=1))
    tmp.replace(p)                          # never a half-written settings file


def library_dir(create: bool = True) -> Path:
    d = Path(load_settings().get("library") or default_library())
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def set_library_dir(path: str | Path) -> Path:
    d = Path(path).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    s = load_settings()
    s["library"] = str(d)
    save_settings(s)
    return d


# --------------------------------------------------------------- the files


def _safe_name(title: str) -> str:
    """A file name from what somebody typed, on every platform.

    Windows refuses `< > : " / \\ | ? *` and a trailing dot, and reserves
    CON, PRN, AUX, NUL, COM1-9 and LPT1-9 whatever the extension. A family
    called "Aux" is not likely; a family called "Smith/Jones" is, and it is
    the one that would have failed silently on a share.
    """
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", title or "").strip(" .")
    name = re.sub(r"\s+", " ", name) or "My family"
    if re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", name):
        name += " family"
    return name[:80]


def unique_path(title: str, folder: Optional[Path] = None) -> Path:
    """A free path for a new family, without ever overwriting one."""
    folder = Path(folder) if folder else library_dir()
    folder.mkdir(parents=True, exist_ok=True)
    stem = _safe_name(title)
    p = folder / f"{stem}{SUFFIX}"
    n = 2
    while p.exists():
        p = folder / f"{stem} {n}{SUFFIX}"
        n += 1
    return p


def _peek(path: Path, sql: str, args=()):
    """One question of a family file, without disturbing it.

    READ-ONLY FIRST, THEN ORDINARY. `mode=ro` is the right way to look at
    somebody else's file — but a database in WAL mode needs to create a
    `-shm` alongside it, and a read-only connection cannot, so the file
    Helix itself currently has open is exactly the one `mode=ro` refuses.
    That is the file whose title is most worth reading, and it came back
    as the bare stem: the library listed the open family under its file
    name and every other family under its real one.
    """
    import sqlite3
    for uri, kw in ((f"file:{path}?mode=ro", {"uri": True}), (str(path), {})):
        try:
            con = sqlite3.connect(uri, timeout=0.5, **kw)
            try:
                return con.execute(sql, args).fetchone()
            finally:
                con.close()
        except Exception:
            continue
    return None


def _title_of(path: Path) -> str:
    # `settings` is (k, v) -- see store/schema.sql. Asked for (key, value)
    # this threw every time and fell through to the stem, so the library
    # listed every family under its file name and none under its own.
    r = _peek(path, "SELECT v FROM settings WHERE k=?", ("project_title",))
    return (r[0] if r else "") or path.stem


def _count(path: Path) -> Optional[int]:
    r = _peek(path, "SELECT COUNT(*) FROM person WHERE COALESCE(active,1)=1")
    return r[0] if r else None


def families(folder: Optional[Path] = None) -> list[dict]:
    """Every family file in the library, most recently opened first."""
    folder = Path(folder) if folder else library_dir()
    recent = [str(Path(x)) for x in load_settings().get("recent", [])]
    out = []
    for p in sorted(folder.glob(f"*{SUFFIX}")):
        if p.name.startswith("."):
            continue
        st = p.stat()
        try:
            rank = recent.index(str(p))
        except ValueError:
            rank = 10_000
        out.append({
            "path": str(p), "name": p.stem, "title": _title_of(p),
            "people": _count(p), "size_kb": round(st.st_size / 1024),
            "modified": datetime.fromtimestamp(st.st_mtime)
                                .isoformat(timespec="minutes"),
            "recent_rank": rank,
            "backups": len(list((p.parent / "backups")
                                .glob(f"{p.stem}-*"))) if (p.parent / "backups").is_dir() else 0,
        })
    out.sort(key=lambda r: (r["recent_rank"], -Path(r["path"]).stat().st_mtime))
    return out


def remember(path: str | Path) -> None:
    """Note that this file was opened. Ten deep, newest first."""
    s = load_settings()
    p = str(Path(path).resolve())
    rec = [x for x in s.get("recent", []) if x != p]
    s["recent"] = [p] + rec[:9]
    s["last"] = p
    save_settings(s)


def last_opened() -> Optional[Path]:
    p = load_settings().get("last")
    return Path(p) if p and Path(p).exists() else None


def create(title: str, folder: Optional[Path] = None,
           sample: bool = False) -> Path:
    """A new family file, ready to open."""
    from ..store.db import connect, set_setting
    path = unique_path(title, folder)
    con = connect(path)
    set_setting(con, "project_title", title or path.stem)
    if sample:
        from tools.make_sample import build          # type: ignore
        build(con)
    con.commit()
    con.close()
    remember(path)
    return path


def rename(path: str | Path, title: str) -> dict:
    """Change what a family is called, inside the file and on disk.

    BOTH, OR NEITHER. The title lives in the file and the name lives on the
    disk, and letting them drift means a folder of `family.helix`,
    `family2.helix`, `family3.helix` with no way to tell which is which
    without opening all three.
    """
    from ..store.db import connect, set_setting
    path = Path(path)
    con = connect(path, create=False)
    set_setting(con, "project_title", title)
    con.commit()
    # CHECKPOINT BEFORE MOVING IT. The file is opened in WAL mode, which
    # means a `-wal` and a `-shm` sitting beside it holding writes that are
    # committed but not yet folded in. Renamed without this, the database
    # moves and its own write-ahead log does not: SQLite then reports
    # "disk I/O error" on the next open and the last few edits are stranded
    # in a file with the wrong name.
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()

    want = unique_path(title, path.parent)
    if want.stem == path.stem:
        return {"path": str(path), "title": title, "renamed": False}
    moved = []
    for src, dst in ((path, want),
                     (Path(str(path) + "-wal"), Path(str(want) + "-wal")),
                     (Path(str(path) + "-shm"), Path(str(want) + "-shm")),
                     (path.with_name(path.stem + "-media"),
                      want.with_name(want.stem + "-media"))):
        if src.exists():
            src.rename(dst)
            moved.append(dst.name)
    remember(want)
    return {"path": str(want), "title": title, "renamed": True, "moved": moved}


def duplicate(path: str | Path) -> Path:
    """A copy, for trying something out.

    Through SQLite's own backup API, so the copy is never a half-written
    file even if something is mid-write -- the same reason `archive.py`
    does it that way.
    """
    from ..store.archive import _copy_consistent
    path = Path(path)
    dest = unique_path(f"{_title_of(path)} copy", path.parent)
    _copy_consistent(path, dest)
    media = path.with_name(path.stem + "-media")
    if media.is_dir():
        shutil.copytree(media, dest.with_name(dest.stem + "-media"),
                        dirs_exist_ok=True)
    return dest


def copy_for(path: str | Path, person_id: str, *, title: str = "",
             prune: bool = False, dry_run: bool = False) -> dict:
    """The same family, as somebody else's tree.

    WHY THIS IS A WHOLE FEATURE AND NOT A SETTING. Every relation in this
    program is measured from one person: who counts as a cousin, whose lines
    are worth researching, what the chart puts at its centre, what the record
    book calls each entry. Change that person and you have not changed a
    preference — you have a different document about the same family.

    So a niece who wants her own tree gets a FILE OF HER OWN. The original is
    not touched, not linked to and not consulted again: she can add her
    mother's family, delete a branch, get the dates wrong, and none of it
    reaches back. That is what makes it safe to hand over.

    PRUNING, and why it is offered rather than done. Her father's brother's
    wife's parents are in the file and are no relation to her at all. Leaving
    them in is not wrong exactly -- they are somebody's family -- but they
    are a third of a chart she cannot read and a research list about
    strangers. So the branches with no path to her are offered up, BY NAME
    and with a count, and she decides. Left in, nothing happens; taken out,
    they are retired the ordinary way and one Ctrl-Z in the new file brings
    them back.

    Returns what was done, or -- with `dry_run` -- what WOULD be done, which
    is what the interface asks for first so the question can be put in front
    of somebody with real names in it.
    """
    from ..graph.build import load
    from ..graph.kinship import Kinship
    from ..store.db import connect, set_setting
    from ..store.records import Edit
    from ..store.archive import _copy_consistent

    src = Path(path)
    con = connect(src, create=False)
    g = load(con)
    if person_id not in g.people:
        con.close()
        raise ValueError("Choose somebody who is in this family file.")
    who = g.people[person_id]
    kin = Kinship(g, person_id)

    # NO PATH TO THEM AT ALL. Not blood, not marriage, not a marriage to
    # somebody they are related to -- `Kinship` has already worked out all
    # three, and this reads its answer rather than deciding again.
    strangers = sorted(
        (pid for pid in g.people
         if kin.of(pid).group == "unrelated" and pid != person_id),
        key=lambda p: (g.people[p].surname or "", g.people[p].given or ""))

    # Grouped into FAMILIES, because "leave out 34 people" is a number
    # nobody can check and "Michaela Denton's own family, 34 people" is a
    # decision somebody can actually make.
    #
    # A family here is a connected lump: parents, children and partners
    # followed until it stops. Grouped by ancestry alone a woman and her own
    # brother came out as two separate branches, which is two questions
    # about one family and the wrong two.
    rest = set(strangers)
    branches: list[dict] = []
    while rest:
        seed = next(iter(rest))
        lump, queue = set(), [seed]
        while queue:
            x = queue.pop()
            if x in lump or x not in rest:
                continue
            lump.add(x)
            queue.extend(g.parents(x, primary_only=False))
            queue.extend(g.children(x))
            queue.extend(g.partners(x))
        rest -= lump
        # WHO IN THE FILE THIS LUMP HANGS OFF, because that is the name the
        # person deciding will recognise. Michaela's parents and her brother
        # are three strangers with a Denton surname; "Michaela Denton's own
        # family" is a thing somebody can say yes or no to.
        #
        # Looked for through partners ALONE it was not found: the bridge is
        # usually the married-in person, and she is her brother's SISTER,
        # not anybody's partner in this lump. So every kind of link counts.
        touching: list[str] = []
        for x in sorted(lump):
            for near in (g.partners(x) + g.children(x)
                         + g.parents(x, primary_only=False)
                         + [c for u in g.people[x].child_of_all
                            for c in g.unions[u].children]):
                if near in g.people and near not in lump \
                        and kin.of(near).group != "unrelated":
                    touching.append(near)
        via = ""
        if touching:
            # The married-in person first: they are the join, and everybody
            # else is only near it.
            touching.sort(key=lambda p: (kin.of(p).group != "married_in",
                                         kin.of(p).rank))
            via = g.people[touching[0]].full_name
        # The oldest of them is the one to name a nameless branch after.
        head = min(lump, key=lambda p: (g.people[p].birth.sort_value or 9e9,
                                        g.people[p].full_name))
        branches.append({
            "id": head, "name": g.people[head].full_name,
            "people": sorted(lump), "count": len(lump),
            "through": via,
            "label": (f"{via}'s own family" if via else
                      f"{g.people[head].full_name} and their line"),
            "blurb": f"{len(lump)} " + ("person" if len(lump) == 1
                                        else "people"),
            "names": [g.people[p].full_name for p in sorted(
                lump, key=lambda p: (g.people[p].birth.sort_value or 9e9))][:6],
        })
    branches.sort(key=lambda b: (-b["count"], b["label"]))

    plan = {
        "root": {"id": person_id, "name": who.full_name,
                 "life": who.lifespan},
        "people": len(g.people),
        "unrelated": len(strangers),
        "branches": branches,
        "title": title or f"{who.short_name}'s family",
    }
    if dry_run:
        con.close()
        return plan

    con.close()
    dest = unique_path(plan["title"], src.parent)
    _copy_consistent(src, dest)
    media = src.with_name(src.stem + "-media")
    if media.is_dir():
        shutil.copytree(media, dest.with_name(dest.stem + "-media"),
                        dirs_exist_ok=True)

    out = connect(dest, create=False)
    set_setting(out, "project_title", plan["title"])
    set_setting(out, "subject_person_id", person_id)
    removed = 0
    if prune and strangers:
        # ONE undoable step, so the whole pruning goes back together. Retire
        # and not delete: rule seven, and the reason somebody can hand this
        # file to a relative without holding their breath.
        with Edit(out, f"Leave out {len(strangers)} people no relation "
                       f"to {who.short_name}") as e:
            for pid in strangers:
                e.update("person", {"id": pid}, {"active": 0})
                for r in out.execute("SELECT union_id FROM union_partner "
                                     "WHERE person_id=?", (pid,)).fetchall():
                    e.delete("union_partner",
                             {"union_id": r["union_id"], "person_id": pid})
                for r in out.execute("SELECT union_id FROM union_child "
                                     "WHERE person_id=?", (pid,)).fetchall():
                    e.delete("union_child",
                             {"union_id": r["union_id"], "person_id": pid})
                removed += 1
    out.commit()
    out.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    out.close()
    remember(dest)
    return {**plan, "path": str(dest), "removed": removed,
            "message": (f"{plan['title']} is a file of its own, with "
                        f"{who.short_name} at the centre."
                        + (f" {removed} people who are no relation to "
                           f"{who.short_name} were left out — open it and "
                           f"press Ctrl-Z to bring them back."
                           if removed else ""))}


def reveal(path: str | Path) -> bool:
    """Show the file in Finder or Explorer.

    THE ANSWER TO "WHERE IS MY DATA". Somebody who has just been told their
    work is in a folder should be able to see that folder, and a button
    that opens it is worth more than a paragraph explaining the path.
    """
    p = Path(path)
    try:
        if platform.system() == "Windows":
            os.startfile(p if p.is_dir() else p.parent)      # noqa: S606
        elif platform.system() == "Darwin":
            import subprocess
            subprocess.Popen(["open", "-R", str(p)] if p.is_file()
                             else ["open", str(p)])
        else:
            import subprocess
            subprocess.Popen(["xdg-open", str(p if p.is_dir() else p.parent)])
        return True
    except Exception:
        return False


def status(path: str | Path) -> dict:
    """Everything the app needs to reassure somebody their work is safe."""
    p = Path(path)
    bdir = p.parent / "backups"
    backups = sorted(bdir.glob(f"{p.stem}-*")) if bdir.is_dir() else []
    media = p.with_name(p.stem + "-media")
    return {
        "path": str(p), "folder": str(p.parent), "name": p.stem,
        "title": _title_of(p) if p.exists() else p.stem,
        "exists": p.exists(),
        "size_kb": round(p.stat().st_size / 1024) if p.exists() else 0,
        "modified": (datetime.fromtimestamp(p.stat().st_mtime)
                     .isoformat(timespec="minutes") if p.exists() else None),
        "backups": len(backups),
        "newest_backup": backups[-1].name if backups else None,
        "photos": len([x for x in media.iterdir() if x.is_file()])
                  if media.is_dir() else 0,
        "library": str(library_dir(create=False)),
    }


def first_run() -> dict:
    """What to open when the application starts with no argument.

    Order matters and each step is a decision:
      1. the file that was open last, if it is still there
      2. the only file in the library, if there is exactly one
      3. nothing -- show the library screen and let somebody choose

    Never "create one silently": a genealogy program that invents an empty
    file on first launch teaches people that their work might not be where
    they left it.
    """
    last = last_opened()
    if last:
        return {"open": str(last), "why": "the one you had open"}
    fams = families()
    if len(fams) == 1:
        return {"open": fams[0]["path"], "why": "the only family in your folder"}
    return {"open": None, "why": "choose or start one",
            "families": fams, "library": str(library_dir())}


def is_frozen() -> bool:
    """True inside a PyInstaller bundle, where paths work differently."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
