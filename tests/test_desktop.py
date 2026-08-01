"""Helix as an application somebody double-clicks.

Two halves, and they fail differently.

  library.py  where family files live on the host computer. This is the
              half that must never lose anything: a decade of research
              behind a rename, a folder somebody moved, a name with a slash
              in it that Windows refuses.
  app.py      the window and the server behind it. Tested for what can be
              tested without a display: that it finds a free port, waits
              for the server, and picks a launch method rather than
              crashing when pywebview is not installed.
"""
from __future__ import annotations

import json
import os
import threading
import urllib.request
from pathlib import Path

import pytest

from helix.desktop import app, library
from helix.store.db import connect, get_setting, set_setting

from test_records import Client, add                      # noqa: F401


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A whole fake home directory, so nothing touches the real one."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    (tmp_path / "Documents").mkdir()
    return tmp_path


# ------------------------------------------------------------ where it lives
def test_families_live_where_a_person_can_find_them(home):
    """VISIBLE ON PURPOSE. macOS would rather this went in Application
    Support and Windows in AppData; both are places people cannot find with
    Finder or Explorer and that "reset this app" wipes. A genealogy file is
    the most irreplaceable thing on somebody's computer."""
    d = library.default_library()
    assert d == home / "Documents" / "Helix"
    assert "Application Support" not in str(d)
    assert "AppData" not in str(d)


def test_the_preference_is_hidden_but_the_data_is_not(home):
    """Which folder is the library is Helix's business; the family is the
    person's."""
    cfg = library.config_dir()
    assert cfg != library.default_library()
    library.set_library_dir(home / "elsewhere")
    assert library.library_dir() == home / "elsewhere"
    assert (cfg / "settings.json").exists()
    assert json.loads((cfg / "settings.json").read_text())["library"] \
        == str(home / "elsewhere")


def test_a_new_family_is_a_real_file_with_a_real_title(home):
    p = library.create("The Whitcombes")
    assert p.exists() and p.suffix == ".helix"
    assert p.parent == library.library_dir()
    assert get_setting(connect(p, create=False), "project_title") == "The Whitcombes"


def test_two_families_of_the_same_name_never_overwrite(home):
    a = library.create("Smith")
    b = library.create("Smith")
    assert a != b and a.exists() and b.exists()


@pytest.mark.parametrize("typed,ok", [
    ("Smith/Jones", "Smith Jones.helix"),          # a slash is not a folder
    ("CON", "CON family.helix"),                   # reserved on Windows
    ('Bad:"name"', "Bad name.helix"),
    ("   ...   ", "My family.helix"),
    ("Ó Súilleabháin", "Ó Súilleabháin.helix"),    # accents are fine
])
def test_a_family_name_becomes_a_file_name_on_every_platform(home, typed, ok):
    """Windows refuses < > : " / \\ | ? * and reserves CON, PRN, AUX and
    friends whatever the extension. A family called Aux is unlikely; one
    called Smith/Jones is not, and that is the one that fails silently on
    a network share."""
    assert library.unique_path(typed).name == ok


def test_the_library_lists_what_is_in_the_folder(home):
    library.create("Alpha")
    library.create("Beta")
    got = {f["title"]: f for f in library.families()}
    assert set(got) == {"Alpha", "Beta"}
    assert got["Alpha"]["people"] == 0
    assert got["Alpha"]["path"].endswith("Alpha.helix")


def test_the_title_is_read_from_inside_the_file_not_the_name(home):
    """`settings` is (k, v). Asked for (key, value) the read threw every
    time and fell back to the file name, so every family in the library was
    listed under its file rather than under itself."""
    p = library.create("Alpha")
    con = connect(p, create=False)
    set_setting(con, "project_title", "The Alpha Family of Bath")
    con.close()
    assert library.families()[0]["title"] == "The Alpha Family of Bath"


def test_a_family_that_is_open_still_reads(home):
    """`mode=ro` cannot create the `-shm` a WAL database needs, so the one
    file Helix itself has open is exactly the one a read-only peek refuses
    — and it is the one whose title matters most."""
    p = library.create("Open Now")
    con = connect(p, create=False)                  # held open, WAL, as the server does
    set_setting(con, "project_title", "Held Open")
    try:
        assert library.families()[0]["title"] == "Held Open"
        assert library.status(p)["title"] == "Held Open"
    finally:
        con.close()


