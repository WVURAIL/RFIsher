"""Builder orchestration with analytically known workers and strict output loading."""
import json
from types import SimpleNamespace

import numpy as np
import pytest

from rfisher import fisherbank
from test_fisherbank_schema import _write_bank


def _worker(task):
    ibin, hours = task
    return ibin, hours, np.diag([ibin + 1.0, ibin + 2.0]) * hours**2, ["A", "sigma_NL"]


@pytest.fixture
def builder(monkeypatch, tmp_path):
    template = _write_bank(tmp_path / "template.npz")
    with np.load(template, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["meta"]))
    monkeypatch.setattr(fisherbank, "_CTX", {"astrophysical_model_profile": "chime_overview_2022"})
    monkeypatch.setattr(fisherbank, "_init_context", lambda *a, **kw: (
        object(), np.array([0.8, 0.9, 1.0]), np.array([0.85, 0.95])))
    monkeypatch.setattr(fisherbank, "_build_provenance", lambda: metadata["provenance"])
    monkeypatch.setattr(fisherbank, "_one_fisher", _worker)
    return tmp_path / "output" / "bank.npz"


@pytest.mark.parametrize("parallel", [False, True])
def test_unordered_worker_results_are_placed_by_bin_and_time(builder, monkeypatch, parallel):
    class UnorderedPool:
        def __init__(self, processes):
            assert processes == 2

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def imap_unordered(self, worker, tasks):
            return iter([worker(task) for task in tasks][::-1])

    if parallel:
        monkeypatch.setattr(fisherbank.mp, "get_context", lambda method: SimpleNamespace(Pool=UnorderedPool))
    times = [8, 2, 1, 4, 6, 3]
    assert fisherbank.build_bank(builder, t_grid_hours=times, nproc=2 if parallel else 1,
                                 cosmology="planck2018") == builder
    bank = fisherbank.FisherBank(builder)
    np.testing.assert_array_equal(bank.t_grid, sorted(times))
    for ibin in range(bank.nbins):
        for hours in sorted(times):
            np.testing.assert_array_equal(bank.F(ibin, hours), _worker((ibin, hours))[2])
    assert times == [8, 2, 1, 4, 6, 3]
    assert bank.artifact_kind == "forecast" and bank.meta["expt_overrides"] == {}


def test_parameter_drift_leaves_existing_output_untouched(builder, monkeypatch):
    builder.parent.mkdir(parents=True)
    builder.write_bytes(b"previous bank")

    def changing_worker(task):
        ibin, hours, matrix, names = _worker(task)
        return ibin, hours, matrix, names if hours == 1 else ["A", "apar"]

    monkeypatch.setattr(fisherbank, "_one_fisher", changing_worker)
    with pytest.raises(RuntimeError, match="parameter schema changed"):
        fisherbank.build_bank(builder, t_grid_hours=[1, 2], nproc=1)
    assert builder.read_bytes() == b"previous bank"


@pytest.mark.parametrize("times", [[], [1], [1, 1], [0, 1], [-1, 1], [1, np.nan], [1, np.inf]])
def test_invalid_time_grids_fail_before_backend_or_output(builder, monkeypatch, times):
    def unexpected(*args, **kwargs):
        pytest.fail("invalid grid reached backend work")

    monkeypatch.setattr(fisherbank, "_init_context", unexpected)
    with pytest.raises(ValueError, match="t_grid_hours"):
        fisherbank.build_bank(builder, t_grid_hours=times, nproc=1)
    assert not builder.exists()
