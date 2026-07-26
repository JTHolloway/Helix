# How to actually find your ancestors

Written for the United Kingdom and Ireland, which is where most of this
applies. The principles hold anywhere; the record sets differ.

You can get four or five generations back for **nothing**. Pay only when the
free routes run out.

---

## Step 0 — Do this first, before any website

**Interview your oldest living relatives, and record it.**

Every genealogist eventually says the same sentence: *I wish I'd asked my
grandmother.* This is the only source with an expiry date. Websites will
still be there next year.

Ask, and write down the answers:
- Full names, including middle names, of everyone they can remember
- Maiden names — the single most valuable thing they know
- Roughly when and where people were born, married, died
- Where the family lived, and when they moved
- What people did for a living
- Nicknames, and who was named after whom
- **Family stories** — even the wrong ones. "We're descended from a
  Huguenot" usually turns out to be half-right in an interesting way.

Photograph every document and photo they have, on the spot, with your phone.
Backs of photographs too — that is where the names are.

## Step 1 — Home sources

Birth, marriage and death certificates. Family bibles (the flyleaf).
Newspaper clippings. Service records. Deeds. School reports. Anything with a
date and a name on it. Photograph everything and enter it.

## Step 2 — The free tier

- **FreeBMD** (freebmd.org.uk) — index to England & Wales civil registration
  from 1837. Volunteer-transcribed, free, excellent.
- **FamilySearch** (familysearch.org) — free with a registration. Enormous.
  Includes digitised parish registers. Its user-submitted tree is **not**
  evidence; treat it as a hint, never as a source.
- **FreeCEN** and **FreeREG** — free census and parish register transcripts.
- **The National Archives Discovery** (discovery.nationalarchives.gov.uk) —
  catalogue of 2,500+ archives. Free to search.
- **Your county record office** — often has free online indexes, and the
  staff will answer a specific question by email.
- **Local and family history societies** — a £15 membership frequently buys
  access to transcripts that exist nowhere else, plus people who know the
  parish intimately.

## Step 3 — The core records, and what each gives you

### Civil registration (England & Wales, from 1 July 1837)
Order certificates from the **GRO** (gro.gov.uk), not third parties — it is
about a third of the price.

Two facts that save enormous time:
- The GRO **birth index gives the mother's maiden name** — from 1837 online,
  which is far earlier than the commercial sites indexed it.
- The GRO **death index gives age at death from 1866**, which converts a
  death into an approximate birth year.

A marriage certificate gives you **both fathers' names and occupations** —
one certificate, two generations. Marriages are the best value in genealogy.

### Census (1841–1921, every ten years, plus the 1939 Register)
- **1841** is the weakest: ages over 15 rounded down to 5, and it only asks
  whether you were born in the county. Do not trust its ages.
- **1851 onward** give exact age, relationship to head, parish of birth.
- **1911** is in the householder's own handwriting, and asks how many
  children were born and how many still living — which reveals children who
  died between censuses and would otherwise be invisible.
- **1921** released 2022. The 1931 census was destroyed by fire; there was no
  1941 census.
- **1939 Register** fills the gap: taken at the outbreak of war, gives exact
  dates of birth.

Scotland's censuses are on ScotlandsPeople and are richer throughout.

### Parish registers (from 1538)
Baptisms, marriages, burials. Coverage before 1600 is patchy and the
Commonwealth period (1642–1660) is badly damaged. Bishop's transcripts are
duplicate copies sent to the diocese and often survive where the original
does not — always check them when a register has a gap.

### Wills and probate
**probatesearch.service.gov.uk** — free index from 1858, and wills are about
£1.50 each. A will names children, grandchildren, in-laws and grudges. It is
the single most information-dense document in genealogy. Pre-1858 wills went
through church courts, mostly the PCC, now at TNA.

### Newspapers
**British Newspaper Archive** (subscription, also via findmypast). Obituaries,
marriage notices, court reports, bankruptcies, inquests. This is where your
ancestors stop being dates and become people.

