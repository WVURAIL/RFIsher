"""Headless rendering plus data/axis assertions for every public forecast figure."""
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pytest

from rfisher import plots


@pytest.fixture
def rendered(monkeypatch):
    figures = []
    original = plots._save

    def record(fig, path):
        figures.append(fig)
        return original(fig, path)

    monkeypatch.setattr(plots, "_save", record)
    with matplotlib.rc_context({"text.usetex": False}):
        yield figures
    for fig in figures:
        plt.close(fig)


def _assert_files(path):
    assert path.is_file()
    pixels = plt.imread(path)
    assert pixels.shape[0] > 400 and pixels.shape[1] > 600
    assert np.std(pixels[..., :3]) > 0.01
    assert path.with_suffix(".pdf").read_bytes().startswith(b"%PDF-")


def test_significance_plot_preserves_curves_and_log_scales(tmp_path, rendered):
    years, significance = np.array([0.1, 1, 10]), np.array([1, 5, 15])
    path = tmp_path / "nested" / "significance.png"
    assert plots.fig_significance_vs_time({"clean": (years, significance)}, {"clean": "Clean"}, path) == path
    _assert_files(path)
    ax = rendered[0].axes[0]
    np.testing.assert_array_equal(ax.lines[0].get_ydata(), significance)
    assert ax.get_xscale() == ax.get_yscale() == "log"
    assert ax.lines[0].get_color() == plots.SCENARIO_COLORS["clean"]
    assert not plt.fignum_exists(rendered[0].number)


def test_required_time_plot_shows_percent_mask_and_reference(tmp_path, rendered):
    fractions = np.array([0, 0.5, 0.9])
    series = [{"label": "Target", "years": [0.1, 0.2, 1], "annotate": True, "reference_years": 0.15}]
    path = tmp_path / "time.png"
    plots.fig_required_time(fractions, series, path)
    _assert_files(path)
    ax = rendered[0].axes[0]
    np.testing.assert_array_equal(ax.lines[0].get_xdata(), [0, 50, 90])
    assert any("50% masked" in text.get_text() for text in ax.texts)
    assert any("0.15 yr" in text.get_text() for text in ax.texts)


def test_channel_mask_plot_orders_channels_and_marks_excision(tmp_path, rendered):
    path = tmp_path / "channels.png"
    plots.fig_channel_masking({30: 1, 14: 0.01, 20: 0.5}, {30}, path)
    _assert_files(path)
    ax = rendered[0].axes[0]
    assert [patch.get_height() for patch in ax.patches] == [1, 50, 100]
    assert any(text.get_text() == "excised" for text in ax.texts)


def test_per_bin_plot_keeps_values_and_frequency_axis(tmp_path, rendered):
    path = tmp_path / "bins.png"
    values = np.array([2, 4, 6])
    plots.fig_per_bin_significance(np.array([1.0, 1.5, 2.0]), {"custom": values}, {}, path,
                                   ylab="Uncertainty", title="Custom target")
    _assert_files(path)
    ax = rendered[0].axes[0]
    np.testing.assert_array_equal(ax.lines[0].get_ydata(), values)
    assert ax.get_ylabel() == "Uncertainty" and ax.get_title() == "Custom target"
    assert ax.child_axes[0].get_xlabel() == "Frequency [MHz]"


def test_delay_plot_marks_zero_information_at_floor_and_draws_soft_curve(tmp_path, rendered):
    path = tmp_path / "delay.png"
    plots.fig_taucut_significance(
        {"clean": {"tau": [30, 100, 200], "significance": [10, 0, np.nan]}},
        {"clean": "Clean"}, {"clean": 20}, lambda tau: 0.01 * tau,
        [(50, "test")], 100, 1.5, path,
        soft_curves={"clean": {"tau": [30, 100], "significance": [12, 3]}})
    _assert_files(path)
    ax = rendered[0].axes[0]
    floor_line = next(line for line in ax.lines if line.get_marker() == "v")
    np.testing.assert_array_equal(floor_line.get_xdata(), [100, 200])
    np.testing.assert_array_equal(floor_line.get_ydata(), [0.1, 0.1])
    assert any("soft cut" in line.get_label() for line in ax.lines)
