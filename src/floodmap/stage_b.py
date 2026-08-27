# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Stage B: TWI, HAND, distances on the live template. No Stage C."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import rasterio

from floodmap.align import (
    interior_mask,
    require_live_template,
    template_fingerprint,
    write_aligned_cog,
)
from floodmap.claims import require_clean, scan_obj
from floodmap.codes import P_DEFINITION
from floodmap.config import (
    DEM_NODATA,
    DIST_NODATA,
    FIRM_LIVE_MIN_HEIGHT,
    FIRM_LIVE_MIN_WIDTH,
    HUC8,
    HYDRO_BURN_M,
    HYDRO_NODATA,
    LOCKED_TRANSFORM_SHA256,
    SLOPE_FLOOR_RAD,
    STAGE_B_BANDS,
    TEMPLATE_KIND_NLCD,
    TEMPLATE_RES_M,
)
from floodmap.errors import GateError
from floodmap.firm import summarize_unmapped
from floodmap.freeze import verify_freeze
from floodmap.huc import load_huc
from floodmap.hydro import (
    burn_dem,
    d8_flowdir,
    euclidean_distance_m,
    flow_accumulation,
    hand_along_flow,
    priority_flood_fill,
    require_finite_twi,
    slope_radians,
    topographic_wetness,
)
from floodmap.nhd import (
    features_to_mask,
    fetch_area_streamriver,
    fetch_flowlines,
    fetch_waterbodies,
)
from floodmap.template import inspect_template
from whiteforge.gate import require_claims, require_freeze, require_stage, require_stale_map


