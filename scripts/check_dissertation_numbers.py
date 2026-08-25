#!/usr/bin/env python3
"""Dissertation number gate: every load-bearing number in the dissertation
must match its machine-readable source, and known-stale values must be gone.

The sibling `check_paper_numbers.py` guards the paper against `out/*.csv`;
this script does the same for the dissertation, whose LaTeX lives outside the
repository (Overleaf). Point it at the source:

    # Overleaf has a git bridge (Menu -> Git), so a local clone works:
    #   git clone https://git.overleaf.com/<project-id> dissertation-tex
    python3 scripts/check_dissertation_numbers.py \
        --tex ../dissertation-tex \
        --summary-json ../pilot-proxy/data/provenance/dissertation_summary_v2.json

`--tex` accepts .tex files, directories (searched recursively for *.tex), or a
plain-text export (e.g. pdftotext output) -- table layout can scramble in text
extraction, so .tex is authoritative and extraction runs are advisory.

Three check kinds, all on a normalized text (unicode dashes -> '-',
multiplication sign -> 'x', digit-group commas removed, TeX comments stripped):

  REQUIRE      a value or phrase that must appear (source-of-truth quotes,
               evidence anchors that are still to be added);
  FORBID       a known-stale literal that must be gone;
  FORBID-PAIR  two numbers that cannot both be right; fails only while both
               are present, so fixing either side clears it.

CSV-driven checks recompute their needles from the shipped out/ artifacts
(`optimal_thresholds.csv`, `fine_operating_points.csv`, and the forecast
headline tables: `fig31_validation.csv`, `required_times.csv`,
`bin_level_targets.csv`, `forecast_completion_all_dtv_bins.json`,
`forecast_completion_template_comparison.csv`, `three_worlds.csv`) at the
dissertation's rounding, so a forecast rerun moves the expectation
automatically. Current-era checks read
`scripts/dissertation/data/bao_era_points.csv`. JSON checks read the
pilot-proxy snapshot (`--summary-json`); they SKIP when it is not supplied.

Exit status 0 = all checks pass; 1 = at least one FAIL. A red run is the
to-do list: each FAIL line says what to change and where the truth lives.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
FIGURE_DATA = ROOT / "scripts" / "dissertation" / "data"
ERA_PRODUCT_PINS = {
    32: ("568.npz",
         "99ad816a828ea8c29e7e5551a34cda7413a95b25afc7d42d0a3ed9d078e0d4da"),
    35: ("521.npz",
         "9f3e63e5ad81ba39d085abe5f725cc5c53d9d7a175724158c6d84230f7e1a38f"),
}
ERA_SOURCE_PIN = (
    "40082de9cc973858151c94aee0ca5cd44e55309343f7f7f91d8cd38fa0b18ea9")
ERA_PRODUCT_SCHEMA = "pilotproxy_detector_datatrawl_v3"
ERA_VALUE_PINS = {
    32: {
        "era": "2023-02..2026-07",
        "masked_fraction": "0.7056423174",
        "best_cost_masked_fraction": "0.05602015113",
        "tau_seconds": "300",
        "tau_quality": "bounded_above",
        "floor_era": "2023-02..2026-07",
        "floor_frames": "14527",
        "floor_db": "-31.53203804",
        "r_tol_dilation": "0.0156",
        "r_eta1_adopted": "0.1672010173",
        "r_cost_adopted": "0.07569214993",
    },
    35: {
        "era": "2021-11..2026-07",
        "masked_fraction": "0.4805376645",
        "best_cost_masked_fraction": "0.01351162139",
        "tau_seconds": "2767.651212",
        "tau_quality": "measured",
        "floor_era": "2018-12..2021-10",
        "floor_frames": "3359",
        "floor_db": "-24.98298361",
        "r_tol_dilation": "0.0352",
        "r_eta1_adopted": "4.198385861",
        "r_cost_adopted": "4.734007338",
    },
}
WORLD_BANK_PINS = {
    "none": ("fisher_bank_chime2022_pres_dense.npz",
             "2b613cff3aea772751c00907fd2927507a9269553cdce9456d965e02d0719020",
             None),
    "peak1": ("fisher_bank_chime2022_pres_kfg22_dense.npz",
              "c289e8cdce00f3ee1f8e832c599aa2ddbc75c43d9fcadf66df0bd70202112e35",
              22.0),
    "peak2": ("fisher_bank_chime2022_pres_kfg44_dense.npz",
              "1e7cecb61371c280d582f864d55aeba9cc21f48c1a298b1665ba0448cfb78aa0",
              44.0),
    "deployed": ("fisher_bank_chime2022_pres_kfg80_dense.npz",
                  "e9ce345c500481e3ba6e0f4409cfd120ff2a83bb6ac42cd7ec64f0047095db73",
                  80.0),
}
WORLD_PRODUCT_PINS = {
    29: ("614.npz",
         "c8b13fcd8ea23b9a384ce71e11f05fed3d9d3fc0f9cbd472f77012233c52502c"),
    32: ERA_PRODUCT_PINS[32],
    33: ("552.npz",
         "5bc12254565cc414e6e72d7e3217c8d51c4f9bc92f41b62d2be59037abd86c83"),
    35: ERA_PRODUCT_PINS[35],
}
WORLD_SOURCE_COMMIT = "70be39cb73bd576da7d17f40a671b6c12e22a147"
WORLD_SOURCE_SHA256 = (
    "9461797acf3f1be1394bb514f98dc717aaa09ccc37313a195c63f2bc1b4ec389")
WORLD_BACKEND_COMMIT = "f6bc9ea0972028ce30472dd21b25d4b21b7068c0"
WORLD_BACKEND_SHA256 = (
    "efad0173be49d51679cf98071ccd1dfccd386dc9b2774e202164086347a4c2cf")
WORLD_SUPPRESSION_DB = {
    "none": 0.0, "peak1": 3.6, "peak2": 8.2, "deployed": 11.4,
}
WORLD_ROWS_SHA256 = (
    "d0d6aa799ffe6163757347c6d97dd9e9d7215d48e68b45c8bf03939ecaf0b2c9")


# ---------------------------------------------------------------- normalize
_DASHES = dict.fromkeys(map(ord, "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"),
                        "-")
_QUOTES = {0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"'}
_SPACES = dict.fromkeys(map(ord, "\u00a0\u2009\u202f\u2005\u2006"), " ")
_MULT = {0x00d7: "x", 0x2248: "~", 0x223c: "~"}


def normalize(text: str, *, tex: bool = False) -> str:
    """One matching surface for .tex and extracted text.

    Unicode dashes/minus -> '-', multiplication sign -> 'x', approx signs ->
    '~', curly quotes straightened, hard/thin spaces -> ' ', digit-group
    commas removed (1,566 -> 1566), TeX comments stripped when ``tex=True``,
    whitespace collapsed. Case is preserved.
    """
    s = text.translate({**_DASHES, **_QUOTES, **_SPACES, **_MULT})
    if tex:
        s = re.sub(r"(?<!\\)%.*", "", s)          # comments, not literal \%
        s = (s.replace("\\%", "%")
              .replace("\\times", "x")            # $1.4\times$ -> 1.4x
              .replace("{,}", ",")                # 1{,}566 -> 1,566 -> 1566
              .replace("---", "-")                # TeX em dash
              .replace("--", "-")                 # TeX en dash: 3.2--7.8
              .replace("\\,", "")                 # 1\,566 -> 1566
              .replace("~", " ")
              .replace("$", ""))                  # math delimiters
    s = re.sub(r"(?<=\d),(?=\d)", "", s)
    return re.sub(r"\s+", " ", s)


def load_tex(paths: list[str]) -> tuple[str, list[Path]]:
    files: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            # Archived papers under evidence/legacy_projects keep their own
            # historical prose; this gate does not govern them, and sweeping
            # them trips FORBID checks on text that is deliberately frozen.
            found = sorted(f for f in p.rglob("*.tex")
                           if "legacy_projects" not in f.parts)
            if not found:
                sys.exit(f"error: no .tex files under {p}")
            files.extend(found)
        elif p.is_file():
            files.append(p)
        else:
            sys.exit(f"error: --tex path not found: {p}")
    body = "".join(
        normalize(f.read_text(encoding="utf-8", errors="replace"),
                  tex=f.suffix == ".tex")
        for f in files)
    return body, files


# ---------------------------------------------------------------- checker
class Checker:
    """`text` is the dissertation source; `extra` is an optional secondary
    surface (frozen figure data, evidence exports) that only checks with
    ``wide=True`` consult -- numbers rendered inside figures live there."""

    def __init__(self, text: str, extra: str = ""):
        self.text = text
        self.wide = text + " " + extra
        self.n = 0
        self.failures = 0
        self._section = None

    def _emit(self, status: str, label: str, msg: str) -> None:
        self.n += 1
        if status == "FAIL":
            self.failures += 1
        tail = f"  [{msg}]" if (msg and status != "PASS") else ""
        print(f"{status:4s}  {label:62s}{tail}")

    def section(self, title: str) -> None:
        if title != self._section:
            print(f"\n-- {title} --")
            self._section = title

    def require(self, label: str, pattern: str, msg: str,
                wide: bool = False) -> None:
        ok = re.search(pattern, self.wide if wide else self.text) is not None
        self._emit("PASS" if ok else "FAIL", label,
                   f"missing; {msg}" if not ok else msg)

    def value(self, label: str, needles: list[str], msg: str,
              wide: bool = False) -> None:
        """Any one of several plain-substring renderings must appear."""
        hay = self.wide if wide else self.text
        ok = any(n in hay for n in needles)
        self._emit("PASS" if ok else "FAIL", label,
                   "" if ok else f"none of {needles} found; {msg}")

    def forbid(self, label: str, pattern: str, msg: str) -> None:
        hit = re.search(pattern, self.text)
        self._emit("PASS" if hit is None else "FAIL", label,
                   "" if hit is None else f"stale '{hit.group(0)}'; {msg}")

    def forbid_pair(self, label: str, pat_a: str, pat_b: str,
                    msg: str) -> None:
        both = (re.search(pat_a, self.text) is not None
                and re.search(pat_b, self.text) is not None)
        self._emit("FAIL" if both else "PASS", label,
                   f"both present, at most one can be right; {msg}"
                   if both else "")

    def skip(self, label: str, msg: str) -> None:
        self._emit("SKIP", label, msg)


# ---------------------------------------------------------------- sources
def read_csv(name: str) -> list[dict]:
    with open(OUT / name, newline="") as fh:
        return list(csv.DictReader(fh))


def path_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def threshold_rows() -> dict[int, dict]:
    """Operating rows of out/optimal_thresholds.csv.

    The dissertation's Table 9.4 quotes the *product-basis* operating points;
    the sigma_null rows differ in margin/penalty for the same eta.
    """
    rows = {}
    for r in read_csv("optimal_thresholds.csv"):
        if r.get("eta") and r.get("basis") == "product":
            rows[int(r["ch"])] = r
    return rows


def fine_rows() -> dict[int, dict]:
    """Product-basis operating rows of out/fine_operating_points.csv.

    Only era-certified rows bind the dissertation: the script records
    archive-only pairs (era_stable False) for the era-mixture demonstration,
    and those are not operating points the text is required to quote.
    """
    rows = {}
    for r in read_csv("fine_operating_points.csv"):
        if (r.get("multiplier_q16") and r.get("basis") == "product"
                and r.get("era_stable") == "True"):
            rows[int(r["ch"])] = r
    return rows


WORLD_ORDER = ("none", "peak1", "peak2", "deployed")


def worlds_rows() -> dict[tuple[str, int], dict]:
    raw = read_csv("three_worlds.csv")
    rows = {(row["world"], int(row["ch"])): row for row in raw}
    if len(rows) != len(raw):
        raise ValueError("duplicate row in three_worlds.csv")
    return rows


def era_rows() -> dict[int, dict]:
    with (FIGURE_DATA / "bao_era_points.csv").open(
            newline="", encoding="utf-8") as stream:
        raw = list(csv.DictReader(stream))
    rows = {int(row["channel"]): row for row in raw}
    if len(rows) != len(raw):
        raise ValueError("duplicate channel in bao_era_points.csv")
    return rows


def era_provenance_ok(rows: dict[int, dict]) -> bool:
    if set(rows) != set(ERA_PRODUCT_PINS):
        return False
    generator_digest = path_sha256(
        ROOT / "scripts" / "calibrated_thresholds.py")
    try:
        for ch, (filename, digest) in ERA_PRODUCT_PINS.items():
            row = rows[ch]
            if not (
                all(row[key] == value
                    for key, value in ERA_VALUE_PINS[ch].items())
                and
                row["product_file"] == filename
                and row["product_sha256"] == digest
                and row["generator_sha256"] == generator_digest
                and row["analysis_source_sha256"] == ERA_SOURCE_PIN
                and row["product_schema"] == ERA_PRODUCT_SCHEMA
                and row["detector_version"].startswith("pilot-proxy/")
                and row["eta_basis"] == "eta_mu_1"
                and row["floor_basis"] == "quiet_era_p90"
                and row["floor_era"]
                and int(row["floor_frames"]) > 0
                and float(row["floor_db"]) < 0.0
                and float(row["tau_seconds"]) > 0.0
            ):
                return False
            tol = float(row["r_tol_dilation"])
            eta1_ratio = float(row["r_eta1_adopted"]) / tol
            cost_ratio = float(row["r_cost_adopted"]) / tol
            if not (
                math.isclose(eta1_ratio, float(row["r_over_rtol"]),
                             rel_tol=2e-9, abs_tol=1e-10)
                and math.isclose(
                    cost_ratio, float(row["best_cost_r_over_rtol"]),
                    rel_tol=2e-9, abs_tol=1e-10)
            ):
                return False
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return False
    return True


def world_provenance_ok(rows: dict[tuple[str, int], dict],
                        era: dict[int, dict]) -> bool:
    expected = {(world, ch) for world in WORLD_BANK_PINS
                for ch in WORLD_PRODUCT_PINS}
    if set(rows) != expected:
        return False
    source_pins = {
        "generator_sha256": path_sha256(ROOT / "scripts" /
                                         "three_worlds.py"),
        "bias_source_sha256": path_sha256(ROOT / "scripts" /
                                           "bias_tolerance.py"),
        "residual_source_sha256": path_sha256(ROOT / "src" / "baonoise" /
                                               "residual.py"),
    }
    try:
        for (world, ch), row in rows.items():
            bank_file, bank_digest, kfg = WORLD_BANK_PINS[world]
            product_file, product_digest = WORLD_PRODUCT_PINS[ch]
            recorded_kfg = (None if row["bank_kfg_fac"] == ""
                            else float(row["bank_kfg_fac"]))
            if not (
                all(row[key] == value for key, value in source_pins.items())
                and row["bank_file"] == bank_file
                and row["bank_sha256"] == bank_digest
                and row["bank_schema"] == "2"
                and row["bank_source_commit"] == WORLD_SOURCE_COMMIT
                and row["bank_source_sha256"] == WORLD_SOURCE_SHA256
                and row["bank_backend_commit"] == WORLD_BACKEND_COMMIT
                and row["bank_backend_sha256"] == WORLD_BACKEND_SHA256
                and recorded_kfg == kfg
                and float(row["bank_epsilon_fg"]) == 0.0
                and float(row["bank_p_res"]) == 1.0
                and row["bank_grid_points"] == "27"
                and row["product_file"] == product_file
                and row["product_sha256"] == product_digest
                and int(row["floor_frames"]) > 0
            ):
                return False
        ch35 = [rows[(world, 35)] for world in WORLD_ORDER]
        if not all(
            row["floor_epoch"] == "through 2021-10"
            and row["floor_frames"] == era[35]["floor_frames"]
            and math.isclose(float(row["floor_db"]),
                             float(era[35]["floor_db"]),
                             rel_tol=0.0, abs_tol=1e-8)
            for row in ch35
        ):
            return False
    except (KeyError, TypeError, ValueError):
        return False
    return True


def world_rows_sha256(rows: dict[tuple[str, int], dict]) -> str:
    payload = [
        {key: rows[item][key] for key in sorted(rows[item])}
        for item in sorted(rows)
    ]
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def world_results_ok(rows: dict[tuple[str, int], dict]) -> bool:
    if world_rows_sha256(rows) != WORLD_ROWS_SHA256:
        return False
    same_by_channel = (
        "residual_status", "n_eta1_kept", "n_eta1_valid",
        "min_eta1_kept", "product_file", "product_sha256", "floor_epoch",
        "floor_frames", "floor_db", "floor_evidence", "tau_quality",
        "tau_reason", "tau_capped",
    )
    try:
        for ch in WORLD_PRODUCT_PINS:
            channel_rows = [rows[(world, ch)] for world in WORLD_ORDER]
            reference = channel_rows[0]
            if not all(all(row[field] == reference[field]
                           for field in same_by_channel)
                       for row in channel_rows):
                return False
            base_residual = reference["r_fine"]
            for world, row in zip(WORLD_ORDER, channel_rows):
                if not math.isclose(float(row["suppression_db"]),
                                    WORLD_SUPPRESSION_DB[world],
                                    rel_tol=0.0, abs_tol=1e-12):
                    return False
                if row["tau_capped"] != str(
                        row["tau_quality"] == "refused"):
                    return False
                if row["residual_status"] == "insufficient_kept_frames":
                    if not (
                        int(row["n_eta1_kept"]) < int(row["min_eta1_kept"])
                        and row["r_fine"] == ""
                        and all(row[f"pass_{name}"] == ""
                                for name in ("aperp", "apar", "fs8"))
                    ):
                        return False
                    continue
                if row["residual_status"] != "evaluated":
                    return False
                residual = float(row["r_fine"])
                if not (math.isfinite(residual) and residual > 0.0):
                    return False
                expected = float(base_residual) / 10.0 ** (
                    WORLD_SUPPRESSION_DB[world] / 10.0)
                if not math.isclose(residual, expected, rel_tol=2e-12,
                                    abs_tol=1e-15):
                    return False
                for name in ("aperp", "apar", "fs8"):
                    tolerance = float(row[f"tol_{name}"])
                    if not (math.isfinite(tolerance) and tolerance > 0.0):
                        return False
                    if row[f"pass_{name}"] != str(residual <= tolerance):
                        return False
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return False
    return True


def world_margin(row: dict) -> str:
    return f"{float(row['tol_fs8']) / float(row['r_fine']):.2g}"


def fig31_clean_columns() -> list[tuple[float, float]]:
    """The seven columns of the Ch. 9 clean-baseline mini-table, from
    out/fig31_validation.csv: the table samples every other forecast bin plus
    the last (z = 0.85 ... 2.43), quoting sigma_dv_clean_pct."""
    rows = {round(float(r["z_center"]), 2): float(r["sigma_dv_clean_pct"])
            for r in read_csv("fig31_validation.csv")}
    return [(z, rows[z]) for z in (0.85, 1.05, 1.25, 1.45, 1.65, 1.85, 2.43)]


def required_times_years() -> dict[str, float]:
    """Survey-level 5-sigma on-sky years per scenario
    (out/required_times.csv)."""
    return {r["scenario"]: float(r["years_5sig"])
            for r in read_csv("required_times.csv")}


def bin_target_years(zbin: str = "1.40-1.50") -> dict[str, float]:
    """Bin-level 5-sigma on-sky years per scenario for one redshift bin
    (out/bin_level_targets.csv); 1.40-1.50 is the most affected DTV bin."""
    return {r["scenario"]: float(r["years_bin5sig"])
            for r in read_csv("bin_level_targets.csv")
            if r["zbin"] == zbin}


def perbin_fs8_tolerances() -> dict[int, float]:
    """Per-bin minimum accepted fsigma8 r_tolerance of the
    perbin_noise_normalized ledger in
    out/forecast_completion_all_dtv_bins.json -- the quantity the
    dissertation's per-bin tolerance table quotes at x1e-3."""
    data = json.loads(
        (OUT / "forecast_completion_all_dtv_bins.json").read_text())
    tol: dict[int, float] = {}
    for b in data["ledgers"]["perbin_noise_normalized"]["bins"]:
        vals = [pt["parameters"]["fs8"]["central"]["r_tolerance"]
                for pt in b["points"] if pt["parameters"]["fs8"]["accepted"]]
        if vals:
            tol[int(b["bin_index"])] = min(vals)
    return tol


