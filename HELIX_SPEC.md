# HELIX — Radial Family Tree, Chronological Clock & Laser Atlas
## Master Build Specification v1.0

> **Working name:** `helix` (a spiral of generations). Rename freely — it appears only in the package name and window title.

---

## 0. How to use this document

**You are the build agent.** This document is the complete brief. Build it in the phase order given in §17. Do not attempt to build everything at once.

### Rules for the build agent

1. **Build phases in order.** Each phase in §17 has acceptance criteria. Do not start phase N+1 until phase N's criteria pass.
2. **Never break the Render Plan abstraction (§7.1).** All geometry is computed once, in Python, into a neutral intermediate format. The screen, the SVG file, the DXF file and the PDF are all *renderers* of that same plan. If you find yourself computing an arc angle inside the exporter, you have made an architectural mistake.
3. **Write the tests as you go**, not at the end. Golden-file snapshot tests for geometry (§16).
4. **No CDN dependencies.** The frontend must work offline. Vendor `d3.v7.min.js` into `web/vendor/`.
5. **No frontend build step.** Plain ES modules served directly. No npm, no webpack, no Vite. This is a deliberate constraint to keep the project maintainable by one person.
6. **Every module gets a docstring** stating its single responsibility and what it must *not* do.
7. **When ambiguous, prefer the genealogically correct model over the convenient one.** Real families break naive assumptions constantly (§7.4).
8. **Commit at each phase boundary** with the phase name in the message.

### Kickoff prompt to paste into a fresh session

> Read `HELIX_SPEC.md` in full. Build Phase 0 and Phase 1 only. Create the repository structure from §4, the SQLite schema from §5.2, the GenDate parser from §5.3, and the sample-data generator from §16.4. Then produce a static SVG of a radial tree from the sample data with no styling beyond black hairlines. Show me the SVG. Do not build the GUI yet. Report which acceptance criteria in §17 Phase 1 pass and which do not.

---

## 1. Goals and non-goals

### What this program is

A desktop-class tool that turns a rigorous genealogical database into a **radial descendant chart** — earliest ancestors at the centre, present day at the rim — designed to be rendered both as a print poster and as a set of **production-ready laser cutting/engraving files**, with an optional **working clock movement** through the centre.

### The five pillars

| Pillar | One-line definition |
|---|---|
| **Truth** | A genealogically correct data model with sources, uncertainty and evidence — not a spreadsheet of names. |
| **Geometry** | A layout engine that handles real families: pedigree collapse, remarriage, adoption, unknown parents, missing dates. |
| **Design control** | Every visual decision exposed as a data-driven token. Nothing hardcoded. |
| **Production** | Output that a laser actually cuts correctly on the first attempt. |
| **Insight** | The chart should tell you something you did not know, including where your research is weakest. |

### Explicit non-goals for v1

- Not a cloud service. Single-user, local files, no accounts.
- Not a genealogy *research* platform (no built-in record search — that stays manual, see §19).
- No mobile app.
- No real-time multi-user collaboration (but see §18 for a merge-based path).

### The signature feature

**The Thread** (§11) — the highlighted set of your direct ancestors, plus a *contingency analysis* that answers: "if this one person had never been born, how much of this chart disappears?" This is the emotional core of the piece and must be treated as a first-class feature, not a colour option.

---

## 2. Vocabulary

Use these terms consistently in code, comments and UI.

| Term | Meaning |
|---|---|
| **Subject** | The person the chart is centred on conceptually (usually you). Not necessarily at the centre geometrically. |
| **Apex** / **Progenitor** | An earliest-known ancestor placed at or near the centre. There may be several. |
| **Ring** | A concentric band. In generation mode, one generation. In chronological mode, a time interval. |
| **Sector** | A wedge of the disc allocated to one apex lineage. |
| **Cell** | The arc-shaped region belonging to one person or one couple. |
| **Union** | A partnership (married or not) that may produce children. GEDCOM calls this a FAM. |
| **The Thread** | The set of your direct ancestors — everyone without whom you would not exist. |
| **Render Plan** | The neutral intermediate geometry format (§7.1). |
| **Token** | A named design value in a style file (§8). |
| **Kerf** | The width of material removed by the laser beam. |
| **Web** | The strip of material remaining between two adjacent cuts. |
| **Island** | A region that would fall out of the workpiece because it is fully enclosed by cuts. |
| **Bridge** / **Tab** | A deliberate interruption in a cut line that holds an island in place. |

---

## 3. Technology stack and rationale

| Layer | Choice | Why not the alternative |
|---|---|---|
| Core language | **Python 3.11+** | Best ecosystem for CAD/vector/font manipulation. `match` statements and typing generics are used. |
| Storage | **SQLite**, single `.helix` file (a plain SQLite db) | One portable file the user can email, back up and query. Not JSON: you need indexes and integrity constraints over ~10k people. |
| DB access | **stdlib `sqlite3` + thin repository layer.** No ORM. | An ORM adds a large dependency and an abstraction that fights the recursive graph queries you need. Use recursive CTEs directly. |
| Local server | **FastAPI + uvicorn** | Serves the UI and a JSON API on `127.0.0.1`. Auto-generated OpenAPI docs are useful for debugging. |
| GUI | **Browser SPA, plain ES modules, no build step.** `d3.v7` vendored locally for zoom/selection only. | Qt would mean reimplementing SVG rendering. Here **the on-screen render is literally SVG**, so what you see is what you cut. This is the single most important stack decision. Electron/Tauri add packaging pain for no gain over a local browser tab. |
| Vector geometry | **shapely** (boolean ops, offsets, connectivity) + **pyclipper** (robust polygon offsetting for kerf) | Hand-rolled offsetting is a trap. |
| Fonts → outlines | **fontTools** | Laser software has no access to your fonts. Text must become paths. Non-negotiable (§10.2). |
| DXF | **ezdxf** | Only mature pure-Python DXF writer. |
| PDF | **reportlab** | Pure Python, pip-installable, no system libraries. Avoid `cairosvg` — cairo is a Windows install nightmare. |
| GEDCOM | **Own parser** (`helix/io/gedcom/`) | GEDCOM 5.5.1 is a trivial line format. Third-party libraries are unmaintained and lose data. Write ~400 lines and own it. |
| Tests | **pytest** + **hypothesis** (for the date parser) | |
| Packaging | `pyproject.toml`, console script `helix`. PyInstaller optional in Phase 8. | |

### Dependency list (pin in `pyproject.toml`)

```
python = ">=3.11"
fastapi
uvicorn[standard]
shapely >= 2.0
pyclipper
ezdxf >= 1.1
fonttools[ufo,lxml]
reportlab
python-dateutil
jellyfish          # soundex / metaphone for fuzzy name matching
platformdirs
typer              # CLI
rich               # CLI output
pytest, pytest-cov, hypothesis   # dev
```

Total: 11 runtime dependencies. Keep it that way. Reject any addition that saves fewer than 200 lines.

---

## 4. Repository layout

```
helix/
├── pyproject.toml
├── README.md
├── HELIX_SPEC.md                  # this document
├── helix/
│   ├── __init__.py
│   ├── cli.py                     # typer entry point
│   ├── server.py                  # FastAPI app + static mount
│   │
│   ├── model/                     # ── pure data, no I/O ──
│   │   ├── person.py
│   │   ├── union.py
│   │   ├── event.py
│   │   ├── place.py
│   │   ├── source.py
│   │   ├── gendate.py             # ★ the fuzzy date type (§5.3)
│   │   └── name.py                # ★ name normalisation rules (§5.4)
│   │
│   ├── store/                     # ── persistence ──
│   │   ├── schema.sql             # ★ full DDL (§5.2)
│   │   ├── migrations/
│   │   │   └── 0001_initial.sql
│   │   ├── db.py                  # connection, pragmas, migration runner
│   │   ├── repo_person.py
│   │   ├── repo_union.py
│   │   ├── repo_event.py
│   │   ├── repo_source.py
│   │   └── queries.py             # recursive CTEs (ancestors, descendants)
│   │
│   ├── graph/                     # ── relationship logic ──
│   │   ├── build.py               # db → in-memory graph
│   │   ├── traverse.py            # ancestors, descendants, MRCA
│   │   ├── thread.py              # ★ The Thread + contingency (§11)
│   │   ├── relationship.py        # "second cousin once removed"
│   │   ├── numbering.py           # Sosa-Stradonitz, d'Aboville, Henry
│   │   └── validate.py            # data integrity checks (§12.3)
│   │
│   ├── layout/                    # ── geometry ──
│   │   ├── plan.py                # ★ RenderPlan dataclasses (§7.1)
│   │   ├── radial.py              # ★ the main layout engine (§7.3)
│   │   ├── scales.py              # radius scales: linear, equal-area, generation
│   │   ├── sectors.py             # multi-apex sector allocation
│   │   ├── labels.py              # text fitting, flipping, curving
│   │   ├── relax.py               # angular collision relaxation
│   │   └── ornament.py            # clock face, decade rings, era bands, frame
│   │
│   ├── style/
│   │   ├── tokens.py              # token schema + resolution/inheritance
│   │   ├── presets/               # ★ shipped styles (§ Appendix A)
│   │   │   ├── labyrinth.json
│   │   │   ├── circuit.json
│   │   │   ├── heirloom.json
│   │   │   ├── nordic.json
│   │   │   ├── botanical.json
│   │   │   └── blueprint.json
│   │   └── colormaps.py           # for data-driven colouring (§12.2)
│   │
│   ├── render/                    # ── plan → output ──
│   │   ├── svg.py                 # ★ hand-rolled, exact mm units
│   │   ├── dxf.py
│   │   ├── pdf.py
│   │   └── json_plan.py           # plan → JSON for the browser
│   │
│   ├── fab/                       # ── laser / CNC production ──
│   │   ├── layers.py              # CUT / SCORE / ENGRAVE conventions
│   │   ├── textpath.py            # ★ glyphs → outlines, incl. along arcs
│   │   ├── hershey/               # single-line engraving fonts
│   │   ├── kerf.py
│   │   ├── islands.py             # ★ fall-out detection + auto-bridging
│   │   ├── preflight.py           # ★ the checklist that saves your plywood
│   │   ├── materials.py           # material presets
│   │   ├── tiling.py              # split oversized art across sheets
│   │   └── clock.py               # bore, hand clearance, movement specs
│   │
│   ├── analysis/
│   │   ├── stats.py               # lifespans, family sizes, distributions
│   │   ├── gaps.py                # ★ research gap / brick wall ranking (§12.4)
│   │   ├── geo.py                 # migration distances
│   │   └── dna.py                 # cM ↔ expected relationship checks
│   │
│   ├── io/
│   │   ├── gedcom/
│   │   │   ├── lexer.py
│   │   │   ├── parser.py          # 5.5.1 + 7.0 read
│   │   │   └── writer.py
│   │   ├── csv_import.py          # forgiving spreadsheet import
│   │   └── backup.py
│   │
│   └── web/                       # ── static frontend, no build step ──
│       ├── index.html
│       ├── vendor/d3.v7.min.js
│       ├── css/app.css
│       └── js/
│           ├── main.js
│           ├── canvas.js          # renders plan JSON → SVG DOM
│           ├── zoom.js
│           ├── inspector.js       # person detail / edit panel
│           ├── controls.js        # style + layout control panel
│           ├── search.js
│           └── contingency.js     # ★ the what-if interaction
│
├── tests/
│   ├── golden/                    # snapshot SVGs
│   ├── fixtures/
│   │   ├── sample_family.ged      # generated, 400 people, 8 generations
│   │   └── pathological.ged       # cousin marriage, adoption, no dates
│   └── test_*.py
│
└── docs/
    ├── RESEARCH_HANDBOOK.md       # §19 extracted for printing
    ├── DATA_ENTRY_RULES.md        # §20
    └── LASER_CHECKLIST.md         # §10.9, print and pin above the machine
```

