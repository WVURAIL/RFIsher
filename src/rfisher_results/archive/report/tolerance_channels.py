"""``tab:tolerance:channels``: the scalar residual chain, term by term, for every
channel on its current era at its operating point (chapter 9, "Channel
Verdicts"), and its evidence ledger for Appendix C.

Two fragments, one row per channel 14--36 in each, keyed alike.

``tolerance_channels`` (``tab:tolerance:channels``) is the chapter table and
prints exactly the short columns the chapter's stub names: allocation, the
redshift span, the current era, the flag rate and the masked fraction at the
point, the kept-frame floor, the tau_c outcome, the residual at the point and
its two tolerance ratios, and the screening class. Twelve columns in one
booktabs ``tabular``, natural width 712pt at the dissertation's 11pt: the
chapter wraps it in ``sidewaystable`` (``rotating``), where it fits the 650pt
sideways line at ``\\footnotesize`` unscaled (625pt) or at ``\\resizebox``
scale 0.91 upright. A ``\\midrule`` after channel 25 marks the half-band
break (14--25 / 26--36) so the two halves read as blocks without being
separate tables. No panel stacking is needed: trimming to the stub's columns
reaches the target on its own, and both fragments are single tabulars.

``tolerance_channels_ledger`` (``tab:archive:tolerance_channels``) is the
companion the stub sends to Appendix~C beside the channel's plate --- "the
term-by-term evidence ledger behind each row ... rather than into a 23-column
table". Same one-row-per-channel shape, seven columns: the monitored bin and
the chain terms behind the residual (on-air shelf, null frames, intra-day
share, ground filter) with the keep-everything residual the mask is measured
against. Natural width 349pt: it sets upright inside the 469.8pt text block
unscaled. Every number keeps its ``ch09.channels.*`` key; only which fragment
prints it moved.

Range and label cells are text mode; single numbers are math mode (minus
signs, ``{,}`` thousands groups). An absent or undefined value prints as
``--`` and the fragment's notes say why.

Chapter columns (ledger ``section.key``):

    ch          channel number
    alloc (MHz) geometry.allocation_low_mhz--allocation_high_mhz, whole MHz
    z           tolerance.z_low--z_high, three decimals
    era         era.current_first_month--era.current_last_month (the current
                era, the off era itself on an off-era channel)
    flag        screening.survey_flag_rate_era, the occupancy indicator
    f           the masked fraction at the row's point (see *point* below) on
                the calibration block: selection.masked_fraction_calibration
                for a selected point, selection.diagnostic_masked_fraction for
                the least-residual diagnostic point, the latter marked with a
                dagger; the mark sits on f alone because r_proxy, R_dil and
                R_fs8 share the row's point (and may carry an exponent)
    floor (dB)  null.floor_db, the kept-frame floor: unmarked when
                null.floor_evidence is ``measured`` (null.floor_basis ``off
                era p90``), marked ``s`` when ``stated`` (the sigma-implied
                substitute: floor_basis ``kept half about mu_0`` or ``bulk
                left side (not H0)``), the dash when ``refused`` (floor_basis
                ``none``: the block carries no null population)
    tau_c (min) chain.tau_quality with chain.tau_c_minutes (three significant
                figures) when ``measured``, ``<= chain.tau_c_high_minutes``
                when ``bounded_above``, and the word ``cap`` when ``refused``
                (the chain is then booked at the sidereal-day cap,
                chain.chain_gain, and takes no ground-filter credit; the
                intra-day share and filter columns of the ledger are
                description there)
    r_proxy     the kept-frame residual at the point:
                selection.r_sys_calibration | selection.diagnostic_r_sys
    R_dil       R = r_proxy / r_tol on the stable dilation tier of the
                channel's bin (R <= 1 passes):
                selection.R_calibration | selection.diagnostic_R (min_R)
    R_fs8       r_proxy / tolerance.r_tol_fs8 where tolerance.fs8_status is
                ``published``; the word ``unpriced`` otherwise
    class       screening.screening_class, abbreviated: ``recovery
                candidate``; ``bound: floor`` (measurement-bound on floor);
                ``bound: tau_c`` (measurement-bound on tau_c); ``occupancy
                wall`` (occupancy-wall excision candidate); ``off-era``

Ledger columns (Appendix C):

    ch          channel number
    bin (MHz)   geometry.pilot_hz / 1e6, three decimals (the monitored bin)
    shelf (dB)  chain.on_shelf_db, the on-air shelf of the era chain
    N_null      null.coarse_frames, frames in the coarse null population of
                the calibration block (the off population where one exists)
    rho_intra   chain.intraday_share
    filter (dB) chain.ground_filter_db
    r_keep      selection.keep_everything_r_sys_calibration, the
                keep-everything residual on the calibration block (the block
                the point was chosen on; selection.r_sys_unmasked_calibration
                is read on a ledger without the new key)

The point. When the selector returned a point (selection.status ``feasible``
with claim_status ``screening`` or ``operational``) f, r_proxy and R_dil are
the selector's calibration-block values. When the within-era drift screen
refused the channel (claim_status ``diagnostic``, status ``no feasible
point``) there is no selected point, and the three cells are the
least-residual point of the calibration surface, selection.diagnostic_*
(selection.min_r_sys_* on an older ledger), replayed on the evaluation block
elsewhere in the ledger but printed here on the block it was found on, with f
marked by a dagger. When the selector refused outright (status ``refused``:
frames without a shelf estimate and no floor) the point, r_keep, r_proxy and
both R cells are dashes. Every channel of the 2026-09-07 run is diagnostic or
refused; none is selected.

The chain. Shelf, intra-day share, filter and tau_c are the era chain
(section ``chain``, evaluated on the current era, or on the previous on era
where the current era is a transmitter-off era: chain.chain_population says
which); the archive-wide chain is recorded beside it in ``chain_archive`` and
is not printed. selection.gain_basis says which chain priced the residual
(``era chain`` on every channel of the run); a row priced on the archive-wide
chain is named in the notes. Only the tau_c outcome stays in the chapter
table, because it is the column that turns a residual into a bound; the three
terms behind it are the ledger's.

Numbers. ``ch09.channels.<column>.chNN`` per cell, unchanged by the split:
the chapter fragment carries allocation_low_mhz, allocation_high_mhz, z_low,
z_high, era_first_month, era_last_month, flag_rate, point_basis,
masked_fraction, floor_db, floor_evidence, tau_quality, tau_c_minutes,
r_proxy, R_dilation, R_fs8 and screening_class, and the ledger fragment
pilot_mhz, on_shelf_db, chain_basis, null_frames, intraday_share,
ground_filter_db and r_keep. The band-level counts ``ch09.channels.<name>``
(n_channels, n_point_selected, n_point_diagnostic, n_floor_measured,
n_floor_stated, n_floor_refused, n_tau_measured, n_tau_bounded,
n_tau_refused, n_fs8_priced, n_off_era) stay with the chapter fragment.
Residuals and ratios print to three significant figures, in
``a.bc\\times10^{n}`` form outside [0.01, 1000); their renderings carry the
printed form. r_keep, r_proxy and both R values carry status ``bounded``
where tau_c is not measured (the chain is an upper bound at the cap or at the
one-sided tau_c bound).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import core
from .core import DASH, Channel, Fragment, Run

NAME = "tolerance_channels"
LABEL = "tab:tolerance:channels"
LEDGER_NAME = "tolerance_channels_ledger"
LEDGER_LABEL = "tab:archive:tolerance_channels"
KEY = "ch09.channels"                # both fragments key their numbers alike
HALF_BAND_BREAK = 25                 # the midrule falls after this channel
DAGGER = "\\dagger"                  # the diagnostic point's mark, on f
STATED = "\\mathrm{s}"               # the stated floor's mark

HEADER = ("ch", "alloc.\\ (MHz)", "$z$", "era", "flag", "$f$", "floor (dB)", "$\\tau_c$ (min)", "$r_{\\rm proxy}$",
          "$R_{\\rm dil}$", "$R_{f\\sigma_8}$", "class")
ALIGN = "lccc" + "r" * 7 + "l"

LEDGER_HEADER = ("ch", "bin (MHz)", "shelf (dB)", "$N_{\\rm null}$", "$\\rho_{\\rm intra}$", "filter (dB)",
                 "$r_{\\rm keep}$")
LEDGER_ALIGN = "l" + "r" * 6

CLASS_ABBREV = {"recovery candidate": "recovery candidate", "measurement-bound on floor": "bound: floor",
                "measurement-bound on tau_c": "bound: $\\tau_c$", "occupancy-wall excision candidate": "occupancy wall",
                "off-era": "off-era"}
SELECTED_STATUS = ("screening", "operational")
ERA_CHAIN = "era chain"


# ------------------------------------------------------------------ cells
def _finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _decimals(text: str) -> int | None:
    """The decimals a printed plain number carries; None for the exponent form."""
    if "\\times" in text:
        return None
    return len(text.split(".", 1)[1]) if "." in text else 0


def sci(value, digits: int = 3, *, dash: str = DASH) -> str:
    """``digits`` significant figures; ``a.bc\\times10^{n}`` outside [0.01, 1000). Math mode is the caller's."""
    if not _finite(value):
        return dash
    x = float(value)
    if x == 0.0:
        return "0"
    if 1e-2 <= abs(x) < 1e3:
        text = core.fmt(x, digits, sig=True)
        if "." in text or len(text.lstrip("-")) <= digits:    # 999.6 rounds to 1000: use the exponent form
            return text
    exp = int(math.floor(math.log10(abs(x))))
    mantissa = core.fmt(x / 10 ** exp, digits, sig=True)
    if abs(float(mantissa)) >= 10.0:          # rounding carried the mantissa to 10: it is exactly 1 one decade up
        exp += 1
        mantissa = core.fmt(math.copysign(1.0, x), digits, sig=True)
    return f"{mantissa}\\times10^{{{exp}}}"


