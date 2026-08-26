# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

from __future__ import annotations

from typing import Any

import pytest

from floodmap.config import HUC8, VECTOR_CRS, WBD_LAYER_URL
from floodmap.errors import CrsMissingError, EmptyHucError, FetchError
from floodmap.fetch import fetch_wbd, fetch_wbd_doc, wbd_query_url
from floodmap.huc import load_huc


def test_wbd_query_url_filters_huc8() -> None:
    url = wbd_query_url()
    assert WBD_LAYER_URL in url
    assert "huc8" in url
    assert HUC8 in url
    assert "outSR=4269" in url
    assert "f=geojson" in url


def test_fetch_wbd_writes_loadable_geojson(tmp_path) -> None:
    geom = {
        "type": "Polygon",
        "coordinates": [
            [[-86.3, 39.9], [-86.0, 39.9], [-86.0, 39.7], [-86.3, 39.7], [-86.3, 39.9]]
        ],
    }

    def get_json(url: str) -> dict[str, Any]:
        if url.endswith("?f=pjson"):
            return {"extent": {"spatialReference": {"wkid": 102100, "latestWkid": 3857}}}
        if "query" in url:
            return {
                "type": "FeatureCollection",
                "crs": {"type": "name", "properties": {"name": "EPSG:4269"}},
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "huc8": "05120201",
                            "name": "Upper White",
                            "states": "IN",
                            "areasqkm": 7046.97,
                        },
                        "geometry": geom,
                    }
                ],
            }
        raise AssertionError(url)

    wkid, doc = fetch_wbd_doc(get_json)
    assert wkid == VECTOR_CRS
    dest = fetch_wbd(tmp_path, get_json=get_json)
    layer = load_huc(dest)
    assert layer.huc8 == HUC8
    assert layer.states == "IN"
    assert layer.areasqkm == 7046.97
    assert not layer.geom.is_empty


def test_fetch_wbd_refuses_missing_crs() -> None:
    def get_json(url: str) -> dict[str, Any]:
        if url.endswith("?f=pjson"):
            return {"extent": {}}
        return {"features": []}

    with pytest.raises(CrsMissingError):
        fetch_wbd_doc(get_json)


def test_fetch_wbd_refuses_empty_and_wrong_huc() -> None:
    def empty(url: str) -> dict[str, Any]:
        if url.endswith("?f=pjson"):
            return {"spatialReference": {"wkid": 3857}}
        return {"type": "FeatureCollection", "features": []}

    with pytest.raises(EmptyHucError):
        fetch_wbd_doc(empty)

    def wrong(url: str) -> dict[str, Any]:
        if url.endswith("?f=pjson"):
            return {"spatialReference": {"wkid": 3857}}
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"huc8": "05120202"},
                    "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
                }
            ],
        }

    with pytest.raises(EmptyHucError, match="05120202"):
        fetch_wbd_doc(wrong)


def test_fetch_wbd_service_error() -> None:
    def get_json(url: str) -> dict[str, Any]:
        return {"error": {"message": "down"}}

    with pytest.raises(FetchError):
        fetch_wbd_doc(get_json)
