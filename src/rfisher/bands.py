"""The 6 MHz channels and the redshift range each one covers."""
import csv
from dataclasses import dataclass
from importlib import resources

from radiofisher.units import NU21_MHZ


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


def channels() -> list[Band]:
    """The DTV allocations 14 to 36 and the radio-astronomy channel 37 (control)."""
    text = resources.files("rfisher.data").joinpath("dtv_channels.csv").read_text()
    return [Band(int(r["channel"]), float(r["low_mhz"]), float(r["high_mhz"]), r["role"])
            for r in csv.DictReader(text.splitlines())]


def channel(number: int) -> Band:
    for band in channels():
        if band.channel == number:
            return band
    raise KeyError(f"no channel {number}")
