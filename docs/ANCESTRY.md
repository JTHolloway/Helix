# Keeping a family, not just drawing one

Helix began as a way to lay a family out and cut it into wood. This is the
other half: somewhere to put what you know about the people on it, and to
read the file rather than only render it.

Four features, and all four are the same one underneath.

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

Measured on the owner's tree, the crossings genuinely fall as it simplifies:

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
helix/graph/kinship.py     the measurement, the groups, the filter
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
| `GET /print/profile\|profiles\|outline` | pages meant for paper |

Every chart route (`/api/plan`, `/api/svg`) accepts the filter, either as
`kin=<json>` or as plain parameters: `max_cousin_degree`, `max_removal`,
`max_steps`, `max_up`, `max_down`, `married_in`, `unrelated`, `groups`.
