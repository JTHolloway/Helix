# Helix as an application

A window you double-click, on Windows or a Mac. No terminal, no browser
tab, no address bar — and your family files kept as ordinary files in a
folder you can see.

---

## Installing it

### The easy way — a built application

Releases carry a build for each platform. `.github/workflows/desktop.yml`
makes them on push of a tag.

| | What you get | What to do with it |
|---|---|---|
| **macOS** | `Helix.app` | Drag into Applications. The first time, **right-click → Open** — macOS asks about any application it has not seen signed before. |
| **Windows** | `Helix-0.5.0-Setup.exe` | Run it. Installs into your own account, so no administrator password. |
| **Windows** | `Helix\` folder | Copy anywhere and run `Helix.exe`. |
| **Linux** | `Helix/` folder | Copy anywhere and run `./Helix`. |

Double-clicking a `.helix` file opens it in Helix on both Windows and macOS.

### From source

```bash
pip install 'helix-tree[desktop]'
helix-app
```

`helix-app` is the application; `helix serve` is still there and still needs
nothing installed.

### Building it yourself

```bash
pip install pyinstaller pywebview
python3 build_app.py
```

**PyInstaller cannot cross-compile.** It freezes the interpreter of the
machine it runs on, so a Windows `.exe` has to be built on Windows and a
`.app` on a Mac. That is what the GitHub workflow is for: push a tag and all
three are built at once, without anybody owning three computers.

---

## Where your work is kept

```
Documents/Helix/
    Holloway.helix              the family. An ordinary SQLite file.
    Holloway-media/             the photographs, beside it.
    backups/                    thirty dated copies, taken automatically.
    Holloway-archive-2026*.zip  whatever Export → Archive has written.
```

**Ordinary files in an ordinary folder, and that is a decision.** Not a
hidden application-support directory, not a proprietary bundle, not a
database of databases. Somebody who has kept a family tree for ten years
wants to copy it to a memory stick, put it in Dropbox and hand it to their
daughter. A file they cannot see is a file they cannot look after, and the
whole promise of this program is that the work outlives it — see
`KEEPING_YOUR_WORK.md`.

macOS would rather this went in `Application Support` and Windows in
`AppData`. Both are places people cannot find with Finder or Explorer and
that "reset this app" wipes.

The **Family** button in the window shows you that folder in full, opens it
in Finder or Explorer, and lets you move it somewhere else.

What *is* hidden is only the preference — which folder is the library and
which file was open last:

| | |
|---|---|
| Windows | `%APPDATA%\Helix\settings.json` |
| macOS | `~/Library/Application Support/Helix/settings.json` |
| Linux | `~/.config/helix/settings.json` |

---

## What the Family screen does

* **Open** any family in the folder. Switching rebuilds the whole window —
  the chart, the sidebar, the research list and the selection all describe
  one file, and leaving them would show half of the family you just closed.
* **Rename** — changes the title inside the file *and* the name on disk, so
  a folder never fills up with `family2.helix`.
* **Make a copy** to experiment on. Through SQLite's own backup API, so the
  copy is never a half-written file.
* **Start another family.**
* **Open this folder** in Finder or Explorer. The answer to "where exactly
  is my data?", which is the first thing anybody asks of a program they are
  about to trust with ten years of work.

There is **no Save button** and there never will be. Every change is written
the moment you make it; there is no unsaved state to lose.

---

## What kind of window you get

Three, best first, and it falls through them by itself.

1. **A native application window** — `pywebview`, a thin wrapper over the web
   engine the operating system already ships: WebView2 on Windows, WKWebView
   on macOS, WebKitGTK on Linux. No Chromium download, no Node, no npm.
2. **An app-mode browser window** — Chrome, Edge or Brave with `--app=`,
   which gives a window with no tabs and no address bar and its own dock
   icon. Needs nothing installed.
3. **An ordinary browser tab** — always works.

```bash
helix-app --window native     # insist on 1
helix-app --window app        # insist on 2
helix-app --window browser    # insist on 3
```

**Why a webview and not a rewrite.** The interface is HTML, CSS and plain
JavaScript with no build step, and the chart it draws is SVG — a vector
format the system's own engine renders correctly at any zoom, with real text
selection and a working print dialogue. Rebuilding that in Tk or Qt would
cost months and lose the chart.

**The core is still dependency-free.** `helix serve` and every command work
on a machine with nothing installed. The desktop shell is
`pip install helix-tree[desktop]`, and without it the launcher degrades to
(2) or (3) rather than failing.

---

## Command line

```bash
helix-app                                   # the family you had open
helix-app "Documents/Helix/Holloway.helix"  # a particular one
helix-app --library /Volumes/Backup/Trees   # keep files somewhere else
```

Everything the terminal could do before, it still does:

```bash
helix serve my.helix          # the same program, in a browser
helix render my.helix -o chart.svg
helix export my.helix -o out.ged
helix import cousins.ged -o new.helix
helix archive my.helix
```

---

## Where the code is

```
helix/desktop/library.py   the folder, the files, first run, rename, copy
helix/desktop/app.py       the window, and the server behind it
helix/web/js/librarypanel.js  the Family screen
build_app.py               PyInstaller, for all three platforms
packaging/helix.iss        the Windows installer (Inno Setup)
.github/workflows/desktop.yml  builds all three on a tag
tests/test_desktop.py      30 tests
```

## Endpoints

| Route | What it does |
|---|---|
| `GET /api/library` | the folder, what is in it, and which is open |
| `POST /api/library/open` | switch to another family |
| `POST /api/library/new` | start one, and open it |
| `POST /api/library/rename` | title and file name together |
| `POST /api/library/duplicate` | a copy to experiment on |
| `POST /api/library/reveal` | show the folder in Finder or Explorer |
| `POST /api/library/folder` | keep family files somewhere else |