def minutes(value, dash: str = DASH) -> str:
    """A correlation time in minutes to three significant figures, trailing zeros dropped (5.00 -> 5)."""
    if not _finite(value):
        return dash
    text = core.fmt(value, 3, sig=True)
    return text.rstrip("0").rstrip(".") if "." in text else text


def _render(text: str) -> str:
    """The number gate's normal form of a printed cell (``\\times`` -> ``x``)."""
    return text.replace("\\times", "x")


def _math(text: str, mark: str = "") -> str:
    """Wrap a formatted number in math mode with an optional superscript mark; the dash stays in text mode."""
    if text == DASH:
        return DASH
    return f"${{{text}}}^{{{mark}}}$" if mark else f"${text}$"   # braces: the base may carry its own exponent


@dataclass(frozen=True)
class Point:
    """The operating point a row prints: ``selected``, the least-residual ``diagnostic`` point, or ``absent``."""

    basis: str
    masked_fraction: object = None
    r_proxy: object = None
    R: object = None
    why: str = ""                 # why the point is absent

    @property
    def diagnostic(self) -> bool:
        return self.basis == "diagnostic"


def point(channel: Channel) -> Point:
    """The channel's point on the calibration block (see the module docstring)."""
    sel = channel.selection
    if not sel:
        return Point("absent", why="no selection section")
    if sel.get("status") == "feasible" and sel.get("claim_status") in SELECTED_STATUS and sel.get("rho") is not None:
        return Point("selected", sel.get("masked_fraction_calibration"), sel.get("r_sys_calibration"), sel.get("R_calibration"))
    r_diag = sel.get("diagnostic_r_sys")
    if _finite(r_diag):
        R = sel.get("diagnostic_R")
        return Point("diagnostic", sel.get("diagnostic_masked_fraction"), r_diag, R if _finite(R) else sel.get("min_R"))
    if _finite(sel.get("min_r_sys")):       # a ledger before the diagnostic_* keys
        return Point("diagnostic", sel.get("min_r_sys_masked_fraction"), sel.get("min_r_sys"), sel.get("min_R"))
    status = str(sel.get("status") or "")
    if status == "refused":
        return Point("absent", why=f"selector refused: {sel.get('refusal') or 'no reason recorded'}")
    return Point("absent", why=f"selection status {status or 'unknown'!r} with no evaluated surface")


