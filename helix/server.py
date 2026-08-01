"""Local web server. Serves the app and a small JSON API on 127.0.0.1.

Uses only the standard library so `helix serve` works before you have
installed anything else. FastAPI is optional and only adds auto-docs.
"""
from __future__ import annotations

import contextlib
import json
import mimetypes
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .graph import build as gbuild
from .graph.build import UNION_CHOICES
from .graph.kinship import (KinFilter, Kinship, all_groups, household,
                            siblings_of)
from .graph.thread import Contingency, thread
from .layout import registry
from .layout.base import LayoutSettings
from .layout.engines import experimental, family, linear, radial  # noqa: F401
from .render import svg as svgrender
from .store import records
from .store.db import connect, get_setting, set_setting
from .style.tokens import Style

WEB = Path(__file__).with_name("web")

# The write half of the API. Each one takes (connection, payload) and returns
# a JSON-able dict; the handler reloads the graph and adds undo state. Keeping
# the table here rather than in a chain of ifs is what makes it obvious that
# every write goes through `store.records` and nothing writes rows inline.
_RECORD_ROUTES = {
    "/api/person":        lambda con, b: records.update_person(con, b),
    "/api/person/new":    lambda con, b: records.add_person(con, b),
    "/api/person/link":   lambda con, b: records.link_person(con, b),
    "/api/person/detach": lambda con, b: records.detach(con, b),
    "/api/person/retire": lambda con, b: records.retire(con, b["id"]),
    "/api/union":         lambda con, b: records.union_op(con, b),
    "/api/union/child":   lambda con, b: records.union_child_op(con, b),
    "/api/undo":          lambda con, b: records.undo(con),
    "/api/redo":          lambda con, b: records.redo(con),
    "/api/person/photo":  lambda con, b: _add_photo(con, b),
    "/api/person/photo/remove": lambda con, b: _drop_photo(con, b),
    "/api/person/photo/caption": lambda con, b: _caption(con, b),
    "/api/person/photo/portrait": lambda con, b: _set_portrait(con, b),
    "/api/person/photo/taken": lambda con, b: _taken(con, b),
    "/api/person/heritage": lambda con, b: records.set_heritage(con, b),
    "/api/person/merge":  lambda con, b: records.merge(con, b),
}


def _add_photo(con, b: dict) -> dict:
    """A photograph or a paper, copied into the album beside the family file.

    The bytes arrive as a `data:` URL because that is what a browser's
    FileReader produces and because the standard library has no multipart
    parser it would be wise to point at untrusted input.

    ONLY A PICTURE CAN BE THE PORTRAIT. A scanned order of service attached
    to somebody is not what should appear in the round frame at the top of
    their profile, so the flag is refused for anything that is not an image
    whatever the request asked for.
    """
    from .store import album
    name, _path = album.store_data_url(ST.dbpath, b["data"],
                                       b.get("filename", ""))
    want = b.get("portrait", album.kind_of(name) == "photo") is not False
    mid = album.attach(con, b["id"], name, caption=b.get("caption", ""),
                       portrait=want and album.kind_of(name) == "photo")
    return {"ok": True, "id": b["id"], "media_id": mid, "name": name,
            "kind": album.kind_of(name)}


def _caption(con, b: dict) -> dict:
    """What a scan IS. "Order of service, St Mary's, 14 March 1998" is the
    difference between a file and a record."""
    from .store import records
    with records.Edit(con, "Describe a file") as e:
        e.update("media", {"id": b["media_id"]},
                 {"caption": (b.get("caption") or "").strip() or None})
    return {"ok": True, "id": b.get("id")}


def _taken(con, b: dict) -> dict:
    """When a photograph was taken, or how old they were in it.

    Somebody's face at 20 and at 80 are both worth keeping and the new one
    goes at the top -- so the old ones need to say WHEN, or a profile is a
    pile of pictures in upload order.
    """
    from .store import album
    album.set_taken(con, b["media_id"], b.get("taken", ""))
    return {"ok": True, "id": b.get("id")}


def _set_portrait(con, b: dict) -> dict:
    from .store import album
    row = con.execute("SELECT path FROM media WHERE id=?",
                      (b["media_id"],)).fetchone()
    if row and album.kind_of(row["path"]) != "photo":
        raise ValueError("Only a picture can be somebody's portrait.")
    album.attach(con, b["id"], row["path"], portrait=True)
    return {"ok": True, "id": b["id"]}


def _drop_photo(con, b: dict) -> dict:
    from .store import album
    album.detach(con, b["id"], b["media_id"])
    return {"ok": True, "id": b["id"]}


class State:
    """Shared server state.

    One connection, guarded by a lock. ThreadingHTTPServer gives every
    request its own thread, and SQLite objects are not safe to share across
    threads without either a connection per thread or serialised access.
    For a single-user local program a lock is simpler and provably correct.
    """

    def __init__(self, dbpath: str):
        self.dbpath = dbpath
        self.lock = threading.RLock()
        self.reload()

    def reload(self):
        self.con = connect(self.dbpath, create=False)
        self.graph = gbuild.load(self.con)
        self.subject = get_setting(self.con, "subject_person_id")
        self.title = get_setting(self.con, "project_title", "My family")
        self._cont = None
        self._kin = None

    @property
    def contingency(self) -> Contingency:
        if self._cont is None:
            self._cont = Contingency(self.graph)
        return self._cont

    @property
    def kin(self) -> Kinship:
        """Everybody's relation to the subject, worked out once per reload.

        Cached because it is read by four different screens and rebuilt on
        every write anyway. Asked per person instead it is quadratic: the
        relatives sidebar lists four hundred people and would walk four
        hundred ancestor sets to do it.
        """
        if self._kin is None:
            self._kin = Kinship(self.graph, self.subject)
        return self._kin