### Scotland and Ireland
- **ScotlandsPeople** — statutory registers from 1855, pay-per-view, and the
  best-value official genealogy site anywhere. Scottish certificates give far
  more than English ones: marriage records name both mothers too.
- **Ireland**: irishgenealogy.ie (free civil records and church registers)
  and census.nationalarchives.ie (free 1901/1911). Much was destroyed in the
  1922 Four Courts fire, so lean on **Griffith's Valuation** (1847–64) and
  the **Tithe Applotment Books** (1823–37) as census substitutes.

## Step 4 — DNA, when documents run out

**AncestryDNA** has the largest database and the best matching, and is the
usual first choice in the UK. **MyHeritage** is stronger in continental
Europe. **FamilyTreeDNA** does Y-DNA (direct male line) and mtDNA (direct
female line), which are the right tools for a specific surname question.
Upload your raw data free to **GEDmatch** and FamilyTreeDNA to fish in more
ponds for nothing.

Read the **Shared cM Project** ranges before interpreting anything. 850 cM is
consistent with grandparent, half-sibling, aunt/uncle and niece/nephew
simultaneously. Trees built on a single confident guess from one cM figure
are the most common serious error in modern genealogy.

Be prepared, genuinely, for a result you did not expect. Misattributed
parentage turns up in roughly 1–2% of tests, and it lands on real people who
are still alive. Decide in advance how you would handle it.

## Step 5 — Prove it

The **Genealogical Proof Standard** is the professional benchmark and it is
worth adopting even as an amateur:

1. Reasonably exhaustive search — not the first record that fits
2. Complete and accurate citation of every source
3. Analysis and correlation of the evidence
4. Resolution of conflicting evidence — do not just ignore the awkward record
5. A soundly reasoned, coherently written conclusion

In practice: **two independent sources, or a documented explanation of why
one is sufficient.**

## Keeping a research log

Record every search, including failures:

| Date | Question | Source searched | Result |
|---|---|---|---|
| 2026-03-04 | Thomas Whitcombe bapt. c.1801 | Walcot PR 1795–1810 (FS film 1234) | Not found |
| 2026-03-04 | as above | Bathwick PR 1795–1810 | Found: 12 Mar 1801, father John |

The negative result is worth as much as the positive one. Helix has a
`research_task` table for exactly this, and `analysis/gaps.py` will eventually
rank what to search next by how many descendants each gap is blocking.

## Common traps

- **Two men with the same name in one parish.** Extremely common. Track the
  whole sibling group and the occupations to tell them apart.
- **Ages are approximate.** People lied, guessed, and did not know. An age
  in the 1841 census is rounded. An age on a death certificate was supplied
  by someone distraught.
- **Spelling was not fixed.** Whitcombe, Whitcomb, Witcombe, Whitcume are one
  family. Search by sound (Soundex), not by spelling.
- **The 1752 calendar change.** Before then the English year began on 25
  March, so a date written "12 February 1723" means 1724 by our reckoning.
  Written as `1723/24`. Helix parses this correctly.
- **Other people's online trees are not evidence.** They are a hypothesis
  someone else did not check. Use them to find records; cite the records.
- **A gap in a register is not proof of absence.** Check the bishop's
  transcripts, then the neighbouring parishes, then the nonconformist
  chapels.

## A sensible order of work

1. Interview relatives. Record it. *(free, urgent)*
2. Photograph home documents. *(free)*
3. FreeBMD + FamilySearch back to about 1837. *(free)*
4. Census 1841–1921 for every household. *(often free)*
5. Order key certificates from the GRO — marriages first. *(~£12 each)*
6. Parish registers back from 1837 to 1538. *(free–cheap)*
7. Wills for anyone who owned anything. *(£1.50)*
8. Newspapers to turn dates into stories. *(subscription)*
9. DNA when the paper trail stops. *(~£80)*
10. Record offices for anything still unresolved. *(travel)*

Four generations is normally achievable free. The eighteenth century costs a
little. Beyond 1700 you are into wills, manorial records and patience.
