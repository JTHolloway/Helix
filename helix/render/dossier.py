"""Profiles and a tree outline, on paper.

WHY THIS IS HTML AND NOT A PDF THIS PROGRAM WRITES. Helix writes its own
SVG, PDF, DXF and EPS because a laser chart is GEOMETRY -- lines at
millimetre positions on one sheet -- and hand-writing that is how the
program works on a machine with nothing installed. A profile is not
geometry. It is a document: text that reflows, that runs to eighty pages
for a large family, and that has photographs in it.

`render/pdf.py` writes one page and has no image support, so a dossier
through it would mean adding pagination and an image encoder. The browser
already does both, correctly, with a print dialogue people know, and it is
already open -- this is a local web app. So the printouts are HTML with a
print stylesheet, and "Print" is Ctrl-P. No dependency, photographs work,
and the page breaks land where the CSS says.

WHAT PRINTS. One profile, everybody as a dossier, and the tree as an
indented outline. The outline exists because a chart is a picture and a
picture cannot be read down a column or checked off against a list; the
same family as text is what you take to an archive.
"""
from __future__ import annotations

import html
from typing import Optional

from ..graph.build import union_word
from ..graph.kinship import (Kinship, bloodline, dna_display, heritage_display,
                             heritage_of, household, shared_dna, siblings_of)

CSS = """
:root{--ink:#1a1a1a;--muted:#6b6b6b;--rule:#d8d2c6;--accent:#8a3324}
*{box-sizing:border-box}
body{font:11pt/1.5 Georgia,'Iowan Old Style',serif;color:var(--ink);
     margin:0;padding:0;background:#fff}
.sheet{max-width:180mm;margin:0 auto;padding:14mm 0}
h1{font-size:20pt;margin:0 0 2mm;letter-spacing:.01em}
h2{font-size:13pt;margin:9mm 0 2mm;padding-bottom:1mm;
   border-bottom:1px solid var(--rule);font-weight:600}
h3{font-size:11pt;margin:5mm 0 1mm;font-weight:600}
.sub{color:var(--muted);font-size:10pt;margin:0 0 1mm}
.rel{display:inline-block;background:#f3ede2;border-radius:3px;
     padding:.5mm 2mm;font-size:9.5pt;color:#5a4632}
.who{display:flex;gap:6mm;align-items:flex-start;margin-bottom:4mm}
.who .txt{flex:1}
.portrait{width:34mm;height:44mm;object-fit:cover;border:1px solid var(--rule);
          background:#f6f2ea}
dl{display:grid;grid-template-columns:34mm 1fr;gap:1mm 4mm;margin:0}
dt{color:var(--muted);font-size:9.5pt}
dd{margin:0}
ul{margin:1mm 0;padding-left:5mm}
li{margin:.5mm 0}
.notes{white-space:pre-wrap;background:#faf7f0;border-left:2px solid var(--rule);
       padding:2mm 3mm;margin:2mm 0}
.gallery{display:flex;flex-wrap:wrap;gap:3mm;margin-top:2mm}
.gallery figure{margin:0;width:44mm}
.gallery img{width:100%;border:1px solid var(--rule)}
.gallery figcaption{font-size:8.5pt;color:var(--muted)}
.none{color:var(--muted);font-style:italic}
.plain{list-style:none;padding-left:0;columns:2;font-size:10pt}
.note{color:var(--muted);font-size:9pt;margin:1mm 0 0}
.share{background:#f7f1e8;border-left:2px solid var(--accent);
       padding:2mm 3mm;margin:2mm 0;font-size:10pt}
.share b{font-size:13pt;color:var(--accent)}
.todo{padding-left:5mm;font-size:10pt}
.todo > li{margin:0 0 2mm}
.todo .sub{display:block;margin:0}
.todo ul{font-size:9pt;color:var(--muted)}
.chron{width:100%;border-collapse:collapse;font-size:10pt}
.chron td{padding:1mm 2mm 1mm 0;vertical-align:top;
          border-bottom:1px solid var(--rule)}
.chron .yr{width:16mm;font-variant-numeric:tabular-nums;color:var(--muted)}
.chron .kd{width:22mm;color:var(--muted);font-size:8.5pt;text-transform:uppercase}
.chron tr.gap td{border:0;color:var(--muted);font-style:italic;font-size:9pt;
                 padding-top:3mm}
.counts{display:flex;flex-wrap:wrap;gap:2mm 6mm;font-size:9.5pt;
        color:var(--muted);margin:2mm 0}
.counts b{color:var(--ink);font-weight:600}
.outline{font-size:10pt}
.outline li{list-style:none;margin:.3mm 0}
.outline ul{padding-left:4mm;border-left:1px dotted var(--rule);margin-left:1mm}
.outline .life{color:var(--muted);font-size:9pt}
.outline .mark{color:var(--accent);font-size:8.5pt}
.person{page-break-after:always;break-after:page}
.person:last-child{page-break-after:auto;break-after:auto}
.foot{margin-top:8mm;padding-top:2mm;border-top:1px solid var(--rule);
      color:var(--muted);font-size:8.5pt}
.bar{position:sticky;top:0;background:#fff;border-bottom:1px solid var(--rule);
     padding:3mm 4mm;display:flex;gap:3mm;align-items:center;
     font-family:system-ui,sans-serif;font-size:10pt}
.bar button{font:inherit;padding:1.5mm 4mm;border:1px solid var(--rule);
            border-radius:4px;background:#fff;cursor:pointer}
.bar button.go{background:var(--accent);color:#fff;border-color:var(--accent)}
@media print{
  .bar{display:none}
  .sheet{max-width:none;padding:0}
  a{color:inherit;text-decoration:none}
  @page{margin:16mm 14mm}
}
"""

