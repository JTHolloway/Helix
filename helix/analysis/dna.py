"""DNA match integration.

Shared centimorgans give an INDEPENDENT check on a paper trail, and a way to
break through a brick wall that documents cannot.

  * Store matches in the dna_match table with shared_cM and platform.
  * Predict relationship ranges from the Shared cM Project v4 distributions
    (Bettinger et al.). Always report a RANGE and a probability, never a
    single relationship: 850 cM is consistent with grandparent, aunt/uncle,
    half-sibling and niece/nephew all at once.
  * Compare predicted against documented: a mismatch beyond the expected
    range is worth investigating, and is how misattributed parentage is
    usually discovered. Handle that finding with care -- it can be
    distressing, so the UI should present it as "worth checking" rather than
    as an accusation.
  * Endogamy inflates shared cM. If graph.endogamy() is non-empty, widen the
    predicted ranges and say so.
"""
from __future__ import annotations


def predict(shared_cm: float) -> list[tuple[str, float]]:
    raise NotImplementedError("Phase 8. Needs the Shared cM Project table.")
