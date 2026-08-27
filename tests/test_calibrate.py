# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

import json
from pathlib import Path

import numpy as np
import rasterio

from floodmap.align import write_aligned
from floodmap.calibrate import calibrate_leave_one_huc10, run_c_calibration
from floodmap.codes import P_DEFINITION
from floodmap.config import HYDRO_NODATA, P_SFHA_CALIBRATED_NAME, P_SFHA_NODATA
from floodmap.huc import load_huc
from floodmap.template import write_synthetic_nlcd

HUC = Path(__file__).resolve().parent / "fixtures" / "huc.geojson"


def test_isotonic_drops_mean_keeps_rank() -> None:
    # Both HUC-10s contain positives and negatives so L1O isotonic can transfer.
    p = np.array([[0.75, 0.40, 0.75, 0.40], [0.75, 0.40, 0.75, 0.40]], dtype=np.float32)
    y = np.array([[1, 0, 1, 0], [1, 0, 1, 0]], dtype=np.uint8)
    huc10 = np.array([[1, 1, 2, 2], [1, 1, 2, 2]], dtype=np.uint16)
    valid = np.ones_like(y, dtype=bool)
    cal = calibrate_leave_one_huc10(p, y, huc10, valid)
    assert cal[0, 0] > cal[0, 1]
    assert float(np.mean(cal)) < float(np.mean(p))


def test_run_c_calibration_keeps_raw_and_hand_nodata(tmp_path: Path) -> None:
    huc = load_huc(HUC)
    tmpl = write_synthetic_nlcd(tmp_path / "nlcd.tif", huc)
    minx, miny, maxx, maxy = huc.geom.bounds
    mid = (minx + maxx) / 2
    with rasterio.open(tmpl.path) as src:
        inside = src.read(1) != src.nodata
    h, w = tmpl.height, tmpl.width
    y = np.zeros((h, w), dtype=np.uint8)
    y[inside] = (np.indices((h, w))[1][inside] % 4 == 0).astype(np.uint8)
    y[~inside] = 255
    p_raw = np.where(y == 1, 0.78, 0.38).astype(np.float32)
    p_raw[~inside] = P_SFHA_NODATA
    hand = np.zeros((h, w), dtype=np.float32)
    hand[~inside] = HYDRO_NODATA
    ys, xs = np.where(inside)
    hand[ys[0], xs[0]] = HYDRO_NODATA
    p_raw[ys[0], xs[0]] = P_SFHA_NODATA
    huc10 = np.ones((h, w), dtype=np.uint16)
    huc10[:, w // 2 :] = 2
    huc10[~inside] = 0
    write_aligned(tmp_path / "p_sfha.tif", tmpl, p_raw, dtype="float32", nodata=P_SFHA_NODATA)
    write_aligned(tmp_path / "sfha.tif", tmpl, y, dtype="uint8", nodata=255)
    write_aligned(tmp_path / "hand.tif", tmpl, hand, dtype="float32", nodata=HYDRO_NODATA)
    write_aligned(tmp_path / "huc10.tif", tmpl, huc10, dtype="uint16", nodata=0)
    c_path = tmp_path / "stage_c_report.json"
    c_path.write_text(
        json.dumps(
            {
                "stage": "C",
                "gate": "pass",
                "p_definition": P_DEFINITION,
                "probabilities_calibrated": False,
            }
        ),
        encoding="utf-8",
    )
    add = run_c_calibration(
        template_path=tmpl.path,
        interim_dir=tmp_path,
        out_dir=tmp_path / "out",
        stage_c_report_path=c_path,
    )
    assert add["probabilities_calibrated"] is True
    assert add["raw_raster_kept"] is True
    assert add["oof_mean_p_calibrated"] < add["oof_mean_p_raw"]
    assert add["brier_calibrated"] < add["brier_raw"]
    assert abs(add["pr_auc_calibrated"] - add["pr_auc_raw"]) < 0.02
    assert (tmp_path / P_SFHA_CALIBRATED_NAME).is_file()
    with rasterio.open(tmp_path / "p_sfha.tif") as src:
        raw_after = src.read(1)
    assert np.allclose(raw_after[inside & (p_raw != P_SFHA_NODATA)], p_raw[inside & (p_raw != P_SFHA_NODATA)])
    with rasterio.open(tmp_path / P_SFHA_CALIBRATED_NAME) as src:
        cal = src.read(1)
    assert cal[ys[0], xs[0]] == P_SFHA_NODATA