BAR = """<div class="bar">
  <button class="go" onclick="print()">Print</button>
  <button onclick="history.back()">Back</button>
  <span style="color:#6b6b6b">%s</span>
</div>"""


def esc(s) -> str:
    return html.escape(str(s or ""))


def page(title: str, body: str, note: str = "", extra_css: str = "") -> str:
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{esc(title)}</title><style>{CSS}{extra_css}</style>"
            f"</head><body>"
            f"{BAR % esc(note)}<div class=sheet>{body}</div></body></html>")


# ------------------------------------------------------------- one person --
def _facts(p, extra: list[tuple[str, str]]) -> str:
    rows = [("Born", p.birth.display), ("Born in", p.birth_place),
            ("Died", p.death.display), ("Died in", p.death_place),
            ("Occupation", p.occupation), ("Education", p.education)]
    rows += extra
    rows = [(k, v) for k, v in rows if v]
    if not rows:
        return "<p class=none>Nothing recorded yet.</p>"
    return "<dl>" + "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>"
                            for k, v in rows) + "</dl>"


def _kinlist(graph, ids: list[str], empty: str) -> str:
    if not ids:
        return f"<p class=none>{esc(empty)}</p>"
    out = []
    for pid in ids:
        q = graph.people.get(pid)
        if not q:
            continue
        life = f" <span class=sub>{esc(q.lifespan)}</span>" if q.lifespan else ""
        out.append(f"<li>{esc(q.full_name)}{life}</li>")
    return "<ul>" + "".join(out) + "</ul>"


def _origins(graph, pid: str, declared: Optional[dict] = None) -> str:
    """Where their family came from, on paper.

    Says "worked out" or "recorded" every time. A percentage on a printed
    sheet with no qualification beside it will be read in twenty years as
    something somebody measured, and this is arithmetic over a family tree.
    """
    if declared is None:
        declared = {q: dict(x.heritage) for q, x in graph.people.items()
                    if x.heritage}
    mix = heritage_of(graph, declared, pid)
    if not mix:
        return ""
    rows = heritage_display(mix)
    said = "Recorded for them" if declared.get(pid) else \
           "Worked out from what is recorded further up — a generalisation"
    return ("<h2>Where they came from</h2><ul class=plain>"
            + "".join(f"<li><b>{r['pct']}%</b> {esc(r['label'])}</li>"
                      for r in rows)
            + f"</ul><p class=note>{said}, not a test result.</p>")


def _bloodline(graph, pid: str, subject: Optional[str]) -> str:
    """The direct line with the DNA share at each step, as a table.

    A TABLE AND NOT THE LITTLE TREE THE SCREEN DRAWS. Four generations of
    boxes are 320 pixels wide and legible on a panel; printed, the same
    thing is a postage stamp in the corner of an A4 sheet. On paper the
    seats read down a column, which is also what you can tick off in an
    archive.
    """
    seats = bloodline(graph, pid, depth=4)
    if len(seats) <= 1:
        return ""
    names = ["", "Parents", "Grandparents", "Great-grandparents"]
    out = []
    for gen in range(1, 4):
        here = [s for s in seats if s["gen"] == gen]
        if not any(s["id"] for s in here):
            continue
        pct = dna_display(0.5 ** gen)
        out.append(f"<h3>{names[gen]} — {pct} each</h3><ul>"
                   + "".join(
                       f"<li>{esc(s['name'])}"
                       + (f" <span class=sub>{esc(s['life'])}</span>"
                          if s["life"] else "")
                       + "</li>" if s["id"] else
                       "<li class=none>not known</li>" for s in here)
                   + "</ul>")
    share = shared_dna(graph, subject, pid) if subject and subject != pid else None
    head = ""
    if share is not None:
        who = graph.people[subject].full_name if subject in graph.people else "you"
        head = (f"<p class=share><b>{dna_display(share)}</b> expected shared "
                f"DNA with {esc(who)}. An average, not a measurement — real "
                f"DNA varies either side of it.</p>")
    return "<h2>Bloodline</h2>" + head + "".join(out)


