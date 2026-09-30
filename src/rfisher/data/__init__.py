"""Versioned runtime data distributed with RFIsher.

Keeping the files in a package makes the same data available from a source
checkout, wheel, or sdist without relying on the current working directory or
a repository layout. :func:`rfisher.forecast.radiofisher_bao.bank.resources.data_file`
locates any of them, and each file is read by the module that owns it:

- the Fisher banks, the P(k) caches and the synthetic n(x) baseline by
  :mod:`rfisher.forecast.radiofisher_bao.bank`;
- ``response_banks/`` and ``tolerances/`` by
  :mod:`rfisher.forecast.radiofisher_bao.response` and
  :mod:`rfisher.forecast.radiofisher_bao.model`, and the two frozen
  reference tolerances in ``tolerances/`` by :mod:`rfisher.tolerance.reference`;
- ``schemas/``, the detector handoff schema, vendored byte for byte;
- the Fig. 10 filter residual by
  :mod:`rfisher.forecast.radiofisher_bao.filter_scenarios`;
- ``products.json`` by :mod:`rfisher.products`, and the survey rates by
  :mod:`rfisher.channels`.

Only the first group is bank data.
"""
