"""The frequency channels and the redshift range each one covers."""
import csv
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from radiofisher.units import NU21_MHZ

COLUMNS = ("channel", "low_mhz", "high_mhz")


@dataclass(frozen=True)
class Band:
    """One channel: a frequency band and the 21 cm redshifts it observes."""
    channel: int
    low_mhz: float
    high_mhz: float
    role: str = "dtv"

    @property
    def z_min(self) -> float:
        return NU21_MHZ / self.high_mhz - 1

    @property
    def z_max(self) -> float:
        return NU21_MHZ / self.low_mhz - 1

    @property
    def z_center(self) -> float:
        """The redshift RadioFisher evaluates the bin at."""
        return 0.5 * (self.z_min + self.z_max)


def channels(path=None) -> list[Band]:
    """The channels of a band file, by default the DTV allocations 14 to 36 and the control channel 37.

    A band file is a CSV with the columns channel, low_mhz and high_mhz and an
    optional role. Every band must lie below the 21 cm rest frequency.
    """
    source = resources.files("rfisher.data").joinpath("dtv_channels.csv") if path is None else Path(path)
    reader = csv.DictReader(source.read_text().splitlines())
    missing = set(COLUMNS) - set(reader.fieldnames or ())
    if missing:
        raise ValueError(f"{source} lacks the columns {sorted(missing)}")
    bands = [Band(int(r["channel"]), float(r["low_mhz"]), float(r["high_mhz"]), r.get("role") or "dtv")
             for r in reader]
    if not bands:
        raise ValueError(f"{source} holds no channels")
    numbers = [b.channel for b in bands]
    if len(set(numbers)) != len(numbers):
        raise ValueError(f"{source} repeats a channel number")
    for b in bands:
        if not 0 < b.low_mhz < b.high_mhz <= NU21_MHZ:
            raise ValueError(f"channel {b.channel} needs 0 < low_mhz < high_mhz <= {NU21_MHZ} MHz")
    return bands


def channel(number: int, path=None) -> Band:
    for band in channels(path):
        if band.channel == number:
            return band
    raise KeyError(f"no channel {number}")