def _write_json(path: Path, obj: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n"
    require_clean(text, source=str(path))
    hits = scan_obj(obj)
    if hits:
        raise GateError(f"stage B claim scan {hits}")
    path.write_text(text, encoding="utf-8")
    return path


def _load_a_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise GateError(f"Stage A report missing: {path}")
    obj = json.loads(path.read_text(encoding="utf-8"))
    if obj.get("stage") != "A" or obj.get("gate") != "pass":
        raise GateError("Stage A report is not a passing Stage A artifact")
    if not obj.get("firm_unshaded_x_ok"):
        raise GateError("Stage B requires firm_unshaded_x_ok")
    return obj


def _paint(values: np.ndarray, valid: np.ndarray, nodata: float) -> np.ndarray:
    out = np.full(values.shape, nodata, dtype=np.float32)
    finite = valid & np.isfinite(values)
    out[finite] = values[finite].astype(np.float32)
    return out


def _band_meta(name: str, path: Path, nodata: float, units: str) -> dict[str, Any]:
    return {
        "name": name,
        "path": str(path),
        "nodata": nodata,
        "units": units,
        "dtype": "float32",
        "driver": "COG",
    }


def run_stage_b(
    *,
    huc_path: Path,
    template_path: Path,
    interim_dir: Path,
    out_dir: Path,
    stage_a_report_path: Path,
    get_json=None,
    flowline_features: list | None = None,
    waterbody_features: list | None = None,
    area_features: list | None = None,
) -> dict[str, Any]:
    verify_freeze()
    require_freeze(rewrite_stage0_packet=False)
    require_claims()
    require_stale_map(request_site_publish=False)
    a_report = _load_a_report(stage_a_report_path)
    huc = load_huc(huc_path)
    template = inspect_template(template_path, kind=TEMPLATE_KIND_NLCD)
    require_live_template(template)
    fp = template_fingerprint(template)
    live = template.width >= FIRM_LIVE_MIN_WIDTH and template.height >= FIRM_LIVE_MIN_HEIGHT
    if live and fp["transform_sha256"] != LOCKED_TRANSFORM_SHA256:
        raise GateError(
            f"template transform {fp['transform_sha256']} != {LOCKED_TRANSFORM_SHA256}"
        )
    require_stage(
        current_stage="A",
        target_stage="B",
        freeze_verified=True,
        template_kind=TEMPLATE_KIND_NLCD,
        stage_a_report=True,
        firm_unshaded_x_ok=True,
        inundation_2008_mask=True,
        thread_id="stage_b",
    )

    dem_path = interim_dir / "dem.tif"
    if not dem_path.is_file():
        raise GateError("Stage B needs data/interim/dem.tif")
    inside = interior_mask(template)
    with rasterio.open(dem_path) as src:
        if tuple(src.transform)[:6] != tuple(template.transform)[:6]:
            raise GateError("DEM transform does not match the live template")
        dem = src.read(1).astype(np.float64)
        dem_nod = src.nodata if src.nodata is not None else DEM_NODATA
    dem_valid = inside & np.isfinite(dem) & (dem != dem_nod)
    if not dem_valid.any():
        raise GateError("DEM has no finite interior cells")

    if flowline_features is None:
        flowline_features = fetch_flowlines(huc, get_json)
    if waterbody_features is None:
        waterbody_features = fetch_waterbodies(huc, get_json)
    if area_features is None:
        if get_json is None:
            area_features = fetch_area_streamriver(huc)
        else:
            area_features = fetch_area_streamriver(huc, get_json)

    flow_mask = features_to_mask(flowline_features, template).astype(bool)
    water_mask = features_to_mask(waterbody_features, template).astype(bool)
    area_mask = features_to_mask(area_features or [], template).astype(bool)
    stream_mask = (flow_mask | water_mask | area_mask) & dem_valid
    if not stream_mask.any():
        raise GateError("burn mask is empty; NHD flowline/waterbody raster is empty")

    if live:
        print("Stage B: slope, burn, fill, D8, accumulation", flush=True)
    slope = slope_radians(dem, dem_valid, TEMPLATE_RES_M)
    burned = burn_dem(dem, stream_mask, depth_m=HYDRO_BURN_M, valid=dem_valid)
    filled = priority_flood_fill(burned, dem_valid, seed_mask=stream_mask)
    flowdir = d8_flowdir(filled, dem_valid, TEMPLATE_RES_M)
    acc = flow_accumulation(flowdir, dem_valid)
    twi, n_floor = topographic_wetness(
        acc, slope, TEMPLATE_RES_M, floor_rad=SLOPE_FLOOR_RAD, valid=dem_valid
    )
    require_finite_twi(twi, dem_valid)
    hand = hand_along_flow(dem, flowdir, stream_mask, dem_valid)
    dist_fl = euclidean_distance_m(flow_mask & inside, TEMPLATE_RES_M)
    dist_wb = euclidean_distance_m(water_mask & inside, TEMPLATE_RES_M)

    interim_dir.mkdir(parents=True, exist_ok=True)
    bands_out: dict[str, Path] = {}
    slope_path = interim_dir / "slope.tif"
    twi_path = interim_dir / "twi.tif"
    hand_path = interim_dir / "hand.tif"
    dfl_path = interim_dir / "dist_flowline.tif"
    dwb_path = interim_dir / "dist_waterbody.tif"
    write_aligned_cog(slope_path, template, _paint(slope, dem_valid, HYDRO_NODATA), dtype="float32", nodata=HYDRO_NODATA)
    write_aligned_cog(twi_path, template, _paint(twi, dem_valid, HYDRO_NODATA), dtype="float32", nodata=HYDRO_NODATA)
    write_aligned_cog(hand_path, template, _paint(hand, dem_valid, HYDRO_NODATA), dtype="float32", nodata=HYDRO_NODATA)
    write_aligned_cog(
        dfl_path,
        template,
        _paint(dist_fl, inside, DIST_NODATA),
        dtype="float32",
        nodata=DIST_NODATA,
    )
    write_aligned_cog(
        dwb_path,
        template,
        _paint(dist_wb, inside, DIST_NODATA),
        dtype="float32",
        nodata=DIST_NODATA,
    )
    bands_out = {
        "slope": slope_path,
        "twi": twi_path,
        "hand": hand_path,
        "dist_flowline": dfl_path,
        "dist_waterbody": dwb_path,
    }
    missing = [name for name in STAGE_B_BANDS if name not in bands_out]
    if missing:
        raise GateError(f"Stage B bands missing {missing}")

    n_hand_undef = int((dem_valid & ~np.isfinite(hand)).sum())
    n_stream = int(stream_mask.sum())
    n_wb = int((water_mask & inside).sum())
    n_fl = int((flow_mask & inside).sum())

    manifest = {
        "template_transform_sha256": fp["transform_sha256"],
        "huc8": HUC8,
        "hsg_in_stack": False,
        "materialized_dense_matrix": False,
        "slope_floor_rad": SLOPE_FLOOR_RAD,
        "hydro_burn_m": HYDRO_BURN_M,
        "bands": [
            _band_meta("slope", slope_path, HYDRO_NODATA, "rad"),
            _band_meta("twi", twi_path, HYDRO_NODATA, "ln(m)"),
            _band_meta("hand", hand_path, HYDRO_NODATA, "m"),
            _band_meta("dist_flowline", dfl_path, DIST_NODATA, "m"),
            _band_meta("dist_waterbody", dwb_path, DIST_NODATA, "m"),
        ],
    }
    _write_json(interim_dir / "stack_manifest.json", manifest)
    _write_json(out_dir / "stack_manifest.json", manifest)

    unmapped_addendum = None
    zone_path = interim_dir / "zone_class.tif"
    if zone_path.is_file():
        with rasterio.open(zone_path) as src:
            zone = src.read(1)
        unmapped_addendum = summarize_unmapped(zone, inside)
        a_report["unmapped_addendum"] = unmapped_addendum
        _write_json(stage_a_report_path, a_report)

    report: dict[str, Any] = {
        "stage": "B",
        "gate": "pass",
        "huc8": HUC8,
        "unit": "pixel",
        "p_definition": P_DEFINITION,
        "template_fingerprint": fp,
        "firm_unshaded_x_ok": True,
        "hsg_incomplete": bool(a_report.get("hsg_incomplete")),
        "hsg_in_stack": False,
        "n_interior": int(inside.sum()),
        "n_dem_valid": int(dem_valid.sum()),
        "n_slope_floor": n_floor,
        "slope_floor_rad": SLOPE_FLOOR_RAD,
        "n_stream_cells": n_stream,
        "n_flowline_cells": n_fl,
        "n_waterbody_cells": n_wb,
        "n_hand_undefined": n_hand_undef,
        "twi_finite_on_dem_valid": True,
        "hand_is_flow_path": True,
        "hydro_burn_m": HYDRO_BURN_M,
        "n_flowline_features": len(flowline_features),
        "n_waterbody_features": len(waterbody_features),
        "n_area_460_features": len(area_features or []),
        "bands": manifest["bands"],
        "stack_manifest": str(out_dir / "stack_manifest.json"),
        "unmapped_addendum": unmapped_addendum,
        "stage_c_started": False,
    }
    require_stage(
        current_stage="B",
        target_stage="B",
        freeze_verified=True,
        template_kind=TEMPLATE_KIND_NLCD,
        stage_a_report=True,
        stage_b_report=True,
        firm_unshaded_x_ok=True,
        inundation_2008_mask=True,
        thread_id="stage_b_complete",
    )
    _write_json(out_dir / "stage_b_report.json", report)
    return report
