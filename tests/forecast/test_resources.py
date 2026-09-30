"""Package-data regressions for source, wheel, and archive installations."""
from __future__ import annotations

import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import get_type_hints

import numpy as np
import pytest

from rfisher.forecast.radiofisher_bao import legacy_masks as channels
from rfisher.forecast.radiofisher_bao.bank import banks as fisherbank, resources
from rfisher.forecast.radiofisher_bao import significance as forecast, scenarios
from rfisher.forecast.radiofisher_bao.bank.backend import find_radiofisher_dir
from rfisher.forecast.radiofisher_bao.bank.banks import (
    ARTIFACT_BIAS_RESPONSE, ARTIFACT_FORECAST, BANK_SCHEMA_VERSION, FisherBank)


EXPECTED_SHA256 = {
    resources.CMBSPA2026_BANK_NAME:
        "1616f7e38c4c0ba00955f907f817caeb8f66890a02ff216ef27c4a3ff61de6b7",
    resources.PLANCK2018_BANK_NAME:
        "7df2c6613cdb27ee2e97ca631e76289094f57a7e61045fe442d4af79a3ef6481",
    resources.PACT2025_BANK_NAME:
        "8c5e246f666aedd1d545ecdd294677bc92c8b81005cf105570a4f9db1ef42548",
    channels.DEFAULT_RATES_NAME:
        "da8c1c1df1f3929920ac132ea037adaa7cad5f5edb215e046ec5a40281d6bde3",
    resources.SYNTHETIC_BASELINE_NAME:
        "101a156d88c212781b098f89a86bfb11ada58433d5dcc5cc2fb86956c930790b",
    "cache_pk.dat":
        "c33b7e8e9b5e5abff63476e518a0a4376ac1a5043aa32a811e037dce5c81506f",
    "cache_pk_chime2022.dat":
        "aaa8a35e42723c2df364616e40a73f340fb1887a7db35507496e6f17451daadf",
    "cache_pk_chime2022_pact2025.dat":
        "f7bdfdc9c241864432b888b670cc99a03d961c164e4e27a0c37e43b08c16e708",
    "cache_pk_chime2022_cmbspa2026.dat":
        "4703b937f8bb1c6a80391a9e0e91f6ee9b3d44d3291a312495e7dbba41501c81",
}
CANONICAL_TEXT_RESOURCES = frozenset({
    channels.DEFAULT_RATES_NAME,
    resources.SYNTHETIC_BASELINE_NAME,
})
BULL_BANK_SHA256 = {
    "fisher_bank_bull2015_planck2013_epsfg1e-6.npz":
        "c5460e3866a6638dae201f9b08fcb47e489b698546d50075f006e9a225b7666e",
    "fisher_bank_bull2015_planck2013_epsfg1e-5.npz":
        "ac1bb92a6d5685e4cd52ca50195e9aed38cbeaca56f5a3be7dc453097a3e0d0d",
}
RESPONSE_BANK_SHA256 = {
    "fisher_bank_chime2022_pres_dense.npz":
        "fc6f014bee4aafca74b774881a05c2da63eb524660042f814218f35f1869d2ce",
    "fisher_bank_chime2022_pres_kfg22_dense.npz":
        "642172cb1fdb072fca51632516e13e013743f70595baaa5db8b000989e493a08",
    "fisher_bank_chime2022_pres_kfg44_dense.npz":
        "d6c2bdd4fc8526ded22a36aeb0d69c44ff7c89c1b337202e6cc9f4063492ee71",
    "fisher_bank_chime2022_pres_kfg80_dense.npz":
        "a862fc0f56ca6c4c5bb9c359ebead956c97aeee12504d0ca24f9066f53d7233a",
}
RESPONSE_BANK_KFG = {
    "fisher_bank_chime2022_pres_dense.npz": None,
    "fisher_bank_chime2022_pres_kfg22_dense.npz": 22.0,
    "fisher_bank_chime2022_pres_kfg44_dense.npz": 44.0,
    "fisher_bank_chime2022_pres_kfg80_dense.npz": 80.0,
}
# The source digest of RFIsher e041d5e, which built every bank before the
# bank code moved into its own subpackage.
BUILD_SOURCE_SHA256 = (
    "814aeb93c00c38c32b044533172af89c15b369ad5342e96b5b200ac8025fde96"
)
EXPECTED_RADIOFISHER_SOURCE_SHA256 = (
    "574f16f12463f4305f089dfcf62889c6106513c909a6cedb35e7c76d6b2e6054"
)


