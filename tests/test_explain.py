# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

import csv
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.warp import transform as rio_transform

from floodmap.align import write_aligned
from floodmap.config import HYDRO_NODATA, P_SFHA_CALIBRATED_NAME, P_SFHA_NODATA, STAGE_C_FEATURES
from floodmap.explain import run_d_shap
from floodmap.huc import load_huc
from floodmap.template import write_synthetic_nlcd

HUC = Path(__file__).resolve().parent / "fixtures" / "huc.geojson"


def test_shap_global_and_headline_have_p_mean(tmp_path: Path) -> None:
    huc = load_huc(HUC)
    tmpl = write_synthetic_nlcd(tmp_path / "nlcd.tif", huc)
    h, w = tmpl.height, tmpl.width
    with rasterio.open(tmpl.path) as src:
        inside = src.read(1) != src.nodata
    hand = np.where(inside, 8.0, HYDRO_NODATA).astype(np.float32)
    hand[:, : w // 3] = 1.0
    sfha = np.zeros((h, w), dtype=np.uint8)
    sfha[:, : w // 3] = 1
    sfha[~inside] = 255
    slope = np.full((h, w), 0.05, dtype=np.float32)
    twi = np.where(hand < 3, 12.0, 5.0).astype(np.float32)
    dist_fl = np.where(hand < 3, 40.0, 400.0).astype(np.float32)
    dist_wb = np.full((h, w), 800.0, dtype=np.float32)
    write_aligned(tmp_path / "hand.tif", tmpl, hand, dtype="float32", nodata=HYDRO_NODATA)
    write_aligned(tmp_path / "sfha.tif", tmpl, sfha, dtype="uint8", nodata=255)
    write_aligned(tmp_path / "slope.tif", tmpl, slope, dtype="float32", nodata=HYDRO_NODATA)
    write_aligned(tmp_path / "twi.tif", tmpl, twi, dtype="float32", nodata=HYDRO_NODATA)
    write_aligned(tmp_path / "dist_flowline.tif", tmpl, dist_fl, dtype="float32", nodata=-1)
    write_aligned(tmp_path / "dist_waterbody.tif", tmpl, dist_wb, dtype="float32", nodata=-1)
    write_aligned(
        tmp_path / P_SFHA_CALIBRATED_NAME,
        tmpl,
        np.where(inside, 0.1, P_SFHA_NODATA).astype(np.float32),
        dtype="float32",
        nodata=P_SFHA_NODATA,
    )
    ys, xs = np.where(inside)
    r, c = int(ys[10]), int(xs[10])
    with rasterio.open(tmpl.path) as src:
        x, y = rasterio.transform.xy(src.transform, r, c, offset="center")
        lon, lat = rio_transform(src.crs, CRS.from_epsg(4269), [x], [y])
    fac = tmp_path / "fac.csv"
    head = tmp_path / "head.csv"
    with fac.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["name", "lat", "lon"])
        w.writeheader()
        w.writerow({"name": "THURSDAY POOLS", "lat": lat[0], "lon": lon[0]})
    with head.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["name", "p_max", "p_mean", "p_max_note", "p_max_dr", "p_max_dc"])
        w.writeheader()
        w.writerow(
            {
                "name": "THURSDAY POOLS",
                "p_max": "0.77",
                "p_mean": "0.15",
                "p_max_note": "neighboring_land_cell",
                "p_max_dr": "0",
                "p_max_dc": "0",
            }
        )
    rep = run_d_shap(
        template_path=tmpl.path,
        interim_dir=tmp_path,
        out_dir=tmp_path / "out",
        facilities_csv=fac,
        headline_csv=head,
        max_train=800,
    )
    assert rep["hsg_in_shap"] is False
    assert rep["raw_p_sampled"] is False
    assert [r["feature"] for r in rep["global_mean_abs_shap"]] == list(STAGE_C_FEATURES) or set(
        r["feature"] for r in rep["global_mean_abs_shap"]
    ) == set(STAGE_C_FEATURES)
    assert rep["headline_max_cells"]
    assert rep["headline_max_cells"][0]["p_mean"] == 0.15
    assert "hsg" not in (rep["headline_max_cells"][0]["features"])
    assert (tmp_path / "out" / "shap_global.png").is_file()
    assert rep["shap_global_png"] == "shap_global.png"
