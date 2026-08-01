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

---

## The root person is the whole document

Every relation in the program is measured from one person: who counts as a
cousin, whose lines are worth researching, what the chart puts at its
centre, what the record book calls each entry. So changing the root is not
setting a preference — it is a different document about the same family.

**Nobody is told to research an in-law's parents.** A person who married
into the family is at every gathering and is not somebody whose parents you
are chasing; their line is a different family's line, real and somebody
else's. Asked for anyway, the research panel filled with "who were her
mother's parents?" about surnames nobody in the family carries, and the
questions that mattered were pushed off the end. Move the root to a
grandchild and the same woman is a grandmother, her line is the direct line,
and her parents become the first question on the list — with no setting to
find and nothing to switch on.

**`library.copy_for` is the other half of that idea.** A niece who wants her
own tree gets a FILE OF HER OWN: the original is not touched, not linked to,
and never consulted again, so she can add her mother's family, delete a
branch, get the dates wrong, and none of it reaches back. Pruning is offered
rather than done, by name and with a count — "Michaela Denton's own family,
3 people" is a decision somebody can make; "leave out 34 people" is a number
nobody can check. What is left out is retired, never deleted, so one Ctrl-Z
in the new file brings it back.

Branches are found by walking parents, children AND partners until the lump
stops. Grouped by ancestry alone, a woman and her own brother came out as
two separate branches, which is two questions about one family and the wrong
two.

## Married, or not

Two people with a child between them are a family whether or not they ever
married, and a program that only knows how to say "married" tells a small
lie about them on every screen it has — including the printed record, which
is the one document in the house somebody will still be quoting in thirty
years. The kind lives on the union, and every place that puts it into words
asks `graph.build.union_word` rather than assuming.

**Never married is not divorced.** A couple who married and later divorced
were married: the marriage is a fact with a date and it stays on the record.
A divorce is an EVENT on the union, not a kind of union, which is why the
enum has no entry for it.

**On the chart it is the same tie with a break struck through the middle**,
at a slant no other mark uses. It reads the way a break in a line always
reads, and it survives being cut in wood at a millimetre and a half — which
a dashed line does not, because the dashes fall between the laser's steps
and come out as a solid line or as nothing. The key explains it only on a
chart that has one.

**Adding a partner still means a marriage.** A couple who never married is
said so deliberately; guessing it from silence would be a claim about two
real people made by a default.

## Brothers and sisters with no parents in the file

"My father had a brother" is a thing somebody types on their first evening,
long before they know either grandparent's name. It makes a family with two
children in it and nobody in the parents' row — honest, and invisible to a
kinship walk that goes from person to person, because there is no person
there to walk through. The uncle came out as "no known relation" and a chart
narrowed to blood relatives left him off; worse, `copy_for` offered to prune
him.

The union itself is the shared ancestor: it stands exactly where the unnamed
couple stands, so two children of it are (1, 1) — brother and sister — and
everything downstream follows. Applied ONLY where the union has no partners
in the file; with a parent present the ordinary pass has already measured
everybody through them, and measuring twice is how two answers start to
disagree.

## A face over a lifetime

Somebody at twenty and the same person at eighty are two photographs of one
person, and replacing the first with the second throws away half of what a
family album is for. Setting a new portrait demotes the old rather than
deleting it, and the earlier ones stay in order with the age they were in
each.

The date box takes a year, a date, or an age, and keeps whatever was typed
(rule five). Given a year it works out the age; given an age it works out
the year; given "the summer before he went out to Kenya" it keeps that,
because a family that knows only that has still said something worth
keeping.

## One page per person in the record book

A binder is filed, added to and pulled apart: somebody wants the page for
their grandmother, and if two other people are on the back of it they cannot
have it. So every entry starts a page, and a life with a great deal written
about it runs on to a second and a third rather than being cut to fit. The
foot of each sheet carries the title and the entry number, so a page that
has come loose can be put back.

## The gallery shows the designs, not pictures of them

There were eleven hand-drawn icons for twenty designs, so nine showed a
sunburst whatever they actually drew, and two more had drifted from the
geometry they were meant to illustrate. A thumbnail is now the design itself,
run on your own family, cropped to its ink by `pathflatten` — the same
geometry the DXF export gets, not a guess at where a path goes. It answers
the question somebody is really asking: not "what is an icicle plot" but
"what does MY family look like as one".

