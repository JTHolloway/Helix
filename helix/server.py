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
}


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

    @property
    def contingency(self) -> Contingency:
        if self._cont is None:
            self._cont = Contingency(self.graph)
        return self._cont


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
        max_people=int(q["max_people"]) if q.get("max_people") else None,
        weight_mode=style.get("layout.weight_mode", "leaves"),
        redact_living=q.get("redact") == "1")
    return registry.run(design, ST.graph, s, style)


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
    rel = g.relationship(st.subject, pid) if st.subject else ""
    return {
        "id": pid, "name": p.full_name, "life": p.lifespan, "age": p.age,
        "sex": p.sex, "confidence": p.confidence,
        "given": p.given, "surname": p.surname,
        "birth": p.birth.display, "death": p.death.display,
        "birth_place": p.birth_place, "occupation": p.occupation,
        "events": evs,
        "relationship": rel,
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


def _siblings(g, pid: str) -> list[str]:
    """Brothers and sisters through either parent, so a half-sibling is a
    sibling here rather than a special case.

    Walks the FAMILY, not the parents. "Add a brother" on somebody whose
    parents are not recorded yet creates the family that will hold them, and
    two children of a family with no named parents are still siblings.
    """
    fams = list(g.people[pid].child_of_all)          # full brothers and sisters
    for par in g.parents(pid, primary_only=False):   # and half, through either
        fams.extend(g.people[par].unions)
    out, seen = [], {pid}
    for uid in dict.fromkeys(fams):
        u = g.unions.get(uid)
        if not u:
            continue
        for c in u.children:
            if c not in seen:
                seen.add(c)
                out.append(c)
    return out


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
