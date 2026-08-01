# Keeping a family, not just drawing one

Helix began as a way to lay a family out and cut it into wood. This is the
other half: somewhere to put what you know about the people on it, and to
read the file rather than only render it.

Seven features, and every one of them reads the same measurement
underneath: the relatives sidebar, narrowing a chart by relation, the
profile, the highlighting, where a family came from, how much blood two
people share, and what is worth going and looking up next.

---

## The keystone: `helix/graph/kinship.py`

`FamilyGraph.relationship` has always answered "how are we related?" in
English — *second cousin once removed* — and English is exactly what you
cannot sort, group, filter or count with.

`kinship.py` answers it with structure. Every blood tie is one fact: the
nearest ancestor two people share, and how many steps each stands below it.

```
up    steps from ME up to that shared ancestor
down  steps from that ancestor down to THEM

(1, 1)  both one step below a shared parent ....  brother or sister
(2, 1)  their parent is my grandparent .........  aunt or uncle
(2, 2)  our grandparents are the same ..........  first cousin
(3, 2)  ........................................  first cousin once removed
```

The cousin **degree** is one less than the smaller of the two; the
**removal** is the difference between them; **steps** is `up + down` and is
what "how distant are they" means.

Everything else reads those numbers:

| Feature | What it takes from here |
|---|---|
| The relatives sidebar | the group key and its rank |
| Narrowing the chart | degree, removal, steps |
| The profile metrics | steps, and the counts in `household()` |
| Highlighting on the chart | all of it, for everybody at once |

One module because they must not disagree. Split, the sidebar's idea of a
cousin and the filter's idea of a cousin drift apart, and somebody appears
under *first cousins* and then vanishes when you allow first cousins.

### The tabs are a judgement, not a formula

By raw path length a grandparent (2) ties with a brother (2) and a
great-grandparent (3) ties with an aunt (3). True, and not how anybody
thinks about their family — nobody puts their grandmother above their
sister. So the familiar groups are ordered deliberately:

> You → Immediate family → Grandparents → Grandchildren → Aunts and uncles →
> Nieces and nephews → First cousins → Great-grandparents → … → Married in →
> No known relation

and the tail past third cousins falls back to the arithmetic. Group keys are
**stable**: renaming a tab must never silently change which people a saved
chart draws.

### Married in is not a distance

Your aunt's husband shares no ancestor with you. The arithmetic says "no
relation", which is true and useless — he is at every family gathering. He
gets his own group, named for whoever he married (*married to your aunt*),
and sorts beside her.

### Half is never dropped

A half-brother shares one parent, so only half the ancestry above him is
shared. Calling him a brother asserts a second parent nobody recorded.
`schema.sql`, `FamilyGraph.sibling_kind` and `describe()` all say the same.

---

## Narrowing: `KinFilter`

Two controls, because people ask two questions.

**How far** — cousin degree, removal, total steps, generations up and down.
**Which** — every relation group as its own switch.

```python
KinFilter(max_cousin_degree=1)                 # first cousins, no further
KinFilter(max_removal=0)                       # nobody a generation off
KinFilter(groups=frozenset({"self", "immediate", "cousins_1"}))
KinFilter(married_in=False)                    # blood only
```

Everything defaults to "everybody", so a chart that has never touched this
screen is the chart it always was.

### It re-lays-out. That is the whole point

The filter is applied in `subject_grid._scope`, **before the grid is built**.
Hiding a branch afterwards leaves the chart arranged around a family that is
no longer on it — a gap where the cousins were, every angle still allotted
as though they were coming back. Removed from the cast list instead, the
ordering search in `couple_grid` runs again on what is left.

Measured on a 142-person file, the crossings genuinely fall as it simplifies:

| Narrowing | People | Crossings |
|---|---|---|
| everybody | 142 | 4 |
| first cousins only | 122 | 4 |
| no cousins at all | 99 | 3 |
| no removals | 115 | 2 |

### Keeping it drawable

Two rules, which feed each other — so it is a fixed point, not two passes.

1. A survivor needs the chain of parents joining them to the subject, or the
   chart has a hole in the middle.
2. A survivor brings their partner. A couple is one cell; **half a couple is
   not a smaller chart, it is a wrong one.**

Run once each, a great-uncle pulled in as somebody's husband arrived after
the chains were closed and stood there with neither parent on the chart.

This is also the honest answer to a contradiction: you cannot draw your
fourth cousin without drawing the ancestor the two of you share.

### And a narrowed chart says so

Ask for no cousins and the cousins come off — but the chart must not then
pretend they never existed. **You cannot tell a family of two from a family
of nine you narrowed down**, and a chart that silently drops people is worse
than one that never had them, because it reads as complete.

So every marriage that lost children grows a *pruned branch*: a stub where a
real stem would start, a cross-tick where it was cut, and the number beside
it. `⊥ +4`.

