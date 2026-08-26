"""Validated residual coordinates for PilotProxy products."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from numbers import Real
from typing import Mapping

import numpy as np


PRODUCT_SCHEMA_NAME = "pilotproxy_per_pilot_product"
PRODUCT_SCHEMA_REVISION = 5
PRODUCT_SCHEMA_TOKEN = "pilotproxy_per_pilot_product_v5"
SOURCE_EVENT_KEY_SCHEMA = "pilotproxy_namespaced_source_event_key_v1"
FINE_BINS = 256

MASK_RULE = (
    "valid && (p_target * reference_norm_sum_sq > target_norm_sq * p_ref_sum)"
)
VALID_RULE = "p_ref_sum != 0"
FINE_MEASUREMENT_METHOD = "exact_fine_power_terms"


class PilotProxyContractError(ValueError):
    """Raised when a product cannot support the declared residual mapping."""


def _array(product: Mapping, name: str, dtype, shape) -> np.ndarray:
    if name not in product:
        raise PilotProxyContractError(f"product is missing {name!r}")
    values = np.asarray(product[name])
    expected = np.dtype(dtype)
    if values.dtype != expected or values.shape != shape:
        raise PilotProxyContractError(
            f"{name!r} must have dtype {expected} and shape {shape}; "
            f"got {values.dtype} and {values.shape}"
        )
    return values


def _string_scalar(product: Mapping, name: str) -> str:
    if name not in product:
        raise PilotProxyContractError(f"product is missing {name!r}")
    values = np.asarray(product[name])
    if values.shape != () or values.dtype.kind not in {"U", "S"}:
        raise PilotProxyContractError(f"{name!r} must be a string scalar")
    value = str(values.item())
    if not value:
        raise PilotProxyContractError(f"{name!r} must not be empty")
    return value


def _integer_scalar(product: Mapping, name: str, *, minimum=None) -> int:
    values = _array(product, name, np.int64, ())
    value = int(values.item())
    if minimum is not None and value < minimum:
        raise PilotProxyContractError(f"{name!r} must be at least {minimum}")
    return value


def _float_scalar(product: Mapping, name: str, *, positive=False) -> float:
    values = _array(product, name, np.float64, ())
    value = float(values.item())
    if not math.isfinite(value) or (positive and value <= 0.0):
        qualifier = "positive and finite" if positive else "finite"
        raise PilotProxyContractError(f"{name!r} must be {qualifier}")
    return value


def _json_scalar(product: Mapping, name: str) -> dict:
    raw = _string_scalar(product, name)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PilotProxyContractError(f"{name!r} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise PilotProxyContractError(f"{name!r} must contain an object")
    return value


def _same_float_array(name: str, stored: np.ndarray,
                      derived: np.ndarray) -> None:
    if not np.allclose(stored, derived, rtol=4e-13, atol=1e-12,
                       equal_nan=True):
        finite = np.isfinite(stored) & np.isfinite(derived)
        maximum = (float(np.max(np.abs(stored[finite] - derived[finite])))
                   if finite.any() else float("nan"))
        raise PilotProxyContractError(
            f"{name!r} disagrees with the exact power terms "
            f"(maximum absolute difference {maximum:g})"
        )


def _legacy_scalar(product: Mapping, name: str) -> float:
    if name not in product:
        raise PilotProxyContractError(f"legacy product is missing {name!r}")
    values = np.asarray(product[name]).reshape(-1)
    if values.size != 1:
        raise PilotProxyContractError(f"legacy field {name!r} must be scalar")
    value = float(values[0])
    if not math.isfinite(value):
        raise PilotProxyContractError(f"legacy field {name!r} must be finite")
    return value


@dataclass(frozen=True)
class ResidualProductView:
    """One residual coordinate system shared by current and legacy products."""

    schema: str
    physical_channel: int
    freq_id: int
    chime_frequency_hz: float
    valid: np.ndarray
    rejected: np.ndarray
    shelf_db: np.ndarray
    statistic: np.ndarray
    null_level: float
    shelf_offset_db: float
    frame_unit_index: np.ndarray
    unit_time0_ctime: np.ndarray
    normalized_excess: np.ndarray
    _p_target: np.ndarray | None = field(default=None, repr=False)
    _p_ref_sum: np.ndarray | None = field(default=None, repr=False)
    _target_norm_sq: int | None = field(default=None, repr=False)
    _reference_norm_sum_sq: int | None = field(default=None, repr=False)

    @property
    def is_current(self) -> bool:
        return self.schema == PRODUCT_SCHEMA_TOKEN

    def rejected_at_multiplier(self, eta: Real) -> np.ndarray:
        """Return the coarse decision at a positive threshold multiplier."""
        if isinstance(eta, bool) or not isinstance(eta, Real):
            raise TypeError("eta must be a number")
        value = float(eta)
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError("eta must be positive and finite")
        if not self.is_current:
            if (not math.isfinite(self.null_level)
                    or not np.isfinite(self.statistic).any()):
                raise PilotProxyContractError(
                    "legacy product lacks fstat_raw/mu0 for rethresholding"
                )
            return self.valid & (self.statistic > value * self.null_level)

        eta_num, eta_den = value.as_integer_ratio()
        target = self._p_target
        reference = self._p_ref_sum
        target_norm = int(self._target_norm_sq)
        reference_norm = int(self._reference_norm_sum_sq)
        decisions = np.fromiter(
            (
                bool(is_valid)
                and int(num) * reference_norm * eta_den
                > target_norm * int(den) * eta_num
                for num, den, is_valid in zip(target, reference, self.valid)
            ),
            dtype=bool,
            count=self.valid.size,
        )
        return decisions


def _current_view(product: Mapping) -> ResidualProductView:
    name = _string_scalar(product, "schema_name")
    revision = _integer_scalar(product, "schema_revision")
    token = _string_scalar(product, "schema_version")
    if (name != PRODUCT_SCHEMA_NAME or revision != PRODUCT_SCHEMA_REVISION
            or token != PRODUCT_SCHEMA_TOKEN):
        raise PilotProxyContractError(
            f"unsupported product schema {name!r} revision {revision} "
            f"token {token!r}"
        )
    if (_string_scalar(product, "source_event_key_schema_version")
            != SOURCE_EVENT_KEY_SCHEMA):
        raise PilotProxyContractError("source-event identity schema is unsupported")

    decision = _json_scalar(product, "decision_contract_json")
    active = decision.get("active_decision")
    fine = decision.get("fine_measurement")
    candidate = decision.get("fine_candidate_decision")
    if (not isinstance(active, dict)
            or active.get("method") != "coarse_normalized_positive_excess"
            or active.get("implementation") != "host_exact_integer_comparison"
            or active.get("output_field") != "reject_mask"):
        raise PilotProxyContractError("active decision contract is incompatible")
    if (not isinstance(fine, dict)
            or fine.get("method") != FINE_MEASUREMENT_METHOD
            or fine.get("role") != "measurement_only_no_scan_time_decision"
            or fine.get("terms_field") != "fine_power_u64"
            or not isinstance(candidate, dict)
            or candidate.get("method") != "fine_order_statistic_cfar"
            or candidate.get("active") is not False):
        raise PilotProxyContractError("fine measurement contract is incompatible")

    detector = _json_scalar(product, "detector_contract_json")
    if (detector.get("schema_version") != "pilotproxy_detector_contract_v1"
            or detector.get("num_weight_terms") != 3
            or detector.get("power_accumulator") != "uint64"
            or detector.get("power_accumulator_bits") != 64
            or detector.get("threshold_mode") != "none"
            or detector.get("per_frequency_threshold") is not False
            or detector.get("valid_rule") != VALID_RULE
            or detector.get("mask_rule") != MASK_RULE
            or detector.get("equivalent_mask_rule")
            != ("R_coarse > R_null; R_null = "
                "2*target_norm_sq/reference_norm_sum_sq")):
        raise PilotProxyContractError("detector contract is incompatible")
    if _string_scalar(product, "mask_rule") != MASK_RULE:
        raise PilotProxyContractError("product mask rule is incompatible")

    frame_index = np.asarray(product.get("frame_index"))
    if frame_index.dtype != np.dtype(np.int64) or frame_index.ndim != 1:
        raise PilotProxyContractError("'frame_index' must be a one-dimensional int64 array")
    frame_count = int(frame_index.size)
    if frame_count == 0 or not np.array_equal(
            frame_index, np.arange(frame_count, dtype=np.int64)):
        raise PilotProxyContractError("'frame_index' must be contiguous and zero-based")

    valid_u8 = _array(product, "valid", np.uint8, (frame_count, 1))
    rejected_u8 = _array(product, "reject_mask", np.uint8, (frame_count, 1))
    if np.any(valid_u8 > 1) or np.any(rejected_u8 > 1):
        raise PilotProxyContractError("valid and reject flags must be zero or one")
    valid = valid_u8[:, 0].astype(bool)
    rejected = rejected_u8[:, 0].astype(bool)

    p_target = _array(product, "p_target_u64", np.uint64,
                      (frame_count, 1))[:, 0]
    p_ref_sum = _array(product, "p_ref_sum_u64", np.uint64,
                       (frame_count, 1))[:, 0]
    p_ref_lower = _array(product, "p_ref_lower_u64", np.uint64,
                         (frame_count, 1))[:, 0]
    p_ref_upper = _array(product, "p_ref_upper_u64", np.uint64,
                         (frame_count, 1))[:, 0]
    for row, (lower, upper, total) in enumerate(
            zip(p_ref_lower, p_ref_upper, p_ref_sum)):
        if int(lower) + int(upper) != int(total):
            raise PilotProxyContractError(
                f"coarse reference terms disagree at frame {row}"
            )
    if not np.array_equal(valid, p_ref_sum != 0):
        raise PilotProxyContractError("valid flags disagree with p_ref_sum != 0")

    target_norm = int(_array(
        product, "target_norm_sq", np.int64, (1,))[0])
    reference_norm = int(_array(
        product, "reference_norm_sum_sq", np.int64, (1,))[0])
    if target_norm <= 0 or reference_norm <= 0:
        raise PilotProxyContractError("weight norms must be positive")
    exact_rejected = np.fromiter(
        (
            bool(is_valid)
            and int(num) * reference_norm > target_norm * int(den)
            for num, den, is_valid in zip(p_target, p_ref_sum, valid)
        ),
        dtype=bool,
        count=frame_count,
    )
    if not np.array_equal(rejected, exact_rejected):
        row = int(np.flatnonzero(rejected != exact_rejected)[0])
        raise PilotProxyContractError(
            f"reject_mask disagrees with the exact decision at frame {row}"
        )

    ratio = np.full(frame_count, np.nan, dtype=np.float64)
    np.divide(
        p_target.astype(np.float64) * float(reference_norm),
        p_ref_sum.astype(np.float64) * float(target_norm),
        out=ratio,
        where=p_ref_sum > 0,
    )
    excess = ratio - 1.0
    coarse = np.full(frame_count, np.nan, dtype=np.float64)
    np.divide(2.0 * p_target.astype(np.float64),
              p_ref_sum.astype(np.float64), out=coarse,
              where=p_ref_sum > 0)
    ratio_db = np.full(frame_count, np.nan, dtype=np.float64)
    ratio_db[ratio > 0.0] = 10.0 * np.log10(ratio[ratio > 0.0])
    excess_db = np.full(frame_count, np.nan, dtype=np.float64)
    excess_db[excess > 0.0] = 10.0 * np.log10(excess[excess > 0.0])

    pilot_below = _float_scalar(product, "pilot_below_data_db")
    bin_enbw = _float_scalar(product, "bin_enbw_hz", positive=True)
    dtv_bandwidth = _float_scalar(product, "dtv_bandwidth_hz", positive=True)
    efficiency = _float_scalar(
        product, "pilot_capture_efficiency", positive=True)
    if pilot_below < 0.0 or efficiency > 1.0:
        raise PilotProxyContractError("shelf calibration values are out of range")
    offset = (pilot_below - 10.0 * np.log10(dtv_bandwidth / bin_enbw)
              - 10.0 * np.log10(efficiency))
    shelf = excess_db + offset

    for field_name, derived in (
            ("coarse_power_ratio", coarse),
            ("normalized_coarse_power_ratio_db", ratio_db),
            ("normalized_pilot_excess", excess),
            ("pilot_excess_db", excess_db),
            ("estimated_data_shelf_snr_db", shelf)):
        stored = _array(product, field_name, np.float64,
                        (frame_count, 1))[:, 0]
        _same_float_array(field_name, stored, derived)

    if int(_array(product, "pilot_in_band", np.uint8, (1,))[0]) != 1:
        raise PilotProxyContractError("pilot is not in the measured band")
    frame_unit = _array(product, "frame_unit_index", np.int32,
                        (frame_count,))
    unit_time0 = np.asarray(product.get("unit_time0_ctime"))
    if unit_time0.dtype != np.dtype(np.float64) or unit_time0.ndim != 1 \
            or unit_time0.size == 0 or not np.isfinite(unit_time0).all():
        raise PilotProxyContractError(
            "'unit_time0_ctime' must be a finite float64 vector"
        )
    if np.any(frame_unit < 0) or np.any(frame_unit >= unit_time0.size):
        raise PilotProxyContractError("frame unit indices are out of range")

    physical_channel = int(_array(
        product, "physical_channel", np.int32, (1,))[0])
    freq_id = int(_array(product, "freq_id", np.int64, (1,))[0])
    chime_frequency = float(_array(
        product, "chime_frequency_hz", np.float64, (1,))[0])
    if not math.isfinite(chime_frequency) or chime_frequency <= 0.0:
        raise PilotProxyContractError("chime frequency must be positive and finite")

    return ResidualProductView(
        schema=PRODUCT_SCHEMA_TOKEN,
        physical_channel=physical_channel,
        freq_id=freq_id,
        chime_frequency_hz=chime_frequency,
        valid=valid,
        rejected=rejected,
        shelf_db=shelf,
        statistic=ratio,
        null_level=1.0,
        shelf_offset_db=float(offset),
        frame_unit_index=frame_unit,
        unit_time0_ctime=unit_time0,
        normalized_excess=excess,
        _p_target=p_target,
        _p_ref_sum=p_ref_sum,
        _target_norm_sq=target_norm,
        _reference_norm_sum_sq=reference_norm,
    )


def _legacy_view(product: Mapping) -> ResidualProductView:
    required = ("valid", "reject_mask", "snr_shelf_db",
                "physical_channel", "freq_id")
    missing = [name for name in required if name not in product]
    if missing:
        raise PilotProxyContractError(
            "product is neither current v5 nor a supported legacy product; "
            "missing " + ", ".join(missing)
        )
    valid_values = np.asarray(product["valid"])
    if valid_values.ndim != 2 or valid_values.shape[1] != 1:
        raise PilotProxyContractError("legacy valid array must have shape (N, 1)")
    frame_count = int(valid_values.shape[0])
    valid = valid_values[:, 0].astype(bool)
    rejected = np.asarray(product["reject_mask"])
    shelf = np.asarray(product["snr_shelf_db"])
    statistic = (np.asarray(product["fstat_raw"])
                 if "fstat_raw" in product else
                 np.full((frame_count, 1), np.nan, dtype=np.float64))
    for name, values in (("reject_mask", rejected),
                         ("snr_shelf_db", shelf),
                         ("fstat_raw", statistic)):
        if values.shape != (frame_count, 1):
            raise PilotProxyContractError(
                f"legacy {name} array must have shape ({frame_count}, 1)"
            )
    null_level = (_legacy_scalar(product, "mu0")
                  if "mu0" in product else float("nan"))
    calibration = ("pilot_below_data_db", "dtv_bandwidth_hz", "bin_enbw_hz")
    if all(name in product for name in calibration):
        pilot_below = _legacy_scalar(product, "pilot_below_data_db")
        bandwidth = _legacy_scalar(product, "dtv_bandwidth_hz")
        bin_enbw = _legacy_scalar(product, "bin_enbw_hz")
        if bandwidth <= 0.0 or bin_enbw <= 0.0:
            raise PilotProxyContractError("legacy bandwidths must be positive")
        offset = pilot_below - 10.0 * np.log10(bandwidth / bin_enbw)
    else:
        offset = float("nan")
    has_frame_unit = "frame_unit_index" in product
    has_unit_time = "unit_time0_ctime" in product
    if has_frame_unit != has_unit_time:
        raise PilotProxyContractError("legacy unit coordinates are incomplete")
    if has_frame_unit:
        frame_unit = np.asarray(product["frame_unit_index"])
        unit_time0 = np.asarray(product["unit_time0_ctime"])
        if frame_unit.shape != (frame_count,) or unit_time0.ndim != 1:
            raise PilotProxyContractError("legacy unit coordinates are malformed")
    else:
        frame_unit = np.empty(0, dtype=np.int32)
        unit_time0 = np.empty(0, dtype=np.float64)
    return ResidualProductView(
        schema="legacy",
        physical_channel=int(np.asarray(product["physical_channel"]).reshape(-1)[0]),
        freq_id=int(np.asarray(product["freq_id"]).reshape(-1)[0]),
        chime_frequency_hz=(
            float(np.asarray(product["chime_frequency_hz"]).reshape(-1)[0])
            if "chime_frequency_hz" in product else float("nan")),
        valid=valid,
        rejected=rejected[:, 0].astype(bool),
        shelf_db=shelf[:, 0].astype(np.float64, copy=False),
        statistic=statistic[:, 0].astype(np.float64, copy=False),
        null_level=float(null_level),
        shelf_offset_db=float(offset),
        frame_unit_index=frame_unit,
        unit_time0_ctime=unit_time0,
        normalized_excess=statistic[:, 0].astype(np.float64, copy=False) - 1.0,
    )


def residual_product_view(product: Mapping) -> ResidualProductView:
    """Validate a product and expose its residual decision coordinates."""
    token = None
    revision = None
    if "schema_version" in product:
        values = np.asarray(product["schema_version"])
        if values.shape == () and values.dtype.kind in {"U", "S"}:
            token = str(values.item())
    if "schema_revision" in product:
        values = np.asarray(product["schema_revision"])
        if values.shape == () and np.issubdtype(values.dtype, np.integer):
            revision = int(values.item())
    if token == PRODUCT_SCHEMA_TOKEN or revision == PRODUCT_SCHEMA_REVISION:
        return _current_view(product)
    return _legacy_view(product)


def is_current_product(product: Mapping) -> bool:
    """Return whether a product declares the current v5 schema."""
    if "schema_version" not in product:
        return False
    values = np.asarray(product["schema_version"])
    return bool(values.shape == () and values.dtype.kind in {"U", "S"}
                and str(values.item()) == PRODUCT_SCHEMA_TOKEN)


def coarse_reject_mask(product: Mapping, eta: Real = 1.0) -> np.ndarray:
    """Return a rethresholded coarse mask in the product's own coordinates."""
    revision = np.asarray(product.get("schema_revision"))
    declares_revision_five = bool(
        revision.shape == ()
        and np.issubdtype(revision.dtype, np.integer)
        and int(revision.item()) == PRODUCT_SCHEMA_REVISION
    )
    if is_current_product(product) or declares_revision_five:
        return _current_view(product).rejected_at_multiplier(eta)
    if "fstat_raw" not in product or "mu0" not in product:
        raise PilotProxyContractError(
            "legacy product lacks fstat_raw/mu0 for rethresholding"
        )
    statistic = np.asarray(product["fstat_raw"])
    if statistic.ndim == 2 and statistic.shape[1] == 1:
        statistic = statistic[:, 0]
    elif statistic.ndim != 1:
        raise PilotProxyContractError(
            "legacy fstat_raw must have shape (N,) or (N, 1)"
        )
    null = _legacy_scalar(product, "mu0")
    if isinstance(eta, bool) or not isinstance(eta, Real):
        raise TypeError("eta must be a number")
    value = float(eta)
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError("eta must be positive and finite")
    return statistic > value * null


__all__ = [
    "PRODUCT_SCHEMA_NAME", "PRODUCT_SCHEMA_REVISION", "PRODUCT_SCHEMA_TOKEN",
    "SOURCE_EVENT_KEY_SCHEMA", "FINE_BINS", "MASK_RULE", "VALID_RULE",
    "FINE_MEASUREMENT_METHOD", "PilotProxyContractError",
    "ResidualProductView", "residual_product_view", "is_current_product",
    "coarse_reject_mask",
]
