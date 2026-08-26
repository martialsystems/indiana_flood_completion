# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""30 m EPSG:5070 template raster. Fixture writer, clip, live-grid check."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.errors import WindowError
from rasterio.crs import CRS
from rasterio.features import rasterize
from rasterio.io import MemoryFile
from rasterio.mask import mask as rio_mask
from rasterio.merge import merge
from rasterio.transform import from_origin
from rasterio.warp import transform_geom
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

from floodmap.config import (
    FIXTURE_COLS,
    FIXTURE_NORTH,
    FIXTURE_ROWS,
    FIXTURE_WEST,
    NLCD_NODATA,
    NLCD_TILE_PX,
    TEMPLATE_CRS,
    TEMPLATE_KIND_FIXTURE,
    TEMPLATE_KIND_NLCD,
    TEMPLATE_RES_M,
    VECTOR_CRS,
)
from floodmap.crs import epsg_from_rasterio, require_epsg
from floodmap.errors import GateError
from floodmap.fetch import fetch_nlcd_tile_bytes, iter_tiles, snap_bounds
from floodmap.huc import HucLayer


@dataclass(frozen=True)
class TemplateGrid:
    path: Path
    crs: int
    res_m: float
    width: int
    height: int
    transform: rasterio.Affine
    kind: str


def write_fixture_template(path: Path) -> TemplateGrid:
    path.parent.mkdir(parents=True, exist_ok=True)
    transform = from_origin(FIXTURE_WEST, FIXTURE_NORTH, TEMPLATE_RES_M, TEMPLATE_RES_M)
    data = np.zeros((FIXTURE_ROWS, FIXTURE_COLS), dtype=np.uint8)
    profile = {
        "driver": "GTiff",
        "height": FIXTURE_ROWS,
        "width": FIXTURE_COLS,
        "count": 1,
        "dtype": "uint8",
        "crs": CRS.from_epsg(TEMPLATE_CRS),
        "transform": transform,
        "nodata": 255,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)
    return inspect_template(path, kind=TEMPLATE_KIND_FIXTURE)


def inspect_template(path: Path, *, kind: str) -> TemplateGrid:
    if not path.is_file():
        raise GateError(f"missing template: {path}")
    with rasterio.open(path) as src:
        epsg = require_epsg(epsg_from_rasterio(src.crs), expected=TEMPLATE_CRS)
        res_x = abs(src.transform.a)
        res_y = abs(src.transform.e)
        if abs(res_x - TEMPLATE_RES_M) > 1e-6 or abs(res_y - TEMPLATE_RES_M) > 1e-6:
            raise GateError(
                f"template resolution {res_x}x{res_y} m != {TEMPLATE_RES_M} m"
            )
        if src.width < 2 or src.height < 2:
            raise GateError(f"template too small: {src.width}x{src.height}")
        return TemplateGrid(
            path=path,
            crs=epsg,
            res_m=TEMPLATE_RES_M,
            width=src.width,
            height=src.height,
            transform=src.transform,
            kind=kind,
        )


def huc_geom_5070(huc: HucLayer) -> BaseGeometry:
    if huc.crs != VECTOR_CRS:
        raise GateError(f"HUC CRS {huc.crs} != {VECTOR_CRS} before warp")
    return shape(
        transform_geom(
            CRS.from_epsg(VECTOR_CRS),
            CRS.from_epsg(TEMPLATE_CRS),
            mapping(huc.geom),
        )
    )


def write_synthetic_nlcd(path: Path, huc: HucLayer) -> TemplateGrid:
    """Write a 30 m 5070 raster covering the HUC, for CI without MRLC."""
    geom = huc_geom_5070(huc)
    west, south, east, north, width, height = snap_bounds(*geom.bounds)
    transform = from_origin(west, north, TEMPLATE_RES_M, TEMPLATE_RES_M)
    rows = np.arange(height, dtype=np.uint16)[:, None]
    cols = np.arange(width, dtype=np.uint16)[None, :]
    data = ((rows + cols) % 101).astype(np.uint8)
    mask = rasterize(
        [(mapping(geom), 1)],
        out_shape=(height, width),
        transform=transform,
        fill=0,
        dtype="uint8",
        all_touched=False,
    )
    data = np.where(mask == 1, data, NLCD_NODATA).astype(np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": "uint8",
        "crs": CRS.from_epsg(TEMPLATE_CRS),
        "transform": transform,
        "nodata": NLCD_NODATA,
        "compress": "lzw",
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)
    return inspect_template(path, kind=TEMPLATE_KIND_NLCD)


