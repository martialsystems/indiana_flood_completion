# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Stage D tables: D1 unshaded_x × calibrated P, D2 2008 coverage. No SHAP."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.warp import transform as rio_transform

from floodmap.align import require_live_template, template_fingerprint
from floodmap.claims import require_clean, scan_obj
from floodmap.codes import (
    D1_ZONE_CLASS,
    MASK_IN_HUC_UNMAPPED,
    MASK_OFR_OR_HWM,
    P_DEFINITION,
    ZONE_CLASS_NAME,
    ZONE_SHADED_X,
    d1_eligible,
    validate_d_report,
)
from floodmap.config import (
    D_BUFFER_RADIUS_CELLS,
    D_HEADLINE_T,
    D_THRESHOLDS,
    D1_HEADER,
    FIRM_LIVE_MIN_HEIGHT,
    FIRM_LIVE_MIN_WIDTH,
    FROZEN_OCCUPANCY_PATH,
    HUC8,
    LOCKED_TRANSFORM_SHA256,
    P_SFHA_CALIBRATED_NAME,
    P_SFHA_NODATA,
    STATE_CODE,
    TEMPLATE_CRS,
    TEMPLATE_KIND_NLCD,
    TEMPLATE_RES_M,
    VECTOR_CRS,
)
from floodmap.errors import GateError
from floodmap.freeze import verify_freeze
from floodmap.stage_c import _load_report
from floodmap.template import inspect_template
from whiteforge.gate import require_claims, require_freeze, require_stage, require_stale_map


