#!/usr/bin/env python3
# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Stage C live: P(sfha | hydro). Do not start Stage D."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "src")]

from whiteforge._bootstrap import ensure_paths  # noqa: E402

ensure_paths()

from floodmap.config import HUC8  # noqa: E402
from floodmap.stage_c import run_stage_c  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--template",
        type=Path,
        default=REPO / "data" / "interim" / f"nlcd_impervious_2021_{HUC8}.tif",
    )
    parser.add_argument("--out", type=Path, default=REPO / "logs" / "stage_c")
    parser.add_argument(
        "--stage-a-report",
        type=Path,
        default=REPO / "logs" / "stage_a" / "stage_a_report.json",
    )
    parser.add_argument(
        "--stage-b-report",
        type=Path,
        default=REPO / "logs" / "stage_b" / "stage_b_report.json",
    )
    args = parser.parse_args()
    report = run_stage_c(
        template_path=args.template,
        interim_dir=REPO / "data" / "interim",
        out_dir=args.out,
        raw_dir=REPO / "data" / "raw",
        stage_a_report_path=args.stage_a_report,
        stage_b_report_path=args.stage_b_report,
    )
    print(
        f"stage {report['stage']} gate={report['gate']} "
        f"pr_auc={report['pr_auc']:.4f} baseline={report['pr_auc_baseline']:.4f} "
        f"brier={report['brier']:.4f} hand_pr_auc={report['hand_negated_pr_auc']:.4f} "
        f"hsg_in_model={report['hsg_in_model']} d_started={report['stage_d_started']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