def _next_steps(graph, pid: str) -> str:
    """What is worth going and looking up about this person.

    NOT ON THE PROFILE SHEET. A printed profile is what somebody FILES --
    it goes in a folder with the certificates and is read again in ten
    years, and a to-do list printed onto it is out of date the week after
    it comes off the printer and looks like a reproach for the rest of its
    life. The sheet carries what is known; the research list lives on
    screen, where it is current.

    Kept, and reachable at `/print/research`, because a list of questions
    with the repositories named IS worth taking to a record office -- just
    as its own page and not stapled to somebody's life.
    """
    from ..analysis.gaps import for_person
    gs = for_person(graph, pid)[:4]
    if not gs:
        return ""
    out = []
    for g in gs:
        where = ("<ul>" + "".join(f"<li>{esc(w)}</li>" for w in g["where"])
                 + "</ul>") if g["where"] else ""
        out.append(f"<li><b>{esc(g['question'])}</b>"
                   f"<div class=sub>{esc(g['why'])}</div>{where}</li>")
    return "<h2>Where to look next</h2><ol class=todo>" + "".join(out) + "</ol>"


def profile(graph, con, pid: str, *, kin: Optional[Kinship] = None,
            photos=None, declared=None) -> str:
    """One person, everything known about them, on one sheet."""
    p = graph.people[pid]
    k = kin.of(pid) if kin else None
    counts = household(graph, pid)
    photos = photos or []
    port = next((x for x in photos if x.get("portrait")), None)
    rest = [x for x in photos if x is not port]

    rel = ""
    if k and k.group != "self":
        rel = f"<span class=rel>{esc(k.label)}</span>"
    elif k:
        rel = "<span class=rel>whose chart this is</span>"

    img = (f"<img class=portrait src='/api/media?name={esc(port['name'])}' "
           f"alt='{esc(p.full_name)}'>") if port else ""

    fams = []
    for uid in p.unions:
        u = graph.unions.get(uid)
        if not u:
            continue
        others = [x for x in u.partners if x != pid]
        who = (graph.people[others[0]].full_name
               if others and others[0] in graph.people else "Unknown")
        kids = [c for c in u.children if c in graph.people]
        fams.append(f"<h3>With {esc(who)}</h3>"
                    + _kinlist(graph, kids, "No children recorded."))

    gallery = ""
    if rest:
        gallery = ("<h2>Photographs</h2><div class=gallery>" + "".join(
            f"<figure><img src='/api/media?name={esc(x['name'])}'>"
            f"<figcaption>{esc(x.get('caption') or '')}</figcaption></figure>"
            for x in rest) + "</div>")

    return f"""<article class=person>
  <div class=who>
    {img}
    <div class=txt>
      <h1>{esc(p.full_name)}</h1>
      <p class=sub>{esc(p.lifespan or 'dates unknown')}
        {'· lived ' + esc(p.age) if p.age else ''}</p>
      {rel}
      <div class=counts>
        <span><b>{counts['siblings']}</b> brothers and sisters</span>
        <span><b>{counts['children']}</b> children</span>
        <span><b>{counts['ancestors_known']}</b> ancestors recorded</span>
        <span><b>{counts['descendants_known']}</b> descendants recorded</span>
        {f"<span><b>{k.steps}</b> steps from you</span>" if k and k.steps < 99 else ""}
      </div>
    </div>
  </div>
  <h2>What is known</h2>
  {_facts(p, [])}
  {f'<div class=notes>{esc(p.notes)}</div>' if p.notes else ''}
  <h2>Family</h2>
  <h3>Parents</h3>
  {_kinlist(graph, graph.parents(pid, primary_only=False), 'Nobody recorded yet.')}
  <h3>Brothers and sisters</h3>
  {_kinlist(graph, siblings_of(graph, pid), 'None recorded.')}
  {''.join(fams) or ''}
  {_origins(graph, pid, declared)}
  {_bloodline(graph, pid, kin.subject if kin else None)}
  {gallery}
</article>"""


def research(graph, gaps: list[dict], *, title="") -> str:
    """The questions worth asking, as a page you take to a record office.

    ITS OWN SHEET AND NOT STAPLED TO A PROFILE. A profile is filed and read
    again in ten years; a research list is out of date the week after it is
    printed. Kept apart, each one can be printed when it is wanted.
    """
    body = [f"<h1>{esc(title or 'Where to look next')}</h1>",
            f"<p class=sub>{len(gaps)} questions, the ones that unblock the "
            f"most people first. Tick them off as you go.</p>"]
    for g in gaps:
        where = ("<ul>" + "".join(f"<li>{esc(w)}</li>" for w in g["where"])
                 + "</ul>") if g.get("where") else ""
        who = " · ".join(x for x in [g.get("relation"), g.get("life")] if x)
        body.append(
            f"<li><b>☐ {esc(g['question'])}</b>"
            f"{f'<div class=sub>{esc(who)}</div>' if who else ''}"
            f"<div class=sub>{esc(g['why'])}</div>{where}</li>")
    return page(title or "Where to look next",
                body[0] + body[1] + "<ol class=todo>"
                + "".join(body[2:]) + "</ol>", note=title)


