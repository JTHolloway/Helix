# The record system — full specification

This is the most important thing left to build. It is specified here in
enough detail to implement without guessing.

## The mental model

**You are always standing on somebody, and you add the next person relative
to them.** That is the whole interaction. Nobody types into a database; they
say "my father had a sister" and the program works out what records that
needs.

The word **union** must never appear in the interface. It is the right word
for the schema and the wrong word for a person adding their aunt. The screen
says *partner*, *married*, *together*. When someone adds a partner, Helix
creates a union behind the scenes and never mentions it.

---

## Screen 1 — The person panel

Opens when you click anyone on the chart, or pick them from search. Three
sections: **who they are**, **who they are connected to**, **what you know**.

```
┌────────────────────────────────────────┐
│  Michael Pargeter              ✎  ⋯    │
│  1962–                                 │
│  your father                           │
├────────────────────────────────────────┤
│  FAMILY                                │
│                                        │
│  Parents                               │
│    Arthur Pargeter      1935–2011      │
│    Edith Marlow         1937–          │
│    + Add father                        │
│                                        │
│  Partners                              │
│    Susan Hallam    1964–   2 children  │
│    Rachel Dunmore  1960–   1 child     │
│    + Add a partner                     │
│                                        │
│  Children                              │
│    with Susan Hallam                   │
│      James Pargeter     1992–   (you)  │
│      Claire Pargeter    1995–          │
│      + Add a child                     │
│    with Rachel Dunmore                 │
│      Hannah Pargeter    1986–          │
│      + Add a child                     │
│                                        │
│  Brothers and sisters                  │
│    + Add a brother or sister           │
├────────────────────────────────────────┤
│  FACTS                        + Add    │
│    Born    12 Mar 1962   Bath          │
│    Married 1990          Walcot        │
│    Occupation  Engine fitter           │
├────────────────────────────────────────┤
│  Make this person “me”                 │
│  Remove from tree                      │
└────────────────────────────────────────┘
```

Points that matter:

- **Children are grouped under the partner they belong to.** This is where a
  person sees, without being taught anything, that they have half-siblings.
- **"+ Add a child" appears once per partner**, so attaching a child to the
  right family needs no explanation.
- If a person has children with nobody recorded, that group is headed
  *"with someone not recorded"* and offers **+ Add the other parent**.
- Relationship to the subject is always shown in plain words at the top.

---

## Screen 2 — Adding a person

One dialogue, used for every relationship. It already knows who it is
attaching to and how, so it never asks.

```
┌──────────────────────────────────┐
│  Add Michael's father            │
│                                  │
│  Given names   [            ]    │
│  Surname       [ Pargeter   ]    │  ← pre-filled, editable
│  Born          [            ]    │
│  Died          [            ]    │
│  Born in       [            ]    │
│                                  │
│  ○ Man  ○ Woman  ○ Not recorded  │
│                                  │
│  [ Add ]   [ Add and add another ]│
└──────────────────────────────────┘
```

- **Only a name is required.** Everything else can be blank.
- The **surname is pre-filled** from the relative where that is the sensible
  guess (father, brother, child of a man) and blank where it is not (mother,
  wife). Always editable.
- Dates accept vague forms — `abt 1834`, `bef 1900`, `bet 1820 and 1825`,
  `Q3 1871`. Show a small live echo: typing `abt 1834` shows *"about 1834"*.
  Never reject a date; store what was typed.
- **"Add and add another"** keeps the dialogue open with the same
  relationship, because siblings and children come in runs.
- If the name closely matches somebody already in the file, offer
  *"Did you mean this person? — Link to them instead"* rather than creating a
  duplicate. Duplicate people are the most common way a tree goes wrong.

---

## What each button does to the database

| Button | Records created |
|---|---|
| Add father / mother | Person; a union for the parents if none exists; `union_child` linking the standing person to it |
| Add partner | Person; a union with both partners |
| Add child (under a partner) | Person; `union_child` on that union |
| Add child (no partner recorded) | Person; a union with one partner; `union_child` |
| Add brother or sister | Person; `union_child` on the standing person's own parents' union |
| Link to existing | No new person; only the link rows |

Every write appends to `change_log` with before and after.

---

## Endpoints

```
POST /api/person/new
  { given, surname, sex, birth, death, birth_place,
    attach: { to: <person_id>,
              as: "father"|"mother"|"partner"|"child"|"sibling",
              union: <union_id|null> } }
  -> { id, union_id, warnings: [...] }

POST /api/person            update fields on an existing person
POST /api/person/link       attach an existing person by relationship
POST /api/person/detach     remove one link, keep the person
POST /api/person/retire     mark inactive  (NEVER a SQL DELETE)
POST /api/union             create; add or remove a partner
POST /api/union/child       attach or detach, with relationship type
POST /api/undo              replay change_log backwards
POST /api/redo
GET  /api/person/search?q=  name match, for the duplicate check
```

`attach.as = "father"` means: create the person, find or create the union
holding the standing person's parents, and add the new person to it as a
partner. The client never has to reason about unions.

---

## Navigation

The record system has to be walkable, not just editable.

- **Search** (`/`) — type-ahead over every name, showing dates and
  relationship to you. Already built.
- **Click anyone on the chart** to open them. Already built.
- **Click any name inside the person panel** to walk to them. Already built.
- **Back / forward** through visited people, with browser history.
- **Recently edited** list, so returning after a break is one click.
- **A plain list view** — every person, sortable by surname, birth year or
  how complete their record is. Some people prefer a table to a chart, and it
  is the fastest way to spot a half-finished record.

---

## Rules the implementation must hold

1. **Never SQL-DELETE a person.** "Remove from tree" marks them inactive and
   detaches links. A wrong ancestor deleted at midnight is a real loss.
2. **Undo everything**, from `change_log`. Ctrl-Z, at least 100 deep.
3. **Autosave.** SQLite means there is no "unsaved document"; there must be
   no Save button either.
4. **Validate softly.** If someone enters a child born before their parent,
   show it inline — *"Hannah would have been born before Michael. Check the
   dates?"* — and still save it. People enter what the record says and fix it
   later.
5. **Never lose typed text.** An unparseable date is stored verbatim with
   `kind='unknown'`.
6. **Back up before any bulk change.** `store/db.backup()`.
7. **Every action reachable by keyboard**, with visible focus.

---

## Done when

You can do all of this without ever touching the command line:

```
1. Start from an empty file
2. Add yourself
3. Add your parents, their parents, their parents
4. Add your siblings
5. Add your father's second partner, and a half-sibling under her
6. See the half-sibling drawn on its own arc, joined to yours by a dashed tie
7. Fix a typo in a date
8. Undo it, redo it
9. Close the browser, reopen, find everything intact
10. Export a 1000 × 1000 mm SVG
```

That sequence is the acceptance test. Write it as an integration test that
drives the API directly, then walk it by hand in the browser.
