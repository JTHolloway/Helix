# Helix

**A genealogy program that keeps everything you know about your family, and
draws it as a chart you can print, frame, or cut out of wood.**

Everything happens inside the program. There is one command to install it;
after that you never need a terminal again.

---

## Installing it

You need **Python 3.11 or newer**. Most Macs and Linux machines already have
it. On Windows, get it from [python.org](https://www.python.org/downloads/)
and tick **“Add Python to PATH”** on the first screen of the installer.

Then open a terminal — Command Prompt on Windows, Terminal on a Mac — go to
the folder you downloaded, and run **one line**:

```
pip install ".[desktop]"
```

That is the last command you need. From now on:

```
helix-app
```

opens Helix in its own window. Make a shortcut to that and you never type
anything again.

> **`[desktop]` is optional.** It installs `pywebview`, which gives Helix a
> real application window. Without it — `pip install .` — everything still
> works: Helix opens a clean browser window with no address bar and no tabs.
> The program itself has **no dependencies at all**.

### Or with nothing installed at all

If you would rather not install anything, the folder runs as it stands:

```
python3 -m helix.desktop
```

Same program, same window, nothing added to your machine.

### An application you double-click

`python3 build_app.py` packages Helix into a single application for the
machine you run it on — `Helix.app` on a Mac, a `Helix` folder with
`Helix.exe` on Windows, a folder with `Helix` on Linux. Copy it wherever you
like; it needs no Python installed. This cannot be cross-compiled: a Windows
build has to be made on Windows.

### Where your family is kept

In **Documents → Helix**, as ordinary files you can see, copy, email and back
up. Not in a hidden application folder — a genealogy file is usually the most
irreplaceable thing on somebody's computer, and it belongs where they keep
the rest of their irreplaceable things.

Helix takes a dated backup every day you open it, keeps the last thirty, and
writes every change to disk the moment you make it. **There is no Save
button, because there is nothing unsaved.**

---

## Your first ten minutes

**Open Helix.** The first time, it makes an empty family and asks for one
person.

1. **Add yourself.** Press <kbd>Enter</kbd> to save. Only a name is needed —
   put a date in if you have one, in whatever form you have it:
   `12 March 1841`, `1841`, `Mar 1841`, `abt 1834`, `bef 1900`,
   `bet 1820 and 1825`, `Q3 1871`. Nothing you type is thrown away, even if
   Helix cannot make a date of it.

2. **Click your name on the chart.** A panel opens with everything known
   about you and everyone you are related to.

3. **Press <kbd>B</kbd> for Build.** Now the panel offers **+ Add father**,
   **+ Add mother**, **+ Add a partner**, **+ Add a child** and **+ Add a
   brother or sister**. Each one already knows who it is attaching to, so it
   never asks.

4. **Keep going.** Every box saves itself the moment you leave it.
   <kbd>Ctrl</kbd>+<kbd>Z</kbd> takes back anything, a hundred steps deep,
   and <kbd>Ctrl</kbd>+<kbd>Y</kbd> puts it back.

Entering a family is a lot of typing, so it is built to be done from the
keyboard: <kbd>Enter</kbd> adds, <kbd>Shift</kbd>+<kbd>Enter</kbd> adds and
starts the next one, and <kbd>Alt</kbd>+<kbd>M</kbd> / <kbd>F</kbd> /
<kbd>U</kbd> says who they were without leaving the name box.

### Already have a tree somewhere?

**Import** takes a GEDCOM from Ancestry, MyHeritage, FamilySearch or almost
anything else, and a spreadsheet as CSV. It tells you what it found *before*
it writes anything, and afterwards shows exactly who arrived, which surnames,
what years they cover, and which of them have nobody above them yet — the
places where their tree and yours have to be joined by hand. One
<kbd>Ctrl</kbd>+<kbd>Z</kbd> takes the whole import back.

---

## What the buttons do

Helix has two halves. **Explore** is for reading a family, **Build** is for
adding to one. The switch is at the top left, or <kbd>E</kbd> and
<kbd>B</kbd>.

| Button | What it is for |
|---|---|
| **Import** | Bring in a GEDCOM or a spreadsheet |
| **Numbers** | What the file says about the family as a whole — ages, family sizes, how far back each line goes |
| **Timeline** | Every birth, marriage and death in order |
| **Relate** | Pick any two people; Helix works out how they are related, and how much DNA they would be expected to share |
| **Sources** | Every record your research rests on, and what each one is cited for |
| **Find** | Search, households, contacts, the file's own history, and comparing a cousin's file against yours |
| **Family** | Which family is open, where your files are kept, and starting or opening another |
| **Print** | Official records, full profiles, the whole record book, and the chart |
| **People** | Everyone as a sortable list, with how complete each record is |
| **Export** | SVG, PDF, DXF, EPS, PNG, GEDCOM, or a full archive |
| **Advanced** | Every layout control, for when you want to change how the chart looks |

### The panel on the left

**How far the tree spreads.** A real family is four hundred people by the
fifth generation, and four hundred names will not fit legibly on a chart.
This is where you say how much of it you want: your direct line only, that
plus their brothers and sisters, everyone you are related to by blood, or
everybody. Narrowing happens *before* the chart is drawn, so what is left is
laid out properly rather than left with holes in it — and any family that
lost children to the narrowing is marked with the number, so a small family
never reads as a complete one.

**Everyone in this family.** Your relatives in tabs, closest first — you,
immediate family, grandparents, aunts and uncles, first cousins, outwards. A
red dot marks a record missing something that stops the person being
findable. **Choose several** turns the list into tick boxes: filter to a
surname, tick what the filter found, and set a place or a correction on all
of them at once — which one <kbd>Ctrl</kbd>+<kbd>Z</kbd> takes back.

**Where to look next.** What is worth looking up, ranked by how many people a
gap is blocking and how likely the record is to have survived. A research
list, not a scolding: the top of it is a findable question worth a Saturday
morning.

### The panel on the right

Click anyone. You get their photograph, everything recorded about them, how
they are related to you, where their family came from, how much DNA you would
be expected to share, their line back to the earliest ancestor in the file,
and what is still to find out.

Everything on it can be edited, and everything that can be added can be taken
away again.

---

## Photographs and papers

Drop a photograph, a scanned certificate, an order of service or a recording
onto the frame at the top of anyone's profile. It is **copied** into an album
beside your family file, so it survives the phone being replaced and the
Pictures folder being tidied.

Somebody at twenty and the same person at eighty are two photographs of one
person: the newest is the one shown, the earlier ones are kept below it, and
you can put a year or an age under each.

**Cropping never cuts the photograph.** The one picture of somebody's
grandmother is usually a group at a wedding. Helix records which *part* of
the picture to show, so the frame shows her face and the file still holds
everybody else at the wedding — and taking the crop off puts the whole
picture back.

---

## Printing

Two things print for one person. An **official record** is the sheet that
goes in a ring binder: every field present whether or not it is filled in,
because a blank is ambiguous forever and “Unknown” is a statement about the
research. A **full profile** is everything on screen.

For everybody there is the **record book** — one page per person, oldest
first and family by family, with a cover, a contents and an index. Helix says
how many sheets it will be *before* you press print.

The chart prints too, on its own sheet, at the size you set.

---

## Cutting it out of wood

Helix was written to make a chart you can hold. **Export → SVG (cut layers
only)** gives red lines to cut and black to engrave. Under **Advanced**,
*Check it will cut cleanly* runs a pre-flight: text too small to read at that
size, lines too fine to survive, pieces that would fall out, anything drawn
outside the cut line. It says what is wrong and what to do about it.

There is a **clock** option: one 8 mm bore at the exact centre, with a warning
if the middle is too tight or the hands would be too heavy.

**DXF** and **EPS** export for the software most cutters use. **PDF** prints
at true size, so nothing is resized on the way to paper.

---

## Twenty ways to draw the same family

The gallery on the left shows each one **drawn from your own family**, not a
stock picture — so what you click is what you get.

The default, **Family Rings**, gives each couple one wedge and one ring per
generation, with the founders at the centre. It is the only one that says
without a legend who is married to whom, which children are whose, and who is
a cousin of whom.

The rest run from a **classic tree** and an **hourglass**, through a **transit
map** and a **timeline of lifespans**, to a **hive plot** that makes
intermarriage countable, a **river of descent** whose ribbons narrow as lines
die out, a **map** of where the family lived and moved, and a **star chart**
for a wall.

---

## Somebody else's tree, from your file

Your niece wants a family tree of her own. **Family → Make this tree for
somebody else** writes a new file with her at the centre, offers by name to
leave out the branches that are no relation to her, and **does not touch
yours**.

That matters more than it sounds. Every relation in Helix is measured from
one person — “my grandmother”, “my second cousin”, the DNA percentages, the
research list. Changing who that is is not a preference; it is a different
document about the same family. So it is a different file.

---

## Keeping your work

* Every change is written to disk immediately. There is no Save button.
* A dated backup is taken once a day; the last thirty are kept beside the file.
* **Export → Archive** writes a single zip holding the database, every
  photograph, and a plain JSON dump that can be read without this program at
  all — in thirty years, on a machine that has never heard of Helix.
* **Export → GEDCOM** opens in Ancestry, MyHeritage and FamilySearch. A second
  version leaves out living people's details, for sending to somebody else.
* Nothing is uploaded anywhere. Helix has no account, no cloud and no network
  connection.

---

## Keyboard shortcuts

| | |
|---|---|
| <kbd>E</kbd> / <kbd>B</kbd> | Explore / Build |
| <kbd>/</kbd> | Find a person |
| <kbd>Ctrl</kbd>+<kbd>Z</kbd> / <kbd>Ctrl</kbd>+<kbd>Y</kbd> | Undo / redo |
| <kbd>+</kbd> <kbd>−</kbd> <kbd>Z</kbd> | Zoom in, zoom out, fit |
| <kbd>T</kbd> | Light up your direct line |
| <kbd>C</kbd> | What if this person had never been born |
| <kbd>P</kbd> <kbd>L</kbd> <kbd>N</kbd> <kbd>Y</kbd> <kbd>R</kbd> <kbd>S</kbd> <kbd>F</kbd> <kbd>I</kbd> <kbd>O</kbd> | Print, People, Numbers, Timeline, Relate, Sources, Find, Import, Family |

---

## On a phone or tablet

By default Helix listens only to the computer it is running on — nobody else
on your network can see it, which is the right default for a file full of
living people's birthdays.

To read your tree from the sofa, start it once with `--lan` — the one time
you need a terminal after installing:

```
helix serve "Documents/Helix/My family.helix" --lan
```

Then open **Family** in the program: it shows the address and a QR code to
point a phone at. The panels become drawers, the chart pinches to zoom, and
everything else is the same program. Close Helix and the address is gone.

---

## If something goes wrong

Helix never shows a stack trace; every message says what to do next. Your
research is in a SQLite file that plenty of other programs can open, with
thirty backups beside it, and nothing you can do in the interface will damage
it.

---

## For developers

```bash
python3 bootstrap.py           # builds a sample family, renders every design,
                               # runs the tests. Installs nothing, no network
python3 -m pytest tests -q     # 621 tests
python3 build_app.py           # a double-clickable application for this OS
```

`node tools/walkthrough-read.mjs URL` and `walkthrough-edit.mjs URL` drive the
real interface in a real browser. They catch what `pytest` cannot — a button
sitting under another button, a click that never reaches its handler, a chart
nobody can select anyone on.

| Folder | What it holds |
|---|---|
| `helix/model/` | Dates that can be vague. Everything depends on this. |
| `helix/store/` | Schema, connection, backup, archive, restore. |
| `helix/graph/` | The family as a graph; kinship; validation. |
| `helix/layout/` | Twenty designs sharing one abstract grid. |
| `helix/render/` | SVG, PDF, DXF, EPS — all written by hand. |
| `helix/fab/` | Materials, pre-flight, kerf, islands, clock. |
| `helix/web/` | The interface. No build step, no npm. |
| `helix/desktop/` | The application window, and where family files live. |
| `helix/io/` | GEDCOM in and out; spreadsheet import. |
| `docs/` | Specifications. Read before writing. |

Start with `START_HERE.md`, then `CLAUDE.md` for the rules that must not be
broken and `docs/DECISIONS.md` for why the program is the way it is.

Everything is still there from a terminal if you want it — `helix serve`,
`helix render`, `helix export`, `helix check` — see `helix --help`.

**Requirements:** Python 3.11+ and nothing else. `pywebview` for a native
window and `pyinstaller` to build an application, both optional.
