# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Allow and block paths for WhiteForge stage, claim, freeze, and map laws."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from whiteforge._bootstrap import ensure_paths

ensure_paths()

from graphforge.product_law import LawBlockedError, require_law

from whiteforge.gate import require_claims, require_freeze, require_stage, require_stale_map
from whiteforge.graphs.claim_bans import build_graph as claim_bans
from whiteforge.graphs.stage0_import_freeze import build_graph as stage0_import_freeze
from whiteforge.graphs.stage_gate import build_graph as stage_gate
from whiteforge.graphs.stale_map import build_graph as stale_map
from whiteforge.product_laws import laws


def test_stage_gate_allows_stage0_with_freeze() -> None:
    require_stage(
        current_stage="0",
        target_stage="0",
        freeze_verified=True,
        claim_stage0_complete=True,
        template_kind="fixture",
        thread_id="test.stage0.allow",
    )


def test_stage_gate_blocks_complete_without_freeze() -> None:
    with pytest.raises(LawBlockedError):
        require_stage(
            current_stage="0",
            target_stage="0",
            freeze_verified=False,
            claim_stage0_complete=True,
            thread_id="test.stage0.block_complete",
        )


def test_stage_gate_blocks_skip_and_fixture_advance() -> None:
    with pytest.raises(LawBlockedError):
        require_stage(
            current_stage="0",
            target_stage="B",
            freeze_verified=True,
            template_kind="nlcd_2021",
            thread_id="test.stage.skip",
        )
    with pytest.raises(LawBlockedError):
        require_stage(
            current_stage="0",
            target_stage="A",
            freeze_verified=True,
            template_kind="fixture",
            thread_id="test.stage.fixture_a",
        )


def test_stage_gate_allows_a_on_nlcd() -> None:
    require_stage(
        current_stage="0",
        target_stage="A",
        freeze_verified=True,
        template_kind="nlcd_2021",
        thread_id="test.stage.a_nlcd",
    )


def test_stage_gate_blocks_c_without_ab_and_d_without_mask() -> None:
    with pytest.raises(LawBlockedError):
        require_stage(
            current_stage="B",
            target_stage="C",
            freeze_verified=True,
            template_kind="nlcd_2021",
            stage_a_report=False,
            stage_b_report=True,
            thread_id="test.stage.c_no_a",
        )
    with pytest.raises(LawBlockedError):
        require_stage(
            current_stage="C",
            target_stage="D",
            freeze_verified=True,
            template_kind="nlcd_2021",
            stage_a_report=True,
            stage_b_report=True,
            stage_c_metrics=True,
            inundation_2008_mask=False,
            thread_id="test.stage.d_no_mask",
        )


def test_claim_bans_allow_default_and_block_storage() -> None:
    require_claims()
    with pytest.raises(LawBlockedError):
        require_claims(tri_pounds_are_storage=True)
    with pytest.raises(LawBlockedError):
        require_law(
            claim_bans(),
            {"p_as_100yr_exceedance": True},
            allow_decisions=["allow"],
            law_id="test.claims.100yr",
            raise_error=True,
        )
    with pytest.raises(LawBlockedError):
        require_claims(d1_without_d2=True)


def test_product_laws_are_the_domain_graphs() -> None:
    ids = [item["id"] for item in laws()]
    assert ids == [
        "white.stage_gate",
        "white.claim_bans",
        "white.stage0_import_freeze",
        "white.stale_map",
    ]


def test_import_freeze_blocks_rewrite_and_replace() -> None:
    require_law(
        stage0_import_freeze(),
        {
            "stage0_packet_frozen": True,
            "rewrite_stage0_packet": False,
            "explicit_unfreeze": False,
            "replace_occupancy_count": False,
        },
        allow_decisions=["allow"],
        law_id="test.freeze.hold",
        raise_error=True,
    )
    with pytest.raises(LawBlockedError):
        require_freeze(rewrite_stage0_packet=True, explicit_unfreeze=False)
    with pytest.raises(LawBlockedError):
        require_freeze(replace_occupancy_count=True)


def test_import_freeze_allows_explicit_unfreeze() -> None:
    require_freeze(rewrite_stage0_packet=True, explicit_unfreeze=True)


def test_stale_map_noop_without_publish() -> None:
    require_stale_map(request_site_publish=False, live_compared=False)


def test_stale_map_blocks_stale_and_uncompared_publish() -> None:
    with pytest.raises(LawBlockedError):
        require_stale_map(
            request_site_publish=True,
            payload_stale_vs_live=True,
            live_compared=True,
        )
    with pytest.raises(LawBlockedError):
        require_stale_map(
            request_site_publish=True,
            payload_stale_vs_live=False,
            live_compared=False,
        )
    require_law(
        stale_map(),
        {
            "request_site_publish": True,
            "payload_stale_vs_live": False,
            "live_compared": True,
        },
        allow_decisions=["allow"],
        law_id="test.map.publish_ok",
        raise_error=True,
    )


def test_unknown_stage_blocked() -> None:
    with pytest.raises(LawBlockedError):
        require_stage(
            current_stage="0",
            target_stage="Z",
            freeze_verified=True,
            thread_id="test.stage.unknown",
        )
