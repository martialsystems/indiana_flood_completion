# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Isotonic calibration of OOF P(sfha | hydro). Same HUC-10 cuts. No test leakage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, brier_score_loss

from floodmap.align import interior_mask, require_live_template, template_fingerprint, write_aligned_cog
from floodmap.claims import require_clean, scan_obj
from floodmap.codes import P_DEFINITION
from floodmap.config import (
    FIRM_LIVE_MIN_HEIGHT,
    FIRM_LIVE_MIN_WIDTH,
    HAND_NODATA_RULE,
    HUC8,
    HYDRO_NODATA,
    LOCKED_TRANSFORM_SHA256,
    P_SFHA_CALIBRATED_NAME,
    P_SFHA_NODATA,
    TEMPLATE_KIND_NLCD,
)
from floodmap.errors import GateError
from floodmap.stage_c import _load_report, _metrics, hand_defined
from floodmap.template import inspect_template


def _write_json(path: Path, obj: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n"
    require_clean(text, source=str(path))
    hits = scan_obj(obj)
    if hits:
        raise GateError(f"calibration claim scan {hits}")
    path.write_text(text, encoding="utf-8")
    return path


def calibrate_leave_one_huc10(
    p_raw: np.ndarray,
    y: np.ndarray,
    huc10: np.ndarray,
    valid: np.ndarray,
) -> np.ndarray:
    """Fit isotonic on other HUC-10s' OOF (p, y); apply to the held-out HUC-10."""
    p_cal = np.full(p_raw.shape, P_SFHA_NODATA, dtype=np.float32)
    scored = valid & (p_raw != P_SFHA_NODATA) & np.isfinite(p_raw)
    ids = [int(i) for i in np.unique(huc10[scored]) if int(i) > 0]
    if len(ids) < 2:
        raise GateError("isotonic calibration needs at least two HUC-10 blocks")
    for k in ids:
        train = scored & (huc10 != k)
        test = scored & (huc10 == k)
        if int(train.sum()) < 4 or not test.any():
            continue
        iso = IsotonicRegression(
            y_min=0.0, y_max=1.0, increasing=True, out_of_bounds="clip"
        )
        iso.fit(p_raw[train].astype(np.float64), y[train].astype(np.float64))
        p_cal[test] = iso.predict(p_raw[test].astype(np.float64)).astype(np.float32)
    return p_cal


def run_c_calibration(
    *,
    template_path: Path,
    interim_dir: Path,
    out_dir: Path,
    stage_c_report_path: Path,
) -> dict[str, Any]:
    """Write p_sfha_calibrated.tif. Do not overwrite p_sfha.tif. Do not start D."""
    c_report = _load_report(stage_c_report_path, "C")
    template = inspect_template(template_path, kind=TEMPLATE_KIND_NLCD)
    require_live_template(template)
    fp = template_fingerprint(template)
    live = template.width >= FIRM_LIVE_MIN_WIDTH and template.height >= FIRM_LIVE_MIN_HEIGHT
    if live and fp["transform_sha256"] != LOCKED_TRANSFORM_SHA256:
        raise GateError("calibration requires the locked live transform")
    raw_path = interim_dir / "p_sfha.tif"
    if not raw_path.is_file():
        raise GateError("missing uncalibrated p_sfha.tif")
    inside = interior_mask(template)
    with rasterio.open(raw_path) as src:
        p_raw = src.read(1).astype(np.float32)
        if tuple(src.transform)[:6] != tuple(template.transform)[:6]:
            raise GateError("p_sfha.tif transform mismatch")
    with rasterio.open(interim_dir / "sfha.tif") as src:
        sfha = src.read(1)
    with rasterio.open(interim_dir / "hand.tif") as src:
        hand = src.read(1)
    with rasterio.open(interim_dir / "huc10.tif") as src:
        huc10 = src.read(1)
    defined = hand_defined(hand, inside)
    valid = defined & ((sfha == 0) | (sfha == 1))
    p_cal = calibrate_leave_one_huc10(p_raw, sfha, huc10, valid)
    if not np.all(p_cal[inside & ~defined] == P_SFHA_NODATA):
        raise GateError("calibrated raster filled HAND-nodata")
    # Keep raw file untouched: write a new path only.
    cal_path = interim_dir / P_SFHA_CALIBRATED_NAME
    write_aligned_cog(cal_path, template, p_cal, dtype="float32", nodata=P_SFHA_NODATA)

    scored = valid & (p_raw != P_SFHA_NODATA) & (p_cal != P_SFHA_NODATA)
    y = sfha[scored].astype(np.uint8)
    raw = p_raw[scored].astype(np.float64)
    cal = p_cal[scored].astype(np.float64)
    pi = float((sfha[valid] == 1).mean())
    m_raw = _metrics(y, raw, pi)
    m_cal = _metrics(y, cal, pi)
    if abs(m_cal["pr_auc"] - m_raw["pr_auc"]) > 0.02:
        raise GateError(
            f"calibration moved PR-AUC too far: {m_raw['pr_auc']} -> {m_cal['pr_auc']}"
        )
    addendum = {
        "stage": "C",
        "addendum": "isotonic_oof",
        "method": "isotonic_leave_one_huc10_out",
        "p_source_raw": str(raw_path),
        "p_source_calibrated": str(cal_path),
        "filename_calibrated": P_SFHA_CALIBRATED_NAME,
        "raw_raster_kept": True,
        "hand_nodata_rule": HAND_NODATA_RULE,
        "huc8": HUC8,
        "p_definition": P_DEFINITION,
        "colorbar": P_DEFINITION,
        "n_scored": int(y.size),
        "oof_mean_p_raw": float(raw.mean()),
        "oof_mean_p_calibrated": float(cal.mean()),
        "pr_auc_raw": m_raw["pr_auc"],
        "pr_auc_calibrated": m_cal["pr_auc"],
        "brier_raw": m_raw["brier"],
        "brier_calibrated": m_cal["brier"],
        "brier_baseline": m_cal["brier_baseline"],
        "sfha_rate_eligible": pi,
        "probabilities_calibrated": True,
        "stage_d_started": False,
    }
    c_report["calibration"] = addendum
    c_report["p_sfha_calibrated_path"] = str(cal_path)
    _write_json(stage_c_report_path, c_report)
    _write_json(out_dir / "stage_c_calibration.json", addendum)
    return addendum