def chronicle(graph, tl: dict, *, title="") -> str:
    """Every birth, marriage and death, in order, on paper.

    THE FAMILY AS A DOCUMENT. A chart is a picture and cannot be read down a
    column; this is the same family as a chronology, which is what you check
    against a parish register.
    """
    body = [f"<h1>{esc(title or 'The family, in order')}</h1>"]
    if tl.get("span"):
        c = tl["counts"]
        body.append(f"<p class=sub>{tl['span'][0]}–{tl['span'][1]} · "
                    f"{c['birth']} births, {c['marriage']} marriages, "
                    f"{c['death']} deaths</p>")
    quiet = {g["from"]: g for g in tl.get("quiet", [])}
    body.append("<table class=chron><tbody>")
    for e in tl["events"]:
        if e["year"] in quiet:
            body.append(f"<tr class=gap><td colspan=3>nothing recorded for "
                        f"{quiet[e['year']]['years']} years</td></tr>")
        body.append(
            f"<tr><td class=yr>{e['year']}</td>"
            f"<td class=kd>{esc(e['kind'])}</td>"
            f"<td>{esc(e['what'])}"
            + (f" <span class=sub>{esc(e['detail'])}</span>"
               if e.get("detail") else "")
            + f"<div class=sub>{esc(e['date'])}</div></td></tr>")
    body.append("</tbody></table>")
    return page(title or "The family, in order", "".join(body), note=title)


# ------------------------------------------------------ the record book --
RECORD_CSS = """
.rb{font:11pt/1.55 Georgia,'Iowan Old Style',serif}
.rbcover{text-align:center;padding:38mm 0 0}
.rbcover h1{font-size:30pt;letter-spacing:.02em;margin:0 0 3mm}
.rbcover .rule{width:56mm;height:1px;background:var(--ink);margin:6mm auto}
.rbcover p{color:var(--muted);font-size:11pt;margin:1mm 0}
.rbcover .crest{font-size:40pt;line-height:1;margin-bottom:6mm;
                letter-spacing:.3em;color:var(--accent)}
.rbtoc{columns:2;column-gap:10mm;font-size:10pt;list-style:none;padding:0}
.rbtoc li{break-inside:avoid;margin:.4mm 0}
.rbtoc .n{color:var(--muted);display:inline-block;width:9mm}
/* ONE PERSON, ONE SHEET. A binder is filed, added to and pulled apart:
   somebody wants the page for their grandmother, and if two other people
   are on the back of it they cannot have it. So every entry starts a
   page — and a life with a great deal written about it runs on to a
   second and a third rather than being cut to fit. */
/* EVERY entry starts a page, the first one included. It used to run on
   from the bottom of the contents, which put one person on a page that is
   not theirs and made the contents look like the start of the record. */
.entry{page-break-before:always;break-before:page;
       padding-top:2mm;display:flex;flex-direction:column;min-height:238mm}
.entry > .grow{flex:1}
.entry h2{border:0;margin:0 0 1mm;font-size:19pt;display:flex;
          align-items:baseline;gap:3mm;letter-spacing:.01em}
.entry h2 .no{color:var(--muted);font-size:11pt;font-weight:400;
              min-width:9mm}
.entry .sub{font-size:11pt}
.entry .hr{height:1px;background:var(--rule);margin:3mm 0 4mm}
.entry .body{display:flex;gap:7mm;align-items:flex-start}
.entry .txt{flex:1;min-width:0}
.entry .port{width:42mm;height:53mm;object-fit:cover;
             border:1px solid var(--rule);background:#f6f2ea}
/* A record with a face on it is worth more than one without, so the
   absence is marked rather than left as a gap in the layout. */
.entry .noport{display:flex;align-items:center;justify-content:center;
               text-align:center;color:#a8a094;font-size:9pt;
               font-style:italic;padding:3mm}
.rbfacts{display:grid;grid-template-columns:34mm 1fr;gap:0 4mm;
         margin:0 0 2mm;font-size:10.5pt}
.rbfacts dt{color:var(--muted);font-size:9.5pt;padding:1mm 0 1mm 0;
            border-bottom:1px solid #efe9dd}
.rbfacts dd{margin:0;padding:1mm 0;border-bottom:1px solid #efe9dd}
.rbfacts dt:last-of-type,.rbfacts dd:last-of-type{border-bottom:0}
/* What is not known is SAID. A blank on a filed record is ambiguous
   forever -- nobody can tell an unknown birthplace from an unfinished
   one -- and "Unknown" is also the only thing that says where the work
   still is. Set in the same size as a fact, greyed, not italic: it is a
   statement, not an apology. */
.unk{color:#9a9284}
.yrs{color:var(--muted);font-size:9pt;white-space:nowrap}
.rbnote-lead{color:var(--muted);font-size:9.5pt;margin:0 0 3mm}
.rbsec{font-size:9pt;letter-spacing:.09em;text-transform:uppercase;
       color:var(--muted);margin:5mm 0 1.5mm;border-bottom:1px solid var(--rule);
       padding-bottom:.8mm}
.rbrel{font-size:10.5pt;margin:1.5mm 0 0}
.rbrel b{color:var(--muted);font-weight:400;font-size:9.5pt;
         display:block;letter-spacing:.04em}
.rbnote{white-space:pre-wrap;font-size:10.5pt;margin:1.5mm 0 0}
.rbpapers{font-size:9.5pt;color:var(--muted);margin:1.5mm 0 0}
/* The foot of the sheet, so a page that has come loose can be put back. */
.rbfoot{display:flex;justify-content:space-between;font-size:8.5pt;
        color:var(--muted);border-top:1px solid var(--rule);
        padding-top:1.5mm;margin-top:5mm}
.rbindex{font-size:9.5pt;columns:2;column-gap:10mm}
.rbindex div{break-inside:avoid}
.newpage{page-break-before:always;break-before:page}
@media print{.rbcover{padding-top:50mm}}
/* ON SCREEN there are no pages, so the sheet boundaries have to be drawn or
   the contents looks like the first entry runs on from it. Printed, these
   rules do nothing and the real page breaks take over. */
@media screen{
  .rb .newpage,.rb .entry{border-top:1px solid var(--rule);
    margin-top:14mm;padding-top:10mm}
  .rb .entry{min-height:0}
}
"""


