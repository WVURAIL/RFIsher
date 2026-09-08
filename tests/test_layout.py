"""Geometry and pair-count conservation of generated baseline densities."""
from itertools import combinations

import numpy as np
import pytest

from rfisher import layout


def test_feed_coordinates_and_named_geometries():
    np.testing.assert_array_equal(
        layout.chime_feed_positions(2, 3, 20.0, 6.0),
        [[0, 0], [0, 2], [0, 4], [20, 0], [20, 2], [20, 4]])
    for geometry in layout.LAYOUTS.values():
        positions = layout.chime_feed_positions(
            geometry.ncyl, geometry.nfeed, geometry.cyl_spacing_m, geometry.cyl_length_m)
        assert positions.shape == (geometry.ncyl * geometry.nfeed, 2)
        assert len(np.unique(positions, axis=0)) == len(positions)
        assert positions[:, 1].max() < geometry.cyl_length_m


def test_cylinder_fov_scales_inversely_with_frequency_and_width():
    reference = 180 * 1.22 * (0.375 / 20) * (np.pi / 180) ** 2
    assert layout.fov_cyl(800, 20) == pytest.approx(reference)
    assert layout.fov_cyl(400, 20) == pytest.approx(2 * reference)
    assert layout.fov_cyl(800, 40) == pytest.approx(reference / 2)


@pytest.mark.parametrize("frequency", [400.0, 800.0])
@pytest.mark.parametrize("cut", [0.0, 20.0, None])
def test_density_integral_counts_each_retained_pair_once(tmp_path, frequency, cut):
    path = tmp_path / "nested" / "nx.dat"
    result = layout.build_nx_file(path, ncyl=3, nfeed=4, cyl_spacing=20,
                                  cyl_length=8, nu_mhz=frequency, dcut=cut)
    assert result == path
    x, density = np.loadtxt(path).T
    assert np.all(np.diff(x) > 0) and np.all(density >= 0)
    assert np.isfinite(density).all()
    # Integrating n(x) over annular area must recover the number of pairs.
    dx = x[1] - x[0]
    counts = density * 2 * np.pi * x * dx
    positions = [(20 * c, 2 * f) for c in range(3) for f in range(4)]
    distances = [np.hypot(a[0] - b[0], a[1] - b[1]) for a, b in combinations(positions, 2)]
    expected = sum(distance > (20 if cut is None else cut) for distance in distances)
    assert counts.sum() == pytest.approx(expected, abs=1e-10)
    np.testing.assert_allclose(counts, np.round(counts), atol=1e-10)
