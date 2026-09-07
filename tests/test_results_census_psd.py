"""The 23-panel census spectra figure: reader, coverage check, render."""
from __future__ import annotations

import csv
import hashlib
import shutil

import numpy as np
import pytest

from rfisher_results import style
from rfisher_results.census_psd import CHANNELS, figure_census_psd, load_census_psd

HAVE_TEX = all(shutil.which(c) for c in ("latex", "dvipng", "kpsewhich"))


def _write(path, channels):
    offsets = np.linspace(-15.0, 15.0, 61)
    with path.open("w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["channel", "offset_khz", "db_rel_median"])
        for ch in channels:
            for x in offsets[::-1]:                      # unsorted on purpose
                w.writerow([ch, f"{x:.4f}", f"{20.0 * np.exp(-(x / 0.4) ** 2) + 0.05 * ch:.4f}"])
    return path


def test_reader_groups_and_sorts_by_channel(tmp_path):
    series = load_census_psd(_write(tmp_path / "census_psd.csv", CHANNELS))
    assert sorted(series) == list(CHANNELS)
    x, y = series[14]
    assert np.all(np.diff(x) > 0) and len(x) == 61 == len(y)


def test_missing_channels_are_refused(tmp_path):
    csv_path = _write(tmp_path / "census_psd.csv", CHANNELS[:-1])
    with pytest.raises(ValueError, match=r"lacks channels \[36\]"):
        figure_census_psd(csv_path, out=tmp_path / "f.pdf", provenance="test")


def test_render_all_23_is_byte_stable(tmp_path):
    style.configure(require_tex=HAVE_TEX)
    csv_path = _write(tmp_path / "census_psd.csv", CHANNELS)
    a = figure_census_psd(csv_path, out=tmp_path / "a.pdf", provenance="synthetic test spectra")
    b = figure_census_psd(csv_path, out=tmp_path / "b.pdf", provenance="synthetic test spectra")
    assert a.stat().st_size > 5000
    assert hashlib.sha256(a.read_bytes()).hexdigest() == hashlib.sha256(b.read_bytes()).hexdigest()
