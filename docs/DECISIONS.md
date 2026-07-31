# Why the program is the way it is

The record of decisions taken, faults found and measurements made. It lives
here rather than in the source so that the code can be read for what it
does, and this can be read for why.

Every measurement below was taken on real files: a 142-person tree of seven
generations, a 463-person generated one, and the 461-person sample. The
files themselves are not in the repository.

---

## Storage and safety

**There is no Save button, and there never will be.** Every write commits
immediately, so there is no unsaved state to lose. A dated backup is taken
once a day and before anything destructive, thirty are kept, and
`helix archive` writes a zip holding the database, a plain JSON dump, CSV
tables and the current renders. The JSON is the long-term guarantee.

**Never SQL-DELETE a person.** `records.retire()` marks them inactive and
takes their links off. Undo of a person's creation does the same rather
than deleting the row.

**Family files are ordinary files in a visible folder** — `Documents/Helix`,
not Application Support and not AppData. Somebody who has kept a tree for
ten years needs to be able to find it, copy it and hand it on. Only the
preference (which folder, which file was last open) is hidden.

**A WAL database cannot be renamed out from under its own log.** Moving the
`.helix` without its `-wal` leaves committed writes stranded: the next open
reports "disk I/O error". `library.rename` checkpoints first and moves all
three files together.

**`settings` is `(k, v)`, not `(key, value)`.** Read the wrong way the query
threw every time and silently fell back to the file name, so the library
listed every family under its file rather than under itself.

---

## Dates

**`GenDate` is an interval, never a date.** Ages are `AgeRange`, never
`int`. Comparisons are between intervals, not midpoints.

**`GenDate.year` returns the year the date is IN**, not a rounded midpoint.
11 August 1967 has a sort value of 1967.6 and rounded to 1968 — so somebody
appeared as "1968–" under a name whose profile said 11 Aug 1967 two lines
below, and on every chart drawn since dates went on them. An interval that
spans a year boundary has no single year, and there the midpoint is the only
honest answer.

**Unparseable dates are kept verbatim** with `kind='unknown'` and the
original string intact. That has to hold through an export as well as a
save, which is why GEDCOM gets `_ORIG` beside its `DATE`.

---

## Layout

### The couple grid

One angular cell per COUPLE, partners stacked radially inside the ring band.
That is what lets the chart say, without a legend, who is married to whom,
which children are whose, and who is a cousin of whom.
`docs/KNOWN_ISSUE_LAYOUT.md` has the reasoning and the measurements;
`subject_grid.py` is the older one-slot-per-person layout and its three
limits are recorded there too.

**A married-in spouse gets a person-sized slot**, not half their partner's
lineage. Weighted by lineage they pushed couples 160° apart.

**`_auto_apexes` must exclude people who married in.** "Everyone with no
known parents" includes every spouse, which gave 130 root sectors and an
unreadable chart.

**Children attach to a UNION, never to a parent.** This is what makes
half-siblings, remarriage and adoption work instead of being special cases.
A child of a second marriage listed under the first parent appeared to be a
full sibling of both — three couples on one 142-person file.

### The ordering pass

Coordinate descent over the free choices ("hinges"), cost = (crossings,
reach). Twenty-five random restarts on a 142-person file all began between 9
and 11 crossings and all converged to exactly (4, 30.39), which is that
file's structural floor rather than a failure of the search.

**Narrowing genuinely re-lays-out**, and the crossings fall as the tree
simplifies: 4 → 3 with no cousins → 2 with no removals.

Faults the search fixed, each of which had been patched specifically before
being solved generally:

* a child bracket anchored to an arbitrary partner ran inward across three
  families and ended in mid-air when a couple straddled rings
* the cost model counted one stem per cell rather than one per marriage, so
  remarriage crossings were invisible to it
* `pick_hinges` required `0 <= c.over`, which excluded exactly the couples
  whose children are drawn elsewhere

### Names on the chart

**Tangential by default, tops pointing inward.** For text set along a ring
the two words mean the opposite of what they sound like: rotating text by
*r* sends the tops of its letters toward *r−90*, so `outward` points them
away from the centre — and at the bottom of the disc that is downward. The
newest generations were the half printed upside down. `inward` puts the
bottom half the right way up, and the chart is turned once to read the top.

**Whole names, by wrapping or by lengthening the branch.** Wrapping a name
across two lines cuts its width by about 40%, which is far more powerful on
a crowded ring than growing the radius. Where that is not enough the
marriage branch is lifted, capped by the room actually available above the
cell's own label rather than the ring maximum.

**The demotion ladder ends at the given name, not at initials.** A name
needing 21.8 mm with 23.6 available can lose its slot to a longer neighbour
by half a millimetre; the given name alone fits with room to spare, and the
surname is the one thing a family tree never has to repeat because it is
written on the branch.

**Turning a tangential name to radial as a last resort does not work**,
though it looks as though it should. It keeps more names — abbreviated ones
fell from three to one — but a radial name runs outward from its row and the
first thing it meets is the rule that means that person is married.

Tangential costs a name its full width in angle instead of its height. On a
142-person file that is free (136 of 136 whole names); on 463 people at five
generations it demotes 12 and drops 1.

### Arcs and paths

**Arcs must take the short way round.** `geometry.short_arc` for any tie
between two people: `arc_path` follows `t1 − t0`, so a couple either side of
the start angle had their marriage drawn across the disc.

**Emit absolute SVG path commands.** A relative circle once flattened into
geometry hundreds of millimetres off the sheet — in the CAD exports only,
because browsers read it correctly.

---

## The ancestry half

