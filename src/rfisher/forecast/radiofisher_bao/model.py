"""The RadioFisher BAO forecast as a science model (``rfisher.science_model``).

The profile (``projects/chime_bao/science_model.yaml``) declares the
parameters, the target time, the role of each delay-filter scenario, the
residual reference and shape the handoff must match, and the band a report
covers by default. It names the science register entries (``register``) that
hold zeta, the year grid and the stability test; those values are read from
the project's register (``rfisher.policy``), their one source. This module
supplies the rest from the forecast: the redshift bins of the experiment, the
bins a frequency band overlaps, and, from the packaged response banks, the
bias per unit residual, sigma, and the stability of the response.

A response bank is loaded, and authenticated, only when a response is first
asked of it, so a model that only maps bands to bins never opens a bank.
"""
from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from pathlib import Path

import numpy as np
import yaml

from rfisher import policy
from rfisher.science_model import SCENARIO_ROLES, Bin, Parameters, Scenario

from . import filter_scenarios
from .bank import experiments
from .bank.banks import bank_source_state
from .bank.physics import HI_REST_FREQUENCY_MHZ
from .bank.resources import DATA_PACKAGE
from .response import (bias_per_unit_residual, load_response_bank,
                       packaged_response_banks, response_stability)

ADAPTER = "radiofisher_bao"
PROFILE_NAME = "science_model.yaml"
PROFILE_KEYS = frozenset({
    "adapter", "experiment", "cosmology", "parameters", "target_years",
    "register", "scenarios", "r_reference", "residual_shapes",
    "report_band_mhz"})
# What the profile's ``register`` names, and the entry each must name.
REGISTER_KEYS = {
    "zeta": "science.systematic_budget.primary_zeta",
    "year_grid": "archive_reference.forecast_year_grid",
    "time_fraction": "science.response_stability.time_fraction",
    "maximum_tolerance_ratio":
        "science.response_stability.maximum_tolerance_ratio",
    "systematic_gain": "transfer.systematic_gain",
    "variance_gain": "transfer.variance_gain",
}
R_REFERENCE_KEYS = frozenset({"definition", "feed_sum", "frame_seconds",
                              "noise_bandwidth_hz", "summed_terms"})
RULE_ROLE = "rule"
# The response banks carry no foreground term (epsilon_fg = 0): the forecast
# prices thermal noise and nothing else.
RESPONSE_EPSILON_FG = 0.0
BIN_EDGE_DECIMALS = 4
COVERAGE_SLACK = 1e-10
# The per-bin tolerance table of the four scenarios at T* = 1 year.
TABLE_NAME = "filter_scenarios_T1yr.csv"
TABLE_DIRECTORY = "tolerances"
# The register values the table depends on; their digest is the table's
# science_register_sha256.
REGISTER_IDS = (
    "archive_reference.three_worlds_parameters",
    "archive_reference.forecast_year_grid",
    "science.response_stability.time_fraction",
    "science.response_stability.maximum_tolerance_ratio",
    "science.systematic_budget.primary_zeta",
)
SOURCES = ("response.py", "filter_scenarios.py", "model.py")


def redshift_range(low_mhz: float, high_mhz: float) -> tuple[float, float]:
    """The 21 cm redshift interval of a band; the low end is its upper edge."""
    return (HI_REST_FREQUENCY_MHZ / high_mhz - 1.0,
            HI_REST_FREQUENCY_MHZ / low_mhz - 1.0)


def packaged_table() -> Path:
    """The packaged per-bin tolerance table."""
    return Path(str(files(DATA_PACKAGE).joinpath(TABLE_DIRECTORY, TABLE_NAME)))