**Six of the twenty were never built.** They were registered so the gallery
could show them "greyed out with a clear note", and nothing ever greyed them
out — so a third of the gallery was pictures you could click to get an
error. A design now says for itself whether it is finished
(`DesignInfo.built`), and the six are listed as plans, at the end, and cannot
be picked.

## A phone is where a family history gets looked at

Standing in a churchyard; sitting with an aunt who has the photograph you
need. Nothing is removed at 380 pixels, it is FOLDED: the two sidebars slide
over the chart, the header's tools fold into one menu, the profile becomes a
sheet. Same DOM, same ids, one set of handlers — a phone version would drift.

Pinch and drag come off the same pointer events, and `touch-action: none` on
the canvas is what lets a finger drag the chart instead of scrolling the page
underneath it.

## Nothing in the browser is compiled until it runs

Python fails a test somewhere the moment a module has a typo in it. The
front-end modules are not read by anything in the test suite, so a syntax
error in one sails through a completely green run and then takes the WHOLE
interface down — every module, because one that fails to parse stops the
import graph. A regular expression written across two lines with Python's
`/x` flag on the end did exactly that, and the window came up as an empty
grey rectangle with a working header. `tests/test_web.py` parses every module
with node.

## Nobody dies before their own children are born

The sample generator drew a death age when it made each person, which is
before it knows whether they went on to have a family: eighty people in a
four-hundred-person file died before their own children were born, one of
them a man dead at two with five sons. Deaths are now settled after the
pedigree is built, against every event the person takes part in. A father may
leave a child born after him and a mother may not, which is the one place the
rule genuinely differs by sex.

`graph/validate.py` gained the check that would have caught it, because it is
also the commonest way two families get joined by mistake: two men of the
same name in the same parish, and the children of the younger hung on the
father of the elder.

## What an official record is

The record book is the thing that goes in a ring binder and is read by
somebody in thirty years who never met anybody in it. Four decisions follow
from that and only from that.

**It is not ordered from the root person.** Closest-first is right for a
sidebar, where the question is "where is my sister", and wrong for a folder
that outlives the person who made it: whoever it was centred on stops being
the obvious place to start the moment somebody else picks it up, and it puts
a man on page 40 with his own children on pages 3 and 91. So it reads the
way a printed genealogy has always read — the earliest people first, each
followed by their husband or wife, then their children, each child followed
immediately by that child's own descendants. The page after somebody is
nearly always a page about somebody they knew.

**Every field is present whether or not it is filled in.** A blank on a
filed record is ambiguous forever: nobody can tell an unknown birthplace
from one where the person filling it in got bored. "Unknown" is a statement
about the research, and it is the only thing on the page that says where the
work still is.

**No bracketed numbers beside names.** They were there so the binder could
be followed without the program that made it, and they made every page read
like a database dump — "Reuben Ashworth [2], Winifred Threlfall [3]" is not
how anybody writes about their family. The contents and the index are where
numbers belong; a name in a sentence is a name. Each name still carries its
dates, which is what actually tells two Alice Whitcombes apart.

**And no "your uncle".** Every relation in the program is measured from one
person, and in thirty years nobody reading the folder is that person. The
relations that belong on a record are the ones stated outright — Father,
Mother, Married, Children — and they are all there.

Every entry starts a page, the first one included: it used to run on from
the bottom of the contents, which put one person on a page that is not
theirs and made the contents look like the start of the record.

## A pruned branch is gone from the copy, not hidden in it

Rule seven says never SQL-DELETE a person, and its reason is that a wrong
ancestor removed at midnight has to still be there in the morning. That
reason does not reach `copy_for`: the ORIGINAL FILE IS UNTOUCHED and still
holds every one of those people with everything ever known about them.
Nothing is at risk.

What is at risk the other way is the new file. A document that quietly
carries a hundred inactive rows for a family it was deliberately not about
is not a clean file — it is the same file with a flag set. It would export
them to GEDCOM, count them in a status line, and offer them all back on the
first Ctrl-Z somebody pressed. `person` is the target of ON DELETE CASCADE
from every link table, so one delete takes the names, events, photographs,
tags and heritage with it; families and events left with nobody in them go
after.

The copy's `change_log` is cleared for the same reason. Inherited, the first
Ctrl-Z in Alice's file would undo something her uncle did in his.

## A whole date, typed the way it is written