ST: State | None = None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    # ------------------------------------------------------------------ GET
    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path.startswith("/api/"):
                with ST.lock:
                    return self._api(u.path[5:], q)
            if u.path.startswith("/print/"):
                with ST.lock:
                    return self._print(u.path[7:], q)
            return self._static(u.path)
        except Exception as e:                       # never show a stack trace
            self._json({"error": str(e)}, 500)

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        try:
          with ST.lock:
            if u.path == "/api/subject":
                set_setting(ST.con, "subject_person_id", body["id"])
                ST.reload()
                return self._json({"ok": True, "subject": ST.subject})
            if u.path == "/api/backup":
                from .store.db import backup, checkpoint
                checkpoint(ST.con)
                return self._json({"ok": True, "path": str(backup(ST.dbpath))})
            if u.path == "/api/archive":
                from .store.archive import archive
                return self._json({"ok": True,
                                   "path": str(archive(ST.dbpath))})
            if u.path.startswith("/api/library"):
                return self._json(_library(u.path[len("/api/library"):], body))
            if u.path == "/api/import":
                out = _import(body)
                if not body.get("dry_run"):
                    ST.reload()
                    out.setdefault("history", records.history(ST.con))
                return self._json(out)
            # ---- the record system. Everything below writes and reloads. --
            if u.path in _RECORD_ROUTES:
                out = _RECORD_ROUTES[u.path](ST.con, body)
                ST.reload()
                out.setdefault("history", records.history(ST.con))
                return self._json(out)
            self._json({"error": "unknown endpoint"}, 404)
        except KeyError as e:
            self._json({"error": f"That request is missing {e}."}, 400)
        except Exception as e:
            self._json({"error": str(e)}, 400)

    # ------------------------------------------------------------------ API
    def _api(self, route, q):
        if route == "meta":
            g = ST.graph
            return self._json({
                "title": ST.title, "subject": ST.subject,
                "stats": g.stats(),
                "designs": [{"key": d.key, "name": d.name, "family": d.family,
                             "blurb": d.blurb, "good_for": d.good_for,
                             "laser": d.laser, "built": d.built}
                            for d in registry.all_designs()],
                "styles": Style.list_presets(),
                # What kinds of couple there are, so the panel offers them
                # rather than hard-coding a list that drifts from the schema.
                "union_kinds": UNION_CHOICES,
                "people": [{"id": p.id, "name": p.full_name,
                            "life": p.lifespan, "sex": p.sex}
                           for p in sorted(g.people.values(),
                                           key=lambda x: (x.surname, x.given))],
            })
        if route == "thumb":
            body = _thumb(q.get("design") or "radial_family").encode()
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if route == "plan":
            return self._json(_plan(q).to_dict())
        if route == "svg":
            plan = _plan(q)
            body = svgrender.render(plan, production=q.get("production") == "1",
                                    interactive=True).encode()
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Content-Disposition",
                             f'attachment; filename="{q.get("name","tree")}.svg"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if route == "person":
            return self._json(_person_detail(ST, q["id"]))
        if route == "relatives":
            # THE SIDEBAR. Everybody in the file, in tabs, closest first.
            return self._json(_relatives(ST))
        if route == "kin":
            # ONE PERSON, MEASURED TWICE: how they stand to you, and how
            # everyone else stands to THEM. The second is what lights the
            # chart up when you click a name -- their cousins, not yours.
            return self._json(_kin_detail(ST, q["id"]))
        if route == "groups":
            return self._json(all_groups())
        if route == "library":
            # WHERE YOUR WORK LIVES. The desktop application has no address
            # bar to type a path into, so the program has to be able to
            # show you the folder, list what is in it, and open another
            # family without going anywhere near a terminal.
            from .desktop import library as lib
            g = ST.graph
            sub = g.people.get(ST.subject) if ST.subject else None
            return self._json({
                "library": str(lib.library_dir()),
                "current": str(Path(ST.dbpath).resolve()),
                "families": lib.families(),
                "status": lib.status(ST.dbpath),
                # WHOSE TREE IT IS. Every relation on every screen is
                # measured from one person, so which person that is belongs
                # with the file rather than buried in a profile.
                "subject": ({"id": sub.id, "name": sub.full_name,
                             "life": sub.lifespan} if sub else None),
                "people": len(g.people),
            })
        if route == "duplicates":
            # THE SAME PERSON, ENTERED TWICE. Rare while you type -- the add
            # dialogue catches those -- and the ordinary case the moment you
            # import somebody else's tree, where four hundred people arrive
            # in one step and nothing was checked against what you had.
            from .analysis import duplicates
            rows = duplicates.find(ST.graph, limit=int(q.get("limit", 60)),
                                   threshold=float(q.get("threshold", 0.55)))
            for r in rows:
                r["people"] = [_dupe_brief(ST, r["a"]), _dupe_brief(ST, r["b"])]
            return self._json({"pairs": rows, "checked": len(ST.graph.people)})
        if route == "stats":
            from .analysis import stats
            return self._json(stats.report(ST.graph, ST.subject))
        if route == "timeline":
            from .analysis import stats
            return self._json(stats.timeline(ST.graph, q["id"]))
        if route == "family-timeline":
            # THE FAMILY AS ONE STORY. A chart says who was related to whom
            # and nothing about when; a person's timeline shows one life.
            # This is the third view.
            from .analysis import stats
            within = None if q.get("all") == "1" else _scoped_ids(q)
            d = stats.family_timeline(ST.graph, within=within, kin=ST.kin)
            d["anniversaries"] = stats.anniversaries(ST.graph, kin=ST.kin)
            d["scope"] = "everybody" if within is None else "this chart"
            return self._json(d)
        if route == "consanguinity":
            from .analysis import consang
            return self._json({"couples": consang.couples(ST.graph),
                               **consang.summary(ST.graph)})
        if route == "relate":
            # HOW ARE THESE TWO RELATED? Any two people in the file, not
            # only whoever the chart is centred on.
            return self._json(_relate(ST, q.get("a", ""), q.get("b", "")))
        if route == "gaps":
            # WHERE MORE RESEARCH IS NEEDED, ranked. Scoped to whatever is
            # on the chart when a focus is given, because a to-do list for
            # a branch you are not looking at is not a to-do list.
            return self._json(_gaps(ST, q))
        if route == "media":
            from .store import album
            p = album.resolve(ST.dbpath, q.get("name", ""))
            if not p:
                return self._json({"error": "No such picture."}, 404)
            body = p.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", album.mime_for(p.name))
            if album.kind_of(p.name) != "photo":
                # A scan is opened or saved, not laid out in a page. The
                # filename somebody sees is the caption they gave it, not
                # the hash the album stores it under.
                want = (q.get("as") or p.name).replace('"', "")
                self.send_header("Content-Disposition",
                                 f'inline; filename="{want}"')
            # named by the hash of its own bytes, so it can never go stale
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if route == "gedcom":
            # THE DOOR OUT, in the browser. A decade of research living in
            # one SQLite file is only safe if it can leave, and this is the
            # format every other program reads.
            import tempfile
            from .io import gedcom
            with tempfile.TemporaryDirectory() as d:
                stem = (ST.title or "family").replace(" ", "-")
                f = Path(d) / f"{stem}.ged"
                gedcom.export_file(ST.con, f,
                                   version=q.get("version", "5.5.1"),
                                   title=ST.title)
                raw = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Disposition",
                             f'attachment; filename="{stem}.ged"')
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if route == "person/search":
            return self._json(records.search(ST.con, q.get("q", ""),
                                             exclude=q.get("exclude", "")))
        if route == "date":
            from .model.gendate import parse as gparse
            d = gparse(q.get("q", ""))
            return self._json({"text": d.spoken, "display": d.display,
                               "kind": d.kind, "known": d.known})
        if route == "history":
            return self._json(records.history(ST.con))
        if route == "people":
            return self._json(_people_list(ST))
        if route == "contingency":
            r = ST.contingency.report(q["id"], ST.subject)
            r["removed"] = sorted(r["removed"])
            return self._json(r)
        if route == "critical":
            crit = ST.contingency.criticality()
            top = sorted(crit.items(), key=lambda kv: -kv[1])[:int(q.get("n", 20))]
            return self._json([{"id": p, "n": n - 1,
                                "name": ST.graph.people[p].full_name,
                                "life": ST.graph.people[p].lifespan}
                               for p, n in top if n > 1])
        if route == "status":
            from .store.archive import verify
            from .store.db import get_setting as gs
            dbp = Path(ST.dbpath)
            d = dbp.parent / "backups"
            backups = sorted(d.glob(f"{dbp.stem}-*")) if d.exists() else []
            st = dbp.stat()
            return self._json({
                "file": str(dbp), "size_kb": round(st.st_size / 1024),
                "modified": __import__("datetime").datetime.fromtimestamp(
                    st.st_mtime).isoformat(timespec="seconds"),
                "people": len(ST.graph.people),
                "families": len(ST.graph.unions),
                "schema": gs(ST.con, "schema_version"),
                "backups": len(backups),
                "newest_backup": backups[-1].name if backups else None,
                "problems": verify(ST.con),
                "saved": True,
            })
        if route == "check":
            from .graph.validate import validate
            return self._json([{"severity": i.severity, "message": i.message,
                                "id": i.person_id} for i in validate(ST.graph)])
        self._json({"error": f"unknown endpoint /api/{route}"}, 404)

    # ---------------------------------------------------------------- print
    def _print(self, what, q):
        """Pages meant for paper. HTML, printed by the browser -- see
        `render/dossier.py` for why that is the right tool and not a
        shortcut."""
        from .render import dossier
        from .store import album
        g, k = ST.graph, ST.kin
        photos = lambda pid: album.photos_of(ST.con, pid)   # noqa: E731

        if what == "profile":
            pid = q["id"]
            return self._html(dossier.one(g, ST.con, pid, kin=k,
                                          photos=photos(pid), title=ST.title))
        if what == "profiles":
            # WHOEVER IS ON THE CHART, in the order the sidebar shows them,
            # so the people somebody actually wants are at the front of the
            # pile rather than wherever the alphabet put them.
            ids = _print_cast(q)
            return self._html(dossier.everybody(
                g, ST.con, ids, kin=k, photos_for=photos,
                title=f"{ST.title} — profiles"))
        if what == "records":
            # THE BINDER. Every person numbered, every relation
            # cross-referenced by number, and nothing on it that is
            # arithmetic over today's file.
            ids = _print_cast(q)
            return self._html(dossier.record_book(
                g, ST.con, ids, kin=k, photos_for=photos,
                title=ST.title or "Family Records",
                subtitle=("Everyone in the file" if q.get("all") == "1"
                          else "Everyone on the chart")))
        if what == "chronicle":
            from .analysis import stats
            within = None if q.get("all") == "1" else _scoped_ids(q)
            return self._html(dossier.chronicle(
                g, stats.family_timeline(g, within=within, kin=k),
                title=f"{ST.title} — in order"))
        if what == "research":
            # WHERE TO LOOK NEXT, on its own sheet. Deliberately not part of
            # a profile: a profile is filed and read again in ten years, and
            # a to-do list printed onto it is stale in a week.
            d = _gaps(ST, q)
            return self._html(dossier.research(
                g, d["gaps"], title=f"{ST.title} — where to look next"))
        if what == "outline":
            plan_ids = set(_print_cast(q))
            roots = [p for p in plan_ids
                     if not [x for x in g.parents(p, primary_only=True)
                             if x in plan_ids]]
            roots.sort(key=lambda p: (g.people[p].birth.sort_value or 9e9,
                                      g.people[p].sort_key))
            return self._html(dossier.outline(
                g, roots, kin=k, elided=_print_elided(q),
                title=f"{ST.title} — outline"))
        self.send_error(404, "Not found")

    def _html(self, body: str):
        raw = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    # --------------------------------------------------------------- static
    def _static(self, path):
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        f = (WEB / rel).resolve()
        if not str(f).startswith(str(WEB.resolve())) or not f.exists():
            self.send_error(404, "Not found")
            return
        body = f.read_bytes()
        ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _plan(q):
    style = Style.load(q.get("style") or None)
    for k, v in q.items():
        if k.startswith("s."):
            style.set(k[2:], _coerce(v))
    design = q.get("design") or style.get("layout.engine", "radial_sunburst")
    style.set("layout.engine", design)
    s = LayoutSettings(
        engine=design, subject_id=q.get("subject") or ST.subject,
        max_generations=int(q["gens"]) if q.get("gens") else None,
        focus=q.get("focus", "all"),
        kin=_kin_filter(q),
        max_people=int(q["max_people"]) if q.get("max_people") else None,
        weight_mode=style.get("layout.weight_mode", "leaves"),
        redact_living=q.get("redact") == "1")
    plan = registry.run(design, ST.graph, s, style)
    # EVERY DESIGN SAYS WHAT IT LEFT OFF, even the ones that cannot draw a
    # mark for it. The flagship puts a pruned branch on each family and
    # writes its own richer count; the other eighteen share the same scoping
    # and would otherwise drop people silently, which is the one thing a
    # narrowed chart must never do. This is the floor: the number, always.
    got = getattr(s, "narrowed", None)
    if got is not None and "elided" not in plan.meta.extra:
        plan.meta.extra["elided"] = {
            "marriages": len(got.elided_union),
            "people": sum(got.elided_union.values()),
            "below": sum(got.elided_below.values()),
            "drawn": False,
        }
    return plan


