# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

from floodmap.huc import load_huc
from floodmap.tri import clip_to_huc, parse_tri_1a
from pathlib import Path

HUC = Path(__file__).resolve().parent / "fixtures" / "huc.geojson"

CSV = """YEAR,TRIFD,FRS ID,FACILITY NAME,ST,LATITUDE,LONGITUDE,CHEMICAL,UNIT OF MEASURE,ON-SITE RELEASE TOTAL,OFF-SITE RELEASE TOTAL
2023,IN123,110000000001,IN HUC PLANT,IN,39.80,-86.15,BENZENE,Pounds,10,0
2023,IN123,110000000001,IN HUC PLANT,IN,39.80,-86.15,DIOXIN AND DIOXIN-LIKE COMPOUNDS,Grams,5,0
2023,IL999,110000000002,OUT OF STATE,IL,41.8,-87.6,LEAD,Pounds,99,0
2023,IN999,110000000003,OUT OF HUC,IN,41.5,-85.0,LEAD,Pounds,20,1
"""


def test_tri_error_budget_and_huc_clip() -> None:
    by_fac, budget = parse_tri_1a(CSV, year=2023)
    assert budget["reporting_year"] == 2023
    assert budget["n_dropped_non_in"] >= 1
    assert budget["n_dioxin_rows_held_grams"] >= 1
    assert budget["n_excluded_off_site"] >= 1
    huc = load_huc(HUC)
    kept, n_out = clip_to_huc(by_fac.values(), huc)
    assert n_out >= 1
    assert any(abs(r["on_site_release_lb"] - 10.0) < 1e-6 for r in kept)
    assert all(r["huc"] == "05120201" for r in kept)
    assert all(r["state"] == "IN" for r in kept)
