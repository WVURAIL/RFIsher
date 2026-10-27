# Development and validation tools

The tools are run from the repository root with the package installed.

| Tool | Purpose |
|---|---|
| `check_nonlinear_bias.py` | runs the finite-amplitude study that a protocol specifies |
| `report_nonlinear_bias.py` | qualifies and summarizes the recorded fits of that study |
| `generate_call_graph.py` | regenerates `docs/rfisher_functions.svg` |

The nonlinear tools need explicit study inputs, and the shipped table can be read
without them. The original protocols and fit receipts are kept unchanged. The
numerical and physical limits of these checks are given in
[the paper/code contract](../docs/PAPER_CODE_MAP.md).
