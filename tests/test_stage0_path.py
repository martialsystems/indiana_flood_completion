# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

import json
from pathlib import Path

import pytest

from floodmap.config import HUC8, TEMPLATE_CRS, TEMPLATE_KIND_NLCD, TEMPLATE_RES_M
from floodmap.errors import GateError
from floodmap.stage0 import run_stage0

HUC = Path(__file__).resolve().parent / "fixtures" / "huc.geojson"


def test_stage0_fixture_writes_report(tmp_path: Path) -> None:
    out = tmp_path / "stage0"
    report = run_stage0(huc_path=HUC, out_dir=out)
    assert report["gate"] == "pass"
    assert report["stage"] == "0"
    assert report["huc8"] == HUC8
    assert report["unit"] == "pixel"
    assert report["p_definition"] == "P(sfha | hydro)"
    assert report["template_crs"] == TEMPLATE_CRS
    assert report["template_res_m"] == TEMPLATE_RES_M
    assert report["template_kind"] == "fixture"
    assert report["imported_occupancy"]["n_in_sfha"] == 120
    path = out / "stage0_report.json"
    assert path.is_file()
    disk = json.loads(path.read_text(encoding="utf-8"))
    assert disk["gate"] == "pass"
    tif = out / "template.tif"
    assert tif.is_file()


def test_stage0_nlcd_kind_requires_path(tmp_path: Path) -> None:
    with pytest.raises(GateError, match="path is required"):
        run_stage0(
            huc_path=HUC,
            out_dir=tmp_path / "stage0",
            template_kind=TEMPLATE_KIND_NLCD,
        )


def test_stage0_refuses_nlcd_kind_on_fixture_grid(tmp_path: Path) -> None:
    out = tmp_path / "stage0"
    first = run_stage0(huc_path=HUC, out_dir=out)
    tif = Path(out / "template.tif")
    assert first["template_kind"] == "fixture"
    with pytest.raises(GateError, match="fixture grid"):
        run_stage0(
            huc_path=HUC,
            out_dir=tmp_path / "stage0b",
            template_path=tif,
            template_kind=TEMPLATE_KIND_NLCD,
        )
