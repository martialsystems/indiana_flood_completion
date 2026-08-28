#!/usr/bin/env python3
# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Write README cartography PNGs. Calibrated P only. Does not rewrite D."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "src")]

from whiteforge._bootstrap import ensure_paths  # noqa: E402

ensure_paths()

from floodmap.cartography import write_cartography  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPO / "logs" / "stage_d")
    args = parser.parse_args()
    info = write_cartography(
        interim_dir=REPO / "data" / "interim",
        facilities_csv=REPO / "logs" / "stage_d" / "facilities.csv",
        headline_csv=REPO / "logs" / "stage_d" / "d1_headline.csv",
        out_dir=args.out,
    )
    print(
        f"cartography disagreement={info['disagreement_png']} "
        f"zooms={info['zooms_png']} ofr={info['ofr_reaches_png']} "
        f"ofr_poly={info['n_ofr_polygons']} p_source={info['p_source']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