def template_rows(family: str = "noise_shaped") -> list[dict]:
    """One analytic family's per-bin rows of
    out/forecast_completion_template_comparison.csv."""
    return [r for r in read_csv("forecast_completion_template_comparison.csv")
            if r["family"] == family]


def frac_needles(x: float) -> list[str]:
    """A fraction as quoted raw (4 dp) or as a percentage (1 dp)."""
    return [f"{100 * x:.1f}%", f"{100 * x:.1f} %", f"{x:.4f}"]


def num_needles(x: float, nds: tuple[int, ...] = (3, 2)) -> list[str]:
    """A number at fixed roundings; every needle keeps >= 3 significant
    characters so short strings like '2.1' can never match by accident."""
    out = []
    for nd in nds + ((1,) if x >= 100 else ()):
        s = f"{x:.{nd}f}"
        if len(s.replace(".", "").lstrip("0")) >= 3 and s not in out:
            out.append(s)
    return out


# ---------------------------------------------------------------- registry
def run_checks(ck: Checker, summary: dict | None) -> None:
    # ---- Fig. 9.4 / SS9.7: one comparison population --------------------
    ck.section("Fig. 9.4 / SS9.7 -- keep-everything on one population")
    if summary is None:
        ck.skip("summary_v2 policy invariants",
                "pass --summary-json <pilot-proxy>/data/provenance/"
                "dissertation_summary_v2.json")
    else:
        pol = {p["policy_key"]: p
               for p in summary["bao_policy_case"]["policies"]}
        keep = float(pol["keep_everything"]["residual_multiple"])
        mad = float(pol["mad_1p8"]["residual_multiple"])
        ratio = max(keep, mad) / min(keep, mad)
        ok = ratio < 2.0
        ck._emit("PASS" if ok else "FAIL",
                 "keep vs MAD residual multiple within 2x (one population)",
                 "" if ok else
                 f"keep={keep:g}x vs MAD={mad:g}x (ratio {ratio:.1f}); "
                 "regenerate keep_everything via scripts/policy_comparison.py"
                 " --json (expect ~1566x / 3.35x), then re-export Fig 9.4")
        for key, p in pol.items():
            mult = int(p["residual_multiple"])
            # Token-bounded so hex digests in scanned manifests cannot match.
            ck.require(f"policy '{key}' multiple in text or figure data",
                       rf"(?<![\w.]){mult}(x|(?![\w.]))",
                       "quote it in prose, or land figure_src/data/.../"
                       "bao_policy_case.csv via the export and pass it with"
                       " --also-scan", wide=True)
    ck.forbid("stale keep-everything caption", r"316x over",
              "Fig 9.4 caption is the all-frames r_keep population; regenerate"
              " after the snapshot fix")
    ck.require("SS9.7 incumbent-comparison multiple",
               r"(?<![\w.])1566(x|(?![\w.]))",
               "keep 2.35 -> 1566x on the acquisitions>=8 base (prose or"
               " figure data)", wide=True)

    # ---- Table 9.4 <- out/optimal_thresholds.csv ------------------------
    ck.section("Table 9.4 <- out/optimal_thresholds.csv")
    for ch, r in sorted(threshold_rows().items()):
        # Needles follow the table's own renderings: eta 2 dp, f as a 1 dp
        # percentage, r at 4 dp, margin as "N.Nx", penalty 2 dp (whole "Nx"
        # when it is quoted in prose, e.g. channel 31's 177x time cost).
        pen = float(r["penalty"])
        ck.value(f"ch {ch}: eta*", [f"{float(r['eta']):.2f}"],
                 "quote the CSV at the table's rounding")
        ck.value(f"ch {ch}: kept fraction f", frac_needles(float(r["f"])),
                 "quote the CSV at the table's rounding")
        ck.value(f"ch {ch}: residual r", [f"{float(r['r_fine']):.4f}"],
                 "quote the CSV at the table's rounding")
        ck.value(f"ch {ch}: margin",
                 [f"{float(r['margin']):.1f}x", f"{float(r['margin']):.2f}"],
                 "quote the CSV at the table's rounding")
        ck.value(f"ch {ch}: penalty",
                 num_needles(pen) + ([f"{pen:.0f}x"] if pen >= 100 else []),
                 "quote the CSV at the table's rounding")

    # ---- Worlds table <- out/three_worlds.csv --------------------------
    ck.section("Worlds table <- out/three_worlds.csv")
    worlds = worlds_rows()
    worlds_provenance = world_provenance_ok(worlds, era_rows())
    ck._emit("PASS" if worlds_provenance else "FAIL",
             "worlds source identities preserved",
             "" if worlds_provenance else
             "regenerate the direct worlds table")
    worlds_results = world_results_ok(worlds)
    ck._emit("PASS" if worlds_results else "FAIL",
             "worlds residuals and verdicts are internally consistent",
             "" if worlds_results else
             "regenerate the direct worlds table")
    for ch in (33, 35):
        cells = []
        for world in WORLD_ORDER:
            row = worlds[(world, ch)]
            value = re.escape(world_margin(row))
            if row["pass_fs8"] == "True":
                value = rf"\\mathbf\{{{value}\}}"
            cells.append(value)
        pattern = rf"ch{ch}\s*&\s*" + r"\s*&\s*".join(cells)
        ck.require(f"ch {ch}: direct fs8 margins", pattern,
                   "quote out/three_worlds.csv at two significant digits")

    ch32 = [worlds[(world, 32)] for world in WORLD_ORDER]
    refusal_ok = all(
        r["residual_status"] == "insufficient_kept_frames"
        and r["n_eta1_kept"] == "16"
        and r["n_eta1_valid"] == "8359"
        and r["min_eta1_kept"] == "30"
        and not r["r_fine"]
        and all(not r[f"pass_{p}"] for p in ("aperp", "apar", "fs8"))
        for r in ch32)
    ck._emit("PASS" if refusal_ok else "FAIL",
             "ch 32: eta=1 refusal preserved in CSV",
             "" if refusal_ok else
             "expected 16/8359 kept, minimum 30, with blank margins")
    ck.require(
        "ch 32: insufficient population in worlds table",
        r"ch32\s*&\s*\\multicolumn\{4\}\{c\}\{not evaluated: "
        r"16<30 kept frames at \\eta=1 in its transmitter-on era\}",
        "render the machine-readable refusal rather than a numeric margin")

    deployed29 = worlds[("deployed", 29)]
    aperp_over = (float(deployed29["r_fine"])
                  / float(deployed29["tol_aperp"]))
    ck.require(
        "ch 29: deployed-cut perpendicular excess",
        rf"ch29\s*&\s*fails all\s*&\s*fails all\s*&\s*fails all"
        rf"\s*&\s*fails all \(\\alpha_\\perp {aperp_over:.1f}x over\)",
        "quote out/three_worlds.csv at one decimal place")
    ck.require(
        "ch 35: isolated parallel-dilation pass disclosed",
        r"Channel 35.{0,300}parallel dilation alone passes at 110 ns",
        "the direct bank passes apar only; aperp and fs8 still fail")
    ch35_provenance = all(
        worlds[(world, 35)].get("floor_evidence") == "measured"
        and worlds[(world, 35)].get("tau_quality") == "measured"
        for world in WORLD_ORDER)
    ck._emit("PASS" if ch35_provenance else "FAIL",
             "ch 35: measured floor and coherence preserved in CSV",
             "" if ch35_provenance else
             "expected measured floor_evidence and tau_quality")
    ck.require(
        "ch 35: measured off-era floor disclosed",
        r"Channel 35.{0,300}measured off-era floor",
        "state the floor basis used by the direct worlds row")

    # ---- Current-era endpoints ----------------------------------------
    ck.section("Current-era endpoints <- bao_era_points.csv")
    era = era_rows()
    ch32, ch35 = era[32], era[35]
    provenance_ok = era_provenance_ok(era)
    ck._emit("PASS" if provenance_ok else "FAIL",
             "current-era source identity and ratios preserved",
             "" if provenance_ok else
             "regenerate the compact current-era export")
    quality_ok = (
        ch32["tau_quality"] == "bounded_above"
        and ch35["tau_quality"] == "measured"
    )
    ck._emit("PASS" if quality_ok else "FAIL",
             "current-era coherence provenance preserved",
             "" if quality_ok else
             "expected ch32 bounded_above and ch35 measured")

    ch32_minutes = float(ch32["tau_seconds"]) / 60.0
    ch32_best = float(ch32["best_cost_r_over_rtol"])
    ck.require(
        "ch 32: bound and adopted-coherence excess",
        rf"Channel 32.{{0,500}}(?:upper bound.{{0,120}}"
        rf"\\tau_c\\leq ?{ch32_minutes:g}|"
        rf"\\tau_c\\leq ?{ch32_minutes:g}.{{0,120}}upper bound)"
        rf".{{0,500}}{ch32_best:.2f}x",
        "quote the upper bound and best-cost adopted-coherence excess")

    ch35_minutes = float(ch35["tau_seconds"]) / 60.0
    ch35_mask = 100.0 * float(ch35["masked_fraction"])
    ch35_endpoint = float(ch35["r_over_rtol"])
    ch35_best_mask = 100.0 * float(ch35["best_cost_masked_fraction"])
    ch35_best = float(ch35["best_cost_r_over_rtol"])
    ck.require(
        "ch 35: calibrated endpoint",
        rf"[Cc]hannel 35.{{0,500}}{ch35_mask:.1f}%"
        rf".{{0,300}}{ch35_endpoint:.0f}x",
        "quote the calibrated eta_mu=1 endpoint")
    ck.require(
        "ch 35: best-cost endpoint",
        rf"{ch35_best_mask:.2f}%.*{ch35_best:.0f}x",
        "quote the best-cost masked fraction and tolerance excess")
    ck.require(
        "ch 35: measured coherence",
        rf"current-era.{{0,200}}(?:tau_c=)?{ch35_minutes:.1f}"
        rf".{{0,20}}min.{{0,80}}measured"
        rf"|measured.{{0,80}}{ch35_minutes:.1f}.{{0,20}}min",
        "quote the current-era measured coherence time")

    # ---- Table 8.1 <- out/fine_operating_points.csv ---------------------
    ck.section("Table 8.1 <- out/fine_operating_points.csv")
    for ch, r in sorted(fine_rows().items()):
        ck.value(f"ch {ch}: eta_q16 filled",
                 [str(int(float(r["multiplier_q16"])))],
                 "fill the pending cells from the epoch-restricted rerun of"
                 " scripts/fine_operating_point.py; CSV is authoritative")
        if r.get("r_late"):
            ck.value(f"ch {ch}: r_late", [f"{float(r['r_late']):.3f}"],
                     "quote the CSV at the table's rounding")

    # ---- Ch.9 clean-baseline mini-table <- out/fig31_validation.csv -----
    ck.section("Ch.9 baseline mini-table <- out/fig31_validation.csv")
    for i, (z, v) in enumerate(fig31_clean_columns()):
        # Column-anchored so a matching digit string elsewhere in the text
        # cannot green-light a stale cell; 2 dp accepted as a prefix of the
        # table's 3 dp rendering.
        alt = f"(?:{re.escape(f'{v:.2f}')}|{re.escape(f'{v:.3f}')})"
        ck.require(f"z = {z:.2f}: sigma(D_V)/D_V clean, 1 on-sky yr",
                   rf", clean, 1 on-sky yr( & \d[\d.]*){{{i}}} & {alt}",
                   "quote out/fig31_validation.csv sigma_dv_clean_pct at the"
                   " mini-table's rounding")

    # ---- Table 9.1 <- out/required_times.csv + out/bin_level_targets.csv
    ck.section("Table 9.1 <- out/required_times.csv / bin_level_targets.csv")
    yrs = required_times_years()
    byrs = bin_target_years()
    ck.value("survey 5-sigma clean on-sky years", [f"{yrs['clean']:.4f}"],
             "quote out/required_times.csv years_5sig at the table's"
             " rounding")
    ck.value("survey 5-sigma measured on-sky years",
             [f"{yrs['measured']:.4f}"],
             "quote out/required_times.csv years_5sig at the table's"
             " rounding")
    ck.value("z=1.40-1.50 bin clean years", [f"{byrs['clean']:.3f}"],
             "quote out/bin_level_targets.csv years_bin5sig at the table's"
             " rounding")
    ck.value("z=1.40-1.50 bin measured years", [f"{byrs['measured']:.3f}"],
             "quote out/bin_level_targets.csv years_bin5sig at the table's"
             " rounding")
    ck.value("z=1.40-1.50 bin penalty (measured/clean years)",
             [f"{byrs['measured'] / byrs['clean']:.3f}"],
             "the bin penalty is the years_bin5sig ratio at 3 dp")
    # The table must also agree with itself: the quoted bin penalty has to
    # equal quoted-measured / quoted-clean within the rounding slack of its
    # own printed cells, whatever record the row happens to hold.
    row_pat = r" & (\d[\d.]*) & (\d[\d.]*) & (\d[\d.]*) & (\d[\d.]*)"
    clean_m = re.search(r"clean \(no DTV\)" + row_pat, ck.text)
    meas_m = (re.search(row_pat, ck.text[clean_m.end():])
              if clean_m else None)
    if meas_m is None:
        ck._emit("FAIL", "Table 9.1 bin penalty consistent with its years",
                 "rows not found; keep the 'clean (no DTV)' label and four"
                 " numeric columns per row")
    else:
        def half_ulp(s: str) -> float:
            return 0.5 * 10.0 ** -(len(s) - s.index(".") - 1
                                   if "." in s else 0)
        c_bin, m_bin, pen = clean_m.group(3), meas_m.group(3), meas_m.group(4)
        lo = (float(m_bin) - half_ulp(m_bin)) / (float(c_bin)
                                                 + half_ulp(c_bin))
        hi = (float(m_bin) + half_ulp(m_bin)) / (float(c_bin)
                                                 - half_ulp(c_bin))
        ok = lo - half_ulp(pen) <= float(pen) <= hi + half_ulp(pen)
        ck._emit("PASS" if ok else "FAIL",
                 "Table 9.1 bin penalty consistent with its years",
                 "" if ok else
                 f"quoted penalty {pen} outside {m_bin}/{c_bin} ="
                 f" [{lo:.3f}, {hi:.3f}]; recompute the row from"
                 " out/bin_level_targets.csv")

    # ---- per-bin r_tol table <- forecast_completion_all_dtv_bins.json ---
    ck.section("Per-bin r_tol table <- out/forecast_completion_all_dtv_bins"
               ".json")
    tol = perbin_fs8_tolerances()
    # Columns run 1.30-1.40 .. 1.90-2.04 (bin indices 5..11); the binding
    # pair and the last two bins are the drift-prone cells worth pinning.
    for b, col, zbin in ((5, 0, "1.30-1.40"), (6, 1, "1.40-1.50"),
                         (10, 5, "1.80-1.90"), (11, 6, "1.90-2.04")):
        needle = re.escape(f"{1e3 * tol[b]:.2f}")
        ck.require(f"bin {zbin}: min accepted fs8 r_tol x1e3",
                   rf"\(x 10\^\{{-3\}}\)( & \d[\d.]*){{{col}}} & {needle}",
                   "quote the perbin_noise_normalized ledger minimum at the"
                   " table's rounding")

    # ---- template table <- forecast_completion_template_comparison.csv --
    ck.section("Template table <- out/forecast_completion_template_"
               "comparison.csv")
    trs = template_rows()
    per = [float(r["perbin_binding_tolerance"]) for r in trs]
    joint = [float(r["combined_binding_tolerance"]) for r in trs]
    ck.value("noise-shaped per-bin fs8 tolerance range",
             [f"{min(per):.6f}-{max(per):.6f}"],
             "quote the CSV's perbin_binding_tolerance span at the table's"
             " rounding")
    ck.value("noise-shaped joint fs8 tolerance range",
             [f"{min(joint):.6f}-{max(joint):.6f}"],
             "quote the CSV's combined_binding_tolerance span at the table's"
             " rounding")
    ck.value("noise-shaped per-bin accepted/rejected count",
             [f"{sum(int(r['perbin_accepted']) for r in trs)}"
              f"/{sum(int(r['perbin_rejected']) for r in trs)}"],
             "quote the CSV's per-bin acceptance tally")

    # ---- SS9.3 quarterly-table provenance --------------------------------
    ck.section("SS9.3 quarterly-table provenance")
    ck.require("fs/2 legacy epoch named next to the quarterly table",
               r"(fs\s*/\s*2|half-?band).{0,600}quarterly"
               r"|quarterly.{0,600}(fs\s*/\s*2|half-?band)",
               "rewrite per PAPER_PLAN.md Amendment A1: legacy bank b0dce17a,"
               " center-at-Nyquist, pilots suppressed 39-47 dB except ch 30")
    ck.forbid("'unrecorded' provenance claim", r"unrecorded",
              "the generating rule IS recorded"
              " (analysis/survey_composition.py, 2026-07-18)")

    # ---- SS9.4 hand-back range & SS6.3 factor of ten ----------------------
    ck.section("SS9.4 / SS6.3 -- ranges and factors")
    ck.forbid("stale hand-back range", r"5\.9-7\.8",
              "with 11.4 dB at 200 ns, 8.2/3.6 dB at the cuts the hand-back"
              " is 3.2-7.8 dB (2.1-6x); SS9.9 already says 3.2 dB")
    ck.require("corrected hand-back range", r"3\.2-7\.8", "see above")
    ck.forbid_pair("fxfft statistic-move dB self-consistent",
                   r"0\.00026 ?dB", r"5\.9 ?x ?10",
                   "10 log10(1 - 5.9e-4) = -0.0026 dB: one of the two is 10x"
                   " off (also quoted in SS6.7 and docs/DESIGN_DECISIONS.md)")

    # ---- Abstract / Ch.1 / Ch.11 vs Tables 9.6/9.8 ----------------------
    ck.section("Abstract / Ch.1 / Ch.11 vs Tables 9.6/9.8")
    ck.forbid("abstract: 'Ten contiguous channels'", r"Ten contiguous",
              "21 of 23 (16-36) have products; rewrite from Tables 9.6/9.8")
    ck.forbid("abstract: 'remaining thirteen channels'",
              r"remaining thirteen", "14-15 remain; the rest are measured")
    ck.forbid("'ten measured channels'", r"ten measured channels",
              "21 measured channels; Table 11.1 needs rows for 16-26")
    ck.forbid("DTV-vs-noise range understated", r"10(-| to )35 dB",
              "measured range is roughly +0 to -44 dB (Tables 9.6/9.8)")
    ck.forbid("tolerance-excess range", r"three hundred thousand",
              "measured spread is ~3e2 (ch 33) to ~5e6 (ch 30)")
    ck.forbid("'about 42 ms' as a CHIME property", r"about 42 ms",
              "current X-engine integrates ~31 ms; 41.94 ms is the detector"
              " frame -- reword")
    ck.forbid("sign-off count", r"three transmitter sign",
              "Fig 8.1 names four (19, 20, 26, 27) and SS9.10 adds ch 32")
    ck.forbid("Eisenstein 2005 sample size", r"half a million",
              "Eisenstein et al. 2005: 46748 SDSS LRGs"
              " (Cole et al. 2005: ~221000 2dFGRS)")
    ck.require("corrected LRG count", r"46748|46,748", "see above")
    ck.forbid("'eight years'", r"eight years",
              "Dec 2018 - Jul 2026 = 7.6 yr; the repos say 7.6 everywhere")
    ck.require("7.6 yr archive span", r"7\.6 (yr|years)", "see above")
    ck.forbid("snapshot count", r"8500 snapshots",
              "SS7.1 says 9192 probed / 8962 valid; pick one census")
    ck.forbid("Vancouver driving distance", r"389 km",
              "great-circle DRAO->Mt. Seymour ~240 km; 389 km is the road")
    ck.forbid("Seattle driving distance", r"451 km",
              "great-circle DRAO->Seattle ~275 km; 451 km is the road")

    # ---- SS9.5 / SS9.7 chain arithmetic ------------------------------------
    ck.section("SS9.5 / SS9.7 chain arithmetic")
    ck.forbid("net chain gain", r"22\.9 dB",
              "r_proxy/p_kept = 0.0359/10^-4.495 = +30.5 dB NET (already"
              " includes the -7.6 dB ground filter); redo the ledger")
    ck.forbid("stale three-channel frame-stage r_proxy list",
              r"0\.057, 0\.0022",
              "Table 9.6 on-air shelves give 0.085 / 3.9e-4 / 1.35e-3")

    # ---- SS6.2 encoding ----------------------------------------------------
    ck.section("SS6.2 encoding / SS10.1 packer duties")
    ck.forbid("'consumes the receiver's native format directly'",
              r"native format directly",
              "native samples are excess-8; the adapter repacks losslessly")
    ck.forbid("'sign extension' as the unpack story", r"sign extension",
              "repack to two's complement (per byte, XOR 0x88); the kernel"
              " sign-extends nibbles")
    ck.require("XOR 0x88 stated", r"XOR 0x88", "state the packer conversion")

    # ---- evidence anchors still to add ----------------------------------
    ck.section("Evidence anchors (red until the artifact exists and is cited)")
    ck.require("bootstrap-rule P_fa stated", r"48\.5 ?(%|per ?cent)",
               "the null_power_ratio point spends 48.5% of verified-quiet"
               " time (docs/DESIGN_DECISIONS.md); put it in SS5.5 and Ch. 9")
    ck.require("fine-gain Monte Carlo cited", r"fine_gain_mc|measure_fine_gain",
               "run tools/measure_fine_gain.py, commit docs/evidence/"
               "fine_gain_mc_<date>/, cite it for the coherent-gain credit")
    ck.require("ROC / Youden-J analysis cited", r"[Yy]ouden",
               "commit youden_j.py with the survey analysis and cite the"
               " coarse-vs-fine ROC table")

    # ---- revision-artifact phrasing --------------------------------------
    ck.section("Revision-artifact phrasing (editor's notes to remove)")
    for phrase in ("supplied for this revision", "not invented here",
                   "the present draft", "left pending", "remembered analysis",
                   "dissertation-source bundle", "the revised analysis"):
        ck.forbid(f"'{phrase}'", re.escape(phrase),
                  "replace with a plain evidence-status statement")


