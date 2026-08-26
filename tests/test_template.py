# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin

import pytest

from floodmap.config import TEMPLATE_CRS, TEMPLATE_RES_M
from floodmap.errors import GateError
from floodmap.template import inspect_template, write_fixture_template


def test_write_and_inspect_fixture(tmp_path: Path) -> None:
    path = tmp_path / "template.tif"
    grid = write_fixture_template(path)
    assert grid.crs == TEMPLATE_CRS
    assert grid.res_m == TEMPLATE_RES_M
    assert grid.kind == "fixture"
    again = inspect_template(path, kind="fixture")
    assert again.width == grid.width
    assert again.height == grid.height


def test_inspect_rejects_wrong_resolution(tmp_path: Path) -> None:
    path = tmp_path / "coarse.tif"
    transform = from_origin(680_000.0, 1_920_000.0, 90.0, 90.0)
    profile = {
        "driver": "GTiff",
        "height": 8,
        "width": 8,
        "count": 1,
        "dtype": "uint8",
        "crs": CRS.from_epsg(TEMPLATE_CRS),
        "transform": transform,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(np.zeros((8, 8), dtype=np.uint8), 1)
    with pytest.raises(GateError, match="resolution"):
        inspect_template(path, kind="fixture")
