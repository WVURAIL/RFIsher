"""Backend discovery and import isolation without an installed RadioFisher."""
import sys
from types import SimpleNamespace

import pytest

from rfisher import backend


def _checkout(path):
    package = path / "radiofisher"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("BACKEND_ID = 'radiofisher'\n", encoding="utf-8")
    (package / "baofisher.py").touch()
    return path


def test_explicit_environment_and_fallback_precedence(tmp_path, monkeypatch):
    first, second = [_checkout(tmp_path / name) for name in ("first", "second")]
    monkeypatch.setenv("RADIOFISHER_DIR", str(first))
    monkeypatch.setattr(backend, "_DEFAULT_RF_CANDIDATES", (second,))
    assert backend.find_radiofisher_dir(second) == second
    assert backend.find_radiofisher_dir() == first
    with pytest.raises(FileNotFoundError, match="requested RadioFisher"):
        backend.find_radiofisher_dir(tmp_path / "missing")
    monkeypatch.setenv("RADIOFISHER_DIR", str(tmp_path / "missing"))
    with pytest.raises(FileNotFoundError, match="RADIOFISHER_DIR"):
        backend.find_radiofisher_dir()
    monkeypatch.delenv("RADIOFISHER_DIR")
    assert backend.find_radiofisher_dir() == second
    monkeypatch.setattr(backend, "_DEFAULT_RF_CANDIDATES", ())
    with pytest.raises(FileNotFoundError, match="Could not find"):
        backend.find_radiofisher_dir()


def test_import_reuses_one_checkout_and_refuses_mixed_code(tmp_path, monkeypatch):
    first, second = [_checkout(tmp_path / name) for name in ("first", "second")]
    # Register cleanup even when the package was absent before this test.
    monkeypatch.setitem(sys.modules, "radiofisher", None)
    monkeypatch.delitem(sys.modules, "radiofisher")
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.delenv("MPLBACKEND", raising=False)
    module, found = backend.import_radiofisher(first)
    assert found == first and module.BACKEND_ID == "radiofisher"
    assert backend.import_radiofisher(first) == (module, first)
    assert sys.path.count(str(first)) == 1
    with pytest.raises(RuntimeError, match="checkout mismatch"):
        backend.import_radiofisher(second)
    assert str(second) not in sys.path


def test_binding_requires_real_import_path_and_complete_checkout(tmp_path):
    with pytest.raises(RuntimeError, match="no import path"):
        backend.bind_radiofisher(object())
    with pytest.raises(RuntimeError, match="complete checkout"):
        backend.bind_radiofisher(SimpleNamespace(__file__=str(tmp_path / "radiofisher" / "__init__.py")))


def test_capability_gate_reports_all_missing_features(tmp_path):
    path = _checkout(tmp_path / "rf")
    module = SimpleNamespace(__file__=str(path / "radiofisher" / "__init__.py"),
                              BACKEND_ID="radiofisher", BACKEND_API_VERSION=1,
                              get_backend_capabilities=lambda: frozenset({"vol_frac"}))
    assert backend.require_backend_capabilities(module, {"vol_frac"}) == frozenset({"vol_frac"})
    with pytest.raises(RuntimeError, match="noise_freq_mode, noise_freq_weight"):
        backend.require_backend_capabilities(module, {"noise_freq_weight", "noise_freq_mode"})
    module.BACKEND_ID = "other"
    with pytest.raises(RuntimeError, match="BACKEND_ID"):
        backend.backend_capabilities(module)
    module.BACKEND_ID = "radiofisher"
    module.get_backend_capabilities = None
    with pytest.raises(RuntimeError, match="no get_backend_capabilities"):
        backend.backend_capabilities(module)
