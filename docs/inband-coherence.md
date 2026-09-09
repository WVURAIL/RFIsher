# In-band voltage coherence development prototype

The September 9 prototype is complete for development event 1153713684:
15 adjacent coarse bins, 32 fixed input columns, 496 pairs and 114,964 shared
samples (0.29430784 s). Exact selected native bytes, complex cross-products,
pair-matched powers/means/counts, block variation and code/rail diagnostics
are saved in `../results/inband_coherence_2026-09-09/` in the parent workspace.
See that release's README, frozen plan, independent recount and two-page PDF.

The helper `rfisher_results.validation.voltage_coherence` and scripts
`measure_inband_coherence_v1.py` / `plot_inband_coherence_v1.py` provide the
reproducible CPU-only path. 26 independent unit tests pass; an independent
integer recount matches every saved complex sum exactly.

Within each coarse bin, the median pair amplitude coherency is 0.0026–0.0029;
the maximum is 0.129–0.161. There are no 0x00 codes in the selected bytes, so
all-stored and 0x00-excluded calculations coincide. Packet validity, physical
baselines, gains, delays and noise calibration remain unavailable. Results
are raw digital voltage moments, not measured DTV residual fractions or the
actual cleaner's response. The frequency coverage is partial, and this
already-used event supplies no independent physical validation.

The exploratory extraction/moment step is complete; the full physical
calibration requirements in [physical-calibration.md](physical-calibration.md)
remain open. No forecast credit, channel acceptance or floor replacement is
enabled. The running fine-detector campaign and its frozen inputs are unchanged.
