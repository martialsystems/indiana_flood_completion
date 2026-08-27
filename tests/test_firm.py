# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import pytest
import rasterio

from floodmap.codes import ZONE_FLOODWAY, ZONE_SFHA, ZONE_UNSHADED_X
from floodmap.config import FIRM_LAYER_URL, FIRM_WHERE
from floodmap.errors import GateError
from floodmap.firm import (
    assert_no_zone_filter,
    fetch_firm_pages,
    firm_attr,
    firm_envelope_query_url,
    firm_query_url,
    rasterize_firm,
    require_unshaded_majority,
    summarize_unmapped,
)
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


def test_firm_query_is_nfhl_unfiltered() -> None:
    assert "NFHL/MapServer/28" in FIRM_LAYER_URL
    assert FIRM_WHERE == "1=1"
    url = firm_query_url(offset=0)
    q = parse_qs(urlparse(url).query)
    assert q["where"] == ["1=1"]
    assert_no_zone_filter(url)
    with pytest.raises(GateError, match="filters zones"):
        assert_no_zone_filter(
            FIRM_LAYER_URL + "/query?where=FLD_ZONE%3D%27AE%27&f=geojson"
        )


def test_firm_attr_case_insensitive() -> None:
    assert firm_attr({"FLD_ZONE": "X", "ZONE_SUBTY": ""}, "fld_zone") == "X"
    assert firm_attr({"fld_zone": "AE"}, "FLD_ZONE") == "AE"


def test_firm_floodway_cells_are_sfha(tmp_path: Path) -> None:
    huc = load_huc(HUC)
    tmpl = write_synthetic_nlcd(tmp_path / "nlcd.tif", huc)
    minx, miny, maxx, maxy = huc.geom.bounds
    mid = (minx + maxx) / 2
    q1 = (minx + mid) / 2
    ae = {
        "type": "Feature",
        "properties": {"FLD_ZONE": "AE", "SFHA_TF": "T", "ZONE_SUBTY": ""},
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
    floodway = {
        "type": "Feature",
        "properties": {
            "FLD_ZONE": "AE",
            "SFHA_TF": "T",
            "ZONE_SUBTY": "FLOODWAY",
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [minx, miny],
                    [q1, miny],
                    [q1, maxy],
                    [minx, maxy],
                    [minx, miny],
                ]
            ],
        },
    }
    x = {
        "type": "Feature",
        "properties": {
            "FLD_ZONE": "X",
            "SFHA_TF": "F",
            "ZONE_SUBTY": "AREA OF MINIMAL FLOOD HAZARD",
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
        [ae, floodway, x],
        tmpl,
        sfha_dest=tmp_path / "sfha.tif",
        zone_dest=tmp_path / "zone.tif",
    )
    assert info["zone_class_counts"].get("floodway", 0) > 0
    with rasterio.open(tmp_path / "zone.tif") as src:
        z = src.read(1)
    with rasterio.open(tmp_path / "sfha.tif") as src:
        s = src.read(1)
    fw = z == ZONE_FLOODWAY
    assert fw.any()
    assert np.all(s[fw] == 1)
    assert info["sfha_counts"]["1"] >= int(info["zone_class_counts"]["floodway"]) + int(
        info["zone_class_counts"]["sfha"]
    )


def test_unmapped_speckle_is_not_a_community() -> None:
    inside = np.ones((20, 20), dtype=bool)
    zone = np.ones((20, 20), dtype=np.uint8)
    zone[5, 5] = 0
    zone[12, 3] = 0
    zone[12, 4] = 0
    info = summarize_unmapped(zone, inside)
    assert info["n_unmapped"] == 3
    assert info["pattern"] == "interior speckle"
    assert info["named_community_without_firm"] is None
    assert info["largest_component_cells"] == 2


def test_require_unshaded_majority() -> None:
    require_unshaded_majority({"unshaded_x": 100, "sfha": 10})
    with pytest.raises(GateError, match="NFHL Zone X"):
        require_unshaded_majority({"unshaded_x": 10, "sfha": 100})


def test_fetch_firm_huc_tiles_unfiltered() -> None:
    huc = load_huc(HUC)
    posts: list[dict] = []

    def get_json(url: str) -> dict:
        if "query" not in url:
            return {"extent": {"spatialReference": {"wkid": 4269, "latestWkid": 4269}}}
        raise AssertionError(f"GET query not expected: {url}")

    def post_json(url: str, fields: dict) -> dict:
        posts.append(fields)
        assert fields["where"] == "1=1"
        assert "FLD_ZONE" not in fields["where"]
        assert fields["geometryType"] == "esriGeometryEnvelope"
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "properties": {
                        "OBJECTID": 1,
                        "FLD_ZONE": "X",
                        "ZONE_SUBTY": "AREA OF MINIMAL FLOOD HAZARD",
                        "SFHA_TF": "F",
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                    },
                }
            ],
        }

    wkid, feats = fetch_firm_pages(
        get_json, huc=huc, post_json=post_json, pause_s=0
    )
    assert wkid == 4269
    assert len(feats) == 1
    assert posts
    env_url = firm_envelope_query_url(
        xmin=-86.2, ymin=39.7, xmax=-86.1, ymax=39.8, offset=0
    )
    assert_no_zone_filter(env_url)
