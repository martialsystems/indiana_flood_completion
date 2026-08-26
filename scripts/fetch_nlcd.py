#!/usr/bin/env python3
# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "src")]

from floodmap.config import HUC8, TEMPLATE_KIND_NLCD  # noqa: E402
from floodmap.fetch import default_get_bytes  # noqa: E402
from floodmap.huc import load_huc  # noqa: E402
from floodmap.template import write_nlcd_template  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Clip NLCD 2021 impervious to the HUC.")
    parser.add_argument("--huc", type=Path, required=True)
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO / "data" / "interim" / f"nlcd_impervious_2021_{HUC8}.tif",
    )
    parser.add_argument("--huc-wkid", type=int, default=None)
    args = parser.parse_args()
    huc = load_huc(args.huc, wkid=args.huc_wkid)
    grid = write_nlcd_template(args.out, huc, get_bytes=default_get_bytes)
    print(f"{grid.kind} {grid.width}x{grid.height} {grid.path}")
    assert grid.kind == TEMPLATE_KIND_NLCD
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
