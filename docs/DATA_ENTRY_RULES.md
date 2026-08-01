# Ten rules for recording a family

Read this before you enter your second person. Following these from the start
costs nothing. Discovering them after 800 people costs a rebuild.

### 1. Record what the document says, not what you concluded

The census says *Elizth Whitcomb, 34, Somerset*. Enter that. Your conclusion
that she is Elizabeth Whitcombe born 1807 in Walcot goes in the reasoning
field, attached to the citation. In five years you will want to know which
was which, and you will not remember.

### 2. Women keep their birth surname

Elizabeth Hallam who married Thomas Whitcombe is recorded as **Hallam**, with
a married name as a secondary name record. Genealogy is traced through birth
families; filing her under Whitcombe makes her untraceable.

### 3. A person you have not proved still gets a record

You know Thomas had a father because Thomas existed. Create the father as a
**placeholder** with confidence 0. He will appear on the chart as a dashed
outline, and he is the thing that tells you where to look next. Placeholders
are how a chart shows you its own edges.

### 4. Never delete. Mark uncertain

If you find you attached the wrong parents, lower the confidence and write
why. Deleting destroys the record of a question you already investigated, and
you will investigate it again.

### 5. One source record per document, many citations

The 1851 census for Walcot is **one** source. Every fact you take from it is
a separate citation pointing at that source with a page reference. Do not
create a new source per person.

### 6. Vague dates are data. Use them

`abt 1834`, `bef 1900`, `bet 1820 and 1825`, `Q3 1871` are all better than
blank, and Helix understands all of them. A blank field tells the program
nothing; "before 1900" narrows a search enormously.

An age from a death certificate is a **calculated** birth date, not an exact
one. Record it as `calc 1834` — ages given at death are frequently wrong by
several years, because the person supplying them was grieving and guessing.

### 6b. Recording only blood relatives is a legitimate choice

Many people record only those they are actually descended from, or descended
alongside — no aunts-in-law, no step-parents, no partner's families. Helix
supports this properly rather than fighting it.

The case that matters: **your father's other child.** Create a second union
for your father and attach the half-sibling to it. Record the other parent or
not, as you prefer — either works, and the chart says something slightly
different in each case:

- your father is drawn **once**, with both families hanging from him, and the
  two sibling groups **bridged by a dashed arc** showing they share him
- the link into the second family is **dashed**, because those children are
  your half-siblings — and that stays true whether or not their mother is on
  the chart
- if you *do* record her, she appears normally, with a **solid cap** showing
  her line is not one you are following
- if you *do not*, a **hollow circle** stands where she would be — the chart
  states that somebody is missing rather than inventing them
- either way the half-siblings sit on their own arc, visibly separate from
  your own brothers and sisters

Recording the other parent is usually worth it: it costs one record, and it
stops a future reader wondering whether the gap is a fact or an omission.

Do **not** put a half-sibling on your own parents' union to save a step. That
tells every future reader that you shared a mother, and no amount of notes
will undo it once the chart is on a wall.

`graph.relationship()` returns `half-sibling`, not `sibling`, whenever only
one parent is shared. `graph.half_siblings(pid)` lists them.

### 7. Enter the whole sibling group

It is tempting to record only your direct ancestor. Don't. Siblings are how
you identify the right family in the next census, how you tell two John Smiths
apart, and how you find the DNA match that breaks a brick wall. They cost
five minutes each and they are the highest-return data you will ever enter.

### 8. Places get their full hierarchy

*Walcot, Bath, Somerset, England* — not *Bath*. Parish boundaries moved,
counties were reorganised in 1974, and a bare place name will eventually
match the wrong place. Helix stores places hierarchically so you type it once.

### 9. Record what you looked for and did not find

"Searched Walcot parish registers 1800–1815, no baptism for Thomas." This is
a **negative result** and it is genuinely valuable. Without it you will search
the same register three times over five years.

### 10. Run `helix check`, and back up

`helix check` finds children born before their parents, people who died
before they were born, and mothers aged 68. It takes two seconds.

Back up to somewhere that is not your computer. The `.helix` file is small
enough to email to yourself. Years of work, one file, no excuse.

---

## Confidence levels

| | Meaning | Drawn as |
|---|---|---|
| **3** | Proved. Primary source, directly stated. | Solid, full weight |
| **2** | Probable. Good indirect evidence. | Solid, normal |
| **1** | Possible. Circumstantial. | Dashed |
| **0** | Placeholder. Must exist; nothing known. | Fine dots, faded |

The chart shows this as linework, so you can see the shape of what you have
actually proved. Most people find their tree is less solid than they thought,
and that is a useful thing to look at.
