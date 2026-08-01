"""Command line interface. Everything the app can do is scriptable, so any
chart you make is reproducible from a single command."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .graph import build as gbuild
from .layout import registry
from .layout.base import LayoutSettings
from .layout.engines import family, linear, network, radial  # noqa: F401
from .render import svg as svgrender
from .store.db import connect, get_setting, set_setting


def cmd_init(a):
    con = connect(a.db)
    set_setting(con, "project_title", a.title or Path(a.db).stem)
    print(f"Created {a.db}. Next: helix sample {a.db}   (or import a GEDCOM)")


def cmd_sample(a):
    import subprocess
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, str(root / "tools" / "make_sample.py"),
                    a.db, "--people", str(a.people)], check=True)


def cmd_designs(a):
    rows = registry.all_designs()
    if a.json:
        print(json.dumps([{"key": d.key, "name": d.name, "family": d.family,
                           "blurb": d.blurb, "good_for": d.good_for,
                           "laser": d.laser} for d in rows], indent=2))
        return
    fam = None
    for d in rows:
        if d.family != fam:
            fam = d.family
            print(f"\n{fam.upper()}")
        print(f"  {d.key:<18} {d.name:<22} laser: {d.laser}")
        print(f"  {'':<18} {d.blurb}")


def cmd_styles(a):
    from .style.tokens import Style
    for s in Style.list_presets():
        print(f"  {s['id']:<16} {s['name']:<22} engine: {s['engine']}")


def cmd_render(a):
    from .style.tokens import Style
    con = connect(a.db, create=False)
    style = Style.load(a.style)
    if a.design:
        style.set("layout.engine", a.design)
    if a.diameter:
        style.set("canvas.width_mm", a.diameter)
        style.set("canvas.height_mm", a.diameter)
    if getattr(a, "panel", None):
        try:
            w, h = (float(x) for x in a.panel.lower().split("x"))
        except ValueError:
            raise SystemExit(f"--panel wants something like 1000x1000, "
                             f"not '{a.panel}'")
        style.set("canvas.width_mm", w)
        style.set("canvas.height_mm", h)
    if getattr(a, "ring_pitch", None):
        style.set("layout.min_ring_pitch_mm", a.ring_pitch)
    if a.title:
        style.set("ornament.title", a.title)
    for pair in getattr(a, "set", None) or []:
        if "=" not in pair:
            raise SystemExit(f"--set wants name=value, not '{pair}'. "
                             f"Try --set thread.enabled=false")
        k, v = pair.split("=", 1)
        style.set(k.strip(), _coerce(v.strip()))
    graph = gbuild.load(con)
    subject = a.subject or get_setting(con, "subject_person_id")
    engine = style.get("layout.engine", "radial_sunburst")
    s = LayoutSettings(engine=engine, subject_id=subject,
                       max_generations=a.max_generations,
                       focus=a.focus, max_people=a.max_people,
                       weight_mode=style.get("layout.weight_mode", "leaves"))
    plan = registry.run(engine, graph, s, style)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    _write(plan, out, production=a.production, style=style)
    print(f"{out}  |  {plan.meta.people} people, {plan.meta.generations} "
          f"generations, {plan.meta.year_min}-{plan.meta.year_max}, "
          f"{len(plan.elements)} shapes")
    if a.production:
        _production_report(plan, style)
    fit = plan.meta.extra.get("fit")
    if fit:
        verdict = "fits" if fit["fits"] else f"OVER by {fit['shortfall_mm']:.0f} mm"
        print(f"  panel {fit['panel_mm']:.0f} mm | needs "
              f"{fit['required_mm']:.0f} mm | {verdict} | rings "
              f"{fit['ring_pitch_mm']:.0f} mm apart "
              f"({fit['ring_pitch_mm'] / 25.4:.1f} inch)")
    for w in plan.meta.warnings:
        print("  ! " + w)


def _coerce(v: str):
    """`--set` values arrive as text. A token that wants a number or a flag
    must not silently receive the string "false", which is true."""
    low = v.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    for cast in (int, float):
        try:
            return cast(v)
        except ValueError:
            pass
    if v[:1] in "[{":
        import json
        try:
            return json.loads(v)
        except ValueError:
            pass
    return v


def _production_report(plan, style) -> None:
    """What the operator needs before the lid goes down.

    Printed, not hidden behind a flag: the whole point of `--production` is
    that nothing is left for somebody to remember to check.
    """
    from .fab import islands
    from .fab.preflight import preflight
    baked = plan.meta.extra.get("text_to_paths")
    if baked:
        print(f"  text  | {baked['strokes']} strokes in '{baked['face']}' — "
              f"no live text left in the file")
    print("  " + islands.check(plan).summary().replace("Island check: ",
                                                       "cut   | "))
    bad = 0
    for f in preflight(plan, style):
        if f.level == "pass":
            continue
        bad += f.level == "fail"
        print(f"  {f.level:5s} | {f.title}: {f.detail}")
        if f.fix:
            print(f"        | {f.fix}")
    print("  ready |" + (" pre-flight passed" if not bad else
                         f" {bad} thing(s) to fix before cutting"))


def _write(plan, out: Path, *, production: bool = False, style=None) -> None:
    """One place decides what a file extension means."""
    if production:
        # Text becomes geometry BEFORE any writer sees it. Do it here and
        # every format gets it; do it in the writers and four of them have to
        # agree about what a letter is.
        from .fab import textpath
        textpath.bake(plan, style)
    ext = out.suffix.lower()
    if ext == ".json":
        out.write_text(plan.to_json(indent=2))
    elif ext == ".pdf":
        from .render import pdf as pdfrender
        pdfrender.write(plan, out, production=production)
    elif ext == ".dxf":
        from .render import dxf as dxfrender
        dxfrender.write(plan, out, production=production)
    elif ext in (".eps", ".ps"):
        from .render import eps as epsrender
        epsrender.write(plan, out, production=production)
    else:
        out.write_text(svgrender.render(plan, production=production,
                                        interactive=False))


def cmd_samples(a):
    """Render every working design to SVG and PDF, plus a contact sheet.

    This is what to run when you want to SEE the options rather than read
    about them. It is also the command the bootstrap script calls, so a fresh
    copy of Helix proves itself the first time it is run.
    """
    from .style.tokens import Style
    con = connect(a.db, create=False)
    graph = gbuild.load(con)
    subject = get_setting(con, "subject_person_id")
    outdir = Path(a.out)
    (outdir / "svg").mkdir(parents=True, exist_ok=True)
    (outdir / "pdf").mkdir(parents=True, exist_ok=True)
    made, skipped = [], []

    for d in registry.all_designs():
        style = Style.load(_style_for(d.key))
        style.set("layout.engine", d.key)
        if a.title:
            style.set("ornament.title", a.title)
        s = LayoutSettings(engine=d.key, subject_id=subject,
                           max_generations=a.max_generations, focus=a.focus)
        try:
            plan = registry.run(d.key, graph, s, style)
        except NotImplementedError:
            skipped.append(d)
            continue
        except Exception as e:
            print(f"  {d.key:<18} could not be drawn: {e}")
            continue
        svg_p = outdir / "svg" / f"{d.key}.svg"
        pdf_p = outdir / "pdf" / f"{d.key}.pdf"
        _write(plan, svg_p)
        _write(plan, pdf_p)
        made.append((d, plan, svg_p, pdf_p))
        print(f"  {d.key:<18} {plan.meta.people:>5} people  "
              f"{len(plan.elements):>5} shapes  ->  pdf/{pdf_p.name}")

    (outdir / "index.html").write_text(_samples_html(made, skipped, a.title))
    for d in skipped:
        print(f"  {d.key:<18} {'':>5}         not built yet ({d.name})")
    print(f"\n  {len(made)} designs rendered to {outdir}/")
    print(f"  Open {outdir / 'index.html'} to compare them.")


def _style_for(design_key: str) -> str | None:
    """Pair each design with the preset that shows it at its best."""
    return {
        "radial_sunburst": "labyrinth", "radial_rings": "panel1m",
        "radial_organic": "botanical", "radial_lifeline": "lifelines",
        "metro_map": "tubemap", "timeline_lanes": "timeline",
        "dendrogram": "blueprint", "circle_pack": "nested",
    }.get(design_key)


def _samples_html(made, skipped, title) -> str:
    cards = "".join(
        f'<figure><a href="svg/{s.name}"><img src="svg/{s.name}" loading="lazy"></a>'
        f'<figcaption><b>{d.name}</b> <em>{d.family}</em>'
        f'<p>{d.blurb}</p>'
        f'<p class="g">Good for: {d.good_for}</p>'
        f'<p class="m">{p.meta.people} people &middot; '
        f'{p.canvas.width_mm:.0f}&times;{p.canvas.height_mm:.0f} mm &middot; '
        f'laser: {d.laser}</p>'
        f'<p><a href="pdf/{pd.name}">PDF</a> &middot; '
        f'<a href="svg/{s.name}">SVG</a> &middot; <code>{d.key}</code></p>'
        f'</figcaption></figure>' for d, p, s, pd in made)
    # Empty now that all twenty draw. Kept rather than deleted so that a
    # half-finished design added later lands here instead of in the grid.
    todo = "".join(f"<li><b>{d.name}</b> <code>{d.key}</code> — {d.blurb}</li>"
                   for d in skipped)
    todo_section = f"<h2>Specified, not yet built</h2><ul>{todo}</ul>" if todo else ""
    return f"""<!doctype html><meta charset=utf-8>