def _sha256(resource, canonical_text: bool = False) -> str:
    with resource.open("rb") as stream:
        data = stream.read()
    if canonical_text:
        # Scientific text content is independent of the checkout's newline
        # convention. .gitattributes enforces LF for future checkouts, while
        # this normalization also handles an already-populated Windows tree.
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def test_packaged_data_bytes_are_unchanged():
    """Moving the canonical files into the package must not alter them."""
    for name, expected in EXPECTED_SHA256.items():
        canonical_text = name in CANONICAL_TEXT_RESOURCES
        assert _sha256(resources.data_file(name), canonical_text) == expected


def test_canonical_text_hash_is_newline_independent(tmp_path):
    lf = tmp_path / "lf.csv"
    crlf = tmp_path / "crlf.csv"
    lf.write_bytes(b"channel,rate\n14,0.1\n")
    crlf.write_bytes(b"channel,rate\r\n14,0.1\r\n")
    assert _sha256(lf, canonical_text=True) == _sha256(
        crlf, canonical_text=True)


def test_scientific_dat_resources_are_checkout_stable_lf():
    attributes = (Path(__file__).resolve().parents[2] / ".gitattributes") \
        .read_text(encoding="utf-8")
    assert "src/rfisher/data/*.dat text eol=lf" in attributes


def test_source_checkout_defaults_load_from_package_data():
    bank = FisherBank(resources.DEFAULT_BANK)
    assert bank.schema_version == BANK_SCHEMA_VERSION
    assert "version" not in bank.meta
    assert bank.meta["config"] == "chime2022"
    assert bank.meta["cosmology"] == "cmbspa2026"
    assert bank.nbins == 15
    assert len(channels.legacy_rate_fractions()) == 23


def test_resource_annotations_resolve_on_supported_python():
    """The Traversable type moved after Python 3.10."""
    assert get_type_hints(resources.data_file)["return"].__name__ \
        == "Traversable"
    assert resources.DEFAULT_BANK.is_file()


def test_named_bank_registry_is_exact_and_immutable():
    assert dict(resources.BANK_NAMES) == {
        "planck2018": resources.PLANCK2018_BANK_NAME,
        "pact2025": resources.PACT2025_BANK_NAME,
        "cmbspa2026": resources.CMBSPA2026_BANK_NAME,
    }
    assert resources.bank_file("planck2018") == resources.PLANCK2018_BANK
    assert resources.bank_file() == resources.DEFAULT_BANK
    assert resources.DEFAULT_BANK_NAME == resources.CMBSPA2026_BANK_NAME
    assert resources.PACT2025_BANK.name == resources.PACT2025_BANK_NAME
    with pytest.raises(TypeError):
        resources.BANK_NAMES["alias"] = resources.DEFAULT_BANK_NAME


def test_unknown_named_bank_fails_before_resource_lookup():
    with pytest.raises(ValueError, match="unknown packaged bank cosmology"):
        resources.bank_file("unknown")


@pytest.mark.parametrize("cosmology", list(resources.BANK_NAMES))
def test_named_packaged_banks_are_strict_v2_forecasts(cosmology):
    resource = resources.bank_file(cosmology)
    bank = FisherBank(resource)

    assert resource.name == resources.BANK_NAMES[cosmology]
    assert bank.schema_version == BANK_SCHEMA_VERSION
    assert bank.artifact_kind == ARTIFACT_FORECAST
    assert "version" not in bank.meta
    assert bank.meta["config"] == "chime2022"
    assert bank.meta["cosmology"] == cosmology
    assert bank.meta["provenance"]["cosmology"]["name"] == cosmology


