"""The science register and the selector policy of a project, side-checked.

A project directory holds two registers: ``science_register.json`` (the
science settings the forecast adapter and the tolerance table depend on) and
``selector_policy.json`` (how the verdict chooses inside the deployable set,
and the screen's precedence). Every entry records its value with units,
basis, status, rationale, evidence and sensitivity values, and is tagged with
its side. This loader reads only ``side: science``: it refuses a file or an
entry of the detector side, whose register belongs to the detector package.

This module holds no values of its own. :func:`default_project` names the
project a library default is read from: the ``projects/chime_bao`` directory
of the source checkout, or the copy an installed package carries.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

SIDE = "science"
FILES = {"science_register.json": "rfisher_science_register_v1",
         "selector_policy.json": "rfisher_selector_policy_v1"}
KEYS = ("id", "side", "value", "units", "basis", "status", "rationale",
        "evidence", "sensitivity_values")
BASES = ("instrument", "derivation", "literature", "empirical", "policy",
         "implementation")
STATUSES = ("derived", "locked", "provisional", "open", "conditional",
            "historical")
DEFAULT_PROJECT = "chime_bao"


class RegisterError(ValueError):
    """A register file does not have the declared form."""


class RegisterSideError(RegisterError):
    """A register file or entry belongs to the other side of the handoff."""


def _freeze(value):
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    return value


def _thaw(value):
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    if isinstance(value, Mapping):
        return {k: _thaw(v) for k, v in value.items()}
    return value


@dataclass(frozen=True)
class Decision:
    """One register entry."""

    id: str
    side: str
    value: Any
    units: str
    basis: str
    status: str
    rationale: str
    evidence: tuple[str, ...]
    sensitivity_values: tuple[Any, ...]
    register: str

    def record(self) -> dict:
        """The JSON form, as the register file writes it."""
        return {k: _thaw(getattr(self, k)) for k in KEYS}


@dataclass(frozen=True)
class Policy:
    """Both registers of a project."""

    project: Any
    decisions: Mapping[str, Decision]

    def decision(self, id: str) -> Decision:
        try:
            return self.decisions[id]
        except KeyError as exc:
            raise KeyError(f"no science decision {id!r} in {self.project}") \
                from exc

    def value(self, id: str):
        """The frozen value of an entry (lists become tuples)."""
        return self.decision(id).value

    def ids(self, register: str | None = None) -> tuple[str, ...]:
        return tuple(sorted(i for i, d in self.decisions.items()
                            if register is None or d.register == register))

    def canonical_json(self) -> str:
        payload = {name: [self.decisions[i].record()
                          for i in self.ids(name)] for name in FILES}
        return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False)

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _decision(entry, *, register: str, where: str) -> Decision:
    if not isinstance(entry, Mapping) or set(entry) != set(KEYS):
        raise RegisterError(f"{where}: an entry holds exactly {list(KEYS)}")
    ident = entry["id"]
    if not isinstance(ident, str) or any(p == "" for p in ident.split(".")):
        raise RegisterError(f"{where}: id must use non-empty dotted parts")
    if entry["side"] != SIDE:
        raise RegisterSideError(
            f"{where}: {ident!r} is tagged side {entry['side']!r}; the "
            f"science loader refuses it")
    if entry["basis"] not in BASES or entry["status"] not in STATUSES:
        raise RegisterError(f"{where}: {ident!r} has an unknown basis or "
                            "status")
    evidence = entry["evidence"]
    if not isinstance(evidence, list) or not all(
            isinstance(e, str) for e in evidence):
        raise RegisterError(f"{where}: evidence must be a list of strings")
    if entry["status"] not in ("open", "historical") and not evidence:
        raise RegisterError(f"{where}: {ident!r} needs evidence")
    if not isinstance(entry["sensitivity_values"], list):
        raise RegisterError(f"{where}: sensitivity_values must be a list")
    if not isinstance(entry["rationale"], str) or not entry["rationale"].strip():
        raise RegisterError(f"{where}: {ident!r} needs a rationale")
    return Decision(
        id=ident, side=SIDE, value=_freeze(entry["value"]),
        units=entry["units"], basis=entry["basis"], status=entry["status"],
        rationale=entry["rationale"], evidence=tuple(evidence),
        sensitivity_values=_freeze(entry["sensitivity_values"]),
        register=register)


def read_register(path) -> list[Decision]:
    """The entries of one register file, side-checked.

    ``path`` is a filesystem path or a package resource (a ``Traversable``).
    """
    if isinstance(path, str):
        path = Path(path)
    name = path.name
    if name not in FILES:
        raise RegisterError(f"{path}: a science register is one of "
                            f"{sorted(FILES)}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping) or not {"schema", "side",
                                             "decisions"} <= set(data):
        raise RegisterError(f"{path}: needs schema, side and decisions")
    if data["side"] != SIDE:
        raise RegisterSideError(f"{path}: a {data['side']!r} register cannot "
                                "be loaded on the science side")
    if data["schema"] != FILES[name]:
        raise RegisterError(f"{path}: schema must be {FILES[name]!r}")
    return [_decision(e, register=name, where=str(path))
            for e in data["decisions"]]


_LOADED: dict[str, Policy] = {}


def _load(key: str, root) -> Policy:
    if key not in _LOADED:
        decisions: dict[str, Decision] = {}
        for name in FILES:
            for d in read_register(root / name):
                if d.id in decisions:
                    raise RegisterError(f"{key}: {d.id!r} is in two registers")
                decisions[d.id] = d
        _LOADED[key] = Policy(project=root,
                              decisions=MappingProxyType(decisions))
    return _LOADED[key]


def default_project():
    """The default project: the checkout's ``projects/chime_bao``, or the copy
    an installed package carries as ``rfisher/projects/chime_bao``.

    The first is a filesystem path; the second is a package resource, which
    may live in an archive.
    """
    checkout = Path(__file__).resolve().parents[2] / "projects" / DEFAULT_PROJECT
    if all((checkout / name).is_file() for name in FILES):
        return checkout
    installed = files("rfisher").joinpath("projects", DEFAULT_PROJECT)
    if all(installed.joinpath(name).is_file() for name in FILES):
        return installed
    raise FileNotFoundError(f"no {DEFAULT_PROJECT} project in the checkout "
                            "or the installed package")


def load(project=None) -> Policy:
    """Both registers of ``project`` (default: :func:`default_project`)."""
    root = project if project is not None else default_project()
    if isinstance(root, (str, Path)):
        root = Path(root).resolve()
    return _load(str(root), root)


def value(id: str, project=None):
    """The value of one entry of ``project``'s registers."""
    return load(project).value(id)


def sha256(project=None) -> str:
    """Digest of both registers' entries, in canonical JSON."""
    return load(project).sha256()