# ─────────────────────────── the design gallery ──────────────────────────
#
# WHAT THE THUMBNAIL IS. It is the design, run on YOUR family, at 120
# pixels. Not a hand-drawn icon of what the design is supposed to look
# like -- there were eleven of those for twenty designs, so nine of them
# showed a sunburst whatever they actually drew, and two more had drifted
# from the geometry they were meant to illustrate.
#
# A picture of a chart that cannot go out of date is worth the render. And
# because it is your own file, the gallery answers the question somebody is
# really asking: not "what is an icicle plot" but "what does MY family look
# like as one".
_THUMBS: dict = {}


def _thumb(design: str) -> str:
    """One design, small, cached until the file changes.

    Cut down to the people around the subject and stripped of type, because
    at 120 pixels a name is a smudge and the SHAPE is the whole message.
    """
    stamp = (ST.dbpath, len(ST.graph.people), ST.subject)
    hit = _THUMBS.get(design)
    if hit and hit[0] == stamp:
        return hit[1]
    style = Style.load()
    style.set("layout.engine", design)
    style.set("labels.show", False)
    style.set("ornament.time_rings", False)
    style.set("lines.key", False)
    style.set("ornament.title", False)
    style.set("canvas.width_mm", 300)
    style.set("canvas.height_mm", 300)
    style.set("connectors.width_mm", 1.6)
    # EVERYBODY, not the narrowed cast. A thumbnail is a picture of a
    # SHAPE, and a shape needs enough people to have one -- narrowed to
    # four generations of one bloodline, half the designs drew a small
    # cluster in the corner of an empty disc.
    s = LayoutSettings(engine=design, subject_id=ST.subject,
                       focus="all", max_people=120,
                       weight_mode=style.get("layout.weight_mode", "leaves"))
    try:
        plan = registry.run(design, ST.graph, s, style)
        out = _crop(svgrender.render(plan), plan)
    except Exception:
        # A design that cannot draw this family gets an honest blank rather
        # than a broken gallery. It is still selectable; it will say why.
        out = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
               "<text x='50' y='54' text-anchor='middle' font-size='9' "
               "fill='#7A7367'>no preview</text></svg>")
    _THUMBS[design] = (stamp, out)
    return out


