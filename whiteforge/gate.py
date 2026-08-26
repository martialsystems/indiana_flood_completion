# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Call sites for stage, claim, freeze, and stale-map laws."""

from __future__ import annotations

from typing import Any

from whiteforge._bootstrap import ensure_paths

ensure_paths()

from graphforge.product_law import require_law

from whiteforge.graphs.claim_bans import build_graph as build_claim_bans
from whiteforge.graphs.stage0_import_freeze import build_graph as build_stage0_import_freeze
from whiteforge.graphs.stage_gate import build_graph as build_stage_gate
from whiteforge.graphs.stale_map import build_graph as build_stale_map


def require_stage(
    *,
    current_stage: str = "0",
    target_stage: str = "0",
    freeze_verified: bool = False,
    claim_stage0_complete: bool = False,
    template_kind: str = "",
    stage_a_report: bool = False,
    stage_b_report: bool = False,
    stage_c_metrics: bool = False,
    inundation_2008_mask: bool = False,
    thread_id: str = "white_stage",
) -> None:
    require_law(
        build_stage_gate(),
        {
            "current_stage": current_stage,
            "target_stage": target_stage,
            "freeze_verified": freeze_verified,
            "claim_stage0_complete": claim_stage0_complete,
            "template_kind": template_kind,
            "stage_a_report": stage_a_report,
            "stage_b_report": stage_b_report,
            "stage_c_metrics": stage_c_metrics,
            "inundation_2008_mask": inundation_2008_mask,
        },
        allow_decisions=["allow"],
        law_id="white.stage_gate",
        thread_id=thread_id,
        raise_error=True,
    )


def require_claims(**flags: Any) -> None:
    state = {
        "emit_casualty_counts": False,
        "emit_climate_attribution": False,
        "emit_tornado_counts": False,
        "emit_population_at_risk": False,
        "tri_pounds_are_storage": False,
        "p_as_100yr_exceedance": False,
        "d1_without_d2": False,
        "score_outside_huc": False,
    }
    state.update(flags)
    require_law(
        build_claim_bans(),
        state,
        allow_decisions=["allow"],
        law_id="white.claim_bans",
        thread_id="white_claims",
        raise_error=True,
    )


def require_freeze(
    *,
    stage0_packet_frozen: bool = True,
    rewrite_stage0_packet: bool = False,
    explicit_unfreeze: bool = False,
    replace_occupancy_count: bool = False,
    thread_id: str = "white_freeze",
) -> None:
    require_law(
        build_stage0_import_freeze(),
        {
            "stage0_packet_frozen": stage0_packet_frozen,
            "rewrite_stage0_packet": rewrite_stage0_packet,
            "explicit_unfreeze": explicit_unfreeze,
            "replace_occupancy_count": replace_occupancy_count,
        },
        allow_decisions=["allow"],
        law_id="white.stage0_import_freeze",
        thread_id=thread_id,
        raise_error=True,
    )


def require_stale_map(
    *,
    request_site_publish: bool = False,
    payload_stale_vs_live: bool = False,
    live_compared: bool = False,
    thread_id: str = "white_stale_map",
) -> None:
    require_law(
        build_stale_map(),
        {
            "request_site_publish": request_site_publish,
            "payload_stale_vs_live": payload_stale_vs_live,
            "live_compared": live_compared,
        },
        allow_decisions=["allow"],
        law_id="white.stale_map",
        thread_id=thread_id,
        raise_error=True,
    )
