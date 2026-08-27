# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Stage A: warp every layer to the live NLCD template. No Stage B."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from floodmap.align import require_live_template, template_fingerprint
from floodmap.claims import require_clean, scan_obj
from floodmap.codes import OFR_APPENDIX2_LABEL, P_DEFINITION, TRI_ERROR_BUDGET_FIELDS
from floodmap.config import (
    FROZEN_OCCUPANCY_PATH,
    HUC8,
    TEMPLATE_KIND_NLCD,
    TRI_YEAR_CANDIDATES,
)
from floodmap.dem import fetch_dem
from floodmap.errors import GateError
from floodmap.firm import (
    fetch_firm_pages,
    is_full_huc_template,
    rasterize_firm,
    summarize_firm_rasters,
)
from floodmap.freeze import verify_freeze
from floodmap.huc import load_huc
from floodmap.nhd import fetch_flowlines, rasterize_distance
from floodmap.ofr2008 import build_2008_mask
from floodmap.soils import (
    default_sda_post,
    fetch_hsg_polygons,
    rasterize_hsg,
    summarize_hsg_raster,
    write_hsg_from_sda,
)
from floodmap.template import inspect_template
from floodmap.tri import clip_to_huc, parse_tri_1a, unzip_csv, write_facilities_csv
from floodmap.fetch import default_get_bytes, default_get_json
from whiteforge.gate import require_claims, require_freeze, require_stage, require_stale_map


def _write_json(path: Path, obj: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n"
    require_clean(text, source=str(path))
    hits = scan_obj(obj)
    if hits:
        raise GateError(f"stage A claim scan {hits}")
    path.write_text(text, encoding="utf-8")
    return path


def run_stage_a(
    *,
    huc_path: Path,
    template_path: Path,
    raw_dir: Path,
    interim_dir: Path,
    out_dir: Path,
    get_json=None,
    get_bytes=None,
    sda_post=None,
    tri_text: str | None = None,
    tri_year: int = TRI_YEAR_CANDIDATES[0],
    ofr_extracted: dict | None = None,
) -> dict[str, Any]:
    freeze = verify_freeze()
    require_freeze(rewrite_stage0_packet=False)
    require_claims()
    require_stale_map(request_site_publish=False)
    huc = load_huc(huc_path)
    template = inspect_template(template_path, kind=TEMPLATE_KIND_NLCD)
    require_live_template(template)
    require_stage(
        current_stage="0",
        target_stage="A",
        freeze_verified=True,
        template_kind=TEMPLATE_KIND_NLCD,
        thread_id="stage_a",
    )
    gj = get_json or default_get_json
    gb = get_bytes or default_get_bytes
    sda = sda_post or default_sda_post
    interim_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    dem_path = interim_dir / "dem.tif"
    dist_path = interim_dir / "dist_stream.tif"
    sfha_path = interim_dir / "sfha.tif"
    zone_path = interim_dir / "zone_class.tif"
    if dem_path.is_file():
        dem_info = {"path": str(dem_path), "skipped_existing": True}
    else:
        dem_info = fetch_dem(template, dem_path, get_bytes=gb)
    if dist_path.is_file():
        nhd_info = {"path": str(dist_path), "skipped_existing": True}
    else:
        if get_json is None:
            flow = fetch_flowlines(huc)
        else:
            flow = fetch_flowlines(huc, gj)
        nhd_info = rasterize_distance(flow, template, dist_path)
    firm_info = None
    if sfha_path.is_file() and zone_path.is_file():
        try:
            firm_info = summarize_firm_rasters(template, sfha_path, zone_path)
        except GateError:
            firm_info = None
    if firm_info is None:
        if get_json is None:
            _wkid, firm_features = fetch_firm_pages(gj, huc=huc)
        else:
            _wkid, firm_features = fetch_firm_pages(gj)
        del _wkid
        firm_info = rasterize_firm(
            firm_features,
            template,
            sfha_dest=sfha_path,
            zone_dest=zone_path,
        )
    hsg_path = interim_dir / "hsg.tif"
    if hsg_path.is_file() and is_full_huc_template(template):
        soils_info = summarize_hsg_raster(template, hsg_path)
    elif get_json is None:
        soils_info = write_hsg_from_sda(huc, template, hsg_path, sda)
    else:
        hsg_polys = fetch_hsg_polygons(huc, sda)
        soils_info = rasterize_hsg(hsg_polys, template, hsg_path)

    if tri_text is None:
        raise GateError("TRI 1a text is required (fetch in run_stage_a.py)")
    by_fac, tri_budget = parse_tri_1a(tri_text, year=tri_year)
    in_huc, n_out = clip_to_huc(by_fac.values(), huc)
    tri_budget["n_dropped_out_of_huc"] = n_out
    tri_budget["n_tris_huc_year"] = len(in_huc)
    for key in TRI_ERROR_BUDGET_FIELDS:
        if key not in tri_budget:
            raise GateError(f"TRI error budget missing {key}")
    write_facilities_csv(interim_dir / "tri_huc.csv", in_huc)

    ofr_info = build_2008_mask(
        template,
        raw_dir / "ofr2008",
        interim_dir,
        interim_dir / "mask_2008.tif",
        get_bytes=gb,
        already_extracted=ofr_extracted,
    )

    fp = template_fingerprint(template)
    report: dict[str, Any] = {
        "stage": "A",
        "gate": "pass",
        "huc8": HUC8,
        "unit": "pixel",
        "p_definition": P_DEFINITION,
        "template_fingerprint": fp,
        "citation_2008": OFR_APPENDIX2_LABEL,
        "martinsville_paragon_intersection": "measured, not assumed",
        "dem": dem_info,
        "nhd": nhd_info,
        "firm": firm_info,
        "firm_source": firm_info.get("firm_source"),
        "firm_unshaded_x_ok": bool(firm_info.get("firm_unshaded_x_ok")),
        "gate_samples": firm_info.get("gate_samples") or [],
        "soils": soils_info,
        "hsg_incomplete": bool(soils_info.get("hsg_incomplete")),
        "tri": tri_budget,
        "ofr2008": ofr_info,
        "imported_occupancy_path": str(FROZEN_OCCUPANCY_PATH),
        "ofr_reaches_intersecting_huc": ofr_info["ofr_reaches_intersecting_huc"],
        "mask_value_counts": ofr_info["mask_value_counts"],
        "zone_class_counts": firm_info["zone_class_counts"],
    }
    require_stage(
        current_stage="A",
        target_stage="A",
        freeze_verified=True,
        template_kind=TEMPLATE_KIND_NLCD,
        stage_a_report=True,
        inundation_2008_mask=True,
        thread_id="stage_a_complete",
    )
    _write_json(out_dir / "stage_a_report.json", report)
    return report
