# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Stage C: P(sfha | hydro) with HUC-10 block CV. No Stage D. No HSG."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from sklearn.metrics import average_precision_score, brier_score_loss
from xgboost import XGBClassifier

from floodmap.align import interior_mask, require_live_template, template_fingerprint, write_aligned_cog
from floodmap.claims import require_clean, scan_obj
from floodmap.codes import P_DEFINITION, ZONE_UNSHADED_X
from floodmap.config import (
    C_NEAR_STREAM_M,
    C_NON_SFHA_RATIO,
    C_RANDOM_SEED,
    DIST_NODATA,
    FIRM_LIVE_MIN_HEIGHT,
    FIRM_LIVE_MIN_WIDTH,
    HAND_NODATA_RULE,
    HUC8,
    HYDRO_NODATA,
    LOCKED_TRANSFORM_SHA256,
    NLCD_NODATA,
    P_SFHA_NODATA,
    STAGE_C_FEATURES,
    TEMPLATE_KIND_NLCD,
)
from floodmap.errors import GateError
from floodmap.freeze import verify_freeze
from floodmap.huc10 import fetch_huc10_features, rasterize_huc10, save_huc10_geojson, train_test_halo
from floodmap.stage_b import encode_b_leftovers
from floodmap.template import inspect_template
from whiteforge.gate import require_claims, require_freeze, require_stage, require_stale_map


