# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin

from floodmap.align import require_live_template, template_fingerprint, warp_to_template
from floodmap.config import TEMPLATE_CRS, TEMPLATE_KIND_FIXTURE, TEMPLATE_RES_M
from floodmap.errors import GateError
from floodmap.huc import load_huc
from floodmap.template import inspect_template, write_fixture_template, write_synthetic_nlcd

HUC = Path(__file__).resolve().parent / "fixtures" / "huc.geojson"


def test_refuse_fixture_template(tmp_path: Path) -> None:
    grid = write_fixture_template(tmp_path / "fix.tif")
    with pytest.raises(GateError, match="nlcd_2021"):
        require_live_template(grid)


def test_warp_to_template_matches_grid(tmp_path: Path) -> None:
    huc = load_huc(HUC)
    tmpl = write_synthetic_nlcd(tmp_path / "nlcd.tif", huc)
    src = tmp_path / "src.tif"
    transform = from_origin(tmpl.transform.c - 60, tmpl.transform.f + 60, 60.0, 60.0)
    data = np.ones((8, 8), dtype=np.float32) * 5.0
    profile = {
        "driver": "GTiff",
        "height": 8,
        "width": 8,
        "count": 1,
        "dtype": "float32",
        "crs": CRS.from_epsg(TEMPLATE_CRS),
        "transform": transform,
        "nodata": -1,
    }
    with rasterio.open(src, "w", **profile) as dst:
        dst.write(data, 1)
    dest = tmp_path / "aligned.tif"
    warp_to_template(src, tmpl, dest, dst_nodata=-1, dtype="float32")
    aligned = inspect_template(dest, kind="nlcd_2021")
    assert aligned.width == tmpl.width
    assert aligned.height == tmpl.height
    assert tuple(aligned.transform)[:6] == tuple(tmpl.transform)[:6]
    fp = template_fingerprint(tmpl)
    assert fp["crs"] == TEMPLATE_CRS
    assert fp["width"] == tmpl.width
    assert "transform_sha256" in fp