def register_sha256(project: str | Path | None = None) -> str:
    """Digest of the register values the tolerance table depends on."""
    values = {key: policy.value(key, project) for key in REGISTER_IDS}
    payload = json.dumps(values, sort_keys=True, separators=(",", ":"),
                         allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def profile_path(project: str | Path) -> Path:
    """The profile file of a project directory (or the file itself)."""
    path = Path(project)
    return path / PROFILE_NAME if path.is_dir() else path


def load_profile(project: str | Path) -> dict:
    """Read a science profile and refuse anything this adapter cannot honour."""
    path = profile_path(project)
    with path.open(encoding="utf-8") as stream:
        profile = yaml.safe_load(stream)
    if not isinstance(profile, dict) or set(profile) != PROFILE_KEYS:
        raise ValueError(f"{path}: a science profile holds exactly "
                         f"{sorted(PROFILE_KEYS)}")
    if profile["adapter"] != ADAPTER:
        raise ValueError(f"{path}: adapter {profile['adapter']!r} is not "
                         f"{ADAPTER!r}")
    if profile["experiment"] != "chime2022" \
            or profile["cosmology"] != "planck2018":
        raise ValueError(f"{path}: the response banks are chime2022 "
                         "planck2018 builds")
    if not isinstance(profile["target_years"], float):
        raise ValueError(f"{path}: target_years must be written as a float")
    if profile["register"] != REGISTER_KEYS:
        raise ValueError(f"{path}: register must name {REGISTER_KEYS}")
    reference = profile["r_reference"]
    if not isinstance(reference, dict) or set(reference) != R_REFERENCE_KEYS:
        raise ValueError(f"{path}: r_reference holds exactly "
                         f"{sorted(R_REFERENCE_KEYS)}")
    shapes = profile["residual_shapes"]
    if not isinstance(shapes, list) or not shapes or not all(
            isinstance(v, str) for v in shapes):
        raise ValueError(f"{path}: residual_shapes is a list of names")
    band = profile["report_band_mhz"]
    if not (isinstance(band, list) and len(band) == 2 and all(
            isinstance(v, float) for v in band) and band[0] < band[1]):
        raise ValueError(f"{path}: report_band_mhz is [low, high] in MHz, "
                         "written as floats")
    return profile


def report_band_mhz(project: str | Path | None = None) -> tuple[float, float]:
    """The band a report covers by default (default project: the policy's)."""
    band = load_profile(project if project is not None
                        else policy.default_project())["report_band_mhz"]
    return float(band[0]), float(band[1])


class RadioFisherBAO:
    """The BAO distance-scale forecast of CHIME, from RadioFisher banks."""

    def __init__(self, profile: str | Path,
                 response_banks_dir: str | Path | None = None,
                 rf_dir: str | Path | None = None):
        data = load_profile(profile)
        self.profile_path = profile_path(profile)
        self.experiment = data["experiment"]
        self.cosmology = data["cosmology"]
        self.parameters = Parameters(
            required=tuple(data["parameters"]["required"]),
            reported=tuple(data["parameters"].get("reported") or ()))
        self.target_years = float(data["target_years"])
        self.project = self.profile_path.parent
        register = policy.load(self.project)
        named = {key: register.value(ident)
                 for key, ident in data["register"].items()}
        self.zeta = float(named["zeta"])
        self.year_grid = tuple(float(value) for value in named["year_grid"])
        self.time_fraction = float(named["time_fraction"])
        self.maximum_tolerance_ratio = float(named["maximum_tolerance_ratio"])
        self.transfer_gains = {"systematic": float(named["systematic_gain"]),
                               "variance": float(named["variance_gain"])}
        self.r_reference = dict(data["r_reference"])
        self.residual_shapes = tuple(data["residual_shapes"])
        self.report_band_mhz = tuple(float(v)
                                     for v in data["report_band_mhz"])
        scenarios = []
        for entry in data["scenarios"]:
            known = filter_scenarios.scenario(entry["name"])
            declared = (entry["bank"], entry["kfg_fac"],
                        entry["suppression_key"])
            if declared != (known.bank, known.kfg_fac, known.suppression_key):
                raise ValueError(
                    f"{self.profile_path}: scenario {entry['name']!r} declares "
                    f"{declared}; the forecast defines "
                    f"{(known.bank, known.kfg_fac, known.suppression_key)}")
            if entry["role"] not in SCENARIO_ROLES:
                raise ValueError(f"{self.profile_path}: role must be one of "
                                 f"{SCENARIO_ROLES}")
            scenarios.append(Scenario(
                name=known.name, role=entry["role"],
                suppression_db=filter_scenarios.suppression_db(known.name),
                response_source=known.bank))
        rules = [item for item in scenarios if item.role == RULE_ROLE]
        if len(rules) != 1 or rules[0].suppression_db != 0.0:
            raise ValueError(
                f"{self.profile_path}: exactly one scenario has the role "
                f"{RULE_ROLE!r}, and it assumes no suppression (S = 0)")
        self.scenarios = tuple(scenarios)
        self.response_banks_dir = Path(
            response_banks_dir if response_banks_dir is not None
            else packaged_response_banks())
        self.rf_dir = rf_dir
        self._banks = {}

    def hours(self, years: float) -> float:
        """On-sky hours in ``years`` Overview on-sky years (8,760 h each)."""
        return years * experiments.OVERVIEW_ONSKY_YEAR_HOURS

    def _edges(self) -> np.ndarray:
        zs, _ = experiments.chime2022_zbins()
        return zs

    def bins(self) -> tuple[Bin, ...]:
        """The redshift bins, with edges rounded as the tolerance table rounds them."""
        zs = self._edges()
        out = []
        for ib in range(len(zs) - 1):
            low = round(float(zs[ib]), BIN_EDGE_DECIMALS)
            high = round(float(zs[ib + 1]), BIN_EDGE_DECIMALS)
            out.append(Bin(index=ib, label=f"z {low!r}-{high!r}", low=low,
                           high=high))
        return tuple(out)

    def bins_for_band(self, low_mhz: float, high_mhz: float
                      ) -> tuple[tuple[int, ...], bool]:
        """The bins a band overlaps, and whether their union covers the band.

        The 21 cm redshift interval of the band runs from its upper edge to
        its lower edge. A bin counts when it overlaps that interval by any
        nonzero amount; a bin that is missing from the union refuses the band.
        """
        z_low, z_high = redshift_range(low_mhz, high_mhz)
        bins = self.bins()
        selected = tuple(sorted({b.index for b in bins
                                 if b.low < z_high and b.high > z_low}))
        covered_to = z_low
        for low, high in sorted({(b.low, b.high) for b in bins
                                 if b.index in selected}):
            if low > covered_to + COVERAGE_SLACK:
                break
            covered_to = max(covered_to, high)
        return selected, covered_to >= z_high - COVERAGE_SLACK

    def scenario(self, name: str) -> Scenario:
        for item in self.scenarios:
            if item.name == name:
                return item
        raise KeyError(f"the profile declares no scenario {name!r}")

    def load(self, scenario: str) -> None:
        """Load and authenticate the scenario's response bank."""
        self.bank(scenario)

    def bank(self, name: str):
        """The authenticated response bank of a scenario (loaded once)."""
        if name not in self._banks:
            known = filter_scenarios.scenario(self.scenario(name).name)
            bank = load_response_bank(
                self.response_banks_dir / known.bank,
                expected_kfg_fac=known.kfg_fac,
                expected_epsilon_fg=RESPONSE_EPSILON_FG, rf_dir=self.rf_dir)
            if not np.array_equal(bank.zs, self._edges()):
                raise ValueError(f"{known.bank}: redshift bins differ from the "
                                 f"{self.experiment} experiment")
            self._banks[name] = bank
        return self._banks[name]

    def response(self, scenario: str, bin_index: int, hours: float
                 ) -> tuple[dict[str, float], dict[str, float]]:
        """``(b, sigma)`` per parameter: the bias per unit residual and the error."""
        bank = self.bank(scenario)
        return bias_per_unit_residual(bank.F(bin_index, hours),
                                      list(bank.paramnames))

    def accept(self, scenario: str, bin_index: int, hours: float,
               parameter: str) -> tuple[float, int]:
        """``(drift, sign count)`` of sigma/|b| over hours * (1 -/+ fraction)."""
        bank = self.bank(scenario)
        return response_stability(bank, bin_index, hours,
                                  list(bank.paramnames), parameter,
                                  frac=self.time_fraction)

    def identity(self, *, responses: bool = True) -> dict:
        """Content digests of everything the responses depend on.

        Each bank's evaluation identity is taken without the commit and dirty
        flag of the RFIsher checkout, which change with every commit; its
        source digest stays in. With ``responses`` False no bank is opened,
        and each bank is identified by its bytes alone (None when missing).
        """
        here = Path(__file__).resolve().parent
        sources = {f"rfisher/forecast/radiofisher_bao/{name}":
                   _sha256_file(here / name) for name in SOURCES}
        banks = {}
        for item in self.scenarios:
            path = self.response_banks_dir / item.response_source
            entry = {"sha256": _sha256_file(path) if path.is_file() else None}
            if responses:
                evaluation = json.loads(json.dumps(
                    self.bank(item.name).evaluation_identity, sort_keys=True))
                for key in ("git_commit", "git_dirty"):
                    evaluation["baonoise"].pop(key, None)
                entry["evaluation_sha256"] = hashlib.sha256(json.dumps(
                    evaluation, sort_keys=True).encode("utf-8")).hexdigest()
            banks[item.response_source] = entry
        return {
            "sources": sources,
            "profile_sha256": _sha256_file(self.profile_path),
            "science_register_sha256": register_sha256(self.project),
            "bank_source_sha256": bank_source_state()["working_tree_sha256"],
            "banks": banks,
        }
