# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

import json
from pathlib import Path

import numpy as np
import rasterio

from floodmap.align import write_aligned
from floodmap.codes import P_DEFINITION
from floodmap.config import DEM_NODATA, HYDRO_NODATA
from floodmap.huc import load_huc
from floodmap.stage_b import run_stage_b
from floodmap.template import write_synthetic_nlcd

HUC = Path(__file__).resolve().parent / "fixtures" / "huc.geojson"


def test_stage_b_toy_path_writes_cogs_not_hsg(tmp_path: Path) -> None:
    huc = load_huc(HUC)
    tmpl = write_synthetic_nlcd(tmp_path / "nlcd.tif", huc)
    minx, miny, maxx, maxy = huc.geom.bounds
    dem = np.full((tmpl.height, tmpl.width), DEM_NODATA, dtype=np.float32)
    with rasterio.open(tmpl.path) as src:
        inside = src.read(1) != src.nodata
    for r in range(tmpl.height):
        dem[r, :] = 80.0 - r * 0.05
    dem[~inside] = DEM_NODATA
    write_aligned(tmp_path / "dem.tif", tmpl, dem, dtype="float32", nodata=DEM_NODATA)

    midx = (minx + maxx) / 2
    midy = (miny + maxy) / 2
    flowline = {
        "type": "Feature",
        "properties": {"objectid": 1, "ftype": 460},
        "geometry": {
            "type": "LineString",
            "coordinates": [[minx, midy], [maxx, midy]],
        },
    }
    lake = {
        "type": "Feature",
        "properties": {"objectid": 2, "gnis_name": "Toy Lake", "ftype": 390},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [midx - 0.01, midy - 0.01],
                    [midx + 0.01, midy - 0.01],
                    [midx + 0.01, midy + 0.01],
                    [midx - 0.01, midy + 0.01],
                    [midx - 0.01, midy - 0.01],
                ]
            ],
        },
    }
    a_path = tmp_path / "stage_a_report.json"
    a_path.write_text(
        json.dumps(
            {
                "stage": "A",
                "gate": "pass",
                "firm_unshaded_x_ok": True,
                "hsg_incomplete": True,
                "p_definition": P_DEFINITION,
            }
        ),
        encoding="utf-8",
    )
    report = run_stage_b(
        huc_path=HUC,
        template_path=tmpl.path,
        interim_dir=tmp_path,
        out_dir=tmp_path / "out",
        stage_a_report_path=a_path,
        flowline_features=[flowline],
        waterbody_features=[lake],
        area_features=[],
    )
    assert report["gate"] == "pass"
    assert report["stage"] == "B"
    assert report["twi_finite_on_dem_valid"] is True
    assert report["hsg_in_stack"] is False
    assert report["stage_c_started"] is False
    assert report["hand_is_flow_path"] is True
    assert report["n_waterbody_cells"] > 0
    assert report["n_slope_floor"] >= 0
    for name in ("twi", "hand", "slope", "dist_flowline", "dist_waterbody"):
        path = tmp_path / f"{name}.tif"
        assert path.is_file()
        with rasterio.open(path) as src:
            assert src.crs.to_epsg() == 5070
            arr = src.read(1)
        if name == "twi":
            finite = arr[inside]
            finite = finite[finite != HYDRO_NODATA]
            assert finite.size > 0
            assert np.isfinite(finite).all()
        if name == "dist_waterbody":
            assert (arr[inside] == 0).any()
    man = json.loads((tmp_path / "out" / "stack_manifest.json").read_text())
    assert man["hsg_in_stack"] is False
    assert man["materialized_dense_matrix"] is False
    names = [b["name"] for b in man["bands"]]
    assert names == ["slope", "twi", "hand", "dist_flowline", "dist_waterbody"]
    assert "hsg" not in names