def _crop(svg: str, plan) -> str:
    """Tighten the viewBox onto what was actually drawn.

    A DESIGN THAT CENTRES A SMALL FAMILY IN A METRE-WIDE DISC is correct at
    a metre and useless at 120 pixels: the picture is a faint ring with a
    thumbprint of chart in the bottom third, and every such design looks
    like every other. Cropping to the ink is what makes the thumbnail a
    picture of the SHAPE.

    The points come from `pathflatten`, which already turns arcs and
    beziers into line segments for the CAD exports -- so this is the same
    geometry the DXF gets, not a guess at where a path goes.
    """
    from .render.pathflatten import flatten_d
    lo_x = lo_y = float("inf")
    hi_x = hi_y = float("-inf")
    for el in plan.elements:
        pts = []
        if el.kind == "path" and el.d:
            # `flatten_d` yields (points, closed) per subpath -- extending
            # with the pair instead of the points is how the first version
            # of this cropped every design to nothing.
            with contextlib.suppress(Exception):
                for run, _closed in flatten_d(el.d, tol=0.6):
                    pts.extend(run)
        elif el.x is not None and el.y is not None:
            pts = [(el.x, el.y)]
        for x, y in pts:
            lo_x, hi_x = min(lo_x, x), max(hi_x, x)
            lo_y, hi_y = min(lo_y, y), max(hi_y, y)
    if lo_x > hi_x or hi_x - lo_x <= 0 or hi_y - lo_y <= 0:
        return svg
    pad = max(hi_x - lo_x, hi_y - lo_y) * 0.04
    lo_x, lo_y = lo_x - pad, lo_y - pad
    w, h = (hi_x - lo_x) + pad, (hi_y - lo_y) + pad
    import re
    return re.sub(r'viewBox="[^"]*"',
                  f'viewBox="{lo_x:.2f} {lo_y:.2f} {w:.2f} {h:.2f}"',
                  svg, count=1)


def _kin_filter(q) -> KinFilter:
    """How far the chart spreads, read off the query string.

    `kin` carries the whole filter as JSON, which keeps a growing set of
    controls out of the URL one parameter at a time; the plain named
    parameters are there so the same chart can be asked for from a script
    without building JSON.
    """
    d: dict = {}
    if q.get("kin"):
        try:
            d = json.loads(q["kin"]) or {}
        except ValueError:
            d = {}
    for name in ("max_cousin_degree", "max_removal", "max_steps",
                 "max_up", "max_down"):
        if q.get(name) not in (None, ""):
            d[name] = q[name]
    if q.get("married_in") in ("0", "false"):
        d["married_in"] = False
    if q.get("unrelated") in ("1", "true"):
        d["unrelated"] = True
    if q.get("groups"):
        d["groups"] = [x for x in q["groups"].split(",") if x]
    return KinFilter.from_dict(d)


def _print_cast(q) -> list[str]:
    """Who a printout covers.

    THE SAME PEOPLE AS THE CHART, by default and on purpose. Print a chart
    narrowed to first cousins and then a dossier of four hundred people and
    the two do not describe the same family -- so the printout is built from
    the same scoping the chart used, and says so on the page.
    """
    g, k = ST.graph, ST.kin
    if q.get("all") == "1":
        ids = list(g.people)
    else:
        keep = _scoped_ids(q)
        ids = [p for p in g.people if p in keep]
    return sorted(ids, key=lambda p: (k.of(p).rank, g.people[p].sort_key))


def _scoped_ids(q) -> set:
    from .graph.kinship import narrow
    from .layout.subject_grid import _by_focus
    subj = q.get("subject") or ST.subject
    if not subj or subj not in ST.graph.people:
        return set(ST.graph.people)
    within = _by_focus(ST.graph, LayoutSettings(subject_id=subj,
                                                focus=q.get("focus", "all")),
                       subj)
    return narrow(ST.graph, subj, _kin_filter(q), within=within,
                  index=ST.kin).keep


def _print_elided(q) -> dict:
    from .graph.kinship import narrow
    from .layout.subject_grid import _by_focus
    subj = q.get("subject") or ST.subject
    filt = _kin_filter(q)
    if not subj or not filt.active:
        return {}
    within = _by_focus(ST.graph, LayoutSettings(subject_id=subj,
                                                focus=q.get("focus", "all")),
                       subj)
    return narrow(ST.graph, subj, filt, within=within,
                  index=ST.kin).elided_union