def test_named_banks_are_distinct_matched_v3_builds():
    planck_resource = resources.bank_file("planck2018")
    pact_resource = resources.bank_file("pact2025")
    assert _sha256(planck_resource) != _sha256(pact_resource)

    planck = FisherBank(planck_resource)
    pact = FisherBank(pact_resource)
    assert planck.meta["cosmology"] == "planck2018"
    assert pact.meta["cosmology"] == "pact2025"
    assert not np.array_equal(planck.F_grid, pact.F_grid)
    assert np.array_equal(planck.t_grid, pact.t_grid)
    assert np.array_equal(planck.zs, pact.zs)
    assert planck.paramnames == pact.paramnames

    current_rfisher_digest = fisherbank.bank_source_state()[
        "working_tree_sha256"]
    expected_caches = {
        "planck2018": "cache_pk_chime2022.dat",
        "pact2025": "cache_pk_chime2022_pact2025.dat",
        "cmbspa2026": "cache_pk_chime2022_cmbspa2026.dat",
    }
    try:
        radiofisher_root = find_radiofisher_dir()
    except FileNotFoundError:
        radiofisher_root = None
    radio_digests = set()
    for cosmology in resources.BANK_NAMES:
        bank = FisherBank(resources.bank_file(cosmology))
        np.testing.assert_array_equal(bank.zs, planck.zs)
        np.testing.assert_array_equal(bank.t_grid, planck.t_grid)
        assert bank.paramnames == planck.paramnames
        provenance = bank.meta["provenance"]
        assert provenance["baonoise"]["version"] == "4.0.0"
        assert provenance["radiofisher"]["backend_version"] == "1.0.0"
        assert provenance["baonoise"]["working_tree_sha256"] \
            == current_rfisher_digest
        assert provenance["baonoise"]["source_manifest"] == {
            key: list(value) for key, value in
            fisherbank.BANK_SOURCE_MANIFEST.items()}
        assert provenance["radiofisher"]["source_manifest"] == {
            key: list(value) for key, value in
            fisherbank.RADIOFISHER_SOURCE_MANIFEST.items()}
        cache_name = expected_caches[cosmology]
        assert provenance["pk_cache"]["filename"] == cache_name
        assert provenance["pk_cache"]["sha256"] == _sha256(
            resources.data_file(cache_name))
        radio_digests.add(
            provenance["radiofisher"]["working_tree_sha256"])
    assert radio_digests == {EXPECTED_RADIOFISHER_SOURCE_SHA256}
    if radiofisher_root is None:
        pytest.skip(
            "RadioFisher code-tree cross-check needs a checkout; "
            "set RADIOFISHER_DIR to run it")
    current_radio_digest = fisherbank._git_state(
        radiofisher_root,
        **fisherbank.RADIOFISHER_SOURCE_MANIFEST,
    )["working_tree_sha256"]
    assert current_radio_digest == EXPECTED_RADIOFISHER_SOURCE_SHA256


@pytest.mark.parametrize("cosmology", ["pact2025", "cmbspa2026"])
def test_packaged_pact_bank_matches_direct_backend_for_masked_bin(cosmology):
    try:
        find_radiofisher_dir()
    except FileNotFoundError:
        pytest.skip("direct P-ACT validation requires a RadioFisher checkout")
    bank = FisherBank(resources.bank_file(cosmology))
    calculator = forecast.Forecast(bank, style="perbin_A")
    scenario = scenarios.legacy_rate_table_scenario()
    bank_sigma = calculator.sigma_A(scenario, 1.0e4, bins=[6])
    direct_sigma = calculator.sigma_A_direct(
        scenario, 1.0e4, bins=[6])
    assert direct_sigma == pytest.approx(bank_sigma, rel=0.015)


def test_bull_research_banks_are_matched_strict_v2_v3_builds():
    root = Path(__file__).resolve().parents[2]
    current_rfisher_digest = fisherbank.bank_source_state()[
        "working_tree_sha256"]
    banks = []
    radio_digests = set()
    for name, expected_sha256 in BULL_BANK_SHA256.items():
        path = root / "data" / name
        assert _sha256(path) == expected_sha256
        bank = FisherBank(path)
        banks.append(bank)

        assert bank.schema_version == BANK_SCHEMA_VERSION
        assert bank.artifact_kind == ARTIFACT_FORECAST
        assert "version" not in bank.meta
        assert bank.meta["config"] == "bull2015"
        assert bank.meta["cosmology"] == "planck2013"
        assert bank.meta["astrophysical_model_profile"] == "bull2015"
        provenance = bank.meta["provenance"]
        assert provenance["cosmology"]["astrophysical_models"] == {
            "Tb_model": "powerlaw",
            "bias_HI_model": "powerlaw",
            "omega_HI_model": "powerlaw",
        }
        assert provenance["baonoise"]["version"] == "4.0.0"
        assert provenance["radiofisher"]["backend_version"] == "1.0.0"
        assert provenance["baonoise"]["working_tree_sha256"] \
            == current_rfisher_digest
        assert provenance["pk_cache"]["filename"] == "cache_pk.dat"
        assert provenance["pk_cache"]["sha256"] == EXPECTED_SHA256[
            "cache_pk.dat"]
        radio_digests.add(
            provenance["radiofisher"]["working_tree_sha256"])

    assert radio_digests == {EXPECTED_RADIOFISHER_SOURCE_SHA256}
    assert np.array_equal(banks[0].t_grid, banks[1].t_grid)
    assert np.array_equal(banks[0].zs, banks[1].zs)
    assert banks[0].paramnames == banks[1].paramnames
    assert not np.array_equal(banks[0].F_grid, banks[1].F_grid)
    epsilon_fg = {
        bank.meta["provenance"]["experiment"]["settings"]["epsilon_fg"]
        for bank in banks
    }
    assert epsilon_fg == {1e-6, 1e-5}