def tau_cell(chain) -> tuple[str, str, object, str]:
    """``(cell, quality, minutes, status)`` for the tau_c outcome column."""
    quality = str(chain.get("tau_quality", "") or "")
    if quality == "measured" and _finite(chain.get("tau_c_minutes")):
        return _math(minutes(chain["tau_c_minutes"])), quality, chain["tau_c_minutes"], "measured"
    if quality == "bounded_above":
        bound = chain.get("tau_c_high_minutes")
        bound = bound if _finite(bound) else chain.get("tau_c_minutes")
        if _finite(bound):
            return f"$\\le {minutes(bound)}$", quality, bound, "bounded"
        return DASH, quality, None, "bounded"
    if quality == "refused":
        return "cap", quality, None, "refused"
    return DASH, quality, None, "pending"


def chain_basis(channel: Channel) -> tuple[str, str]:
    """``('previous era' | 'current era' | '', chain.chain_population)``: the era the chain was evaluated on."""
    population = str(channel.chain.get("chain_population", "") or "")
    if not channel.has("chain"):
        return "", population
    if population.startswith("previous era") or bool(channel.era.get("off_era_current")):
        return "previous era", population
    return "current era", population


def _bounded(channel: Channel) -> bool:
    """The chain is an upper bound (at the cap or the one-sided tau_c bound) unless tau_c is measured."""
    return str(channel.chain.get("tau_quality", "") or "") != "measured"


