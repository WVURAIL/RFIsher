"""Score each incumbent against the same synthetic product population."""
import numpy as np
import pytest

from rfisher import incumbent
from rfisher.npzio import load_npz
from test_pilotproxy_v5 import _write_product, _replace


def test_product_comparison_uses_one_population_and_conserves_retained_shelf(tmp_path):
    path = _write_product(tmp_path / "product.npz", 14, frames=64, units=4)
    power = np.tile([1, 1.01, 1.02, 1.03, 1.04, 1.05, 1.06, 2], 8)
    _replace(path, baseband_power_linear=power[:, None])
    results, metadata = incumbent.compare_flaggers(path)
    assert metadata["n_scored"] == metadata["n_frames"] == 64 and metadata["n_blocks"] == 4
    data = load_npz(path)
    shelf, floor = incumbent.shelf_per_frame(data)
    assert floor == metadata["floor_db"]
    keep_all, mad, sk, proxy = results
    assert keep_all.f == 0 and keep_all.n_kept == 64 and keep_all.reduction_db == pytest.approx(0)
    assert keep_all.r == pytest.approx(shelf.mean())
    retained = ~data["reject_mask"][:, 0].astype(bool)
    assert proxy.n_kept == retained.sum()
    assert proxy.r == pytest.approx(shelf[retained].mean())
    assert metadata["duty_cycle"] == pytest.approx(1 - retained.mean())
    assert all(result.n_kept == round(64 * (1 - result.f)) for result in results)
    with pytest.raises(ValueError, match="no acquisition reaches"):
        incumbent.compare_flaggers(path, min_frames=17)


@pytest.mark.parametrize("power,message", [(np.zeros(8), "no usable"), (np.ones(8), "degenerate")])
def test_sk_refuses_unidentifiable_null(power, message):
    with pytest.raises(ValueError, match=message):
        incumbent.calibrate_sk_null(power, np.zeros(8))
    assert incumbent.spectral_kurtosis(np.zeros(8), 1) == 1
    assert incumbent.spectral_kurtosis(np.array([1]), 1) == 1
