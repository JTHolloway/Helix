"""Photographs, kept beside the family file.

WHY THE PICTURES ARE COPIED AND NOT REFERENCED. A path into somebody's
Pictures folder is a promise the program cannot keep: the folder gets tidied,
the phone gets replaced, the laptop dies, and the file that survives all
three is the one thing this program tells people to keep. A tree with two
hundred broken image links is worse than one with none, because it says a
picture existed and cannot show it.

So an image is COPIED, once, into an album folder beside the database:

    my-family.helix
    my-family-media/
        3f2a9c….jpg
        7b18e0….png

Named by the SHA-256 of its own bytes, which gives three things for free.
The same photograph attached to five brothers is stored once. Re-attaching a
picture somebody already added is silently the same picture rather than a
second copy. And the name can never collide, contain a directory, or be
talked into pointing somewhere else -- which matters because the name comes
in over HTTP.

The `media` and `media_link` tables were in `schema.sql` from the start;
this fills them in. `store/archive.py` walks the album so a zip of the
family holds the pictures too, and a restore puts them back.
"""
from __future__ import annotations

import base64
import hashlib
import shutil
from pathlib import Path
from typing import Optional

from .db import new_id

# What a browser will hand us, and what a laser or a printer can read back.
# Deliberately short: this is a family archive, not a media library, and
# every format here will still open in thirty years.
TYPES = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
    "image/gif": ".gif", "image/heic": ".heic", "image/tiff": ".tif",
}
BY_EXT = {v: k for k, v in TYPES.items()}
MAX_BYTES = 24 * 1024 * 1024


def album_dir(db_path: str | Path, create: bool = False) -> Path:
    """The folder beside the family file. Named after it, so moving the two
    together is obvious and moving only one is obviously wrong."""
    p = Path(db_path)
    d = p.parent / f"{p.stem}-media"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def _ext_for(mime: str, filename: str) -> str:
    if mime in TYPES:
        return TYPES[mime]
    suf = Path(filename or "").suffix.lower()
    return suf if suf in BY_EXT else ".jpg"


def store_bytes(db_path: str | Path, raw: bytes, *, filename: str = "",
                mime: str = "") -> tuple[str, Path]:
    """Put the bytes in the album. Returns (stored name, full path).

    Idempotent by content: the same photograph added twice is one file.
    """
    if not raw:
        raise ValueError("That file was empty. Try choosing it again.")
    if len(raw) > MAX_BYTES:
        raise ValueError(
            f"That picture is {len(raw) // (1024 * 1024)} MB, and the limit is "
            f"{MAX_BYTES // (1024 * 1024)} MB. Save a smaller copy and try "
            f"again — a photograph does not need to be larger than the "
            f"screen it is looked at on.")
    name = hashlib.sha256(raw).hexdigest()[:32] + _ext_for(mime, filename)
    d = album_dir(db_path, create=True)
    path = d / name
    if not path.exists():
        path.write_bytes(raw)
    return name, path


def store_data_url(db_path: str | Path, data_url: str,
                   filename: str = "") -> tuple[str, Path]:
    """A `data:` URL, which is what a browser's FileReader produces.

    Chosen over multipart because it needs no parser: the standard library
    has no multipart reader that is safe to point at untrusted input, and
    writing one to accept a photograph would be the largest attack surface
    in the program.
    """
    head, _, b64 = data_url.partition(",")
    if not b64 or not head.startswith("data:"):
        raise ValueError("That did not look like an image. Try again.")
    mime = head[5:].split(";")[0]
    if mime and mime not in TYPES:
        raise ValueError(
            f"Helix keeps photographs as JPEG, PNG, WebP, GIF, HEIC or TIFF, "
            f"and that one is {mime}. Export it as a JPEG and try again.")
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception:
        raise ValueError("That picture could not be read. Try another copy.")
    return store_bytes(db_path, raw, filename=filename, mime=mime)