def clip_to_huc(
    src_path: Path,
    huc: HucLayer,
    dest: Path,
    *,
    kind: str = TEMPLATE_KIND_NLCD,
) -> TemplateGrid:
    geom = huc_geom_5070(huc)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(src_path) as src:
        require_epsg(epsg_from_rasterio(src.crs), expected=TEMPLATE_CRS)
        try:
            window_arr, transform = rio_mask(
                src,
                [mapping(geom)],
                crop=True,
                nodata=NLCD_NODATA,
                all_touched=False,
                filled=True,
            )
        except (ValueError, WindowError) as exc:
            raise GateError("NLCD clip does not overlap HUC") from exc
        data = window_arr[0]
        if data.size == 0:
            raise GateError("NLCD clip is empty")
        valid = data != NLCD_NODATA
        if not np.any(valid):
            raise GateError("NLCD clip has no valid cells inside HUC")
        profile = src.profile.copy()
        profile.update(
            {
                "height": data.shape[0],
                "width": data.shape[1],
                "transform": transform,
                "nodata": NLCD_NODATA,
                "compress": "lzw",
                "driver": "GTiff",
            }
        )
    with rasterio.open(dest, "w", **profile) as dst:
        dst.write(data, 1)
    return inspect_template(dest, kind=kind)


def _nlcd_tile_with_valid_zero(payload: bytes):
    """WMS GeoTIFFs tag nodata=0. Zero is a valid impervious percent. Rewrite nodata to 255."""
    with MemoryFile(payload) as mem_in, mem_in.open() as src:
        data = src.read(1)
        profile = src.profile.copy()
        transform = src.transform
        crs = src.crs
        height, width = src.height, src.width
        dtype = src.dtypes[0]
    mem_out = MemoryFile()
    dst = mem_out.open(
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=dtype,
        crs=crs,
        transform=transform,
        nodata=NLCD_NODATA,
    )
    dst.write(data, 1)
    return mem_out, dst


def write_nlcd_template(
    dest: Path,
    huc: HucLayer,
    *,
    get_bytes,
    tile_px: int = NLCD_TILE_PX,
) -> TemplateGrid:
    geom = huc_geom_5070(huc)
    west, south, east, north, _w, _h = snap_bounds(*geom.bounds)
    datasets = []
    memfiles = []
    try:
        for tw, ts, te, tn, w, h in iter_tiles(
            west, south, east, north, tile_px=tile_px
        ):
            payload = fetch_nlcd_tile_bytes(
                get_bytes, west=tw, south=ts, east=te, north=tn, width=w, height=h
            )
            mem_out, ds = _nlcd_tile_with_valid_zero(payload)
            memfiles.append(mem_out)
            datasets.append(ds)
        if not datasets:
            raise GateError("NLCD WMS returned no tiles")
        mosaic, transform = merge(datasets, nodata=NLCD_NODATA)
        data = mosaic[0]
        dest.parent.mkdir(parents=True, exist_ok=True)
        unclipped = dest.with_name(dest.stem + "_unclipped.tif")
        profile = {
            "driver": "GTiff",
            "height": data.shape[0],
            "width": data.shape[1],
            "count": 1,
            "dtype": data.dtype,
            "crs": CRS.from_epsg(TEMPLATE_CRS),
            "transform": transform,
            "nodata": NLCD_NODATA,
            "compress": "lzw",
        }
        with rasterio.open(unclipped, "w", **profile) as dst:
            dst.write(data, 1)
    finally:
        for ds in datasets:
            ds.close()
        for mem in memfiles:
            mem.close()
    grid = clip_to_huc(unclipped, huc, dest, kind=TEMPLATE_KIND_NLCD)
    unclipped.unlink(missing_ok=True)
    return grid


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 256), b""):
            digest.update(chunk)
    return digest.hexdigest()
