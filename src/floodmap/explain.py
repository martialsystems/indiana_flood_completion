# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""SHAP for C features. Write-up, not a new model. Does not rewrite P rasters."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.warp import transform as rio_transform

from floodmap.align import interior_mask
from floodmap.claims import require_clean, scan_obj
from floodmap.codes import P_DEFINITION
from floodmap.config import (
    C_RANDOM_SEED,
    HAND_NODATA_RULE,
    HUC8,
    NLCD_NODATA,
    P_SFHA_CALIBRATED_NAME,
    STAGE_C_FEATURES,
    TEMPLATE_KIND_NLCD,
)
from floodmap.errors import GateError
from floodmap.stage_c import _fit_booster, gather_features, hand_defined
from floodmap.template import inspect_template


def _write_json(path: Path, obj: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n"
    require_clean(text, source=str(path))
    hits = scan_obj(obj)
    if hits:
        raise GateError(f"shap claim scan {hits}")
    path.write_text(text, encoding="utf-8")
    return path


def run_d_shap(
    *,
    template_path: Path,
    interim_dir: Path,
    out_dir: Path,
    facilities_csv: Path,
    headline_csv: Path,
    max_train: int = 80_000,
) -> dict[str, Any]:
    import shap

    if "hsg" in STAGE_C_FEATURES:
        raise GateError("SHAP must not add HSG")
    if not (interim_dir / P_SFHA_CALIBRATED_NAME).is_file():
        raise GateError("SHAP runs after calibrated P exists")
    template = inspect_template(template_path, kind=TEMPLATE_KIND_NLCD)
    inside = interior_mask(template)
    with rasterio.open(interim_dir / "hand.tif") as src:
        hand = src.read(1).astype(np.float32)
        p_crs = src.crs
        p_tf = src.transform
    with rasterio.open(interim_dir / "sfha.tif") as src:
        sfha = src.read(1)
    with rasterio.open(interim_dir / "slope.tif") as src:
        slope = src.read(1).astype(np.float32)
    with rasterio.open(interim_dir / "twi.tif") as src:
        twi = src.read(1).astype(np.float32)
    with rasterio.open(interim_dir / "dist_flowline.tif") as src:
        dist_fl = src.read(1).astype(np.float32)
    with rasterio.open(interim_dir / "dist_waterbody.tif") as src:
        dist_wb = src.read(1).astype(np.float32)
    with rasterio.open(template.path) as src:
        nlcd = src.read(1).astype(np.float32)
        nlcd_nod = src.nodata if src.nodata is not None else NLCD_NODATA
    defined = hand_defined(hand, inside)
    eligible = defined & ((sfha == 0) | (sfha == 1))
    stack = {
        "slope": slope,
        "twi": twi,
        "hand": hand,
        "dist_flowline": dist_fl,
        "dist_waterbody": dist_wb,
        "nlcd_impervious": np.where(nlcd == nlcd_nod, np.nan, nlcd),
    }
    rng = np.random.default_rng(C_RANDOM_SEED)
    pos_i = np.flatnonzero(eligible & (sfha == 1))
    neg_i = np.flatnonzero(eligible & (sfha == 0))
    if pos_i.size == 0 or neg_i.size == 0:
        raise GateError("SHAP sample empty")
    n_pos = min(max(200, max_train // 4), int(pos_i.size))
    n_neg = min(max_train - n_pos, int(neg_i.size))
    idx = np.concatenate(
        [
            rng.choice(pos_i, size=n_pos, replace=False),
            rng.choice(neg_i, size=n_neg, replace=False),
        ]
    )
    tr, tc = np.unravel_index(idx, sfha.shape)
    y = sfha[tr, tc].astype(np.uint8)
    x = gather_features(stack, tr, tc)
    finite = np.isfinite(x).all(axis=1)
    x, y = x[finite], y[finite]
    clf = _fit_booster(x, y, C_RANDOM_SEED)
    n_bg = min(400, int(x.shape[0]))
    bg = x[rng.choice(x.shape[0], size=n_bg, replace=False)]
    explainer = shap.TreeExplainer(clf, feature_perturbation="tree_path_dependent")
    sv_bg = explainer.shap_values(bg)
    sv_bg = np.asarray(getattr(sv_bg, "values", sv_bg))
    if sv_bg.ndim == 3:
        sv_bg = sv_bg[..., 1] if sv_bg.shape[-1] == 2 else sv_bg[:, 1]
    mean_abs = np.abs(sv_bg).mean(axis=0)
    global_rows = [
        {"feature": name, "mean_abs_shap": float(mean_abs[i])}
        for i, name in enumerate(STAGE_C_FEATURES)
    ]
    global_rows.sort(key=lambda r: r["mean_abs_shap"], reverse=True)

    fac = {r["name"]: r for r in csv.DictReader(facilities_csv.open(encoding="utf-8"))}
    local: list[dict[str, Any]] = []
    for hr in csv.DictReader(headline_csv.open(encoding="utf-8")):
        name = hr["name"]
        rec = fac.get(name)
        if rec is None:
            continue
        lon, lat = float(rec["lon"]), float(rec["lat"])
        xs, ys = rio_transform("EPSG:4326", p_crs, [lon], [lat])
        orow, ocol = rasterio.transform.rowcol(p_tf, xs[0], ys[0])
        dr = int(float(hr.get("p_max_dr") or 0))
        dc = int(float(hr.get("p_max_dc") or 0))
        rr, cc = int(orow + dr), int(ocol + dc)
        x1 = gather_features(stack, np.array([rr]), np.array([cc]))
        if not np.isfinite(x1).all():
            continue
        sv = explainer.shap_values(x1)
        sv = np.asarray(getattr(sv, "values", sv))
        if sv.ndim == 3:
            sv = sv[0, :, 1] if sv.shape[-1] == 2 else sv[0, 1]
        else:
            sv = sv[0]
        feats = {
            STAGE_C_FEATURES[i]: {
                "value": float(x1[0, i]),
                "shap": float(sv[i]),
            }
            for i in range(len(STAGE_C_FEATURES))
        }
        local.append(
            {
                "name": name,
                "p_max": float(hr["p_max"]),
                "p_mean": float(hr["p_mean"]),
                "p_max_note": hr.get("p_max_note"),
                "row": rr,
                "col": cc,
                "features": feats,
            }
        )

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 3.2))
    labels = [r["feature"] for r in global_rows][::-1]
    vals = [r["mean_abs_shap"] for r in global_rows][::-1]
    ax.barh(labels, vals, color="#334455")
    ax.set_xlabel("mean |SHAP|")
    ax.set_title(f"Global SHAP for {P_DEFINITION} (C features, no HSG)")
    fig.tight_layout()
    png_path = out_dir / "shap_global.png"
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=120)
    plt.close(fig)

    report = {
        "huc8": HUC8,
        "p_definition": P_DEFINITION,
        "p_source": P_SFHA_CALIBRATED_NAME,
        "hand_nodata_rule": HAND_NODATA_RULE,
        "features": list(STAGE_C_FEATURES),
        "hsg_in_shap": False,
        "n_train": int(y.size),
        "global_mean_abs_shap": global_rows,
        "headline_max_cells": local,
        "shap_global_png": png_path.name,
        "raw_p_sampled": False,
    }
    _write_json(out_dir / "shap_report.json", report)
    return report
