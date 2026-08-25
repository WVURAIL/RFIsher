"""Compatibility import path for RFIsher 1.x users."""
from __future__ import annotations

from importlib import import_module
import sys

from rfisher import __all__, __version__


_SUBMODULES = (
    "_validation",
    "api",
    "channels",
    "cli",
    "compat",
    "constants",
    "cosmologies",
    "data",
    "fisherbank",
    "forecast",
    "incumbent",
    "layout",
    "npzio",
    "pkcache",
    "plots",
    "products",
    "residual",
    "residual_templates",
    "resources",
    "scenarios",
    "survey",
    "tolerances",
)

for _name in _SUBMODULES:
    _module = import_module(f"rfisher.{_name}")
    sys.modules[f"{__name__}.{_name}"] = _module
    if not _name.startswith("_"):
        globals()[_name] = _module

del _module, _name