# ---------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tex", nargs="+", required=True,
                    help=".tex files, directories of .tex (an Overleaf git"
                         " clone), or a plain-text export")
    ap.add_argument("--baseline", default=None,
                    help="path to a file containing an integer FAIL budget."
                         " With it, exit 0 while failures <= budget and 1"
                         " only on regression -- a CI ratchet: lower the"
                         " committed number as items are fixed. A missing"
                         " file falls back to the strict gate.")
    ap.add_argument("--also-scan", nargs="*", default=[],
                    help="extra text surfaces (files or directories: frozen"
                         " figure data CSVs, evidence exports) consulted only"
                         " by figure-borne checks")
    ap.add_argument("--summary-json", default=None,
                    help="pilot-proxy data/provenance/"
                         "dissertation_summary_v2.json (policy invariants"
                         " SKIP without it)")
    args = ap.parse_args(argv)

    text, files = load_tex(args.tex)
    extra = ""
    for raw in args.also_scan:
        q = Path(raw)
        picks = ([q] if q.is_file() else
                 [f for f in sorted(q.rglob("*"))
                  if f.suffix in (".csv", ".json", ".md", ".txt", ".py",
                                  ".tikz", ".tex")])
        for f in picks:
            extra += " " + normalize(
                f.read_text(encoding="utf-8", errors="replace"),
                tex=f.suffix == ".tex")
    print(f"checking {len(files)} source file(s), {len(text):,} chars"
          f" normalized"
          + (f" (+{len(extra):,} chars scanned)" if extra else ""))
    summary = None
    if args.summary_json:
        summary = json.loads(Path(args.summary_json).read_text())

    ck = Checker(text, extra)
    run_checks(ck, summary)
    print(f"\n{ck.n - ck.failures}/{ck.n} checks passed.")
    if ck.failures:
        print("Each FAIL line above names the fix and the authoritative"
              " source.")
    if args.baseline is not None:
        base_path = Path(args.baseline)
        if not base_path.is_file():
            print(f"baseline file {base_path} not found; strict gate applies.")
        else:
            budget = int(base_path.read_text().strip())
            if ck.failures > budget:
                print(f"REGRESSION: {ck.failures} failures exceed the"
                      f" committed baseline of {budget}.")
                return 1
            if ck.failures < budget:
                print(f"Ratchet: {ck.failures} failures, baseline {budget}"
                      f" -- lower {base_path} to {ck.failures}.")
            else:
                print(f"Within baseline ({budget}).")
            return 0
    return 1 if ck.failures else 0


if __name__ == "__main__":
    sys.exit(main())
