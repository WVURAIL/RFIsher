# capture_ruling_a19_2026-09-25_r5_2: changes from capture_ruling_a19_2026-09-25_r5_1

Revision 5.2 applies DECISIONS.md item 41: the ground-credit sensitivity reading takes the settled form from B-1, (1 − γ), in place of (1 − γ²). The spec is DECISIONS.md (sha in MANIFEST.json), unchanged. No rule, gate, bar or disposition of the ruling changes (item 37). The ruling takes no credit (item 17), so the change reaches only the credit readings, the labels built on them, and the printed coherence and rescue columns.

`build_release.py --r52` builds this release. With the r5.1 credit values, `build_release.py --r52 --credit-form one_minus_gamma_sq --credit-gamma released --rel <scratch> --run <scratch> --tables-only` (or `--r51`) rebuilds r5.1 byte for byte: all 48 files, including `promotion_least_corners.csv` and `PROMOTION_EVIDENCE.md` (tests/test_a18.py `test_reproduces_r51`). The following stay frozen:
- r5.1, r5 and the earlier releases;
- the table of record (9867551a);
- the FA tree.

## 1. Switches

Two named switches in `ruling_a18.py`. `--a18` and `--r51` keep the r5.1 values, which write no key to the json, and `--r52` sets the r5.2 values.

| Switch | r5.1 | r5.2 | Source |
|---|---|---|---|
| `CREDIT_FORM` | one_minus_gamma_sq | one_minus_gamma | item 41, B-1 section 2 |
| `CREDIT_GAMMA` | released | reconciled | B-1 section 3 |

- **The form.** A per-day ground filter leaves f = 1 − \|E V\|² / E\|V\|². The capture γ is a pair statistic, E cos(φ_a − φ_b). For constant amplitude f = 1 − γ exactly, and amplitude fluctuations only raise f, so (1 − γ) is the most generous credit the measured γ allows (B-1, `b1_results.json`, `form`).
- **The range γ.** B-1's reconciled definition is the median over the range's measured (gain) classes, the classes whose residual G prices, clamped to [0, 0.95]. Where no class is measured it is the all-class median, as released. It equals B-1's `steady_share_ranges.csv` on all 44 ranges it lists. It moves three ranges:
  - 15 long: 0.144 to 0.226 (ew3 is the only measured class);
  - 26 short: 0.856 to 0.95 (ns32 alone, 0.976 before the clamp);
  - 27 short: 0.808 to 0.93 (ns32 alone).
- **Channel 24** has no measured coherence, so its credit readings take the ceiling in the settled form, (1 − 0.95): 13.01 dB in place of 10.11 dB.
- **The rescue coherence** (the coherence a ground filter would need, with no credit taken) is read in the same form: 1 − c in place of √(1 − c), with c the reduction the bar needs.
- The other scripts take one flag each: `ch24_2020_basis_a18.py --credit-form one_minus_gamma` and `postprocessing_sensitivity_a18.py --credit-form one_minus_gamma`.

B-2's grid already used this credit. Its capture cells (rule, Stokes I, cos dec 0.7, released λ_dep) equal this release's r3 and r2 bars on every BAO range with a bar (`test_r52_credit`).

## 2. What does not move

- **Dispositions.** Excised: 14, 15, 17, 24, 26, 27, 30, 31, 33 and 35. Kept: none. Undetermined: 22 and every other channel.
- **Every no-credit number.** Each R, bar, G, verdict, threshold and disposition of the ruling equals r5.1's. `dispositions_a18.csv`, `thresholds_a18.csv`, `ch24_basis_a18.txt`, `run/ch24_a18.json`, `tau_lower_bounds_a19.csv`, `keep_gap_a18.csv`, `duration_nofilter.csv` and the phase limit are byte-identical to r5.1.
- **The promotion set.** Item 18 as coded, and under B-2's admissible grid: 17, 24, 30, 31, 33 and 35. B-2's least corners are unchanged.

## 3. The label: channel 26 becomes idealized-only

| Reading, 26 short | r5.1 | r5.2 |
|---|---|---|
| No credit (the ruling) | +22.05 dB, excise | +22.05 dB, excise |
| Ground credit | 5.72 dB | 13.01 dB |
| r3, ground credit | +16.33 dB, excise | +9.04 dB, excise |
| r2, 200 ns filter plus S and the ground credit | +7.76 dB, excise | **+0.48 dB, inside the allowance** |
| Label | robust to post-processing | **idealized-only**, removed by the 200 ns filter plus S |

- It takes both parts of the settled credit. The form alone, at the released γ, reads +5.08 dB in r2. The reconciled γ alone, in the old form, reads +3.38 dB. Both are still excised. B-3's `ch26_label.csv` has the same credit (13.0103 dB at γ 0.95).
- **Idealized-only:** 26 and 27, each removed by the 200 ns filter plus S.
- **Robust to post-processing:** 14, 15, 17, 24, 30, 31, 33 and 35.

