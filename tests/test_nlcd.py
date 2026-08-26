# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import pytest
from rasterio.crs import CRS
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from floodmap.config import HUC8, NLCD_LAYER, TEMPLATE_CRS, TEMPLATE_KIND_NLCD, TEMPLATE_RES_M
from floodmap.errors import FetchError, GateError
from floodmap.fetch import iter_tiles, nlcd_wms_url, snap_bounds
from floodmap.huc import load_huc
from floodmap.stage0 import run_stage0
from floodmap.template import (
    clip_to_huc,
    huc_geom_5070,
    write_nlcd_template,
    write_synthetic_nlcd,
)

HUC = Path(__file__).resolve().parent / "fixtures" / "huc.geojson"


def _geotiff_bytes(
    west: float,
    south: float,
    east: float,
    north: float,
    width: int,
    height: int,
    value: int = 12,
    nodata: int = 0,
) -> bytes:
    transform = from_origin(west, north, TEMPLATE_RES_M, TEMPLATE_RES_M)
    data = np.full((height, width), value, dtype=np.uint8)
    data[0, 0] = 0
    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            height=height,
            width=width,
            count=1,
            dtype="uint8",
            crs=CRS.from_epsg(TEMPLATE_CRS),
            transform=transform,
            nodata=nodata,
        ) as dst:
            dst.write(data, 1)
        return mem.read()


def test_nlcd_wms_url_native_grid() -> None:
    url = nlcd_wms_url(west=1, south=2, east=3, north=4, width=10, height=20)
    parsed = urlparse(url)
    q = parse_qs(parsed.query)
    assert q["LAYERS"] == [NLCD_LAYER]
    assert q["CRS"] == [f"EPSG:{TEMPLATE_CRS}"]
    assert q["WIDTH"] == ["10"]
    assert q["HEIGHT"] == ["20"]
    assert q["FORMAT"] == ["image/geotiff"]
    assert q["BBOX"] == ["1,2,3,4"]


def test_iter_tiles_covers_remainder() -> None:
    tiles = list(iter_tiles(0, 0, 90, 90, res=30, tile_px=2))
    # 3x3 pixels, tile_px=2 -> 4 tiles (2x2, 1x2, 2x1, 1x1)
    assert len(tiles) == 4
    widths = [t[4] for t in tiles]
    heights = [t[5] for t in tiles]
    assert 1 in widths and 2 in widths
    assert 1 in heights and 2 in heights


def test_snap_bounds_pads() -> None:
    west, south, east, north, width, height = snap_bounds(31.0, 31.0, 59.0, 59.0, res=30, pad_px=1)
    assert west == 0.0
    assert south == 0.0
    assert east == 90.0
    assert north == 90.0
    assert width == 3
    assert height == 3


def test_synthetic_nlcd_stage0_nlcd_kind(tmp_path: Path) -> None:
    huc = load_huc(HUC)
    tif = tmp_path / "nlcd.tif"
    grid = write_synthetic_nlcd(tif, huc)
    assert grid.kind == TEMPLATE_KIND_NLCD
    assert grid.width > 32
    assert grid.height > 32
    report = run_stage0(
        huc_path=HUC,
        out_dir=tmp_path / "out",
        template_path=tif,
        template_kind=TEMPLATE_KIND_NLCD,
    )
    assert report["gate"] == "pass"
    assert report["template_kind"] == TEMPLATE_KIND_NLCD
    assert report["huc8"] == HUC8
    assert "template_sha256" in report


def test_clip_refuses_disjoint_raster(tmp_path: Path) -> None:
    huc = load_huc(HUC)
    far = tmp_path / "far.tif"
    from rasterio.transform import from_origin as fo
    import rasterio

    transform = fo(0.0, 1000.0, 30.0, 30.0)
    profile = {
        "driver": "GTiff",
        "height": 8,
        "width": 8,
        "count": 1,
        "dtype": "uint8",
        "crs": CRS.from_epsg(TEMPLATE_CRS),
        "transform": transform,
        "nodata": 255,
    }
    with rasterio.open(far, "w", **profile) as dst:
        dst.write(np.zeros((8, 8), dtype=np.uint8), 1)
    with pytest.raises(GateError, match="overlap|no valid"):
        clip_to_huc(far, huc, tmp_path / "clip.tif")


def test_write_nlcd_template_mosaic_from_injected_tiles(tmp_path: Path) -> None:
    huc = load_huc(HUC)
    geom = huc_geom_5070(huc)
    west, south, east, north, _, _ = snap_bounds(*geom.bounds)

    def get_bytes(url: str) -> bytes:
        q = parse_qs(urlparse(url).query)
        bbox = [float(x) for x in q["BBOX"][0].split(",")]
        w = int(q["WIDTH"][0])
        h = int(q["HEIGHT"][0])
        return _geotiff_bytes(bbox[0], bbox[1], bbox[2], bbox[3], w, h, value=9)

    dest = tmp_path / "template.tif"
    grid = write_nlcd_template(dest, huc, get_bytes=get_bytes, tile_px=400)
    assert grid.kind == TEMPLATE_KIND_NLCD
    assert grid.width > 32
    assert dest.is_file()
    import rasterio

    with rasterio.open(dest) as src:
        arr = src.read(1)
        assert 0 in np.unique(arr)
        assert src.nodata == 255


def test_nlcd_wms_xml_is_refused() -> None:
    from floodmap.fetch import fetch_nlcd_tile_bytes

    def get_bytes(url: str) -> bytes:
        return b"<?xml version='1.0'?><ServiceExceptionReport></ServiceExceptionReport>"

    with pytest.raises(FetchError, match="exception"):
        fetch_nlcd_tile_bytes(
            get_bytes, west=0, south=0, east=30, north=30, width=1, height=1
        )