def _library(what: str, body: dict) -> dict:
    """Managing the family files themselves, not the people in them.

    SWITCHING FAMILIES REBINDS THE WHOLE SERVER, and it has to: `State`
    holds one connection, one graph and one kinship index, and every screen
    reads them. Opening a second family by pointing the same state at a new
    path is the only way that does not leave half the window describing the
    family you just left.
    """
    from .desktop import library as lib
    what = what.strip("/")
    if what == "new":
        p = lib.create(body.get("title") or "My family",
                       sample=bool(body.get("sample")))
        _rebind(p)
        return {"ok": True, "path": str(p), "opened": True,
                "message": f"Started {body.get('title') or 'a new family'}. "
                           f"It is saved in {lib.library_dir()}."}
    if what == "open":
        p = Path(body["path"])
        if not p.exists():
            raise ValueError(
                f"There is no family file at {p}. It may have been moved or "
                f"renamed — the ones Helix can see are in {lib.library_dir()}.")
        _rebind(p)
        return {"ok": True, "path": str(p), "opened": True}
    if what == "rename":
        target = Path(body.get("path") or ST.dbpath)
        mine = target.resolve() == Path(ST.dbpath).resolve()
        # LET GO OF THE FILE BEFORE MOVING IT. The server holds an open
        # connection with a write-ahead log beside it; renaming underneath
        # that leaves the log behind and the next open fails.
        if mine:
            with contextlib.suppress(Exception):
                ST.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                ST.con.close()
        out = lib.rename(target, body["title"])
        if mine:
            _rebind(Path(out["path"]))
        return {"ok": True, **out,
                "message": f"Now called {body['title']}."
                           + (f" The file is {Path(out['path']).name}."
                              if out.get("renamed") else "")}
    if what == "duplicate":
        p = lib.duplicate(body.get("path") or ST.dbpath)
        return {"ok": True, "path": str(p),
                "message": f"Copied to {p.name}. The original is untouched."}
    if what == "copy-for":
        # THE SAME FAMILY, AS SOMEBODY ELSE'S TREE. Asked twice: once with
        # `preview` to find out what would be left out, so the question can
        # be put to somebody with real names in it, and once to do it.
        who = body.get("id") or ""
        if body.get("preview"):
            return {"ok": True, **lib.copy_for(ST.dbpath, who, dry_run=True)}
        out = lib.copy_for(ST.dbpath, who, title=body.get("title", ""),
                           prune=bool(body.get("prune")))
        if body.get("open"):
            _rebind(Path(out["path"]))
            out["opened"] = True
        return {"ok": True, **out}
    if what == "reveal":
        ok = lib.reveal(body.get("path") or ST.dbpath)
        return {"ok": ok, "path": body.get("path") or ST.dbpath,
                "message": "Opened the folder." if ok else
                           f"Your files are in {lib.library_dir()}."}
    if what == "folder":
        d = lib.set_library_dir(body["path"])
        return {"ok": True, "library": str(d),
                "families": lib.families(),
                "message": f"Helix will keep family files in {d}."}
    raise ValueError(f"Unknown library action {what!r}.")


def _rebind(path) -> None:
    """Point the running server at another family file."""
    from .desktop import library as lib
    old = ST.con
    ST.dbpath = str(path)
    ST.reload()
    lib.remember(path)
    if old is not ST.con:
        with contextlib.suppress(Exception):
            old.close()


def _import(body: dict) -> dict:
    """Bring somebody else's tree in, over HTTP.

    The bytes arrive as a `data:` URL for the same reason a photograph does:
    the standard library has no multipart parser it would be wise to point
    at untrusted input, and FileReader is what a browser already gives you.

    A DRY RUN WRITES NOTHING and is what the dialog shows first. Nobody's
    first import is the one they meant, and four hundred people entered by
    mistake is not something to discover afterwards.
    """
    import base64
    import tempfile

    # THE NAME IS CHECKED BEFORE THE BYTES. Told the file is a photograph,
    # somebody wants to hear that Helix reads GEDCOM -- not "that file could
    # not be read", which is what the decoder says about a .jpg and is no
    # help at all (rule 8).
    name = (body.get("filename") or "family.ged").strip() or "family.ged"
    suffix = Path(name).suffix.lower() or ".ged"
    if suffix not in (".ged", ".gedcom", ".csv", ".tsv", ".txt"):
        raise ValueError(
            f"Helix reads family trees as GEDCOM (.ged) and spreadsheets "
            f"(.csv). {name} is a {suffix} file. In Ancestry, MyHeritage or "
            f"FamilySearch, look for 'Export tree' and choose GEDCOM.")
    raw = body.get("data") or ""
    if "," in raw:
        raw = raw.split(",", 1)[1]
    try:
        blob = base64.b64decode(raw)
    except Exception:
        raise ValueError("That file could not be read. Try choosing it again.")
    dry = bool(body.get("dry_run"))

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / Path(name).name
        path.write_bytes(blob)
        if suffix in (".csv", ".tsv", ".txt"):
            from .io.csv_import import import_csv
            r = import_csv(path, None if dry else ST.con, dry_run=dry)
            r["kind"] = "spreadsheet"
            r.setdefault("events", 0)
            return {"ok": True, "dry_run": dry, **r}
        from .io import gedcom
        if dry:
            roots, meta = gedcom.read(path)
            kinds: dict = {}
            for x in roots:
                kinds[x.tag] = kinds.get(x.tag, 0) + 1
            return {"ok": True, "dry_run": True, "kind": "gedcom",
                    "file": name, "encoding": meta["encoding"],
                    "people": kinds.get("INDI", 0),
                    "families": kinds.get("FAM", 0),
                    "sources": kinds.get("SOUR", 0),
                    "tags": kinds, "problems": meta["problems"][:10],
                    "warnings": []}
        r = gedcom.import_file(path, ST.con)
        r["kind"] = "gedcom"
        r["file"] = name
        return {"ok": True, "dry_run": False, **r}


def _dupe_brief(st: State, pid: str) -> dict:
    """Enough about one of a pair to choose between them without leaving
    the screen. Which record is right is a judgement about somebody's
    research, and it cannot be made from two names alone."""
    from .store import album
    g = st.graph
    p = g.people[pid]
    port = album.portrait_of(st.con, pid)
    return {
        "id": pid, "name": p.full_name, "life": p.lifespan, "sex": p.sex,
        "birth": p.birth.display, "death": p.death.display,
        "birth_place": p.birth_place, "occupation": p.occupation,
        "notes": (p.notes or "")[:200],
        "relation": st.kin.label(pid),
        "portrait": port["name"] if port else None,
        "parents": [g.people[x].full_name for x in g.parents(pid, False)
                    if x in g.people],
        "partners": [g.people[x].full_name for x in g.partners(pid)
                     if x in g.people],
        "children": len(g.children(pid)),
        "facts": _completeness(g, p),
    }


