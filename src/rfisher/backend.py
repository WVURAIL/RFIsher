"""Locate, bind, and validate the supported RadioFisher backend."""
from __future__ import annotations

import os
import sys
from pathlib import Path

_DEFAULT_RF_CANDIDATES = (
    Path(__file__).resolve().parents[3] / "RadioFisher",   # sibling of project
    Path.home() / "work" / "RadioFisher",
    Path.cwd() / "RadioFisher",
)

SUPPORTED_BACKEND_API_VERSION = 1
DIRECT_MASK_CAPABILITIES = frozenset(
    {"noise_freq_weight", "noise_freq_mode", "vol_frac",
     "explicit_physical_densities", "astrophysical_model_profiles"})


def find_radiofisher_dir(explicit: str | os.PathLike | None = None) -> Path:
    """Locate a RadioFisher checkout (env RADIOFISHER_DIR overrides)."""
    if explicit is not None:
        candidate = Path(explicit).expanduser().resolve()
        if (candidate / "radiofisher" / "baofisher.py").is_file():
            return candidate
        raise FileNotFoundError(
            f"the requested RadioFisher checkout is invalid: {candidate}")
    if os.environ.get("RADIOFISHER_DIR"):
        candidate = Path(os.environ["RADIOFISHER_DIR"]).expanduser().resolve()
        if (candidate / "radiofisher" / "baofisher.py").is_file():
            return candidate
        raise FileNotFoundError(
            f"RADIOFISHER_DIR does not name a checkout: {candidate}")
    for candidate in _DEFAULT_RF_CANDIDATES:
        if (candidate / "radiofisher" / "baofisher.py").exists():
            return candidate.resolve()
    raise FileNotFoundError(
        "Could not find a RadioFisher checkout. Clone "
        "https://github.com/WVURAIL/RadioFisher and set RADIOFISHER_DIR."
    )


def _module_file(radiofisher) -> Path:
    module_file = getattr(radiofisher, "__file__", None)
    if not module_file:
        raise RuntimeError(
            "RadioFisher backend has no import path; pass the actual imported "
            "radiofisher package, not a proxy object")
    return Path(module_file).resolve()


def bind_radiofisher(radiofisher,
                     explicit: str | os.PathLike | None = None) -> Path:
    """Return the checkout backing ``radiofisher`` and reject mixed state."""
    requested_root = (find_radiofisher_dir(explicit)
                      if explicit is not None else None)
    module_file = _module_file(radiofisher)
    imported_root = module_file.parent.parent
    requested_root = requested_root or imported_root
    try:
        module_file.relative_to(requested_root)
    except ValueError as exc:
        raise RuntimeError(
            "RadioFisher checkout mismatch: requested configuration/data "
            f"from {requested_root}, but Python already imported code from "
            f"{imported_root}. Start a fresh process with one checkout or "
            "install a pinned backend package.") from exc
    if not (requested_root / "radiofisher" / "baofisher.py").is_file():
        raise RuntimeError(
            f"imported radiofisher does not belong to a complete checkout: "
            f"{requested_root}")
    return requested_root


def backend_capabilities(radiofisher) -> frozenset[str]:
    """Read and validate the explicit RadioFisher capability declaration."""
    if getattr(radiofisher, "BACKEND_ID", None) != "radiofisher":
        raise RuntimeError(
            "RadioFisher backend does not expose BACKEND_ID='radiofisher'; "
            "use the supported WVURAIL backend revision")
    api_version = getattr(radiofisher, "BACKEND_API_VERSION", None)
    if (isinstance(api_version, bool) or not isinstance(api_version, int)
            or api_version != SUPPORTED_BACKEND_API_VERSION):
        raise RuntimeError(
            "RadioFisher backend API does not match this RFIsher release; "
            f"BACKEND_API_VERSION must equal {SUPPORTED_BACKEND_API_VERSION}")
    getter = getattr(radiofisher, "get_backend_capabilities", None)
    if not callable(getter):
        raise RuntimeError(
            "RadioFisher backend has no get_backend_capabilities() contract")
    declared = getter()
    if not isinstance(declared, frozenset) \
            or not all(isinstance(item, str) for item in declared):
        raise RuntimeError(
            "RadioFisher get_backend_capabilities() must return frozenset[str]")
    return declared


def require_backend_capabilities(radiofisher, required, *, rf_dir=None) \
        -> frozenset[str]:
    """Fail closed unless the backend supports every required feature."""
    bound = bind_radiofisher(radiofisher, rf_dir)
    declared = backend_capabilities(radiofisher)
    missing = sorted(frozenset(required) - declared)
    if missing:
        raise RuntimeError(
            f"RadioFisher backend at {bound} lacks required capability(s): "
            + ", ".join(missing))
    return declared


def import_radiofisher(explicit: str | os.PathLike | None = None):
    """Import exactly one path-bound RadioFisher checkout per process."""
    os.environ.setdefault("MPLBACKEND", "Agg")
    rf_dir = find_radiofisher_dir(explicit)
    already = sys.modules.get("radiofisher")
    if already is not None:
        bind_radiofisher(already, rf_dir)
    if str(rf_dir) not in sys.path:
        sys.path.insert(0, str(rf_dir))
    import radiofisher  # noqa: PLC0415

    bind_radiofisher(radiofisher, rf_dir)
    return radiofisher, rf_dir
