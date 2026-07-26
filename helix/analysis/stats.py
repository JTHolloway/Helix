"""Family statistics: the numbers that make people say 'I had no idea'.

  * average age at first marriage, by generation and by sex
  * average number of children, and how it collapses after 1880
  * infant mortality rate per decade
  * average lifespan excluding infant deaths (the honest figure -- raw means
    are dragged down catastrophically by infant mortality and mislead people
    into thinking nobody reached fifty)
  * longest and shortest lives; oldest mother; youngest father
  * migration distance per generation, if places are geocoded
  * surname frequency and extinction dates
  * pedigree collapse: distinct ancestors at generation n vs the 2^n maximum
"""
from __future__ import annotations

from statistics import median


def summary(graph) -> dict:
    people = graph.people.values()
    lifes = [(p.death.sort_value - p.birth.sort_value) for p in people
             if p.birth.sort_value and p.death.sort_value]
    adult = [x for x in lifes if x >= 5]
    return {
        "count": len(graph.people),
        "with_both_dates": len(lifes),
        "median_lifespan_all": round(median(lifes), 1) if lifes else None,
        "median_lifespan_excl_infants": round(median(adult), 1) if adult else None,
        "infant_deaths": sum(1 for x in lifes if x < 5),
        "infant_rate": round(sum(1 for x in lifes if x < 5) / len(lifes), 3) if lifes else None,
        "endogamy_cases": len(graph.endogamy()),
    }


def by_decade(graph) -> dict:
    raise NotImplementedError("Phase 7 -- see the docstring for the full list.")
