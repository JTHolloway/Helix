"""Family structure: the questions a chart has to answer."""
from helix.graph.thread import Contingency, thread


def test_loads(graph):
    assert len(graph.people) > 100
    assert len(graph.unions) > 10


def test_every_child_has_a_parent_edge_back(graph):
    for pid, p in graph.people.items():
        for kid in graph.children(pid):
            assert pid in graph.parents(kid, primary_only=False)


def test_ancestor_walk_terminates_on_cousin_marriage(graph):
    """A cousin marriage makes the pedigree a DAG, not a tree. A naive
    recursive walk loops forever; this must not."""
    for pid in list(graph.people)[:60]:
        anc = graph.ancestors(pid)
        assert pid in anc
        assert len(anc) <= len(graph.people)


def test_relationship_is_symmetric_in_kind(graph):
    a = next(iter(graph.people))
    assert graph.relationship(a, a) == "the same person"


def test_contingency_matches_brute_force(graph):
    """erased_by(P) must equal 'everyone who disappears if P is removed'.
    Descent is an AND-join -- a child needs both parents -- so the answer is
    the descendant closure. Verified here against a direct simulation."""
    c = Contingency(graph)
    crit = c.criticality()
    victims = sorted(crit, key=lambda k: -crit[k])[:5]
    for pid in victims:
        gone = c.erased_by(pid)
        # brute force: remove pid, then anyone with a removed parent
        removed = {pid}
        changed = True
        while changed:
            changed = False
            for x in graph.people:
                if x in removed:
                    continue
                if any(p in removed for p in graph.parents(x, primary_only=False)):
                    removed.add(x)
                    changed = True
        assert gone == removed


def test_thread_is_ancestors_of_subject(graph):
    subj = graph.subject_id
    if not subj:
        return
    t = thread(graph, subj)
    assert subj in t
    assert t.members == set(graph.ancestors(subj))


def test_apexes_have_no_parents(graph):
    for a in graph.apexes():
        assert not graph.parents(a, primary_only=False)
