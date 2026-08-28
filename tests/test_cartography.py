# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

import csv
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.warp import transform as rio_transform

from floodmap.align import write_aligned
from floodmap.cartography import (
    CLS_HYDRO_OUTSIDE_AE,
    CLS_MAPPED_SFHA,
    CLS_OTHER,
    disagreement_classes,
    write_cartography,
)
from floodmap.codes import MASK_OFR_OR_HWM, ZONE_FLOODWAY, ZONE_SFHA, ZONE_UNSHADED_X
from floodmap.config import D_HEADLINE_T, P_SFHA_CALIBRATED_NAME, P_SFHA_NODATA
from floodmap.errors import GateError
from floodmap.huc import load_huc
from floodmap.template import write_synthetic_nlcd

HUC = Path(__file__).resolve().parent / "fixtures" / "huc.geojson"


def test_cyan_only_on_unshaded_x_at_headline_t() -> None:
    zone = np.array([[ZONE_UNSHADED_X, ZONE_SFHA], [ZONE_FLOODWAY, ZONE_UNSHADED_X]], dtype=np.uint8)
    p = np.array([[0.80, 0.90], [0.88, 0.20]], dtype=np.float32)
    cls = disagreement_classes(zone, p)
    assert cls[0, 0] == CLS_HYDRO_OUTSIDE_AE
    assert cls[0, 1] == CLS_MAPPED_SFHA
    assert cls[1, 0] == CLS_MAPPED_SFHA
    assert cls[1, 1] == CLS_OTHER
    assert D_HEADLINE_T == 0.75


def _point_from_cell(tmpl, row: int, col: int) -> tuple[float, float]:
    with rasterio.open(tmpl.path) as src:
        x, y = rasterio.transform.xy(src.transform, row, col, offset="center")
        lon, lat = rio_transform(src.crs, CRS.from_epsg(4269), [x], [y])
    return float(lat[0]), float(lon[0])


def test_cartography_uses_calibrated_p_and_p_mean_titles(tmp_path: Path) -> None:
    huc = load_huc(HUC)
    tmpl = write_synthetic_nlcd(tmp_path / "nlcd.tif", huc)
    h, w = tmpl.height, tmpl.width
    p = np.full((h, w), 0.05, dtype=np.float32)
    zone = np.full((h, w), ZONE_UNSHADED_X, dtype=np.uint8)
    zone[:, : w // 5] = ZONE_SFHA
    p[:, : w // 5] = 0.9
    p[h // 2, w // 2] = 0.82
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[2:6, 2:6] = MASK_OFR_OR_HWM
    mask[h - 8 : h - 4, w - 8 : w - 4] = MASK_OFR_OR_HWM
    write_aligned(tmp_path / P_SFHA_CALIBRATED_NAME, tmpl, p, dtype="float32", nodata=P_SFHA_NODATA)
    write_aligned(tmp_path / "zone_class.tif", tmpl, zone, dtype="uint8", nodata=255)
    write_aligned(tmp_path / "mask_2008.tif", tmpl, mask, dtype="uint8", nodata=0)
    names = [
        "THURSDAY POOLS",
        "FGF LLC",
        "ROYAL SPA CORP",
        "LINDE GAS & EQUIPMENT",
        "MAGNA POWERTRAIN EAST",
    ]
    means = ["0.152", "0.060", "0.113", "0.192", "0.098"]
    fac = tmp_path / "fac.csv"
    head = tmp_path / "head.csv"
    with fac.open("w", encoding="utf-8", newline="") as fh:
        wcsv = csv.DictWriter(fh, fieldnames=["name", "lat", "lon"])
        wcsv.writeheader()
        for i, name in enumerate(names):
            lat, lon = _point_from_cell(tmpl, h // 2, min(w // 2 + i, w - 2))
            wcsv.writerow({"name": name, "lat": lat, "lon": lon})
    with head.open("w", encoding="utf-8", newline="") as fh:
        wcsv = csv.DictWriter(
            fh,
            fieldnames=["name", "p_max", "p_mean", "p_max_note", "p_max_zone_class", "p_max_dr", "p_max_dc"],
        )
        wcsv.writeheader()
        notes = [
            ("neighboring_land_cell", "unshaded_x"),
            ("adjacent_hydro_cell", "floodway"),
            ("adjacent_hydro_cell", "sfha"),
            ("neighboring_land_cell", "unshaded_x"),
            ("neighboring_land_cell", "unshaded_x"),
        ]
        for name, mean, (note, zc) in zip(names, means, notes, strict=True):
            wcsv.writerow(
                {
                    "name": name,
                    "p_max": "0.77",
                    "p_mean": mean,
                    "p_max_note": note,
                    "p_max_zone_class": zc,
                    "p_max_dr": "1",
                    "p_max_dc": "-2",
                }
            )
    info = write_cartography(
        interim_dir=tmp_path,
        facilities_csv=fac,
        headline_csv=head,
        out_dir=tmp_path / "out",
        downsample=4,
    )
    assert info["p_source"] == P_SFHA_CALIBRATED_NAME
    assert info["raw_p_sampled"] is False
    assert not (tmp_path / "p_sfha.tif").is_file()
    out = tmp_path / "out"
    assert (out / info["disagreement_png"]).is_file()
    assert (out / info["zooms_png"]).is_file()
    assert (out / info["ofr_reaches_png"]).is_file()
    assert len(info["zoom_titles"]) == 5
    for name, mean, title in zip(names, means, info["zoom_titles"], strict=True):
        assert name in title
        assert "p_mean" in title
        assert mean in title
    assert info["n_ofr_polygons"] >= 1
    assert "Martinsville" in info["caption_ofr"] or any(
        "Martinsville" in (r or "") or "Paragon" in (r or "") for r in info["ofr_reaches"]
    )


def test_cartography_refuses_missing_calibrated(tmp_path: Path) -> None:
    try:
        write_cartography(
            interim_dir=tmp_path,
            facilities_csv=tmp_path / "f.csv",
            headline_csv=tmp_path / "h.csv",
            out_dir=tmp_path / "out",
        )
    except GateError as exc:
        assert P_SFHA_CALIBRATED_NAME in str(exc)
    else:
        raise AssertionError("expected GateError")
