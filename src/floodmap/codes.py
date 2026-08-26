# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Locked Stage A codebooks: FIRM zone_class and OFR 2008-1322 mask.

Do not treat OFR Appendix 2 as a basin flood layer. Do not substitute
SIM 3251 / SIM 3231 for the Appendix 2 ERDAS grids.
"""

from __future__ import annotations

from typing import Any, Mapping

from floodmap.errors import GateError

# 2008 three-state mask (uint8). Code 3 is optional.
MASK_OUTSIDE_HUC = 0
MASK_IN_HUC_UNMAPPED = 1
MASK_OFR_OR_HWM = 2
MASK_HWM_BUFFER_ONLY = 3

MASK_2008_REQUIRED = frozenset({MASK_OUTSIDE_HUC, MASK_IN_HUC_UNMAPPED})
MASK_2008_IF_INTERSECT = MASK_OFR_OR_HWM

# FIRM zone_class (uint8). D1 uses unshaded_x only.
ZONE_UNMAPPED = 0
ZONE_SFHA = 1
ZONE_FLOODWAY = 2
ZONE_SHADED_X = 3
ZONE_UNSHADED_X = 4
ZONE_D = 5
ZONE_OTHER = 6

ZONE_CLASS_NAME = {
    ZONE_UNMAPPED: "unmapped",
    ZONE_SFHA: "sfha",
    ZONE_FLOODWAY: "floodway",
    ZONE_SHADED_X: "shaded_x",
    ZONE_UNSHADED_X: "unshaded_x",
    ZONE_D: "D",
    ZONE_OTHER: "other",
}
ZONE_CLASS_CODE = {name: code for code, name in ZONE_CLASS_NAME.items()}

D1_ZONE_CLASS = "unshaded_x"
D1_ZONE_CODE = ZONE_UNSHADED_X
# Shaded X (0.2% annual chance) is mapped FEMA moderate hazard. It is Zone X
# in speech and is not eligible for D1. Count it in a sensitivity column.
SHADED_X_ELIGIBLE_FOR_D1 = False

P_DEFINITION = "P(sfha | hydro)"

OFR_2008_1322_URL = "https://pubs.usgs.gov/of/2008/1322/"
OFR_APPENDIX2_LABEL = "June 7-9, 2008 inundation (OFR 2008-1322)"
OFR_NOT_SUBSTITUTES = ("SIM 3251", "SIM 3231")
OFR_ZIP_BASE = "https://pubs.usgs.gov/of/2008/1322/zip/"
# (slug, display name, zip filename). 17 Appendix 2 reaches. Not a basin layer.
OFR_APPENDIX2_ZIPS: tuple[tuple[str, str, str], ...] = (
    ("blue_edinburgh", "Blue River at Edinburgh", "blue_edinburgh.ZIP"),
    ("canary_franklin", "Canary Ditch at Franklin", "canary_franklin.ZIP"),
    ("clifty_columbus", "Clifty Creek at Columbus", "clifty_columbus.ZIP"),
    ("eastfk_white_columbus", "East Fork White River at Columbus", "eastfk_white_columbus.ZIP"),
    ("eastfk_white_seymour", "East Fork White River at Seymour", "eastfk_white_seymour.ZIP"),
    ("eastside_swale_edinburgh", "East Side Swale at Edinburgh", "eastside_swale_edinburgh.ZIP"),
    ("eel_worthington", "Eel River at Worthington", "eel_worthington.ZIP"),
    ("flatrock_columbus", "Flatrock River at Columbus", "flatrock_columbus.ZIP"),
    ("haw_columbus", "Haw Creek at Columbus", "haw_columbus.ZIP"),
    ("hurricane_franklin", "Hurricane Creek at Franklin", "hurricane_franklin.ZIP"),
    ("unt_fall_paragon", "unnamed tributary of Fall Creek at Paragon", "unt_fall_paragon.ZIP"),
    ("unt_youngs_franklin", "unnamed tributary of Youngs Creek at Franklin", "unt_youngs_franklin.ZIP"),
    ("white_martinsville", "White River at Martinsville", "white_martinsville.ZIP"),
    ("white_newberry", "White River at Newberry", "white_newberry.ZIP"),
    ("white_spencer", "White River at Spencer", "white_spencer.ZIP"),
    ("white_worthington", "White River at Worthington", "white_worthington.ZIP"),
    ("youngs_franklin", "Youngs Creek at Franklin", "youngs_franklin.ZIP"),
)
OFR_CANDIDATE_SLUGS = frozenset({"white_martinsville", "unt_fall_paragon"})
# No Appendix 2 raster. Do not invent from HWMs unless code 3 is written.
OFR_NO_RASTER = ("Sartor Ditch at Martinsville", "Elnora (withdrawn)")

# Appendix 2 mapped communities (reach-scale .img grids). Not a HUC layer.
OFR_APPENDIX2_COMMUNITIES: tuple[tuple[str, str, str], ...] = (
    ("Columbus", "East Fork / Driftwood / Flatrock", "outside"),
    ("Edinburgh", "East Fork / Driftwood / Flatrock", "outside"),
    ("Franklin", "East Fork / Driftwood / Flatrock", "outside"),
    ("Paragon", "edge of Upper White", "maybe"),
    ("Seymour", "East Fork White", "outside"),
    ("Spencer", "Lower / mid White", "unlikely"),
    ("Martinsville", "edge of Upper White", "maybe"),
    ("Newberry", "05120202 Lower White", "outside"),
    ("Worthington", "05120202 Lower White", "outside"),
)

TRI_ERROR_BUDGET_FIELDS: tuple[str, ...] = (
    "n_dropped_missing_xy",
    "n_dropped_out_of_huc",
    "n_dropped_non_in",
    "n_dioxin_rows_held_grams",
    "reporting_year",
    "n_excluded_off_site",
    "n_tris_huc_year",
)

_SFHA_ZONES = frozenset({"A", "AE", "AH", "AO", "AR", "A99", "V", "VE"})
_UNMAPPED_ZONES = frozenset({"", "OPEN WATER", "AREA NOT INCLUDED"})


def _sfha_true(sfha_tf: object) -> bool:
    token = str(sfha_tf or "").strip().upper()
    return token in {"T", "TRUE", "1", "YES"}


def classify_firm_zone(
    fld_zone: object,
    zone_subty: object = "",
    sfha_tf: object = "",
) -> tuple[int, str]:
    """Return (zone_code, zone_class) from IndianaMap FIRM attributes."""
    zone = str(fld_zone or "").strip().upper()
    sub = str(zone_subty or "").strip().upper()
    sfha = _sfha_true(sfha_tf)
    if "FLOODWAY" in sub and (sfha or zone in _SFHA_ZONES):
        return ZONE_FLOODWAY, "floodway"
    if sfha or zone in _SFHA_ZONES:
        return ZONE_SFHA, "sfha"
    if zone == "D":
        return ZONE_D, "D"
    if zone == "X" or "MINIMAL FLOOD" in sub or "0.2" in sub:
        if "0.2" in sub or "SHADED" in sub:
            return ZONE_SHADED_X, "shaded_x"
        return ZONE_UNSHADED_X, "unshaded_x"
    if zone in _UNMAPPED_ZONES or "NOT INCLUDED" in zone:
        return ZONE_UNMAPPED, "unmapped"
    return ZONE_OTHER, "other"


def d1_eligible(zone_class: str) -> bool:
    if zone_class == "shaded_x":
        return SHADED_X_ELIGIBLE_FOR_D1
    return zone_class == D1_ZONE_CLASS


def require_mask_unique(values: set[int], *, appendix2_intersects_huc: bool) -> None:
    missing = MASK_2008_REQUIRED - values
    if missing:
        raise GateError(f"2008 mask missing required codes {sorted(missing)}")
    if appendix2_intersects_huc and MASK_2008_IF_INTERSECT not in values:
        raise GateError("Appendix 2 intersects HUC but mask has no code 2")
    if not appendix2_intersects_huc and MASK_2008_IF_INTERSECT in values:
        raise GateError("mask has code 2 but no Appendix 2 raster intersects HUC")


def validate_d_report(obj: Mapping[str, Any]) -> None:
    """Fail closed if a Stage D payload omits the coverage split or retunes occupancy."""
    if obj.get("p_definition") != P_DEFINITION:
        raise GateError("Stage D p_definition must be P(sfha | hydro)")
    if obj.get("d1_zone_class") != D1_ZONE_CLASS:
        raise GateError(f"Stage D d1_zone_class must be {D1_ZONE_CLASS}")
    path = obj.get("imported_occupancy_path")
    if not path:
        raise GateError("Stage D must cite imported_occupancy_path")
    if "n_tris_huc_year" not in obj:
        raise GateError("Stage D must report n_tris_huc_year")
    if "share_in_sfha" in obj:
        raise GateError("Stage D must not print share_in_sfha as this tree's occupancy")
    for key in ("d2_n_code1", "d2_n_code2", "ofr_reaches_intersecting_huc"):
        if key not in obj:
            raise GateError(f"Stage D missing 2008 coverage field {key}")
    reaches = obj.get("ofr_reaches_intersecting_huc")
    if not isinstance(reaches, (list, tuple)):
        raise GateError("ofr_reaches_intersecting_huc must be a list")
    try:
        n1 = int(obj["d2_n_code1"])
        n2 = int(obj["d2_n_code2"])
    except (TypeError, ValueError) as exc:
        raise GateError("d2_n_code1/code2 must be integers") from exc
    if n1 < 0 or n2 < 0:
        raise GateError("d2 coverage counts must be >= 0")
    # Zero D2 rows is a coverage result. The split must still be present.
    del n1, n2, path