def _cell_writer(channel: Channel, frag: Fragment, absent: list[str]):
    """``(add, gap)``: emit one cell's number, or record why the cell is a dash."""
    ch = channel.channel
    row = {"channel": ch}

    def add(column: str, value, **kw):
        frag.add(f"{KEY}.{column}.ch{ch}", value, row=row, column=column, **kw)

    def gap(column: str, why: str, *, status: str = "pending", rendering: str = DASH):
        absent.append(f"ch{ch} {column}: {why}")
        add(column, None, kind="text", status=status, renderings=(rendering,))

    return add, gap


# ------------------------------------------------------------------ rows
def _row(c: Channel, frag: Fragment, absent: list[str]) -> list[str]:
    """The chapter table's row: the stub's short columns (the chain terms are the ledger's)."""
    era, null, tol, sel, scr = c.era, c.null, c.tolerance, c.selection, c.screening
    geo = c.section("geometry")
    add, gap = _cell_writer(c, frag, absent)
    cells = [str(c.channel)]

    # allocation
    lo, hi = geo.get("allocation_low_mhz"), geo.get("allocation_high_mhz")
    cells.append(core.fmt_range(lo, hi, 0))
    if _finite(lo) and _finite(hi):
        add("allocation_low_mhz", lo, precision=0)
        add("allocation_high_mhz", hi, precision=0)
    else:
        gap("allocation_low_mhz", "geometry.allocation_low_mhz/high_mhz absent")
        add("allocation_high_mhz", None, kind="text", renderings=(DASH,))

    # redshift span
    zl, zh = tol.get("z_low"), tol.get("z_high")
    cells.append(core.fmt_range(zl, zh, 3))
    if _finite(zl) and _finite(zh):
        add("z_low", zl, precision=3)
        add("z_high", zh, precision=3)
    else:
        gap("z_low", "tolerance.z_low/z_high absent (no tolerance section)")
        add("z_high", None, kind="text", renderings=(DASH,))

    # current era
    first, last = era.get("current_first_month"), era.get("current_last_month")
    if first and last:
        cells.append(f"{core.fmt_month(first)}--{core.fmt_month(last)}")
        add("era_first_month", str(first), kind="text", renderings=(str(first),))
        add("era_last_month", str(last), kind="text", renderings=(str(last),))
    else:
        cells.append(DASH)
        gap("era_first_month", "era.current_first_month/current_last_month absent")
        add("era_last_month", None, kind="text", renderings=(DASH,))

    # flag rate
    flag = scr.get("survey_flag_rate_era")
    cells.append(_math(core.fmt(flag, 3)))
    if _finite(flag):
        add("flag_rate", flag, precision=3)
    else:
        gap("flag_rate", "screening.survey_flag_rate_era absent")

    # the point: masked fraction now, r_proxy and R below
    pt = point(c)
    bounded = _bounded(c)
    residual_status = "bounded" if bounded else ("measured" if pt.basis == "selected" else "derived")
    add("point_basis", pt.basis, kind="text", renderings=(pt.basis,), status="measured" if pt.basis == "selected" else "derived")
    cells.append(_math(core.fmt(pt.masked_fraction, 3), DAGGER if pt.diagnostic else ""))
    if _finite(pt.masked_fraction):
        add("masked_fraction", pt.masked_fraction, precision=3, status="measured" if pt.basis == "selected" else "derived")
    else:
        gap("masked_fraction", pt.why if pt.basis == "absent" else "masked fraction undefined at the point",
            status="refused" if sel.get("status") == "refused" else "pending")

    # the kept-frame floor
    floor, evidence = null.get("floor_db"), str(null.get("floor_evidence", "") or "")
    floor_basis = str(null.get("floor_basis", "") or "")
    if _finite(floor):
        cells.append(_math(core.fmt(floor, 1), STATED if evidence == "stated" else ""))
        add("floor_db", floor, precision=1, status="measured" if evidence == "measured" else "derived")
        add("floor_evidence", evidence or "unknown", kind="text",
            renderings=(evidence or DASH,) + ((floor_basis,) if floor_basis else ()))
    elif evidence == "refused":
        cells.append(DASH)
        absent.append(f"ch{c.channel} floor_db: floor refused ({null.get('floor_population') or 'no reason recorded'})")
        add("floor_db", None, kind="text", status="refused", renderings=(DASH,))
        add("floor_evidence", "refused", kind="text", status="refused", renderings=("refused",))
    else:
        cells.append(DASH)
        gap("floor_db", "null.floor_db absent" + ("" if c.has("null") else " (no null section)"))
        add("floor_evidence", None, kind="text", renderings=(DASH,))

    # the tau_c outcome (the chain terms behind it are the ledger's)
    cell, quality, tau_minutes, status = tau_cell(c.chain)
    cells.append(cell)
    add("tau_quality", quality or None, kind="text", renderings=(quality or DASH,), status=status)
    if _finite(tau_minutes):
        add("tau_c_minutes", tau_minutes, precision=_decimals(minutes(tau_minutes)), status=status,
            renderings=(minutes(tau_minutes),))
    elif quality == "refused":
        add("tau_c_minutes", None, kind="text", status="refused", renderings=("cap",))
    else:
        gap("tau_c_minutes", "chain.tau_quality absent or carries no minutes", status=status)

    # residuals at the point
    cells.append(_math(sci(pt.r_proxy)))
    if _finite(pt.r_proxy):
        add("r_proxy", pt.r_proxy, precision=_decimals(sci(pt.r_proxy)), renderings=(_render(sci(pt.r_proxy)),),
            status=residual_status)
    else:
        gap("r_proxy", pt.why if pt.basis == "absent" else "residual undefined at the point",
            status="refused" if sel.get("status") == "refused" else "pending")

    cells.append(_math(sci(pt.R)))
    if _finite(pt.R):
        add("R_dilation", pt.R, precision=_decimals(sci(pt.R)), renderings=(_render(sci(pt.R)),), status=residual_status)
    else:
        gap("R_dilation", pt.why if pt.basis == "absent" else "R undefined at the point (r_tol absent)",
            status="refused" if sel.get("status") == "refused" else "pending")

    fs8_tol, fs8_status = tol.get("r_tol_fs8"), str(tol.get("fs8_status", "") or "")
    if fs8_status == "published" and _finite(fs8_tol) and float(fs8_tol) > 0 and _finite(pt.r_proxy):
        r_fs8 = float(pt.r_proxy) / float(fs8_tol)
        cells.append(_math(sci(r_fs8)))
        add("R_fs8", r_fs8, precision=_decimals(sci(r_fs8)), renderings=(_render(sci(r_fs8)),), status=residual_status)
    elif fs8_status.startswith("unpriced") or (fs8_status and not _finite(fs8_tol)):
        cells.append("unpriced")
        add("R_fs8", None, kind="text", status="pending", renderings=("unpriced",))
    elif not fs8_status:
        cells.append(DASH)
        gap("R_fs8", "tolerance.fs8_status absent (no tolerance section)")
    else:
        cells.append(DASH)
        gap("R_fs8", "f sigma_8 tolerance published but r_proxy undefined: " + (pt.why or "residual undefined at the point"),
            status="refused" if sel.get("status") == "refused" else "pending")

    # screening class
    cls = str(scr.get("screening_class", "") or "")
    if cls:
        cells.append(CLASS_ABBREV.get(cls, core.tex(cls)))
        add("screening_class", cls, kind="text", renderings=(cls, CLASS_ABBREV.get(cls, cls).replace("$\\tau_c$", "tau_c")))
    else:
        cells.append(DASH)
        gap("screening_class", "screening.screening_class absent")
    return cells


