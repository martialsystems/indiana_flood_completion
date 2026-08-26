# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

import pytest

from floodmap.claims import require_clean, scan_text
from floodmap.errors import ClaimBanError


def test_clean_pixel_report() -> None:
    text = (
        "P(sfha | hydro) on 30 m cells in HUC 05120201. "
        "On-site release lb tagged 2023. Zone AE."
    )
    assert scan_text(text) == []
    require_clean(text, source="t")


def test_bans_sibling_and_this_tree() -> None:
    assert "casualty_count" in scan_text("projected deaths in the floodplain")
    assert "climate_attribution" in scan_text("CMIP6 downscaled the hazard")
    assert "population_at_risk" in scan_text("people at risk near the plant")
    assert "tornado_count" in scan_text("tornado counts from the GCM")
    assert "tri_storage" in scan_text("chemicals stored annually at the plant")
    assert "p_as_100yr" in scan_text("100-year exceedance from the model")
    assert "unmapped_risk" in scan_text("these unmapped risk sites")
    with pytest.raises(ClaimBanError):
        require_clean("fatalities overnight", source="t")


def test_allows_firm_and_sfha_like() -> None:
    assert scan_text(
        "SFHA-like hydrology outside Zone A/AE. Flood hazard zone X. TRI reporter. "
        "June 7-9, 2008 inundation (OFR 2008-1322)."
    ) == []


def test_ofr_abstract_and_empty_d2_phrase() -> None:
    assert "casualty_count" in scan_text(
        "The flood caused three deaths and evacuation of thousands of residents."
    )
    assert "d2_empty_without_split" in scan_text("there was no 2008 overlap in the HUC")
    assert "unmapped_risk" not in scan_text(
        "SFHA-like hydrology outside Zone A/AE on unshaded X"
    )
