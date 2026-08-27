# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

import json
from pathlib import Path

import numpy as np
import rasterio

from floodmap.align import write_aligned
from floodmap.codes import P_DEFINITION, ZONE_UNSHADED_X
from floodmap.config import (
    DEM_NODATA,
    DIST_NODATA,
    HAND_NODATA_RULE,
    HYDRO_NODATA,
    P_SFHA_NODATA,
    STAGE_C_FEATURES,
)
from floodmap.huc import load_huc
from floodmap.stage_b import stream_composition
from floodmap.stage_c import hand_defined, run_stage_c, stratify_sample
from floodmap.template import write_synthetic_nlcd

HUC = Path(__file__).resolve().parent / "fixtures" / "huc.geojson"


def test_stream_composition_lines_vs_waterbody() -> None:
    inside = np.ones((4, 4), dtype=bool)
    dist_fl = np.full((4, 4), 100.0)
    dist_wb = np.full((4, 4), 100.0)
    dist_fl[0, :] = 0
    dist_wb[:, 0] = 0
    info = stream_composition(
        inside=inside, dist_flowline=dist_fl, dist_waterbody=dist_wb, n_stream_cells=8
    )
    assert info["dilated"] is False
    assert "no extra buffer_m" in info["rasterize"]
    assert info["n_flowline_only"] == 3
    assert info["n_waterbody_only"] == 3
    assert info["n_flowline_and_waterbody"] == 1


def test_hand_defined_excludes_nodata() -> None:
    inside = np.ones((3, 3), dtype=bool)
    hand = np.zeros((3, 3), dtype=np.float32)
    hand[1, 1] = HYDRO_NODATA
    hand[0, 0] = np.nan
    d = hand_defined(hand, inside)
    assert not d[1, 1]
    assert not d[0, 0]
    assert d[2, 2]


def test_stratify_keeps_all_positives() -> None:
    pos = np.zeros((10, 10), dtype=bool)
    pos[0, :5] = True
    neg = ~pos
    near = np.zeros_like(pos)
    near[9, :8] = True
    rng = np.random.default_rng(0)
    r, c = stratify_sample(pos=pos, neg=neg, unshaded_near=near, ratio=2.0, rng=rng)
    y = pos[r, c]
    assert int(y.sum()) == 5
    assert r.size == 5 + 10


def test_stage_c_oof_and_hand_nodata(tmp_path: Path) -> None:
    huc = load_huc(HUC)
    tmpl = write_synthetic_nlcd(tmp_path / "nlcd.tif", huc)
    minx, miny, maxx, maxy = huc.geom.bounds
    mid = (minx + maxx) / 2
    with rasterio.open(tmpl.path) as src:
        inside = src.read(1) != src.nodata
    h, w = tmpl.height, tmpl.width
    # Low HAND on the left (SFHA), high HAND on the right.
    hand = np.full((h, w), 20.0, dtype=np.float32)
    hand[:, : w // 2] = 1.0
    hand[~inside] = HYDRO_NODATA
    hand[inside][0] = HYDRO_NODATA  # one nodata interior after flatten... use coords
    ys, xs = np.where(inside)
    hand[ys[0], xs[0]] = HYDRO_NODATA
    sfha = np.zeros((h, w), dtype=np.uint8)
    sfha[:, : w // 2] = 1
    sfha[~inside] = 255
    slope = np.full((h, w), 0.02, dtype=np.float32)
    twi = np.where(hand < 5, 12.0, 6.0).astype(np.float32)
    dist_fl = np.where(hand < 5, 30.0, 400.0).astype(np.float32)
    dist_wb = np.full((h, w), 800.0, dtype=np.float32)
    dist_wb[h // 2, w // 2] = 0.0
    zone = np.full((h, w), ZONE_UNSHADED_X, dtype=np.uint8)
    for name, arr, nod in (
        ("hand", hand, HYDRO_NODATA),
        ("slope", slope, HYDRO_NODATA),
        ("twi", twi, HYDRO_NODATA),
        ("dist_flowline", dist_fl, DIST_NODATA),
        ("dist_waterbody", dist_wb, DIST_NODATA),
        ("sfha", sfha, 255),
        ("zone_class", zone, 255),
    ):
        write_aligned(tmp_path / f"{name}.tif", tmpl, arr, dtype=arr.dtype.name, nodata=nod)
    write_aligned(tmp_path / "dem.tif", tmpl, np.where(inside, 200.0, DEM_NODATA).astype(np.float32), dtype="float32", nodata=DEM_NODATA)

    left = {
        "type": "Feature",
        "properties": {"huc10": "0512020198", "name": "Left"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[minx, miny], [mid, miny], [mid, maxy], [minx, maxy], [minx, miny]]],
        },
    }
    right = {
        "type": "Feature",
        "properties": {"huc10": "0512020199", "name": "Right"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[mid, miny], [maxx, miny], [maxx, maxy], [mid, maxy], [mid, miny]]],
        },
    }
    a_path = tmp_path / "stage_a_report.json"
    b_path = tmp_path / "stage_b_report.json"
    a_path.write_text(
        json.dumps({"stage": "A", "gate": "pass", "firm_unshaded_x_ok": True, "hsg_incomplete": True}),
        encoding="utf-8",
    )
    b_path.write_text(
        json.dumps(
            {
                "stage": "B",
                "gate": "pass",
                "firm_unshaded_x_ok": True,
                "n_stream_cells": 1,
                "hsg_in_stack": False,
            }
        ),
        encoding="utf-8",
    )
    report = run_stage_c(
        template_path=tmpl.path,
        interim_dir=tmp_path,
        out_dir=tmp_path / "out",
        raw_dir=tmp_path / "raw",
        stage_a_report_path=a_path,
        stage_b_report_path=b_path,
        huc10_features=[left, right],
    )
    assert report["gate"] == "pass"
    assert report["p_definition"] == P_DEFINITION
    assert report["colorbar"] == P_DEFINITION
    assert report["filename"] == "p_sfha.tif"
    assert report["hsg_in_model"] is False
    assert report["stage_d_started"] is False
    assert report["d1_d2_written"] is False
    assert report["ofr_touched"] is False
    assert report["hand_nodata_rule"] == HAND_NODATA_RULE
    assert report["pr_auc"] > report["pr_auc_baseline"]
    assert report["probabilities_calibrated"] is False
    assert "hsg" not in report["features"]
    assert list(report["features"]) == list(STAGE_C_FEATURES)
    with rasterio.open(tmp_path / "p_sfha.tif") as src:
        p = src.read(1)
    assert p[ys[0], xs[0]] == P_SFHA_NODATA
    b = json.loads(b_path.read_text())
    assert b["stream_composition"]["dilated"] is False
    assert b["hand_nodata_filled_with_zero"] is False
    assert (tmp_path / "out" / "stage_c_report.json").is_file()
