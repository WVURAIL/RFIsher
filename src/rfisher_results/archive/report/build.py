"""The report of one archive run: every table fragment and figure, one manifest.

``build_report(results_dir, out_dir)`` loads the ledger, renders every
registered table builder into ``out_dir/tables`` with its ``numbers.json``,
renders the figures into ``out_dir/figures`` (each figure module exposes
``render(run, out_dir) -> [paths]`` and, where it prints numbers, a
``build(run) -> Fragment``), and writes ``export_manifest.json``. A module
registers its builders as ``BUILDERS`` (a tuple of ``build(run)`` callables)
or a single ``build``. Modules are imported lazily so a missing optional
dependency (matplotlib for the figures) disables only what needs it.
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Callable, Sequence

from .core import Fragment, Run, load_run, write_report

TABLE_MODULES: tuple[str, ...] = (
    "calibration_eras", "calibration_anchors", "calibration_nulls", "blocked_evaluation", "held_out_summary",
    "tolerance_eta", "tolerance_channels", "conclusions_matrix", "handover", "flagger_survey",
)
FIGURE_MODULES: tuple[str, ...] = ("figures_status", "figures_two_walls", "figures_census_psd",
                                   "figures_masking_cost")


def _module(name: str):
    return importlib.import_module(f"{__package__}.{name}")


def table_builders(modules: Sequence[str] = TABLE_MODULES) -> list[Callable[[Run], Fragment]]:
    """Every table builder, in the registry's order."""
    out: list[Callable[[Run], Fragment]] = []
    for name in modules:
        mod = _module(name)
        builders = getattr(mod, "BUILDERS", None) or (mod.build,)
        out.extend(builders)
    return out


def build_report(results_dir: Path | str, out_dir: Path | str | None = None, *, commit: str | None = None,
                 generated: str | None = None, figures: bool = True, modules: Sequence[str] = TABLE_MODULES,
                 figure_modules: Sequence[str] = FIGURE_MODULES, require_tex: bool = True) -> dict:
    """Render tables, numbers and figures for one run; return the manifest.

    ``require_tex`` is the document's typography contract: the figures are set
    in Latin Modern through LaTeX, which the dissertation's figure audit
    enforces. Pass ``False`` only for a preview on a machine without a TeX
    installation, and never for a report that will be vendored.
    """
    import datetime as dt

    run = load_run(results_dir)
    out = Path(out_dir) if out_dir is not None else run.results_dir / "dissertation"
    commit = commit or run.commit
    generated = generated or dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    builders = table_builders(modules)
    extra: list[Path] = []
    if figures:
        # the document's own style, Latin Modern through LaTeX: the figure audit refuses a
        # substituted font, so a report rendered without it cannot be vendored
        from ... import style

        style.configure(require_tex=require_tex)
        fig_dir = out / "figures"
        fig_dir.mkdir(parents=True, exist_ok=True)
        for name in figure_modules:
            mod = _module(name)
            extra.extend(Path(p) for p in mod.render(run, fig_dir))
            if hasattr(mod, "build"):
                builders.append(mod.build)
    return write_report(run, out, builders, commit=commit, generated=generated, extra_artifacts=extra)