**One module decides what a cousin is**: `graph/kinship.py`. Seven features
read it. Written out twice they drift, and somebody appears under "first
cousins" and vanishes when you allow first cousins.

**Narrowing happens BEFORE the grid is built**, never after. Hiding a branch
afterwards leaves the chart arranged around a family that is no longer on
it.

**A narrowed chart says what it left off.** You cannot tell a family of two
from a family of nine you narrowed down, so every marriage that lost
children carries a pruned-branch mark with the number.

**"Look for the ⊥ marks" is not an instruction anybody can follow.** At the
zoom where a whole chart fits on a screen those marks are two pixels long.
The readout now has a button that makes the chart point at them.

**Shared DNA is `0.5 ** steps`, doubled when both members of the couple at
the top are shared.** That doubling is the whole difference between a full
relation and a half one, and it is why the number cannot be read off the
label: a full aunt and a half-uncle are both filed under "aunts and uncles"
and they are 25% and 12.5%.

**The percentage keeps two decimals and rounds half up.** Every value is
`2^-n` or twice it, so one decimal turns the exact 6.25 of a
half-first-cousin into "6.2", and Python's default half-to-even makes 3.125
into "3.12" when every printed cousin table says 3.13.

**Heritage is never written to a row.** A computed share goes stale the day
a great-grandparent is added, so it is derived on every read from the
declarations only. A person's own declaration beats what they would inherit.
The unaccounted-for remainder is named rather than hidden: "62% Irish" alone
reads as a rounding error, "62% Irish, 38% not recorded" reads as research
still to do.

**Empty seats in the bloodline are drawn, not skipped**, and only the
frontier counts toward the missing percentage. Four unknown
great-grandparents behind two unknown grandparents are the same missing half
counted twice — which once made a half-recorded ancestry read as 100%
unknown.

**Research gaps are computed on every read**, not stored in `research_task`.
Those rows are for what somebody has decided to chase; this list is derived
from the state of the file, so a gap that gets filled leaves it the same
second.

---

## Import and export

**The writer came first.** A format you can only read is a trap with a
welcome mat.

**The encoding is sniffed, never trusted.** `CHAR ANSEL` is a lie more often
than not; `CHAR ANSI` has always meant Windows-1252 and never the ANSI
standard. ANSEL puts its combining marks BEFORE the letter, so read naively
"José" arrives as "Jos´e" and every accented name in the file is quietly
wrong.

**CONT is a newline, CONC is a join with no space.** Swapped, a two-line
note comes back as one line and a long name gains a space in the middle.

**An import is one `Edit`**, so one Ctrl-Z takes back the largest change
anybody will ever make to their file.

**Nothing is refused and nothing is silently dropped.** A FAM with no HUSB,
a child listed twice, a pointer at nobody, a person with no NAME, a level
that jumps — all ordinary in real files. Cyclic pedigrees are detected and
reported rather than followed forever. Unmodelled tags go into
`person.notes` prefixed `[GEDCOM]`.

**The round trip is exact**: 463 people and 67 families out and back compare
identical as multisets — every name, sex, date, place, occupation and
family.

**Duplicate detection needs negative evidence as much as positive.** Name
similarity alone produced 58 false pairs on a 463-person file. Adding two
rules — different middle names, and two recorded deaths that disagree — cut
that to 3 without losing a single real duplicate.

**Two people with one parent and different birth years are brothers, not one
person written twice.** Children were often named for the same grandfather,
and a name was reused when the first child died.

---

## The interface

**The window opens on `radial_family`.** It opened on `radial_rings` for a
long time, so the flagship — the design every layout document describes, and
the only one that draws the pruned-branch marks — was something you had to
go and find.

**The view is refitted whenever the stage changes size.** The stage loses
330px the moment a profile opens; fitted once at start-up and never again,
the chart spent most of a session with a third of the family off the
right-hand edge, under the very panel that had just opened to tell you about
somebody. One wheel click or one drag and the view is the person's, and
refitting stops.

**A highlight rule must not set `fill` on linework.** The chart's paths are
drawn with `fill:none` and mean it; one rule setting both turned the whole
disc into a solid red shape.

**A printed profile is what you file.** It carries what is known and nothing
else. A research to-do list printed onto it is stale within a week and reads
as a reproach for the rest of its life; the questions print on their own
sheet.

**An absent field is not an empty one.** A request that never mentions a key
means "leave this alone"; an empty string means "clear it". Read the same
way, saving a birthplace wiped the birth date beside it.

**The word "union" must never reach the screen.** It is right for the schema
and wrong for someone adding their aunt.

---

## Traps in the plumbing

**The server threads every request.** A SQLite connection made on the main
thread cannot be used from a request thread. It is opened with
`check_same_thread=False` and all access goes through `ST.lock`. Test new
endpoints against a running server, not as function calls — that is how this
one hid.

**Every migration runs on every open**, not just the ones above the recorded
version, and each must therefore be safe to run twice. `schema.sql` is the
version 1 schema and is never edited.

**macOS launches a bundle with `-psn_0_12345`** — a process serial number,
not a path — when you double-click a document. argparse refuses to start
over it.

**PyInstaller cannot cross-compile.** A Windows `.exe` has to be built on
Windows and a `.app` on a Mac, which is why the release workflow builds on
three runners.

---

## Measurement, not inspection

A passing test suite says nothing about whether a chart looks right. Every
layout fault in this program survived one. `tools/ink_check.py` runs seven
checks that a structural test cannot — touching arcs, the long way round,
text on a line, lines crossing, loose ends, a marriage above the siblings,
and a relationship that is not drawn at all — and the answer to all seven
should be zero.