def _gaps(st: State, q) -> dict:
    """Where more research is needed, best question first.

    Scoped the same way the chart is: ask for the gaps while looking at a
    chart narrowed to first cousins and you get the gaps on that chart. The
    alternative -- always the whole file -- means the panel beside a
    four-generation chart opens with a question about somebody who is not
    on it.
    """
    from .analysis import gaps as gapmod
    within = None if q.get("all") == "1" else _scoped_ids(q)
    # Ranked in full, then cut. The headline counts how many lines really
    # stop dead; worked out from the visible twenty it would have said
    # "2 lines stop here" of a file with forty-one.
    rows = gapmod.rank(st.graph, st.con, country=q.get("country", "england"),
                       limit=10 ** 6, within=within,
                       subject=q.get("subject") or st.subject,
                       index=st.kin)
    n = int(q.get("limit", 40))
    # WHO THEY ARE TO YOU, added here because this is the only place that
    # knows. Two people recorded as nothing but "Harris" produce two
    # identical questions; "your great-grandmother" and "your third cousin
    # twice removed" are what tell them apart.
    for r in rows[:n]:
        k = st.kin.of(r["pid"])
        r["relation"] = "" if k.group in ("self", "unrelated") else k.label
    # GROUPED BY WHAT KIND OF JOB IT IS. Ranked purely by score, a
    # blood ancestor's missing birth year always outranks a whole in-law
    # family nobody has begun -- correct arithmetic, and it means one kind
    # of task is never seen. The panel offers them as separate lists.
    kinds = {}
    for r in rows:
        kinds.setdefault(r["kind"], 0)
        kinds[r["kind"]] += 1
    want = q.get("kind") or ""
    shown = [r for r in rows if r["kind"] == want] if want else rows
    return {"gaps": shown[:n], "summary": gapmod.summary(rows),
            "shown": min(n, len(shown)), "total": len(shown),
            "all_total": len(rows), "kinds": kinds, "kind": want,
            "groups": [{"key": k, "label": _GAP_GROUPS[k], "n": kinds.get(k, 0)}
                       for k in _GAP_GROUPS if kinds.get(k)],
            "scope": "everybody" if within is None else "this chart",
            "considered": len(st.graph.people) if within is None else len(within)}


# The name each kind of question goes under in the panel. Ordered by how
# much of a family a single answer opens up.
_GAP_GROUPS = {
    "parents": "Lines that stop",
    "story": "Within living memory",
    "name": "No full name",
    "birth": "No birth date",
    "birth_place": "No birthplace",
    "death": "No death recorded",
    "spouse": "No partner recorded",
    "occupation": "No occupation",
}


def _inbreeding(st: State, pid: str) -> dict:
    """Whether this person's own parents were already related, and by how
    much. Zero is the ordinary answer and is said plainly."""
    from .analysis import consang
    d = consang.inbreeding(st.graph, pid)
    # And whether THEY married a relative, which is a different question
    # and the one people actually ask at a wedding.
    mine = []
    for uid in st.graph.people[pid].unions:
        u = st.graph.unions.get(uid)
        if not u:
            continue
        for other in u.partners:
            if other == pid or other not in st.graph.people:
                continue
            rel = consang.between(st.graph, pid, other)
            if rel.related:
                mine.append({**rel.to_dict(),
                             "word": u.word.capitalize(),
                             "name": st.graph.people[other].full_name,
                             "ancestor_names": [
                                 st.graph.people[x].full_name
                                 for x in rel.ancestors
                                 if x in st.graph.people]})
    d["married_a_relative"] = mine
    return d


def _person_gaps(st: State, pid: str) -> list[dict]:
    from .analysis import gaps as gapmod
    return gapmod.for_person(st.graph, pid)[:5]


def _heritage(st: State, pid: str) -> dict:
    """Where somebody's family came from: told, and worked out.

    `declared` is what somebody was told about this person directly.
    `mix` is what that person inherits from everybody above them, and is
    never written to a row -- see the note in `kinship.heritage_of` for why
    a computed percentage in a column goes wrong the day a grandparent is
    added.
    """
    from .graph.kinship import heritage_display, heritage_of
    g = st.graph
    declared = {p: dict(p_.heritage) for p, p_ in g.people.items()
                if p_.heritage}
    mix = heritage_of(g, declared, pid)
    own = declared.get(pid, {})
    return {
        "declared": [{"label": k, "share": v, "pct": round(v * 100, 1)}
                     for k, v in sorted(own.items(), key=lambda kv: -kv[1])],
        "mix": heritage_display(mix),
        "inherited": not own,
        # every label anybody in the file has used, so the box can offer
        # them rather than making somebody spell "Northumbrian" twice
        "known_labels": sorted({lab for d in declared.values() for lab in d}),
    }


def _dna(st: State, pid: str) -> dict:
    """How much DNA this person and the subject are expected to share.

    EXPECTED, not measured. Two full siblings share 50% on average and
    anywhere from about 38% to 61% in fact; the number here is the average,
    which is the only one that can be worked out from a tree.
    """
    from .graph.kinship import bloodline, dna_display, shared_dna
    g, sub = st.graph, st.subject
    kin = st.kin.of(pid) if sub else None
    share = shared_dna(g, sub, pid, kin=kin) if sub else None
    return {
        "share": share,
        "display": dna_display(share),
        "with_name": (g.people[sub].full_name
                      if sub and sub in g.people else ""),
        "bloodline": bloodline(g, pid, depth=4),
        "note": "Expected average. Real DNA varies either side of it, "
                "and beyond second cousins a pair may share none at all.",
        # Why it is zero, which is a different sentence for a husband than
        # for somebody nobody has yet connected to the rest of the file.
        "why": ("" if share else
                ("Related by marriage — no shared ancestor."
                 if kin and kin.group == "married_in" else
                 "No shared ancestor has been recorded.")),
    }


