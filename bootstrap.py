#!/usr/bin/env python3
"""Run this first. It needs no arguments and installs nothing.

    python3 bootstrap.py

It will:
  1. check your Python version
  2. create a sample family file if you have not got one
  3. render every working design to SVG and PDF
  4. run the test suite if pytest happens to be available
  5. tell you the one command that opens the app

Everything happens inside this folder. Nothing is downloaded, nothing is
installed, and nothing leaves your computer. Safe to run repeatedly.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

SAMPLE = ROOT / "sample-family.helix"
SAMPLES_DIR = ROOT / "samples"
PEOPLE = 400
MIN_PY = (3, 11)


def say(msg="", indent=0):
    print(" " * indent + msg, flush=True)


def rule(title=""):
    say()
    say(f"── {title} " + "─" * max(0, 66 - len(title)))


def main() -> int:
    t0 = time.time()
    say()
    say("  HELIX")
    say("  Family trees as circular mazes, transit maps and laser atlases")
    say()

    # ---------------------------------------------------------------- 1 ---
    rule("Checking Python")
    if sys.version_info < MIN_PY:
        say(f"  Helix needs Python {MIN_PY[0]}.{MIN_PY[1]} or newer.", 0)
        say(f"  You are running {sys.version.split()[0]}.")
        say("  Install a newer Python and run this again.")
        return 1
    say(f"  Python {sys.version.split()[0]}  ✓", 0)

    try:
        from helix.layout import registry
        from helix.layout.engines import experimental, family, linear, radial  # noqa: F401
    except Exception as e:
        say(f"  Could not load Helix: {e}")
        say("  Make sure you are running this from inside the helix folder.")
        return 1
    designs = registry.all_designs()
    say(f"  {len(designs)} designs registered  ✓")

    # ---------------------------------------------------------------- 2 ---
    rule("Sample family")
    if SAMPLE.exists():
        say(f"  {SAMPLE.name} already exists — leaving it alone.")
    else:
        say(f"  Creating {SAMPLE.name} with about {PEOPLE} people…")
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "make_sample.py"),
                            str(SAMPLE), "--people", str(PEOPLE)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            say("  Could not build the sample:")
            say("  " + (r.stderr.strip().splitlines() or ["unknown error"])[-1])
            return 1
        say("  " + r.stdout.strip())

    from helix.graph import build as gbuild
    from helix.store.db import connect
    graph = gbuild.load(connect(SAMPLE, create=False))
    st = graph.stats()
    say(f"  {st['people']} people, {st['unions']} marriages, "
        f"{st['earliest_year']}–{st['latest_year']}  ✓")

    # ---------------------------------------------------------------- 3 ---
    rule("Checking the data")
    from helix.graph.validate import validate
    issues = validate(graph)
    errs = [i for i in issues if i.severity == "error"]
    warns = [i for i in issues if i.severity == "warning"]
    say(f"  {len(errs)} errors, {len(warns)} warnings  "
        + ("✓" if not errs else "✗"))
    for i in errs[:3]:
        say(f"    {i.message}")

    # ---------------------------------------------------------------- 4 ---
    rule("Rendering every design (SVG + PDF)")
    if SAMPLES_DIR.exists():
        shutil.rmtree(SAMPLES_DIR)
    from helix.cli import main as cli_main
    say("  Using --focus thread_siblings: the subject's direct line plus")
    say("  their brothers and sisters. A whole 460-person family on one disc")
    say("  is unreadable, and this is the setting that fixes that.")
    say()
    try:
        cli_main(["samples", str(SAMPLE), "-o", str(SAMPLES_DIR),
                  "--title", "Sample Family", "--max-generations", "5",
                  "--focus", "thread_siblings"])
    except SystemExit:
        pass
    except Exception as e:
        say(f"  Rendering stopped: {e}")
        return 1

    n_pdf = len(list((SAMPLES_DIR / "pdf").glob("*.pdf"))) if SAMPLES_DIR.exists() else 0
    n_svg = len(list((SAMPLES_DIR / "svg").glob("*.svg"))) if SAMPLES_DIR.exists() else 0

    # ---------------------------------------------------------------- 5 ---
    rule("Tests")
    try:
        import pytest  # noqa: F401
        r = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q"],
                           cwd=ROOT, capture_output=True, text=True)
        line = [l for l in r.stdout.strip().splitlines() if l.strip()][-1:]
        say("  " + (line[0] if line else "no output")
            + ("  ✓" if r.returncode == 0 else "  ✗"))
    except ImportError:
        say("  pytest is not installed, so the tests were skipped.")
        say("  That is fine — everything above already ran for real.")
        say("  To run them:  pip install pytest hypothesis && python3 -m pytest")

    # ---------------------------------------------------------------- 6 ---
    rule("Ready")
    say()
    say(f"  {n_svg} SVG and {n_pdf} PDF samples written to  samples/")
    say(f"  Open  samples/index.html  to compare every design side by side.")
    say()
    say("  To use the app:")
    say()
    say(f"      python3 -m helix.cli serve {SAMPLE.name}")
    say()
    say("  If a chart ever looks too crowded, that is density, not a bug:")
    say("      --focus thread          your direct line only  (~20 people)")
    say("      --focus thread_siblings plus their siblings    (~45 people)")
    say("      --focus all             everyone                (400+, needs a big sheet)")
    say()
    say("  To start your own family instead of the sample:")
    say()
    say("      python3 -m helix.cli init my-family.helix --title \"My Family\"")
    say("      python3 -m helix.cli serve my-family.helix")
    say()
    say(f"  Finished in {time.time() - t0:.1f}s.")
    say()
    return 0


if __name__ == "__main__":
    sys.exit(main())
