# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

import csv
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.warp import transform as rio_transform
from shapely.geometry import mapping, box

from floodmap.align import write_aligned
from floodmap.codes import ZONE_UNSHADED_X
from floodmap.config import P_SFHA_CALIBRATED_NAME, P_SFHA_NODATA
from floodmap.huc import load_huc
from floodmap.parcels import nearest_parcel, reading_for, run_five_site_parcels
from floodmap.template import write_synthetic_nlcd

HUC = Path(__file__).resolve().parent / "fixtures" / "huc.geojson"
NAMES = [
    "THURSDAY POOLS",
    "FGF LLC",
    "ROYAL SPA CORP",
    "LINDE GAS & EQUIPMENT",
    "MAGNA POWERTRAIN EAST",
]


def test_reading_and_snap() -> None:
    assert reading_for(office_id="A", max_id="A") == "max cell on office parcel"
    assert reading_for(office_id="A", max_id="B") == "max cell off office parcel"
    assert reading_for(office_id="A", max_id=None) == "max cell in unparceled area"
    poly = mapping(box(-86.20, 39.70, -86.19, 39.71))
    feat = {"type": "Feature", "geometry": poly, "properties": {"parcel_id": "X"}}
    hit, dist = nearest_parcel(-86.195, 39.705, [feat], snap_m=30)
    assert hit is not None
    assert dist == 0.0
    miss, _ = nearest_parcel(-86.0, 39.0, [feat], snap_m=30)
    assert miss is None


def _lonlat(tmpl, row: int, col: int) -> tuple[float, float]:
    with rasterio.open(tmpl.path) as src:
        x, y = rasterio.transform.xy(src.transform, row, col, offset="center")
        lon, lat = rio_transform(src.crs, CRS.from_epsg(4269), [x], [y])
    return float(lon[0]), float(lat[0])


def test_five_site_parcels_injected_getter(tmp_path: Path) -> None:
    huc = load_huc(HUC)
    tmpl = write_synthetic_nlcd(tmp_path / "nlcd.tif", huc)
    h, w = tmpl.height, tmpl.width
    p = np.full((h, w), 0.1, dtype=np.float32)
    zone = np.full((h, w), ZONE_UNSHADED_X, dtype=np.uint8)
    write_aligned(tmp_path / P_SFHA_CALIBRATED_NAME, tmpl, p, dtype="float32", nodata=P_SFHA_NODATA)
    write_aligned(tmp_path / "zone_class.tif", tmpl, zone, dtype="uint8", nodata=255)
    fac = tmp_path / "fac.csv"
    head = tmp_path / "head.csv"
    lons, lats = [], []
    with fac.open("w", encoding="utf-8", newline="") as fh:
        wcsv = csv.DictWriter(fh, fieldnames=["name", "lat", "lon"])
        wcsv.writeheader()
        for i, name in enumerate(NAMES):
            lon, lat = _lonlat(tmpl, h // 2, min(w // 3 + i * 3, w - 4))
            lons.append(lon)
            lats.append(lat)
            wcsv.writerow({"name": name, "lat": lat, "lon": lon})
    with head.open("w", encoding="utf-8", newline="") as fh:
        wcsv = csv.DictWriter(
            fh,
            fieldnames=["name", "p_max", "p_mean", "p_max_note", "p_max_zone_class", "p_max_dr", "p_max_dc"],
        )
        wcsv.writeheader()
        means = ["0.152", "0.060", "0.113", "0.192", "0.098"]
        for name, mean in zip(NAMES, means, strict=True):
            wcsv.writerow(
                {
                    "name": name,
                    "p_max": "0.77",
                    "p_mean": mean,
                    "p_max_note": "neighboring_land_cell",
                    "p_max_zone_class": "unshaded_x",
                    "p_max_dr": "0",
                    "p_max_dc": "2",
                }
            )

    def getter(_url: str) -> dict:
        feats = []
        for lon, lat, name in zip(lons, lats, NAMES, strict=True):
            pad = 0.00015
            feats.append(
                {
                    "type": "Feature",
                    "geometry": mapping(box(lon - pad, lat - pad, lon + pad, lat + pad)),
                    "properties": {"parcel_id": f"OFFICE-{name[:4]}", "county_fips": "18097", "SHAPE__Area": 1.0},
                }
            )
        return {"type": "FeatureCollection", "features": feats}

    d1 = tmp_path / "d1_headline.csv"
    d1.write_text("keep\n", encoding="utf-8")
    info = run_five_site_parcels(
        interim_dir=tmp_path,
        facilities_csv=fac,
        headline_csv=head,
        out_dir=tmp_path / "parcels",
        get_json=getter,
    )
    assert info["n_sites"] == 5
    assert info["d_tables_rewritten"] is False
    assert info["raw_p_sampled"] is False
    assert d1.read_text(encoding="utf-8") == "keep\n"
    assert (tmp_path / "parcels" / "zooms_parcels.png").is_file()
    assert (tmp_path / "parcels" / "five_sites.geojson").is_file()
    assert len(info["sites"]) == 5
    for row, mean in zip(info["sites"], means, strict=True):
        assert row["p_mean"] == float(mean)
        assert "p_mean" in str(row)
    assert all("p_mean" in t for t in info["zoom_titles"])
    assert "THURSDAY POOLS" in info["caption"]
