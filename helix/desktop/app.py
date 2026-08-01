"""Helix as an application you double-click.

WHAT THIS IS. A native desktop window with Helix inside it: no address bar,
no tabs, no browser. It starts the local server on a private port, opens one
window on it, and shuts the server down when the window closes. The person
using it never sees a URL and never has to have a browser open.

WHY IT IS A WEBVIEW AND NOT A REWRITE. The interface is 2,500 lines of HTML,
CSS and plain JavaScript, and the chart it draws is SVG — a vector format the
system's own web engine renders correctly, at any zoom, with real text
selection and a working print dialogue. Rebuilding that in Tk or Qt would
cost months and lose the chart. Every operating system this program targets
already ships a web engine:

    Windows   WebView2 (Chromium, shipped with Windows 10/11)
    macOS     WKWebView (Safari's engine, part of the OS)
    Linux     WebKitGTK

`pywebview` is a thin wrapper over exactly those three and nothing else --
no Chromium download, no Node, no npm.

THREE WAYS TO RUN, BEST FIRST, and it falls through them by itself:

  1. pywebview          a real application window. `pip install helix-tree[desktop]`
  2. app-mode browser   Chrome/Edge/Brave `--app=`, which gives a chromeless
                        window with no tabs and its own dock icon. Not as
                        good, but indistinguishable at a glance and needs
                        nothing installed.
  3. an ordinary tab    always works.

THE CORE STAYS DEPENDENCY-FREE. `helix serve` and every command still run on
a machine with nothing installed; the desktop shell is an optional extra and
degrades to (2) or (3) rather than failing.
"""
from __future__ import annotations

import contextlib
import os
import platform
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from . import library

TITLE = "Helix"
MIN_W, MIN_H = 1100, 720


def free_port() -> int:
    """A port the operating system has just told us is free.

    Binding to 0 and reading the number back is the only way to ask without
    racing: a fixed port fails the second time somebody opens two families,
    and a random guess fails whenever something else has it.
    """
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for(url: str, timeout: float = 20.0) -> bool:
    """Do not open a window on a server that is not answering yet."""
    import urllib.error
    import urllib.request
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=0.6) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.12)
    return False


# ------------------------------------------------------------- the server


class Backend:
    """The local server, on a private port, in a thread of its own."""

    def __init__(self, dbpath: str | Path):
        from ..server import make_server
        self.dbpath = str(dbpath)
        self.port = free_port()
        self.srv = make_server(self.dbpath, host="127.0.0.1", port=self.port)
        self.thread = threading.Thread(target=self.srv.serve_forever,
                                       daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def start(self) -> "Backend":
        self.thread.start()
        if not wait_for(self.url + "api/meta"):
            raise RuntimeError(
                "Helix could not start its own window.\n"
                "Nothing is wrong with your family file. Try opening it from "
                "a terminal with:  helix serve <file>")
        return self

    def stop(self) -> None:
        with contextlib.suppress(Exception):
            self.srv.shutdown()
        with contextlib.suppress(Exception):
            self.srv.server_close()


# ------------------------------------------------------------ the windows


def _pywebview(url: str, title: str) -> bool:
    """A real application window. Returns False if pywebview is not here."""
    try:
        import webview                                      # type: ignore
    except ImportError:
        return False

    win = webview.create_window(
        title, url, width=1440, height=920,
        min_size=(MIN_W, MIN_H), text_select=True,
        confirm_close=False,
    )
    # `private_mode=False` keeps a persistent profile beside the settings
    # file, so the window remembers its size and the print dialogue does not
    # ask about the same printer twice.
    profile = library.config_dir() / "window"
    profile.mkdir(parents=True, exist_ok=True)
    try:
        webview.start(private_mode=False, storage_path=str(profile),
                      gui=_gui_hint())
    except TypeError:                       # an older pywebview
        webview.start()
    del win
    return True


def _gui_hint() -> Optional[str]:
    """Let pywebview choose, except on Linux where it needs telling.

    On macOS and Windows there is exactly one right answer and pywebview
    knows it. On Linux it will try Qt first and fall over if PyQt is
    half-installed, which is common; GTK is the one that is usually there.
    """
    if platform.system() == "Linux":
        return "gtk"
    return None


# Chromium-family browsers all support `--app=`, which opens a window with no
# tabs, no address bar and its own icon in the dock. It is not a native
# window and it is close enough that most people cannot tell.
_APP_BROWSERS = {
    "Darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ],
    "Windows": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    ],
    "Linux": ["google-chrome", "chromium", "chromium-browser",
              "microsoft-edge", "brave-browser"],
}


