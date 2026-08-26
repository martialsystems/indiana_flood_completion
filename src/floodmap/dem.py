# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""USGS 3DEP elevation, tiled onto the live template."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.io import MemoryFile

from floodmap.align import interior_mask, require_live_template, template_bounds, write_aligned
from floodmap.config import DEM_IMAGE_URL, DEM_NODATA, DEM_TILE_PX, TEMPLATE_CRS
from floodmap.errors import FetchError, GateError
from floodmap.fetch import GetBytes, default_get_bytes, iter_tiles
from floodmap.template import TemplateGrid


def dem_export_url(
    *,
    west: float,
    south: float,
    east: float,
    north: float,
    width: int,
    height: int,
) -> str:
    return (
        f"{DEM_IMAGE_URL}"
        f"?bbox={west},{south},{east},{north}"
        f"&bboxSR={TEMPLATE_CRS}&imageSR={TEMPLATE_CRS}"
        f"&size={width},{height}"
        f"&format=tiff&pixelType=F32"
        f"&interpolation=RSP_BilinearInterpolation&f=image"
    )


def fetch_dem(
    template: TemplateGrid,
    dest: Path,
    *,
    get_bytes: GetBytes | None = None,
    tile_px: int = DEM_TILE_PX,
) -> dict:
    require_live_template(template)
    getter = get_bytes or default_get_bytes
    west, south, east, north = template_bounds(template)
    dest_arr = np.full(
        (template.height, template.width), DEM_NODATA, dtype=np.float32
    )
    n_tiles = 0
    for tw, ts, te, tn, w, h in iter_tiles(
        west, south, east, north, tile_px=tile_px
    ):
        url = dem_export_url(west=tw, south=ts, east=te, north=tn, width=w, height=h)
        payload = getter(url)
        if payload[:4] not in (b"II*\x00", b"MM\x00*"):
            raise FetchError(f"3DEP export is not TIFF: {url[:120]}")
        with MemoryFile(payload) as mem, mem.open() as src:
            tile = src.read(1)
            if tile.shape != (h, w):
                raise GateError(f"3DEP tile shape {tile.shape} != {(h, w)}")
            col0 = int(round((tw - west) / abs(template.transform.a)))
            row0 = int(round((north - tn) / abs(template.transform.e)))
            dest_arr[row0 : row0 + h, col0 : col0 + w] = tile
        n_tiles += 1
    inside = interior_mask(template)
    dest_arr[~inside] = DEM_NODATA
    if not np.isfinite(dest_arr[inside]).any():
        raise GateError("DEM has no finite cells inside the HUC")
    write_aligned(dest, template, dest_arr, dtype="float32", nodata=DEM_NODATA)
    valid = dest_arr[inside]
    valid = valid[np.isfinite(valid) & (valid != DEM_NODATA)]
    return {
        "n_tiles": n_tiles,
        "dem_min": float(valid.min()) if valid.size else None,
        "dem_max": float(valid.max()) if valid.size else None,
        "path": str(dest),
    }
