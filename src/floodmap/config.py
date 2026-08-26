# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Locked Stage 0 constants. Upper White 05120201."""

from __future__ import annotations

from pathlib import Path

HUC8 = "05120201"
HUC_NAME = "Upper White"
STATE_CODE = "IN"
STATE_FIPS = "18"
VECTOR_CRS = 4269
TEMPLATE_CRS = 5070
TEMPLATE_RES_M = 30.0
TEMPLATE_KIND_FIXTURE = "fixture"
TEMPLATE_KIND_NLCD = "nlcd_2021"

FROZEN_N_TRIS_JOINABLE = 2897
FROZEN_N_IN_SFHA = 120
FROZEN_SHARE_IN_SFHA = 0.041422
FROZEN_N_DROPPED_MISSING_XY = 13
FROZEN_CRS = 4269
FROZEN_DATE = "2026-08-25"

# Tiny Albers window over central Indiana for the fixture template.
FIXTURE_WEST = 680_000.0
FIXTURE_NORTH = 1_920_000.0
FIXTURE_ROWS = 32
FIXTURE_COLS = 32

USER_AGENT = "MartialSystemsResearch/indiana_flood_completion (stage0)"

WBD_LAYER_URL = (
    "https://hydro.nationalmap.gov/arcgis/rest/services/wbd/MapServer/4"
)
WBD_MAX_ALLOWABLE_OFFSET_DEG = 0.0001
WBD_GEOMETRY_PRECISION = 6
# USGS catalog ~2700 sq mi; live query 2026-08-26 was 7046.97 km2.
EXPECTED_AREA_SQKM = (6000.0, 8000.0)

NLCD_WMS_URL = "https://www.mrlc.gov/geoserver/mrlc_download/wms"
NLCD_LAYER = "NLCD_2021_Impervious_L48"
NLCD_WMS_VERSION = "1.3.0"
NLCD_TILE_PX = 2000
NLCD_NODATA = 255
NLCD_YEAR = 2021

FIRM_LAYER_URL = (
    "https://gisdata.in.gov/server/rest/services/Hosted/"
    "FIRM_Flood_Hazard_Zones_2023/FeatureServer/1"
)
FIRM_MAX_ALLOWABLE_OFFSET_DEG = 0.0001
FIRM_GEOMETRY_PRECISION = 6
FIRM_PAGE_SIZE = 1000
FIRM_EXPECTED_CRS = 4269

FRS_URL = "https://ordsext.epa.gov/FLA/www3/state_files/state_single_in.zip"
FRS_CSV_NAME = "STATE_SINGLE_IN.CSV"
TRI_PROGRAM = "TRIS"
TRI_YEAR_CANDIDATES = (2023, 2022, 2021)
# EPA TRI basic data file 1a (on-site releases), national zip, filtered to IN.
TRI_1A_URL_TMPL = (
    "https://www.epa.gov/system/files/other-files/{year_path}/us_1a_{year}.zip"
)

DEM_IMAGE_URL = (
    "https://elevation.nationalmap.gov/arcgis/rest/services/"
    "3DEPElevation/ImageServer/exportImage"
)
DEM_NODATA = -9999.0
DEM_TILE_PX = 2000

NHD_FLOWLINE_URL = (
    "https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer/6"
)
NHD_PAGE_SIZE = 2000
DIST_NODATA = -1.0

# gSSURGO / muaggatt hydrologic group. Dual groups stay distinct codes.
HSG_CODE = {
    "A": 1,
    "B": 2,
    "C": 3,
    "D": 4,
    "A/D": 5,
    "B/D": 6,
    "C/D": 7,
    "A/B": 8,
    "B/C": 9,
}
HSG_NODATA = 255
SDA_URL = "https://sdmdataaccess.nrcs.usda.gov/Tabular/post.rest"

REPO_ROOT = Path(__file__).resolve().parents[2]
FROZEN_OCCUPANCY_PATH = REPO_ROOT / "data" / "frozen" / "sibling_stage0_occupancy.json"