def _rb_order(graph, ids: list[str]) -> list[str]:
    """The order a family history is read in: oldest first, family by family.

    NOT CLOSEST-TO-YOU. That order is right for a sidebar, where the
    question is "where is my sister", and wrong for a folder that outlives
    the person who made it: whoever it was centred on stops being the
    obvious place to start the moment somebody else picks it up. It is also
    the order that puts a man on page 40 and his own children on pages 3
    and 91.

    So the record reads the way a printed genealogy has always read. Start
    at the earliest people the file knows about; give each of them a page;
    then their children, each followed immediately by that child's own
    descendants. A family stays together and a generation runs downwards,
    which means the page after somebody is nearly always a page about
    somebody they knew.
    """
    want = [p for p in ids if p in graph.people]
    left = set(want)
    out: list[str] = []

    def year(pid) -> float:
        p = graph.people[pid]
        return (p.birth.sort_value if p.birth.known and p.birth.sort_value
                else (p.death.sort_value or 0) - 60 or 9e9)

    def walk(pid: str, guard: int = 0) -> None:
        if pid not in left or guard > 40:
            return
        left.discard(pid)
        out.append(pid)
        # Husbands and wives come with the person they married, so a couple
        # is never split across a generation boundary.
        for uid in graph.people[pid].unions:
            u = graph.unions.get(uid)
            if not u:
                continue
            for mate in u.partners:
                if mate in left:
                    left.discard(mate)
                    out.append(mate)
        for uid in graph.people[pid].unions:
            u = graph.unions.get(uid)
            if not u:
                continue
            for kid in sorted((c for c in u.children if c in left), key=year):
                walk(kid, guard + 1)

    # The founders: everybody in the cast with no parent who is also in it.
    roots = [p for p in want
             if not any(x in left for x in graph.parents(p, primary_only=False))]
    for pid in sorted(roots, key=year):
        walk(pid)
    # Anything the walk could not reach -- a person with no links at all.
    out.extend(sorted(left, key=lambda p: (graph.people[p].surname or "",
                                           graph.people[p].given or "")))
    return out


# WHAT IS NOT KNOWN IS SAID, NOT LEFT OUT.
#
# A blank line on a filed record is ambiguous forever: in thirty years
# nobody can tell whether the birthplace was unknown or whether the person
# filling it in got bored. "Unknown" is a statement about the research, and
# it is also the only thing that tells somebody where the work still is.
UNKNOWN = '<span class=unk>Unknown</span>'
NONE_REC = '<span class=unk>None recorded</span>'


def _or_unknown(v, blank: str = UNKNOWN) -> str:
    v = (v or "").strip() if isinstance(v, str) else v
    return esc(v) if v else blank