Somebody copying off a birth certificate types what is printed on it, and
what is printed on it is "Friday, 1st March 1900" or "March 12, 1880" — not
"1900-03-01". Refused, they shrug and type the year, and a day and a month
that somebody had in front of them are lost for good.

So the phrase is tidied before any pattern is tried: weekday names, ordinal
suffixes, "of", commas, and a month or year written first. Nothing is
INTERPRETED there — no guessing at ambiguous numbers, no inventing a month.
It removes the wording a person puts round a date and leaves the date.

`c. 1834` is how it is written in every parish transcript there is, and the
full stop alone was enough to make it unparseable.

Double dating keeps its day: "24 Feb 1723/24" is February 1723 by the old
English year, which began on 25 March, and 1724 by ours. It used to display
as "1723/24", throwing away the most precise thing anybody had written down.

## Two kinds of paper about the same person

An OFFICIAL RECORD is filed and read in thirty years by somebody who never
met anybody in it. It states what is known, marks what is not, and carries
nothing that is arithmetic over today's file.

A PROFILE is everything on screen: how they stand to you, the DNA
percentages, where the family came from, the small bloodline tree, what is
still to find out. That is working material — it changes the moment a
grandparent is added, and it is exactly what somebody wants when they are
researching rather than filing.

Both are wanted and they are not the same document, so the Print screen
offers both and the buttons say which is which. The same split runs through
the rest of it: *This person* — the record, or the profile. *Everyone* — the
record book, or every profile, each for the chart's cast or the whole file.
*The family tree* — the chart itself, the outline, the chronicle, the
research list.

**Printing the chart is not Export → SVG.** The export writes the millimetre
geometry a laser cutter needs. Printing writes the picture on A4 with a
caption under it — the family's name, how many people, the years it covers,
the date it was printed — which is what somebody means by "print the tree":
to put on a wall, take to an aunt, or check against a parish register with
a pencil. The page turns landscape by itself when the chart is wider than
it is tall.

**"Uncle" is the label and not the whole answer.** Somebody looking at a
name they do not recognise wants to know WHICH uncle, so the profile says
the way through — "through Peter Whitcombe" — read off the same path the
Relate screen draws, so the two can never disagree. It never appears on a
record, where "your" means nothing.

Drawing that path turned up a gap left over from the parentless-family fix:
`Kinship` could MEASURE two people whose shared parents are not in the file,
and `relate` could not draw the way between them, because there is no person
standing where the shared ancestor stands. The path now names the family
itself — "Their parents, not recorded" — since no path at all would read as
no relation.

## What a historian needs and a chart cannot hold

Four sections separate a pretty page about somebody from a record another
researcher can WORK from. Each answers a question that gets asked of every
ancestor, and all four were already in the schema and unused.

**Also recorded as.** An index is filed under the spelling the clerk wrote,
and a Whitcombe is a Whitcomb, a Whitcome and a Witcombe in four different
registers. A researcher who does not know that searches once and concludes
the family was not there. `person_name` has carried married names, aliases
and as-recorded spellings from the beginning.

**Places and dates.** The movement of a family is half of its history, and
it is what places the next record: the parish you search in 1861 is not the
one you search in 1841. One chronological table of every event that has a
place — birth, baptism, census, residence, marriage, death, burial — with
what the record said. An entry with no date is NOT given "Unknown" in the
date column; a chronological table with a blank where the year goes cannot
be read down, so those come after it, said plainly. Anything with no place
at all is still listed, under "other records".

**Line of descent.** From the earliest person the file knows down to them,
following the surname where there is one. Root-free — reckoned from the
oldest ancestor rather than from whoever the program is centred on — which
is exactly why it belongs on a record and "your uncle" does not. It is also
the one thing a bloodline historian is holding the folder to find out.

**Where this came from.** The line between research and hearsay. A date with
no source is a rumour somebody typed carefully, and a record that does not
say where it got something cannot be checked, corrected or built on. One
entry per SOURCE rather than per citation — the parish register cited for a
baptism, a marriage and a burial is one book, and listing it three times
turns a bibliography into a log. Where there is nothing, the record says so
and says why.

Two things had to be deduplicated to make this readable. The same christening
imported from two GEDCOMs puts the same line on the page twice, and a record
that says a thing twice reads as two findings. And a page reference already
inside its source's own reference — "RG 9/1652 f.71 p.12 · f.71 p.12" — is
the same reference said twice.