---

## 5. Data model

### 5.1 Design principles

These seven rules prevent 90% of the pain that hits genealogy databases at generation five.

1. **Stable opaque IDs.** Every entity gets a UUIDv4 primary key. Never key on a name, never on a display number. Names change, get corrected, and duplicate.
2. **Never store a single "full name" field.** See §5.4.
3. **Never link child → parent directly.** Link `person → union` (as child) and `person → union` (as partner). This is the GEDCOM model and it is correct: it handles half-siblings, remarriage, single parents, and unknown partners without special cases.
4. **Everything dated is an Event, not a column.** Do not put `birth_date` on `person`. Put a birth Event with a role. This means you get baptism, census, emigration, probate, military service, apprenticeship and burial for free, with the same date/place/source machinery.
5. **Record what the document says, then normalise separately.** Two fields: `as_recorded` (verbatim, never edited) and the parsed/normalised value. When you later discover the transcription was wrong, you still have the original.
6. **Every fact can carry a citation and a confidence.** Unsourced facts are hypotheses. The chart can *render* this distinction (§8) — dashed outlines for unproven people is one of the most useful things this program will do for you.
7. **Absence is data.** An "Unknown mother of John Smith" is a real person record with a real ID. Without it your tree structure silently collapses and sibling groups merge incorrectly.

