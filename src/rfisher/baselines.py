"""Compatibility access to RadioFisher's CHIME baseline construction.

RFIsher retains its recorded input file and generator destination. The
array geometry and density calculation belong to RadioFisher.
"""
from importlib import resources
from pathlib import Path

from radiofisher import baselines as _baselines

CYLINDERS = _baselines.CYLINDERS
CYLINDER_SPACING_M = _baselines.CYLINDER_SPACING_M
FEEDS = _baselines.FEEDS
FEED_SPACING_M = _baselines.FEED_SPACING_M
METERS_PER_X = _baselines.METERS_PER_X
INTER_FILE = _baselines.INTER_FILE

density = _baselines.density
radiofisher_file = _baselines.radiofisher_file


def inter_file() -> Path:
    """The RFIsher input retained for recorded forecast provenance."""
    return Path(str(resources.files("rfisher.data").joinpath(INTER_FILE)))


def build(path=None) -> Path:
    """Regenerate the historical RFIsher input using RadioFisher."""
    path = Path(path) if path is not None else Path(__file__).parent / "data" / INTER_FILE
    return _baselines.build(path)


if __name__ == "__main__":  # pragma: no cover
    print(build())