def store_file(db_path: str | Path, src: str | Path) -> tuple[str, Path]:
    """Copy a file already on disk. Used by the importer and the tests."""
    src = Path(src)
    return store_bytes(db_path, src.read_bytes(), filename=src.name)


def resolve(db_path: str | Path, name: str) -> Optional[Path]:
    """The full path of a stored picture, or None.

    The name arrives over HTTP, so it is checked rather than trusted: only a
    bare filename, and the result has to still be inside the album after
    resolving. `..%2f..%2fetc%2fpasswd` is one request away otherwise.
    """
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    d = album_dir(db_path).resolve()
    try:
        p = (d / name).resolve()
    except OSError:
        return None
    if not str(p).startswith(str(d)) or not p.is_file():
        return None
    return p


def mime_for(name: str) -> str:
    return BY_EXT.get(Path(name).suffix.lower(), "application/octet-stream")


# --------------------------------------------------------------- the rows --
def attach(con, pid: str, name: str, *, caption: str = "",
           portrait: bool = True) -> str:
    """Link a stored picture to a person.

    Goes through `records.Edit` like every other write, so adding a
    photograph is undoable and shows up in the history with a plain label.
    One portrait each: setting a new one demotes the old rather than
    deleting it, because the previous photograph is still a photograph of
    them.
    """
    from . import records
    with records.Edit(con, f"Add a photo of {records.display_name(con, pid)}") as e:
        row = con.execute("SELECT id FROM media WHERE path=?", (name,)).fetchone()
        mid = row["id"] if row else new_id()
        if not row:
            e.insert("media", {"id": mid, "path": name, "type": mime_for(name),
                               "caption": caption or None,
                               "sha256": Path(name).stem})
        if portrait:
            for r in con.execute(
                "SELECT media_id FROM media_link WHERE person_id=? "
                "AND is_portrait=1", (pid,)
            ):
                e.update("media_link",
                         {"media_id": r["media_id"], "person_id": pid,
                          "event_id": None}, {"is_portrait": 0})
        have = con.execute(
            "SELECT 1 FROM media_link WHERE media_id=? AND person_id=?",
            (mid, pid)).fetchone()
        if have:
            e.update("media_link", {"media_id": mid, "person_id": pid,
                                    "event_id": None},
                     {"is_portrait": 1 if portrait else 0})
        else:
            e.insert("media_link", {"media_id": mid, "person_id": pid,
                                    "event_id": None,
                                    "is_portrait": 1 if portrait else 0})
    return mid


def detach(con, pid: str, media_id: str) -> None:
    """Take a picture off a person. The FILE stays in the album: another
    person may be in it, and a photograph is not something to delete because
    one caption was wrong."""
    from . import records
    with records.Edit(con, f"Remove a photo of "
                           f"{records.display_name(con, pid)}") as e:
        e.delete("media_link", {"media_id": media_id, "person_id": pid,
                                "event_id": None})


def photos_of(con, pid: str) -> list[dict]:
    """Every picture linked to somebody, the portrait first."""
    return [{"media_id": r["id"], "name": r["path"], "type": r["type"],
             "caption": r["caption"] or "", "portrait": bool(r["is_portrait"])}
            for r in con.execute(
                "SELECT m.id, m.path, m.type, m.caption, l.is_portrait "
                "FROM media m JOIN media_link l ON l.media_id = m.id "
                "WHERE l.person_id = ? "
                "ORDER BY l.is_portrait DESC, m.path", (pid,))]


def portrait_of(con, pid: str) -> Optional[dict]:
    ph = [p for p in photos_of(con, pid) if p["portrait"]]
    return ph[0] if ph else None


def copy_album(db_path: str | Path, into: str | Path) -> int:
    """Copy the whole album somewhere. `archive.py` uses it so a zip of the
    family holds the pictures and not just the rows that name them."""
    src = album_dir(db_path)
    if not src.is_dir():
        return 0
    dest = Path(into)
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(src.iterdir()):
        if f.is_file():
            shutil.copy2(f, dest / f.name)
            n += 1
    return n
