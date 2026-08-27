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
        --summary-json ../pilot-proxy/data/provenance/dissertation_summary_v3.json

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
    "5c92cea44fa00c495a71a304467614f978c2af16e67d0c6881890d89d21c893e")
ERA_GENERATOR_PIN = (
    "2c188cd7a1689b088c0d80406507b145283b02aa38bdfcc9e0d305f72a484029")
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
             "1717cd3b73089b9c0510bdc12d08b8536961da93fc7218df13eb8e133ffe2288",
             None),
    "peak1": ("fisher_bank_chime2022_pres_kfg22_dense.npz",
              "b112825024aa294216432b08eddd225ea5a2480cf59004885e190fcb4aaa0e8a",
              22.0),
    "peak2": ("fisher_bank_chime2022_pres_kfg44_dense.npz",
              "f57fc323617b05852086499c964c4326f390fb5c6338a645ebfb0efb2185069a",
              44.0),
    "deployed": ("fisher_bank_chime2022_pres_kfg80_dense.npz",
                  "e201e3517510305041a894dc1ea16d027cf4a53ed14cd2cd5b60d6a2f43c86a6",
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
WORLD_SOURCE_COMMIT = "abba22a2c2a489a712ea0f21f794139a987935cf"
WORLD_SOURCE_SHA256 = (
    "4cc1bcd4662e3026b4ea5f5565aad8853814bbdb12b8cd0fbe006fbf04fb7bb4")
WORLD_BACKEND_COMMIT = "f6bc9ea0972028ce30472dd21b25d4b21b7068c0"
WORLD_BACKEND_SHA256 = (
    "efad0173be49d51679cf98071ccd1dfccd386dc9b2774e202164086347a4c2cf")
WORLD_SUPPRESSION_DB = {
    "none": 0.0, "peak1": 3.6, "peak2": 8.2, "deployed": 11.4,
}
WORLD_ROWS_SHA256 = (
    "a10ae66dd4ea76a9997770e4dd8973a4bd225e09013f7b1b41bd4766119e3a01")
WORLD_PIPELINE_SOURCE_PINS = {
    "generator_sha256":
        "a3f04c067c3bc251eabe9a42f0e54b3a523971ba8cf4987e5d93ffa37b91993a",
    "bias_source_sha256":
        "d260c276d5821e766b52e18f6c686e2978e4fa12e243bb2b6adb0ca59e1e6530",
    "residual_source_sha256":
        "304f91c97059caac2e34d59c31258b6caad6fc58399d68346a432dd63184821c",
    "selection_policy_sha256":
        "b36c612ca1a59c0b5e09ced129bca9e15c589fb94a7e2e3648c6ebd815b68cf7",
}


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
    try:
        for ch, (filename, digest) in ERA_PRODUCT_PINS.items():
            row = rows[ch]
            if not (
                all(row[key] == value
                    for key, value in ERA_VALUE_PINS[ch].items())
                and
                row["product_file"] == filename
                and row["product_sha256"] == digest
                and row["generator_sha256"] == ERA_GENERATOR_PIN
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
    try:
        for (world, ch), row in rows.items():
            bank_file, bank_digest, kfg = WORLD_BANK_PINS[world]
            product_file, product_digest = WORLD_PRODUCT_PINS[ch]
            recorded_kfg = (None if row["bank_kfg_fac"] == ""
                            else float(row["bank_kfg_fac"]))
            if not (
                all(row[key] == value
                    for key, value in WORLD_PIPELINE_SOURCE_PINS.items())
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


def required_time_penalties() -> dict[str, float]:
    """Survey-level time penalty against the clean baseline per scenario
    (out/required_times.csv). The column is formed from the underlying
    hours, so it is finer than the ratio of the rounded years_5sig cells
    and is the quantity the table's survey-penalty column quotes."""
    return {r["scenario"]: float(r["time_penalty_vs_clean"])
            for r in read_csv("required_times.csv")}


def half_ulp(s: str) -> float:
    """Half a unit in the last printed place of a decimal literal -- the
    rounding slack a quoted table cell carries."""
    return 0.5 * 10.0 ** -(len(s) - s.index(".") - 1 if "." in s else 0)


def table_row_cells(text: str, label: str,
                    after: str | None = None) -> list[str] | None:
    """The cells of one tabular row, located by its leading label and cut at
    the row terminator. Checking a value in its own cell matters: a bare
    substring search over the whole document can be satisfied by an
    unrelated number elsewhere (0.984 is a substring of 0.9845). Pass
    ``after`` to scope the search past an anchor when a row label is not
    unique in the document."""
    if after is not None:
        start = text.find(after)
        if start < 0:
            return None
        text = text[start:]
    # Non-greedy to the row terminator rather than "no backslash until it":
    # a cell may legitimately hold a control sequence (the band-wide row
    # ends in \infty), and a single backslash is not the terminator.
    m = re.search(re.escape(label) + r"([\s\S]*?)\\\\", text)
    if m is None:
        return None
    return [c.strip() for c in m.group(1).split("&")]


def cell_matches(printed: str, value: float) -> bool:
    """A printed cell agrees with a computed value when the value lies
    within half a unit of that cell's own last printed place, so each cell
    is held at whatever precision it chose to display."""
    try:
        return abs(value - float(printed)) <= half_ulp(printed)
    except ValueError:
        return False


def check_row(ck, name: str, label: str, values: list[float], hint: str,
              first: int = 1, after: str | None = None) -> None:
    """Compare one recomputed row against the cells the table prints."""
    cells = table_row_cells(ck.text, label, after=after)
    if cells is None:
        ck._emit("FAIL", name,
                 f"row '{label}' not found; keep the row label and its"
                 " cells on one line")
        return
    got = cells[first:first + len(values)]
    if len(got) < len(values):
        ck._emit("FAIL", name,
                 f"row '{label}' has {len(got)} cells, expected"
                 f" {len(values)}")
        return
    bad = [(i, c, v) for i, (c, v) in enumerate(zip(got, values))
           if not cell_matches(c, v)]
    ck._emit("PASS" if not bad else "FAIL", name,
             "" if not bad else
             "; ".join(f"cell {i + 1} prints {c} but recomputes to"
                       f" {v:.6g}" for i, c, v in bad) + f"; {hint}")


def flagger_cells() -> dict[int, dict] | None:
    """Per-channel cells of the ch09 flagger comparison table, recomputed
    from the archive products via incumbent.compare_flaggers at the shipped
    defaults. That table is serialized in no artifact, so recomputation is
    its only source. Returns None when the products are unreachable (they
    are not vendored in the repo), and the caller skips rather than fails."""
    try:
        from rfisher import products
        from rfisher.incumbent import DEFAULT_MAD_K, compare_flaggers
    except Exception:
        return None
    got = products.paths([34, 35, 36], announce=False)
    if len(got) < 3:
        return None
    cells: dict[int, dict] = {}
    for ch, path in got.items():
        rows, meta = compare_flaggers(path, mad_k=DEFAULT_MAD_K,
                                      sk_nsigma=3.0, min_frames=8)
        entry = {"duty": float(meta["duty_cycle"])}
        for row in rows:
            name = row.name.lower()
            key = ("mad" if name.startswith("mad")
                   else "sk" if name.startswith("sk")
                   else "proxy" if "proxy" in name else None)
            if key:
                entry[key] = (float(row.reduction_db), float(row.f))
        cells[ch] = entry
    return cells


def table91_historical_rows() -> dict | None:
    """Table 9.1's substituted and band-wide rows, recomputed. They are
    absent from out/required_times.csv only because run_forecast.py's
    table_scens dict does not build them; both are first-class shipped
    scenarios and both move when the pinned bank is rebuilt, so holding
    them against the table's own baseline is weaker than recomputing.
    The band-wide row needs only the pinned bank. The substituted row also
    needs the ch34-36 archive products and is omitted without them."""
    try:
        import numpy as np

        from rfisher import forecast, scenarios, survey
        from rfisher.backend import import_radiofisher
        from rfisher.fisherbank import FisherBank
        from rfisher.resources import DEFAULT_BANK
    except Exception:
        return None
    try:
        bank = FisherBank(DEFAULT_BANK)
        style = ("perbin_A" if bank.meta["config"] == "chime2022"
                 else "shared_A")
        rf, rf_dir = ((None, None) if style == "perbin_A"
                      else import_radiofisher())
        fc = forecast.Forecast(bank, rf, style=style, rf_dir=rf_dir)
    except Exception:
        return None

    zbin = 6  # z = 1.40-1.50, the most affected DTV bin
    hour = survey.OVERVIEW_ONSKY_YEAR_HOURS

    def survey_hours(sc):
        return fc.required_hours(sc, 5.0)

    def bin_hours(sc):
        return fc.required_hours_metric(
            lambda t, sc=sc: fc.significance(sc, t, bins=[zbin]), 5.0)

    clean = scenarios.clean()
    h_clean, hb_clean = survey_hours(clean), bin_hours(clean)
    rows: dict[str, dict] = {}

    def add(key, sc):
        h5 = survey_hours(sc)
        entry = {"survey_years": h5 / hour, "survey_penalty": h5 / h_clean}
        hb = bin_hours(sc)
        if np.isfinite(hb):
            entry["bin_years"] = hb / hour
            entry["bin_penalty"] = hb / hb_clean
        rows[key] = entry

    add("band", scenarios.uniform(0.942, scenarios.DTV_BAND,
                                  excise_threshold=0.5))
    try:
        from rfisher import products
        got = products.paths([34, 35, 36], announce=False)
        if len(got) == 3:
            add("sub", scenarios.survey_product_scenario(
                [got[34], got[35], got[36]], fill_missing="csv"))
    except Exception:
        pass
    return rows


def eta_sweep_ch33(etas=(1, 1.2, 1.5, 2, 5)) -> list | None:
    """Channel 33's displayed eta sweep (residual.threshold_sweep). The grid
    is the one the chapter prints, not the pinned default grid, and the rows
    are serialized nowhere -- so this recomputation is the table's only
    source. None when the product is unreachable."""
    try:
        from rfisher import products
        from rfisher.residual import threshold_sweep
    except Exception:
        return None
    got = products.paths([33], announce=False)
    if 33 not in got:
        return None
    return threshold_sweep(got[33], etas=list(etas))


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
        ck.skip("summary_v3 policy invariants",
                "pass --summary-json <pilot-proxy>/data/provenance/"
                "dissertation_summary_v3.json")
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
             "worlds recorded source identities preserved",
             "" if worlds_provenance else
             "restore the authenticated snapshot or regenerate from its"
             " recorded inputs")
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
             "current-era recorded source identity and ratios preserved",
             "" if provenance_ok else
             "restore the authenticated snapshot or regenerate from its"
             " recorded inputs")
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
    ck.value("survey 5-sigma legacy rate-table on-sky years",
             [f"{yrs['legacy_rate_table']:.4f}"],
             "quote out/required_times.csv years_5sig at the table's"
             " rounding")
    ck.value("z=1.40-1.50 bin clean years", [f"{byrs['clean']:.3f}"],
             "quote out/bin_level_targets.csv years_bin5sig at the table's"
             " rounding")
    ck.value("z=1.40-1.50 bin legacy rate-table years",
             [f"{byrs['legacy_rate_table']:.3f}"],
             "quote out/bin_level_targets.csv years_bin5sig at the table's"
             " rounding")
    ck.value("z=1.40-1.50 bin penalty (legacy/clean years)",
             [f"{byrs['legacy_rate_table'] / byrs['clean']:.3f}"],
             "the bin penalty is the years_bin5sig ratio at 3 dp")
    # The table must also agree with itself: the quoted bin penalty has to
    # equal quoted-legacy / quoted-clean within the rounding slack of its
    # own printed cells, whatever record the row happens to hold.
    row_pat = r" & (\d[\d.]*) & (\d[\d.]*) & (\d[\d.]*) & (\d[\d.]*)"
    clean_m = re.search(r"uncontaminated baseline" + row_pat, ck.text)
    legacy_m = (re.search(row_pat, ck.text[clean_m.end():])
                if clean_m else None)
    if legacy_m is None:
        ck._emit("FAIL", "Table 9.1 bin penalty consistent with its years",
                 "rows not found; keep the 'uncontaminated baseline' label and four"
                 " numeric columns per row")
    else:
        c_bin = clean_m.group(3)
        legacy_bin = legacy_m.group(3)
        pen = legacy_m.group(4)
        lo = (float(legacy_bin) - half_ulp(legacy_bin)) / (float(c_bin)
                                                           + half_ulp(c_bin))
        hi = (float(legacy_bin) + half_ulp(legacy_bin)) / (float(c_bin)
                                                           - half_ulp(c_bin))
        ok = lo - half_ulp(pen) <= float(pen) <= hi + half_ulp(pen)
        ck._emit("PASS" if ok else "FAIL",
                 "Table 9.1 bin penalty consistent with its years",
                 "" if ok else
                 f"quoted penalty {pen} outside {legacy_bin}/{c_bin} ="
                 f" [{lo:.3f}, {hi:.3f}]; recompute the row from"
                 " out/bin_level_targets.csv")

    # The survey-penalty column. Only the published legacy row is a row of
    # required_times.csv, so it is pinned to the artifact. The products-
    # substituted and band-wide rows are absent from that CSV only because
    # run_forecast.py's table_scens dict does not build them: both are
    # reproducible from shipped constructors --
    # scenarios.survey_product_scenario([537, 521, 506], fill_missing="csv")
    # and scenarios.uniform(0.942, DTV_BAND, excise_threshold=0.5) -- and
    # they DO move when the pinned bank is rebuilt. Until those two are added
    # to run_forecast.py they cannot be pinned to an artifact here, so the
    # check below is a floor, not a ceiling: it holds each row against the
    # table's own baseline within the rounding slack of its printed cells,
    # which catches a stale or mistyped row but not a shared drift.
    ck.value("survey penalty, legacy rate table (published row)",
             [f"{required_time_penalties()['legacy_rate_table']:.3f}"],
             "quote out/required_times.csv time_penalty_vs_clean at the"
             " table's rounding")
    survey_pat = r"[^&]*& (\d[\d.]*) & (\d[\d.]*)"
    base_s = re.search(r"uncontaminated baseline" + survey_pat, ck.text)
    for label, name in (("legacy detector rate table", "legacy rate table"),
                        ("with products substituted", "products on ch 34-36"),
                        ("bootstrap rule band-wide", "bootstrap band-wide")):
        row_s = re.search(re.escape(label) + survey_pat, ck.text)
        if base_s is None or row_s is None:
            ck._emit("FAIL", f"Table 9.1 survey penalty self-consistent:"
                             f" {name}",
                     "row not found; keep the row label and its two survey"
                     " columns numeric")
            continue
        base_yr, row_yr, spen = (base_s.group(1), row_s.group(1),
                                 row_s.group(2))
        slo = (float(row_yr) - half_ulp(row_yr)) / (float(base_yr)
                                                    + half_ulp(base_yr))
        shi = (float(row_yr) + half_ulp(row_yr)) / (float(base_yr)
                                                    - half_ulp(base_yr))
        sok = slo - half_ulp(spen) <= float(spen) <= shi + half_ulp(spen)
        ck._emit("PASS" if sok else "FAIL",
                 f"Table 9.1 survey penalty self-consistent: {name}",
                 "" if sok else
                 f"quoted penalty {spen} outside {row_yr}/{base_yr} ="
                 f" [{slo:.3f}, {shi:.3f}]; recompute the row from"
                 " out/required_times.csv")

    # Recomputed cover for the same two rows. The self-consistency checks
    # above catch a mistyped or stale row; these catch a shared drift the
    # baseline moves with, which is what a bank rebuild produces.
    hist = table91_historical_rows()
    if hist is None:
        ck.skip("Table 9.1 historical rows recomputed",
                "the pinned forecast bank could not be loaded")
    else:
        check_row(ck, "Table 9.1 band-wide row recomputed",
                  "bootstrap rule band-wide",
                  [hist["band"]["survey_years"],
                   hist["band"]["survey_penalty"]],
                  "recompute with scenarios.uniform(0.942, DTV_BAND,"
                  " excise_threshold=0.5)")
        if "sub" in hist:
            sub = hist["sub"]
            check_row(ck, "Table 9.1 products-substituted row recomputed",
                      "with products substituted",
                      [sub["survey_years"], sub["survey_penalty"],
                       sub["bin_years"], sub["bin_penalty"]],
                      "recompute with scenarios.survey_product_scenario"
                      "([537, 521, 506], fill_missing='csv')")
        else:
            ck.skip("Table 9.1 products-substituted row recomputed",
                    "set RFISHER_PRODUCT_DIRS for the ch34-36 products")

    # ---- flagger comparison table <- incumbent.compare_flaggers ---------
    # Recomputed, not read: this table is serialized in no provenance
    # summary, no out/ artifact, and no vendored export, so a stale cell
    # here turns nothing else red. The products are not vendored, so the
    # section skips when they are unreachable.
    ck.section("Flagger table <- incumbent.compare_flaggers (products)")
    flag = flagger_cells()
    if flag is None:
        ck.skip("flagger comparison table",
                "set RFISHER_PRODUCT_DIRS to the archive per-pilot products")
    else:
        chans = (34, 35, 36)
        # 'duty cycle' also occurs in prose, so every row here is scoped
        # past this table's own column header.
        top = "shelf removed (dB)"
        check_row(ck, "flagger table duty cycle row", "duty cycle",
                  [flag[c]["duty"] for c in chans],
                  "recompute with compare_flaggers duty_cycle", after=top)
        for key, row_label, name in (
                ("mad", "MAD 1.8x (per acquisition)", "MAD 1.8x"),
                ("sk", "spectral kurtosis, 3\\sigma", "spectral kurtosis"),
                ("proxy", "pilot proxy (bootstrap rule)", "pilot proxy")):
            check_row(ck, f"flagger table {name} shelf removed (dB)",
                      row_label, [flag[c][key][0] for c in chans],
                      "recompute with compare_flaggers reduction_db",
                      after=top)
            check_row(ck, f"flagger table {name} masked fraction",
                      row_label, [flag[c][key][1] for c in chans],
                      "recompute with compare_flaggers f", first=4,
                      after=top)

    # ---- channel 33 eta sweep <- residual.threshold_sweep ---------------
    # Also recomputed rather than read. The displayed eta grid is the one
    # the chapter prints; the pinned default grid is a different one, so
    # the grid itself is an input this check fixes.
    ck.section("Channel 33 eta sweep <- residual.threshold_sweep (products)")
    sweep = eta_sweep_ch33()
    if sweep is None:
        ck.skip("channel 33 eta sweep",
                "set RFISHER_PRODUCT_DIRS to the archive per-pilot products")
    else:
        # 'masked fraction f' also heads a column of the flagger table, so
        # every row here is scoped past this sweep's own header.
        head = "\\eta & 1 (floor)"
        # The grid is an input, not an output: the values below are computed
        # at the etas this gate sweeps, so the header has to still name them
        # or the rows would be right about the wrong thing.
        header = table_row_cells(ck.text, "\\eta &")
        printed_etas = [c.split()[0] for c in (header or [])[:len(sweep)]
                        if c.split()]
        want_etas = [f"{float(r['eta']):g}" for r in sweep]
        ck._emit(
            "PASS" if printed_etas == want_etas else "FAIL",
            "ch33 sweep header lists the swept etas",
            "" if printed_etas == want_etas else
            f"header reads {printed_etas} but the rows are computed at"
            f" {want_etas}; keep the two in step")
        check_row(ck, "ch33 sweep masked fraction row",
                  "masked fraction f",
                  [float(r["f"]) for r in sweep],
                  "recompute with threshold_sweep f", after=head)
        check_row(ck, "ch33 sweep kept-frame shelf row",
                  "kept-frame shelf (dB)",
                  [float(r["kept_shelf_db"]) for r in sweep],
                  "recompute with threshold_sweep kept_shelf_db",
                  after=head)
        check_row(ck, "ch33 sweep residual row", "residual r_{\\rm proxy}",
                  [float(r["r_masked"]) for r in sweep],
                  "recompute with threshold_sweep r_masked", after=head)
        if summary:
            r_tol = float(summary["bao_policy_case"]["residual_tolerance"])
            check_row(ck, "ch33 sweep residual over tolerance row",
                      "r_{\\rm proxy}/r_{\\text{tol}}",
                      [float(r["r_masked"]) / r_tol for r in sweep],
                      "recompute as r_masked / bao_policy_case"
                      ".residual_tolerance", after=head)
        else:
            ck.skip("ch33 sweep residual over tolerance row",
                    "pass --summary-json for the pinned residual tolerance")

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
                         "dissertation_summary_v3.json (policy invariants"
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
