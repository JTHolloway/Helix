from helix.graph.validate import validate


def test_runs_clean_enough_on_sample(graph):
    issues = validate(graph)
    errors = [i for i in issues if i.severity == "error"]
    assert not errors, f"sample data has real errors: {[e.message for e in errors][:3]}"


def test_messages_name_the_person(graph):
    for i in validate(graph):
        assert len(i.message) > 15
        assert i.message[0].isupper() or i.message[0] == "["


def test_infant_death_same_year_is_not_an_error():
    """Born 27 Nov 1741, died 1741. Comparing midpoints says the death came
    first and raises a false alarm. Intervals say it is fine, because it is.
    A validator that cries wolf gets switched off."""
    from helix.graph.validate import _impossible_order
    from helix.model.gendate import parse
    assert not _impossible_order(parse("27 Nov 1741"), parse("1741"))
    assert not _impossible_order(parse("abt 1800"), parse("1798"))
    assert _impossible_order(parse("1850"), parse("1820"))


def test_vague_dates_never_trigger_errors():
    from helix.graph.validate import _impossible_order
    from helix.model.gendate import parse
    for a, b in [("abt 1834", "abt 1836"), ("bef 1900", "1880"),
                 ("1850s", "1855"), ("", "1900"), ("junk", "junk")]:
        assert not _impossible_order(parse(a), parse(b))
