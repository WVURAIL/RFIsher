"""The report registry: every registered module exposes its builders."""
from __future__ import annotations

from rfisher_results.archive.report import build as rb


def test_registry_imports_every_table_module_and_yields_callables():
    builders = rb.table_builders()
    assert len(builders) >= len(rb.TABLE_MODULES) and all(callable(b) for b in builders)
    names = [b.__module__.rsplit(".", 1)[-1] for b in builders]
    assert set(rb.TABLE_MODULES) <= set(names)


def test_figure_modules_expose_render():
    for name in rb.FIGURE_MODULES:
        mod = rb._module(name)
        assert callable(getattr(mod, "render", None))
