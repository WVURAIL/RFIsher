"""
Shared figure style: match the proposal's typography.

main.tex is 12 pt article with \\usepackage{mathptmx}, i.e. Times for both
text and math, on US Letter with 1 in margins -> \\textwidth = 6.5 in.

TeX Gyre Termes is the same URW Times that mathptmx resolves to, so figure
text and body text come out in the same face. Math is set with the STIX
fontset, which is Times-metric.

Draw every figure at TEXTWIDTH inches and include it at \\textwidth in the
document. That way nothing is scaled, and a 9 pt label in the figure really
renders at 9 pt on the page. Scaling a figure down with
\\includegraphics[width=0.8\\textwidth] shrinks its type by the same factor,
which is why the labels were coming out small.

Usage:
    from figstyle import use, TEXTWIDTH
    use()
    fig, ax = plt.subplots(figsize=(TEXTWIDTH, 3.0), dpi=200)
"""
import matplotlib

TEXTWIDTH = 6.5      # inches; \showthe\textwidth in main.tex if the geometry changes
BASE_PT = 9          # figure body text; the document body is 12 pt


def use(base=BASE_PT):
    matplotlib.rcParams.update({
        "font.family": "serif",
        "font.serif": ["TeX Gyre Termes", "Nimbus Roman", "Times New Roman",
                       "STIXGeneral", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": base,
        "axes.titlesize": base,
        "axes.labelsize": base,
        "xtick.labelsize": base - 1,
        "ytick.labelsize": base - 1,
        "legend.fontsize": base - 1,
        "figure.titlesize": base,
        "axes.linewidth": 0.7,
        "xtick.major.width": 0.7,
        "ytick.major.width": 0.7,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
        "pdf.fonttype": 42,      # embed as TrueType, not Type 3
        "ps.fonttype": 42,
    })
