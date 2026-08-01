#!/usr/bin/env python3
"""The entry point PyInstaller freezes. Two lines, and both of them matter.

WHY THIS FILE EXISTS AT ALL. `build_app.py` used to hand PyInstaller
`helix/desktop/app.py` directly, which looks like the obvious thing to do and
does not work: PyInstaller runs whatever it is given as `__main__`, with no
package around it, and the first line of `app.py` that says `from . import
library` raises

    ImportError: attempted relative import with no known parent package

before the window has any chance to open. The built application died on
launch, every time, on every platform. NOBODY FOUND OUT because the build was
never run -- `python3 build_app.py` returned 2 for a missing PyInstaller and
that was as far as anyone got, so a script that could not produce a working
application sat in the repository looking finished.

Importing the module by its real name instead gives it its package, and the
relative imports resolve exactly as they do from `python3 -m helix.desktop.app`.

`packaging/` and not `helix/`, because this belongs to the build rather than
to the program: run from source there is nothing here to run.
"""
import sys

from helix.desktop.app import main

if __name__ == "__main__":
    sys.exit(main())
