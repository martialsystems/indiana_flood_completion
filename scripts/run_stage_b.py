#!/usr/bin/env python3
# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Stage B live hydrology. Warp to nlcd_2021. Do not start Stage C."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "src")]

from whiteforge._bootstrap import ensure_paths  # noqa: E402

ensure_paths()

from floodmap.config import HUC8  # noqa: E402
from floodmap.stage_b import run_stage_b  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--huc",
        type=Path,
        default=REPO / "data" / "raw" / f"huc{HUC8}.geojson",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=REPO / "data" / "interim" / f"nlcd_impervious_2021_{HUC8}.tif",
    )
    parser.add_argument("--out", type=Path, default=REPO / "logs" / "stage_b")
    parser.add_argument(
        "--stage-a-report",
        type=Path,
        default=REPO / "logs" / "stage_a" / "stage_a_report.json",
    )
    args = parser.parse_args()
    report = run_stage_b(
        huc_path=args.huc,
        template_path=args.template,
        interim_dir=REPO / "data" / "interim",
        out_dir=args.out,
        stage_a_report_path=args.stage_a_report,
    )
    print(
        f"stage {report['stage']} gate={report['gate']} "
        f"twi_finite={report['twi_finite_on_dem_valid']} "
        f"n_slope_floor={report['n_slope_floor']} "
        f"n_waterbody_cells={report['n_waterbody_cells']} "
        f"hsg_in_stack={report['hsg_in_stack']} "
        f"stage_c_started={report['stage_c_started']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