def _ledger_row(c: Channel, frag: Fragment, absent: list[str]) -> list[str]:
    """The Appendix C companion's row: the monitored bin and the chain terms behind the residual."""
    chain, null, sel = c.chain, c.null, c.selection
    geo = c.section("geometry")
    add, gap = _cell_writer(c, frag, absent)
    cells = [str(c.channel)]

    # monitored bin
    pilot = geo.get("pilot_hz")
    if _finite(pilot):
        mhz = float(pilot) / 1e6
        cells.append(_math(core.fmt(mhz, 3)))
        add("pilot_mhz", mhz, precision=3)
    else:
        cells.append(DASH)
        gap("pilot_mhz", "geometry.pilot_hz absent")

    # the era chain: shelf, null population, share, filter
    shelf = chain.get("on_shelf_db")
    cells.append(_math(core.fmt(shelf, 1)))
    if _finite(shelf):
        add("on_shelf_db", shelf, precision=1)
    else:
        gap("on_shelf_db", "chain.on_shelf_db absent" + ("" if c.has("chain") else " (no chain section)"))
    basis, population = chain_basis(c)
    if basis:
        add("chain_basis", basis, kind="text", renderings=(basis, population) if population else (basis,))
    else:
        add("chain_basis", None, kind="text", status="pending", renderings=(DASH,))

    frames = null.get("coarse_frames")
    cells.append(_math(core.fmt_int(frames)))
    if _finite(frames):
        add("null_frames", int(round(float(frames))), kind="int")
    else:
        gap("null_frames", "null.coarse_frames absent" + ("" if c.has("null") else " (no null section)"))

    share = chain.get("intraday_share")
    cells.append(_math(core.fmt(share, 3)))
    if _finite(share):
        add("intraday_share", share, precision=3)
    else:
        gap("intraday_share", "chain.intraday_share absent")

    gfilter = chain.get("ground_filter_db")
    cells.append(_math(core.fmt(gfilter, 1)))
    if _finite(gfilter):
        add("ground_filter_db", gfilter, precision=1)
    else:
        gap("ground_filter_db", "chain.ground_filter_db absent")

    # the keep-everything residual the mask is measured against
    r_keep = sel.get("keep_everything_r_sys_calibration", sel.get("r_sys_unmasked_calibration"))
    cells.append(_math(sci(r_keep)))
    if _finite(r_keep):
        add("r_keep", r_keep, precision=_decimals(sci(r_keep)), renderings=(_render(sci(r_keep)),),
            status="bounded" if _bounded(c) else "measured")
    else:
        pt = point(c)
        if pt.basis == "absent" and sel:
            gap("r_keep", pt.why, status="refused" if sel.get("status") == "refused" else "pending")
        else:
            gap("r_keep", "selection.keep_everything_r_sys_calibration absent" + ("" if sel else " (no selection section)"))
    return cells


