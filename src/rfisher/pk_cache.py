"""Check that the linear P(k) table belongs to the cosmology, or rebuild it.

The table's header binds it to the physical densities, the CAMB settings and a
SHA-256 digest of its numbers. Rebuilding needs the optional ``camb`` package
(pip install -e '.[pk]'). A committed table only needs checking.
"""
import copy
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path

import numpy as np

CACHE_FORMAT = "baonoise-pk-v2"   # the format name the committed table carries
DEFAULT_KMAX_H = 20.0
DEFAULT_NPOINTS = 1400
DEFAULT_AS = 2.1e-9
DEFAULT_TAU = 0.06
NEUTRINO_MASS_DENSITY_EV = 93.04


def physical_densities(cosmo: dict) -> dict:
    """Baryon, cold dark matter and neutrino densities (omega h^2).

    ``omega_M_0`` is the total matter density and covers the massive neutrinos. When
    the explicit ``ombh2``/``omch2``/``omnuh2`` triplet is given, it is used in place of
    the densities derived from ``omega_b_0``, ``omega_M_0``, and ``mnu``.
    """
    explicit = ("ombh2", "omch2", "omnuh2")
    present = [key for key in explicit if key in cosmo]
    if present and len(present) != 3:
        raise ValueError("explicit physical densities are all-or-none")
    if present:
        out = {key: float(cosmo[key]) for key in explicit}
    else:
        h = float(cosmo["h"])
        ombh2 = float(cosmo["omega_b_0"]) * h**2
        omnuh2 = float(cosmo.get("mnu", 0.0)) / NEUTRINO_MASS_DENSITY_EV
        omch2 = float(cosmo["omega_M_0"]) * h**2 - ombh2 - omnuh2
        out = {"ombh2": ombh2, "omch2": omch2, "omnuh2": omnuh2}
    if any(not np.isfinite(v) or v < 0 for v in out.values()):
        raise ValueError(f"unphysical densities: {out}")
    return out


def with_explicit_physical_densities(cosmo: dict) -> dict:
    """Copy a cosmology and attach its density triplet."""
    out = copy.deepcopy(cosmo)
    densities = physical_densities(out)
    out.update(densities)
    out["mnu"] = densities["omnuh2"] * NEUTRINO_MASS_DENSITY_EV
    h2 = float(out["h"]) ** 2
    out["omega_cdm_0"] = densities["omch2"] / h2
    out["omega_nu_0"] = densities["omnuh2"] / h2
    return out


def _canonical_json(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path) -> str:
    return _sha256(Path(path).read_bytes())


def _request(cosmo: dict, kmax_h: float, npoints: int) -> dict:
    densities = physical_densities(cosmo)
    return {
        "format": CACHE_FORMAT,
        "cosmology": {
            "h": float(cosmo["h"]),
            "ns": float(cosmo["ns"]),
            "sigma_8": float(cosmo["sigma_8"]),
            "N_eff": float(cosmo.get("N_eff", 3.046)),
            "mnu": densities["omnuh2"] * NEUTRINO_MASS_DENSITY_EV,
            **densities,
        },
        "settings": {
            "As": DEFAULT_AS,
            "tau": DEFAULT_TAU,
            "kmax_h_mpc": float(kmax_h),
            "minkh_h_mpc": 1e-4,
            "npoints": int(npoints),
            "redshift": 0.0,
            "nonlinear": False,
            "accurate_massive_neutrino_transfers": False,
            "neutrino_input": "omnuh2_active",
        },
    }


def inspect_pk_cache(path) -> dict:
    """The table's header, after checking both digests."""
    raw = Path(path).read_bytes().split(b"\n", 2)
    if len(raw) != 3:
        raise ValueError(f"{path} has no versioned P(k) header")
    first, second, body = raw[0].decode().strip(), raw[1].decode().strip(), raw[2]
    prefix = "# baonoise-meta "
    if not (first.startswith("# ") and first.endswith("#") and second.startswith(prefix)):
        raise ValueError(f"{path} has no versioned P(k) header")
    meta = json.loads(second[len(prefix):])
    if meta.get("format") != CACHE_FORMAT:
        raise ValueError(f"unsupported P(k) table format {meta.get('format')!r}")
    if _sha256(body) != meta.get("data_sha256"):
        raise ValueError(f"{path}: the numbers do not match their digest")
    if first[2:-1] != _sha256(_canonical_json(meta).encode()):
        raise ValueError(f"{path}: the header does not match its digest")
    return meta


def cache_matches(path, cosmo: dict, kmax_h: float = DEFAULT_KMAX_H,
                  npoints: int = DEFAULT_NPOINTS) -> bool:
    """True when the table is intact and was built for this cosmology."""
    try:
        meta = inspect_pk_cache(path)
    except (OSError, ValueError, IndexError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return all(meta.get(key) == value for key, value in _request(cosmo, kmax_h, npoints).items())


def build_pk_cache(cosmo: dict, path, kmax_h: float = DEFAULT_KMAX_H,
                   npoints: int = DEFAULT_NPOINTS) -> Path:  # pragma: no cover - needs camb
    """Run CAMB for ``cosmo`` and write a verified table to ``path``."""
    import camb

    cosmo = with_explicit_physical_densities(cosmo)
    densities = physical_densities(cosmo)
    h = cosmo["h"]
    pars = camb.CAMBparams()
    pars.set_cosmology(H0=100.0 * h, ombh2=densities["ombh2"], omch2=densities["omch2"],
                       omk=0.0, mnu=None, omnuh2_active=densities["omnuh2"],
                       nnu=cosmo.get("N_eff", 3.046), tau=DEFAULT_TAU)
    pars.InitPower.set_params(As=DEFAULT_AS, ns=cosmo["ns"])
    pars.set_matter_power(redshifts=[0.0], kmax=kmax_h, accurate_massive_neutrino_transfers=False)
    pars.NonLinear = camb.model.NonLinear_none
    results = camb.get_results(pars)
    kh, _z, pk = results.get_matter_power_spectrum(minkh=1e-4, maxkh=kmax_h, npoints=npoints)
    renorm = (cosmo["sigma_8"] / results.get_sigma8_0()) ** 2
    stream = io.StringIO(newline="\n")
    np.savetxt(stream, np.column_stack([kh * h, pk[0] * renorm / h**3]))
    body = stream.getvalue().encode()
    meta = {**_request(cosmo, kmax_h, npoints),
            "generator": {"package": "camb", "version": getattr(camb, "__version__", None)
                          or importlib.metadata.version("camb")},
            "data_sha256": _sha256(body)}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(f"# {_sha256(_canonical_json(meta).encode())}#\n".encode()
                     + f"# baonoise-meta {_canonical_json(meta)}\n".encode() + body)
    return path
