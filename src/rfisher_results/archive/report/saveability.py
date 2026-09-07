r"""``tab:tolerance:saveability``: which channels could be recovered, and by what.

Chapter 9's verdicts are per parameter, and the parameters do not fail
together. The growth rate is the tightest constraint in every bin; the two
dilations tolerate about an order of magnitude more. A channel can therefore
be out of reach for $f\sigma_8$ and inside reach for $\alpha_\perp$ and
$\alpha_\parallel$, and a table that reports only "fails" hides that
difference. This fragment sorts the band into what each channel would take.

Four tiers, each the weakest instrument that reaches it:

``growth``      some delay-cut world puts $R_{f\sigma_8} \le 1$. The growth
                rate is the binding parameter, so a channel that reaches it
                reaches everything.
``dilation``    some world puts both dilation ratios at or under 1 while the
                growth rate stays out. The channel is usable for the
                distance scale and not for the growth rate.
``cadence``     nothing reaches 1 as booked, but the residual is booked at
                the sidereal-day cap because the correlation time was
                refused, and a timescale the band actually exhibits would
                bring it inside. This is a *what-if*, in the sense
                :func:`rfisher.residual.surviving_components` fixes: a sub-cap
                timescale assumed on a refused channel books all shelf power
                at that timescale and restores no ground-filter credit. It
                says a contiguous-cadence campaign is worth running on the
                channel, not that the channel passes.
``none``        no world, and no attainable timescale, brings any parameter
                under 1.

A channel with no operating point, or none whose bins the stability gate
accepted, is ``no verdict`` and is counted separately: it is an absent
measurement, not a failure.

What a tier does not mean. ``R \le 1`` is already the loose test. At the
adopted ``zeta = 1`` convention it permits the induced systematic to equal the
entire statistical error on the parameter, so a channel outside it is not
marginal, and a channel outside it by orders of magnitude is not close to
anything. The tiers say what would have to change for a channel to come
inside, not how near it already is.

The cadence test is a number, not a guess. Every capped channel is quoted the
correlation time that *would* bring its best world to ``R = 1``: the cap
divided by that ratio, since a refusal books all power at one timescale and
the residual scales with it alone. The channel takes the ``cadence`` tier only
where that required time is at least the shortest timescale the band itself
exhibits -- the most favourable assumption its own evidence supports. A
required time below that is reported all the same, and it is the honest way to
say the cap is not what is wrong with the channel.

Whether the era represents the future. Every verdict is read on the
channel's current era, which is the right basis only where that era describes
what the channel will keep doing. Two ledger facts say it may not: an era
that is itself a transmitter-off era prices a dead carrier, and an
unconfirmed instrument change in the last month means the era has not settled.
Both are marked in their own column and neither changes a tier -- the tier is
what the evidence says, the mark is how far the evidence carries.

Numbers: ``ch09.saveability.<column>.chNN`` per cell, ``ch09.saveability.n_<tier>``
for the counts, and ``ch09.saveability.reference_tau_minutes``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from rfisher import residual

from ..worlds import PARAMETERS, WORLD_LABEL, WORLDS
from . import core
from .core import DASH, Channel, Fragment, Run
from .tolerance_channels import sci

NAME = "saveability"
LABEL = "tab:tolerance:saveability"
KEY = "ch09.saveability"
SECTION = "worlds"
HALF_BAND_BREAK = 25
WORLD_NAMES = tuple(w[0] for w in WORLDS)
DILATIONS = tuple(p for p in PARAMETERS if p != "fs8")
GROWTH = "fs8"
CAP_SECONDS = residual.MAX_TAU_C_SECONDS
FALLBACK_TAU_MINUTES = 5.0        # only when the run measures and bounds nothing

TIERS = ("growth", "dilation", "cadence", "none", "no verdict")
TIER_LABEL = {"growth": "growth rate", "dilation": "dilation only", "cadence": "cadence-conditional",
              "none": "not recoverable", "no verdict": "no verdict"}
HEADER = ("ch", "tier", "reached by", r"$R_{f\sigma_8}$", r"$R_{\rm dil}$", r"$\tau_c$",
          r"$\tau_c$ needed (s)", "era")
ALIGN = "lll" + "r" * 4 + "l"


def _finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _num(value):
    return float(value) if _finite(value) else None


def reference_tau_seconds(run: Run) -> tuple[float, str]:
    """``(seconds, basis)``: the shortest correlation time the band exhibits.

    The tier asks whether a channel *could* be recovered, so the reference is
    the most favourable timescale the run's own evidence supports: the
    smallest measured tau_c or upper bound anywhere in the band. A required
    time shorter than this is shorter than anything the band has shown, and
    the channel does not take the cadence tier on it.
    """
    evidence = []
    for c in run.channels:
        quality = str(c.chain.get("tau_quality") or "")
        if quality == "measured":
            evidence.append((_num(c.chain.get("tau_c_minutes")), "measured"))
        elif quality == "bounded_above":
            evidence.append((_num(c.chain.get("tau_c_high_minutes")), "bounded"))
    evidence = [(v, k) for v, k in evidence if v is not None]
    if not evidence:
        return (FALLBACK_TAU_MINUTES * 60.0,
                f"a stated {FALLBACK_TAU_MINUTES:g} min (the run measures and bounds nothing)")
    value, kind = min(evidence)
    word = "measured correlation time" if kind == "measured" else "correlation-time bound"
    return value * 60.0, f"the shortest {word} in the band"


def cadence_headroom(tau_seconds: float) -> float:
    """How far a refused channel's residual would fall if its timescale were ``tau``.

    The chain books a refusal at the sidereal-day cap with no ground-filter
    credit. The what-if books all shelf power at the assumed timescale, also
    with no credit, so the residual scales by the ratio of the two coherence
    counts and nothing else moves.
    """
    return residual.n_coh_from_correlation_time(tau_seconds) / residual.n_coh_from_correlation_time(CAP_SECONDS)


def required_tau_seconds(ratio: float) -> float:
    """The correlation time that would bring a capped channel's ``ratio`` to 1.

    A refusal books every surviving component at one timescale, so the
    residual is proportional to it and the cap divided by the ratio is the
    time that lands exactly on the line.
    """
    return CAP_SECONDS / ratio if math.isfinite(ratio) and ratio > 0 else math.nan


@dataclass(frozen=True)
class Saveable:
    """One channel's tier and the evidence for it."""

    channel: int
    tier: str
    reached_by: str                 # the world that reaches the tier, or ''
    growth_ratio: float             # the best R over the worlds, as booked
    dilation_ratio: float
    tau_quality: str
    headroom: float                 # what the cadence what-if would multiply the ratios by (1.0 where none applies)
    off_era: bool
    unsettled: bool
    required_tau: float = math.nan  # the correlation time that would land the best world on R = 1
    note: str = ""


