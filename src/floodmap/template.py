# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""30 m EPSG:5070 template raster. Fixture writer plus live-grid check."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin

from floodmap.config import (
    FIXTURE_COLS,
    FIXTURE_NORTH,
    FIXTURE_ROWS,
    FIXTURE_WEST,
    TEMPLATE_CRS,
    TEMPLATE_KIND_FIXTURE,
    TEMPLATE_RES_M,
)
from floodmap.crs import epsg_from_rasterio, require_epsg
from floodmap.errors import GateError


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
