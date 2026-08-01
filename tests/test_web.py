"""The front end: does it parse, and does it say what it should.

WHY A TEST FOR THIS AT ALL. Python is compiled the moment it is imported, so
a typo in a `.py` file fails a test somewhere. The browser modules are not:
nothing in the test suite ever reads them, and a syntax error in one of them
sails through a completely green run and then takes the WHOLE interface down
in the browser — every module, because one that fails to parse stops the
import graph and there is no chart, no sidebar and no dialogue.

That is not hypothetical. A regular expression written across two lines with
Python's `/x` flag on the end -- which JavaScript does not have -- threw
"Invalid regular expression: missing /" at parse time, and the window came up
as an empty grey rectangle with a working header.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

JS = sorted((Path(__file__).parent.parent / "helix" / "web" / "js").glob("*.js"))
NODE = shutil.which("node")


def test_there_are_modules_to_check():
    assert JS, "no front-end modules found at all"


@pytest.mark.skipif(not NODE, reason="node is not installed")
@pytest.mark.parametrize("path", JS, ids=lambda p: p.name)
def test_every_module_parses(path):
    r = subprocess.run([NODE, "--input-type=module", "--check"],
                       stdin=path.open("rb"), capture_output=True, text=True)
    assert r.returncode == 0, f"{path.name} does not parse:\n{r.stderr}"


def test_every_module_the_page_asks_for_exists():
    """A renamed module is a blank window, and only in the browser."""
    web = Path(__file__).parent.parent / "helix" / "web"
    html = (web / "index.html").read_text()
    import re
    for src in re.findall(r'src="([^"]+\.js)"', html):
        assert (web / src).exists(), f"index.html loads {src}, which is missing"


def test_nothing_on_the_page_says_union():
    """Rule: the word is right for the schema and wrong for somebody adding
    their aunt, so it stays on the far side of the API. Checked against the
    VISIBLE text of the page -- comments and field names are the schema's
    side of the line and are left alone."""
    import re
    web = Path(__file__).parent.parent / "helix" / "web"
    html = (web / "index.html").read_text()
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)     # comments
    html = re.sub(r"<[^>]+>", " ", html)                    # tags
    assert "union" not in html.lower(), \
        "the word 'union' is on the page where somebody can read it"