## 4. The credit readings

Deciding bars, dB over tolerance:

| Ch | r3, r5.1 | r3, r5.2 | r2, r5.1 | r2, r5.2 | Label |
|---|---|---|---|---|---|
| 14 | +14.11 | +12.76 | +13.41 | +12.05 | robust |
| 15 | +10.84 | +9.82 | +10.14 | +9.11 | robust |
| 17 | +61.79 | +59.53 | +49.01 | +46.76 | robust |
| 24 | +28.67 | +25.77 | +20.11 | +17.21 | robust |
| 26 | +16.33 | +9.04 | +7.76 | +0.48 | **idealized-only** |
| 27 | +12.43 | +5.47 | −1.60 | −8.56 | idealized-only |
| 30 | +45.10 | +42.91 | +36.66 | +34.47 | robust |
| 31 | +50.63 | +47.98 | +42.19 | +39.54 | robust |
| 33 | +32.66 | +30.10 | +24.22 | +21.66 | robust |
| 35 | +45.60 | +43.06 | +41.64 | +39.11 | robust |

- The ground credit on the BAO ranges is now 0.07 to 13.01 dB, where r5.1 had 0.00 to 10.11 dB (`postprocessing_sensitivity.csv`, `ground_credit_*_db`).
- In the credit readings' thresholds, 14, 15, 26 and 27 move. In r2, 26 is now undetermined, and 27 needs τ > 6.30 s (was 1.27 s).
- **Channel 24, per in-band bin** (`ch24_per_bin_a19.csv`): every both-credits bar falls by 2.90 dB, the change of the ceiling. On the long range, 15 of 16 bins are over the allowance with both credits (r5.1: 16 of 16). Bin 676, the upper edge, reads +1.54 dB. Every no-credit column is unchanged.

## 5. Printed coherence and rescue columns

These are texts, not readings.
- `a18_<range>_rho` in `table_of_record_a18.csv`, `<range>_rho` in `run/*_full.csv` and `rho_ew` in `robustness_a18.csv` carry the reconciled γ on 15 long, 26 short and 27 short.
- The rescue coherence is read in the settled form: `a18_<range>_rescue_rho` (611 values) and the "rescued only by a ground filter reaching coherence ..." clause of the verdict texts (86 reasons in `table_of_record_a18.csv`). For example, 26 short now reads 0.9876 against the measured 0.95, where r5.1 read 0.9938 against 0.86.

## 6. PROMOTION_EVIDENCE.md

- The title, the label of 26, and the r3 and r2 bars of every channel follow the settled credit.
- Channel 24's line now cites the author's ruling (item 39) in place of "an author ruling ... which this release does not make".
- **B-7's both-credit margins** move dB for dB with the r2 bar, so each is shifted by the r2 bar's change from r5.1:

| Ch | r5.1 harmonic / inverse-variance | r5.2 | Verdict |
|---|---|---|---|
| 17 | +41.0 / +37.3 | +39.3 / +35.7 | fails both |
| 24 | +7.3 / +4.1 | +4.4 / +1.2 | fails both |
| 30 | +34.4 / +30.9 | +33.4 / +29.9 | fails both |
| 31 | +29.2 / +25.9 | +26.5 / +23.3 | fails both |
| 33 | +11.2 / +8.0 | +8.6 / +5.4 | fails both |
| 35 | +31.1 / +27.8 | +28.9 / +25.6 | fails both |
| 14 | −0.7 / −4.1 | −2.1 / −5.4 | passes both |
| 15 | −4.0 / −7.4 | −5.0 / −8.4 | passes both |
| 26 | −4.3 / −7.8 | −11.6 / −15.1 | passes both |
| 27 | −7.5 / −10.7 | −14.4 / −17.6 | passes both |

No verdict changes. Channel 24's inverse-variance margin, +1.2 dB, is now the smallest of the six.

## 7. Tests

`tests/test_a18.py` on this release. New:
- `test_reproduces_r51`: r5.1 byte for byte, as above.
- `test_r52_credit`:
  - the reconciled γ against B-1;
  - each r3 exclusion reading equals the no-credit one times (1 − γ);
  - each r2 reading equals r5.1's r2 times (1 − γ_rec) / (1 − γ_rel²);
  - channel 24 at (1 − 0.95);
  - B-2's capture cells and B-3's channel 26 row;
  - that the no-credit ruling equals r5.1's, and that only 26's label moves;
  - the per-bin shift;
  - the form-only side reading.

The r5.1 tests run on r5.2 with the settled form where a credit is read. The r5, r4, r3 and r2 reproductions still pass.