def _relate(st: State, a: str, b: str) -> dict:
    """How any two people in the file are related.

    THE PATH IS THE ANSWER. "Second cousins once removed" is a label nobody
    repeats; "up to William Whitcombe, who was her great-grandfather and his
    great-great-grandfather" is what gets said at a funeral, and it is the
    only form somebody can check against their own research.

    Where the two married, their coefficient of inbreeding comes with it —
    that is what F is a statement about, and the pair who married is the
    only place it means anything.
    """
    from .analysis import consang
    from .graph.kinship import relate
    g = st.graph
    if a not in g.people or b not in g.people:
        return {"error": "Choose two people who are both in this file.",
                "ok": False}
    r = relate(g, a, b)
    out = r.to_dict()
    who = lambda p: {"id": p, "name": g.people[p].full_name,
                     "life": g.people[p].lifespan, "sex": g.people[p].sex}
    out["people"] = {"a": who(a), "b": who(b)}
    out["ok"] = True
    # Married to each other? Then F for any child of theirs is the fact
    # that matters, and it is the one place the number is not idle.
    married = any(a in u.partners and b in u.partners
                  for u in g.unions.values())
    out["married"] = married
    if married and r.related:
        f = consang.inbreeding_of_child(g, a, b)
        out["inbreeding"] = {"coefficient": round(f, 6), "percent": consang.pct(f)}
    out["note"] = ("Worked out from what is in this file. A relation Helix "
                   "cannot see is one nobody has entered yet.")
    return out


def _relatives(st: State) -> dict:
    """Everybody in the file, in tabs, closest first.

    The tabs are drop-downs rather than a flat list because a real family
    file is hundreds of people and the useful question is almost always
    "who are my first cousins", not "who is person 214".
    """
    g, k = st.graph, st.kin
    return {
        "subject": st.subject,
        "subject_name": (g.people[st.subject].full_name
                         if st.subject in g.people else ""),
        "total": len(g.people),
        "groups": [_with_people(st, grp) for grp in k.groups()],
    }


# What makes a record LOOK unfinished at a glance. Deliberately short: a
# red dot beside four hundred names is decoration, so it is only shown for
# the two things that stop somebody being findable at all -- no full name,
# and no dates -- plus a line that has simply never been started.
def _needs_work(g, p) -> str:
    if not (p.given or "").strip() or not (p.surname or "").strip():
        return "no full name"
    if not p.birth.known and not p.death.known:
        return "no dates"
    if not g.parents(p.id, primary_only=False):
        return "no parents recorded"
    return ""


def _with_people(st: State, grp: dict) -> dict:
    people = [_kin_brief(st, p) for p in grp["people"]]
    return dict(grp, people=people,
                needs=sum(1 for x in people if x["needs"]))


def _kin_brief(st: State, pid: str) -> dict:
    from .store import album
    p = st.graph.people[pid]
    kin = st.kin.of(pid)
    port = album.portrait_of(st.con, pid)
    return {"id": pid, "name": p.full_name, "life": p.lifespan, "sex": p.sex,
            "relation": kin.label, "steps": kin.steps, "group": kin.group,
            "portrait": port["name"] if port else None,
            "needs": _needs_work(st.graph, p),
            "is_subject": pid == st.subject}


def _kin_detail(st: State, pid: str) -> dict:
    """One person, measured twice.

    HOW THEY STAND TO YOU is what the profile says in words. HOW EVERYONE
    ELSE STANDS TO THEM is what lights the chart up when you click a name:
    their brothers and sisters, their cousins, their second cousins. Those
    are two different measurements from two different origins, and reading
    the second off the first is the mistake that would put YOUR cousins in
    a halo around SOMEBODY ELSE.
    """
    g = st.graph
    kin = st.kin.of(pid)
    theirs = st.kin.relatives_of(pid)
    return {
        "id": pid,
        "relation": kin.to_dict(),
        "counts": household(g, pid),
        "highlight": {key: ids for key, ids in theirs.items() if ids},
        "highlight_titles": {grp["key"]: grp["title"] for grp in all_groups()},
        "through": (_brief(g, kin.through)
                    if kin.through and kin.through in g.people else None),
    }


def _coerce(v: str):
    if v[:1] in "[{":                       # a JSON list, e.g. labels.lines
        try:
            return json.loads(v)
        except ValueError:
            pass
    low = v.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v


def _person_detail(st: State, pid: str) -> dict:
    g = st.graph
    p = g.people[pid]
    evs = []
    for r in st.con.execute(
        "SELECT e.type,e.date_json,e.description,pl.name place,e.confidence,"
        "(SELECT COUNT(*) FROM citation c WHERE c.event_id=e.id) cites "
        "FROM event e JOIN event_role er ON er.event_id=e.id "
        "LEFT JOIN place pl ON pl.id=e.place_id WHERE er.person_id=? "
        "ORDER BY e.date_sort", (pid,)
    ):
        from .model.gendate import GenDate
        d = GenDate.from_json(r["date_json"])
        evs.append({"type": r["type"], "date": d.display, "place": r["place"] or "",
                    "desc": r["description"] or "", "confidence": r["confidence"],
                    "citations": r["cites"]})
    from .store import album
    kin = st.kin.of(pid)
    return {
        "id": pid, "name": p.full_name, "life": p.lifespan, "age": p.age,
        "sex": p.sex, "confidence": p.confidence,
        "given": p.given, "surname": p.surname,
        "birth": p.birth.display, "death": p.death.display,
        "birth_place": p.birth_place, "occupation": p.occupation,
        "education": p.education, "notes": p.notes or "",
        "events": evs,
        # WHAT A PROFILE PAGE IS FOR. The relation in words and in numbers,
        # the counts, the photographs, and everything anybody has written
        # down. `relationship` is kept as it was so nothing that reads it
        # breaks; `kin` is the same fact with structure on it.
        "kin": kin.to_dict(),
        "counts": household(g, pid),
        "photos": _photos(st, p),
        "missing": _missing(g, st.con, p),
        "complete": _completeness(g, p),
        # THE THREE THINGS A PROFILE ANSWERS BESIDES "who is this". Where
        # their family came from, how much blood you share, and what is
        # worth going and looking up about them next.
        "heritage": _heritage(st, pid),
        "dna": _dna(st, pid),
        "gaps": _person_gaps(st, pid),
        "inbreeding": _inbreeding(st, pid),
        "relationship": kin.label if st.subject else "",
        "is_subject": pid == st.subject,
        # WHICH FAMILY EACH PARENT IS A PARENT THROUGH. Needed so the
        # panel can offer to take a wrong one off again -- a father hung on
        # the wrong man is the commonest thing to want back.
        "parents": [dict(_brief(g, x), union_id=_parent_union(g, pid, x))
                    for x in g.parents(pid, False)],
        "partners": [_brief(g, x) for x in g.partners(pid)],
        "children": [_brief(g, x) for x in g.children(pid)],
        "siblings": [dict(_brief(g, x), kind=g.sibling_kind(pid, x))
                     for x in _siblings(g, pid)],
        "families": _families(g, pid),
        "on_thread": pid in thread(g, st.subject).members,
    }