def _channel_list(channels) -> str:
    return ", ".join(f"ch{c}" for c in channels) if channels else "none"


def _half_band_breaks(channels) -> list[int]:
    return [i for i, c in enumerate(channels) if i > 0 and channels[i - 1].channel <= HALF_BAND_BREAK < c.channel]


def build(run: Run) -> Fragment:
    """``tab:tolerance:channels``: the chapter table, the stub's short columns only."""
    frag = Fragment(NAME, LABEL, "")
    absent: list[str] = []
    channels = sorted(run.channels, key=lambda c: c.channel)
    rows = [_row(c, frag, absent) for c in channels]
    frag.tex = core.booktabs(HEADER, rows, ALIGN, midrules=_half_band_breaks(channels))

    # band-level counts, and what the marks mean on this run
    def which(pred) -> list[int]:
        return [c.channel for c in channels if pred(c)]

    n = len(channels)
    points = {c.channel: point(c) for c in channels}
    selected = [ch for ch, p in points.items() if p.basis == "selected"]
    diagnostic = [ch for ch, p in points.items() if p.diagnostic]
    no_point = [ch for ch, p in points.items() if p.basis == "absent"]
    floors = {e: which(lambda c, e=e: c.null.get("floor_evidence") == e) for e in ("measured", "stated", "refused")}
    taus = {q: which(lambda c, q=q: c.chain.get("tau_quality") == q) for q in ("measured", "bounded_above", "refused")}
    fs8 = which(lambda c: c.tolerance.get("fs8_status") == "published")
    off_era = which(lambda c: chain_basis(c)[0] == "previous era")
    archive_gain = which(lambda c: c.selection and str(c.selection.get("gain_basis", ERA_CHAIN) or ERA_CHAIN) != ERA_CHAIN)
    for key, value in (("n_channels", n), ("n_point_selected", len(selected)), ("n_point_diagnostic", len(diagnostic)),
                       ("n_floor_measured", len(floors["measured"])), ("n_floor_stated", len(floors["stated"])),
                       ("n_floor_refused", len(floors["refused"])), ("n_tau_measured", len(taus["measured"])),
                       ("n_tau_bounded", len(taus["bounded_above"])), ("n_tau_refused", len(taus["refused"])),
                       ("n_fs8_priced", len(fs8)), ("n_off_era", len(off_era))):
        frag.add(f"{KEY}.{key}", value, kind="int", status="derived", column=key)

    frag.notes.append(f"layout: one {len(HEADER)}-column tabular, the short columns of the chapter's stub, natural width "
                      "712pt at 11pt; it is a sidewaystable (rotating), fitting the 650pt sideways line at footnotesize "
                      f"unscaled (625pt) or upright at resizebox scale 0.91; the midrule after channel {HALF_BAND_BREAK} is "
                      "the half-band break; one tabular, no panel split needed")
    frag.notes.append(f"the term-by-term evidence ledger behind each row is the companion fragment {LEDGER_NAME} "
                      f"({LEDGER_LABEL}, Appendix C, beside the channel's plate): the monitored bin, the on-air shelf, the "
                      "null frames, the intra-day share, the ground filter and r_keep, one row per channel, same keys")
    frag.notes.append(f"point: f, r_proxy, R_dil and R_fs8 are on the calibration block; {len(selected)} of {n} channels "
                      f"carry a selected operating point ({_channel_list(selected)}); {len(diagnostic)} print the "
                      "least-residual diagnostic point of the calibration surface (selection.diagnostic_*: the within-era "
                      f"drift screen refused, no feasible point), with f marked by a dagger; {len(no_point)} have no point "
                      f"at all and print dashes ({_channel_list(no_point)}: the selector refused)")
    frag.notes.append("chain: the tau_c outcome is the era chain (chain.*), evaluated on the current era, or on the previous "
                      f"on era where the current era is a transmitter-off era ({_channel_list(off_era)}); the archive-wide "
                      "chain (chain_archive) is recorded beside it and not printed")
    if archive_gain:
        frag.notes.append(f"gain basis: the residual is priced on the archive-wide chain (era chain refused) on {_channel_list(archive_gain)}")
    else:
        frag.notes.append("gain basis: every residual is priced on the era chain (selection.gain_basis)")
    frag.notes.append(f"floor: measured (the verified off era's 90th-percentile shelf) on {len(floors['measured'])} channels "
                      f"({_channel_list(floors['measured'])}), unmarked; stated (sigma-implied substitute: kept half about mu_0 "
                      f"or the bulk's left side) on {len(floors['stated'])}, marked s; refused (no null population) on "
                      f"{len(floors['refused'])} ({_channel_list(floors['refused'])}), dashed")
    unfloored = [ch for ch in floors["refused"] if points[ch].basis != "absent"]
    if unfloored:
        frag.notes.append(f"floor refused beside a point on {_channel_list(unfloored)}: every calibration frame there carries "
                          "a shelf estimate, so the residual is the shelf alone with no floor term (the selector refuses only "
                          "where a frame without a shelf estimate would need the floor)")
    frag.notes.append(f"tau_c: measured on {len(taus['measured'])} ({_channel_list(taus['measured'])}), bounded above on "
                      f"{len(taus['bounded_above'])} ({_channel_list(taus['bounded_above'])}: one-sided bound printed), refused "
                      f"on {len(taus['refused'])} (printed cap: chain booked at the sidereal-day cap, no ground-filter credit; "
                      "the ledger's intra-day share and filter are description on those rows); r_keep, r_proxy and R are upper "
                      "bounds wherever tau_c is not measured")
    frag.notes.append(f"R_fs8: priced on {len(fs8)} channels ({_channel_list(fs8)}); unpriced where no published f sigma_8 "
                      "constant exists for the bin")
    frag.notes.extend(f"dashed: {why}" for why in absent)
    return frag