def _write_json(path: Path, obj: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n"
    require_clean(text, source=str(path))
    hits = scan_obj(obj)
    if hits:
        raise GateError(f"stage D claim scan {hits}")
    path.write_text(text, encoding="utf-8")
    return path


def buffer_p_stats(
    p: np.ndarray,
    row: int,
    col: int,
    *,
    radius: int,
    nodata: float,
) -> tuple[float | None, float | None, int]:
    h, w = p.shape
    r0 = max(0, row - radius)
    r1 = min(h, row + radius + 1)
    c0 = max(0, col - radius)
    c1 = min(w, col + radius + 1)
    win = p[r0:r1, c0:c1]
    ok = np.isfinite(win) & (win != nodata)
    if not ok.any():
        return None, None, 0
    vals = win[ok]
    return float(vals.max()), float(vals.mean()), int(ok.sum())


def _load_tri_csv(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise GateError(f"TRI in-HUC csv missing: {path}")
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if len(rows) == 0:
        raise GateError("TRI in-HUC csv is empty")
    out: list[dict[str, Any]] = []
    for rec in rows:
        out.append(
            {
                "key": rec.get("key") or "",
                "frs": rec.get("frs") or "",
                "trifd": rec.get("trifd") or "",
                "name": rec.get("name") or "",
                "lat": float(rec["lat"]),
                "lon": float(rec["lon"]),
                "state": rec.get("state") or STATE_CODE,
                "huc": rec.get("huc") or HUC8,
                "year": int(float(rec.get("year") or 0)),
                "on_site_release_lb": float(rec.get("on_site_release_lb") or 0.0),
                "n_chem": int(float(rec.get("n_chem") or 0)),
            }
        )
    return out


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def run_stage_d(
    *,
    template_path: Path,
    interim_dir: Path,
    out_dir: Path,
    stage_a_report_path: Path,
    stage_c_report_path: Path,
    tri_csv: Path,
) -> dict[str, Any]:
    verify_freeze()
    require_freeze(rewrite_stage0_packet=False)
    require_claims()
    require_stale_map(request_site_publish=False)
    a_report = _load_report(stage_a_report_path, "A")
    c_report = _load_report(stage_c_report_path, "C")
    cal = c_report.get("calibration") or {}
    if not cal.get("probabilities_calibrated"):
        raise GateError("Stage D needs the C isotonic addendum")
    cal_name = Path(str(cal.get("p_source_calibrated") or interim_dir / P_SFHA_CALIBRATED_NAME)).name
    if cal_name != P_SFHA_CALIBRATED_NAME:
        raise GateError("Stage D p_source must be p_sfha_calibrated.tif")
    template = inspect_template(template_path, kind=TEMPLATE_KIND_NLCD)
    require_live_template(template)
    fp = template_fingerprint(template)
    live = template.width >= FIRM_LIVE_MIN_WIDTH and template.height >= FIRM_LIVE_MIN_HEIGHT
    if live and fp["transform_sha256"] != LOCKED_TRANSFORM_SHA256:
        raise GateError("Stage D requires the locked live transform")
    require_stage(
        current_stage="C",
        target_stage="D",
        freeze_verified=True,
        template_kind=TEMPLATE_KIND_NLCD,
        stage_a_report=True,
        stage_b_report=True,
        stage_c_metrics=True,
        inundation_2008_mask=True,
        firm_unshaded_x_ok=True,
        thread_id="stage_d",
    )

    p_path = interim_dir / P_SFHA_CALIBRATED_NAME
    if not p_path.is_file():
        raise GateError(f"missing {P_SFHA_CALIBRATED_NAME}")
    raw_path = interim_dir / "p_sfha.tif"
    if not raw_path.is_file():
        raise GateError("uncalibrated p_sfha.tif must remain on disk")
    with rasterio.open(p_path) as src:
        p = src.read(1)
        p_crs = src.crs
        p_transform = src.transform
    with rasterio.open(interim_dir / "zone_class.tif") as src:
        zone = src.read(1)
    with rasterio.open(interim_dir / "mask_2008.tif") as src:
        mask = src.read(1)

    facilities = _load_tri_csv(tri_csv)
    n_tris = len(facilities)
    if n_tris != int(a_report["tri"]["n_tris_huc_year"]):
        raise GateError(
            f"TRI csv n={n_tris} != n_tris_huc_year {a_report['tri']['n_tris_huc_year']}"
        )
    radius = D_BUFFER_RADIUS_CELLS
    rows_out: list[dict[str, Any]] = []
    n_code1 = 0
    n_code2 = 0
    for rec in facilities:
        if rec["huc"] != HUC8 or rec["state"] != STATE_CODE:
            raise GateError(f"facility {rec['key']} is not huc={HUC8} state={STATE_CODE}")
        xs, ys = rio_transform(
            CRS.from_epsg(VECTOR_CRS),
            p_crs or CRS.from_epsg(TEMPLATE_CRS),
            [rec["lon"]],
            [rec["lat"]],
        )
        row, col = rasterio.transform.rowcol(p_transform, xs[0], ys[0])
        zcode = int(zone[row, col]) if 0 <= row < zone.shape[0] and 0 <= col < zone.shape[1] else 255
        mcode = int(mask[row, col]) if 0 <= row < mask.shape[0] and 0 <= col < mask.shape[1] else 0
        if mcode == MASK_IN_HUC_UNMAPPED:
            n_code1 += 1
        elif mcode == MASK_OFR_OR_HWM:
            n_code2 += 1
        zname = ZONE_CLASS_NAME.get(zcode, "other")
        p_max, p_mean, n_buf = buffer_p_stats(
            p, int(row), int(col), radius=radius, nodata=P_SFHA_NODATA
        )
        item = {
            "key": rec["key"],
            "name": rec["name"],
            "lat": rec["lat"],
            "lon": rec["lon"],
            "huc": HUC8,
            "state": STATE_CODE,
            "year": rec["year"],
            "on_site_release_lb": rec["on_site_release_lb"],
            "zone_class": zname,
            "mask_2008_point": mcode,
            "p_max": p_max,
            "p_mean": p_mean,
            "n_buffer_cells": n_buf,
            "buffer_radius_cells": radius,
            "buffer_m": radius * TEMPLATE_RES_M,
            "d1_eligible": bool(d1_eligible(zname) and p_max is not None),
        }
        for t in D_THRESHOLDS:
            key = f"d1_t_{t:.2f}".replace(".", "p")
            item[key] = bool(item["d1_eligible"] and p_max is not None and p_max >= t)
        item["d2"] = bool(d1_eligible(zname) and mcode == MASK_OFR_OR_HWM)
        rows_out.append(item)

    d1_rows = [r for r in rows_out if r["d1_eligible"]]
    d2_rows = [r for r in rows_out if r["d2"]]
    shaded = [r for r in rows_out if r["zone_class"] == ZONE_CLASS_NAME[ZONE_SHADED_X]]

    def _count_at(rows: list[dict[str, Any]], t: float, pkey: str) -> int:
        return sum(1 for r in rows if r.get(pkey) is not None and r[pkey] >= t)

    def _expected(rows: list[dict[str, Any]], pkey: str, t: float | None = None) -> float:
        total = 0.0
        for r in rows:
            pv = r.get(pkey)
            if pv is None:
                continue
            if t is not None and pv < t:
                continue
            total += float(pv) * float(r["on_site_release_lb"])
        return total

    summary_t: list[dict[str, Any]] = []
    for t in D_THRESHOLDS:
        n_max = _count_at(d1_rows, t, "p_max")
        n_mean = _count_at(d1_rows, t, "p_mean")
        n_sh = sum(
            1
            for r in shaded
            if r.get("p_max") is not None and r["p_max"] >= t
        )
        summary_t.append(
            {
                "t": t,
                "headline": t == D_HEADLINE_T,
                "n_d1_p_max": n_max,
                "n_d1_p_mean": n_mean,
                "n_shaded_x_p_max_sensitivity": n_sh,
                "expected_pounds_p_max": _expected(d1_rows, "p_max", t),
                "expected_pounds_p_mean": _expected(d1_rows, "p_mean", t),
            }
        )

    reaches = list(a_report.get("ofr_reaches_intersecting_huc") or [])
    fields = [
        "key",
        "name",
        "lat",
        "lon",
        "huc",
        "state",
        "year",
        "on_site_release_lb",
        "zone_class",
        "mask_2008_point",
        "p_max",
        "p_mean",
        "n_buffer_cells",
        "d1_eligible",
        "d2",
    ]
    for t in D_THRESHOLDS:
        fields.append(f"d1_t_{t:.2f}".replace(".", "p"))

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(out_dir / "d1.csv", d1_rows, fields)
    _write_csv(out_dir / "d2.csv", d2_rows, fields)
    _write_csv(out_dir / "facilities.csv", rows_out, fields)

    report: dict[str, Any] = {
        "stage": "D",
        "gate": "pass",
        "huc8": HUC8,
        "state": STATE_CODE,
        "p_definition": P_DEFINITION,
        "d1_header": D1_HEADER,
        "d1_zone_class": D1_ZONE_CLASS,
        "p_source": P_SFHA_CALIBRATED_NAME,
        "p_source_raw_kept": "p_sfha.tif",
        "expected_pounds_from_calibrated_p": True,
        "expected_pounds_from_raw_p": False,
        "headline_p": "p_max",
        "headline_t": D_HEADLINE_T,
        "thresholds": list(D_THRESHOLDS),
        "buffer_radius_cells": radius,
        "buffer_m": radius * TEMPLATE_RES_M,
        "n_tris_huc_year": n_tris,
        "reporting_year": int(a_report["tri"]["reporting_year"]),
        "n_dioxin_rows_held_grams": int(a_report["tri"]["n_dioxin_rows_held_grams"]),
        "imported_occupancy_path": str(FROZEN_OCCUPANCY_PATH),
        "d1_n_unshaded_x": len(d1_rows),
        "d1_by_t": summary_t,
        "d2_n": len(d2_rows),
        "d2_n_code1": n_code1,
        "d2_n_code2": n_code2,
        "ofr_reaches_intersecting_huc": reaches,
        "d2_empty_is_coverage": True,
        "template_fingerprint": fp,
        "hsg_in_model": False,
        "shap_written": False,
        "folium_written": False,
    }
    validate_d_report(report)
    require_stage(
        current_stage="D",
        target_stage="D",
        freeze_verified=True,
        template_kind=TEMPLATE_KIND_NLCD,
        stage_a_report=True,
        stage_b_report=True,
        stage_c_metrics=True,
        inundation_2008_mask=True,
        firm_unshaded_x_ok=True,
        thread_id="stage_d_complete",
    )
    _write_json(out_dir / "stage_d_report.json", report)
    return report