def _write_json(path: Path, obj: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n"
    require_clean(text, source=str(path))
    hits = scan_obj(obj)
    if hits:
        raise GateError(f"stage C claim scan {hits}")
    path.write_text(text, encoding="utf-8")
    return path


def _load_report(path: Path, stage: str) -> dict[str, Any]:
    if not path.is_file():
        raise GateError(f"Stage {stage} report missing: {path}")
    obj = json.loads(path.read_text(encoding="utf-8"))
    if obj.get("stage") != stage or obj.get("gate") != "pass":
        raise GateError(f"Stage {stage} report is not a passing artifact")
    return obj


def hand_defined(hand: np.ndarray, inside: np.ndarray) -> np.ndarray:
    return inside & np.isfinite(hand) & (hand != HYDRO_NODATA)


def stratify_sample(
    *,
    pos: np.ndarray,
    neg: np.ndarray,
    unshaded_near: np.ndarray,
    ratio: float = C_NON_SFHA_RATIO,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (rows, cols) for all positives plus `ratio` times as many negatives.

    Extra weight: at least half of the negative draw comes from unshaded_x near
    streams when that pool is large enough. Does not ravel the full interior.
    """
    shape = pos.shape
    pos_i = np.flatnonzero(pos)
    n_pos = int(pos_i.size)
    if n_pos == 0:
        raise GateError("Stage C sample has no SFHA positives")
    n_neg_target = int(round(n_pos * ratio))
    neg_i = np.flatnonzero(neg)
    if neg_i.size == 0:
        raise GateError("Stage C sample has no non-SFHA cells")
    near_i = np.flatnonzero(unshaded_near & neg)
    n_near_take = min(int(near_i.size), max(n_neg_target // 2, 1)) if near_i.size else 0
    near_pick = (
        rng.choice(near_i, size=n_near_take, replace=False)
        if n_near_take
        else np.array([], dtype=np.intp)
    )
    other_pool = np.setdiff1d(neg_i, near_pick, assume_unique=False)
    n_other_take = min(int(other_pool.size), n_neg_target - n_near_take)
    other_pick = (
        rng.choice(other_pool, size=n_other_take, replace=False)
        if n_other_take
        else np.array([], dtype=np.intp)
    )
    idx = np.concatenate([pos_i, near_pick, other_pick])
    rows, cols = np.unravel_index(idx, shape)
    return rows.astype(np.int32, copy=False), cols.astype(np.int32, copy=False)


def gather_features(stack: dict[str, np.ndarray], rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
    cols_feat = [stack[name][rows, cols] for name in STAGE_C_FEATURES]
    x = np.column_stack(cols_feat).astype(np.float32, copy=False)
    if x.shape[1] != len(STAGE_C_FEATURES):
        raise GateError("Stage C feature width mismatch")
    if "hsg" in STAGE_C_FEATURES:
        raise GateError("HSG is not an allowed Stage C feature")
    return x


def _fit_booster(x: np.ndarray, y: np.ndarray, rng_seed: int) -> XGBClassifier:
    n_pos = int((y == 1).sum())
    n_neg = int((y == 0).sum())
    spw = (n_neg / n_pos) if n_pos else 1.0
    clf = XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.08,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="binary:logistic",
        eval_metric="logloss",
        n_jobs=4,
        tree_method="hist",
        scale_pos_weight=spw,
        random_state=rng_seed,
        verbosity=0,
    )
    clf.fit(x, y)
    return clf


def _metrics(y: np.ndarray, p: np.ndarray, pi: float) -> dict[str, float]:
    pr_auc = float(average_precision_score(y, p))
    brier = float(brier_score_loss(y, p))
    baseline = np.full(y.shape, pi, dtype=np.float64)
    pr_base = float(average_precision_score(y, baseline))
    brier_base = float(brier_score_loss(y, baseline))
    return {
        "pr_auc": pr_auc,
        "brier": brier,
        "pr_auc_baseline": pr_base,
        "brier_baseline": brier_base,
        "sfha_rate": float(pi),
    }


def run_stage_c(
    *,
    template_path: Path,
    interim_dir: Path,
    out_dir: Path,
    raw_dir: Path,
    stage_a_report_path: Path,
    stage_b_report_path: Path,
    get_json=None,
    huc10_features: list | None = None,
) -> dict[str, Any]:
    verify_freeze()
    require_freeze(rewrite_stage0_packet=False)
    require_claims()
    require_stale_map(request_site_publish=False)
    a_report = _load_report(stage_a_report_path, "A")
    b_report = _load_report(stage_b_report_path, "B")
    if not a_report.get("firm_unshaded_x_ok") or not b_report.get("firm_unshaded_x_ok"):
        raise GateError("Stage C requires firm_unshaded_x_ok")
    if "hsg" in STAGE_C_FEATURES:
        raise GateError("HSG is not an allowed Stage C feature")
    template = inspect_template(template_path, kind=TEMPLATE_KIND_NLCD)
    require_live_template(template)
    fp = template_fingerprint(template)
    live = template.width >= FIRM_LIVE_MIN_WIDTH and template.height >= FIRM_LIVE_MIN_HEIGHT
    if live and fp["transform_sha256"] != LOCKED_TRANSFORM_SHA256:
        raise GateError(
            f"template transform {fp['transform_sha256']} != {LOCKED_TRANSFORM_SHA256}"
        )
    require_stage(
        current_stage="B",
        target_stage="C",
        freeze_verified=True,
        template_kind=TEMPLATE_KIND_NLCD,
        stage_a_report=True,
        stage_b_report=True,
        firm_unshaded_x_ok=True,
        inundation_2008_mask=True,
        thread_id="stage_c",
    )

    inside = interior_mask(template)
    with rasterio.open(interim_dir / "hand.tif") as src:
        hand = src.read(1).astype(np.float32)
    with rasterio.open(interim_dir / "dist_flowline.tif") as src:
        dist_fl = src.read(1).astype(np.float32)
    with rasterio.open(interim_dir / "dist_waterbody.tif") as src:
        dist_wb = src.read(1).astype(np.float32)
    leftovers = encode_b_leftovers(
        stage_b_report_path,
        inside=inside,
        dist_flowline=dist_fl,
        dist_waterbody=dist_wb,
        hand=hand,
    )
    if leftovers["hand_nodata_rule"] != HAND_NODATA_RULE:
        raise GateError("HAND nodata rule mismatch")
    if leftovers["hand_nodata_filled_with_zero"]:
        raise GateError("HAND nodata must not be filled with 0")

    with rasterio.open(interim_dir / "sfha.tif") as src:
        sfha = src.read(1)
    with rasterio.open(interim_dir / "slope.tif") as src:
        slope = src.read(1).astype(np.float32)
    with rasterio.open(interim_dir / "twi.tif") as src:
        twi = src.read(1).astype(np.float32)
    with rasterio.open(template.path) as src:
        nlcd = src.read(1).astype(np.float32)
        nlcd_nod = src.nodata if src.nodata is not None else NLCD_NODATA
    zone_path = interim_dir / "zone_class.tif"
    if zone_path.is_file():
        with rasterio.open(zone_path) as src:
            zone = src.read(1)
    else:
        zone = np.zeros(sfha.shape, dtype=np.uint8)

    defined = hand_defined(hand, inside)
    eligible = defined & ((sfha == 0) | (sfha == 1))
    n_hand_drop = int((inside & ~defined).sum())
    n_sfha = int(((sfha == 1) & eligible).sum())
    if n_sfha == 0:
        raise GateError("no SFHA positives after HAND-nodata drop")

    if huc10_features is None:
        huc10_features = fetch_huc10_features(get_json)
    save_huc10_geojson(huc10_features, raw_dir / f"huc10_{HUC8}.geojson")
    huc10_info = rasterize_huc10(huc10_features, template, interim_dir / "huc10.tif")
    with rasterio.open(huc10_info["path"]) as src:
        huc10 = src.read(1)
    ids = [int(k) for k in huc10_info["legend"]]
    if len(ids) < 2:
        raise GateError("Stage C needs at least two HUC-10 blocks")

    stack = {
        "slope": slope,
        "twi": twi,
        "hand": hand,
        "dist_flowline": dist_fl,
        "dist_waterbody": dist_wb,
        "nlcd_impervious": np.where(nlcd == nlcd_nod, np.nan, nlcd),
    }
    if set(stack) != set(STAGE_C_FEATURES):
        raise GateError("Stage C stack keys != STAGE_C_FEATURES")

    unshaded_near = (
        (zone == ZONE_UNSHADED_X)
        & (
            ((dist_fl >= 0) & (dist_fl < C_NEAR_STREAM_M) & (dist_fl != DIST_NODATA))
            | ((dist_wb >= 0) & (dist_wb < C_NEAR_STREAM_M) & (dist_wb != DIST_NODATA))
        )
    )
    rng = np.random.default_rng(C_RANDOM_SEED)
    p_map = np.full(sfha.shape, P_SFHA_NODATA, dtype=np.float32)
    y_oof: list[np.ndarray] = []
    p_oof: list[np.ndarray] = []
    hand_oof: list[np.ndarray] = []
    n_train_pos = 0
    n_train_neg = 0
    n_halo = 0
    fold_rows: list[dict[str, Any]] = []

    for test_id in ids:
        if live:
            print(f"Stage C: HUC-10 {huc10_info['legend'][str(test_id)]}", flush=True)
        train_m, test_m, halo_m = train_test_halo(huc10, test_id, eligible)
        n_halo += int((halo_m & ~test_m).sum())
        if not test_m.any() or not train_m.any():
            continue
        pos = train_m & (sfha == 1)
        neg = train_m & (sfha == 0)
        tr, tc = stratify_sample(pos=pos, neg=neg, unshaded_near=unshaded_near, rng=rng)
        ytr = sfha[tr, tc].astype(np.uint8)
        xtr = gather_features(stack, tr, tc)
        finite = np.isfinite(xtr).all(axis=1)
        xtr, ytr = xtr[finite], ytr[finite]
        n_train_pos += int((ytr == 1).sum())
        n_train_neg += int((ytr == 0).sum())
        clf = _fit_booster(xtr, ytr, C_RANDOM_SEED + test_id)
        er, ec = np.where(test_m)
        xte = gather_features(stack, er, ec)
        finite_te = np.isfinite(xte).all(axis=1)
        p = np.full(er.size, np.nan, dtype=np.float32)
        if finite_te.any():
            p[finite_te] = clf.predict_proba(xte[finite_te])[:, 1].astype(np.float32)
        ok = np.isfinite(p)
        p_map[er[ok], ec[ok]] = p[ok]
        y_oof.append(sfha[er[ok], ec[ok]].astype(np.uint8))
        p_oof.append(p[ok])
        hand_oof.append(hand[er[ok], ec[ok]])
        fold_rows.append(
            {
                "huc10": huc10_info["legend"][str(test_id)],
                "n_test": int(ok.sum()),
                "n_train_sampled": int(ytr.size),
            }
        )

    if not y_oof:
        raise GateError("Stage C produced no OOF predictions")
    y = np.concatenate(y_oof)
    p = np.concatenate(p_oof)
    hand_te = np.concatenate(hand_oof)
    pi = float((sfha[eligible] == 1).mean())
    metrics = _metrics(y, p, pi)
    hand_score = (-hand_te).astype(np.float64)
    hand_pr = float(average_precision_score(y, hand_score))
    if metrics["pr_auc"] <= metrics["pr_auc_baseline"]:
        raise GateError(
            f"PR-AUC {metrics['pr_auc']} is not above SFHA-rate baseline "
            f"{metrics['pr_auc_baseline']}"
        )

    p_path = interim_dir / "p_sfha.tif"
    write_aligned_cog(p_path, template, p_map, dtype="float32", nodata=P_SFHA_NODATA)
    # HAND-nodata cells stay nodata.
    with rasterio.open(p_path) as src:
        check = src.read(1)
    nd_ok = np.all(check[inside & ~defined] == P_SFHA_NODATA)
    if not nd_ok:
        raise GateError("p_sfha.tif filled HAND-nodata cells")

    report: dict[str, Any] = {
        "stage": "C",
        "gate": "pass",
        "huc8": HUC8,
        "unit": "pixel",
        "p_definition": P_DEFINITION,
        "colorbar": P_DEFINITION,
        "filename": "p_sfha.tif",
        "p_sfha_path": str(p_path),
        "template_fingerprint": fp,
        "features": list(STAGE_C_FEATURES),
        "hsg_in_model": False,
        "hsg_omitted": "tiled_sda_incomplete; not a silent column",
        "hand_nodata_rule": HAND_NODATA_RULE,
        "n_hand_nodata_excluded": n_hand_drop,
        "n_sfha_eligible": n_sfha,
        "n_oof": int(y.size),
        "n_train_pos_sampled": n_train_pos,
        "n_train_neg_sampled": n_train_neg,
        "non_sfha_ratio": C_NON_SFHA_RATIO,
        "n_huc10": huc10_info["n_huc10"],
        "huc10_codes": huc10_info["huc10_codes"],
        "n_halo_train_excluded": n_halo,
        "cv": "leave_one_huc10_out",
        "halo_pixels": 1,
        "pr_auc": metrics["pr_auc"],
        "pr_auc_baseline": metrics["pr_auc_baseline"],
        "brier": metrics["brier"],
        "brier_baseline": metrics["brier_baseline"],
        "sfha_rate_eligible": pi,
        "hand_negated_pr_auc": hand_pr,
        "booster_minus_hand_pr_auc": metrics["pr_auc"] - hand_pr,
        "hand_threshold_logged": True,
        "booster_barely_beats_hand": bool(0 <= metrics["pr_auc"] - hand_pr < 0.02),
        "probabilities_calibrated": False,
        "stream_composition": leftovers["stream_composition"],
        "stage_d_started": False,
        "d1_d2_written": False,
        "ofr_touched": False,
        "tri_touched": False,
        "folds": fold_rows,
    }
    require_stage(
        current_stage="C",
        target_stage="C",
        freeze_verified=True,
        template_kind=TEMPLATE_KIND_NLCD,
        stage_a_report=True,
        stage_b_report=True,
        stage_c_metrics=True,
        firm_unshaded_x_ok=True,
        inundation_2008_mask=True,
        thread_id="stage_c_complete",
    )
    _write_json(out_dir / "stage_c_report.json", report)
    return report
