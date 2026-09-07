"""The results layer, as its own package: what turns products and evaluations into stated results.

Every figure and table the dissertation states is produced here, whatever the
source -- offline CANFAR products, GNU Radio estimator evaluations, LimeSDR
captures -- in one style. It lives beside ``rfisher`` rather than inside it
because the shipped Fisher banks pin a digest of ``src/rfisher/``; rendering
code must not change a bank's recorded scientific source (``rfisher_results.style``, byte-identical to the
dissertation's ``figure_src/style.py``).
"""
