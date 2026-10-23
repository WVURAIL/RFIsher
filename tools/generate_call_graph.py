"""Draw docs/rfisher_functions.svg: RFIsher at function level, and where RadioFisher and the DTV model enter."""
from pathlib import Path

INK, MUTED, SURF, BG = "#1c2126", "#5a6168", "#ffffff", "#f6f7f5"
AMBER, AMBERBG, BLUE, BLUEBG = "#9a5a00", "#fff4e0", "#1f5fa8", "#eef4fb"
MONO = "DejaVu Sans Mono, monospace"


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, t, size=13, col=MUTED, weight="normal", mono=False, anchor="start"):
    fam = f' font-family="{MONO}"' if mono else ""
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{col}" font-weight="{weight}"'
            f' text-anchor="{anchor}"{fam} xml:space="preserve">{esc(t)}</text>')


def box(x, y, w, h, title, lines=(), stroke=INK, sw=1.3, fill=SURF, tcol=INK, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>',
           text(x + 12, y + 23, title, 14, tcol, "600", True)]
    for i, line in enumerate(lines):
        out.append(text(x + 12, y + 44 + 18 * i, line, 12.5))
    return "\n".join(out)


def arrow(x1, y1, x2, y2, col=INK, mk="a"):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col}" stroke-width="1.5" marker-end="url(#{mk})"/>'


W, H = 1300, 1150
s = [(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="DejaVu Sans, sans-serif" role="img" '
     'aria-label="RFIsher call graph: fixed inputs, the per-channel forecast with the DTV residual, the tolerance and the table">'),
     ("<defs>" + "".join(
         f'<marker id="{i}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
         f'<path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>' for i, c in (("a", INK), ("b", AMBER), ("c", BLUE), ("m", MUTED)))
     + "</defs>"), f'<rect width="{W}" height="{H}" fill="{BG}"/>',
     text(24, 34, "RFIsher: one tolerance per 6 MHz channel", 19, INK, "600"),
     text(24, 56, "Every function, run once per channel. Blue boxes call RadioFisher; the amber box is the DTV model.", 13)]

# fixed inputs
s.append(text(24, 88, "FIXED INPUTS  (bands.py, inputs.py)", 12, MUTED, "600"))
s.append(box(24, 98, 300, 118, "bands.channels()", ["24 channels: DTV 14 to 36,", "control 37 (608-614 MHz)",
                                                     "Band.z_min, z_max, z_center", "from the 6 MHz edges"]))
s.append(box(340, 98, 300, 118, "inputs.cosmology()", ["latest: cmbspa2026 (SPT+ACT+Planck,", "DESI DR2); its P(k) table checked by",
                                                       "pk_cache.cache_matches", "-> radiofisher.load_power_spectrum"], stroke=BLUE, fill=BLUEBG))
s.append(box(656, 98, 300, 118, "inputs.experiment()", ["CHIME (radiofisher.chime)", "t = 8,760 h of retained data",
                                                        "(one year)"]))
s.append(box(972, 98, 304, 118, "inputs.background()", ["H(z), r(z), D(z), f(z)", "radiofisher.background_",
                                                         "evolution_splines"], stroke=BLUE, fill=BLUEBG))
for x in (174, 490, 806, 1124):
    s.append(arrow(x, 216, x, 262))

# per channel
s.append(f'<rect x="24" y="264" width="1252" height="616" rx="9" fill="{SURF}" stroke="{INK}" stroke-width="2.2"/>')
s.append(text(42, 292, "table.row(band)", 16, INK, "600", True))
s.append(text(200, 292, "for each channel, in parallel under table.build_table()", 12.5))

s.append(box(44, 306, 600, 156, "1  forecast.prepare(band)", ["radiofisher.prepare_bin(z_min, z_max, ...)",
                                                             "  the channel's own redshift, 6 MHz deep",
                                                             "BAO template slope taken directly at each k",
                                                             "residual.geometry(cosmo, expt)",
                                                             "residual.coherent_shelf(g)  ->  expt['P_res']"], stroke=BLUE, fill=BLUEBG))
s.append(box(664, 306, 592, 156, "residual.coherent_shelf: the DTV model", [
    "dP / C_N = a x N_nu x N_meas(k_perp) x f_w(k_perp)",
    "inside the wedge |k_par| <= m k_perp + pi / L, else 0",
    "N_nu = 15.4 channels; N_meas = baselines per Fourier cell;",
    "f_w = pi / (L k_w) spreads one mode over the wedge;",
    "unit strength a = 1 (bias is proportional to a)"], stroke=AMBER, sw=2.2, fill=AMBERBG, tcol=AMBER))
s.append(arrow(662, 420, 646, 420, AMBER, "b"))
s.append(arrow(344, 462, 344, 484))

s.append(box(44, 486, 1212, 118, "2  forecast.integrate(p)", [
    "radial_edges, angular_edges (+ residual.wedge_mu): split k and mu at every kink of the integrand",
    "Gauss-Legendre, 8 nodes per k segment x 16 per mu segment;  at each node:",
    "radiofisher.fisher_integrands(k, mu, cosmo, expt)  ->  12 parameter rows and the '_Pres' row",
    "F_ij = Vfac x 2 Sum k^2 w d_i d_j   (13 x 13, the last row and column belong to the residual)"], stroke=BLUE, fill=BLUEBG))
s.append(arrow(344, 604, 344, 626))

s.append(box(44, 628, 1212, 136, "3  tolerance.tolerance(F, names)", [
    "fit A, damping variance s_NL, alpha_perp, alpha_par, f sigma_8, b sigma_8",
    "C = (F_fit)^-1, the clean one-year covariance;   B = the '_Pres' column;   bias per unit a = C B",
    "combine the dilations as the CHIME Overview does: ln alpha_V = 2/3 ln alpha_perp + 1/3 ln alpha_par",
    "sigma_dv = sqrt(w C w);   response_dv = (w . bias) / sigma_dv,   w = (2/3, 1/3)",
    "a_tol = 1 / |response_dv|  -- the strength at which the bias of D_V equals its sigma"]))
s.append(arrow(344, 764, 344, 786))
s.append(box(44, 788, 1212, 74, "row", [
    "channel, band, z_center, sigma_dv, response_dv, a_tol   (+ each dilation's sigma, bias and response)"]))

# outputs
s.append(arrow(330, 880, 330, 912))
s.append(arrow(970, 880, 970, 912))
s.append(box(24, 914, 612, 96, "table.write_table(table, out)", ["channel_table.json: rows + inputs + provenance",
                                                                 "(RFIsher and RadioFisher commits, P(k) table SHA-256)",
                                                                 "channel_table.csv: the rows"]))
s.append(box(656, 914, 620, 96, "figures.draw_all(table, out)", ["summary.png: tolerance, response and sigma by channel",
                                                                 "channel_NN.png: where the residual sits, and the bias",
                                                                 "of D_V against residual strength"]))

# downstream
s.append(box(24, 1030, 1252, 100, "downstream, not in RFIsher: the detector side reads the table", [
    "for each threshold:  power x and kept fraction kappa from the archive histogram",
    "a = (gamma x_hi)^2 x 16,384 x G; gamma = stack / proxy, G = assumed gain; bias / sigma = a x |response_dv|",
    "rule: the knee if bias / sigma <= 1, else the passing threshold closest to it, else word 0x1;   time = 1 / kappa"],
    stroke=MUTED, dash="6 4", tcol=MUTED))
s.append(f'<line x1="330" y1="1010" x2="330" y2="1028" stroke="{MUTED}" stroke-width="1.5" stroke-dasharray="4 3" marker-end="url(#m)"/>')
s.append("</svg>")
(Path(__file__).resolve().parents[1] / "docs" / "rfisher_functions.svg").write_text("\n".join(s) + "\n")
