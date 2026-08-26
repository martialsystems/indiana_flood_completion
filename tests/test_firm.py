# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

from pathlib import Path

import rasterio

from floodmap.codes import ZONE_SFHA, ZONE_UNSHADED_X
from floodmap.firm import rasterize_firm
from floodmap.huc import load_huc
from floodmap.template import write_synthetic_nlcd

HUC = Path(__file__).resolve().parent / "fixtures" / "huc.geojson"


def test_firm_zone_class_not_just_sfha(tmp_path: Path) -> None:
    huc = load_huc(HUC)
    tmpl = write_synthetic_nlcd(tmp_path / "nlcd.tif", huc)
    minx, miny, maxx, maxy = huc.geom.bounds
    mid = (minx + maxx) / 2
    ae = {
        "type": "Feature",
        "properties": {"fld_zone": "AE", "sfha_tf": "T", "zone_subty": ""},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [minx, miny],
                    [mid, miny],
                    [mid, maxy],
                    [minx, maxy],
                    [minx, miny],
                ]
            ],
        },
    }
    x = {
        "type": "Feature",
        "properties": {
            "fld_zone": "X",
            "sfha_tf": "F",
            "zone_subty": "AREA OF MINIMAL FLOOD HAZARD",
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [mid, miny],
                    [maxx, miny],
                    [maxx, maxy],
                    [mid, maxy],
                    [mid, miny],
                ]
            ],
        },
    }
    info = rasterize_firm(
        [ae, x],
        tmpl,
        sfha_dest=tmp_path / "sfha.tif",
        zone_dest=tmp_path / "zone.tif",
    )
    assert info["sfha_has_0_and_1"]
    assert info["sfha_counts"]["0"] > 0
    assert info["sfha_counts"]["1"] > 0
    assert info["zone_class_counts"].get("unshaded_x", 0) > 0
    assert info["zone_class_counts"].get("sfha", 0) > 0
    with rasterio.open(tmp_path / "zone.tif") as src:
        z = src.read(1)
    assert ZONE_UNSHADED_X in z
    assert ZONE_SFHA in z