Not dots trailing off. On a laser those are islands that fall out of the
sheet; on paper a fading line is indistinguishable from one the printer lost.

Counted **per marriage**, not per person — a missing child has two parents,
so per person they are counted twice.

`radial_family` draws the mark. The other eighteen designs share the same
scoping and report the number in `plan.meta.extra["elided"]`, so none of
them drops anybody silently.

---

## The window: Explore and Build

Two halves, and the split is not cosmetic. Reading a family and building one
ask different questions, and the reading half has to be safe to hand to
somebody who is not going to be careful with it. **Explore is the default**,
because most of the time most people are reading.

* **Explore** — the relatives sidebar, the profile panel, the scoping
  controls. Clicking anybody shows who they are.
* **Build** — the design gallery, every style control, and the editor panel
  that adds and changes people.

`E` and `B` switch. `P` opens the print dialogue.

### Clicking somebody lights up *their* relatives

Not yours. A second measurement from a different origin — read the second
off the first and you get your cousins in a halo around somebody else.

It is a halo and not a repaint: every line keeps its own colour and gains a
ring, so the chart still reads as the chart while it answers a question.

---

## A profile

Everything anybody knows about one person: the relation in words, the
counts, the facts, the notes, the photographs.

**Only changed fields are sent.** The server reads an absent key as *leave
this alone* and an empty one as *clear it*, and posting the whole form every
time throws that distinction away — which is how saving a birthplace once
wiped a birth date.

### Photographs are copied, never referenced

A path into somebody's Pictures folder is a promise the program cannot keep.
The folder gets tidied, the phone gets replaced, the laptop dies — and the
file that survives all three is the one thing this program tells people to
keep. A tree with two hundred broken image links is worse than one with
none, because it says a picture existed and cannot show it.

So each picture is copied into an album beside the database:

```
my-family.helix
my-family-media/
    3f2a9c….jpg
```

Named by the SHA-256 of its own bytes, which buys three things: the same
photograph on five brothers is stored once, re-adding one is silently the
same picture, and a name that arrived over HTTP can never contain a
directory. `archive` and `restore` carry the album.

### Still to find out

Named, not scored. A percentage tells somebody to feel bad; *"where they
were born · what they did · a photograph"* is a next action. Never a
reproach — plenty of these stay unknown forever, and a file that nags about
a great-grandmother nobody photographed is a file people stop opening.

### See the family from their side

Whose chart it is can be changed from any profile. Every relation on screen
is measured from one person, so this is not a camera move — it re-reads the
whole family from where somebody else stood, and it is what makes a shared
file useful to more than one person in it.

---

### Everything is editable from the profile

Name, surname, sex, dates, places, occupation, education and notes, in the
same panel that shows the relation and the photograph — because the moment
you find out somebody's middle name is the moment you are looking at them,
not the moment you go and find the Build screen.

One save changes it **everywhere**: the chart is redrawn, the relatives
sidebar reloaded, and every printout picks it up. Written to one of the
three and not the others, a file quietly holds two versions of the same
person.

The absent-versus-empty rule (rule 10) is what makes this safe. The form
sends only the fields that changed; a key that never arrives means "leave
this alone" and an empty string means "clear it". Sent the same way, saving
a birthplace wiped the birth date beside it.

---

## Where they came from

`person_heritage` holds what somebody was **told**: `{person, label, share}`.
`kinship.heritage_of` works out what everybody below them inherits — half
from each parent, recursively, so a grandmother recorded as Irish makes her
grandchild 25% Irish and two of them make it 50%.

Three rules, and each of them was a decision:

* **A computed share is never written to a row.** It would go stale the day
  a great-grandparent is added. It is derived on every read, from the
  declarations only.
* **A person's own declaration wins outright** over anything they would have
  inherited. Recording that your grandmother was Irish is a statement about
  *her*, not a guess to be averaged with her parents'.
* **The remainder is named, not hidden.** "62% Irish" on its own reads as a
  rounding error; *"62% Irish, 38% not recorded"* reads as research still to
  do, which is what it is. `heritage_display` adds that row.

It is a generalisation and the interface says so every time it shows a
number — on screen and on paper. It assumes a person's heritage is exactly
the average of their parents', which is a reasonable way to talk about a
family and not a fact about anybody's genome.

Typed as a sentence rather than built out of repeating rows, because that is
how anybody says it: "half Irish, half Scottish" is one statement. `Irish`
means all of it; `Irish, Scottish` splits evenly; `Irish 75, Scottish 25` is
taken as typed.

---

## How much blood: `shared_dna`

The expected share of autosomal DNA, `0.5 ** steps`, **doubled when both
members of the couple at the top are shared**. That doubling is the whole of
the difference between a full relation and a half one, and it is why the
number cannot be read off the label — a full aunt and a half-uncle are both
filed under "aunts and uncles" and they are 25% and 12.5%.