def _best(section, world: str, parameters) -> float:
    """The binding ratio over ``parameters`` in one world; NaN when none is priced."""
    values = [_num(section.get(f"{world}_{p}_R")) for p in parameters]
    values = [v for v in values if v is not None]
    return max(values) if values else math.nan


def classify(c: Channel, *, headroom: float) -> Saveable:
    """The channel's tier: the weakest instrument that brings a ratio to 1."""
    s = c.section(SECTION) if c.has(SECTION) else {}
    tau_quality = str(c.chain.get("tau_quality") or "")
    off_era = bool(c.era.get("off_era_current") or c.screening.get("off_era_current"))
    unsettled = bool(c.era.get("unconfirmed_instrument_change_last_month"))
    growth = {w: _best(s, w, (GROWTH,)) for w in WORLD_NAMES}
    dil = {w: _best(s, w, DILATIONS) for w in WORLD_NAMES}
    best_growth = min((v for v in growth.values() if math.isfinite(v)), default=math.nan)
    best_dil = min((v for v in dil.values() if math.isfinite(v)), default=math.nan)
    common = dict(channel=c.channel, growth_ratio=best_growth, dilation_ratio=best_dil,
                  tau_quality=tau_quality, off_era=off_era, unsettled=unsettled)
    if tau_quality == "refused":
        common["required_tau"] = required_tau_seconds(min(best_growth, best_dil))
    if not math.isfinite(best_growth) and not math.isfinite(best_dil):
        why = str(s.get("status") or "no worlds section")
        return Saveable(tier="no verdict", reached_by="", headroom=1.0, note=why, **common)

    def reaching(table) -> str:
        """The weakest cut that brings the table under 1, in cut order."""
        for w in WORLD_NAMES:
            if math.isfinite(table[w]) and table[w] <= 1.0:
                return w
        return ""

    world = reaching(growth)
    if world:
        return Saveable(tier="growth", reached_by=world, headroom=1.0, **common)
    world = reaching(dil)
    if world:
        return Saveable(tier="dilation", reached_by=world, headroom=1.0, **common)
    if tau_quality == "refused":
        what_if_growth = {w: v * headroom for w, v in growth.items()}
        what_if_dil = {w: v * headroom for w, v in dil.items()}
        world = reaching(what_if_growth) or reaching(what_if_dil)
        if world:
            tier_of = "growth" if reaching(what_if_growth) else "dilation"
            return Saveable(tier="cadence", reached_by=world, headroom=headroom,
                            note=f"the what-if reaches the {tier_of} tier", **common)
        req = common["required_tau"]
        why = ("the cap is not what is wrong: reaching the line would take tau_c "
               + (f"{sci(req).replace(chr(92) + 'times', 'x')} s" if math.isfinite(req) else "of no finite length")
               + ", shorter than anything the band exhibits")
        return Saveable(tier="none", reached_by="", headroom=headroom, note=why, **common)
    return Saveable(tier="none", reached_by="", headroom=1.0, **common)


