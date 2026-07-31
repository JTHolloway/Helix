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

from ..graph.kinship import Kinship, household, siblings_of

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


def page(title: str, body: str, note: str = "") -> str:
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{esc(title)}</title><style>{CSS}</style></head><body>"
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


def profile(graph, con, pid: str, *, kin: Optional[Kinship] = None,
            photos=None) -> str:
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
  {gallery}
</article>"""


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
    for pid in ids:
        body.append(profile(graph, con, pid, kin=kin,
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
