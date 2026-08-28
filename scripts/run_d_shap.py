#!/usr/bin/env python3
# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""SHAP for C features and the five P_max cells. Does not rewrite P."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "src")]

from whiteforge._bootstrap import ensure_paths  # noqa: E402

ensure_paths()

from floodmap.config import HUC8  # noqa: E402
from floodmap.explain import run_d_shap  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--template",
        type=Path,
        default=REPO / "data" / "interim" / f"nlcd_impervious_2021_{HUC8}.tif",
    )
    parser.add_argument("--out", type=Path, default=REPO / "logs" / "stage_d")
    args = parser.parse_args()
    rep = run_d_shap(
        template_path=args.template,
        interim_dir=REPO / "data" / "interim",
        out_dir=args.out,
        facilities_csv=REPO / "logs" / "stage_d" / "facilities.csv",
        headline_csv=REPO / "logs" / "stage_d" / "d1_headline.csv",
    )
    top = rep["global_mean_abs_shap"][0]["feature"]
    print(
        f"shap n_train={rep['n_train']} top={top} "
        f"headline_cells={len(rep['headline_max_cells'])} hsg={rep['hsg_in_shap']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