def build_ledger(run: Run) -> Fragment:
    """``tab:archive:tolerance_channels``: the chapter table's evidence ledger, for Appendix C."""
    frag = Fragment(LEDGER_NAME, LEDGER_LABEL, "")
    absent: list[str] = []
    channels = sorted(run.channels, key=lambda c: c.channel)
    rows = [_ledger_row(c, frag, absent) for c in channels]
    frag.tex = core.booktabs(LEDGER_HEADER, rows, LEDGER_ALIGN, midrules=_half_band_breaks(channels))
    off_era = [c.channel for c in channels if chain_basis(c)[0] == "previous era"]
    capped = [c.channel for c in channels if str(c.chain.get("tau_quality", "") or "") == "refused"]

    frag.notes.append(f"layout: one {len(LEDGER_HEADER)}-column tabular, one row per channel, keyed to "
                      f"{LABEL} row for row; natural width 349pt at 11pt, upright inside the 469.8pt text block "
                      f"unscaled; the midrule after channel {HALF_BAND_BREAK} is the half-band break; one tabular, no "
                      "panel split needed")
    frag.notes.append(f"the term-by-term evidence behind {LABEL} (chapter 9): the columns the chapter's stub sends to "
                      "Appendix C beside the channel's plate rather than into a 23-column table; the verdict columns "
                      "(masked fraction, floor, tau_c outcome, residual and its two ratios, screening class) stay in the "
                      "chapter table and are not repeated here")
    frag.notes.append("chain: shelf, intra-day share and filter are the era chain (chain.*), evaluated on the current era, or "
                      f"on the previous on era where the current era is a transmitter-off era ({_channel_list(off_era)}: "
                      "chain.chain_population, recorded as chain_basis); the archive-wide chain (chain_archive) is recorded "
                      "beside it and not printed")
    if capped:
        frag.notes.append(f"intra-day share and ground filter are measured description, not applied credit, on the cap "
                          f"channels ({_channel_list(capped)}): where tau_c is refused the chain is booked at the "
                          "sidereal-day cap and takes no ground-filter credit")
    frag.notes.append("N_null is the coarse null population of the calibration block (the off population where one exists); "
                      "r_keep is the keep-everything residual on the same block (selection.keep_everything_r_sys_calibration), "
                      f"an upper bound wherever tau_c is not measured ({LABEL} carries the outcome)")
    frag.notes.extend(f"dashed: {why}" for why in absent)
    return frag


BUILDERS = (build, build_ledger)
