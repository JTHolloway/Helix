"""Design registry.

Every design is (engine x router x glyph x label policy). Engines register
themselves here so the GUI can present a gallery and the CLI can name one.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from .plan import RenderPlan


@dataclass
class DesignInfo:
    key: str
    name: str
    family: str            # radial | linear | network | spatial | experimental
    blurb: str
    good_for: str
    laser: str             # excellent | good | poor
    fn: Optional[Callable] = None

    @property
    def built(self) -> bool:
        """Whether this design actually draws anything yet.

        SIX OF TWENTY DID NOT. They were registered so the gallery could
        show them "greyed out with a clear note", and nothing ever greyed
        them out -- so a third of the gallery was pictures you could click
        to get an error. A design says for itself whether it is finished,
        and the gallery reads that rather than finding out by crashing.
        """
        return not getattr(self.fn, "todo", False)


_REGISTRY: dict[str, DesignInfo] = {}


def register(key: str, name: str, family: str, blurb: str,
             good_for: str = "", laser: str = "good"):
    def deco(fn: Callable) -> Callable:
        _REGISTRY[key] = DesignInfo(key, name, family, blurb, good_for, laser, fn)
        return fn
    return deco


def get(key: str) -> DesignInfo:
    if key not in _REGISTRY:
        raise KeyError(
            f"No design called '{key}'. Available: {', '.join(sorted(_REGISTRY))}"
        )
    return _REGISTRY[key]


def all_designs() -> list[DesignInfo]:
    return sorted(_REGISTRY.values(), key=lambda d: (d.family, d.name))


def run(key: str, graph, settings, style) -> RenderPlan:
    return get(key).fn(graph, settings, style)      # type: ignore[misc]
