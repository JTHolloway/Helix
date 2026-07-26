"""The Thread: your ancestral cone, and what vanishes without any one person.

Single responsibility: answer "who am I descended from?" and "if this person
had never been born, how much of this chart disappears?"

The second question is a DOMINATOR problem on the ancestry DAG. Person X is
erased by removing P if every path from any root to X passes through P.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ThreadResult:
    members: set[str] = field(default_factory=set)
    edges: set[tuple[str, str]] = field(default_factory=set)   # (parent, child)
    by_gen: dict[int, set[str]] = field(default_factory=dict)

    def __contains__(self, pid: str) -> bool:
        return pid in self.members


def thread(graph, subject_id: str | None) -> ThreadResult:
    """Everyone without whom the subject would not exist, plus the subject."""
    res = ThreadResult()
    if not subject_id or subject_id not in graph.people:
        return res
    anc = graph.ancestors(subject_id)
    res.members = set(anc)
    for pid, gen in anc.items():
        res.by_gen.setdefault(gen, set()).add(pid)
    for pid in anc:
        for par in graph.parents(pid, primary_only=False):
            if par in anc:
                res.edges.add((par, pid))
    return res


# ------------------------------------------------------------- dominators --
def _topo_order(graph) -> list[str]:
    """Topological order of the descent DAG (parents before children)."""
    indeg: dict[str, int] = {p: 0 for p in graph.people}
    for pid in graph.people:
        for kid in graph.children(pid):
            indeg[kid] += 1
    queue = [p for p, d in indeg.items() if d == 0]
    order: list[str] = []
    while queue:
        n = queue.pop()
        order.append(n)
        for kid in graph.children(n):
            indeg[kid] -= 1
            if indeg[kid] == 0:
                queue.append(kid)
    # any leftovers are in a cycle (bad data); append so nothing is lost
    order.extend(p for p in graph.people if p not in set(order))
    return order


def dominator_tree(graph) -> dict[str, str | None]:
    """Iterative Cooper-Harvey-Kennedy dominators over a virtual super-root.

    Returns idom[person] = immediate dominator. Everyone in P's dominator
    subtree vanishes if P is never born.
    """
    order = _topo_order(graph)
    pos = {p: i for i, p in enumerate(order)}
    ROOT = "\x00ROOT"
    pos[ROOT] = -1
    idom: dict[str, str | None] = {ROOT: ROOT}

    def preds(p: str) -> list[str]:
        ps = graph.parents(p, primary_only=False)
        return ps if ps else [ROOT]

    def intersect(a: str, b: str) -> str:
        while a != b:
            while pos[a] > pos[b]:
                a = idom[a] or ROOT
            while pos[b] > pos[a]:
                b = idom[b] or ROOT
        return a

    changed = True
    guard = 0
    while changed and guard < 50:
        changed = False
        guard += 1
        for p in order:
            new = None
            for q in preds(p):
                if q not in idom:
                    continue
                new = q if new is None else intersect(new, q)
            if new is not None and idom.get(p) != new:
                idom[p] = new
                changed = True
    idom.pop(ROOT, None)
    return {k: (None if v == ROOT else v) for k, v in idom.items()}


class Contingency:
    """'If this person had never been born, who disappears?'

    The important modelling point: descent is an AND-join, not an OR-join.
    A child needs BOTH parents, so losing either parent erases the child, and
    erasing the child erases everything below them.

    That makes the answer exactly the descendant closure -- no dominator
    machinery required. (Dominators answer a different question, kept below
    for the 'which lines pass only through here' analysis.)

    Adoptive, step and foster links are NOT followed: a step-parent's absence
    does not un-birth anybody.
    """

    def __init__(self, graph, biological_only: bool = True):
        self.graph = graph
        self.biological_only = biological_only
        self._cache: dict[str, set[str]] = {}

    def erased_by(self, pid: str) -> set[str]:
        if pid in self._cache:
            return self._cache[pid]
        out: set[str] = set()
        stack = [pid]
        while stack:
            n = stack.pop()
            if n in out:
                continue
            out.add(n)
            stack.extend(self.graph.children(n))
        self._cache[pid] = out
        return out

    def criticality(self) -> dict[str, int]:
        """How many people each person is structurally responsible for.
        Feeds the criticality colour mode and the 'most important ancestors'
        list: the chart becomes a heatmap of who the family hangs on."""
        return {p: len(self.erased_by(p)) for p in self.graph.people}

    def report(self, pid: str, subject_id: str | None = None) -> dict:
        gone = self.erased_by(pid)
        people = self.graph.people
        surnames = {people[x].surname for x in gone if people[x].surname}
        gens = {self.graph.generation_of(x, self.graph.apexes()) for x in gone}
        return {
            "person_id": pid,
            "name": people[pid].full_name if pid in people else "?",
            "removed_count": len(gone) - 1,
            "removed": gone,
            "surnames_lost": sorted(surnames),
            "generations_lost": (max(gens) - min(gens) + 1) if gens else 0,
            "subject_removed": bool(subject_id and subject_id in gone),
        }
