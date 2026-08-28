# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

import csv
from pathlib import Path

import numpy as np
from shapely.geometry import box, mapping

from floodmap.align import write_aligned
from floodmap.codes import MASK_OFR_OR_HWM, ZONE_UNSHADED_X
from floodmap.config import P_SFHA_CALIBRATED_NAME, P_SFHA_NODATA
from floodmap.huc import load_huc
from floodmap.map_d import build_d_map, cluster_ofr_features
from floodmap.template import write_synthetic_nlcd

HUC = Path(__file__).resolve().parent / "fixtures" / "huc.geojson"


def test_map_uses_calibrated_p_and_p_mean_in_popup(tmp_path: Path) -> None:
    huc = load_huc(HUC)
    tmpl = write_synthetic_nlcd(tmp_path / "nlcd.tif", huc)
    h, w = tmpl.height, tmpl.width
    p = np.full((h, w), 0.05, dtype=np.float32)
    p[h // 2, w // 2] = 0.8
    zone = np.full((h, w), ZONE_UNSHADED_X, dtype=np.uint8)
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[2:6, 2:6] = MASK_OFR_OR_HWM
    write_aligned(tmp_path / P_SFHA_CALIBRATED_NAME, tmpl, p, dtype="float32", nodata=P_SFHA_NODATA)
    write_aligned(tmp_path / "p_sfha.tif", tmpl, p, dtype="float32", nodata=P_SFHA_NODATA)
    write_aligned(tmp_path / "zone_class.tif", tmpl, zone, dtype="uint8", nodata=255)
    write_aligned(tmp_path / "mask_2008.tif", tmpl, mask, dtype="uint8", nodata=0)
    import rasterio
    from rasterio.crs import CRS
    from rasterio.warp import transform as rio_transform

    with rasterio.open(tmpl.path) as src:
        x, y = rasterio.transform.xy(src.transform, h // 2, w // 2, offset="center")
        lon, lat = rio_transform(src.crs, CRS.from_epsg(4269), [x], [y])
    fac = tmp_path / "fac.csv"
    head = tmp_path / "head.csv"
    with fac.open("w", encoding="utf-8", newline="") as fh:
        wcsv = csv.DictWriter(
            fh,
            fieldnames=["name", "lat", "lon", "p_max", "p_mean", "p_max_note", "d1_eligible", "zone_class"],
        )
        wcsv.writeheader()
        wcsv.writerow(
            {
                "name": "THURSDAY POOLS",
                "lat": lat[0],
                "lon": lon[0],
                "p_max": "0.80",
                "p_mean": "0.15",
                "p_max_note": "neighboring_land_cell",
                "d1_eligible": "True",
                "zone_class": "unshaded_x",
            }
        )
    with head.open("w", encoding="utf-8", newline="") as fh:
        wcsv = csv.DictWriter(
            fh,
            fieldnames=["name", "p_max", "p_mean", "p_max_note", "p_max_dr", "p_max_dc"],
        )
        wcsv.writeheader()
        wcsv.writerow(
            {
                "name": "THURSDAY POOLS",
                "p_max": "0.80",
                "p_mean": "0.15",
                "p_max_note": "neighboring_land_cell",
                "p_max_dr": "0",
                "p_max_dc": "1",
            }
        )
    dest = tmp_path / "map.html"
    info = build_d_map(
        interim_dir=tmp_path,
        facilities_csv=fac,
        headline_csv=head,
        dest_html=dest,
        downsample=4,
    )
    html = dest.read_text(encoding="utf-8")
    assert info["p_source"] == P_SFHA_CALIBRATED_NAME
    assert info["n_points"] == 1
    assert info["n_headline"] == 1
    assert info["n_ofr_polygons"] == 1
    assert "p_mean=0.150" in html or "p_mean=0.15" in html
    assert "THURSDAY POOLS" in html
    assert "calibrated" in html.lower()
    assert "p_sfha.tif" not in html
    assert "office to P_max cell" in html


def test_ofr_empty_stays_empty() -> None:
    assert cluster_ofr_features([]) == []


def test_ofr_speckle_clusters_to_two_named_reaches() -> None:
    martinsville = [
        mapping(box(-86.445, 39.422, -86.441, 39.426)),
        mapping(box(-86.442, 39.428, -86.441, 39.429)),
    ]
    paragon = [
        mapping(box(-86.568, 39.393, -86.564, 39.396)),
        mapping(box(-86.560, 39.398, -86.559, 39.399)),
    ]
    feats = cluster_ofr_features(martinsville + paragon)
    assert len(feats) == 2
    names = {f["properties"]["reach"] for f in feats}
    assert names == {
        "White River at Martinsville",
        "unnamed tributary of Fall Creek at Paragon",
    }
