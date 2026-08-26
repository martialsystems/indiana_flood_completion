# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from floodmap.codes import OFR_APPENDIX2_ZIPS
from floodmap.huc import load_huc
from floodmap.stage_a import run_stage_a
from floodmap.template import write_synthetic_nlcd
from tests.test_ofr2008 import _depth_tif
from tests.test_tri import CSV

HUC = Path(__file__).resolve().parent / "fixtures" / "huc.geojson"


def _tiff_bytes(width: int, height: int, value: float = 200.0) -> bytes:
    transform = from_origin(0, height * 30, 30, 30)
    data = np.full((height, width), value, dtype=np.float32)
    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            height=height,
            width=width,
            count=1,
            dtype="float32",
            crs=CRS.from_epsg(5070),
            transform=transform,
            nodata=-9999,
        ) as dst:
            dst.write(data, 1)
        return mem.read()


def test_stage_a_injected_path(tmp_path: Path) -> None:
    huc = load_huc(HUC)
    tmpl = write_synthetic_nlcd(tmp_path / "nlcd.tif", huc)
    minx, miny, maxx, maxy = huc.geom.bounds
    mid = (minx + maxx) / 2
    ae = {
        "type": "Feature",
        "properties": {"fld_zone": "AE", "sfha_tf": "T", "zone_subty": ""},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[minx, miny], [mid, miny], [mid, maxy], [minx, maxy], [minx, miny]]],
        },
    }
    xz = {
        "type": "Feature",
        "properties": {
            "fld_zone": "X",
            "sfha_tf": "F",
            "zone_subty": "AREA OF MINIMAL FLOOD HAZARD",
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[mid, miny], [maxx, miny], [maxx, maxy], [mid, maxy], [mid, miny]]],
        },
    }
    line = {
        "type": "Feature",
        "properties": {"objectid": 1},
        "geometry": {
            "type": "LineString",
            "coordinates": [[minx, (miny + maxy) / 2], [maxx, (miny + maxy) / 2]],
        },
    }

    def get_json(url: str) -> dict:
        if "FIRM" in url and "query" not in url:
            return {"extent": {"spatialReference": {"wkid": 4269, "latestWkid": 4269}}}
        if "FIRM" in url and "query" in url:
            return {"type": "FeatureCollection", "features": [ae, xz]}
        if "nhd/MapServer/6" in url:
            return {"type": "FeatureCollection", "features": [line]}
        raise AssertionError(url)

    def get_bytes(url: str) -> bytes:
        q = parse_qs(urlparse(url).query)
        w = int((q.get("size") or ["32,32"])[0].split(",")[0])
        h = int((q.get("size") or ["32,32"])[0].split(",")[1])
        return _tiff_bytes(w, h)

    def sda_post(sql: str) -> dict:
        if "hydgrpdcd" in sql.lower() or "hydgrp" in sql.lower():
            return {"Table": [["mukey", "hydgrpdcd"], ["1", "B"], ["2", "B/D"]]}
        poly = {
            "type": "Polygon",
            "coordinates": [[[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]]],
        }
        return {"Table": [["mukey", "geojson"], ["1", poly], ["2", poly]]}

    wet = _depth_tif(tmp_path / "wet.tif", tmpl, wet=True)
    dry = _depth_tif(tmp_path / "dry.tif", tmpl, wet=False)
    extracted = {
        slug: wet if slug == "white_martinsville" else dry
        for slug, _n, _f in OFR_APPENDIX2_ZIPS
    }
    report = run_stage_a(
        huc_path=HUC,
        template_path=tmpl.path,
        raw_dir=tmp_path / "raw",
        interim_dir=tmp_path / "interim",
        out_dir=tmp_path / "out",
        get_json=get_json,
        get_bytes=get_bytes,
        sda_post=sda_post,
        tri_text=CSV,
        tri_year=2023,
        ofr_extracted=extracted,
    )
    assert report["gate"] == "pass"
    assert report["p_definition"] == "P(sfha | hydro)"
    assert report["martinsville_paragon_intersection"] == "measured, not assumed"
    assert "share_in_sfha" not in report
    assert report["tri"]["n_tris_huc_year"] >= 1
    assert report["tri"]["reporting_year"] == 2023
    assert "unshaded_x" in report["zone_class_counts"]
    assert "White River at Martinsville" in report["ofr_reaches_intersecting_huc"]
    assert (tmp_path / "out" / "stage_a_report.json").is_file()
    assert (tmp_path / "interim" / "dem.tif").is_file()
    assert (tmp_path / "interim" / "mask_2008.tif").is_file()
    assert (tmp_path / "interim" / "zone_class.tif").is_file()