**A marriage with no date does not print "Date: Unknown".** Everywhere else
on the record an empty field is filled in, because a blank where a
birthplace goes is ambiguous forever. A marriage is different: the marriage
itself is the fact, it is stated, and three rows of "Unknown" beneath it say
nothing except that the page is padded. Where the date IS known it carries
how old they were, which is the first thing anybody checks a marriage record
against.

## One field, several people

The point at which somebody stops using the program and opens the database.
A census page gives forty people the same parish; a transcription gives a
whole branch the same misspelt surname. One at a time that is forty
dialogues and forty undo steps, thirty-nine of which leave the file half
corrected.

`records.bulk_edit` is one `Edit`, so the whole change is one entry in the
history and **one Ctrl-Z takes all of it back**. The list of fields it
accepts is deliberately short and refuses everything else by name: a
surname, a place, an occupation, a confidence, a tag — the things that can
sensibly be true of a whole branch at once. A birth date is a fact about one
person and setting it on forty is always wrong, so asking for it gets an
error that lists what CAN be set instead.

It lives in the list of names, not in a menu of its own, because the useful
sequence is already there: filter to "whitcombe", tick what the filter
found, set the place once. Only what the filter is SHOWING can be ticked in
one press — somebody in a closed tab being changed invisibly is how a bulk
edit becomes a thing people are afraid of.

Tags needed adding to `KEYS` to make this work, and finding that out was the
point. A tag was the one thing in the program that could be added and not
taken back: written outside `Edit` it left no `change_log` row, so Ctrl-Z
stepped over it and undid whatever came before instead.

## "Imported 463 people" is not a report

It is a number, and it is the one thing nobody can check. Four hundred and
sixty-three could equally be the wrong file. What somebody wants to know
after an import is which surnames arrived, what years they cover, and — the
only part that needs a decision — which of the new people have nobody above
them, because those are where the two trees have to be joined by hand.

`records.what_changed` reads it back out of `change_log` rather than
counting a second time on the way in. The record system is already the only
thing that writes, so the report cannot drift from what happened, and a
batch is exactly the unit one Ctrl-Z takes back.

Counting `person` rows alone was wrong and looked right. A birthplace is an
event — rule 4, there is no `birth_place` column on `person` — so correcting
forty birthplaces reported "0 people changed". Every table that can be
traced back to somebody is traced, and `event` is traced through
`event_role`, which is also how one marriage correctly reports as two
people.

**Importing into an empty file drew an empty chart.** Every relation is
measured from one person, so with nobody at the centre there is nothing to
draw — and the screen said nothing about why. The report now asks who the
root is, from the list of people that have just arrived. Asked, not guessed:
which document this is is not a preference.

## How much paper, before the button

"Print the record book" on a four-hundred-person file is four hundred sheets
and most of a cartridge, and the only warning was the printer starting.

**A floor, and it says it is one.** Where a paragraph breaks depends on the
browser, the font the machine has and the paper chosen in the print
dialogue. Measuring the page on screen does not help either: `@media screen`
lays it out at a different width with different padding, and the count came
out ten per cent wrong — which, presented as a number, is worse than no
number at all. What IS certain is structural, and it is the part that
matters: `.entry{page-break-before:always}` means one sheet per person
whatever else happens.

Measuring it turned up a real defect. A perfectly ordinary entry — nothing
unusual recorded — came out 283mm against a 265mm page and took two sheets,
the second nearly empty; sixty people printed as 120 sheets. Seven section
headings at 5mm above and 1.5mm below is 87mm of a page spent on labels and
the air around them, and a millimetre above and below each of two dozen fact
rows is another forty. Tightened to 3.5mm and 0.55mm, an entry is 249mm and
"one page per person" is true again for anybody without a great deal
recorded: sixty people is now 74 sheets, and the ones that run on are the
ones that should.

## Cropping a photograph without cropping it

The one photograph of somebody's grandmother is usually a group at a
wedding. Cropping it to her face by writing new pixels destroys the only
copy of everybody else at it, and nothing undoes that — the bytes are gone.
It would also mean an image library, which the program does not have.

So a crop is four fractions on the `media` row, and the frame shows that
rectangle: `background-size:100/w` and `background-position:x/(1-w)`, which
is the one identity that slides and scales an image to an arbitrary
rectangle. `object-fit` cannot do it, which is why the portrait is a div and
not an `<img>` in all four places it appears.

