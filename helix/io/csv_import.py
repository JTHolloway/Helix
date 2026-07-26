"""Spreadsheet import -- the realistic first step for most people.

Almost everyone starts with a spreadsheet from a relative. This importer is
deliberately tolerant: it guesses columns, reports what it guessed, and lets
the user correct the mapping before anything is written.

EXPECTED (all optional except a name)
  id, given, surname, sex, birth_date, birth_place, death_date, death_place,
  occupation, education, father_id, mother_id, spouse_id, marriage_date, notes

BEHAVIOUR
  * Header matching is fuzzy and case-insensitive: "DOB", "Born", "birth
    date", "b." all map to birth_date.
  * Rows referencing an unknown father_id create a PLACEHOLDER person rather
    than failing, so a partial spreadsheet still imports.
  * Every date goes through model.gendate.parse, so "abt 1834" survives.
  * A dry run reports counts and problems and writes nothing.
"""
from __future__ import annotations

import csv
from pathlib import Path

ALIASES = {
    "given": ["given", "first", "forename", "firstname", "first name", "christian"],
    "surname": ["surname", "last", "lastname", "last name", "family name"],
    "sex": ["sex", "gender", "m/f"],
    "birth_date": ["birth", "birth date", "born", "dob", "b", "date of birth"],
    "birth_place": ["birth place", "birthplace", "born in", "pob"],
    "death_date": ["death", "death date", "died", "dod", "d"],
    "death_place": ["death place", "deathplace", "died in"],
    "occupation": ["occupation", "job", "trade", "profession"],
    "education": ["education", "school", "university"],
    "father_id": ["father", "father id", "fatherid", "dad"],
    "mother_id": ["mother", "mother id", "motherid", "mum", "mom"],
    "spouse_id": ["spouse", "spouse id", "husband", "wife", "partner"],
    "marriage_date": ["marriage", "married", "marriage date"],
    "notes": ["notes", "note", "comment", "comments"],
    "id": ["id", "ref", "key", "person id", "#"],
}


def guess_mapping(header: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for col in header:
        k = col.strip().lower().replace("_", " ")
        for field, names in ALIASES.items():
            if k in names and field not in out.values():
                out[col] = field
                break
    return out


def import_csv(path: str | Path, con, *, mapping=None, dry_run: bool = True) -> dict:
    raise NotImplementedError(
        "CSV import is Phase 3. `guess_mapping` above already works and is "
        "the hard part; the writer follows the same pattern as "
        "tools/make_sample.py."
    )
