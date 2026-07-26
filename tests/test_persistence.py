"""Your work has to survive years, a power cut and this program.

These are the tests that matter most in the long run. A chart can be
redrawn; a decade of research cannot.
"""
import json
import sqlite3
import zipfile

import pytest

from helix.store import archive as arc
from helix.store.db import SCHEMA_VERSION, backup, checkpoint, connect, get_setting


def test_every_edit_is_committed_immediately(tmp_path):
    """There is no unsaved state, so closing the window loses nothing."""
    db = tmp_path / "t.helix"
    con = connect(db)
    from helix.store.db import new_id
    pid = new_id()
    con.execute("INSERT INTO person(id,sex) VALUES(?,'M')", (pid,))
    con.commit()
    del con                                        # simulate a crash: no close
    again = connect(db)
    assert again.execute("SELECT COUNT(*) FROM person").fetchone()[0] == 1


def test_reopening_preserves_everything(sample_db):
    a = connect(sample_db)
    before = a.execute("SELECT COUNT(*) FROM person").fetchone()[0]
    checkpoint(a)
    b = connect(sample_db)
    assert b.execute("SELECT COUNT(*) FROM person").fetchone()[0] == before


def test_a_backup_is_taken_automatically(tmp_path):
    db = tmp_path / "t.helix"
    connect(db)
    connect(db)                                    # second open: file exists
    assert list((tmp_path / "backups").glob("t-*.helix"))


def test_only_one_automatic_backup_a_day(tmp_path):
    db = tmp_path / "t.helix"
    connect(db)
    for _ in range(5):
        connect(db)
    assert len(list((tmp_path / "backups").glob("t-*.helix"))) == 1


def test_manual_backup_is_a_working_database(sample_db):
    dest = backup(sample_db)
    con = sqlite3.connect(dest)
    con.row_factory = sqlite3.Row
    assert con.execute("SELECT COUNT(*) FROM person").fetchone()[0] > 0


def test_backups_are_pruned(tmp_path):
    db = tmp_path / "t.helix"
    connect(db)
    for _ in range(8):
        backup(db, keep=3)
    assert len(list((tmp_path / "backups").glob("t-*.helix"))) <= 4


def test_an_old_file_migrates_without_losing_data(tmp_path, sample_db):
    """Somebody's file is sitting at every version this program ever had."""
    import shutil
    db = tmp_path / "old.helix"
    shutil.copy2(sample_db, db)
    raw = sqlite3.connect(db)
    raw.execute("UPDATE settings SET v='1' WHERE k='schema_version'")
    raw.commit(); raw.close()
    before = sqlite3.connect(db).execute(
        "SELECT COUNT(*) FROM person").fetchone()[0]
    con = connect(db)
    assert int(get_setting(con, "schema_version")) == SCHEMA_VERSION
    assert con.execute("SELECT COUNT(*) FROM person").fetchone()[0] == before
    cols = [r[1] for r in con.execute("PRAGMA table_info(person)")]
    assert "active" in cols


def test_migration_is_idempotent(sample_db):
    for _ in range(3):
        con = connect(sample_db)
    assert int(get_setting(con, "schema_version")) == SCHEMA_VERSION


def test_verify_reports_a_sound_file(sample_db):
    assert arc.verify(connect(sample_db)) == []


def test_verify_catches_a_broken_link(tmp_path, sample_db):
    import shutil
    db = tmp_path / "b.helix"
    shutil.copy2(sample_db, db)
    raw = sqlite3.connect(db)
    raw.execute("PRAGMA foreign_keys=OFF")
    raw.execute("INSERT INTO union_child(union_id,person_id) "
                "VALUES('nope','also-nope')")
    raw.commit(); raw.close()
    assert arc.verify(connect(db))


def test_archive_holds_everything_needed_to_rebuild(sample_db, tmp_path):
    out = arc.archive(sample_db, tmp_path / "a.zip")
    names = zipfile.ZipFile(out).namelist()
    assert {"README.txt", "family.helix", "family.json",
            "people.csv"} <= set(names)


def test_the_json_dump_is_readable_without_helix(sample_db, tmp_path):
    """The long-term guarantee: plain data, no schema knowledge required."""
    out = arc.archive(sample_db, tmp_path / "a.zip")
    data = json.loads(zipfile.ZipFile(out).read("family.json"))
    assert data["format"] == "helix-archive"
    people = data["tables"]["person"]
    names = data["tables"]["person_name"]
    assert len(people) > 50 and len(names) >= len(people)
    assert {"union_", "union_partner", "union_child"} <= set(data["tables"])
    ids = {p["id"] for p in people}
    assert all(n["person_id"] in ids for n in names)


def test_the_csv_has_one_row_per_person(sample_db):
    con = connect(sample_db)
    n = con.execute("SELECT COUNT(*) FROM person").fetchone()[0]
    assert len(arc.people_csv(con).strip().splitlines()) == n + 1


def test_vague_dates_survive_the_round_trip(sample_db):
    con = connect(sample_db)
    dump = arc.to_json(con)
    kinds = set()
    for e in dump["tables"]["event"]:
        if e.get("date_json"):
            kinds.add(json.loads(e["date_json"])["kind"])
    assert kinds and kinds <= {"exact", "about", "before", "after", "between",
                               "quarter", "estimated", "calculated", "unknown"}


# ------------------------------------------------------------- restoring --
def test_an_archive_restores_to_an_identical_chart(sample_db, tmp_path):
    """The test that makes an archive a real backup rather than a hopeful
    gesture: the data goes back in, and the chart comes out the same."""
    from helix.graph import build
    from helix.layout import registry
    from helix.layout.base import LayoutSettings
    from helix.layout.engines import radial  # noqa: F401
    from helix.style.tokens import Style

    zip_path = arc.archive(sample_db, tmp_path / "a.zip")
    restored = tmp_path / "back.helix"
    result = arc.restore(zip_path, restored)
    assert result["problems"] == []

    def chart(path):
        g = build.load(connect(path))
        return registry.run("radial_rings", g,
                            LayoutSettings(engine="radial_rings",
                                           subject_id=g.subject_id,
                                           focus="bloodline",
                                           max_generations=5),
                            Style.load("panel1m")).hash()

    assert chart(restored) == chart(sample_db)


def test_restore_accepts_a_plain_backup_file(sample_db, tmp_path):
    out = tmp_path / "fromdb.helix"
    r = arc.restore(sample_db, out)
    assert r["people"] > 0 and out.exists()


def test_restore_refuses_to_clobber_without_being_told(sample_db, tmp_path):
    out = tmp_path / "x.helix"
    arc.restore(sample_db, out)
    with pytest.raises(FileExistsError):
        arc.restore(sample_db, out)
    arc.restore(sample_db, out, overwrite=True)      # explicit is fine


def test_restore_rejects_something_that_is_not_an_archive(tmp_path):
    bad = tmp_path / "notes.json"
    bad.write_text('{"hello": "world"}')
    with pytest.raises(ValueError) as e:
        arc.restore(bad, tmp_path / "o.helix")
    assert "not a Helix archive" in str(e.value)


def test_restored_file_is_editable_not_read_only(sample_db, tmp_path):
    out = tmp_path / "r.helix"
    arc.restore(arc.archive(sample_db, tmp_path / "a.zip"), out)
    con = connect(out)
    from helix.store.db import new_id
    pid = new_id()
    con.execute("INSERT INTO person(id,sex) VALUES(?,'F')", (pid,))
    con.commit()
    assert con.execute("SELECT COUNT(*) FROM person WHERE id=?",
                       (pid,)).fetchone()[0] == 1
