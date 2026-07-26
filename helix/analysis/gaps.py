"""Research gap ranking -- 'what should I look for next?'

This turns the chart into a to-do list, which is the difference between a
poster and a working research tool.

SCORE for each missing fact:
    score = descendants_affected
          * source_availability(year, country, record_type)
          * (1 / effort)

  descendants_affected  people whose line is blocked by this gap. A missing
                        1790 birth that blocks 400 descendants beats a missing
                        1890 occupation that blocks nobody.
  source_availability   England & Wales: civil registration from Jul 1837,
                        censuses 1841-1921, parish registers from 1538 with
                        a large gap during the Commonwealth (1642-1660).
                        Scotland: statutory from 1855, far richer.
                        Ireland: much destroyed in 1922 -- weight down.
  effort                free online (1) < paid index (2) < record office
                        visit (5) < overseas archive (10).

OUTPUT
  A ranked list of research_task rows: "Find the 1841 census entry for
  Thomas Whitcombe of Walcot -- would unblock 63 descendants."
"""
from __future__ import annotations


def rank(graph, con, *, country: str = "england", limit: int = 40) -> list[dict]:
    raise NotImplementedError("Phase 7.")