| Relation | Share |
|---|---|
| parent, child, full sibling | 50% |
| grandparent, full aunt or uncle, half sibling | 25% |
| great-grandparent, first cousin, half-uncle | 12.5% |
| first cousin once removed, half-first-cousin | 6.25% |
| second cousin | 3.13% |

**Expected, never measured.** Two brothers share 50% on average and
anywhere from about 38% to 61% in fact; beyond second cousins a pair may
share none at all. Every place the number appears says so — a bare
percentage beside a cousin's name will be read as a test result, and on a
printed sheet it will still be there in twenty years with nobody left to ask.

`dna_display` keeps two decimals and rounds half **up**. Every value here is
`2^-n` or twice it, so one decimal turns the exact 6.25 of a
half-first-cousin into "6.2" — a number that is neither right nor
convincing — and Python's default half-to-even makes 3.125 into "3.12" when
every table of cousin percentages ever printed says 3.13.

### The little tree

`bloodline(graph, pid, depth)` returns the direct ancestry with the share at
every seat, numbered as an **Ahnentafel**: 1 is the person, 2 their father,
3 their mother, `2n` and `2n+1` the parents of `n`.

**Empty seats are returned, not skipped.** A hole with an address is a
research gap; a tree that quietly closes up around it says the line ended
when it has only stopped. The panel draws them dashed and counts what they
cost — *"6 of 15 seats are empty — 50% of their ancestry with nobody's name
on it yet"* — and only the **frontier** counts towards that percentage. Four
unknown great-grandparents sitting behind two unknown grandparents are the
same missing half counted twice, which once made a half-recorded ancestry
read as 100% unknown.

Three generations by default, because four columns of legible names do not
fit a 330px panel: drawn anyway they either ran off the edge, so the
great-grandparents could not be seen at all, or shrank the type until
nothing could be read. The fourth is one click away and earns its column by
shrinking the boxes.

---

## Where to look next: `helix/analysis/gaps.py`

The chart as a to-do list, which is the difference between a poster and a
working research tool.

```
score = reach * findability(year, kind, country) / effort
```

* **reach** — how many people are standing behind the gap. A missing 1790
  birth that blocks 400 descendants beats a missing 1890 occupation that
  blocks nobody. Ancestors of the subject are weighted up again: "blocks my
  own line" is what somebody means by asking where to look next.
* **findability** — England & Wales civil registration from July 1837,
  censuses 1841–1921, parish registers from 1538 with the Commonwealth gap
  1642–1660; Scotland statutory from 1855 and far richer; Ireland weighted
  down for 1922. Deliberately coarse: 0.9 means "the register almost
  certainly survives", not "you will find them".
* **effort** — free online (1) through a record-office visit (5).

**Why three factors and not one.** Ranked by reach alone the list opens with
a 1600s couple whose records burned; ranked by findability alone it opens
with a great-aunt's middle name. The product puts a findable, cheap,
high-reach question at the top — the only kind worth doing on a Saturday
morning.

**Every question says where to go and look**, by name, and never returns an
empty list: rule 8 applies to a research prompt as much as to an error, and
a question with nowhere to look is a nag. **Every question also says who it
is about** — two ancestors recorded as nothing but "Harris" produce two
identical lines, and the relation is what tells them apart.

Scoped like everything else: ask for the gaps while looking at a chart
narrowed to first cousins and you get the gaps on that chart. A to-do list
about somebody who is not on screen is a list nobody acts on. Pass `all=1`
for the whole file.

The headline is worked out over the **whole** ranked list before it is cut,
or a panel showing six would report "2 lines stop here" of a file with
forty-one.

---

## Printing

`/print/profile?id=…`, `/print/profiles`, `/print/outline`.

HTML with a print stylesheet, printed by the browser. Helix writes its own
SVG, PDF, DXF and EPS because a laser chart is **geometry** — lines at
millimetre positions on one sheet — and hand-writing that is how the program
works on a machine with nothing installed. A profile is not geometry. It is
a document: text that reflows, that runs to eighty pages for a large family,
and that has photographs in it. `render/pdf.py` writes one page and has no
image support, so a dossier through it would mean writing pagination and an
image encoder; the browser already does both, correctly, and it is already
open.

A printout covers **the same people the chart does**. Print a chart narrowed
to first cousins and then a dossier of four hundred people and the two do
not describe the same family.

The outline exists because a chart is a picture, and a picture cannot be
read down a column or ticked off against a list. The same family as text is
what you take to an archive.

---

## Where things live

