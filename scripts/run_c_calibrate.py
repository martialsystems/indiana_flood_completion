#!/usr/bin/env python3
# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""C addendum: isotonic OOF calibration. Does not overwrite p_sfha.tif."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "src")]

from whiteforge._bootstrap import ensure_paths  # noqa: E402

ensure_paths()

from floodmap.config import HUC8  # noqa: E402
from floodmap.calibrate import run_c_calibration  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--template",
        type=Path,
        default=REPO / "data" / "interim" / f"nlcd_impervious_2021_{HUC8}.tif",
    )
    parser.add_argument("--out", type=Path, default=REPO / "logs" / "stage_c")
    parser.add_argument(
        "--stage-c-report",
        type=Path,
        default=REPO / "logs" / "stage_c" / "stage_c_report.json",
    )
    args = parser.parse_args()
    add = run_c_calibration(
        template_path=args.template,
        interim_dir=REPO / "data" / "interim",
        out_dir=args.out,
        stage_c_report_path=args.stage_c_report,
    )
    print(
        f"calibrated mean_p={add['oof_mean_p_calibrated']:.4f} "
        f"(raw {add['oof_mean_p_raw']:.4f}) "
        f"brier={add['brier_calibrated']:.4f} (raw {add['brier_raw']:.4f}) "
        f"pr_auc={add['pr_auc_calibrated']:.4f} (raw {add['pr_auc_raw']:.4f})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
