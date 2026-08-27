# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

import csv
import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.warp import transform as rio_transform

from floodmap.align import write_aligned
from floodmap.codes import P_DEFINITION, ZONE_SFHA, ZONE_UNSHADED_X
from floodmap.config import D1_HEADER, HYDRO_NODATA, P_SFHA_CALIBRATED_NAME, P_SFHA_NODATA
from floodmap.huc import load_huc
from floodmap.stage_d import buffer_p_stats, run_stage_d
from floodmap.template import write_synthetic_nlcd

HUC = Path(__file__).resolve().parent / "fixtures" / "huc.geojson"


def test_buffer_uses_neighbors_not_only_center() -> None:
    p = np.zeros((5, 5), dtype=np.float32)
    p[2, 2] = 0.1
    p[2, 3] = 0.9
    mx, mn, n = buffer_p_stats(p, 2, 2, radius=1, nodata=P_SFHA_NODATA)
    assert mx == pytest.approx(0.9, rel=1e-5)
    assert mn is not None and mn < mx
    assert n == 9


def test_stage_d_calibrated_join(tmp_path: Path) -> None:
    huc = load_huc(HUC)
    tmpl = write_synthetic_nlcd(tmp_path / "nlcd.tif", huc)
    with rasterio.open(tmpl.path) as src:
        inside = src.read(1) != src.nodata
        transform = src.transform
        crs = src.crs
    h, w = tmpl.height, tmpl.width
    ys, xs = np.where(inside)
    r0, c0 = int(ys[len(ys) // 3]), int(xs[len(xs) // 3])
    r1, c1 = int(ys[2 * len(ys) // 3]), int(xs[2 * len(xs) // 3])
    p = np.full((h, w), 0.05, dtype=np.float32)
    p[~inside] = P_SFHA_NODATA
    p[r0, c0] = 0.2
    p[r0, c0 + 1] = 0.85
    p[r1, c1] = 0.01
    zone = np.full((h, w), ZONE_UNSHADED_X, dtype=np.uint8)
    zone[r1, c1] = ZONE_SFHA
    mask = np.ones((h, w), dtype=np.uint8)
    hand = np.zeros((h, w), dtype=np.float32)
    write_aligned(tmp_path / P_SFHA_CALIBRATED_NAME, tmpl, p, dtype="float32", nodata=P_SFHA_NODATA)
    write_aligned(tmp_path / "p_sfha.tif", tmpl, p, dtype="float32", nodata=P_SFHA_NODATA)
    write_aligned(tmp_path / "zone_class.tif", tmpl, zone, dtype="uint8", nodata=255)
    write_aligned(tmp_path / "mask_2008.tif", tmpl, mask, dtype="uint8", nodata=0)
    write_aligned(tmp_path / "hand.tif", tmpl, hand, dtype="float32", nodata=HYDRO_NODATA)

    def xy(r, c):
        x, y = rasterio.transform.xy(transform, r, c, offset="center")
        lon, lat = rio_transform(crs, CRS.from_epsg(4269), [x], [y])
        return lat[0], lon[0]

    lat0, lon0 = xy(r0, c0)
    lat1, lon1 = xy(r1, c1)
    tri = tmp_path / "tri_huc.csv"
    with tri.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "key",
                "frs",
                "trifd",
                "name",
                "lat",
                "lon",
                "state",
                "huc",
                "year",
                "on_site_release_lb",
                "n_chem",
            ],
        )
        w.writeheader()
        w.writerow(
            {
                "key": "a",
                "frs": "a",
                "trifd": "",
                "name": "Plant A",
                "lat": lat0,
                "lon": lon0,
                "state": "IN",
                "huc": "05120201",
                "year": 2023,
                "on_site_release_lb": 100.0,
                "n_chem": 1,
            }
        )
        w.writerow(
            {
                "key": "b",
                "frs": "b",
                "trifd": "",
                "name": "Plant B",
                "lat": lat1,
                "lon": lon1,
                "state": "IN",
                "huc": "05120201",
                "year": 2023,
                "on_site_release_lb": 50.0,
                "n_chem": 1,
            }
        )
    a_path = tmp_path / "a.json"
    c_path = tmp_path / "c.json"
    a_path.write_text(
        json.dumps(
            {
                "stage": "A",
                "gate": "pass",
                "tri": {
                    "n_tris_huc_year": 2,
                    "reporting_year": 2023,
                    "n_dioxin_rows_held_grams": 0,
                },
                "ofr_reaches_intersecting_huc": [
                    "White River at Martinsville",
                    "unnamed tributary of Fall Creek at Paragon",
                ],
            }
        ),
        encoding="utf-8",
    )
    c_path.write_text(
        json.dumps(
            {
                "stage": "C",
                "gate": "pass",
                "p_definition": P_DEFINITION,
                "calibration": {
                    "probabilities_calibrated": True,
                    "p_source_calibrated": str(tmp_path / P_SFHA_CALIBRATED_NAME),
                },
            }
        ),
        encoding="utf-8",
    )
    report = run_stage_d(
        template_path=tmpl.path,
        interim_dir=tmp_path,
        out_dir=tmp_path / "out",
        stage_a_report_path=a_path,
        stage_c_report_path=c_path,
        tri_csv=tri,
    )
    assert report["d1_header"] == D1_HEADER
    assert report["p_source"] == P_SFHA_CALIBRATED_NAME
    assert report["expected_pounds_from_raw_p"] is False
    assert "share_in_sfha" not in report
    assert report["d2_n"] == 0
    assert report["d2_n_code1"] == 2
    assert report["d2_n_code2"] == 0
    assert "White River at Martinsville" in report["ofr_reaches_intersecting_huc"]
    assert report["n_tris_huc_year"] == 2
    head = next(s for s in report["d1_by_t"] if s["headline"])
    assert head["t"] == 0.75
    assert head["n_d1_p_max"] == 1
    assert head["expected_pounds_p_max"] > 0
    d1 = list(csv.DictReader((tmp_path / "out" / "d1.csv").open()))
    assert len(d1) == 1
    assert d1[0]["name"] == "Plant A"
    assert float(d1[0]["p_max"]) >= 0.75
    d2 = list(csv.DictReader((tmp_path / "out" / "d2.csv").open()))
    assert d2 == []
