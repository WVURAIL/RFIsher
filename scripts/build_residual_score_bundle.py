#!/usr/bin/env python3
"""Build an exact residual-score bundle from declared calibration inputs."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np

from rfisher.residual_scores import (ResidualScoreRefused,
                                     build_residual_score_bundle)


def _load_mask(path: str, name: str) -> np.ndarray:
    source = Path(path).expanduser()
    try:
        values = np.load(source, allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise ResidualScoreRefused(f"{name} is not a safe NPY array") from exc
    if isinstance(values, np.lib.npyio.NpzFile):
        values.close()
        raise ResidualScoreRefused(f"{name} must be a single NPY array")
    result = np.asarray(values)
    if result.dtype != np.dtype(bool) or result.ndim != 1:
        raise ResidualScoreRefused(
            f"{name} must be a one-dimensional boolean array")
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Build exact Q16 scores from a current per-pilot product.")
    result.add_argument("product", help="current v5 per-pilot NPZ product")
    result.add_argument("--selected-frames", required=True,
                        help="explicit accepted-frame boolean NPY array")
    result.add_argument("--anchor-bin", required=True, type=int)
    result.add_argument("--designated-half-width", required=True, type=int)
    result.add_argument("--bulk-mask", required=True,
                        help="declared 256-bin boolean NPY array")
    result.add_argument("--output", required=True,
                        help="output residual-score NPZ bundle")
    result.add_argument("--overwrite", action="store_true",
                        help="replace an existing output")
    return result


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        output_path = Path(args.output).expanduser()
        if output_path.exists() and not args.overwrite:
            raise ResidualScoreRefused(
                "output already exists; pass --overwrite to replace it")
        bundle = build_residual_score_bundle(
            args.product,
            _load_mask(args.selected_frames, "selected_frames"),
            anchor_bin=args.anchor_bin,
            designated_half_width=args.designated_half_width,
            bulk_mask=_load_mask(args.bulk_mask, "bulk_mask"))
        output = bundle.save(output_path, overwrite=args.overwrite)
    except ResidualScoreRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {output}")
    print(f"content_sha256={bundle.content_sha256}")
    print(f"frames={bundle.frame_count} rho={bundle.supported_rho_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
