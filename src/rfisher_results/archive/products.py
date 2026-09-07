"""Lazy access to one v5 per-pilot product, and the geometry every table needs.

A product is a compressed ``.npz`` of up to 1.5 GB; ``numpy.load`` opens it
without reading any member, and a member is decoded only when indexed. This
module keeps that laziness: ``Product`` holds the open archive and exposes
the small per-frame and per-unit fields as cached arrays, the exact-integer
residual view of :mod:`rfisher.pilotproxy`, the frame selection the health
gate leaves, and the channel geometry (nominal pilot position on the fine
axis and on the per-frame spectrum axis). The two large members,
``fine_power_u64`` and ``psd_frame_db_i16``, are never touched here; the
modules that need them read them in row chunks through ``fine_terms`` and
``psd_rows``.

Coordinates follow ``docs/archive-results-design.md`` section 2: every
frequency reported outward is the RF offset from the nominal pilot, positive
towards higher RF; the fine axis measures the carrier modulo ``f_s / K``
about the coarse grid, so the nominal pilot's fine bin (the grid residual)
is a channel constant computed here and used to convert fine offsets to RF.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Iterator

import numpy as np

from rfisher.pilotproxy import ResidualProductView, residual_product_view

SCHEMA_TOKEN = "pilotproxy_per_pilot_product_v5"
HEALTH_GATE_SCHEMA = "pilotproxy_archive_frame_health_gate_v1"

SAMPLE_RATE_HZ = 390625.0
NFFT = 16384
PSD_BIN_HZ = SAMPLE_RATE_HZ / NFFT                 # 23.84185791 Hz
DETECTOR_WINDOW = 128                              # K of the campaign
COARSE_BIN_HZ = SAMPLE_RATE_HZ / DETECTOR_WINDOW   # 3051.7578125 Hz
FINE_BINS = 256                                    # L_F = 2 N / K
FINE_BIN_HZ = COARSE_BIN_HZ / FINE_BINS            # 11.92092896 Hz
FRAME_SECONDS = NFFT * 2.56e-6                     # 41.94 ms
PSD_DB_INVALID = -32768

FINE_TARGET, FINE_REF_LOWER, FINE_REF_UPPER = 0, 1, 2


def sha256_of(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fine_power_ratio(terms: np.ndarray) -> np.ndarray:
    """``T[f] = 2 S_0[f] / (S_1[f] + S_2[f])`` from exact terms ``(n, 3, B)``.

    The deployed fine statistic, formed the way ``pilot_proxy.fine_reduction``
    forms it: a zero denominator gives 0.0. Returned as float64 ``(n, B)``.
    """
    terms = np.asarray(terms)
    if terms.ndim != 3 or terms.shape[1] != 3:
        raise ValueError(f"fine terms must have shape (n, 3, B); got {terms.shape}")
    s_t = terms[:, FINE_TARGET].astype(np.float64)
    den = terms[:, FINE_REF_LOWER].astype(np.float64) + terms[:, FINE_REF_UPPER].astype(np.float64)
    positive = den > 0.0
    return np.where(positive, 2.0 * s_t / np.where(positive, den, 1.0), 0.0)


def grid_residual_hz(pilot_hz: float, centre_hz: float, sense: int,
                     coarse_bin_hz: float = COARSE_BIN_HZ) -> float:
    """Where an exactly-nominal pilot appears on the fine axis, in Hz.

    The receiver-frame offset ``sense * (pilot - centre)`` reduced to the
    nearest coarse-grid frequency: the fine spectrum's origin is that grid
    point, so a nominal pilot sits at this residual, not at zero.
    """
    eff = float(np.sign(sense) or 1) * (float(pilot_hz) - float(centre_hz))
    return eff - round(eff / coarse_bin_hz) * coarse_bin_hz


def fine_bin_of_hz(offset_hz: float, fine_bins: int = FINE_BINS, fine_bin_hz: float = FINE_BIN_HZ) -> int:
    """Padded fine bin (0..L_F-1) of a fine-axis offset in Hz."""
    return int(round(offset_hz / fine_bin_hz)) % fine_bins


def fine_hz_of_bin(bin_index, fine_bins: int = FINE_BINS, fine_bin_hz: float = FINE_BIN_HZ):
    """Fine-axis offset in Hz of a padded bin, centred convention ((b + L/2) mod L) - L/2."""
    b = np.asarray(bin_index)
    return (((b + fine_bins // 2) % fine_bins) - fine_bins // 2) * fine_bin_hz


def fine_offset_to_rf_hz(fine_offset_hz, grid_residual: float, sense: int) -> np.ndarray:
    """RF offset from the nominal pilot of a fine-axis offset.

    The fine offset is unwrapped about the grid residual (so an anchor a few
    bins above the residual is a small positive shift even when the wrap
    puts it at the other end of the axis), then the receiver sense is
    undone: ``rf = sign(sense) * (fine - residual)`` with ``sign(-1) = -1``.
    """
    fine = np.asarray(fine_offset_hz, dtype=float)
    delta = fine - grid_residual
    delta = (delta + COARSE_BIN_HZ / 2.0) % COARSE_BIN_HZ - COARSE_BIN_HZ / 2.0
    return float(np.sign(sense) or 1) * delta


@dataclass(frozen=True)
class Geometry:
    """Channel constants: where the nominal pilot is on each axis."""

    physical_channel: int
    freq_id: int
    pilot_hz: float
    centre_hz: float
    sense: int
    grid_residual_hz: float          # fine-axis offset of the nominal pilot (fine-array direction)
    nominal_fine_bin: int            # its padded fine bin (what fine_designated_bins is centred on)
    nominal_psd_bin: float           # its (real-valued) receiver-frame bin on the per-frame spectrum axis
    centre_line_rf_offset_hz: float  # the instrumental channel-centre line, RF offset from nominal
    stored_window_centre: int        # centre of the product's fine_designated_bins (the scan's prediction)

    @property
    def matches_stored_window(self) -> bool:
        """Whether the scan's designated window was centred on the same nominal bin."""
        return self.stored_window_centre == self.nominal_fine_bin

    def psd_rf_offset_hz(self, bins) -> np.ndarray:
        """RF offset from the nominal pilot of per-frame spectrum bins (FFT order)."""
        b = np.asarray(bins, dtype=float)
        receiver = ((b + NFFT // 2) % NFFT - NFFT // 2) * PSD_BIN_HZ
        return float(np.sign(self.sense) or 1) * receiver + (self.centre_hz - self.pilot_hz)

    def psd_bin_of_rf_offset(self, rf_offset_hz) -> np.ndarray:
        """Receiver-frame bin (real-valued, FFT order) of an RF offset from the nominal pilot."""
        receiver = (np.asarray(rf_offset_hz, dtype=float) - (self.centre_hz - self.pilot_hz)) / float(np.sign(self.sense) or 1)
        return (receiver / PSD_BIN_HZ) % NFFT


class Product:
    """One open v5 product; nothing large is read until asked for."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._z = np.load(self.path, allow_pickle=False)
        token = str(np.asarray(self._z["schema_version"]).item()) if "schema_version" in self._z.files else ""
        if token != SCHEMA_TOKEN:
            raise ValueError(f"{self.path.name}: schema {token!r}, expected {SCHEMA_TOKEN!r}")

    # ------------------------------------------------------------ raw access
    @property
    def archive(self):
        return self._z

    def scalar(self, name: str):
        return np.asarray(self._z[name]).reshape(-1)[0] if np.asarray(self._z[name]).ndim else np.asarray(self._z[name]).item()

    def frame_column(self, name: str) -> np.ndarray:
        """A per-frame field, shaped (N,)."""
        arr = np.asarray(self._z[name])
        return arr[:, 0] if arr.ndim == 2 and arr.shape[1] == 1 else arr.reshape(arr.shape[0], -1)[:, 0] if arr.ndim == 2 else arr

    # -------------------------------------------------------- small fields
    @cached_property
    def view(self) -> ResidualProductView:
        """The exact-integer residual view (validates the v5 contracts)."""
        return residual_product_view(self._z)

    @cached_property
    def n_frames(self) -> int:
        return int(self.view.valid.size)

    @cached_property
    def valid(self) -> np.ndarray:
        return self.view.valid

    @cached_property
    def rejected(self) -> np.ndarray:
        """The stored survey flag ``F > mu_0`` (eta = 1), re-derived exactly by the view."""
        return self.view.rejected

    @cached_property
    def statistic(self) -> np.ndarray:
        """``Q = F / mu_0`` per frame (NaN where invalid)."""
        return self.view.statistic

    @cached_property
    def level_db(self) -> np.ndarray:
        """``10 log10(F / mu_0)`` per frame (NaN where invalid or nonpositive)."""
        q = self.statistic
        out = np.full(q.shape, np.nan)
        ok = np.isfinite(q) & (q > 0)
        out[ok] = 10.0 * np.log10(q[ok])
        return out

    @cached_property
    def shelf_db(self) -> np.ndarray:
        """Estimated data-shelf SNR (finite only where the normalized excess is positive)."""
        return self.view.shelf_db

    @cached_property
    def frame_unit_index(self) -> np.ndarray:
        return np.asarray(self.view.frame_unit_index, dtype=np.int64)

    @cached_property
    def frame_in_unit(self) -> np.ndarray:
        return np.asarray(self._z["frame_in_unit"], dtype=np.int64).reshape(-1)

    @cached_property
    def unit_time0(self) -> np.ndarray:
        """Unix UTC seconds of each acquisition unit's first sample."""
        return np.asarray(self.view.unit_time0_ctime, dtype=np.float64)

    @cached_property
    def unit_delta_time(self) -> np.ndarray:
        return np.asarray(self._z["unit_delta_time"], dtype=np.float64).reshape(-1)

    @cached_property
    def unit_event_id(self) -> np.ndarray:
        return np.asarray(self._z["unit_event_id"]).reshape(-1)

    @cached_property
    def unit_input_map_sha256(self) -> np.ndarray:
        return np.asarray(self._z["unit_input_map_sha256"]).reshape(-1)

    @cached_property
    def unit_git_version_tag(self) -> np.ndarray:
        return np.asarray(self._z["unit_git_version_tag"]).reshape(-1)

    @cached_property
    def frame_time(self) -> np.ndarray:
        """Unix UTC seconds of each frame's first sample.

        ``unit_time0 + frame_in_unit * nfft * unit_delta_time``; NaN where the
        unit's sample interval is unrecorded (1-2% of units), so calendar
        statistics must state that denominator.
        """
        t0 = self.unit_time0[self.frame_unit_index]
        dt = self.unit_delta_time[self.frame_unit_index]
        return t0 + self.frame_in_unit * NFFT * dt

    @cached_property
    def unit_time(self) -> np.ndarray:
        """Unit time of each frame (its acquisition's first sample), never NaN."""
        return self.unit_time0[self.frame_unit_index]

    @cached_property
    def mu0(self) -> float:
        return 2.0 * int(self.scalar("target_norm_sq")) / int(self.scalar("reference_norm_sum_sq"))

    @cached_property
    def fine_designated_bins(self) -> np.ndarray:
        """The scan-time predicted window (nominal bin +- 30); not a measured anchor."""
        return np.asarray(self._z["fine_designated_bins"], dtype=np.int64).reshape(-1)

    @cached_property
    def fine_census_excluded_bins(self) -> np.ndarray:
        return np.asarray(self._z["fine_census_excluded_bins"], dtype=np.int64).reshape(-1)

    @cached_property
    def fine_pad_factor(self) -> int:
        return int(self.scalar("fine_pad_factor"))

    @cached_property
    def fine_guard_bins(self) -> int:
        return int(self.scalar("fine_guard_fine_bins"))

    # ------------------------------------------------------------ geometry
    @cached_property
    def geometry(self) -> Geometry:
        pilot = float(self.scalar("pilot_frequency_hz"))
        centre = float(self.scalar("chime_frequency_hz"))
        sense = int(self.scalar("sense"))
        residual = grid_residual_hz(pilot, centre, sense)
        nominal_bin = fine_bin_of_hz(residual)
        designated = self.fine_designated_bins
        stored_centre = int(designated[len(designated) // 2]) if designated.size else -1
        return Geometry(
            physical_channel=int(self.view.physical_channel),
            freq_id=int(self.view.freq_id),
            pilot_hz=pilot, centre_hz=centre, sense=sense,
            grid_residual_hz=residual, nominal_fine_bin=nominal_bin,
            # receiver-frame frequency of the pilot is sense * (pilot - centre)
            nominal_psd_bin=float((float(np.sign(sense) or 1) * (pilot - centre) / PSD_BIN_HZ) % NFFT),
            centre_line_rf_offset_hz=centre - pilot,
            stored_window_centre=stored_centre,
        )

    # -------------------------------------------------------- frame gating
    @cached_property
    def health(self) -> "HealthGate":
        return health_gate(self)

    @cached_property
    def selected(self) -> np.ndarray:
        """Frames every downstream step may use: valid and passing the health gate."""
        return self.valid & self.health.include

    # ---------------------------------------------------------- big members
    def fine_terms(self, rows) -> np.ndarray:
        """Exact fine terms for the given frame rows, shaped (len(rows), 3, 256)."""
        return np.asarray(self._z["fine_power_u64"])[np.asarray(rows)]

    def fine_terms_all(self) -> np.ndarray:
        """The whole fine-terms member (about 240 MB per channel); prefer ``fine_terms``."""
        return np.asarray(self._z["fine_power_u64"])

    def psd_rows(self, chunk: int = 2048) -> Iterator[tuple[slice, np.ndarray]]:
        """Decoded per-frame spectra in row chunks: yields (row slice, linear power (n, 16384)).

        Decoding follows the product contract: ``psd_db_reference *
        10 ** (code / 1000)`` with NaN at the invalid code. The int16 member is
        read once in full (it is a compressed zip member and cannot be sliced
        on disk); the decode is chunked so the float64 copy never exceeds the
        chunk.
        """
        codes = np.asarray(self._z["psd_frame_db_i16"])
        reference = self.frame_column("psd_db_reference").astype(np.float64)
        invalid = int(self.scalar("psd_db_invalid_code"))
        n = codes.shape[0]
        for start in range(0, n, int(chunk)):
            stop = min(n, start + int(chunk))
            block = codes[start:stop]
            power = reference[start:stop, None] * np.power(10.0, block.astype(np.float64) / 1000.0)
            power[block == invalid] = np.nan
            yield slice(start, stop), power

    def close(self) -> None:
        self._z.close()

    def __enter__(self) -> "Product":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


@dataclass(frozen=True)
class HealthGate:
    """Which frames the frame-health gate admits, and which gate that was."""

    schema: str                  # HEALTH_GATE_SCHEMA, or 'valid_only' when pilot_proxy is absent
    include: np.ndarray          # bool (N,)
    reason_counts: dict[str, int]


def health_gate(product: Product) -> HealthGate:
    """Apply pilot-proxy's v1 frame-health gate when its package is importable.

    The gate excludes 192 of the campaign's 770,478 frames (saturated-ceiling
    and detector-invalid frames). Without ``pilot_proxy`` the selection is
    ``valid`` alone, and the ledger says so.
    """
    try:
        from pilot_proxy.archive_health import evaluate_frame_health  # type: ignore
    except ImportError:
        return HealthGate("valid_only", product.valid.copy(), {"detector_invalid": int((~product.valid).sum())})
    result = evaluate_frame_health(product.archive)
    include = np.asarray(result.include, dtype=bool)
    if include.shape != product.valid.shape:
        raise ValueError("health gate mask does not match the frame axis")
    return HealthGate(HEALTH_GATE_SCHEMA, include, {k: int(v) for k, v in dict(result.reason_counts).items()})


def open_products(directory: Path | str) -> list[Product]:
    """Every ``*.npz`` product under a directory, ordered by physical channel."""
    products = [Product(p) for p in sorted(Path(directory).glob("*.npz"))]
    return sorted(products, key=lambda p: p.view.physical_channel)
