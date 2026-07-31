"""Helix as a desktop application.

  app.py       the window, and starting the server behind it
  library.py   where family files live on the host computer

`helix-app` is the entry point; `python3 -m helix.desktop` is the same
thing. Neither is needed to use the program from a terminal -- the core
still installs nothing and `helix serve` works as it always did.
"""
from .app import launch, main            # noqa: F401
from .library import (create, families, library_dir, reveal,   # noqa: F401
                      set_library_dir, status)
