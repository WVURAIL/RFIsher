"""What a science model must supply for a residual tolerance.

The tolerance rule (``rfisher.tolerance.rule``) turns a science model into a
tolerance on a residual: for each scenario, bin and parameter it asks the
model for the bias per unit residual b and the statistical error sigma at the
target integration time, checks that the linear response is stable there, and
prices the residual at zeta * sigma / |b|. Nothing in the rule knows what the
parameters, bins or scenarios mean; a model declares them.

A model is any object with the attributes and methods of :class:`ScienceModel`.
The one model today is ``rfisher.forecast.radiofisher_bao.model.RadioFisherBAO``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

SCENARIO_ROLES = ("rule", "sensitivity")


@dataclass(frozen=True)
class Parameters:
    """``required`` parameters set a tolerance; ``reported`` ones are listed."""

    required: tuple[str, ...]
    reported: tuple[str, ...] = ()

    @property
    def all(self) -> tuple[str, ...]:
        """Every parameter, required first, in the model's order."""
        return self.required + self.reported


@dataclass(frozen=True)
class Scenario:
    """A condition under which the model is evaluated.

    ``role`` is ``rule`` for the scenario a verdict rests on and
    ``sensitivity`` for one that is only reported. ``suppression_db`` is the
    suppression S the scenario assumes for the residual; it is listed beside
    the tolerance and never folded into it. ``response_source`` names what
    supplies the model's response in this scenario.
    """

    name: str
    role: str
    suppression_db: float
    response_source: str


@dataclass(frozen=True)
class Bin:
    """One model bin: its index, a label, and its edges as the table rounds them."""

    index: int
    label: str
    low: float
    high: float


@runtime_checkable
class ScienceModel(Protocol):
    """The interface ``rfisher.tolerance`` needs from a science model."""

    parameters: Parameters
    target_years: float
    zeta: float
    year_grid: tuple[float, ...]
    maximum_tolerance_ratio: float
    scenarios: tuple[Scenario, ...]

    def load(self, scenario: str) -> None:
        """Make the scenario's response available; raise if it cannot be."""

    def hours(self, years: float) -> float:
        """Integration hours of ``years`` of observing."""

    def bins(self) -> tuple[Bin, ...]:
        """The model's bins, in index order."""

    def bins_for_band(self, low_mhz: float, high_mhz: float
                      ) -> tuple[tuple[int, ...], bool]:
        """The bins that overlap a frequency band, and whether they cover it."""

    def response(self, scenario: str, bin_index: int, hours: float
                 ) -> tuple[dict[str, float], dict[str, float]]:
        """``(b, sigma)`` for every parameter at once; raises on a refusal."""

    def accept(self, scenario: str, bin_index: int, hours: float,
               parameter: str) -> tuple[float, int]:
        """``(drift, sign count)`` of the stability test; raises on a refusal."""

    def identity(self, *, responses: bool = True) -> dict:
        """Content digests of the inputs, including ``sources``, a mapping of
        source file to digest. With ``responses`` False, only the digests
        that need no response loaded; a digest that needs one is a field of
        an entry of ``banks``."""
