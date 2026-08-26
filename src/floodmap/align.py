# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Warp every Stage A raster onto the live NLCD 2021 template grid."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.warp import reproject

from floodmap.config import (
    FIXTURE_COLS,
    FIXTURE_ROWS,
    NLCD_NODATA,
    TEMPLATE_CRS,
    TEMPLATE_KIND_NLCD,
)
from floodmap.errors import GateError
from floodmap.template import TemplateGrid, sha256_file


def require_live_template(template: TemplateGrid) -> TemplateGrid:
    if template.kind != TEMPLATE_KIND_NLCD:
        raise GateError("warp_to_template requires live nlcd_2021 template")
    if template.width <= FIXTURE_COLS and template.height <= FIXTURE_ROWS:
        raise GateError("warp_to_template refuses the fixture grid")
    if template.crs != TEMPLATE_CRS:
        raise GateError(f"template CRS {template.crs} != {TEMPLATE_CRS}")
    return template


def template_bounds(template: TemplateGrid) -> tuple[float, float, float, float]:
    t = template.transform
    west = float(t.c)
    north = float(t.f)
    east = west + template.width * float(t.a)
    south = north + template.height * float(t.e)
    return west, south, east, north


def template_fingerprint(template: TemplateGrid) -> dict:
    t = template.transform
    payload = (
        f"{template.crs}|{template.width}|{template.height}|"
        f"{t.a},{t.b},{t.c},{t.d},{t.e},{t.f}"
    )
    return {
        "kind": template.kind,
        "crs": template.crs,
        "width": template.width,
        "height": template.height,
        "transform": [float(t.a), float(t.b), float(t.c), float(t.d), float(t.e), float(t.f)],
        "transform_sha256": hashlib.sha256(payload.encode("ascii")).hexdigest(),
        "raster_sha256": sha256_file(template.path) if template.path.is_file() else "",
    }


def interior_mask(template: TemplateGrid) -> np.ndarray:
    """True where the NLCD template is not nodata (inside the HUC clip)."""
    require_live_template(template)
    with rasterio.open(template.path) as src:
        arr = src.read(1)
        nod = src.nodata
    if nod is None:
        nod = NLCD_NODATA
    return arr != nod


def empty_like(template: TemplateGrid, *, dtype: str, nodata) -> np.ndarray:
    require_live_template(template)
    return np.full((template.height, template.width), nodata, dtype=dtype)


def write_aligned(
    dest: Path,
    template: TemplateGrid,
    data: np.ndarray,
    *,
    dtype: str,
    nodata,
) -> Path:
    require_live_template(template)
    if data.shape != (template.height, template.width):
        raise GateError(
            f"aligned raster shape {data.shape} != "
            f"({template.height}, {template.width})"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "height": template.height,
        "width": template.width,
        "count": 1,
        "dtype": dtype,
        "crs": CRS.from_epsg(template.crs),
        "transform": template.transform,
        "nodata": nodata,
        "compress": "lzw",
    }
    with rasterio.open(dest, "w", **profile) as dst:
        dst.write(np.asarray(data, dtype=dtype), 1)
    return dest


def warp_to_template(
    src_path: Path,
    template: TemplateGrid,
    dest: Path,
    *,
    resampling: Resampling = Resampling.bilinear,
    src_nodata=None,
    dst_nodata=None,
    dtype: str | None = None,
) -> Path:
    """Reproject src onto the live template. Never invent a second grid."""
    require_live_template(template)
    if not src_path.is_file():
        raise GateError(f"missing source raster: {src_path}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(src_path) as src:
        dst_dtype = dtype or src.dtypes[0]
        nodata = dst_nodata if dst_nodata is not None else src.nodata
        dest_arr = np.full(
            (template.height, template.width),
            nodata if nodata is not None else 0,
            dtype=dst_dtype,
        )
        reproject(
            source=rasterio.band(src, 1),
            destination=dest_arr,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=template.transform,
            dst_crs=CRS.from_epsg(template.crs),
            resampling=resampling,
            src_nodata=src_nodata if src_nodata is not None else src.nodata,
            dst_nodata=nodata,
        )
    return write_aligned(dest, template, dest_arr, dtype=dst_dtype, nodata=nodata)