@pytest.mark.parametrize("name", sorted(BULL_BANK_SHA256))
def test_each_bull_research_bank_matches_its_recorded_direct_backend(name):
    try:
        rf_dir = find_radiofisher_dir()
    except FileNotFoundError:
        pytest.skip("direct Bull-bank validation requires a RadioFisher checkout")
    from rfisher.forecast.radiofisher_bao.bank.backend import import_radiofisher

    rf, rf_dir = import_radiofisher(rf_dir)
    bank = FisherBank(Path(__file__).resolve().parents[2] / "data" / name)
    calculator = forecast.Forecast(
        bank, rf=rf, style="shared_A", rf_dir=rf_dir)
    scenario = scenarios.clean()
    bank_sigma = calculator.sigma_A(scenario, 1.0e4, bins=[6])
    direct_sigma = calculator.sigma_A_direct(
        scenario, 1.0e4, bins=[6], rf_dir=rf_dir)
    assert direct_sigma == pytest.approx(bank_sigma, rel=0.015)


@pytest.mark.parametrize("name", sorted(BULL_BANK_SHA256))
def test_each_bull_bank_interpolates_bin8_below_one_percent(name):
    try:
        rf_dir = find_radiofisher_dir()
    except FileNotFoundError:
        pytest.skip("Bull interpolation validation requires RadioFisher")
    from rfisher.forecast.radiofisher_bao.bank.backend import import_radiofisher

    rf, rf_dir = import_radiofisher(rf_dir)
    bank = FisherBank(Path(__file__).resolve().parents[2] / "data" / name)
    calculator = forecast.Forecast(
        bank, rf=rf, style="shared_A", rf_dir=rf_dir)
    scenario = scenarios.clean()
    bank_sigma = calculator.sigma_A(scenario, 3300.0, bins=[8])
    direct_sigma = calculator.sigma_A_direct(
        scenario, 3300.0, bins=[8], rf_dir=rf_dir)

    assert abs(bank_sigma / direct_sigma - 1.0) < 0.01


def test_packaged_response_banks_are_restamped_unit_responses():
    directory = (Path(__file__).resolve().parents[2] / "src" / "rfisher"
                 / "data" / "response_banks")
    assert sorted(path.name for path in directory.glob("*.npz")) \
        == sorted(RESPONSE_BANK_SHA256)
    current = fisherbank.bank_source_state()["working_tree_sha256"]
    for name, expected_sha256 in RESPONSE_BANK_SHA256.items():
        path = directory / name
        assert _sha256(path) == expected_sha256
        bank = FisherBank(path, expected_artifact_kind=ARTIFACT_BIAS_RESPONSE)
        assert bank.meta["config"] == "chime2022"
        assert bank.meta["cosmology"] == "planck2018"
        assert bank.meta["expt_overrides"].get("P_res") == 1.0
        assert bank.meta["expt_overrides"].get("kfg_fac") \
            == RESPONSE_BANK_KFG[name]
        assert bank.meta["foreground_settings"]["epsilon_fg"] == 0
        provenance = bank.meta["provenance"]
        assert provenance["baonoise"]["version"] == "4.0.0"
        assert provenance["baonoise"]["working_tree_sha256"] == current
        assert provenance["radiofisher"]["working_tree_sha256"] \
            == EXPECTED_RADIOFISHER_SOURCE_SHA256
        assert bank.meta["restamp"]["from_working_tree_sha256"] \
            == BUILD_SOURCE_SHA256