def _photos(st: State, p) -> list[dict]:
    """Somebody's pictures, with what each one says about WHEN.

    A PORTRAIT IS THE ONE THAT LOOKS LIKE THEM NOW; the others are what they
    looked like before, and a photograph nobody can date is half a
    photograph. Somebody who knows a face was "about twelve" there has said
    something worth keeping, so both readings are accepted and the one that
    can be worked out is worked out.
    """
    from .model.gendate import parse as parse_date
    from .store import album
    born = p.birth
    out = []
    for ph in album.photos_of(st.con, p.id):
        raw = (ph.get("taken") or "").strip()
        when, age, year = "", None, None
        if raw:
            digits = "".join(c for c in raw if c.isdigit())
            bare = raw.replace("aged", "").replace("age", "").strip()
            if bare.isdigit() and len(bare) <= 3 and int(bare) <= 120:
                # An AGE, which is what somebody usually knows about an old
                # photograph. The year follows from the birth, if there is one.
                age = int(bare)
                if born.known and born.earliest:
                    year = born.earliest.year + age
                when = f"aged {age}" + (f", about {year}" if year else "")
            else:
                d = parse_date(raw)
                if d.known and d.earliest:
                    year = d.earliest.year
                    if born.known and born.earliest:
                        age = year - born.earliest.year
                    when = d.display + (f" · aged about {age}"
                                        if age is not None and 0 <= age < 120
                                        else "")
                else:
                    when = raw            # kept verbatim, rule five
        out.append({**ph, "when": when, "age": age, "year": year})
    # Oldest first among the ones that can be ordered, so a profile reads as
    # a life rather than as an upload order.
    out.sort(key=lambda x: (not x["portrait"], x["year"] is None,
                            x["year"] or 0))
    return out


def _parent_union(g, child: str, parent: str) -> str:
    """The family that makes this person that person's parent."""
    for uid in g.people[child].child_of_all:
        u = g.unions.get(uid)
        if u and parent in u.partners:
            return uid
    return ""


def _brief(g, pid: str) -> dict:
    p = g.people[pid]
    # `sex` is here so the panel knows whether it still needs a "+ Add father"
    # or a "+ Add mother" button.
    return {"id": pid, "name": p.full_name, "life": p.lifespan, "sex": p.sex}


# ONE DEFINITION OF A SIBLING, and it lives in the module that owns the word
# "relation". Written out twice the two drifted: the profile counted
# half-brothers and the sidebar did not.
_siblings = siblings_of


def _families(g, pid: str) -> list[dict]:
    """Children grouped under the partner they belong to.

    This is the one piece of the panel that teaches somebody something they
    did not know: seeing their father's children split into two lists is how
    a person discovers the word half-brother without being taught it. A
    family with no partner recorded still gets its own group, headed so the
    UI can offer to name the other parent.
    """
    out = []
    for uid in g.people[pid].unions:
        u = g.unions.get(uid)
        if not u:
            continue
        others = [x for x in u.partners if x != pid]
        out.append({
            "union_id": uid,
            "partner": _brief(g, others[0]) if others else None,
            "children": [_brief(g, c) for c in u.children],
            # WHETHER THEY MARRIED. Two people with a child between them are
            # a family whether or not they ever married, and every screen
            # that says "married" of a couple who did not is telling a small
            # lie about two real people.
            "kind": u.type or "unknown",
            "word": u.word,
            "married": u.married,
            "date": u.date.display,
            "place": u.place,
        })
    return out


def _missing(g, con, p) -> list[str]:
    """What is NOT recorded about somebody, named rather than scored.

    `_completeness` gives a percentage, which is the right thing for sorting
    a list and the wrong thing to show a person: 43% tells you to feel bad
    and not what to do. This says "no birth date, no parents, no
    photograph", which is a next action.

    Never a reproach and never a demand. Plenty of these will stay unknown
    forever, and a file that nags about a great-grandmother nobody
    photographed is a file people stop opening.
    """
    from .store import album
    out = []
    if not p.birth.known:
        out.append("when they were born")
    if not p.birth_place:
        out.append("where they were born")
    if p.living is not True and not p.death.known and (p.birth_year or 0) < 1930:
        out.append("when they died")
    if not g.parents(p.id, primary_only=False):
        out.append("their parents")
    if not p.occupation:
        out.append("what they did")
    if not album.portrait_of(con, p.id):
        out.append("a photograph")
    if not p.notes:
        out.append("anything you remember")
    return out


def _completeness(g, p) -> int:
    """How finished a record looks, 0-100. Deliberately crude: it exists to
    sort a list so the half-filled records rise to the top, not to grade
    anybody's research."""
    have = [bool(p.given), bool(p.surname), p.birth.known, p.death.known,
            bool(p.birth_place), bool(g.parents(p.id, primary_only=False)),
            p.sex in ("M", "F")]
    return round(100 * sum(1 for x in have if x) / len(have))


def _people_list(st: State) -> list[dict]:
    """Every person as a plain table. Some people prefer a list to a chart,
    and it is the fastest way to spot a half-finished record."""
    g = st.graph
    return [{"id": p.id, "name": p.full_name, "surname": p.surname,
             "given": p.given, "life": p.lifespan,
             "born": p.birth.year, "sex": p.sex,
             "complete": _completeness(g, p),
             "is_subject": p.id == st.subject}
            for p in g.people.values()]


def make_server(dbpath: str, host="127.0.0.1", port=8731) -> ThreadingHTTPServer:
    """Build the server without starting it.

    Exists so the tests can drive the real thing over real HTTP. That is not
    fussiness: every database-backed endpoint once failed with a threading
    error that no test caught, because the tests called the functions
    directly and only a request thread triggers it. Pass port 0 for a free
    one and read `srv.server_port` back.
    """
    global ST
    ST = State(dbpath)
    return ThreadingHTTPServer((host, port), Handler)


def serve(dbpath: str, host="127.0.0.1", port=8731, open_browser=True):
    srv = make_server(dbpath, host, port)
    url = f"http://{host}:{srv.server_port}/"
    print(f"\n  Helix is running.  Open  {url}\n  (Ctrl-C to stop)\n")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("  Stopped.")