def record_book(graph, con, ids, *, kin=None, photos_for=None, title="",
                subtitle="", covers=True) -> str:
    """Every person, everything known about them, as a folder.

    WHAT AN OFFICIAL RECORD IS. The thing that goes in a ring binder and is
    read by somebody in thirty years who never met anybody in it. One page
    per person, so a page can be taken out and handed over; every field
    present whether or not it is filled in, because a blank is ambiguous
    forever and "Unknown" is a statement about the research; and the
    photograph, because a name with a face beside it is a person.

    WHAT IS DELIBERATELY LEFT OUT. The inbreeding coefficient, the DNA
    percentages, the completeness score and the research list. Those are
    working numbers -- arithmetic over the file as it stands today, changing
    the moment a grandparent is added -- and on a filed document they read
    as findings rather than as the working notes they are. What goes in the
    binder is what is KNOWN.
    """
    people = _rb_order(graph, list(ids))
    order = {pid: i + 1 for i, pid in enumerate(people)}
    # ONE PERSON'S OFFICIAL RECORD is the same sheet without the apparatus.
    # A cover page, a contents and an index for a single entry would be
    # four sheets of stationery around one fact.
    covers = covers and len(people) > 1
    declared = {q: dict(x.heritage) for q, x in graph.people.items() if x.heritage}

    def nm(pid) -> str:
        """A person named in somebody else's entry.

        NO BRACKETED NUMBER AFTER THE NAME. It was there so the binder could
        be followed without the program that made it, and it made every page
        read like a database dump -- "Reuben Ashworth [2], Winifred Threlfall
        [3]" is not how anybody writes about their family. The contents and
        the index are where numbers belong; a name in a sentence is a name.
        """
        if pid not in graph.people:
            return UNKNOWN
        p = graph.people[pid]
        life = p.lifespan
        return esc(p.full_name) + (f" <span class=yrs>{esc(life)}</span>"
                                   if life else "")

    body = [f"<div class=rb>"]

    # ---- the cover
    if covers:
        body.append(
        "<div class=rbcover>"
        "<div class=crest>&#10022;</div>"
        f"<h1>{esc(title or 'Family Records')}</h1>"
        "<div class=rule></div>"
        f"<p>{esc(subtitle) if subtitle else ''}</p>"
        f"<p>{len(people)} people, "
        f"{len([u for u in graph.unions.values() if any(x in order for x in u.partners)])}"
        f" families</p>"
        f"<p>Compiled {__import__('datetime').date.today().strftime('%d %B %Y')}"
        "</p></div>")

        # ---- the contents, on its own page, with nothing else on it
        body.append("<div class=newpage><h2>Contents</h2>"
                    "<p class=rbnote-lead>One page each, oldest first, family "
                    "by family.</p><ol class=rbtoc>")
        for pid in people:
            p = graph.people[pid]
            body.append(f"<li><span class=n>{order[pid]}</span> "
                        f"{esc(p.full_name)}"
                        + (f" <span class=sub>{esc(p.lifespan)}</span>"
                           if p.lifespan else "") + "</li>")
        body.append("</ol></div>")

    # ---- the entries, one page each
    for pid in people:
        p = graph.people[pid]
        pics = [x for x in (photos_for(pid) if photos_for else [])
                if x.get("kind", "photo") == "photo"]
        # The portrait if one is chosen, otherwise any photograph there is:
        # a record with a face on it is worth more than a rule about which
        # face.
        port = next((x for x in pics if x.get("portrait")), pics[0] if pics else None)
        papers = [x for x in (photos_for(pid) if photos_for else [])
                  if x.get("kind", "photo") != "photo"]
        img = (f"<img class=port src='/api/media?name={esc(port['name'])}' "
               f"alt='{esc(p.full_name)}'>") if port else \
            "<div class='port noport'>No photograph</div>"

        # ---- the life. EVERY row, filled in or not.
        life_rows = [
            ("Born", _or_unknown(p.birth.display)),
            ("Born in", _or_unknown(p.birth_place)),
            ("Died", "<span class=unk>Living</span>"
             if (p.living is True and not p.death.known)
             else _or_unknown(p.death.display)),
            ("Died in", _or_unknown(p.death_place)),
            ("Age", _or_unknown(p.age)),
            ("Occupation", _or_unknown(p.occupation)),
            ("Education", _or_unknown(p.education)),
        ]
        own = declared.get(pid) or {}
        life_rows.append(
            ("Family origin",
             ", ".join(esc(k) for k in own) if own else UNKNOWN))

        # ---- the family. Parents, brothers and sisters, each marriage.
        pars = [x for x in graph.parents(pid, primary_only=False)
                if x in graph.people]
        fam = [("Father", next((nm(x) for x in pars
                                if graph.people[x].sex == "M"), UNKNOWN)),
               ("Mother", next((nm(x) for x in pars
                                if graph.people[x].sex == "F"), UNKNOWN))]
        other = [x for x in pars if graph.people[x].sex not in ("M", "F")]
        if other:
            fam.append(("Parent", ", ".join(nm(x) for x in other)))
        sibs = [x for x in siblings_of(graph, pid) if x in graph.people]
        fam.append(("Brothers and sisters",
                    ", ".join(nm(x) for x in sibs) if sibs else NONE_REC))

        marriages = []
        for uid in p.unions:
            u = graph.unions.get(uid)
            if not u:
                continue
            others = [x for x in u.partners if x != pid and x in graph.people]
            kids = [x for x in u.children if x in graph.people]
            head = union_word(u).capitalize()
            rows = [(head, nm(others[0]) if others else UNKNOWN),
                    ("Date", _or_unknown(u.date.display)),
                    ("Place", _or_unknown(u.place)),
                    ("Children", ", ".join(nm(x) for x in kids)
                     if kids else NONE_REC)]
            marriages.append(rows)
        if not marriages:
            marriages = [[("Married", NONE_REC)]]

        # ---- anything else anybody recorded as an event
        extra = []
        for r in con.execute(
            "SELECT e.type,e.date_json,e.description,pl.name place "
            "FROM event e JOIN event_role er ON er.event_id=e.id "
            "LEFT JOIN place pl ON pl.id=e.place_id WHERE er.person_id=? "
            "ORDER BY e.date_sort", (pid,)
        ):
            if r["type"] in ("birth", "death", "occupation", "education"):
                continue                       # already above, in their own rows
            from ..model.gendate import GenDate as _GD
            d = _GD.from_json(r["date_json"])
            extra.append((r["type"].replace("_", " ").capitalize(),
                          " · ".join(x for x in (d.display, r["place"] or "",
                                                 r["description"] or "") if x)
                          or UNKNOWN))

        def dl(rows, cls="rbfacts"):
            return (f"<dl class={cls}>" + "".join(
                f"<dt>{esc(k)}</dt><dd>{v}</dd>" for k, v in rows) + "</dl>")

        body.append(
            "<article class=entry>"
            # NO "YOUR UNCLE" ON A FILED RECORD. Every relation in the
            # program is measured from one person, and in thirty years
            # nobody reading this folder is that person. The relations that
            # belong here are the ones stated outright -- father, mother,
            # married to -- and they are all below.
            + (f"<h2><span class=no>{order[pid]}</span> {esc(p.full_name)}</h2>"
               if covers else f"<h2>{esc(p.full_name)}</h2>")
            + f"<p class=sub>"
            + (esc(p.lifespan) if p.lifespan else "Dates unknown")
            + "</p><div class=hr></div>"
            + f"<div class=body>{img}<div class=txt>"
            + "<p class=rbsec>Life</p>" + dl(life_rows)
            + "<p class=rbsec>Parents and family</p>" + dl(fam)
            + "".join("<p class=rbsec>" + ("Marriage" if len(marriages) == 1
                                           else f"Marriage {i + 1}")
                      + "</p>" + dl(m)
                      for i, m in enumerate(marriages))
            + (("<p class=rbsec>Other records</p>" + dl(extra)) if extra else "")
            + "<p class=rbsec>What is known about them</p>"
            + (f"<div class=rbnote>{esc(p.notes)}</div>"
               if (p.notes or "").strip()
               else '<p class=rbnote><span class=unk>Nothing written down '
                    'yet</span></p>')
            + ("<p class=rbsec>Papers on file</p><p class=rbpapers>"
               + ", ".join(esc(x.get("caption") or x["name"]) for x in papers)
               + "</p>" if papers else "")
            + "</div></div><div class=grow></div>"
            + "<div class=rbfoot><span>"
            + esc(title or "Family Records") + "</span><span>"
            + (f"{esc(p.full_name)} &middot; page {order[pid]} of "
               f"{len(people)}" if covers else
               esc(__import__("datetime").date.today().strftime("%d %B %Y")))
            + "</span></div></article>")

    # ---- the index, by surname
    if not covers:
        body.append("</div>")
        return page(title or "Family Records", "".join(body),
                    note=title, extra_css=RECORD_CSS)
    body.append("<div class=newpage><h2>Index of names</h2>"
                "<p class=rbnote-lead>The number is the page.</p>"
                "<div class=rbindex>")
    by_sur: dict = {}
    for pid in people:
        p = graph.people[pid]
        by_sur.setdefault((p.surname or "—").upper(), []).append(pid)
    for sur in sorted(by_sur):
        entries = sorted(by_sur[sur],
                         key=lambda x: graph.people[x].given or "")
        body.append(f"<div><b>{esc(sur)}</b><br>" + "<br>".join(
            f"{esc(graph.people[x].given or '—')} "
            f"<span class=sub>{order[x]}</span>" for x in entries) + "</div>")
    body.append("</div></div></div>")

    return page(title or "Family Records", "".join(body),
                note=title, extra_css=RECORD_CSS)


