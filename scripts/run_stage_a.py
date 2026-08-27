#!/usr/bin/env python3
# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Stage A live fetch. Warp to nlcd_2021. Do not start Stage B."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "src")]

from whiteforge._bootstrap import ensure_paths  # noqa: E402

ensure_paths()

from floodmap.config import HUC8, TRI_YEAR_CANDIDATES  # noqa: E402
from floodmap.errors import GateError  # noqa: E402
from floodmap.stage_a import run_stage_a  # noqa: E402
from floodmap.tri import fetch_tri_envirofacts  # noqa: E402


def fetch_tri_1a(raw_dir: Path) -> tuple[str, int]:
    import csv
    import io

    raw_dir.mkdir(parents=True, exist_ok=True)
    last_err: Exception | None = None
    for year in TRI_YEAR_CANDIDATES:
        try:
            rows = fetch_tri_envirofacts(year=year)
            dest = raw_dir / f"tri_in_{year}.json"
            dest.write_text(json.dumps({"year": year, "n_rows": len(rows)}), encoding="utf-8")
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            w.writeheader()
            for rec in rows:
                w.writerow({k: "" if rec.get(k) is None else rec.get(k) for k in w.fieldnames})
            return buf.getvalue(), year
        except (GateError, OSError, ValueError) as exc:
            last_err = exc
            continue
    raise GateError(f"TRI Envirofacts download failed: {last_err}")


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
    parser.add_argument("--out", type=Path, default=REPO / "logs" / "stage_a")
    args = parser.parse_args()
    tri_text, year = fetch_tri_1a(REPO / "data" / "raw")
    report = run_stage_a(
        huc_path=args.huc,
        template_path=args.template,
        raw_dir=REPO / "data" / "raw",
        interim_dir=REPO / "data" / "interim",
        out_dir=args.out,
        tri_text=tri_text,
        tri_year=year,
    )
    n2 = (report.get("mask_value_counts") or {}).get("2", 0)
    reaches = report.get("ofr_reaches_intersecting_huc") or []
    zc = report.get("zone_class_counts") or {}
    print(
        f"stage {report['stage']} gate={report['gate']} "
        f"template={report['template_fingerprint']['width']}x"
        f"{report['template_fingerprint']['height']} "
        f"mask2={n2} reaches={len(reaches)} "
        f"n_tris_huc_year={report['tri']['n_tris_huc_year']} "
        f"firm_ok={report.get('firm_unshaded_x_ok')} "
        f"unshaded_x={zc.get('unshaded_x')} sfha={zc.get('sfha')} "
        f"hsg_incomplete={report.get('hsg_incomplete')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
