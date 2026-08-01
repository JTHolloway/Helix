-- Helix database schema v1
-- One SQLite file holds an entire family archive. This is the only
-- irreplaceable artefact the program produces; everything else is derived.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS person (
  id             TEXT PRIMARY KEY,
  sex            TEXT NOT NULL DEFAULT 'U' CHECK (sex IN ('M','F','X','U')),
  living         INTEGER,
  privacy        TEXT NOT NULL DEFAULT 'inherit'
                 CHECK (privacy IN ('public','private','inherit')),
  is_placeholder INTEGER NOT NULL DEFAULT 0,
  confidence     INTEGER NOT NULL DEFAULT 2 CHECK (confidence BETWEEN 0 AND 3),
  notes          TEXT,
  created_at     TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS person_name (
  id             TEXT PRIMARY KEY,
  person_id      TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  type           TEXT NOT NULL DEFAULT 'birth'
                 CHECK (type IN ('birth','married','also_known_as','legal',
                                 'religious','nickname','anglicised','as_recorded')),
  is_primary     INTEGER NOT NULL DEFAULT 0,
  title          TEXT,
  given          TEXT,
  given_used     TEXT,
  surname_prefix TEXT,
  surname        TEXT,
  suffix         TEXT,
  as_recorded    TEXT,
  valid_from     TEXT,
  valid_to       TEXT,
  soundex        TEXT,
  dmetaphone     TEXT,
  sort_key       TEXT
);
CREATE INDEX IF NOT EXISTS ix_name_person  ON person_name(person_id);
CREATE INDEX IF NOT EXISTS ix_name_surname ON person_name(surname);
CREATE INDEX IF NOT EXISTS ix_name_sort    ON person_name(sort_key);
CREATE INDEX IF NOT EXISTS ix_name_sdx     ON person_name(soundex);

CREATE TABLE IF NOT EXISTS union_ (
  id         TEXT PRIMARY KEY,
  type       TEXT NOT NULL DEFAULT 'marriage'
             CHECK (type IN ('marriage','civil_partnership','unmarried','unknown','annulled')),
  confidence INTEGER NOT NULL DEFAULT 2,
  notes      TEXT
);

CREATE TABLE IF NOT EXISTS union_partner (
  union_id  TEXT NOT NULL REFERENCES union_(id) ON DELETE CASCADE,
  person_id TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  role      TEXT NOT NULL DEFAULT 'partner',
  seq       INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (union_id, person_id)
);
CREATE INDEX IF NOT EXISTS ix_up_person ON union_partner(person_id);

CREATE TABLE IF NOT EXISTS union_child (
  union_id     TEXT NOT NULL REFERENCES union_(id) ON DELETE CASCADE,
  person_id    TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  rel_partner1 TEXT NOT NULL DEFAULT 'biological',
  rel_partner2 TEXT NOT NULL DEFAULT 'biological',
  is_primary   INTEGER NOT NULL DEFAULT 1,
  birth_order  INTEGER,
  confidence   INTEGER NOT NULL DEFAULT 2,
  PRIMARY KEY (union_id, person_id)
);
CREATE INDEX IF NOT EXISTS ix_uc_person ON union_child(person_id);

CREATE TABLE IF NOT EXISTS place (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  type        TEXT,
  parent_id   TEXT REFERENCES place(id),
  lat         REAL,
  lon         REAL,
  as_recorded TEXT,
  valid_from  TEXT,
  valid_to    TEXT,
  notes       TEXT
);
CREATE INDEX IF NOT EXISTS ix_place_parent ON place(parent_id);

CREATE TABLE IF NOT EXISTS event (
  id            TEXT PRIMARY KEY,
  type          TEXT NOT NULL,
  date_json     TEXT,
  date_earliest TEXT,
  date_latest   TEXT,
  date_sort     REAL,
  place_id      TEXT REFERENCES place(id),
  description   TEXT,
  age_text      TEXT,
  confidence    INTEGER NOT NULL DEFAULT 2,
  notes         TEXT
);
CREATE INDEX IF NOT EXISTS ix_event_sort ON event(date_sort);
CREATE INDEX IF NOT EXISTS ix_event_type ON event(type);

CREATE TABLE IF NOT EXISTS event_role (
  event_id  TEXT NOT NULL REFERENCES event(id) ON DELETE CASCADE,
  person_id TEXT REFERENCES person(id) ON DELETE CASCADE,
  union_id  TEXT REFERENCES union_(id) ON DELETE CASCADE,
  role      TEXT NOT NULL DEFAULT 'principal',
  PRIMARY KEY (event_id, person_id, union_id, role)
);
CREATE INDEX IF NOT EXISTS ix_role_person ON event_role(person_id);
CREATE INDEX IF NOT EXISTS ix_role_event  ON event_role(event_id);

CREATE TABLE IF NOT EXISTS source (
  id TEXT PRIMARY KEY, title TEXT NOT NULL, author TEXT, publisher TEXT,
  repository TEXT, ref TEXT, url TEXT, type TEXT,
  quality INTEGER NOT NULL DEFAULT 2, notes TEXT, accessed TEXT
);

CREATE TABLE IF NOT EXISTS citation (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES source(id) ON DELETE CASCADE,
  person_id TEXT REFERENCES person(id) ON DELETE CASCADE,
  event_id  TEXT REFERENCES event(id) ON DELETE CASCADE,
  union_id  TEXT REFERENCES union_(id) ON DELETE CASCADE,
  name_id   TEXT REFERENCES person_name(id) ON DELETE CASCADE,
  page TEXT, transcript TEXT, image_path TEXT,
  confidence INTEGER NOT NULL DEFAULT 2, reasoning TEXT
);
CREATE INDEX IF NOT EXISTS ix_cite_person ON citation(person_id);
CREATE INDEX IF NOT EXISTS ix_cite_event  ON citation(event_id);

CREATE TABLE IF NOT EXISTS media (
  id TEXT PRIMARY KEY, path TEXT NOT NULL, type TEXT,
  caption TEXT, taken TEXT, sha256 TEXT,
  -- Which part of the picture is the face, as "x,y,w,h" in fractions of the
  -- image. A rectangle and not new pixels: the one photograph of somebody's
  -- grandmother is usually a group at a wedding, and cropping to her face by
  -- re-encoding destroys the only copy of everybody else at it.
  crop TEXT
);
CREATE TABLE IF NOT EXISTS media_link (
  media_id TEXT NOT NULL REFERENCES media(id) ON DELETE CASCADE,
  person_id TEXT REFERENCES person(id) ON DELETE CASCADE,
  event_id  TEXT REFERENCES event(id) ON DELETE CASCADE,
  is_portrait INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (media_id, person_id, event_id)
);

CREATE TABLE IF NOT EXISTS tag (
  id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, colour TEXT
);
CREATE TABLE IF NOT EXISTS person_tag (
  person_id TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  tag_id    TEXT NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
  PRIMARY KEY (person_id, tag_id)
);

CREATE TABLE IF NOT EXISTS research_task (
  id TEXT PRIMARY KEY,
  person_id TEXT REFERENCES person(id) ON DELETE CASCADE,
  question TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open'
         CHECK (status IN ('open','in_progress','done','dead_end')),
  priority INTEGER NOT NULL DEFAULT 2,
  repository TEXT, result TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dna_match (
  id TEXT PRIMARY KEY, person_id TEXT REFERENCES person(id),
  match_name TEXT, platform TEXT, shared_cm REAL, largest_cm REAL,
  segments INTEGER, predicted_rel TEXT, documented_rel TEXT, notes TEXT
);

CREATE TABLE IF NOT EXISTS change_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL DEFAULT (datetime('now')),
  op TEXT NOT NULL, tbl TEXT NOT NULL, row_id TEXT NOT NULL,
  before TEXT, after TEXT
);

CREATE TABLE IF NOT EXISTS settings (k TEXT PRIMARY KEY, v TEXT);

-- Convenience view: one row per person with their primary name + vital dates.
CREATE VIEW IF NOT EXISTS v_person AS
SELECT
  p.id, p.sex, p.living, p.confidence, p.is_placeholder,
  n.given, n.given_used, n.surname_prefix, n.surname, n.suffix, n.sort_key,
  (SELECT e.date_sort FROM event e JOIN event_role r ON r.event_id = e.id
    WHERE r.person_id = p.id AND e.type = 'birth' LIMIT 1)  AS birth_sort,
  (SELECT e.date_json FROM event e JOIN event_role r ON r.event_id = e.id
    WHERE r.person_id = p.id AND e.type = 'birth' LIMIT 1)  AS birth_json,
  (SELECT e.date_sort FROM event e JOIN event_role r ON r.event_id = e.id
    WHERE r.person_id = p.id AND e.type = 'death' LIMIT 1)  AS death_sort,
  (SELECT e.date_json FROM event e JOIN event_role r ON r.event_id = e.id
    WHERE r.person_id = p.id AND e.type = 'death' LIMIT 1)  AS death_json
FROM person p
LEFT JOIN person_name n ON n.person_id = p.id AND n.is_primary = 1;