CHART_CSS = """
.chartsheet{text-align:center}
.chartsheet svg{width:100%;height:auto;max-height:245mm;display:block;
                margin:0 auto}
.chartcap{margin-top:6mm;color:var(--muted);font-size:9.5pt;
          border-top:1px solid var(--rule);padding-top:2mm;
          display:flex;justify-content:space-between;gap:6mm}
.chartcap b{color:var(--ink);font-weight:600}
@media print{
  /* THE SHEET IS THE CHART'S OWN SHAPE. A metre-square disc on a portrait
     page is a disc with a third of the paper wasted under it, and a wide
     fan on a portrait page comes out unreadable. */
  @page{size:__PAGE__;margin:12mm}
  .chartsheet svg{max-height:none}
}
"""


def chart(svg: str, *, title: str = "", people: int = 0, span: str = "",
          landscape: bool = False, note: str = "") -> str:
    """The chart itself, on paper.

    NOT AN EXPORT. `Export → SVG` gives the file to send to a laser cutter,
    at the millimetre sizes the panel needs. This is the picture on A4 or A3
    with a caption under it, which is what somebody wants when they mean
    "print the tree" — to put on a wall, take to an aunt, or check against a
    parish register with a pencil.
    """
    import datetime
    cap = " · ".join(x for x in (
        f"<b>{esc(title)}</b>" if title else "",
        f"{people} people" if people else "",
        esc(span)) if x)
    return page(title or "Family tree",
                f"<div class=chartsheet>{svg}"
                f"<div class=chartcap><span>{cap}</span>"
                f"<span>{datetime.date.today().strftime('%d %B %Y')}</span>"
                f"</div></div>",
                note=note or title,
                extra_css=CHART_CSS.replace(
                    "__PAGE__", "A4 landscape" if landscape else "A4"))