def test_renaming_moves_the_file_and_its_photographs(home):
    p = library.create("Old Name")
    media = p.with_name(p.stem + "-media")
    media.mkdir()
    (media / "portrait.jpg").write_bytes(b"not really a jpeg")
    out = library.rename(p, "New Name")
    assert out["renamed"]
    new = Path(out["path"])
    assert new.exists() and not p.exists()
    assert (new.with_name(new.stem + "-media") / "portrait.jpg").exists()
    assert get_setting(connect(new, create=False), "project_title") == "New Name"


def test_renaming_an_open_file_does_not_strand_its_write_ahead_log(home):
    """The file is opened in WAL mode, so a `-wal` sits beside it holding
    writes that are committed but not folded in. Moved without the log, the
    next open reports "disk I/O error" and the last edits are stranded in a
    file with the wrong name."""
    p = library.create("Wally")
    con = connect(p, create=False)
    from helix.store.records import add_person
    add_person(con, {"given": "Written", "surname": "Late"})
    con.close()
    out = library.rename(p, "Wally Renamed")
    new = Path(out["path"])
    from helix.graph.build import load
    g = load(connect(new, create=False))            # must not raise
    assert any(x.full_name == "Written Late" for x in g.people.values())
    assert not Path(str(p) + "-wal").exists()


def test_a_copy_is_a_whole_copy(home):
    p = library.create("Original")
    media = p.with_name(p.stem + "-media")
    media.mkdir()
    (media / "a.jpg").write_bytes(b"x")
    d = library.duplicate(p)
    assert d.exists() and d != p
    assert (d.with_name(d.stem + "-media") / "a.jpg").exists()
    assert p.exists(), "duplicating must not touch the original"


def test_what_to_open_on_a_first_launch(home):
    """1. what you had open  2. the only one there  3. ask.
    Never "create one silently" -- that teaches people their work might not
    be where they left it."""
    assert library.first_run()["open"] is None      # nothing yet: ask
    a = library.create("Only One")
    library.save_settings({k: v for k, v in library.load_settings().items()
                           if k not in ("last", "recent")})
    assert Path(library.first_run()["open"]) == a   # exactly one: open it
    b = library.create("Second")
    assert Path(library.first_run()["open"]) == b   # now: the last one opened


def test_a_file_that_has_been_moved_away_is_not_offered(home):
    p = library.create("Gone")
    library.remember(p)
    p.unlink()
    assert library.last_opened() is None


def test_status_answers_where_is_my_data(home):
    p = library.create("Somewhere")
    st = library.status(p)
    assert st["path"].endswith("Somewhere.helix")
    assert st["folder"] == str(library.library_dir())
    assert st["exists"] and st["size_kb"] > 0


# ---------------------------------------------------------------- the window
def test_it_asks_the_operating_system_for_a_free_port():
    """A fixed port fails the second time somebody opens two families; a
    guess fails whenever something else has it."""
    a, b = app.free_port(), app.free_port()
    assert 1024 < a < 65536 and 1024 < b < 65536


def test_the_window_never_opens_on_a_server_that_is_not_answering(home):
    assert app.wait_for("http://127.0.0.1:1/", timeout=0.4) is False


def test_the_backend_starts_and_stops(home):
    p = library.create("Backend")
    back = app.Backend(p).start()
    try:
        with urllib.request.urlopen(back.url + "api/meta") as r:
            assert json.load(r)["title"] == "Backend"
    finally:
        back.stop()


def test_launching_falls_back_rather_than_failing(home, monkeypatch):
    """THE CORE STAYS DEPENDENCY-FREE. Without pywebview and without a
    Chromium-family browser it opens an ordinary tab; it must never be an
    error that a machine has neither."""
    p = library.create("Fallback")
    monkeypatch.setattr(app, "_pywebview", lambda url, title: False)
    monkeypatch.setattr(app, "_app_window", lambda url: None)
    opened = {}
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda u: opened.setdefault("url", u))

    def stop_immediately(secs):
        raise KeyboardInterrupt
    monkeypatch.setattr(app.time, "sleep", stop_immediately)
    assert app.launch(p, quiet=True) == 0
    assert opened["url"].startswith("http://127.0.0.1:")


