# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""
Domain product laws for this tree.

Verify-before-done is the finish gate and already runs home-global. These
graphs only refuse stage skips, forbidden claims, freeze rewrites, and a
stale public map. Mandatory engine templates still run on graphforge-gate;
this module does not duplicate them.
"""

from __future__ import annotations

from typing import Any


def laws() -> list[dict[str, Any]]:
    from whiteforge.graphs.claim_bans import build_graph as claim_bans
    from whiteforge.graphs.stage0_import_freeze import build_graph as stage0_import_freeze
    from whiteforge.graphs.stage_gate import build_graph as stage_gate
    from whiteforge.graphs.stale_map import build_graph as stale_map

    return [
        {
            "id": "white.stage_gate",
            "build": stage_gate,
            "state": {
                "current_stage": "0",
                "target_stage": "0",
                "freeze_verified": True,
                "claim_stage0_complete": True,
                "template_kind": "fixture",
            },
            "allow_decisions": ["allow"],
        },
        {
            "id": "white.claim_bans",
            "build": claim_bans,
            "state": {
                "emit_casualty_counts": False,
                "emit_climate_attribution": False,
                "emit_tornado_counts": False,
                "emit_population_at_risk": False,
                "tri_pounds_are_storage": False,
                "p_as_100yr_exceedance": False,
                "d1_without_d2": False,
                "score_outside_huc": False,
            },
            "allow_decisions": ["allow"],
        },
        {
            "id": "white.stage0_import_freeze",
            "build": stage0_import_freeze,
            "state": {
                "stage0_packet_frozen": True,
                "rewrite_stage0_packet": False,
                "explicit_unfreeze": False,
                "replace_occupancy_count": False,
            },
            "allow_decisions": ["allow"],
        },
        {
            "id": "white.stale_map",
            "build": stale_map,
            "state": {
                "request_site_publish": False,
                "payload_stale_vs_live": False,
                "live_compared": False,
            },
            "allow_decisions": ["allow"],
        },
    ]
