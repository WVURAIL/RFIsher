"""Results from the archive campaign products.

The September 2026 CANFAR campaign products (``pilotproxy_per_pilot_product_v5``)
retain the exact integer powers the detector formed, so every number the
dissertation states about the archive -- eras, anchors, null calibration, the
selected rank and multiplier, masked fractions, residuals -- is recomputed
here from those terms. ``docs/archive-results-design.md`` is the design; each
module carries the definitions it implements in its docstring.

Modules are added in the order the design lists them: ``products`` (lazy
product access and geometry), ``blocks`` (calibration/evaluation split and
the acquisition block bootstrap), ``eras``, ``psd``, ``anchors``, ``nulls``,
``tolerances``, ``chain``, ``selection``, ``screening``, ``ledger``,
``numbers``, and ``run`` (the driver).
"""
