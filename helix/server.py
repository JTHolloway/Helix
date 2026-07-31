"""Local web server. Serves the app and a small JSON API on 127.0.0.1.

Uses only the standard library so `helix serve` works before you have
installed anything else. FastAPI is optional and only adds auto-docs.
"""
from __future__ import annotations

import json
import mimetypes
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .graph import build as gbuild
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
    "/api/person/heritage": lambda con, b: records.set_heritage(con, b),
}


def _add_photo(con, b: dict) -> dict:
    """A photograph, copied into the album beside the family file.

    The bytes arrive as a `data:` URL because that is what a browser's
    FileReader produces and because the standard library has no multipart
    parser it would be wise to point at untrusted input.
    """
    from .store import album
    name, _path = album.store_data_url(ST.dbpath, b["data"],
                                       b.get("filename", ""))
    mid = album.attach(con, b["id"], name, caption=b.get("caption", ""),
                       portrait=b.get("portrait", True) is not False)
    return {"ok": True, "id": b["id"], "media_id": mid, "name": name}


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
                             "laser": d.laser} for d in registry.all_designs()],
                "styles": Style.list_presets(),
                "people": [{"id": p.id, "name": p.full_name,
                            "life": p.lifespan, "sex": p.sex}
                           for p in sorted(g.people.values(),
                                           key=lambda x: (x.surname, x.given))],
            })
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
            # named by the hash of its own bytes, so it can never go stale
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
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
                       subject=q.get("subject") or st.subject)
    n = int(q.get("limit", 40))
    # WHO THEY ARE TO YOU, added here because this is the only place that
    # knows. Two people recorded as nothing but "Harris" produce two
    # identical questions; "your great-grandmother" and "your third cousin
    # twice removed" are what tell them apart.
    for r in rows[:n]:
        k = st.kin.of(r["pid"])
        r["relation"] = "" if k.group in ("self", "unrelated") else k.label
    return {"gaps": rows[:n], "summary": gapmod.summary(rows),
            "shown": min(n, len(rows)), "total": len(rows),
            "scope": "everybody" if within is None else "this chart",
            "considered": len(st.graph.people) if within is None else len(within)}


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
    share = shared_dna(g, sub, pid, kin=st.kin.of(pid)) if sub else None
    return {
        "share": share,
        "display": dna_display(share),
        "with_name": (g.people[sub].full_name
                      if sub and sub in g.people else ""),
        "bloodline": bloodline(g, pid, depth=4),
        "note": "Expected average. Real DNA varies either side of it, "
                "and beyond second cousins a pair may share none at all.",
    }


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
        "groups": [dict(grp, people=[_kin_brief(st, p) for p in grp["people"]])
                   for grp in k.groups()],
    }


def _kin_brief(st: State, pid: str) -> dict:
    from .store import album
    p = st.graph.people[pid]
    kin = st.kin.of(pid)
    port = album.portrait_of(st.con, pid)
    return {"id": pid, "name": p.full_name, "life": p.lifespan, "sex": p.sex,
            "relation": kin.label, "steps": kin.steps, "group": kin.group,
            "portrait": port["name"] if port else None,
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
        "photos": album.photos_of(st.con, pid),
        "missing": _missing(g, st.con, p),
        "complete": _completeness(g, p),
        # THE THREE THINGS A PROFILE ANSWERS BESIDES "who is this". Where
        # their family came from, how much blood you share, and what is
        # worth going and looking up about them next.
        "heritage": _heritage(st, pid),
        "dna": _dna(st, pid),
        "gaps": _person_gaps(st, pid),
        "relationship": kin.label if st.subject else "",
        "is_subject": pid == st.subject,
        "parents": [_brief(g, x) for x in g.parents(pid, False)],
        "partners": [_brief(g, x) for x in g.partners(pid)],
        "children": [_brief(g, x) for x in g.children(pid)],
        "siblings": [dict(_brief(g, x), kind=g.sibling_kind(pid, x))
                     for x in _siblings(g, pid)],
        "families": _families(g, pid),
        "on_thread": pid in thread(g, st.subject).members,
    }


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
