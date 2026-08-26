# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS

from floodmap.codes import (
    MASK_IN_HUC_UNMAPPED,
    MASK_OFR_OR_HWM,
    MASK_OUTSIDE_HUC,
    OFR_APPENDIX2_ZIPS,
)
from floodmap.huc import load_huc
from floodmap.ofr2008 import build_2008_mask
from floodmap.template import write_synthetic_nlcd

HUC = Path(__file__).resolve().parent / "fixtures" / "huc.geojson"


def _depth_tif(path: Path, template, *, wet: bool) -> Path:
    with rasterio.open(template.path) as src:
        arr = np.zeros((src.height, src.width), dtype=np.float32)
        if wet:
            arr[src.height // 2, src.width // 2] = 1.5
        profile = src.profile.copy()
        profile.update(dtype="float32", nodata=-9999.0, count=1)
        path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(arr, 1)
    return path


def test_ofr_mask_only_mosaics_intersecting_reaches(tmp_path: Path) -> None:
    huc = load_huc(HUC)
    tmpl = write_synthetic_nlcd(tmp_path / "nlcd.tif", huc)
    wet = _depth_tif(tmp_path / "wet.tif", tmpl, wet=True)
    dry = _depth_tif(tmp_path / "dry.tif", tmpl, wet=False)
    extracted = {}
    for slug, _name, _fn in OFR_APPENDIX2_ZIPS:
        extracted[slug] = wet if slug == "white_martinsville" else dry
    dest = tmp_path / "mask.tif"
    info = build_2008_mask(
        tmpl,
        tmp_path / "raw",
        tmp_path / "interim",
        dest,
        already_extracted=extracted,
    )
    assert info["martinsville_paragon_measured"] is True
    assert "White River at Martinsville" in info["ofr_reaches_intersecting_huc"]
    assert "unnamed tributary of Fall Creek at Paragon" not in info["ofr_reaches_intersecting_huc"]
    by_slug = {r["slug"]: r["intersect_cells"] for r in info["reaches"]}
    assert by_slug["white_martinsville"] >= 1
    assert by_slug["unt_fall_paragon"] == 0
    assert by_slug["white_newberry"] == 0
    with rasterio.open(dest) as src:
        arr = src.read(1)
    assert MASK_OFR_OR_HWM in arr
    assert MASK_IN_HUC_UNMAPPED in arr
    assert MASK_OUTSIDE_HUC in arr
    assert info["sartor_ditch_img"] is False
    assert info["elnora_withdrawn"] is True
