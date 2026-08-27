#!/usr/bin/env python3
# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Stage D tables from calibrated P. Does not touch OFR/TRI sources."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "src")]

from whiteforge._bootstrap import ensure_paths  # noqa: E402

ensure_paths()

from floodmap.config import HUC8  # noqa: E402
from floodmap.stage_d import run_stage_d  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--template",
        type=Path,
        default=REPO / "data" / "interim" / f"nlcd_impervious_2021_{HUC8}.tif",
    )
    parser.add_argument("--out", type=Path, default=REPO / "logs" / "stage_d")
    parser.add_argument(
        "--stage-a-report",
        type=Path,
        default=REPO / "logs" / "stage_a" / "stage_a_report.json",
    )
    parser.add_argument(
        "--stage-c-report",
        type=Path,
        default=REPO / "logs" / "stage_c" / "stage_c_report.json",
    )
    parser.add_argument(
        "--tri",
        type=Path,
        default=REPO / "data" / "interim" / "tri_huc.csv",
    )
    args = parser.parse_args()
    report = run_stage_d(
        template_path=args.template,
        interim_dir=REPO / "data" / "interim",
        out_dir=args.out,
        stage_a_report_path=args.stage_a_report,
        stage_c_report_path=args.stage_c_report,
        tri_csv=args.tri,
    )
    head = next(s for s in report["d1_by_t"] if s["headline"])
    print(
        f"stage {report['stage']} gate={report['gate']} "
        f"n_tris={report['n_tris_huc_year']} "
        f"d1_unshaded={report['d1_n_unshaded_x']} "
        f"d1_t0.75_max={head['n_d1_p_max']} "
        f"d2={report['d2_n']} code1={report['d2_n_code1']} code2={report['d2_n_code2']} "
        f"p_source={report['p_source']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
