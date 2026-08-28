#!/usr/bin/env python3
# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Five-site Indiana 2025 parcels. Does not rewrite D tables."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "src")]

from whiteforge._bootstrap import ensure_paths  # noqa: E402

ensure_paths()

from floodmap.parcels import run_five_site_parcels  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPO / "logs" / "parcels")
    args = parser.parse_args()
    info = run_five_site_parcels(
        interim_dir=REPO / "data" / "interim",
        facilities_csv=REPO / "logs" / "stage_d" / "facilities.csv",
        headline_csv=REPO / "logs" / "stage_d" / "d1_headline.csv",
        out_dir=args.out,
    )
    readings = "; ".join(f"{r['name']} p_mean {r['p_mean']:.3f}={r['reading']}" for r in info["sites"])
    print(
        f"parcels n={info['n_sites']} rewritten={info['d_tables_rewritten']} "
        f"png={info['zooms_png']} {readings}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
