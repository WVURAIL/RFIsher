"""The baseline density: rebuilt from the layout, and the inter-cylinder copy the table uses."""
import numpy as np

from rfisher import baselines, inputs


def test_all_pairs_rebuild_radiofishers_density():
    x, n = np.loadtxt(baselines.radiofisher_file()).T
    np.testing.assert_allclose(baselines.density(x, inter_only=False), n, rtol=1e-12)


def test_the_packaged_density_is_the_inter_cylinder_build():
    x, n = np.loadtxt(baselines.inter_file()).T
    np.testing.assert_allclose(n, baselines.density(x, inter_only=True), rtol=1e-12)
    dx = x[1] - x[0]
    assert (n * 2 * np.pi * x * dx).sum() == np.float64(6 * 256 ** 2)   # 6 cylinder pairs
    assert not n[x * baselines.METRES_PER_X < 21.9].any()                 # nothing shorter than 22 m


def test_the_table_uses_inter_cylinder_baselines_and_the_overview_all():
    assert inputs.experiment()["n(x)"] == str(baselines.inter_file())
    assert inputs.experiment(baselines="all")["n(x)"] == str(baselines.radiofisher_file())