def test_a_restamped_shipped_bank_records_the_bank_it_came_from():
    """A shipped bank was either re-stamped once from the e041d5e build or
    rebuilt by the current bank code (scripts/rebuild_shipped_banks.sh)."""
    root = Path(__file__).resolve().parents[2]
    paths = [resources.data_file(name) for name in EXPECTED_SHA256
             if name.startswith("fisher_bank")]
    paths += [root / "data" / name for name in BULL_BANK_SHA256]
    assert len(paths) == 5
    for path in paths:
        meta = FisherBank(path).meta
        if "restamp" not in meta:
            continue
        assert meta["restamp"]["from_working_tree_sha256"] \
            == BUILD_SOURCE_SHA256
        assert meta["restamp"]["from_source_manifest"] == {
            "include": ["pyproject.toml", "src/rfisher/*.py"],
            "exclude": ["src/rfisher/data/fisher_bank*.npz"]}
        assert set(meta["restamp"]["member_sha256"]) == {
            "F.npy", "t_grid.npy", "zs.npy", "zc.npy", "paramnames.npy"}


def test_missing_packaged_data_fails_clearly():
    with pytest.raises(FileNotFoundError, match="package data is missing"):
        resources.data_file("not-distributed.dat")


def test_defaults_work_through_a_zip_importer(tmp_path):
    """Exercise archive-backed Traversables, not only pathlib resources."""
    package_root = Path(__file__).resolve().parents[2] / "src" / "rfisher"
    projects_root = Path(__file__).resolve().parents[2] / "projects"
    archive = tmp_path / "rfisher-test.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # The package, and its projects where the wheel puts them.
        for root, prefix in ((package_root, Path("rfisher")),
                             (projects_root, Path("rfisher") / "projects")):
            for source in root.rglob("*"):
                if (source.is_file() and "__pycache__" not in source.parts
                        and source.suffix != ".pyc"):
                    zf.write(source, prefix / source.relative_to(root))

    code = f"""
import sys
sys.path.insert(0, {str(archive)!r})
from rfisher.forecast.radiofisher_bao import legacy_masks as channels
from rfisher.forecast.radiofisher_bao import api
from rfisher.forecast.radiofisher_bao.bank import resources
assert '.zip/' in str(resources.DEFAULT_BANK)
forecast = api.load()
assert forecast.bank.meta['config'] == 'chime2022'
assert len(channels.legacy_rate_fractions()) == 23
for resource_name in resources.RADIOFISHER_FILESYSTEM_NAMES:
    with resources.data_file(resource_name).open('rb') as stream:
        assert stream.read(1)
try:
    resources.filesystem_data_file('cache_pk.dat')
except RuntimeError as exc:
    assert 'install the rfisher wheel' in str(exc)
else:
    raise AssertionError('zip-imported cache unexpectedly had a filesystem path')
result = api.required_time(forecast, uniform=0.0)
assert result['hours'] > 0.0
print(result['hours'])
"""
    completed = subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path,
        text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_built_wheel_contains_and_loads_named_banks_and_manifest(tmp_path):
    root = Path(__file__).resolve().parents[2]
    wheel_dir = tmp_path / "wheel"
    wheel_dir.mkdir()
    built = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps",
         "--wheel-dir", str(wheel_dir), str(root)],
        cwd=tmp_path, text=True, capture_output=True, check=False)
    assert built.returncode == 0, built.stdout + built.stderr
    wheel = next(wheel_dir.glob("rfisher-*.whl"))
    code = f"""
import importlib.util
import sys
sys.path.insert(0, {str(wheel)!r})
import rfisher
from rfisher.forecast.radiofisher_bao.bank import resources
from rfisher.forecast.radiofisher_bao.bank.banks import (
    BANK_SCHEMA_VERSION, FisherBank)
assert rfisher.__version__ == '4.0.0'
assert importlib.util.find_spec('baonoise') is None
assert set(resources.BANK_NAMES) == {{'planck2018', 'pact2025', 'cmbspa2026'}}
for cosmology in resources.BANK_NAMES:
    bank = FisherBank(resources.bank_file(cosmology))
    assert bank.schema_version == BANK_SCHEMA_VERSION
    assert bank.meta['cosmology'] == cosmology
for resource_name in resources.RADIOFISHER_FILESYSTEM_NAMES:
    with resources.data_file(resource_name).open('rb') as stream:
        assert stream.read(1)
"""
    loaded = subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path,
        text=True, capture_output=True, check=False)
    assert loaded.returncode == 0, loaded.stdout + loaded.stderr
