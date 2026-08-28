#!/usr/bin/env python3
# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Write the D Folium map. Calibrated P only."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "src")]

from whiteforge._bootstrap import ensure_paths  # noqa: E402

ensure_paths()

from floodmap.map_d import build_d_map  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPO / "logs" / "stage_d" / "map.html")
    args = parser.parse_args()
    info = build_d_map(
        interim_dir=REPO / "data" / "interim",
        facilities_csv=REPO / "logs" / "stage_d" / "facilities.csv",
        headline_csv=REPO / "logs" / "stage_d" / "d1_headline.csv",
        dest_html=args.out,
    )
    print(
        f"map {info['path']} points={info['n_points']} "
        f"headline={info['n_headline']} ofr_poly={info['n_ofr_polygons']} "
        f"p_source={info['p_source']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