### 5.2 Schema (`helix/store/schema.sql`)

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ─────────────────────────── PEOPLE ───────────────────────────
CREATE TABLE person (
  id            TEXT PRIMARY KEY,            -- uuid4
  sex           TEXT NOT NULL DEFAULT 'U'
                CHECK (sex IN ('M','F','X','U')),
  living        INTEGER,                     -- NULL = infer (§5.7)
  privacy       TEXT NOT NULL DEFAULT 'inherit'
                CHECK (privacy IN ('public','private','inherit')),
  is_placeholder INTEGER NOT NULL DEFAULT 0, -- "Unknown father of X"
  confidence    INTEGER NOT NULL DEFAULT 2   -- 0 speculative … 3 proven
                CHECK (confidence BETWEEN 0 AND 3),
  notes         TEXT,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

-- Multiple names per person, with validity windows.
CREATE TABLE person_name (
  id             TEXT PRIMARY KEY,
  person_id      TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  type           TEXT NOT NULL DEFAULT 'birth'
                 CHECK (type IN ('birth','married','also_known_as','legal',
                                 'religious','nickname','anglicised','as_recorded')),
  is_primary     INTEGER NOT NULL DEFAULT 0,
  title          TEXT,        -- Rev, Dr, Lady
  given          TEXT,        -- "John Henry"
  given_used     TEXT,        -- "Harry"  — the name they actually went by
  surname_prefix TEXT,        -- van, de, Mac, Ó
  surname        TEXT,
  suffix         TEXT,        -- Jr, III
  as_recorded    TEXT,        -- verbatim from the source document
  valid_from     TEXT,        -- ISO date or NULL
  valid_to       TEXT,
  soundex        TEXT,        -- computed on write
  dmetaphone     TEXT,        -- computed on write
  sort_key       TEXT         -- "SMITH, John Henry" — computed on write
);
CREATE INDEX ix_name_person   ON person_name(person_id);
CREATE INDEX ix_name_surname  ON person_name(surname);
CREATE INDEX ix_name_soundex  ON person_name(soundex);
CREATE INDEX ix_name_sort     ON person_name(sort_key);

-- ─────────────────────────── UNIONS ───────────────────────────
CREATE TABLE union_ (
  id         TEXT PRIMARY KEY,
  type       TEXT NOT NULL DEFAULT 'marriage'
             CHECK (type IN ('marriage','civil_partnership','unmarried',
                             'unknown','annulled')),
  confidence INTEGER NOT NULL DEFAULT 2,
  notes      TEXT
);

CREATE TABLE union_partner (
  union_id  TEXT NOT NULL REFERENCES union_(id) ON DELETE CASCADE,
  person_id TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  role      TEXT NOT NULL DEFAULT 'partner',   -- partner | husband | wife
  seq       INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (union_id, person_id)
);

CREATE TABLE union_child (
  union_id     TEXT NOT NULL REFERENCES union_(id) ON DELETE CASCADE,
  person_id    TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  -- relationship to EACH parent may differ (adopted by one, natural to other)
  rel_partner1 TEXT NOT NULL DEFAULT 'biological'
               CHECK (rel_partner1 IN ('biological','adopted','step','foster',
                                       'guardian','unknown')),
  rel_partner2 TEXT NOT NULL DEFAULT 'biological'
               CHECK (rel_partner2 IN ('biological','adopted','step','foster',
                                       'guardian','unknown')),
  is_primary   INTEGER NOT NULL DEFAULT 1,  -- ★ the union used for LAYOUT
  birth_order  INTEGER,
  confidence   INTEGER NOT NULL DEFAULT 2,
  PRIMARY KEY (union_id, person_id)
);
CREATE INDEX ix_child_person ON union_child(person_id);

-- ★ CRITICAL: a person may belong to several unions as a child (adoption,
--   uncertain parentage). Exactly one must have is_primary = 1. That is the
--   edge the layout engine follows. All others are drawn as chords (§7.4).

-- ─────────────────────────── EVENTS ───────────────────────────
CREATE TABLE event (
  id            TEXT PRIMARY KEY,
  type          TEXT NOT NULL,     -- see controlled vocabulary below
  date_json     TEXT,              -- serialised GenDate (§5.3) — the truth
  date_earliest TEXT,              -- ISO, denormalised for indexing
  date_latest   TEXT,
  date_sort     REAL,              -- decimal year midpoint — used by layout
  place_id      TEXT REFERENCES place(id),
  description   TEXT,
  age_text      TEXT,              -- age as stated in the source, verbatim
  confidence    INTEGER NOT NULL DEFAULT 2,
  notes         TEXT
);
CREATE INDEX ix_event_sort ON event(date_sort);
CREATE INDEX ix_event_type ON event(type);

-- Events are shared. A marriage has two principals and witnesses.
-- A census has an entire household. This is why roles are a separate table.
CREATE TABLE event_role (
  event_id  TEXT NOT NULL REFERENCES event(id) ON DELETE CASCADE,
  person_id TEXT REFERENCES person(id) ON DELETE CASCADE,
  union_id  TEXT REFERENCES union_(id) ON DELETE CASCADE,
  role      TEXT NOT NULL DEFAULT 'principal',
            -- principal | spouse | witness | informant | officiant
            -- | parent | child | household_member | employer
  PRIMARY KEY (event_id, person_id, union_id, role)
);
CREATE INDEX ix_role_person ON event_role(person_id);

-- Controlled event vocabulary (enforce in Python, not SQL, so it stays extensible):
--  VITAL:      birth, baptism, christening, death, burial, cremation, stillbirth
--  UNION:      marriage, marriage_banns, marriage_licence, divorce, separation,
--              engagement, civil_partnership
--  RECORD:     census, electoral_roll, probate, will, tax_list, directory_entry
--  LIFE:       occupation, education, apprenticeship, graduation, military_service,
--              enlistment, discharge, immigration, emigration, naturalisation,
--              residence, religion, title, honour, imprisonment, illness
--  RESEARCH:   dna_test, photograph, note

-- ─────────────────────────── PLACES ───────────────────────────
-- Hierarchical, because "Bath" means different things in 1750 and 1974.
CREATE TABLE place (
  id           TEXT PRIMARY KEY,
  name         TEXT NOT NULL,
  type         TEXT,   -- house|street|parish|town|county|country|region
  parent_id    TEXT REFERENCES place(id),
  lat          REAL,
  lon          REAL,
  as_recorded  TEXT,
  valid_from   TEXT,   -- boundary changes: "Somerset" pre-1974 vs "Avon"
  valid_to     TEXT,
  notes        TEXT
);
CREATE INDEX ix_place_parent ON place(parent_id);

-- ───────────────────── SOURCES & CITATIONS ─────────────────────
CREATE TABLE source (
  id         TEXT PRIMARY KEY,
  title      TEXT NOT NULL,
  author     TEXT,
  publisher  TEXT,
  repository TEXT,          -- "Somerset Heritage Centre", "GRO", "Ancestry"
  ref        TEXT,          -- shelfmark / piece / folio / URL
  url        TEXT,
  type       TEXT,          -- civil_reg|parish|census|probate|newspaper
                            -- |monument|family|dna|website|book|interview
  quality    INTEGER NOT NULL DEFAULT 2,  -- 0 unreliable … 3 original+primary
  notes      TEXT,
  accessed   TEXT
);

CREATE TABLE citation (
  id           TEXT PRIMARY KEY,
  source_id    TEXT NOT NULL REFERENCES source(id) ON DELETE CASCADE,
  -- polymorphic target: exactly one of these is non-null
  person_id    TEXT REFERENCES person(id) ON DELETE CASCADE,
  event_id     TEXT REFERENCES event(id) ON DELETE CASCADE,
  union_id     TEXT REFERENCES union_(id) ON DELETE CASCADE,
  name_id      TEXT REFERENCES person_name(id) ON DELETE CASCADE,
  page         TEXT,
  transcript   TEXT,      -- ★ paste the full transcription here. Always.
  image_path   TEXT,
  confidence   INTEGER NOT NULL DEFAULT 2,
  reasoning    TEXT       -- your analysis: why this record is your ancestor
);
CREATE INDEX ix_cite_person ON citation(person_id);
CREATE INDEX ix_cite_event  ON citation(event_id);

-- ─────────────────────── MEDIA & METADATA ───────────────────────
CREATE TABLE media (
  id       TEXT PRIMARY KEY,
  path     TEXT NOT NULL,     -- relative to the .helix file's folder
  type     TEXT,              -- photo|document|audio|video
  caption  TEXT,
  taken    TEXT,
  sha256   TEXT
);
CREATE TABLE media_link (
  media_id  TEXT NOT NULL REFERENCES media(id) ON DELETE CASCADE,
  person_id TEXT REFERENCES person(id) ON DELETE CASCADE,
  event_id  TEXT REFERENCES event(id) ON DELETE CASCADE,
  is_portrait INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (media_id, person_id, event_id)
);

CREATE TABLE tag (
  id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, colour TEXT
);
CREATE TABLE person_tag (
  person_id TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  tag_id    TEXT NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
  PRIMARY KEY (person_id, tag_id)
);

-- ─────────────────────── RESEARCH & DNA ───────────────────────
CREATE TABLE research_task (
  id          TEXT PRIMARY KEY,
  person_id   TEXT REFERENCES person(id) ON DELETE CASCADE,
  question    TEXT NOT NULL,           -- "Find John's baptism, Bath, c.1812"
  status      TEXT NOT NULL DEFAULT 'open'
              CHECK (status IN ('open','in_progress','done','dead_end')),
  priority    INTEGER NOT NULL DEFAULT 2,
  repository  TEXT,
  result      TEXT,                    -- ★ record NEGATIVE results too
  created_at  TEXT, updated_at TEXT
);

CREATE TABLE dna_match (
  id            TEXT PRIMARY KEY,
  person_id     TEXT REFERENCES person(id),   -- may be NULL if unidentified
  match_name    TEXT,
  platform      TEXT,      -- ancestry|myheritage|23andme|ftdna|gedmatch
  shared_cm     REAL,
  largest_cm    REAL,
  segments      INTEGER,
  predicted_rel TEXT,
  documented_rel TEXT,     -- filled by the app from the tree
  notes         TEXT
);

-- ─────────────────────── AUDIT / UNDO ───────────────────────
CREATE TABLE change_log (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ts        TEXT NOT NULL,
  op        TEXT NOT NULL,     -- insert|update|delete
  tbl       TEXT NOT NULL,
  row_id    TEXT NOT NULL,
  before    TEXT,              -- JSON
  after     TEXT               -- JSON
);
-- Undo = replay `before` states in reverse. Keep unbounded; it is tiny.

-- ─────────────────────── PROJECT SETTINGS ───────────────────────
CREATE TABLE settings (k TEXT PRIMARY KEY, v TEXT);
-- keys: subject_person_id, schema_version, project_title, default_style, …
```

### 5.3 `GenDate` — the fuzzy date type

**This is the single most under-engineered thing in amateur genealogy software.** Get it right and everything downstream works.

Real dates you will encounter:

| Written | Meaning |
|---|---|
| `12 MAR 1841` | exact |
| `abt 1834` / `c.1834` | about — ±3 years by convention, configurable |
| `bef 1900` | before |
| `aft 1866` | after |
| `bet 1820 and 1825` | range |
| `Q3 1871` | GRO index quarter — Jul–Sep 1871 |
| `1750/51` | **dual dating** — English legal year began 25 March until 1752 |
| `24 FEB 1723/24` | same |
| `est 1795` | estimated from an age at another event |
| `calc 1798` | calculated (e.g. from "aged 54" on an 1852 death record) |

**Representation** — a frozen dataclass, serialised to `date_json`:

```python
@dataclass(frozen=True)
class GenDate:
    kind: Literal["exact","about","before","after","between",
                  "quarter","estimated","calculated","unknown"]
    earliest: date | None        # inclusive lower bound
    latest: date | None          # inclusive upper bound
    precision: Literal["day","month","quarter","year","decade","century","unknown"]
    calendar: Literal["gregorian","julian","dual"] = "gregorian"
    original: str = ""           # ★ never lose the input string
    confidence: int = 2

    @property
    def sort_value(self) -> float | None:   # decimal year midpoint
    @property
    def display(self) -> str:               # renders back to human text
    def overlaps(self, other) -> bool
    def is_definitely_before(self, other) -> bool
```

**Parser requirements** (`gendate.parse(str) -> GenDate`):

- Accept GEDCOM date phrases, ISO, UK `dd/mm/yyyy`, US `mm/dd/yyyy` (configurable ambiguity policy — **default to UK, and flag ambiguous ones** rather than guessing silently).
- Handle dual dates: `1723/24` → earliest `1724-01-01`, latest `1724-03-24`, calendar `dual`. Store the historically correct year.
- `about` widens bounds by `settings.about_years` (default 3) but keeps `precision="year"`.
- **Never raise.** Unparseable input → `kind="unknown"` with `original` preserved and a validation warning logged. You must never lose a user's typing.
- Round-trip property test: `parse(d.display).earliest == d.earliest` for all generated cases (use hypothesis).

**Age calculation** returns an *interval*, not a number:

```python
def age_at(birth: GenDate, event: GenDate) -> AgeRange:
    """Returns (min_years, max_years, display).
    display examples: "42", "41–43", "≥ 38", "unknown".
    NEVER return a bare int. An age computed from two 'about' dates
    that is displayed as an exact number is a lie the chart will repeat
    for a hundred years."""
```

### 5.4 Name storage rules

Store the pieces; compose for display. Never the reverse.

| Field | Example | Note |
|---|---|---|
| `title` | Rev | |
| `given` | John Henry | space-separated, ordered |
| `given_used` | Harry | the name they answered to — often *not* the first given name |
| `surname_prefix` | van der / Mac / Ó / de la | keep separate so sorting works |
| `surname` | Smith | |
| `suffix` | Jr, III | |
| `as_recorded` | "Jno Hy Smyth" | verbatim from the record — never edit |

**Rules:**

1. **Women are stored under their birth surname as primary.** Add a `type='married'` name record with `valid_from` = marriage date. The display setting `surname_display` then chooses: birth / married / `Smith (née Jones)` / both.
2. **Spelling variants are not errors.** Smith/Smyth/Smythe are separate `as_recorded` values under one person. Never "correct" a source.
3. **Compute on write:** `soundex`, `dmetaphone` (via `jellyfish`), and `sort_key` = `f"{surname.upper()}, {given}"`. Normalise to Unicode NFC first.
4. **Placeholders are structured too:** `given=NULL, surname='SMITH', is_placeholder=1`, display rule renders `[Unknown] Smith`. Never type the literal string "Unknown" into `given`.
5. Patronymics (`Jónsdóttir`), generational names, and cultures where the family name comes first are handled by a per-person `name_order` hint on `person_name` if you ever need it — leave the column out of v1, note the extension.

### 5.5 The relationship graph

The union model gives you a **directed acyclic graph**, not a tree. Both directions matter:

```
person --(union_child, is_primary)--> union --(union_partner)--> parents
person --(union_partner)-----------> union --(union_child)-----> children
```

**Key queries as recursive CTEs** (`store/queries.py`):

```sql
-- All ancestors of :root, with generation depth
WITH RECURSIVE anc(person_id, gen) AS (
    SELECT :root, 0
  UNION
    SELECT up.person_id, a.gen + 1
    FROM anc a
    JOIN union_child uc ON uc.person_id = a.person_id AND uc.is_primary = 1
    JOIN union_partner up ON up.union_id = uc.union_id
)
SELECT * FROM anc;
```

`UNION` (not `UNION ALL`) terminates on pedigree collapse. If you use `UNION ALL` a cousin marriage will loop forever — **this is the number one bug in home-made family tree code.**

Also provide: `descendants(root)`, `mrca(a, b)`, `path_between(a, b)`, `siblings(p)` (full vs half — distinguished by how many parents are shared).

### 5.6 Confidence and evidence

Every `confidence` column uses one scale:

| Value | Meaning | Rendered as |
|---|---|---|
| 0 | Speculative / family legend | dotted outline, 40% opacity |
| 1 | Circumstantial, one weak source | dashed outline |
| 2 | Documented, one good source (default) | solid thin |
| 3 | Proven — multiple independent primary sources | solid, full weight |

The style system (§8) can bind stroke pattern and opacity to this field. **The result is a chart that visibly shows the quality of your own research.** This is a feature, not an embarrassment: the fuzzy edges are honest, and they tell you exactly where to work next.

### 5.7 Living-person privacy

```python
def is_living(p) -> bool:
    if p.living is not None: return bool(p.living)
    if has_death_or_burial_event(p): return False
    b = birth_year(p)
    if b is None: return True                    # ★ fail safe, assume living
    return (current_year - b) < settings.privacy_age_cutoff   # default 100
```

Export modes: `full` / `redact_living` (name → `Living Smith`, dates hidden) / `omit_living`.
**The redaction happens in the layout engine, before the render plan is built** — so a redacted SVG cannot leak data in a hidden attribute. Test for this explicitly.

### 5.8 Import / export

- **GEDCOM 5.5.1 import** — must handle `CONT`/`CONC` line continuation, ANSEL/UTF-8/UTF-16 encodings (sniff the BOM and the `CHAR` tag), custom `_` tags (preserve into `notes` rather than dropping), and `@I123@` cross-references.
- **GEDCOM 7.0 import** — same shape, stricter, UTF-8 only.
- **GEDCOM 5.5.1 export** — for round-tripping into Ancestry/Gramps/FamilySearch.
- **CSV import** — a forgiving path for spreadsheet starters. Expect one row per person with a `parent_ref` column; run duplicate detection after.
- **Backup:** every write session copies the `.helix` file to `backups/YYYYMMDD-HHMMSS.helix`, keeping the last 30. Non-negotiable. Genealogy data is irreplaceable.

---

## 6. Domain layer API

`helix/graph/build.py` loads the whole database into memory once (10k people ≈ 30 MB — trivial) and exposes:

```python
class FamilyGraph:
    people: dict[str, Person]
    unions: dict[str, Union]
    subject_id: str

    def parents(self, pid, primary_only=True) -> list[str]
    def children(self, pid) -> list[str]
    def partners(self, pid) -> list[str]
    def ancestors(self, pid, max_gen=None) -> dict[str, int]   # id → generation
    def descendants(self, pid, max_gen=None) -> dict[str, int]
    def mrca(self, a, b) -> tuple[str, int, int] | None
    def relationship(self, a, b) -> str      # "second cousin once removed"
    def apexes(self) -> list[str]            # people with no known parents
    def is_endogamous(self) -> list[tuple]   # pedigree collapse pairs
```

Rebuild is cheap; do not attempt incremental graph updates in v1. On any edit, reload.

---

## 7. The layout engine

### 7.1 The Render Plan — the central abstraction

**Everything downstream consumes this. Nothing downstream computes geometry.**

```python
@dataclass
class RenderPlan:
    canvas: Canvas                  # width_mm, height_mm, centre, bleed
    elements: list[Element]         # ordered, back to front
    meta: PlanMeta                  # person count, date span, style id, hash

@dataclass
class Element:
    kind: Literal["arc","path","line","circle","text","textpath","group","marker"]
    layer: Literal["CUT","SCORE","ENGRAVE","ENGRAVE_DEEP","GUIDE","PRINT_ONLY"]
    d: str | None                   # SVG path data in mm, absolute coords
    stroke: str | None              # resolved colour
    stroke_width: float | None      # mm
    fill: str | None
    text: str | None
    font: FontSpec | None
    transform: str | None
    # ── provenance: every element knows what it represents ──
    person_id: str | None
    union_id: str | None
    role: str                       # "cell" | "connector" | "label" | "thread"
                                    # | "tick" | "ornament" | "bore" | "bridge"
    z: int
```

Rules:

- **Units are millimetres throughout.** Never pixels, never points, until the very last line of a renderer.
- **Coordinates are absolute**, origin at top-left of the canvas, y down (SVG convention). Convert from polar once, in the layout engine.
- Path data uses **absolute commands only** (`M`, `L`, `A`, `C`, `Z`) and at most **4 decimal places** (0.1 µm — far below laser resolution, prevents 12 MB files).
- Each element carries its `person_id`. This is what makes hover, click, search-highlight and contingency-fade work on the frontend with zero extra data.

### 7.2 Layout modes

Expose all three; they answer different questions.

**A. Generation rings** (`mode="generation"`)
Ring index = generation depth from the apex. Tidy, symmetrical, traditional. Weakness: a cousin born in 1890 and one born in 1965 sit on the same ring, which is visually misleading.

**B. Chronological rings** (`mode="chronological"`) — **make this the default.**
Radius is a function of birth year. The chart becomes a *timeline in polar coordinates*. Decade and century rings can be engraved as concentric ticks. This is the mode that makes the clock in the centre conceptually coherent: **the whole disc is a clock, the rings are years, and the hands sweep across two centuries of your family.**

**C. Lifeline mode** (`mode="lifeline"`) — the visual showpiece.
Chronological radii, but each person is drawn as a **radial bar from their birth radius to their death radius**. Bar length = lifespan. You instantly see infant mortality as tiny stubs, the 1918 flu as a band of terminations, and long-lived matriarchs as long spokes. Living people get an open-ended arrow to the rim. Combine with mode B by making cells lifeline-shaped rather than fixed-height.

**D. Hourglass** (`mode="hourglass"`, Phase 7)
You sit on a middle ring. Ancestors radiate *inward*, descendants *outward*. Best if the tree is deep in both directions.

### 7.3 Radius scales (`layout/scales.py`)

```python
# Generation mode: ring widths chosen so arc-length per person is roughly
# constant, so outer (crowded) rings can be thinner and still legible.
def generation_radii(counts: list[int], r0, R, min_ring, label_h) -> list[float]

# Chronological, linear in time:
def r_linear(t, t0, t1, r0, R):
    return r0 + (t - t0) / (t1 - t0) * (R - r0)

# ★ Chronological, EQUAL-AREA. Because disc area grows as r², a linear time
#   scale crams recent, populous generations into the outer rings where they
#   are already densest. Equal-area gives every year the same amount of ink.
def r_equal_area(t, t0, t1, r0, R):
    frac = (t - t0) / (t1 - t0)
    return math.sqrt(r0**2 + frac * (R**2 - r0**2))
```

Offer both, with a `radius_gamma` slider (γ=1 linear, γ=0.5 equal-area, continuous in between) so the user can dial the compression by eye. Also allow a **piecewise scale** with manual breakpoints — useful when you have one line reaching back to 1620 and everyone else starting in 1810.

### 7.4 The hard cases — solve these explicitly

| Problem | Solution |
|---|---|
| **Pedigree collapse / cousin marriage.** Two people in the chart marry each other. The graph is not a tree; a naive recursion loops or duplicates. | Follow only `is_primary=1` child links for layout. Draw the second parentage as a **chord** across the disc, in a distinct style. Chords are visually striking and honest. Count them: `graph.is_endogamous()`. |
| **Remarriage.** A person appears in three unions. | The person occupies **one cell**. Each union gets a small marker on the cell's outer edge, and its children hang from that marker's angular sub-range. Order unions by marriage date. |
| **Unknown parents.** The line just stops. | Insert a synthetic `is_placeholder` person only if `settings.pad_unknown_generations` is on (default off). Otherwise the branch terminates and is drawn with an **open-ended "frayed" cap** — this reads as "research continues here", not as an error. Style token: `terminus.frayed`. |
| **Missing birth dates in chronological mode.** | Estimate from siblings/parents/marriage using an inference chain (parent birth + 25y, marriage − 24y, first child − 25y). Record the estimate as an `estimated` GenDate and **render the cell with a distinct texture** so it's visibly inferred, not known. Never silently invent. |
| **Child born before parent** (a real data error). | Validator flags it (§12.3). Layout clamps the child's radius to parent + ε and marks the element `role="error"` for red highlight in the GUI. Never crash. |
| **Very unequal branch sizes.** One line has 300 descendants, another has 4. | `weight_mode` option: `leaves` (arc ∝ number of leaf descendants — cleanest), `descendants` (∝ total subtree), `equal` (each apex gets an equal sector — good for a symmetric poster), `sqrt_leaves` (compromise). |
| **Sibling groups with no partner.** | Fine — a person with no union is a leaf cell. |
| **Two people are the same person** (duplicate). | Out of scope for layout; handle in the merge tool (§12.5). |

### 7.5 The core algorithm

```
LAYOUT(graph, settings, style) -> RenderPlan

1. SELECT SCOPE
   roots = settings.apexes or graph.apexes()
   include = union of descendants(root) for root in roots
   apply privacy filter (§5.7)          # ★ before anything else
   apply generation/date/tag filters

2. RESOLVE PRIMARY EDGES
   for each person: pick the union_child row with is_primary=1
   detect cycles → break by earliest-marriage heuristic, log warning
   collect secondary edges into `chords`

3. SECTOR ALLOCATION (multi-apex)
   total_weight = sum(weight(root))
   optionally reserve `sector_gap` degrees between lineages
   assign each root an angular span ∝ its weight (or equal, per weight_mode)
   optionally snap sector boundaries to the 12 clock positions   # ★ lovely
   
4. ANGULAR ASSIGNMENT  (recursive, O(n))
   weight(p) = 1 if no children else sum(weight(c) for c in children)
   # bottom-up post-order, memoised
   
   assign(p, θ0, θ1):
       p.θ_centre = (θ0 + θ1) / 2
       p.θ_span   = θ1 - θ0
       cursor = θ0 + pad
       for u in unions(p) sorted by marriage date:
           for c in children(u) sorted by birth date (then by name):
               span = (θ1 - θ0 - 2*pad) * weight(c) / weight(p)
               assign(c, cursor, cursor + span)
               cursor += span

5. RADIAL ASSIGNMENT
   generation mode  → r = generation_radii[gen(p)]
   chronological    → r = r_scale(birth_year(p))
   lifeline         → r_in = r_scale(birth), r_out = r_scale(death or now)
   enforce r(child) > r(parent) + min_ring_gap

6. RELAXATION  (labels/cells that would collide)
   for each ring:
       min_sep(p) = required_arc_length(p) / r(p)     # radians
       run 1-D constrained relaxation along θ (see relax.py)
       max 200 iterations, ε = 0.0001 rad
   if a cell still cannot fit its label:
       demote per label_policy: full → initials → number → dot
       record in plan.meta.demotions for the GUI legibility report

7. GEOMETRY EMISSION
   cells        → annular sector paths (arc, line, arc reversed, close)
   connectors   → per style: 'labyrinth' (radial+arc only, right angles),
                  'organic' (cubic Bézier with radial control points),
                  'straight', 'circuit' (45° chamfered corners)
   labels       → §7.6
   chords       → quadratic Bézier through the centre region
   ornaments    → decade rings, era bands, clock face, border, title cartouche
   thread       → §11, emitted LAST so it sits on top

8. VALIDATE & RETURN
   run fab preflight if production_mode != 'print'
   attach warnings to plan.meta
```

### 7.6 Label placement (`layout/labels.py`)

This is where most radial charts fail. Requirements:

- **Two orientations.** `tangential` (text curved along the arc — best for inner rings where cells are angularly wide) and `radial` (text runs outward along the spoke — best for outer rings). Auto-select per ring: use radial when `cell_arc_length < text_width`.
- **Auto-flip.** For radial text on the left half of the disc (θ between 90° and 270°), rotate 180° and right-align, so nothing is upside down. Same for tangential text below the horizontal.
- **Curved text for laser** must be baked to outlines by transforming each glyph's outline along the arc (§10.2) — `textPath` does not survive export to DXF.
- **Content templates.** The user controls exactly what appears, via a template string per ring band:
  ```
  "{given_used|given_first} {surname}"
  "{given} {surname}\n{birth_year}–{death_year}"
  "{initials}"
  "{surname}\n{birth_year}"
  "{n}"                          # index number → companion booklet (§18.7)
  ```
  Supported fields: `given, given_first, given_used, initials, surname,
  surname_married, birth_year, death_year, birth_date, death_date, age,
  birth_place, birth_place_short, occupation, education, sosa, n, lifespan_bar`.
  Missing values collapse gracefully (no stray dashes or empty brackets).
- **Per-ring overrides.** Inner rings (few people, lots of room) get full detail; outer rings get names only. This should be a first-class control: `label_detail_by_ring: {0-2: "full", 3-5: "name_dates", 6+: "name"}`.
- **Minimum type size guard.** If resolved font size < `style.min_font_mm` (default 2.2 mm cap height for wood engraving), demote and warn.

### 7.7 Ornaments (`layout/ornament.py`)

- **Decade / century rings** — thin engraved circles with year labels at a chosen bearing (e.g. always at 3 o'clock, or repeated at 12/3/6/9).
- **Era bands** — faint filled annuli with labels: *Regency*, *Victorian*, *Edwardian*, *The Great War*, *WWII*. Ships with a UK preset (`data/eras_uk.json`), user-editable. Gives the chart historical meaning and instantly contextualises every ancestor.
- **Event annotations** — optional tick + label at a specific year: `1918 influenza`, `1834 Poor Law`, `1914–18`. Drawn in the margin ring.
- **Title cartouche**, **legend**, **compass/orientation mark**, **maker's mark and date**.
- **Clock face** — see §10.8.

---

## 8. The style system

**Styles are data, not code.** A style is a JSON file of tokens. The Python layer only ever reads resolved token values.

```jsonc
{
  "id": "labyrinth",
  "name": "Labyrinth",
  "extends": null,
  "canvas": {
    "diameter_mm": 600, "margin_mm": 20,
    "background": "#F7F4EE", "shape": "circle"   // circle | square | hex
  },
  "layout": {
    "mode": "chronological",     // generation | chronological | lifeline | hourglass
    "radius_gamma": 0.5,
    "inner_radius_mm": 90,       // the clock zone
    "start_angle_deg": -90,      // 12 o'clock
    "sweep_deg": 360,            // < 360 gives a fan
    "sector_gap_deg": 2,
    "weight_mode": "leaves",
    "cell_pad_deg": 0.15,
    "min_ring_gap_mm": 4,
    "couple_layout": "shared_cell"   // shared_cell | adjacent | offset_ring
  },
  "connectors": {
    "style": "labyrinth",        // labyrinth | organic | straight | circuit | none
    "corner_radius_mm": 1.5,
    "width_mm": 0.4,
    "colour": "#2B2B2B"
  },
  "cells": {
    "shape": "annular_sector",   // annular_sector | capsule | none | lifeline_bar
    "fill": "none",
    "stroke_width_mm": 0.3,
    "stroke_by_confidence": true // ★ dashes unproven people
  },
  "type": {
    "family": "Cormorant Garamond",
    "family_fallback": "EB Garamond",
    "engrave_font": "hershey_sans_1stroke",   // for laser ENGRAVE layer
    "size_mm": 3.2,
    "min_size_mm": 2.2,
    "tracking": 0.02,
    "case": "as_typed",          // as_typed | smallcaps | upper
    "surname_weight": 600
  },
  "labels": {
    "template_default": "{given_first} {surname}",
    "by_ring": { "0-2": "{given} {surname}\n{birth_year}–{death_year}",
                 "3-5": "{given_first} {surname}\n{birth_year}",
                 "6+":  "{given_first} {surname}" },
    "orientation": "auto"
  },
  "thread": {                     // ★ §11
    "enabled": true,
    "stroke_width_mm": 1.6,
    "colour": "#B03A2E",
    "layer": "ENGRAVE_DEEP",
    "halo_mm": 0.8,
    "node_marker": "diamond"
  },
  "ornament": {
    "decade_rings": true, "century_rings": true,
    "era_bands": true, "era_set": "uk",
    "border": "double_rule", "cartouche": true, "legend": true
  },
  "colour": {
    "mode": "none",              // none|sex|lineage|lifespan|geography|
                                 // occupation|confidence|criticality|surname
    "palette": ["#2B2B2B","#7D5A3C","#3E6B70","#B03A2E","#8A7B4F"]
  },
  "production": {
    "mode": "engrave_only",      // print | engrave_only | cut_outline | full_cutout
    "material": "birch_ply_3mm",
    "kerf_mm": 0.15,
    "min_web_mm": 1.2,
    "bridge_width_mm": 1.5,
    "text_to_paths": true
  }
}
```

**Resolution rules:** `extends` allows inheritance; deep-merge child over parent. Any token may be overridden per-element by a *rule*:

```jsonc
"rules": [
  { "when": "confidence <= 1",      "set": { "cells.dash": "2,1.5" } },
  { "when": "is_thread",            "set": { "cells.stroke_width_mm": 1.6 } },
  { "when": "birth_year < 1800",    "set": { "type.case": "smallcaps" } },
  { "when": "tag == 'emigrated'",   "set": { "cells.fill": "#EDE3D2" } }
]
```

Implement `when` as a tiny safe expression evaluator over a fixed variable set — **not** `eval()`. Use `ast.parse` in `eval` mode and walk a whitelist of node types (Compare, BoolOp, Name, Constant, UnaryOp only).

### 8.1 Visual direction for the shipped presets

Take the aesthetic seriously; the whole point is a heirloom object. Six presets, each with a genuine point of view (details in Appendix A):

- **Labyrinth** — orthogonal-in-polar connectors (radial segments and arc segments only, right-angle turns). Reads as a true maze. Ink-thrifty, laser-friendly, the closest to the original brief.
- **Circuit** — 45° chamfers, square terminal pads at each person, thin traces. Reads as a PCB. Superb on anodised aluminium or black acrylic.
- **Heirloom** — Victorian engraved-plate feel, hairline double rules, small caps surnames, hand-drawn cartouche. For walnut or brass.
- **Nordic** — extreme minimalism, one weight of rule, generous negative space, Futura-adjacent geometric sans, no cells at all — just dots and connectors.
- **Botanical** — organic Bézier connectors that thicken toward the centre like roots, leaf-shaped terminal marks for living people.
- **Blueprint** — white on cyan, dimension lines, revision block, everything annotated. Genuinely funny and genuinely legible.

---

## 9. Renderers

All four consume the same `RenderPlan`. **They contain no geometry logic.**

### 9.1 SVG (`render/svg.py`)

Hand-rolled string writer, not a library. Requirements:

- Root: `width="600mm" height="600mm" viewBox="0 0 600 600"` — **real physical units**, so Illustrator/Inkscape/LightBurn open it at the correct size. Getting this wrong is the most common laser-file failure.
- One `<g>` per layer, `id="CUT"` / `"ENGRAVE"` etc., with the layer's convention colour.
- `stroke-width` in mm (user units). For cut lines use `style.production.hairline_mm` (default 0.05).
- Inkscape layer compatibility: add `inkscape:groupmode="layer"` and `inkscape:label` attributes.
- Set `vector-effect="non-scaling-stroke"` **only** in the browser preview, never in the exported file.
- Include `<!-- helix vN | plan hash | date | person count -->` for reproducibility.

### 9.2 DXF (`render/dxf.py`)

- `ezdxf.new("R2000")`, `doc.units = ezdxf.units.MM`.
- Layers `CUT` (colour 1 red), `SCORE` (5 blue), `ENGRAVE` (7 black), `ENGRAVE_DEEP` (3 green).
- Arcs → `ARC` entities where exact; Béziers → `SPLINE`, or flatten to `LWPOLYLINE` with `flatten_tolerance_mm` (default 0.05) — **offer flattening as an option**; some laser software handles splines badly.
- Text is always outlines (`LWPOLYLINE` loops), never `TEXT` entities.

### 9.3 PDF (`render/pdf.py`)

reportlab, built from the plan directly. Two profiles:
- **Poster** — full colour, bleed, crop marks, embedded fonts, A0/A1/A2 or custom.
- **Cut file** — 1:1, vector, spot-colour-coded, for laser bureaus that prefer PDF.

### 9.4 Browser (`web/js/canvas.js`)

Consumes `plan.json` from `GET /api/plan`. Creates SVG DOM nodes one-to-one with plan elements, setting `data-person-id` from `element.person_id`. Because the preview is built from the identical plan, **the screen is a true proof of the cut file.**

Performance: for >4000 elements, render into a single `<path>` per layer with concatenated `d` strings for the static background, and keep only interactive elements as individual nodes. Use `requestIdleCallback` for label rendering.

---

## 10. Fabrication module — the part that saves your plywood

### 10.1 Layer conventions

| Layer | Meaning | SVG colour | DXF colour |
|---|---|---|---|
| `CUT` | Cut through | `#FF0000` | 1 red |
| `SCORE` | Shallow vector score | `#0000FF` | 5 blue |
| `ENGRAVE` | Raster/vector engrave | `#000000` | 7 black |
| `ENGRAVE_DEEP` | Second, deeper pass (the Thread) | `#00FF00` | 3 green |
| `GUIDE` | Registration, alignment, notes — **do not cut** | `#CCCCCC` | 8 grey |

These are the near-universal conventions across LightBurn, Glowforge, Epilog and most bureaus. Document them in the exported file's header comment.

### 10.2 Text → outlines (`fab/textpath.py`)

**Laser software cannot see your fonts.** Two paths:

**(a) Outline fonts** — `fontTools.pens.svgPathPen.SVGPathPen` over `TTFont.getGlyphSet()`. Handle kerning via the GPOS table (or fall back to `hmtx` advances). Scale from font units to mm: `scale = size_mm / font.upem`.

**(b) Single-line "stroke" fonts** — ★ **the pro move.** Outline fonts engraved small produce two closely-spaced contours that the laser fills, which is slow, burns wide, and looks muddy at 2–3 mm. A Hershey/single-stroke font draws each letter as one centreline pass: 3–5× faster, crisper, and legible at much smaller sizes. Ship Hershey Sans/Serif/Script vector data in `fab/hershey/` (public domain, from the NBS Hershey dataset). Make this the **default for the ENGRAVE layer** and outline fonts the default for print.

**(c) Text along an arc** — for tangential labels, place each glyph individually:

```python
def glyphs_along_arc(text, font, size_mm, cx, cy, radius, theta_start, flip):
    """Advance θ by (glyph_advance_mm / radius) radians per glyph.
    Rotate each glyph by (θ + π/2) so its baseline is tangent.
    If flip: rotate the whole run 180° about its midpoint and reverse order.
    Returns a list of absolute-coordinate path strings."""
```

Test with a golden file: a known string on a known radius must produce byte-identical output across runs.

### 10.3 Kerf compensation (`fab/kerf.py`)

Only matters for `CUT` layer geometry where parts must fit (inlays, tiled panels, the clock bore). Offset closed cut paths outward/inward by `kerf/2` using `pyclipper` with `JT_ROUND`, `ET_CLOSEDPOLYGON`. Sign convention: **holes grow, outlines shrink**. Provide a `kerf_test.svg` generator — a strip of 8 squares from 0.05 to 0.30 mm compensation to cut once and measure. Every material/power combination is different; measuring beats guessing.

### 10.4 Island detection and auto-bridging (`fab/islands.py`) ★

**The single most valuable feature in this module.** In any cut-out design, a region fully enclosed by cut lines falls out of the machine and is lost. On a dense family tree with hundreds of enclosed counters (the holes in `O`, `A`, `e`, and any closed cell), this is guaranteed.

```
DETECT:
  1. Buffer every CUT path by kerf/2  → shapely polygons
  2. cuts = unary_union(buffered)
  3. remaining = disc.difference(cuts)
  4. keep = the polygon containing the mounting/anchor point
  5. islands = [g for g in remaining.geoms if g is not keep]
  6. Report: count, total area, centroid list

AUTO-BRIDGE:
  for each island (largest first):
      find nearest point pair (island, keep) via shapely.ops.nearest_points
      locate the CUT path segment between them
      split that LineString at the nearest parameter t
      remove a segment of length `bridge_width_mm` centred on t
      emit two shortened paths + an element with role="bridge"
  re-run DETECT; iterate up to 20 times; if islands remain, fail preflight
```

Add `bridge_strategy`: `auto` / `manual` (GUI lets you click bridge points) / `none` (engrave-only designs).
Also handle **letter counters** specially: if `production.mode != "full_cutout"`, letters go on ENGRAVE and never generate islands. Only offer stencil-font substitution when text really must be cut through.

### 10.5 Minimum feature checks (`fab/preflight.py`)

Run before every export. Each check returns pass / warn / fail with a count and a clickable element list.

| Check | Default threshold | Why |
|---|---|---|
| Minimum web width between cuts | ≥ 1.2 mm (3 mm ply) | thinner snaps or chars through |
| Minimum engraved cap height | ≥ 2.2 mm | below this, wood grain eats the letterform |
| Minimum stroke separation in engrave | ≥ 0.35 mm | strokes merge into a blob |
| Closed islands | 0 (or all bridged) | parts fall out |
| Artwork within bed size | material preset | |
| Clock bore diameter and centring | ±0.1 mm | |
| Hand sweep clearance | no `CUT` inside hand radius | |
| Total path length | reported in m + time estimate | a 600 mm disc can be a 4-hour job |
| Duplicate/overlapping paths | 0 | doubled cuts burn twice, common after boolean ops |
| Open paths on the CUT layer | 0 | |
| Text still live (not outlined) | 0 | |
| Self-intersecting polygons | 0 | |

Path length → time estimate: `time ≈ Σ(length / feed_rate) + pierce_count × pierce_time`, with feed rates from the material preset. Rough, but it stops you starting a 5-hour job at 11 pm.

### 10.6 Material presets (`fab/materials.py`)

```jsonc
{
  "birch_ply_3mm": {
    "thickness_mm": 3.0, "kerf_mm": 0.18, "min_web_mm": 1.2,
    "min_cap_height_mm": 2.5, "cut_feed_mm_s": 8, "engrave_feed_mm_s": 200,
    "bed_mm": [600, 400], "notes": "Grain direction affects engrave contrast.
       Mask with paper tape to avoid smoke staining."
  },
  "mdf_5mm":      { "thickness_mm": 5.0, "kerf_mm": 0.25, "min_web_mm": 2.0, … },
  "acrylic_3mm_cast": { "kerf_mm": 0.12, "min_web_mm": 1.0,
       "notes": "Cast, not extruded — extruded engraves grey and dull." },
  "walnut_veneer_ply_4mm": { … },
  "slate_coaster":  { "engrave_only": true, "notes": "White engrave on dark. No cuts." },
  "anodised_alu_1mm": { "engrave_only": true,
       "notes": "Fibre or CO2+marking spray. Superb for fine type." },
  "leather_2mm":  { … },
  "card_1mm":     { "notes": "Prototype material. Cut a half-scale test first." }
}
```

**Always prototype on card or 3 mm MDF at 50% scale before committing to walnut.** Put this in `docs/LASER_CHECKLIST.md`.

### 10.7 Tiling (`fab/tiling.py`)

A 600 mm disc will not fit a 400 × 300 bed. Split into pie sectors or a rectangular grid, with:
- Overlap-free butt joints, or **finger joints** on straight cuts.
- **Alignment dowel holes** (3 mm) at consistent offsets, plus registration V-marks engraved on the back.
- A **backing plate** design: cut the full disc from thin ply as a substrate and glue the tiles down.
- Auto-generated **assembly diagram** PDF with tile numbers.

### 10.8 The clock (`fab/clock.py`)

| Spec | Value / rule |
|---|---|
| Bore diameter | Standard quartz movements need **7.9–8.0 mm**. Provide `bore_mm` (default 8.0) plus kerf compensation. Verify against your specific movement. |
| Shaft length | Must exceed material thickness by ~4–6 mm for the washer and nut. Common shaft lengths 12/16/20/25 mm. Preflight warns if `shaft_length < thickness + 5`. |
| Torque | Hands longer than ~150 mm need a **high-torque** movement. Warn based on `hand_length = inner_radius × 0.85`. |
| Clearance | Nothing raised, and ideally nothing cut, inside the hand sweep radius. Preflight enforces. |
| Hour markers | 12 engraved ticks. Options: plain, roman, arabic, or ★ **decade labels** — the hour positions double as the century/decade scale of the chronological rings. |
| Sector snapping | Option to snap lineage sector boundaries to clock hour positions. With 4, 6 or 12 apex lineages this is extremely satisfying. |
| Hanging | Keyhole slot engraved+cut on the reverse, or two 4 mm holes at 10 and 2 o'clock. Include a `back_plate.svg` export. |
| Second hand | Optional; a sweep (continuous) movement is silent, a stepping one ticks. For a wall piece in a quiet room, choose sweep. |

### 10.9 Pre-flight checklist (goes in `docs/LASER_CHECKLIST.md`, print it)

1. Units confirmed: open the SVG in Inkscape, measure the outer circle, compare to the intended diameter.
2. All text converted to paths — select all, check the font menu shows nothing.
3. Layers correct and mapped to the right power/speed in the machine software.
4. Island report clean; bridges present where expected.
5. Kerf test strip cut on **this** sheet of **this** material today.
6. Half-scale proof cut on card. Read every name on it. Check for upside-down labels.
7. Material larger than artwork + 10 mm on all sides. Flat, taped, focused.
8. Estimated run time acceptable; extraction on; fire extinguisher present; **do not leave the machine unattended.**
9. Cut order: engrave first, score second, inner cuts third, outer perimeter **last** (once the perimeter is cut, the part can shift).
10. Save the exact exported file and the style JSON alongside the finished piece. In five years you will want to cut another one.

---

## 11. The Thread — the signature feature ★

### 11.1 Definition

**The Thread** is the set of people without whom the Subject would not exist: the Subject's complete ancestral cone, following biological links only.

```python
def thread(graph, subject_id) -> ThreadResult:
    """
    members:  set[str]  — all biological ancestors of subject (+ subject)
    edges:    set[tuple[str,str]] — parent→child links along the cone
    by_gen:   dict[int, set[str]]
    """
```

Note it is not a single line — at generation *n* it contains up to 2ⁿ people. In a descendant-radial chart it renders as a set of continuous strands running from the centre outward to the Subject, converging as they go. This convergence is the visual point: **hundreds of separate families narrowing to one person.**

Rendering (all controllable in the style file):
- Heavier stroke, distinct colour, optional halo/outline offset.
- On laser: a **separate layer** (`ENGRAVE_DEEP`) for a second, deeper pass — the Thread is physically incised into the wood. Or cut it through entirely and **inlay brass wire or a contrasting veneer**. This is the detail that makes the object.
- Node markers on each Thread member (diamond/dot) so individuals are readable at a glance.

### 11.2 Contingency analysis — "what if they had never been born?"

```python
def contingency(graph, person_id) -> Contingency:
    """
    If `person_id` had never been born, who disappears?
    removed        : all descendants reachable ONLY through this person
                     (a descendant with another line of descent survives —
                      handle this correctly, it matters with cousin marriage)
    removed_count  : int
    subject_removed: bool          # does the Subject vanish?
    generations_lost: int
    surnames_lost  : list[str]
    """
```

Algorithm: compute `descendants(person)`. For each candidate, test whether *every* path from any apex to that candidate passes through `person`. Equivalent to a **dominator** computation on the ancestry DAG — build the dominator tree once (Lengauer–Tarjan, or the simple iterative algorithm, which is fast enough for 10k nodes) and answer all queries in O(1) thereafter. Everyone in `person`'s dominator subtree disappears.

**GUI behaviour:** hover any person → the doomed set fades to 15% opacity with a 400 ms transition, and a readout appears:

> **Elizabeth Whitcombe (1798–1861)**
> Without her: **412 people vanish** from this chart — 9 generations, 23 surnames — **including you.**

This is the feature the whole piece exists for. Give it real polish: smooth transition, a pin/lock mode so you can hold a state and screenshot it, and an "export this view" button.

### 11.3 Criticality colouring

Precompute, for every person, `criticality = size of their dominator subtree`. Offer it as a colour mode — the chart becomes a heatmap of structural importance. The centre glows; a childless branch is cold. Add a **"Top 20 most critical ancestors"** panel. Nobody expects this and everybody loves it.

### 11.4 Related highlights

- **Path between two people** — highlight the chain, with the relationship named ("your great-grandmother's second cousin").
- **MRCA highlighter** — select two people, ring their most recent common ancestor.
- **Cousin rings** — colour everyone by their relationship degree to the Subject.
- **Surname migration** — animate/highlight how one surname spreads through the disc.

---

## 12. Analysis engine

### 12.1 Statistics (`analysis/stats.py`)

Lifespan distribution by century and by sex; age at first marriage; children per union; infant mortality rate by decade; surname frequency; birth-month distribution; longest-lived; largest family; generational interval (mean years between generations — typically 25–33 and a useful sanity check on your own research).

### 12.2 Colour modes

`sex`, `lineage` (which apex sector), `lifespan` (continuous), `age_at_death` bucketed, `geography` (colour by country/county of birth — instantly shows migrations), `occupation` (grouped into ~12 categories via a keyword map), `confidence`, `criticality`, `surname`, `data_completeness`, `generation`.

Each mode auto-generates a legend element in the plan.

### 12.3 Validation (`graph/validate.py`)

Run on load and on demand; results feed both the GUI and preflight.

| Rule | Severity |
|---|---|
| Child born before a parent's birth | error |
| Child born > 9 months after father's death, or after mother's death | warning |
| Mother < 12 or > 55 at a child's birth | warning |
| Father < 12 or > 80 | warning |
| Death before birth | error |
| Marriage before age 14 | warning |
| Lifespan > 110 | warning |
| Person is their own ancestor (cycle) | error |
| Duplicate-looking people (fuzzy name + date within 3 y) | info |
| Event date outside the person's lifespan | warning |
| No primary child-union but multiple child-unions exist | error |
| Missing citation on a `confidence >= 2` fact | info |

### 12.4 Research gap ranking (`analysis/gaps.py`) ★

**A chart that tells you what to research next.** Score every open question:

```
score = w1 · potential_ancestors_unlocked      # 2^(generations you'd likely gain)
      + w2 · thread_membership                 # is this person on The Thread?
      + w3 · tractability                      # do cheap sources plausibly exist?
      + w4 · descendant_count
      - w5 · attempts_already_made
```

`tractability` heuristic: a person born in England 1837–1911 with a known name and county has civil registration *and* census coverage → high. Born pre-1650, or in a parish with lost registers → low.

Output a ranked **"Next 10 things to look for"** list, each with the person, the specific question, and the recommended repository (drawing on the source map in §19). Export as a printable to-do sheet. Render "brick wall" people on the chart with a distinct marker so the gaps are visible in the artwork itself.

### 12.5 Duplicate detection and merge

Blocking on `dmetaphone(surname)`, then score candidate pairs on: given-name similarity (Jaro-Winkler), birth-year proximity, birthplace match, parent-name overlap, spouse-name overlap. Present pairs above threshold in a side-by-side merge UI with per-field "keep left / keep right / keep both" and full undo.

### 12.6 DNA cross-check (`analysis/dna.py`)

Given a `dna_match` linked to a person in the tree, compare `shared_cm` against the expected range for the documented relationship (ship the Shared cM Project ranges as a data table). Flag matches where the documented relationship is statistically implausible — this is how you find a misattributed parentage, and it should be surfaced gently and privately, never on an exported chart.

---

## 13. GUI specification

Single page, three regions. Design it for someone who wants to fiddle with sliders and see the result instantly — every control updates the preview live.

```
┌────────────────────────────────────────────────────────────────────┐
│  Helix   [file ▾] [style ▾] [export ▾]     ⌕ search…      ⚠ 3      │
├──────────┬──────────────────────────────────────┬──────────────────┤
│ LEFT     │                                      │ RIGHT            │
│ Controls │        CANVAS                        │ Inspector        │
│          │        (pan / zoom / click)          │                  │
│ ▸ Layout │                                      │  selected person │
│ ▸ Rings  │                                      │  facts + sources │
│ ▸ Labels │                                      │  edit inline     │
│ ▸ Style  │                                      │  relationship    │
│ ▸ Colour │                                      │  contingency     │
│ ▸ Thread │                                      │                  │
│ ▸ Fabric.│                                      │                  │
│ ▸ Filter │                                      │                  │
├──────────┴──────────────────────────────────────┴──────────────────┤
│ 1,842 people · 9 generations · 1671–2026 · ⏱ est. 3 h 20 m cut     │
└────────────────────────────────────────────────────────────────────┘
```

### 13.1 Control panel sections

- **Layout** — mode, radius gamma slider, start angle, sweep, inner radius, sector gaps, weight mode, couple layout, apex selection.
- **Rings** — decade/century rings, era bands, ring width strategy, generation limit.
- **Labels** — global template, per-ring templates with a live token picker, orientation, size, min size, demotion policy. Show the **legibility report**: "37 labels demoted to initials — increase diameter to 720 mm to fit all names."
- **Style** — preset dropdown, then every token exposed with a sensible widget. "Duplicate preset & edit" saves a user style to `~/.helix/styles/`.
- **Colour** — mode + palette editor.
- **Thread** — subject picker, on/off, weight, colour, layer, contingency mode.
- **Fabrication** — production mode, material, kerf, bridges, tiling, clock settings, **Run preflight** button with a results list you can click to zoom to each problem.
- **Filter** — by generation, date range, surname, tag, place, confidence, living. Filters affect layout, not just visibility (removing people re-flows the disc).

### 13.2 Canvas interactions

| Action | Result |
|---|---|
| Scroll / pinch | zoom (d3-zoom, 0.2×–40×) |
| Drag | pan |
| Click person | select → Inspector |
| Hover person | tooltip + **contingency fade** (if armed) |
| Shift-click two people | show relationship + path |
| `F` | focus/zoom to selection |
| `T` | toggle Thread |
| `C` | arm/disarm contingency mode |
| `L` | cycle label detail |
| `Space` (hold) | temporary pan |
| `/` | focus search |
| `Esc` | clear selection |
| `Ctrl/⌘+Z` | undo (data edits) |
| `Ctrl/⌘+E` | export dialog |

Also: **minimap** in a corner for large charts, **breadcrumb** showing the selected person's line back to an apex, and a **year scrubber** (§18.6).

### 13.3 Inspector

Tabs: **Facts** (events in date order, each with confidence pip and citation count) · **Sources** · **Media** · **Relationships** (parents, partners, children, and computed relationship to Subject) · **Research** (open tasks, gap score) · **Raw** (JSON, for debugging).

Inline editing everywhere. Every edit writes to `change_log` and triggers a debounced re-layout (300 ms).

### 13.4 Accessibility and comfort

- Keyboard reachable throughout; visible focus rings.
- `prefers-reduced-motion` respected (contingency fade becomes instant).
- **A dyslexia-friendly UI option:** toggle the interface font to Atkinson Hyperlegible, increase line spacing to 1.6, and off-white background `#FAF7F0` rather than pure white. Applies to the *interface*, not the artwork. Ship it on by default; it costs nothing and helps everyone.
- All numeric inputs accept typed values, not just sliders.

---

## 14. CLI specification

Everything the GUI does must be scriptable, so charts are reproducible.

```bash
helix init my-family.helix
helix import gedcom ancestry-export.ged --db my-family.helix --merge-strategy=ask
helix export gedcom --db my-family.helix -o out.ged

helix render --db my-family.helix \
             --style labyrinth.json \
             --mode chronological \
             --subject "James Hxxx" \
             --diameter 600 \
             --out artwork/tree.svg

helix fab   --db my-family.helix --style labyrinth.json \
            --material birch_ply_3mm --production full_cutout \
            --tile 400x300 --out fab/

helix check --db my-family.helix          # validation report
helix gaps  --db my-family.helix --top 20 # research to-do list
helix stats --db my-family.helix
helix serve --db my-family.helix --port 8731 --open
```

`render` and `fab` must be **deterministic**: same db + same style → byte-identical output. Seed any tie-breaking sort with a stable key (person id). This is what makes golden-file tests possible.

---

## 15. Configuration files

| File | Location | Purpose |
|---|---|---|
| `*.helix` | user-chosen | the SQLite database (the only irreplaceable file) |
| `*.style.json` | alongside the db, or `~/.helix/styles/` | design tokens |
| `project.json` | alongside the db | subject id, default style, canvas size, apex list |
| `materials.json` | `~/.helix/` | user's measured kerf values — **update after every kerf test** |
| `eras_uk.json` | package data | historical era bands |
| `~/.helix/config.toml` | | app preferences, recent files, UI font choice |

---

## 16. Testing

### 16.1 Unit
- `gendate`: hypothesis round-trip, all GEDCOM phrase forms, dual dating, quarters, garbage input never raises.
- `names`: sort keys, prefixes, née display, Unicode NFC.
- `graph`: ancestors/descendants/MRCA on a hand-built 5-generation fixture; **cousin-marriage fixture must terminate**.
- `dominators`: contingency counts verified by brute force on a 200-person graph.

### 16.2 Golden-file (geometry)
Render `sample_family.ged` with each shipped preset → compare SVG to `tests/golden/*.svg`. Any diff fails the test and prints a side-by-side. Regenerate deliberately with `pytest --update-golden`.

### 16.3 Fabrication
- Islands: a fixture with 12 known enclosed regions must find exactly 12 and bridge all 12.
- Kerf: offset a 50 mm square by 0.2 mm kerf → measure 49.8 mm.
- Preflight: a deliberately broken plan must produce exactly the expected failure list.
- **Privacy**: render with `redact_living` and assert no living person's name or date appears **anywhere** in the output bytes, including comments and metadata.

### 16.4 Fixtures to generate
- `sample_family.ged` — 400 people, 8 generations, realistic UK names/dates/places, 15% missing data.
- `pathological.ged` — first-cousin marriage, double-cousin marriage, adoption, a person with 4 unions, a child born before their recorded father, 30% of people with no dates at all, one unicode-heavy name (`Ó Súilleabháin`), one 1723/24 dual date.
- `huge.ged` — 10,000 people, for performance tests.

### 16.5 Performance targets

| Operation | Target (10k people) |
|---|---|
| DB load + graph build | < 1.5 s |
| Full layout | < 800 ms |
| Plan → JSON → browser render | < 2 s |
| Contingency query (after dominator precompute) | < 5 ms |
| SVG export | < 3 s |
| Live re-layout on slider drag | debounced 150 ms, feels instant |

If layout exceeds target, profile before optimising. The likely hotspot is the relaxation pass — cap iterations and use numpy for the per-ring arrays.

---

## 17. Build phases

Each phase must end with something you can **look at**. This matters more than architectural purity.

### Phase 0 — Skeleton (half a day)
Repo structure, `pyproject.toml`, `helix init`, schema created, migrations runner, `pytest` green with one trivial test.
**Done when:** `helix init test.helix` produces a valid, empty database.

### Phase 1 — Data in, picture out (2–3 days) ★ **the motivating milestone**
GenDate parser · name model · repositories · GEDCOM 5.5.1 import · graph build · basic radial layout (generation mode, `leaves` weighting) · RenderPlan · SVG renderer.
**Done when:** `helix render --db sample.helix -o t.svg` produces a recognisable radial family tree with names, opened in a browser.
*Do not build the GUI before this works. Seeing the first circle appear is the thing that carries the project.*

### Phase 2 — The browser (3–4 days)
FastAPI server · `/api/plan` · canvas.js · zoom/pan · click-to-select · inspector (read-only) · search.
**Done when:** you can explore your tree on screen, click any person and read their facts.

### Phase 3 — Design control (3–4 days)
Token system · style resolution · rules engine · control panel · three presets · label templates and per-ring detail · chronological mode · equal-area scale · decade rings.
**Done when:** you can produce two visually distinct posters from the same data without touching code.

### Phase 4 — The Thread (2 days) ★
Ancestral cone · dominator tree · contingency · fade interaction · criticality colouring · Top-20 panel.
**Done when:** hovering an 18th-century ancestor fades 400 descendants and tells you the number.

### Phase 5 — Fabrication (4–5 days)
Layers · text→outlines (both outline and Hershey) · curved text baking · kerf · island detection · auto-bridging · preflight · materials · DXF export · clock module.
**Done when:** a preflight-clean SVG cuts correctly on card at half scale, first attempt.

### Phase 6 — Editing and research tools (4–5 days)
Inline editing · change log and undo · validation report · duplicate detection and merge · research tasks · gap ranking · statistics · GEDCOM export.
**Done when:** you can run the whole research workflow inside the app and never open a spreadsheet again.

### Phase 7 — Polish and production (3–4 days)
PDF poster · tiling · remaining presets · lifeline and hourglass modes · era bands · legend · cartouche · minimap · year scrubber · privacy modes · backups · docs.
**Done when:** you send a file to a laser and hang the result on a wall.

### Phase 8 — Optional
PyInstaller bundle · FamilySearch API sync · map view · animation export · companion booklet.

**Total realistic effort: 3–5 focused weeks.** Phases 1 and 5 carry the risk; everything else is assembly.

---

## 18. Extension roadmap — ideas beyond the brief

Ranked by (value ÷ effort). The starred ones are the ones worth building even if you build nothing else on this list.

1. ★ **Lifeline bars** (§7.2C) — each person's radial extent = their lifespan. Highest visual payoff of anything here.
2. ★ **Equal-area time scale** (§7.3) — makes chronological mode actually work.
3. ★ **Research gap ranking** (§12.4) — the chart tells you what to look for next.
4. ★ **Confidence-as-linework** (§5.6) — the artwork honestly shows what is proven.
5. ★ **Era bands** (§7.7) — puts your family inside history.
6. **Year scrubber / animation** — a hand sweeps the clock, births light up, deaths dim. Export MP4/GIF. The clock and the timeline become the same object.
7. **Companion booklet** — auto-generated PDF index keyed to numbers on the chart, so the engraving stays clean but every detail is available. Solves the "too much information, not enough room" problem completely.
8. **Numbered chart + QR** — a small QR in the cartouche linking to a local HTML export of the full database.
9. **Multi-layer relief** — cut each generation from a separate sheet and stack them. The tree becomes a physical topography, oldest at the bottom.
10. **Inlay mode** — the Thread cut through and inlaid with brass wire, contrasting veneer, or resin.
11. **Two-material sandwich** — dark acrylic engraved over a light backer, or the reverse.
12. **Map view** — places plotted with migration arcs. Toggle with the radial view.
13. **"Where were they in year X"** — snapshot view: everyone alive in 1881, with their residence from the census.
14. **DNA overlay** (§12.6) — colour segments of the chart by which DNA matches confirm them. Genuinely rare in hobby software.
15. **Occupation ribbons** — an outer annulus banded by occupation category, showing the family's economic story.
16. **Photo medallions** — small circular portrait cutouts for print mode.
17. **Braille layer** — names in Grade 1 braille as engraved dots. Trivial to add, and it makes the piece tactile.
18. **Half-charts and fans** — `sweep_deg=180` gives a mantelpiece fan; `sweep_deg=90` a corner piece.
19. **Gift mode** — re-centre The Thread on a different family member and re-export, so each relative gets their own version of the same data.
20. **Postcard/coaster export** — a per-branch mini-chart set.
21. **FamilySearch API sync** — free API, pulls from the world tree. Big data win, moderate effort, requires a developer key.
22. **Watch-face export** — the same layout at 40 mm for a smartwatch face. Silly. Do it anyway.
23. **Diff view** — compare two versions of the database and show what changed. Useful after a big import.
24. **Public HTML export** — a static, privacy-filtered, zoomable web version to share with relatives.
25. **Voice/interview capture** — attach recorded audio to a person, with transcript. The oldest relatives are the most perishable source you have (§19.1).

---

## 19. Research handbook — how to actually find the information

*(Extract this section into `docs/RESEARCH_HANDBOOK.md`.)*

Assumes a UK/Ireland starting point; international pointers at the end.

### 19.1 Do this first, before any website

**Interview the oldest people in your family now.** This is the only source that expires. Everything else will still be there next year.

- Record audio (phone is fine). Ask open questions: *"Tell me about your grandmother."* Not *"When was she born?"*
- Ask specifically about: full names including middle names, nicknames, maiden names, where people lived, occupations, siblings who died young (often omitted), family stories, and **who has the photos and papers**.
- Photograph every document and the **backs of photographs** — annotations there are gold.
- Home sources: birth/marriage/death certificates, family bibles, funeral cards, obituaries, war medals and service papers, wills, deeds, school reports, letters, address books, samplers, inscribed jewellery.
- Enter what you're told as `confidence = 1` with a `source` of type `interview`. Family memory is a lead, not a fact.

### 19.2 The method

Work **backwards**, one generation at a time, and prove each link before moving on. The universal beginner's mistake is jumping to a same-named person three generations back and building a tree onto the wrong family.

Follow the **Genealogical Proof Standard**:
1. Reasonably exhaustive search (not just the first hit).
2. Complete, specific source citations.
3. Analysis and correlation of the evidence.
4. Resolution of conflicting evidence.
5. A written conclusion — use the `citation.reasoning` field for this.

Keep a **research log**, including negative results. "Searched Walcot St Swithin baptisms 1800–1815, no John Smith" is valuable information that stops you repeating the search in 2029. That's what `research_task.result` is for.

### 19.3 England & Wales — the core stack

| Source | Covers | Where | Cost |
|---|---|---|---|
| **GRO index** (gro.gov.uk) | Births 1837–, deaths 1837– | GRO website, free account | Free to search |
| **GRO PDF certificates** | Full detail | same | ~£3–8 each — far cheaper than paper certificates |
| **FreeBMD** | Civil registration index 1837–~1990s | freebmd.org.uk | Free |
| **Census** | 1841, 51, 61, 71, 81, 91, 1901, 1911, 1921 | Ancestry / Findmypast / FamilySearch | Subscription (1921 is Findmypast) |
| **1939 Register** | Sept 1939 household schedule | Findmypast / Ancestry | Substitutes for the destroyed 1931 and never-taken 1941 census |
| **Parish registers** | Baptisms, marriages, burials from 1538 | FamilySearch (free), Ancestry, Findmypast, and **county record offices** | Mixed |
| **Probate Search** (gov.uk) | Wills & admons, England & Wales 1858– | probatesearch.service.gov.uk | Free index, ~£1.50 per will |
| **National Archives Discovery** | Everything else: military, merchant navy, prisons, apprenticeships | discovery.nationalarchives.gov.uk | Free catalogue |
| **British Newspaper Archive** | Obituaries, marriages, court reports, adverts | britishnewspaperarchive.co.uk | Subscription |
| **FamilySearch** | Vast global index + shared tree + digitised film | familysearch.org | **Free**, account required |
| **FreeREG / FreeCEN** | Volunteer parish & census transcriptions | freereg.org.uk / freecen.org.uk | Free |

**Two high-value tricks:**
- The GRO's **online birth index includes the mother's maiden name** — this lets you assemble complete sibling sets cheaply and confirm the right family before buying anything.
- The GRO **death index gives age at death from 1866**, and exact date of birth from 1969. An age lets you cross-check a baptism.

**County record offices** hold the original parish registers, manorial records, school admission registers, poor law and settlement examinations (the latter are extraordinarily detailed about ordinary people). Find yours via the National Archives' "Find an archive" tool. Somerset, Bath, Wiltshire and Gloucestershire records are held in separate offices, and boundary changes mean a parish may sit in an unexpected one — check the parish, not the modern county.

### 19.4 Scotland, Ireland, Wales

- **Scotland: ScotlandsPeople** (scotlandspeople.gov.uk) — pay-per-view, but the *best* system in the British Isles. Statutory registers from 1855 are extraordinarily detailed (marriage records name both sets of parents; death records name the deceased's parents). Old Parish Registers from 1553. Censuses 1841–1921.
- **Ireland:** **irishgenealogy.ie** (free civil registration and church records), **census.nationalarchives.ie** (free 1901 and 1911 census, complete), Griffith's Valuation and Tithe Applotment Books (free, standing in for the destroyed pre-1901 censuses), **RootsIreland** (parish records, subscription).
- **Wales** is covered by the England & Wales systems. Watch for patronymics persisting into the 1800s in the north and west, and the extreme surname concentration (a parish of Joneses needs occupation and place to disambiguate).

### 19.5 If the family emigrated

FamilySearch (US censuses 1790–1950, free), Ellis Island / Castle Garden (free), **Trove** (Australia, free newspapers), **Library and Archives Canada**, **Ancestry** for passenger lists, and country-specific archives. Search the *departure* records in UK sources too — outbound passenger lists 1890–1960 are on Findmypast.

### 19.6 DNA

For breaking brick walls once documents run out:
- **AncestryDNA** has the largest UK-matching database; **MyHeritage** is strong in continental Europe; **23andMe** is health-oriented with a weaker tree ecosystem; **FamilyTreeDNA** offers Y-DNA (direct paternal surname line) and mtDNA (direct maternal line).
- Upload your raw data free to **GEDmatch** and **FamilyTreeDNA** to fish in other ponds from one test.
- Learn to read **shared centimorgans**: the Shared cM Project tables give the plausible relationship range for any cM value. Ship these in `analysis/dna.py`.
- **Be prepared for surprises.** Roughly a few percent of documented paternal lines are not biological. Decide in advance how you will handle that, and treat other people's results as confidential.

### 19.7 Cost control

A workable budget path: FamilySearch + FreeBMD + FreeREG + Probate Search + TNA Discovery are all **free**. Add GRO PDF certificates at a few pounds each only when you need to prove a specific link. Buy a **one-month** Findmypast or Ancestry subscription and use it in a concentrated burst — make a shopping list of every census and record you need beforehand. Many UK public libraries offer free in-branch Ancestry and Findmypast access.

### 19.8 Feeding the results into Helix

- Create the `source` record **first**, then attach citations as you enter facts. It takes ten extra seconds and saves ten hours later.
- Paste the **full transcription** into `citation.transcript` — then you never need to re-open the image.
- Save record images into the `media/` folder next to the `.helix` file, named `surname-given-year-type.jpg`.
- Set `confidence` honestly. The chart will show you the difference, and the fuzzy areas *are* your research plan.

---

## 20. Data-entry conventions

*(Extract to `docs/DATA_ENTRY_RULES.md` — one page, pinned up.)*

1. Enter what the record says, not what you think it means. Corrections go in `notes`.
2. Dates: type them however you like; the parser handles `abt`, `bef`, `aft`, `bet…and`, `Q3 1871`, `1723/24`. If you're guessing, prefix with `est`.
3. Places: full hierarchy, period-correct — `Walcot, Bath, Somerset, England`, not `Bath`.
4. Women: birth surname primary, married name as a second name record.
5. Unknown people still get a record, with `is_placeholder = 1`.
6. Never delete. Mark `confidence = 0` and explain in notes. You may be wrong about being wrong.
7. One source record per document; one citation per fact.
8. Enter siblings even when they lead nowhere — they are how you confirm you have the right family, and they are how DNA matches connect.
9. Run `helix check` after every session and clear the errors while the context is fresh.
10. Back up. The app does it automatically; also keep a copy somewhere that is not your laptop.

---

## 21. Known-hard problems (read before you start)

| Risk | Mitigation |
|---|---|
| **The DAG problem.** Cousin marriage breaks tree assumptions everywhere. | `is_primary` edges + chords, from Phase 1. Retro-fitting this is painful. |
| **Label legibility at scale.** 1,800 names on a 600 mm disc gives each outer person ~1 mm of arc. | Be honest early: the legibility report and demotion policy exist to tell you the disc must be 900 mm, or the outer generations must be numbers keyed to a booklet. Decide the physical size **before** designing. |
| **Curved-text baking.** Placing glyph outlines along an arc with correct kerning is fiddly. | Golden-file tests from day one of Phase 5. Budget a full day. |
| **DXF spline fidelity.** Some laser software mangles splines. | Ship a flatten-to-polyline option and default it on. |
| **GEDCOM encoding.** ANSEL is a genuinely awful legacy encoding. | Sniff BOM + `CHAR` tag; ship an ANSEL→Unicode table; on failure, import as latin-1 and flag. Never refuse the file. |
| **Scope creep.** This spec describes a lot. | Phases 1–5 are the product. Everything in §18 is optional forever. |
| **Emotional weight.** You will find infant deaths, workhouses, and possibly a surprise in the DNA. | This is normal and it is part of the value. Take breaks. |

---

## Appendix A — Style preset briefs

Each preset ships as a JSON token file. Design intent, so the values are chosen rather than defaulted:

| Preset | Palette | Type | Connectors | Best material |
|---|---|---|---|---|
| **Labyrinth** | Ink `#1C1C1A`, bone `#F2EDE3`, one accent madder `#9B3A2E` | Grotesque caps for surnames, humanist lowercase for given names | Orthogonal-in-polar, 1.5 mm radiused corners | Birch ply |
| **Circuit** | Board green `#0B3D2E`, solder `#C9C9C4`, trace gold `#C9A227` | Monospace, tracked wide, all caps | 45° chamfers, square pads at each person | Black acrylic / anodised alu |
| **Heirloom** | Walnut `#3B2A1E`, cream `#EDE4D3`, oxblood `#6B2020` | Small-caps surnames, old-style figures, engraved hairline rules | Fine tapering curves | Walnut veneer, brass |
| **Nordic** | Two values only: `#111` on `#FFFDF8` | Single geometric sans, one weight, generous tracking | Straight radial spokes, no cells at all — people are 1.2 mm dots | Pale ply, white acrylic |
| **Botanical** | Bark `#4A3B2A`, moss `#5E6B4F`, bloom `#B7746B` | Italic given names, roman surnames | Organic cubics thickening toward the centre; leaf terminals for the living | Cherry, maple |
| **Blueprint** | Cyan `#0F4C81` ground, white line, red revisions | Technical stencil face, dimension lines and leaders throughout | Straight with arrowheads and callouts | Print, or blue anodised |

**One rule across all presets:** spend boldness in exactly one place. The Thread is that place. Everything else stays quiet.

---

## Appendix B — Glossary

**Sosa-Stradonitz (Ahnentafel)** — ancestor numbering: subject 1, father 2n, mother 2n+1. **d'Aboville / Henry** — descendant numbering. **Pedigree collapse** — the same ancestor appearing via multiple lines. **Endogamy** — sustained intermarriage within a community, causing widespread collapse. **MRCA** — most recent common ancestor. **cM (centimorgan)** — unit of shared DNA. **Banns** — public notice of intended marriage, read for three Sundays. **Admon** — letters of administration, granted where there was no will. **Settlement examination** — a poor-law interrogation recording a person's whole life history; the richest source for working-class ancestors. **Bastardy bond** — a parish record naming a putative father. **OPR** — Scotland's Old Parish Registers. **Dual dating** — the 1752 calendar change, when the English legal year began on 25 March.

---

## Appendix C — Decisions already made (do not re-litigate)

1. Browser SPA with no build step, not a native GUI. *(§3)*
2. Render Plan as the single geometry source of truth. *(§7.1)*
3. GEDCOM-style union model, not direct parent links. *(§5.1)*
4. Events, not date columns. *(§5.1)*
5. GenDate is an interval type, never a `date`. *(§5.3)*
6. Chronological + equal-area is the default layout. *(§7.3)*
7. The Thread is a first-class feature, not a colour option. *(§11)*
8. Text is always outlined for fabrication. *(§10.2)*
9. Island detection runs on every export. *(§10.4)*
10. SQLite, one file, always backed up. *(§5.8)*

---

*End of specification. Build Phase 0 and Phase 1 first, then come back.*
