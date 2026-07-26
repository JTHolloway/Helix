import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def sample_db(tmp_path_factory):
    """A real 400-person family, generated once for the whole run."""
    db = tmp_path_factory.mktemp("helix") / "sample.helix"
    subprocess.run([sys.executable, str(ROOT / "tools" / "make_sample.py"),
                    str(db), "--people", "300", "--seed", "42"], check=True)
    return db


@pytest.fixture(scope="session")
def graph(sample_db):
    from helix.graph import build
    from helix.store.db import connect
    return build.load(connect(sample_db))