def _app_window(url: str) -> Optional[subprocess.Popen]:
    for cand in _APP_BROWSERS.get(platform.system(), []):
        exe = cand if Path(cand).exists() else shutil.which(cand)
        if not exe:
            continue
        profile = library.config_dir() / "window"
        profile.mkdir(parents=True, exist_ok=True)
        try:
            return subprocess.Popen(
                [exe, f"--app={url}", f"--user-data-dir={profile}",
                 "--no-first-run", "--no-default-browser-check",
                 f"--window-size={1440},{920}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            continue
    return None


# ------------------------------------------------------------------ launch


def launch(dbpath: Optional[str | Path] = None, *,
           prefer: str = "auto", quiet: bool = False) -> int:
    """Open Helix as an application. Blocks until the window is closed.

    With no path it opens whatever `library.first_run` decides -- the file
    you had open, or the only one in your folder, or the library screen.
    """
    if dbpath is None:
        first = library.first_run()
        dbpath = first["open"]
        if dbpath is None:
            # NOTHING TO OPEN IS NOT AN ERROR. Somebody's first launch ends
            # here, and the answer is a family file with nobody in it and a
            # window that says so -- not a dialog box before they have seen
            # the program.
            dbpath = library.create("My family")
            if not quiet:
                print(f"  Started a new family file at {dbpath}")
    dbpath = Path(dbpath)
    if not dbpath.exists():
        raise SystemExit(
            f"\n  There is no family file at {dbpath}.\n"
            f"  Your files live in {library.library_dir()} — open Helix with "
            f"no arguments to choose one.\n")

    library.remember(dbpath)
    back = Backend(dbpath).start()
    title = f"{library._title_of(dbpath)} — {TITLE}"
    if not quiet:
        print(f"  {TITLE} is open. Close the window to quit.")

    try:
        if prefer in ("auto", "native") and _pywebview(back.url, title):
            return 0
        if prefer in ("auto", "native", "app"):
            proc = _app_window(back.url)
            if proc is not None:
                if not quiet and prefer != "app":
                    print("  (Using an application window. For a fully "
                          "native one:  pip install pywebview)")
                proc.wait()
                return 0
        import webbrowser
        webbrowser.open(back.url)
        if not quiet:
            print(f"  Opened in your browser: {back.url}\n"
                  f"  Press Ctrl-C here to quit.")
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        return 0
    finally:
        back.stop()


def main(argv: Optional[list[str]] = None) -> int:
    """The entry point a double-click reaches."""
    import argparse
    ap = argparse.ArgumentParser(
        prog="helix-app",
        description="Open Helix as a desktop application.")
    ap.add_argument("db", nargs="?", help="a .helix family file")
    ap.add_argument("--library", help="use this folder for family files")
    ap.add_argument("--window", default="auto",
                    choices=["auto", "native", "app", "browser"],
                    help="which kind of window to open")
    a = ap.parse_args(argv if argv is not None else _argv_from_os())
    if a.library:
        library.set_library_dir(a.library)
    return launch(a.db, prefer=a.window)


def _argv_from_os() -> list[str]:
    """Arguments, with the ones macOS invents removed.

    Double-clicking a `.helix` file in Finder launches the bundle with
    `-psn_0_12345` -- a process serial number, not a path -- and argparse
    would refuse to start over it.
    """
    return [x for x in sys.argv[1:] if not x.startswith("-psn_")]


if __name__ == "__main__":
    sys.exit(main())