```
helix/graph/kinship.py     the measurement, the groups, the filter,
                           shared DNA, the bloodline seats, heritage
helix/analysis/gaps.py     what is worth looking up next, ranked
helix/store/album.py       photographs on disk
helix/render/dossier.py    profiles and the outline, as HTML
helix/web/js/relatives.js  the tabs
helix/web/js/profile.js    the profile panel and the halo
tests/test_kinship.py      the arithmetic and the narrowing
tests/test_ancestry.py     all of it over real HTTP
```

## Endpoints

| Route | What it gives |
|---|---|
| `GET /api/relatives` | everybody in tabs, closest first |
| `GET /api/kin?id=` | one person's relation, counts, and highlight sets |
| `GET /api/groups` | every relation group, for the scoping screen |
| `GET /api/person?id=` | the profile, with photos, facts and what is missing |
| `GET /api/media?name=` | a stored photograph |
| `POST /api/person/photo` | add one, as a `data:` URL |
| `POST /api/person/photo/remove` | take it off a person; the file stays |
| `POST /api/person/photo/crop` | which part of it is the face, as `x,y,w,h` in fractions; empty puts the whole picture back |
| `POST /api/person` | edit anything about them, from the profile |
| `POST /api/person/bulk` | one field on several people, in ONE undoable step |
| `POST /api/person/heritage` | where their family came from, as a whole list |
| `GET /api/history/list` | everything done to this file, newest first |
| `GET /api/history/what?batch=` | who and what one of those changes touched |
| `GET /api/sheets` | how many sheets a record book will be, at least |
| `GET /api/gaps` | where more research is needed, ranked |
| `GET /print/profile\|profiles\|outline\|record\|records\|chart` | pages meant for paper |

**Cropping is never re-encoding.** The crop is four fractions on the `media`
row and the photograph itself is untouched — the one picture of somebody's
grandmother is usually a group at a wedding. Four places show it (the
profile frame, the sidebar avatar, the printed profile, the record book) and
all four build the same background style from the same numbers.

**`/api/person/bulk` refuses more than it accepts.** `records.BULK_FIELDS`
is the list, and anything else gets an error naming what can be set instead:
a surname, a place, an occupation, a confidence, a tag. A birth date is a
fact about one person.

`/api/person` also carries `heritage` (declared and inherited), `dna` (the
share and the bloodline seats) and `gaps` (the five worth doing about that
person). `/api/gaps` takes `limit`, `country`, `all=1`, and the same scoping
parameters as the chart.

Every chart route (`/api/plan`, `/api/svg`) accepts the filter, either as
`kin=<json>` or as plain parameters: `max_cousin_degree`, `max_removal`,
`max_steps`, `max_up`, `max_down`, `married_in`, `unrelated`, `groups`.


---

## Related lines: `helix/analysis/consang.py`

Cousins marrying cousins is not an oddity of one family — before the
railways most people married somebody from the same parish, and in a village
of four hundred that means a shared great-grandparent more often than not.

**Wright's coefficient of inbreeding**, over every ancestor two parents
share:

```
F = Σ over shared ancestors A of  (1/2)^(n1 + n2 + 1) × (1 + F_A)
```

First cousins marrying give their children F = 1/16 = 6.25% exactly; second
cousins, 1/64. `(1 + F_A)` — the ancestor's own inbreeding — is what makes
this Wright's formula rather than an approximation of it, and in a village
where cousins married for four generations the approximation is out by a
fifth.

**Two things the interface must say every time.** F is a statement about a
*pedigree*, not about anybody's health, and it is only as deep as the file:
a tree that stops four generations back cannot see the shared
great-great-grandparents that would raise it. So a zero means "none found
here", never "none", and the panel says so.

`consang.couples()` lists every marriage in the file where the two were
already related, with what they were to each other and which ancestors they
share. It is as much a fact about a place as about a family: a village where
this happens six times is a village people did not leave.

---

## The family in order: `stats.family_timeline`

A chart says who was related to whom and nothing about when. A person's own
timeline shows one life. This is the third view — 1841 a marriage, 1843 a
birth, 1849 a death — the shape of a household changing.

**A stretch with nothing in it is a finding.** Between two dense periods a
quiet decade is usually not a family that stopped happening; it is a
register nobody has looked at. Those gaps are marked.

`stats.anniversaries()` reads the same data forwards: birthdays and wedding
anniversaries in the next month, living people first. **Only where the day
is actually recorded** — a date stored as "1841" has no day in it, and
offering somebody a birthday the program invented is worse than offering
none.

---

## Families that married in

Somebody who married in and has no parents recorded is not a missing detail.
They are the door to an entire branch that is not in the file at all, and
half of every descendant's ancestry comes through it.

Ranked purely by score they never surface: a blood ancestor's missing birth
year blocks more people, which is correct arithmetic and means that job is
never seen. So the research panel groups by **kind of job**, and "married
in, not started" is one of them.

The boost is by how close the relative they married is — your mother's
husband's family is a real question and a fourth cousin's wife's family is
not.