Those four places have to agree. The frame in the profile, the avatar in the
sidebar, the printed profile and the record book all build the same style
from the same fractions, and the two implementations — `cropStyle` in
`profile.js` and `crop_style` in `dossier.py` — are pinned to each other by
a test. They disagreed once already: the JavaScript used double quotes
inside `url()` and the HTML attribute they were interpolated into closed on
the first one, so the interface frame was blank while the printed sheet was
right. A difference nobody would think to check.

`print-color-adjust:exact` is what stops a browser dropping the background
as decoration and taking the face off every sheet in the binder.

## Three things a passing test suite could not see

Six hundred and twenty tests were green, `bootstrap.py` printed Ready, and
the program could not be used. Every one of these was found by opening it in
a browser and doing what somebody would do.

**Nobody could click anyone on the chart.** `zoom.js` took
`setPointerCapture` on pointerdown so that a drag which leaves the window
keeps panning. Pointer capture also retargets the `click` the browser
synthesises at the end of the gesture — so every click on a name arrived at
the wrapper, the per-name handlers never ran, and selecting a person, which
is the whole interaction with a family tree, did nothing at all. Capture is
now deferred until the pointer has moved four pixels: under that it is a
click and the name gets it, over it it is a drag and the capture is taken
then. Pan, wheel-zoom, pinch and click were all measured afterwards.

**The header did not fit, and said nothing.** Twelve tool buttons, a search
box, the mode switch and Export need about 1480px; on a 1440px laptop every
flex child shrank to make room. The Explore/Build control — the switch
between reading a family and building one — collapsed to two pixels with its
labels spilling over the search box, so it was both invisible and
unclickable, and Export hung off the right-hand edge. Nothing shrinks now;
the tools wrap to a second row.

**The panel's close × sat on top of the ✎ that opens the editor**, so
clicking to edit somebody closed their panel instead. Room for the × is
reserved rather than fought over.

`tools/walkthrough-read.mjs` and `walkthrough-edit.mjs` are what found them:
71 checks over every screen, every dialogue, every export and every editing
path, driven in a real browser. They are not part of `pytest` — they need a
browser and the program has no dependencies — and they are the answer to the
oldest rule in this repository, that a structural check cannot tell you a
chart looks right.

## The first chart anybody sees

Everybody starts with one person, so the one-person chart is the most-viewed
chart this program will ever draw, and it was a mess.

**The key was printed over the names.** On a full disc the key goes in the
hole in the middle, where there is room and where the cut line reaches it.
With four people the hole is where the people are — the whole chart is hole —
and four lines of explanation landed on top of them. It now goes in the hole
only if it FITS in the hole, otherwise the bottom-left corner if that is
clear of names, otherwise a strip below the chart with the sheet grown to
hold it. Which of the three is decided by measuring, not assumed.

**And it explained marks that were not there.** A sibling arc on a chart
with no siblings is a note about something not on it. Every row is now
checked against the plan that was just built — which for one person leaves
no rows, and no key.

**One ring grew to 963mm to hold a 3.4mm name.** Growing the rings to fill
the sheet is right and is what makes a chart use the wood it is cut from —
until the result stops being a chart. The search found a twelve-degree
sliver with a ring band fifty-four times deeper than its contents and
reported a perfect fit, because it did fill the sheet. Capped at twelve
times, which is measured: the real charts here run from 1.0x to 8.1x.

**"1 people · 1 generations"** is what a template gets you, and the first
chart has exactly one of each.

**The first thing anybody does left the window half updated.** Adding
yourself called `refresh()` alone, so the sidebar said "0 of 0 people on the
chart" beside a chart with you on it.

## The one place with unsaved state

The Build panel had a **Save** button. Type a birthplace, click anywhere
else, and it was gone — in a program whose first rule is that every write
commits immediately and whose documentation says there is no unsaved state.
Each box now writes itself when you leave it, one field per request so that
saving a birthplace cannot wipe the birth date beside it.

## PDF, DXF and EPS were reachable only from a terminal

The three renderers are hand-written, have worked since the first release,
and were not on the Export screen — which offered SVG and stopped. Somebody
who installed the application and wanted a DXF for their laser had to go and
find a command line, which is the one thing this program is not supposed to
ask anybody to do.
