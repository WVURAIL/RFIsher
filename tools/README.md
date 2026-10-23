# Development and validation tools

Run from the repository root with the package installed.

- `check_nonlinear_bias.py`: execute the finite-amplitude study specified by a protocol.
- `report_nonlinear_bias.py`: qualify and summarize its recorded fits.
- `generate_call_graph.py`: regenerate `docs/rfisher_functions.svg`.

The nonlinear tools require explicit study inputs; they are not prerequisites
for reading the shipped table. Preserve the original protocols and fit receipts.
See [the forecast contract](../docs/PAPER_CODE_MAP.md) for the numerical and
physical limits of these checks.
