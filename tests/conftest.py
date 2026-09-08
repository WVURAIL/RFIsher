"""Opt-in external-provider doubles for synthetic pipeline tests."""
import sys

import pytest


@pytest.fixture
def synthetic_archive_health(tmp_path, monkeypatch):
    """Accept valid fixture rows; real pilot-proxy health is tested separately.

    This fixture is deliberately not autouse: health-contract refusal tests
    and real-product tests must continue to exercise the production provider.
    """
    # An importable provider also works in freshly spawned workers; a parent
    # process monkeypatch would silently depend on the platform's fork default.
    root = tmp_path / "synthetic_provider"
    package = root / "pilot_proxy"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "archive_health.py").write_text(
        "from types import SimpleNamespace\n"
        "import numpy as np\n"
        "def evaluate_frame_health(archive):\n"
        "    valid = np.asarray(archive['valid'], dtype=bool).reshape(-1)\n"
        "    return SimpleNamespace(include=valid, reason_counts={'detector_invalid': int((~valid).sum())})\n",
        encoding="utf-8")
    saved = {name: module for name, module in sys.modules.items()
             if name == "pilot_proxy" or name.startswith("pilot_proxy.")}
    for name in saved:
        del sys.modules[name]
    monkeypatch.syspath_prepend(str(root))
    try:
        yield root
    finally:
        for name in list(sys.modules):
            if name == "pilot_proxy" or name.startswith("pilot_proxy."):
                del sys.modules[name]
        sys.modules.update(saved)
