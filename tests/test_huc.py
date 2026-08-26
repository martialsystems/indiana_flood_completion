# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

import json
from pathlib import Path

import pytest

from floodmap.errors import EmptyHucError, GateError
from floodmap.huc import load_huc

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "huc.geojson"


def test_load_fixture_huc() -> None:
    layer = load_huc(FIXTURE)
    assert layer.huc8 == "05120201"
    assert layer.crs == 4269
    assert not layer.geom.is_empty
    assert layer.n_features == 1


def test_wrong_huc_code(tmp_path: Path) -> None:
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    doc["features"][0]["properties"]["huc8"] = "05120202"
    path = tmp_path / "wrong.geojson"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(EmptyHucError, match="05120202"):
        load_huc(path)


def test_huc_refuses_wrong_state(tmp_path: Path) -> None:
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    doc["features"][0]["properties"]["states"] = "IL"
    path = tmp_path / "il.geojson"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(GateError, match="states"):
        load_huc(path)


def test_huc_refuses_area_outside_lock(tmp_path: Path) -> None:
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    doc["features"][0]["properties"]["areasqkm"] = 12.0
    path = tmp_path / "tiny.geojson"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(GateError, match="area_sqkm"):
        load_huc(path)


def test_empty_huc(tmp_path: Path) -> None:
    doc = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "EPSG:4269"}},
        "features": [],
    }
    path = tmp_path / "empty.geojson"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(EmptyHucError):
        load_huc(path)
