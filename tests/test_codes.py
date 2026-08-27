# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

import pytest

from floodmap.codes import (
    D1_ZONE_CLASS,
    MASK_IN_HUC_UNMAPPED,
    MASK_OFR_OR_HWM,
    MASK_OUTSIDE_HUC,
    P_DEFINITION,
    SHADED_X_ELIGIBLE_FOR_D1,
    TRI_ERROR_BUDGET_FIELDS,
    classify_firm_zone,
    d1_eligible,
    require_mask_unique,
    validate_d_report,
)
from floodmap.errors import GateError


def test_classify_sfha_and_floodway() -> None:
    assert classify_firm_zone("AE", "", "T") == (1, "sfha")
    assert classify_firm_zone("AE", "FLOODWAY", "T")[1] == "floodway"


def test_classify_zone_x_shaded_and_unshaded() -> None:
    assert classify_firm_zone("X", "AREA OF MINIMAL FLOOD HAZARD", "F")[1] == "unshaded_x"
    assert classify_firm_zone("X", "", "F")[1] == "unshaded_x"
    assert classify_firm_zone("X", "0.2 PCT ANNUAL CHANCE FLOOD HAZARD", "F")[1] == "shaded_x"
    assert SHADED_X_ELIGIBLE_FOR_D1 is False
    assert d1_eligible("unshaded_x") is True
    assert d1_eligible("shaded_x") is False
    assert d1_eligible("sfha") is False


def test_classify_unmapped_d_other() -> None:
    assert classify_firm_zone("OPEN WATER", "", "F")[1] == "unmapped"
    assert classify_firm_zone("AREA NOT INCLUDED", "", "F")[1] == "unmapped"
    assert classify_firm_zone("D", "", "F")[1] == "D"
    assert classify_firm_zone("ZZ", "LEVEE", "F")[1] == "other"


def test_mask_unique_requires_code1_and_code2_when_intersect() -> None:
    require_mask_unique({MASK_OUTSIDE_HUC, MASK_IN_HUC_UNMAPPED}, appendix2_intersects_huc=False)
    require_mask_unique(
        {MASK_OUTSIDE_HUC, MASK_IN_HUC_UNMAPPED, MASK_OFR_OR_HWM},
        appendix2_intersects_huc=True,
    )
    with pytest.raises(GateError, match="code 2"):
        require_mask_unique(
            {MASK_OUTSIDE_HUC, MASK_IN_HUC_UNMAPPED},
            appendix2_intersects_huc=True,
        )
    with pytest.raises(GateError, match="no Appendix 2"):
        require_mask_unique(
            {MASK_OUTSIDE_HUC, MASK_IN_HUC_UNMAPPED, MASK_OFR_OR_HWM},
            appendix2_intersects_huc=False,
        )
    with pytest.raises(GateError, match="required codes"):
        require_mask_unique({MASK_OUTSIDE_HUC}, appendix2_intersects_huc=False)


def test_validate_d_report_coverage_split_and_occupancy() -> None:
    ok = {
        "p_definition": P_DEFINITION,
        "d1_zone_class": D1_ZONE_CLASS,
        "imported_occupancy_path": "data/frozen/sibling_stage0_occupancy.json",
        "n_tris_huc_year": 12,
        "d2_n_code1": 12,
        "d2_n_code2": 0,
        "ofr_reaches_intersecting_huc": [],
        "p_source": "p_sfha_calibrated.tif",
    }
    validate_d_report(ok)
    bad = dict(ok)
    bad["share_in_sfha"] = 0.041422
    with pytest.raises(GateError, match="share_in_sfha"):
        validate_d_report(bad)
    missing = dict(ok)
    del missing["d2_n_code1"]
    with pytest.raises(GateError, match="d2_n_code1"):
        validate_d_report(missing)
    wrong_filter = dict(ok)
    wrong_filter["d1_zone_class"] = "sfha"
    with pytest.raises(GateError, match="unshaded_x"):
        validate_d_report(wrong_filter)
    raw = dict(ok)
    raw["p_source"] = "p_sfha.tif"
    with pytest.raises(GateError, match="p_sfha_calibrated"):
        validate_d_report(raw)
    raw_lb = dict(ok)
    raw_lb["expected_pounds_from_raw_p"] = True
    with pytest.raises(GateError, match="raw grid"):
        validate_d_report(raw_lb)


def test_tri_error_budget_fields_locked() -> None:
    assert "n_tris_huc_year" in TRI_ERROR_BUDGET_FIELDS
    assert "n_dioxin_rows_held_grams" in TRI_ERROR_BUDGET_FIELDS
    assert "reporting_year" in TRI_ERROR_BUDGET_FIELDS
