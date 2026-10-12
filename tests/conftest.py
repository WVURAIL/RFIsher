import pytest

from rfisher import inputs


@pytest.fixture(scope="session")
def shared():
    """Cosmology, experiment and background, loaded once."""
    cosmo = inputs.cosmology()
    return cosmo, inputs.experiment(), inputs.background(cosmo)
