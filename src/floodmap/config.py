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

REPO_ROOT = Path(__file__).resolve().parents[2]
FROZEN_OCCUPANCY_PATH = REPO_ROOT / "data" / "frozen" / "sibling_stage0_occupancy.json"
