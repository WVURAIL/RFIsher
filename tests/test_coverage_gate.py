"""The verification gate must fail closed and cannot hide an untested module."""
import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "rfisher_coverage_gate", Path(__file__).resolve().parents[1] / "scripts" / "check_test_coverage.py")
gate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gate)


def _report(covered=9, statements=10, branches=2, covered_branches=2):
    return {"meta": {"branch_coverage": True}, "files": {
        "src/rfisher/demo.py": {"summary": {"covered_lines": covered, "num_statements": statements,
                                             "num_branches": branches, "covered_branches": covered_branches}}}}


@pytest.fixture
def source_tree(tmp_path):
    package = tmp_path / "src" / "rfisher"
    package.mkdir(parents=True)
    (package / "demo.py").write_text("pass\n", encoding="utf-8")
    return tmp_path


def test_good_branch_inclusive_report_passes(source_tree):
    assert gate.check(_report(), source_tree) == []


def test_unmeasured_new_component_is_not_hidden_by_total(source_tree):
    (source_tree / "src" / "rfisher" / "new.py").touch()
    assert any("new.py: absent" in failure for failure in gate.check(_report(), source_tree))


def test_branch_and_total_regressions_fail(source_tree):
    failures = gate.check(_report(covered=10, branches=10, covered_branches=0), source_tree)
    assert any("demo.py" in failure for failure in failures)
    assert any("total:" in failure for failure in failures)
    report = _report()
    report["meta"]["branch_coverage"] = False
    assert "branch coverage is required" in gate.check(report, source_tree)[0]


def test_per_component_gate_is_not_hidden_by_large_covered_module(source_tree):
    report = _report(covered=6)
    (source_tree / "src" / "rfisher" / "large.py").touch()
    report["files"]["src/rfisher/large.py"] = _report(1000, 1000)["files"]["src/rfisher/demo.py"]
    failures = gate.check(report, source_tree)
    assert len(failures) == 1 and "demo.py" in failures[0]


def test_gate_refuses_absent_sources_and_corrupt_report(tmp_path, capsys):
    assert gate.check(_report(), tmp_path) == ["no package source files found"]
    missing = tmp_path / "missing.json"
    assert gate.main([str(missing)]) == 1
    missing.write_text("{}", encoding="utf-8")
    assert gate.main([str(missing)]) == 1
    assert "branch coverage is required" in capsys.readouterr().out