def one(graph, con, pid: str, *, kin=None, photos=None, title="") -> str:
    p = graph.people[pid]
    return page(p.full_name or "Profile",
                profile(graph, con, pid, kin=kin, photos=photos),
                note=title)


def everybody(graph, con, ids: list[str], *, kin=None, photos_for=None,
              title="") -> str:
    """The whole family as a dossier, one person per sheet.

    Ordered the way the sidebar orders them -- closest first -- so the
    people somebody actually wants are at the front of the pile rather than
    wherever the alphabet put them.
    """
    body = [f"<h1>{esc(title or 'Family profiles')}</h1>"
            f"<p class=sub>{len(ids)} people. One to a page.</p>"
            f"<div style='page-break-after:always;break-after:page'></div>"]
    # Gathered once. Read per person it is a scan of the whole file for each
    # of four hundred sheets, which turned "print everybody" into a wait.
    declared = {q: dict(x.heritage) for q, x in graph.people.items()
                if x.heritage}
    for pid in ids:
        body.append(profile(graph, con, pid, kin=kin, declared=declared,
                            photos=(photos_for(pid) if photos_for else [])))
    return page(title or "Family profiles", "".join(body), note=title)


# ------------------------------------------------------------ the outline --
def outline(graph, roots: list[str], *, kin=None, elided=None,
            title="") -> str:
    """The family as an indented list, descendants under their parents.

    A chart is a picture, and a picture cannot be read down a column or
    ticked off against a list. This is the same family as text: what you
    take to an archive, hand to a relative who wants to check it, or read
    aloud to somebody who remembers the names.
    """
    elided = elided or {}
    seen: set[str] = set()

    def branch(pid: str, depth: int) -> str:
        if pid in seen or depth > 25:
            return ""
        seen.add(pid)
        p = graph.people[pid]
        k = kin.of(pid) if kin else None
        life = f" <span class=life>{esc(p.lifespan)}</span>" if p.lifespan else ""
        rel = (f" <span class=life>· {esc(k.label)}</span>"
               if k and k.group not in ("self", "unrelated") else "")
        rows = []
        for uid in p.unions:
            u = graph.unions.get(uid)
            if not u:
                continue
            mates = [x for x in u.partners if x != pid and x in graph.people]
            if mates:
                m = graph.people[mates[0]]
                seen.add(mates[0])
                rows.append(f"<li>= {esc(m.full_name)}"
                            f"{f' <span class=life>{esc(m.lifespan)}</span>' if m.lifespan else ''}"
                            f"</li>")
            kids = [c for c in u.children if c in graph.people]
            rows.extend(branch(c, depth + 1) for c in kids)
            gone = elided.get(uid)
            if gone:
                rows.append(f"<li><span class=mark>"
                            f"+{gone} more, not on this chart</span></li>")
        inner = f"<ul>{''.join(rows)}</ul>" if rows else ""
        return f"<li><b>{esc(p.full_name)}</b>{life}{rel}{inner}</li>"

    body = (f"<h1>{esc(title or 'Family outline')}</h1>"
            f"<p class=sub>Everyone on the chart, descendants indented under "
            f"their parents. A partner is marked <b>=</b>.</p>"
            f"<ul class=outline>"
            + "".join(branch(r, 0) for r in roots) + "</ul>")
    left = [p for p in graph.people if p not in seen]
    if left:
        body += ("<h2>Not reached from the founders</h2>"
                 + _kinlist(graph, left, ""))
    return page(title or "Family outline", body, note=title)
