#!/usr/bin/env python3
"""Build Helix into an application somebody can double-click.

    python3 build_app.py            # for the machine you are on
    python3 build_app.py --check    # say what would happen, build nothing

WHAT COMES OUT

    macOS     dist/Helix.app          drag into Applications
    Windows   dist/Helix/Helix.exe    a folder to copy, or run the installer
    Linux     dist/Helix/Helix        a folder to copy

CROSS-COMPILING IS NOT POSSIBLE and no amount of configuration changes that.
PyInstaller freezes the interpreter and the libraries of the machine it runs
on; a Windows .exe has to be built on Windows and a .app on a Mac. That is
why this is one script that knows all three rather than three scripts, and
why `.github/workflows/desktop.yml` builds on all three at once — push a tag
and the release has every platform in it without anybody owning three
computers.

WHAT GOES IN. The whole `helix` package including `web/`, `store/schema.sql`,
`style/presets/` and `fab/hershey/` — the interface and the schema are data
files, and PyInstaller does not find data by itself. Everything else is the
standard library.
"""
from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
NAME = "Helix"
BUNDLE_ID = "com.helix.tree"


def version() -> str:
    import re
    m = re.search(r'version\s*=\s*"([^"]+)"',
                  (ROOT / "pyproject.toml").read_text())
    return m.group(1) if m else "0.0.0"


# The data files. `--add-data` wants `src<sep>dest`, and the separator is a
# colon everywhere except Windows, where a colon is already the drive letter.
SEP = ";" if platform.system() == "Windows" else ":"
DATA = [
    ("helix/web", "helix/web"),
    ("helix/store/schema.sql", "helix/store"),
    ("helix/style/presets", "helix/style/presets"),
    ("helix/fab/hershey", "helix/fab/hershey"),
]


def icon_arg() -> list[str]:
    """An icon if one has been drawn, and no complaint if not.

    A missing icon must not stop a build: the program works perfectly with
    the default one, and refusing to package over a picture would be the
    silliest way to fail.
    """
    for name in ("Helix.icns", "Helix.ico", "Helix.png"):
        p = ROOT / "packaging" / name
        if p.exists():
            want = {".icns": "Darwin", ".ico": "Windows"}.get(p.suffix)
            if want in (None, platform.system()):
                return ["--icon", str(p)]
    return []


def command() -> list[str]:
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", NAME,
        "--noconfirm", "--clean",
        # NOT --onefile. A single executable unpacks itself into a temporary
        # folder on every launch, which on Windows takes several seconds and
        # trips antivirus; worse, the family files people then create beside
        # "the program" land in a folder that is deleted when it quits.
        "--windowed",
        "--osx-bundle-identifier", BUNDLE_ID,
        # NOT `helix/desktop/app.py`. PyInstaller runs whatever it freezes as
        # `__main__` with no package around it, and app.py's `from . import
        # library` then raises ImportError before the window opens -- the
        # built application died on launch and the build had never been run
        # to find out. `packaging/launch.py` imports it by name instead.
        str(ROOT / "packaging" / "launch.py"),
    ]
    for src, dest in DATA:
        if (ROOT / src).exists():
            cmd += ["--add-data", f"{ROOT / src}{SEP}{dest}"]
    # PyInstaller finds imports by reading the source, and every layout
    # engine is registered by a decorator at import time from a module
    # nothing names directly.
    for mod in ("helix.layout.engines.family", "helix.layout.engines.radial",
                "helix.layout.engines.linear",
                "helix.layout.engines.network",
                "helix.io.gedcom.writer", "helix.io.gedcom.parser",
                "helix.io.gedcom.lexer", "helix.io.csv_import",
                "helix.analysis.gaps", "helix.analysis.stats",
                "helix.analysis.duplicates"):
        cmd += ["--hidden-import", mod]
    cmd += icon_arg()
    return cmd


PLIST_EXTRA = """
    <key>CFBundleDocumentTypes</key>
    <array><dict>
      <key>CFBundleTypeName</key><string>Helix family file</string>
      <key>CFBundleTypeRole</key><string>Editor</string>
      <key>LSHandlerRank</key><string>Owner</string>
      <key>CFBundleTypeExtensions</key><array><string>helix</string></array>
    </dict></array>
    <key>NSHumanReadableCopyright</key><string>Helix</string>
    <key>LSApplicationCategoryType</key>
      <string>public.app-category.productivity</string>
"""


def teach_macos_about_helix_files(app: Path) -> None:
    """Make `.helix` files open in Helix when you double-click them.

    Info.plist is XML that PyInstaller has already written, so this splices
    the document-type declaration in rather than templating the whole file.
    """
    plist = app / "Contents" / "Info.plist"
    if not plist.exists():
        return
    text = plist.read_text()
    if "CFBundleDocumentTypes" in text:
        return
    plist.write_text(text.replace("</dict>\n</plist>",
                                  PLIST_EXTRA + "</dict>\n</plist>", 1))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="report and build nothing")
    a = ap.parse_args()

    system = platform.system()
    print(f"  Helix {version()} for {system} {platform.machine()}")
    print(f"  Python {platform.python_version()}")

    have_pyinstaller = True
    try:
        import PyInstaller                              # noqa: F401
    except ImportError:
        have_pyinstaller = False
    try:
        import webview                                  # noqa: F401
        have_webview = True
    except ImportError:
        have_webview = False

    print(f"  PyInstaller {'yes' if have_pyinstaller else 'NO'}"
          f"   pywebview {'yes' if have_webview else 'NO'}")
    if not have_webview:
        print("\n  WITHOUT PYWEBVIEW the packaged application still runs, but\n"
              "  it opens an app-mode browser window instead of a native one.\n"
              "  For a real window:  pip install pywebview")
    if not have_pyinstaller:
        print("\n  Install the build tools first:\n"
              "      pip install 'helix-tree[desktop]'\n"
              "  or  pip install pyinstaller pywebview\n")
        return 2

    cmd = command()
    if a.check:
        print("\n  Would run:\n    " + " \\\n      ".join(cmd) + "\n")
        return 0

    print("\n  Building. This takes a couple of minutes.\n")
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode:
        return r.returncode

    out = ROOT / "dist"
    if system == "Darwin":
        app = out / f"{NAME}.app"
        teach_macos_about_helix_files(app)
        target = app
        how = (f"  Drag {NAME}.app into your Applications folder.\n"
               f"  The first time, right-click it and choose Open — macOS\n"
               f"  asks about any application it has not seen signed before.")
    elif system == "Windows":
        target = out / NAME
        how = (f"  Copy the {NAME} folder anywhere and run {NAME}.exe.\n"
               f"  To make an installer:  iscc packaging\\helix.iss")
    else:
        target = out / NAME
        how = f"  Copy the {NAME} folder anywhere and run ./{NAME}"

    size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
    print(f"\n  {target}   ({size / 1e6:.0f} MB)\n")
    print(how)
    print(f"\n  Family files will be kept in Documents/{NAME}, and the\n"
          f"  application shows you that folder on its Family screen.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
