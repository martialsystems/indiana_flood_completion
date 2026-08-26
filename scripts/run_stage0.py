#!/usr/bin/env python3
# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Stage 0: occupancy freeze, HUC clip, 30 m template, claim scan."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "src")]

from whiteforge._bootstrap import ensure_paths  # noqa: E402

ensure_paths()

from floodmap.config import TEMPLATE_KIND_FIXTURE  # noqa: E402
from floodmap.stage0 import run_stage0  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--huc", type=Path, required=True)
    parser.add_argument("--template", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--huc-wkid", type=int, default=None)
    parser.add_argument(
        "--template-kind",
        default=TEMPLATE_KIND_FIXTURE,
        help="fixture (CI) or nlcd_2021 (live). Stage A refuses fixture.",
    )
    args = parser.parse_args()
    report = run_stage0(
        huc_path=args.huc,
        out_dir=args.out,
        template_path=args.template,
        huc_wkid=args.huc_wkid,
        template_kind=args.template_kind,
    )
    print(
        f"stage {report['stage']} gate={report['gate']} "
        f"huc={report['huc8']} template={report['template_kind']} "
        f"{report['template_shape'][1]}x{report['template_shape'][0]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
