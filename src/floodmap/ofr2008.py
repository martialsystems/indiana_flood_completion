# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""OFR 2008-1322 Appendix 2 reach rasters. Not a basin flood layer."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Callable

import numpy as np
import rasterio
from rasterio.enums import Resampling

from floodmap.align import (
    empty_like,
    interior_mask,
    require_live_template,
    warp_to_template,
    write_aligned,
)
from floodmap.codes import (
    MASK_IN_HUC_UNMAPPED,
    MASK_OFR_OR_HWM,
    MASK_OUTSIDE_HUC,
    OFR_APPENDIX2_ZIPS,
    OFR_ZIP_BASE,
    require_mask_unique,
)
from floodmap.errors import FetchError, GateError
from floodmap.fetch import GetBytes, default_get_bytes
from floodmap.template import TemplateGrid

GetBytesFn = GetBytes


def ofr_zip_url(filename: str) -> str:
    return f"{OFR_ZIP_BASE}{filename}"


def extract_depth_img(zip_path: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        depth = [n for n in names if n.lower().endswith(".img") and "/fd_" in f"/{n.lower()}"]
        if not depth:
            depth = [n for n in names if n.lower().startswith("fd_") and n.lower().endswith(".img")]
        if not depth:
            raise GateError(f"no fd_*.img depth grid in {zip_path.name}: {names}")
        name = depth[0]
        zf.extract(name, dest_dir)
        # sidecar files needed by ERDAS
        stem = Path(name).stem
        for extra in names:
            extra_p = Path(extra)
            if extra_p.stem.startswith(stem) or extra_p.name.startswith(stem):
                if extra != name:
                    zf.extract(extra, dest_dir)
        return dest_dir / name


def download_ofr_zip(
    dest: Path,
    filename: str,
    *,
    get_bytes: GetBytesFn | None = None,
) -> Path:
    getter = get_bytes or default_get_bytes
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    payload = getter(ofr_zip_url(filename))
    if payload[:2] != b"PK":
        raise FetchError(f"OFR zip is not a zip: {filename}")
    dest.write_bytes(payload)
    return dest


def count_wet_on_template(depth_path: Path, template: TemplateGrid, huc_mask: np.ndarray) -> int:
    """Warp depth to template; count cells with depth > 0 inside the HUC."""
    tmp = depth_path.with_suffix(".aligned.tif")
    warp_to_template(
        depth_path,
        template,
        tmp,
        resampling=Resampling.nearest,
        dst_nodata=-9999.0,
        dtype="float32",
    )
    with rasterio.open(tmp) as src:
        depth = src.read(1)
        nod = src.nodata
    wet = (depth > 0) & np.isfinite(depth)
    if nod is not None:
        wet &= depth != nod
    wet &= huc_mask
    return int(wet.sum())


def apply_wet(mask: np.ndarray, depth_path: Path, template: TemplateGrid, huc_mask: np.ndarray) -> int:
    tmp = depth_path.with_suffix(".aligned.tif")
    warp_to_template(
        depth_path,
        template,
        tmp,
        resampling=Resampling.nearest,
        dst_nodata=-9999.0,
        dtype="float32",
    )
    with rasterio.open(tmp) as src:
        depth = src.read(1)
        nod = src.nodata
    wet = (depth > 0) & np.isfinite(depth)
    if nod is not None:
        wet &= depth != nod
    wet &= huc_mask
    n = int(wet.sum())
    mask[wet] = MASK_OFR_OR_HWM
    return n


def build_2008_mask(
    template: TemplateGrid,
    raw_dir: Path,
    interim_dir: Path,
    dest: Path,
    *,
    get_bytes: GetBytesFn | None = None,
    already_extracted: dict[str, Path] | None = None,
) -> dict:
    """Download every Appendix 2 zip. Mosaic only reaches with wet cells in-HUC."""
    require_live_template(template)
    huc_mask = interior_mask(template)
    mask = empty_like(template, dtype="uint8", nodata=MASK_OUTSIDE_HUC)
    mask[huc_mask] = MASK_IN_HUC_UNMAPPED
    rows: list[dict] = []
    intersecting: list[str] = []
    for slug, name, filename in OFR_APPENDIX2_ZIPS:
        if already_extracted and slug in already_extracted:
            img = already_extracted[slug]
        else:
            zpath = download_ofr_zip(raw_dir / filename, filename, get_bytes=get_bytes)
            img = extract_depth_img(zpath, raw_dir / slug)
        n = apply_wet(mask, img, template, huc_mask)
        row = {
            "slug": slug,
            "name": name,
            "zip": filename,
            "intersect_cells": n,
        }
        rows.append(row)
        if n > 0:
            intersecting.append(name)
    write_aligned(dest, template, mask, dtype="uint8", nodata=MASK_OUTSIDE_HUC)
    values = {int(v) for v in np.unique(mask)}
    appendix2_intersects = len(intersecting) > 0
    require_mask_unique(values, appendix2_intersects_huc=appendix2_intersects)
    counts = {str(k): int((mask == k).sum()) for k in sorted(values)}
    return {
        "reaches": rows,
        "ofr_reaches_intersecting_huc": intersecting,
        "mask_value_counts": counts,
        "appendix2_intersects_huc": appendix2_intersects,
        "n_zips": len(OFR_APPENDIX2_ZIPS),
        "sartor_ditch_img": False,
        "elnora_withdrawn": True,
        "mask_path": str(dest),
        "citation": "June 7-9, 2008 inundation (OFR 2008-1322)",
        "martinsville_paragon_measured": True,
    }