def _tau_cell(quality: str) -> str:
    return {"measured": "measured", "bounded_above": "bound", "refused": "cap"}.get(quality, DASH)


def _era_cell(v: Saveable) -> str:
    if v.off_era:
        return "off era"
    if v.unsettled:
        return "unsettled"
    return "current"


def build(run: Run) -> Fragment:
    """``tab:tolerance:saveability``: one row per channel, sorted by tier then channel."""
    frag = Fragment(NAME, LABEL, "")
    channels = sorted(run.channels, key=lambda c: c.channel)
    if not channels:
        frag.tex = ""
        frag.notes.append("the run carries no channel")
        return frag
    tau_seconds, tau_basis = reference_tau_seconds(run)
    headroom = cadence_headroom(tau_seconds)
    verdicts = [classify(c, headroom=headroom) for c in channels]

    rows = []
    for v in verdicts:
        row = {"channel": v.channel}

        def add(column, value, **kw):
            frag.add(f"{KEY}.{column}.ch{v.channel}", value, row=row, column=column, **kw)

        growth = sci(v.growth_ratio) if math.isfinite(v.growth_ratio) else DASH
        dil = sci(v.dilation_ratio) if math.isfinite(v.dilation_ratio) else DASH
        reached = WORLD_LABEL[v.reached_by] if v.reached_by else DASH
        need = sci(v.required_tau) if math.isfinite(v.required_tau) else DASH
        rows.append([str(v.channel), TIER_LABEL[v.tier], reached,
                     f"${growth}$" if growth != DASH else DASH,
                     f"${dil}$" if dil != DASH else DASH,
                     _tau_cell(v.tau_quality), f"${need}$" if need != DASH else DASH, _era_cell(v)])
        add("tier", v.tier, kind="text", renderings=(TIER_LABEL[v.tier],))
        add("reached_by", v.reached_by or None, kind="text",
            renderings=(reached.replace("$", "").replace("~", " "),))
        for column, value, text in (("growth_ratio", v.growth_ratio, growth),
                                    ("dilation_ratio", v.dilation_ratio, dil)):
            if math.isfinite(value):
                add(column, value, status="bounded", renderings=(text.replace("\\times", "x"),))
            else:
                add(column, None, kind="text", status="pending", renderings=(DASH,))
        add("tau_quality", v.tau_quality or None, kind="text", renderings=(_tau_cell(v.tau_quality),))
        if math.isfinite(v.required_tau):
            add("required_tau_seconds", v.required_tau, status="derived",
                renderings=(sci(v.required_tau).replace("\\times", "x"),))
        else:
            add("required_tau_seconds", None, kind="text", status="pending", renderings=(DASH,))
        add("era_basis", _era_cell(v), kind="text", renderings=(_era_cell(v),))

    frag.tex = core.booktabs(HEADER, rows, ALIGN, midrules=_half_band_breaks(channels))

    counts = {t: [v.channel for v in verdicts if v.tier == t] for t in TIERS}
    for tier in TIERS:
        frag.add(f"{KEY}.n_{tier.replace(' ', '_')}", len(counts[tier]), kind="int",
                 row={"tier": tier}, column="channels")
    frag.add(f"{KEY}.channels", len(channels), kind="int", column="channels")
    frag.add(f"{KEY}.reference_tau_minutes", tau_seconds / 60.0, precision=1, column="reference_tau")
    frag.add(f"{KEY}.cadence_headroom", headroom, status="derived", column="headroom",
             renderings=(sci(headroom).replace("\\times", "x"),))
    frag.add(f"{KEY}.n_off_era", sum(1 for v in verdicts if v.off_era), kind="int", column="channels")
    frag.add(f"{KEY}.n_unsettled", sum(1 for v in verdicts if v.unsettled), kind="int", column="channels")
    closest = min((v for v in verdicts if math.isfinite(v.dilation_ratio)),
                  key=lambda v: v.dilation_ratio, default=None)
    if closest is not None:
        frag.add(f"{KEY}.closest_channel", closest.channel, kind="int", column="channel")
        frag.add(f"{KEY}.closest_ratio", closest.dilation_ratio, status="bounded", column="R",
                 renderings=(sci(closest.dilation_ratio).replace("\\times", "x"),))

    frag.notes.append(f"layout: one {len(HEADER)}-column tabular, natural width 388pt at 11pt; it sets upright "
                      f"inside the text block unscaled, with a midrule after channel {HALF_BAND_BREAK}")
    frag.notes.append("tiers, weakest instrument first: growth rate (some delay-cut world reaches R <= 1 on "
                      "fs8, which reaches every parameter); dilation only (a world reaches both dilations while "
                      "the growth rate stays out); cadence-conditional (nothing reaches 1 as booked, but the "
                      "residual is at the sidereal-day cap and the reference-timescale what-if reaches a tier); "
                      "not recoverable; no verdict (no operating point, or no bin the stability gate accepted)")
    frag.notes.append("counts: " + ", ".join(f"{TIER_LABEL[t]} {len(counts[t])}"
                                             + (f" ({_channel_list(counts[t])})" if counts[t] else "")
                                             for t in TIERS))
    capped = [v for v in verdicts if v.tau_quality == "refused" and math.isfinite(v.required_tau)]
    if capped:
        best = max(capped, key=lambda v: v.required_tau)
        frag.notes.append("tau_c needed (s) is the correlation time that would put a capped channel's best world "
                          f"exactly on R = 1; the longest any capped channel could accept is ch{best.channel:02d}'s "
                          f"{core.fmt(best.required_tau, 3, sig=True)} s, against the "
                          f"{core.fmt(tau_seconds, 3, sig=True)} s reference, so the column says how far short of "
                          "the band's own evidence the cap channels fall")
        if "bound" in tau_basis:
            frag.notes.append("the reference is an upper bound, not a measurement, so a required time below it is "
                              "unsupported rather than excluded: the band has never shown a correlation time that "
                              "short, and it has not shown that none exists; the contiguous-cadence campaign is what "
                              "would decide it")
    frag.notes.append(f"the cadence what-if assumes tau_c = {core.fmt(tau_seconds / 60.0, 2)} min, {tau_basis}; on a "
                      "refused channel that books all surviving shelf power at the assumed timescale and restores no "
                      "ground-filter credit (rfisher.residual.surviving_components), so it multiplies the ratios by "
                      f"{core.fmt(headroom, 3, sig=True)} and nothing else moves; it says a contiguous-cadence "
                      "campaign is worth running, not that the channel passes")
    frag.notes.append("era: every verdict is read on the channel's current era, which is the right basis only where "
                      "that era describes what the channel will keep doing; 'off era' marks a verdict priced on a "
                      "dead carrier and 'unsettled' an unconfirmed instrument change in the last month "
                      f"({sum(1 for v in verdicts if v.off_era)} and {sum(1 for v in verdicts if v.unsettled)} "
                      "channels); neither changes a tier")
    frag.notes.append("R <= 1 is already the loose test: at the adopted zeta = 1 convention it lets the induced "
                      "systematic equal the whole statistical error on the parameter, so a channel outside it is "
                      "not marginal and a channel outside it by orders of magnitude is not close; the tiers name "
                      "what would have to change, not how near a channel is")
    if closest is not None:
        frag.notes.append(f"the closest channel anywhere in the band is ch{closest.channel:02d} at R = "
                          f"{core.fmt(closest.dilation_ratio, 3, sig=True)} on the dilation tier")
    return frag


def _channel_list(channels) -> str:
    return ", ".join(f"ch{c:02d}" for c in sorted(channels)) or "none"


def _half_band_breaks(channels) -> tuple[int, ...]:
    for i, c in enumerate(channels):
        if c.channel > HALF_BAND_BREAK:
            return (i,) if i else ()
    return ()


BUILDERS = (build,)