<title>Helix — design samples</title>
<style>
 body{{font:16px/1.6 'Atkinson Hyperlegible',system-ui,sans-serif;
   background:#14130F;color:#EDE7DA;margin:0;padding:40px}}
 h1{{font-weight:500;margin:0 0 6px}} h2{{font-weight:500;margin:48px 0 12px}}
 .sub{{color:#9C9482;margin:0 0 28px}}
 .grid{{display:grid;gap:26px;grid-template-columns:repeat(auto-fill,minmax(400px,1fr))}}
 figure{{margin:0;background:#FBF8F2;border-radius:10px;overflow:hidden}}
 img{{width:100%;display:block;background:#FBF8F2}}
 figcaption{{padding:14px 16px;color:#2A2723;font-size:14px}}
 figcaption b{{font-size:16px}} figcaption em{{color:#8A8375;font-style:normal;
   font-size:12px;text-transform:uppercase;letter-spacing:.06em;margin-left:8px}}
 figcaption p{{margin:6px 0}} .g{{color:#6B6455}} .m{{color:#8A8375;font-size:12.5px}}
 code{{color:#9B3A2E}} a{{color:#9B3A2E}}
 ul{{color:#BDB5A6;line-height:1.9}} li code{{color:#C08A6E}}
</style>
<h1>Helix — {title or 'design samples'}</h1>
<p class=sub>Every design, rendered from the same family. Click a picture for
the SVG, or take the PDF straight to a printer — both are at true physical size.</p>
<div class=grid>{cards}</div>
{todo_section}"""


def cmd_contact_sheet(a):
    """Render every design at small size so you can choose by eye."""
    from .style.tokens import Style
    con = connect(a.db, create=False)
    graph = gbuild.load(con)
    subject = get_setting(con, "subject_person_id")
    outdir = Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    made = []
    for d in registry.all_designs():
        try:
            style = Style.load(a.style) if a.style else Style.load()
            style.set("layout.engine", d.key)
            s = LayoutSettings(engine=d.key, subject_id=subject,
                               max_generations=a.max_generations)
            plan = registry.run(d.key, graph, s, style)
            p = outdir / f"{d.key}.svg"
            p.write_text(svgrender.render(plan))
            made.append((d, p, len(plan.elements)))
            print(f"  {d.key:<18} {len(plan.elements):>6} shapes -> {p.name}")
        except NotImplementedError:
            print(f"  {d.key:<18} {'':>6} not built yet ({d.name})")
        except Exception as e:                   # never let one design stop the sheet
            print(f"  {d.key:<18} {'':>6} could not be drawn: {e}")
    (outdir / "index.html").write_text(_contact_html(made))
    print(f"\nOpen {outdir / 'index.html'} to compare them side by side.")


def _contact_html(made) -> str:
    cards = "".join(
        f'<figure><img src="{p.name}" loading="lazy">'
        f'<figcaption><b>{d.name}</b><br><small>{d.blurb}</small>'
        f'<br><code>{d.key}</code></figcaption></figure>' for d, p, n in made)
    return (
        "<!doctype html><meta charset=utf-8><title>Helix design gallery</title>"
        "<style>body{font:16px/1.5 system-ui;background:#14130F;color:#EDE7DA;"
        "margin:0;padding:32px}h1{font-weight:500}"
        "div{display:grid;gap:24px;grid-template-columns:repeat(auto-fill,"
        "minmax(360px,1fr))}figure{margin:0;background:#FBF8F2;border-radius:8px;"
        "overflow:hidden}img{width:100%;display:block;background:#FBF8F2}"
        "figcaption{padding:12px 14px;color:#2A2723;font-size:14px}"
        "code{color:#8A5A3A}</style><h1>Helix design gallery</h1><div>"
        + cards + "</div>")


def cmd_check(a):
    from .graph.validate import validate
    con = connect(a.db, create=False)
    graph = gbuild.load(con)
    issues = validate(graph)
    if not issues:
        print("No problems found.")
        return
    for sev in ("error", "warning", "info"):
        rows = [i for i in issues if i.severity == sev]
        if rows:
            print(f"\n{sev.upper()} ({len(rows)})")
            for i in rows[:a.limit]:
                print(f"  {i.message}")


def cmd_stats(a):
    con = connect(a.db, create=False)
    graph = gbuild.load(con)
    st = graph.stats()
    for k, v in st.items():
        print(f"  {k:<18} {v}")
    from .graph.thread import Contingency, thread
    subj = get_setting(con, "subject_person_id")
    if subj:
        t = thread(graph, subj)
        print(f"  thread_members     {len(t.members)}")
        c = Contingency(graph)
        crit = c.criticality()
        top = sorted(crit.items(), key=lambda kv: -kv[1])[:10]
        print("\n  Most structurally critical ancestors:")
        for pid, n in top:
            p = graph.people[pid]
            print(f"    {n:>5} descendants depend on  {p.full_name} {p.lifespan}")


def cmd_archive(a):
    """Write a portable zip: the database, a plain JSON dump, CSV tables and
    the current renders. This is the copy to keep somewhere else."""
    from .store.archive import archive
    renders = []
    if a.include_renders:
        from .style.tokens import Style
        con = connect(a.db, create=False)
        graph = gbuild.load(con)
        subject = get_setting(con, "subject_person_id")
        tmp = Path(a.db).parent / ".helix-renders"
        tmp.mkdir(exist_ok=True)
        for design, style in (("radial_rings", "panel1m"),
                              ("timeline_lanes", "timeline")):
            try:
                st = Style.load(style)
                plan = registry.run(design, graph,
                                    LayoutSettings(engine=design,
                                                   subject_id=subject,
                                                   focus="bloodline"), st)
                f = tmp / f"{design}.svg"
                f.write_text(svgrender.render(plan))
                renders.append(f)
            except Exception:
                continue
    out = archive(a.db, a.out, renders)
    for f in renders:
        f.unlink(missing_ok=True)
    size = Path(out).stat().st_size / 1024
    print(f"{out}  ({size:.0f} kB)")
    print("  Keep a copy somewhere that is not this computer.")


def cmd_restore(a):
    """Rebuild a family file from an archive, a JSON dump, or a backup."""
    from .store.archive import restore
    r = restore(a.src, a.out, overwrite=a.overwrite)
    print(f"  Restored {r['people']} people into {a.out}")
    if r.get("exported"):
        print(f"  Archive was made {r['exported']}")
    for t, n in sorted(r.get("tables", {}).items()):
        print(f"    {t:<16} {n}")
    if r["problems"]:
        print("\n  Problems found after restoring:")
        for x in r["problems"]:
            print(f"    {x}")
    else:
        print("\n  No problems. Open it with:  helix serve " + str(a.out))


def cmd_verify(a):
    """Check the file is sound, and say how much work is in it."""
    from .store.archive import verify
    con = connect(a.db, create=False)
    problems = verify(con)
    n = con.execute("SELECT COUNT(*) FROM person").fetchone()[0]
    u = con.execute("SELECT COUNT(*) FROM union_").fetchone()[0]
    e = con.execute("SELECT COUNT(*) FROM event").fetchone()[0]
    ver = get_setting(con, "schema_version", "?")
    print(f"  {a.db}")
    print(f"  {n} people, {u} families, {e} recorded facts")
    print(f"  schema version {ver}")
    d = Path(a.db).parent / "backups"
    backups = sorted(d.glob(f"{Path(a.db).stem}-*")) if d.exists() else []
    print(f"  {len(backups)} backups" +
          (f", newest {backups[-1].name}" if backups else " \u2014 none yet"))
    if problems:
        print("\n  PROBLEMS FOUND:")
        for x in problems:
            print(f"    {x}")
        raise SystemExit(1)
    print("\n  No problems found. Your file is sound.")


def cmd_backup(a):
    from .store.db import backup as do_backup, checkpoint
    con = connect(a.db, create=False)
    checkpoint(con)
    print(f"  {do_backup(a.db)}")


def cmd_export(a):
    """Write the family out as GEDCOM, so it is not trapped in this program.

    Rule from `docs/KEEPING_YOUR_WORK.md`: the file must be able to leave.
    GEDCOM is the one format Ancestry, MyHeritage, FamilySearch, Gramps and
    Family Tree Maker all read, so this is the door out.
    """
    from .io import gedcom
    con = connect(a.db, create=False)
    title = get_setting(con, "project_title", "")
    out = a.out or str(Path(a.db).with_suffix(".ged"))
    r = gedcom.export_file(con, out, version=a.version, title=title,
                           submitter=a.submitter or "")
    print(f"  {r['path']}  ({r['bytes'] / 1024:.0f} kB, GEDCOM {r['version']})")
    print(f"  {r['people']} people, {r['families']} families, "
          f"{r['sources']} sources")
    print("\n  This file opens in Ancestry, MyHeritage, FamilySearch, "
          "Gramps and\n  Family Tree Maker. Keep a copy somewhere that is "
          "not this computer.")


def cmd_import(a):
    """Read somebody else's tree in -- GEDCOM or a spreadsheet.

    Nothing is refused and nothing is silently dropped: anything Helix has
    no column for is kept in that person's notes. If the result is not what
    you wanted, one Ctrl-Z in the app takes the whole import back.
    """
    src = Path(a.src)
    out = Path(a.out or (src.stem + ".helix"))
    csvish = src.suffix.lower() in (".csv", ".tsv", ".txt")

    # A DRY RUN MUST NOT CREATE THE FILE. `connect()` makes one if it is not
    # there, so opening it before this check left an empty family file
    # behind -- and the real import then refused to run because its own
    # dry run had already created the target.
    if a.dry_run:
        if csvish:
            from .io.csv_import import import_csv
            r = import_csv(src, None, dry_run=True)
            print(f"  {src.name}: {r['rows']} rows -> {r['people']} people, "
                  f"{r['placeholders']} to be filled in later")
            print(f"  Columns understood: "
                  f"{', '.join(sorted(set(r['mapping'].values())))}")
            if r["unmapped"]:
                print(f"  Not understood (would be kept in notes): "
                      f"{', '.join(r['unmapped'])}")
            for x in r["problems"]:
                print(f"    ! {x}")
        else:
            from .io import gedcom
            roots, meta = gedcom.read(src)
            kinds: dict = {}
            for x in roots:
                kinds[x.tag] = kinds.get(x.tag, 0) + 1
            print(f"  {src.name}: {meta['bytes'] / 1024:.0f} kB, "
                  f"read as {meta['encoding']}")
            for tag, n in sorted(kinds.items(), key=lambda kv: -kv[1]):
                print(f"    {tag:<6} {n}")
            for x in meta["problems"][:5]:
                print(f"    ! {x}")
        print("\n  Nothing was written. Run again without --dry-run.")
        return

    if out.exists() and not a.into:
        raise SystemExit(
            f"\n  {out} already exists.\n"
            f"  Choose another name with -o, or pass --into to add these "
            f"people to it.\n")
    con = connect(out)
    if csvish:
        from .io.csv_import import import_csv
        r = import_csv(src, con, dry_run=False)
        print(f"  {src.name}: {r['rows']} rows -> {r['people']} people, "
              f"{r['families']} families" +
              (f", {r['placeholders']} to be filled in later"
               if r["placeholders"] else ""))
        print(f"  Columns understood: "
              f"{', '.join(sorted(set(r['mapping'].values())))}")
        if r["unmapped"]:
            print(f"  Not understood (kept in notes): "
                  f"{', '.join(r['unmapped'])}")
    else:
        from .io import gedcom
        r = gedcom.import_file(src, con)
        print(f"  {src.name}: read as {r['encoding']}")
        print(f"  {r['people']} people, {r['families']} families, "
              f"{r['events']} facts, {r['sources']} sources")
        if r["notes_kept"]:
            print(f"  {r['notes_kept']} people had extra tags kept in their "
                  f"notes, marked [GEDCOM]")
        for x in (r["problems"] + r["warnings"])[:8]:
            print(f"    ! {x}")
    n = con.execute("SELECT COUNT(*) FROM person").fetchone()[0]
    if not get_setting(con, "subject_person_id"):
        # SOMEBODY HAS TO BE THE CENTRE, or the chart opens on nobody and
        # every relation on screen reads "no known relation". The person
        # with the most descendants is the best guess available before
        # anyone has said whose tree it is.
        row = con.execute(
            "SELECT up.person_id, COUNT(*) n FROM union_partner up "
            "JOIN union_child uc ON uc.union_id = up.union_id "
            "GROUP BY up.person_id ORDER BY n DESC LIMIT 1").fetchone()
        if row:
            set_setting(con, "subject_person_id", row["person_id"])
            print(f"  Centred the chart on the person with the most "
                  f"children. Change it in the app.")
    print(f"\n  {out} now holds {n} people.")
    print(f"  Open it with:  helix serve {out}")


def cmd_serve(a):
    from .server import serve
    # A DELIBERATE ACT, and it says what it is doing. The interface folds
    # down to a phone and none of that was any use while the server only
    # listened on 127.0.0.1 -- but a family's whole history on a shared
    # network is not something to switch on by accident.
    host = "0.0.0.0" if getattr(a, "lan", False) else a.host
    serve(a.db, host=host, port=a.port, open_browser=not a.no_open)


def main(argv=None):
    ap = argparse.ArgumentParser("helix", description="Family tree atlas")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="create an empty family file")
    p.add_argument("db"); p.add_argument("--title"); p.set_defaults(f=cmd_init)

    p = sub.add_parser("sample", help="fill a file with a realistic sample family")
    p.add_argument("db"); p.add_argument("--people", type=int, default=400)
    p.set_defaults(f=cmd_sample)

    p = sub.add_parser("designs", help="list every available design")
    p.add_argument("--json", action="store_true"); p.set_defaults(f=cmd_designs)

    p = sub.add_parser("styles", help="list built-in styles")
    p.set_defaults(f=cmd_styles)

    p = sub.add_parser("render", help="render one chart to SVG")
    p.add_argument("db"); p.add_argument("-o", "--out", default="tree.svg")
    p.add_argument("--style"); p.add_argument("--design")
    p.add_argument("--subject"); p.add_argument("--diameter", type=float)
    p.add_argument("--title"); p.add_argument("--max-generations", type=int)
    p.add_argument("--focus", default="all",
                   choices=["all", "thread", "thread_siblings", "subtree",
                            "bloodline"],
                   help="bloodline = everyone you are related to by blood "
                        "(recommended); thread = your direct line only; "
                        "thread_siblings = plus their brothers and sisters; "
                        "subtree = plus cousins; all = everyone in the file")
    p.add_argument("--max-people", type=int,
                   help="hard limit; least-connected people are dropped first")
    p.add_argument("--panel", help="finished size in mm, e.g. 1000x1000")
    p.add_argument("--ring-pitch", type=float,
                   help="minimum gap between rings in mm (default 25.4, one inch)")
    p.add_argument("--set", action="append", metavar="NAME=VALUE",
                   help="any style token, repeatable. docs/OPTIONS.md lists "
                        "them all. e.g. --set thread.enabled=false "
                        "--set family.wedges=false --set couple.leaf=split")
    p.add_argument("--production", action="store_true")
    p.set_defaults(f=cmd_render)
    p.description = ("Output format follows the file extension: .svg, .pdf, "
                     ".dxf (CAD and CAM), .eps, or .json")

    p = sub.add_parser("samples", help="render EVERY design to SVG + PDF")
    p.add_argument("db"); p.add_argument("-o", "--out", default="samples")
    p.add_argument("--title"); p.add_argument("--max-generations", type=int, default=5)
    p.add_argument("--focus", default="bloodline",
                   choices=["all", "thread", "thread_siblings", "subtree",
                            "bloodline"])
    p.set_defaults(f=cmd_samples)

    p = sub.add_parser("gallery", help="render EVERY design so you can choose")
    p.add_argument("db"); p.add_argument("-o", "--out", default="gallery")
    p.add_argument("--style"); p.add_argument("--max-generations", type=int)
    p.set_defaults(f=cmd_contact_sheet)

    p = sub.add_parser("check", help="validate the data")
    p.add_argument("db"); p.add_argument("--limit", type=int, default=25)
    p.set_defaults(f=cmd_check)

    p = sub.add_parser("stats", help="summary statistics")
    p.add_argument("db"); p.set_defaults(f=cmd_stats)

    p = sub.add_parser("archive", help="portable zip: database + JSON + CSV")
    p.add_argument("db"); p.add_argument("-o", "--out")
    p.add_argument("--include-renders", action="store_true", default=True)
    p.set_defaults(f=cmd_archive)

    p = sub.add_parser("restore",
                       help="rebuild a family file from an archive or backup")
    p.add_argument("src", help="an archive .zip, a family.json, or a .helix")
    p.add_argument("-o", "--out", default="restored.helix")
    p.add_argument("--overwrite", action="store_true")
    p.set_defaults(f=cmd_restore)

    p = sub.add_parser("verify", help="check the file is sound")
    p.add_argument("db"); p.set_defaults(f=cmd_verify)

    p = sub.add_parser("backup", help="take a backup now")
    p.add_argument("db"); p.set_defaults(f=cmd_backup)

    p = sub.add_parser("export", help="write the family out as GEDCOM")
    p.add_argument("db"); p.add_argument("-o", "--out")
    p.add_argument("--version", default="5.5.1", choices=["5.5.1", "7.0"])
    p.add_argument("--submitter", default="")
    p.set_defaults(f=cmd_export)

    p = sub.add_parser("import", help="read a GEDCOM or spreadsheet in")
    p.add_argument("src", help="a .ged from any program, or a .csv")
    p.add_argument("-o", "--out", help="the family file to create")
    p.add_argument("--into", action="store_true",
                   help="add to an existing file instead of refusing")
    p.add_argument("--dry-run", action="store_true",
                   help="report what would happen and write nothing")
    p.set_defaults(f=cmd_import)

    p = sub.add_parser("serve", help="open the app in your browser")
    p.add_argument("db"); p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--lan", action="store_true",
                   help="let phones and tablets on the same network open it")
    p.add_argument("--port", type=int, default=8731)
    p.add_argument("--no-open", action="store_true"); p.set_defaults(f=cmd_serve)

    a = ap.parse_args(argv)
    try:
        a.f(a)
    except FileNotFoundError as e:
        print(f"\n  {e}\n", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
