#!/usr/bin/env python3
# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Live Stage 0: WBD 05120201 + NLCD 2021 template, then the Stage 0 gate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "src")]

from whiteforge._bootstrap import ensure_paths  # noqa: E402

ensure_paths()

from floodmap.config import (  # noqa: E402
    HUC8,
    NLCD_LAYER,
    NLCD_WMS_URL,
    NLCD_YEAR,
    TEMPLATE_KIND_NLCD,
    WBD_LAYER_URL,
)
from floodmap.fetch import default_get_bytes, fetch_wbd  # noqa: E402
from floodmap.huc import load_huc  # noqa: E402
from floodmap.stage0 import run_stage0  # noqa: E402
from floodmap.template import write_nlcd_template  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--out", type=Path, default=REPO / "logs" / "stage0")
    args = parser.parse_args()
    raw = REPO / "data" / "raw"
    interim = REPO / "data" / "interim"
    huc_path = raw / f"huc{HUC8}.geojson"
    template_path = interim / f"nlcd_impervious_2021_{HUC8}.tif"
    if args.force or not huc_path.is_file():
        huc_path = fetch_wbd(raw)
    huc = load_huc(huc_path)
    if args.force or not template_path.is_file():
        write_nlcd_template(template_path, huc, get_bytes=default_get_bytes)
    report = run_stage0(
        huc_path=huc_path,
        out_dir=args.out,
        template_path=template_path,
        template_kind=TEMPLATE_KIND_NLCD,
        extra={
            "wbd_layer": WBD_LAYER_URL,
            "nlcd_wms": NLCD_WMS_URL,
            "nlcd_layer": NLCD_LAYER,
            "nlcd_year": NLCD_YEAR,
        },
    )
    print(
        f"stage {report['stage']} gate={report['gate']} "
        f"huc={report['huc8']} template={report['template_kind']} "
        f"{report['template_shape'][1]}x{report['template_shape'][0]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