def test_opening_a_file_that_is_not_there_says_where_to_look(home):
    """Rule 8: every message says what to do next."""
    with pytest.raises(SystemExit) as e:
        app.launch(home / "nope.helix", quiet=True)
    assert "no family file" in str(e.value)
    assert str(library.library_dir()) in str(e.value)


def test_macos_process_serial_numbers_are_not_mistaken_for_a_path(monkeypatch):
    """Double-clicking a .helix file in Finder launches the bundle with
    `-psn_0_12345` -- a process serial number, not a path -- and argparse
    would refuse to start over it."""
    monkeypatch.setattr(app.sys, "argv", ["Helix", "-psn_0_774323", "x.helix"])
    assert app._argv_from_os() == ["x.helix"]


# --------------------------------------------------------------- in the app
@pytest.fixture
def running(home):
    from helix.server import make_server
    a = library.create("First Family")
    library.create("Second Family")
    srv = make_server(str(a), port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    c = Client(f"http://127.0.0.1:{srv.server_port}")
    try:
        yield c, a
    finally:
        srv.shutdown()
        srv.server_close()


def test_the_app_can_say_where_the_files_are(running):
    c, a = running
    d = c.get("library")
    assert d["library"] == str(library.library_dir())
    assert Path(d["current"]) == a
    assert {f["title"] for f in d["families"]} == {"First Family", "Second Family"}


def test_switching_family_rebuilds_the_whole_window(running):
    """`State` holds one connection, one graph and one kinship index and
    every screen reads them. Pointed at a new path without a reload, half
    the window would still be describing the family you just closed."""
    c, a = running
    other = next(f for f in c.get("library")["families"]
                 if f["title"] == "Second Family")
    assert c.post("library/open", {"path": other["path"]})["opened"]
    assert c.get("meta")["title"] == "Second Family"
    assert Path(c.get("library")["current"]) == Path(other["path"])
    # and back, with the file still sound
    assert c.post("library/open", {"path": str(a)})["opened"]
    assert c.get("meta")["title"] == "First Family"


def test_starting_a_family_from_the_app_opens_it(running):
    c, a = running
    r = c.post("library/new", {"title": "Third Family"})
    assert r["opened"] and "Documents" in r["message"]
    assert c.get("meta")["title"] == "Third Family"
    assert c.get("meta")["stats"]["people"] == 0


def test_renaming_from_the_app_moves_the_file_too(running):
    """Otherwise the folder fills up with family2.helix and there is no way
    to tell which is which without opening all of them."""
    c, a = running
    r = c.post("library/rename", {"title": "Whitcombe of Bath"})
    assert r["renamed"]
    assert Path(r["path"]).name == "Whitcombe of Bath.helix"
    assert c.get("meta")["title"] == "Whitcombe of Bath"
    assert c.get("meta")["stats"]["people"] == 0     # the file still opens


def test_opening_a_family_that_has_moved_says_what_to_do(running):
    c, a = running
    out = c.post_expecting_failure("library/open", {"path": "/nowhere/x.helix"})
    assert "no family file" in out["error"]
    assert str(library.library_dir()) in out["error"]


def test_the_data_and_the_photographs_stay_together(running):
    """A file people can find, with its pictures beside it. The whole
    promise in docs/KEEPING_YOUR_WORK.md is that the work outlives the
    program, and that needs plain files in a folder somebody can copy."""
    import base64
    c, a = running
    pid = add(c, "Portrait", "Person")
    pixel = base64.b64encode(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQ"
        "GAhKmMIQAAAABJRU5ErkJggg==")).decode()
    c.post("person/photo", {"id": pid, "filename": "p.png",
                            "data": "data:image/png;base64," + pixel})
    media = a.with_name(a.stem + "-media")
    assert media.is_dir() and any(media.iterdir())
    assert library.status(a)["photos"] == 1
