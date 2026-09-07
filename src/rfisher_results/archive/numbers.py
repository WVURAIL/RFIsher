"""``numbers.json``: every number a table emits, keyed, so the dissertation's
``\\rerun{}`` markers can be verified mechanically.

Each export writes one document beside its table (``numbers/<export>.numbers.json``)
with the producing repository and commit, the inputs it read (paths and
SHA-256), and a list of numbers: a stable key, the value, its kind (float,
int, text, range), the renderings the text may use, the printed precision,
and where it came from (table, row, column). The dissertation's
``STUBS_rerun_inventory.csv`` (``file, line, section, value, context``) lists
every wrapped marker; :func:`match_markers` normalizes each marker the way the
number gate does (strip ``$``, ``\\rerun{}``, ``\\mathbf{}``, ``~``, ``\\,``,
``{,}``; ``\\times`` to ``x``; dashes to ``-``) and verifies it against the
numbers: a numeric marker verifies when a number's value lies within half a
unit of the marker's last printed digit, or equals a listed rendering; text
and range markers verify by rendering. The report says, per chapter, how many
markers verified, how many changed (a number exists but disagrees) and how
many have no source yet; a chapter is flipped to black only when none
changed and none lack a source.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

SCHEMA = {"name": "rfisher-dissertation-numbers", "version": 1}
KINDS = ("float", "int", "text", "range")
STATUSES = ("measured", "bounded", "refused", "pending", "derived")


@dataclass(frozen=True)
class Number:
    key: str                      # e.g. 'ch08.nulls.coarse_core_width_factor.ch29'
    value: float | int | str | None
    kind: str = "float"
    unit: str = ""
    renderings: tuple[str, ...] = ()
    precision: int | None = None  # decimals the text prints, when known
    status: str = "measured"
    source: dict = field(default_factory=dict)     # {"table": ..., "row": {...}, "column": ...}
    tex: dict = field(default_factory=dict)        # {"label": ..., "row_label": ..., "cell": n}

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"unknown number kind {self.kind!r}")
        if self.status not in STATUSES:
            raise ValueError(f"unknown number status {self.status!r}")


def git_commit(repo: Path | str) -> str:
    try:
        return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True,
                              text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def sha256_of(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass
class NumbersDocument:
    export: str
    producer: dict
    inputs: list = field(default_factory=list)
    numbers: list = field(default_factory=list)

    @classmethod
    def new(cls, export: str, *, repository: str, commit: str, script: str, generated: str) -> "NumbersDocument":
        return cls(export=export, producer={"repository": repository, "commit": commit, "script": script, "generated": generated})

    def add_input(self, path: Path | str, **extra) -> None:
        p = Path(path)
        self.inputs.append({"path": str(p), "sha256": sha256_of(p) if p.is_file() else None, **extra})

    def add(self, number: Number) -> None:
        if any(n.key == number.key for n in self.numbers):
            raise ValueError(f"duplicate number key {number.key!r}")
        self.numbers.append(number)

    def to_json(self) -> dict:
        return {"schema": dict(SCHEMA), "export": self.export, "producer": dict(self.producer), "inputs": list(self.inputs),
                "numbers": [_number_json(n) for n in self.numbers]}

    def write(self, path: Path | str) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), indent=1, sort_keys=False) + "\n", encoding="utf-8")
        return path


def _number_json(n: Number) -> dict:
    d = asdict(n)
    v = d["value"]
    if isinstance(v, float) and not math.isfinite(v):
        d["value"] = None
    d["renderings"] = list(n.renderings)
    return d


def load_numbers(paths: Iterable[Path | str]) -> list[Number]:
    out = []
    for path in paths:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        if doc.get("schema", {}).get("name") != SCHEMA["name"]:
            raise ValueError(f"{path}: not a numbers document")
        for item in doc["numbers"]:
            out.append(Number(key=item["key"], value=item.get("value"), kind=item.get("kind", "float"), unit=item.get("unit", ""),
                              renderings=tuple(item.get("renderings", ())), precision=item.get("precision"),
                              status=item.get("status", "measured"), source=item.get("source", {}), tex=item.get("tex", {})))
    return out


# --------------------------------------------------------------- markers
@dataclass(frozen=True)
class Marker:
    file: str
    line: int
    section: str
    value: str
    context: str
    key: str = ""             # optional binding to a numbers key (inventory 'key' column)


def load_inventory(path: Path | str) -> list[Marker]:
    rows = []
    with Path(path).open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows.append(Marker(row["file"], int(row["line"]), row.get("section", ""), row["value"], row.get("context", ""),
                               row.get("key", "") or ""))
    return rows


_WRAPPERS = re.compile(r"\\(?:rerun|mathbf|textbf|mathrm|text|rm|si|num)\{")


def normalize_marker(value: str) -> str:
    """The number gate's normalization for one marker: unwrap macros, drop math delimiters."""
    s = value
    for _ in range(6):                          # peel nested wrappers
        m = _WRAPPERS.search(s)
        if not m:
            break
        start = m.start()
        depth, i = 0, m.end() - 1
        while i < len(s):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        s = s[:start] + s[m.end():i] + s[i + 1:]
    s = s.replace("$", "").replace("~", " ").replace("\\,", "").replace("{,}", ",")
    s = s.replace("\\times", "x").replace("---", "-").replace("--", "-").replace("\\%", "%").replace("\\ ", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


_NUMBER = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?")


def parse_numeric(normalized: str) -> tuple[float, int] | None:
    """First numeric literal and its decimal count; digit-group commas removed."""
    m = _NUMBER.search(normalized)
    if not m:
        return None
    literal = m.group(0).replace(",", "")
    decimals = len(literal.split(".")[1].split("e")[0].split("E")[0]) if "." in literal else 0
    try:
        return float(literal), decimals
    except ValueError:
        return None


def half_ulp(decimals: int) -> float:
    return 0.5 * 10.0 ** (-decimals)


@dataclass(frozen=True)
class MarkerMatch:
    marker: Marker
    status: str               # 'verified' | 'changed' | 'no-source'
    key: str
    number_value: float | int | str | None
    detail: str


def match_markers(markers: Sequence[Marker], numbers: Sequence[Number]) -> list[MarkerMatch]:
    """Verify each marker against the numbers. A marker bound to a key (inventory
    'key' column) is checked against that number only; an unbound marker is
    checked against every number whose renderings or value fit, and reports
    'no-source' when none does."""
    by_key = {n.key: n for n in numbers}
    out = []
    for marker in markers:
        norm = normalize_marker(marker.value)
        candidates = [by_key[marker.key]] if marker.key and marker.key in by_key else (list(numbers) if not marker.key else [])
        if not candidates:
            out.append(MarkerMatch(marker, "no-source", marker.key, None, "no number carries this key"))
            continue
        parsed = parse_numeric(norm)
        verified = None
        nearest = None
        for n in candidates:
            if norm in n.renderings or (isinstance(n.value, str) and norm == normalize_marker(n.value)):
                verified = n
                break
            if parsed and isinstance(n.value, (int, float)) and n.value is not None and not isinstance(n.value, bool):
                literal, decimals = parsed
                tol = half_ulp(n.precision if n.precision is not None else decimals)
                if math.isfinite(float(n.value)) and abs(float(n.value) - literal) <= tol + 1e-12:
                    verified = n
                    break
                if marker.key and nearest is None:
                    nearest = n
        if verified is not None:
            out.append(MarkerMatch(marker, "verified", verified.key, verified.value, f"{norm!r} matches {verified.key}"))
        elif marker.key and nearest is not None:
            out.append(MarkerMatch(marker, "changed", marker.key, nearest.value,
                                   f"{norm!r} vs {nearest.value!r} ({nearest.status})"))
        elif marker.key:
            out.append(MarkerMatch(marker, "changed", marker.key, by_key[marker.key].value, f"{norm!r} does not render {marker.key}"))
        else:
            out.append(MarkerMatch(marker, "no-source", "", None, f"no number renders {norm!r}"))
    return out


def chapter_report(matches: Sequence[MarkerMatch]) -> dict[str, dict]:
    """Per file: counts by status and whether the chapter may be flipped to black."""
    report: dict[str, dict] = {}
    for m in matches:
        rec = report.setdefault(m.marker.file, {"verified": 0, "changed": 0, "no-source": 0})
        rec[m.status] += 1
    for rec in report.values():
        rec["flip"] = rec["changed"] == 0 and rec["no-source"] == 0
    return report
