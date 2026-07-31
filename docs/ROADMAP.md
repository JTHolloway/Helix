# Ideas, ranked

Everything here is specified enough to build. `docs/DECISIONS.md` records
what was built and why it is the way it is; this is what is left.

---

## Built since this list was written

| | |
|---|---|
| **Research gap ranking** ✅ | `reach × findability ÷ effort`, with the repositories named. Families that married in and have never been started are their own kind of job, so they are never buried under a blood ancestor's missing birth year. |
| **The family in order** ✅ | Every birth, marriage and death on one timeline, with the quiet stretches marked — a decade with nothing in it is usually a register nobody has looked at. |
| **Related lines** ✅ | Wright's coefficient of inbreeding, and every marriage where the two were already related, with what they were to each other. |
| **Anniversaries** ✅ | Birthdays and wedding anniversaries in the next month. Only where the day is actually recorded. |
| **Shared DNA and a bloodline tree** ✅ | Expected percentages, Ahnentafel seats, and the empty seats drawn rather than skipped. |
| **Where a family came from** ✅ | Heritage declared on whoever is known to have it, inherited by everybody below, with the remainder named. |
| **Duplicate detection and merge** ✅ | The commonest thing that goes wrong, and the thing an import guarantees. |
| **GEDCOM and spreadsheets, both ways** ✅ | The round trip through 463 people is exact. |
| **A desktop application** ✅ | Windows and macOS, with family files in a folder you can see. |
| **First and middle names** ✅ | Two boxes, one field. A middle name was the commonest thing left out because there was nowhere obvious to put it. |

---

## Worth building next

**A relationship calculator between any two people.** *Small — `graph.kinship`
already answers it; this is a screen.* "How is Aunt Rose related to the man
in this photograph?" Two search boxes and the path between them, drawn.

**Sources and citations, surfaced.** *Medium — the schema is there and
unused.* `source` and `citation` exist and nothing in the interface writes
to them. A genealogy without sources is a rumour with dates on it. The
minimum: attach a source to a fact, mark uncited claims, and print a
bibliography.

**A household view.** *Medium.* "Who was living in this house in 1861" is
how the records are organised and is not a shape this program can draw.

**Living-person privacy on export.** *Small — `redact_living` exists for
charts and not for GEDCOM.* Sharing a tree that names living children and
their birthdays is the one mistake a genealogy program should not help with
silently.

**Two files compared.** *Medium.* A cousin sends a GEDCOM of the same
family. What is in theirs and not in yours, fact by fact.

**Undo history as a list.** *Small — `change_log` already holds it.* Not
just Ctrl-Z but "what did I change last Tuesday", and stepping back to a
point.

**Custom fact types.** *Medium.* `event.type` is already a free string; the
interface offers four kinds. Military service, emigration, wills and
apprenticeships are one form away.

**Search that understands the family.** *Small.* "Whitcombes born before
1850", "everybody with no death date". The filters exist; one box that takes
them does not.

---

## Deliberately not built

**Automatic hints from online trees.** Every commercial program does this
and it is how bad data spreads: somebody accepts a hint and a wrong
great-grandmother propagates into forty trees. Helix makes no network calls
and will not start.

**A confidence percentage per person.** Confidence per FACT is honest;
rolled into one number it invites people to read 82% as research rather
than as arithmetic over their own guesses.

**Kerf compensation.** `fab/kerf.py` should stay a stub until somebody has
callipers on a test strip. Doing it from a guess produces parts that do not
fit.

**Cloud sync.** The file is the product. Dropbox, a memory stick and a
GEDCOM export already move it, and nobody can turn those off.

---

## The original catalogue

## Build these first

**1. The what-if overlay.** ✅ *built* — hover any ancestor, watch everyone
who depends on them fade. This is the feature people will show other people.

**2. Lifelines.** ✅ *built* — bar length = lifespan. Infant mortality becomes
visible as a band of stubs. The design most likely to make someone cry.

**3. Equal-area radius.** ✅ *built* — disc area grows as r², so a linear time
scale crushes the recent, populous generations into the rim. `gamma = 0.5`
fixes it. Quiet, mathematical, transforms the chart.

**4. Confidence as linework.** ✅ *built* — proved facts solid, probable
normal, possible dashed, placeholders dotted. You see the shape of what you
have actually proved rather than what you have assumed.

**5. Research gap ranking.** ✅ *built* — score each missing fact by
`descendants_blocked × source_availability ÷ effort` and produce a ranked
to-do list: *"Find the 1841 census for Thomas Whitcombe — unblocks 63
descendants."* Turns a poster into a working tool.

**6. Era bands.** ⏳ — faint background rings labelled with what was happening:
Napoleonic Wars, cholera 1832, Great Famine, 1918 influenza, the wars. Your
family stops being isolated and becomes part of history. Cheap to build,
enormous emotional return.

**7. The year scrubber.** ⏳ — a slider that greys out anyone not yet born or
already dead. Drag from 1750 to 2026 and watch the family breathe. Export as
an animated GIF and people will actually share it.

## Objects and outputs

**8. Working clock.** ⏳ — 8 mm bore, sectors snapped to clock hours so hands
never hide a name that matters. Numbers in `fab/clock.py`.

**9. Companion booklet.** ⏳ — chart carries numbers, booklet carries the
detail. Removes the density ceiling entirely: a chart with 2,000 people is
impossible, a chart with 2,000 numbers is fine.

**10. QR to the archive.** ⏳ — a small QR in the border linking to a local
HTML export with photographs and sources.

**11. Multi-layer relief.** ⏳ — one sheet per generation, stood off by 3 mm
spacers. The tree acquires literal depth. Needs per-layer registration holes.

**12. Two-material sandwich.** ⏳ — dark walnut face over pale maple; cut the
names through the top so the pale layer shows. Needs kerf compensation to fit.

**13. Brass inlay for the Thread.** ⏳ — cut the Thread's channel through the
face layer, lay in 1 mm brass rod, sand flush. The bloodline becomes metal.

**14. Coasters.** ⏳ — one branch per 100 mm slate coaster, set of six. The
gift that works when the wall piece is too much.

**15. Braille layer.** ⏳ — Grade 1 names on a separate deep-engrave layer at
correct dot pitch.

## Analysis

**16. Map view.** ⏳ — plot people at their birthplaces, draw descent lines.
See a family migrate across a county over two centuries.

**17. "Where were they in 1881?"** ⏳ — pick a year, show everyone alive and
where they were. History rather than structure.

**18. DNA overlay.** ⏳ — colour by which segment of the tree a match confirms.
Shows instantly which parts of the paper trail have independent support.

**19. Occupation ribbons.** ⏳ — a thin ring of colour by trade, showing the
family move from land to industry to office over three generations.

**20. Diff view.** ⏳ — two `.helix` files, or one file at two dates,
side by side with the differences highlighted. Essential once you are
collaborating with a cousin.

## Longer term

**21. Photo medallions.** ⏳ — dithered halftone engravings in the innermost
ring. Technically fussy; extraordinary when it works.

**22. Public HTML export.** ⏳ — a static, self-contained site of your tree
with living people redacted. One file you can email.

**23. FamilySearch API sync.** ⏳ — pull the shared tree, flag conflicts,
never overwrite silently.

**24. Voice interview capture.** ⏳ — record the conversation with your
grandmother, transcribe it, and attach clips to the people mentioned. Closes
the loop on Step 0 of the research handbook, which is the step everyone
regrets skipping.

**25. Watch face.** ⏳ — the whole ancestry compressed to 40 mm on anodised
aluminium. Absurd. Someone will want it.
