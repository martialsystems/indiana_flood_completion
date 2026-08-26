# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Refuse claims this tree is not allowed to emit."""

from __future__ import annotations

from typing import Any

from whiteforge._bootstrap import ensure_paths

ensure_paths()

from graphforge import END, START, StateGraph, last_value, operator_add
from graphforge.state import ChannelSpec, StateSchema


def _schema() -> StateSchema:
    return StateSchema.from_specs(
        [
            ChannelSpec("emit_casualty_counts", last_value, default=False),
            ChannelSpec("emit_climate_attribution", last_value, default=False),
            ChannelSpec("emit_tornado_counts", last_value, default=False),
            ChannelSpec("emit_population_at_risk", last_value, default=False),
            ChannelSpec("tri_pounds_are_storage", last_value, default=False),
            ChannelSpec("p_as_100yr_exceedance", last_value, default=False),
            ChannelSpec("d1_without_d2", last_value, default=False),
            ChannelSpec("score_outside_huc", last_value, default=False),
            ChannelSpec("violations", last_value, default=[]),
            ChannelSpec("decision", last_value, default=None),
            ChannelSpec("events", operator_add, default=[]),
        ]
    )


def _evaluate(state: dict[str, Any]) -> dict[str, Any]:
    flags = (
        ("emit_casualty_counts", "casualty_counts"),
        ("emit_climate_attribution", "climate_attribution"),
        ("emit_tornado_counts", "tornado_counts"),
        ("emit_population_at_risk", "population_at_risk"),
        ("tri_pounds_are_storage", "tri_storage_pounds"),
        ("p_as_100yr_exceedance", "p_as_100yr"),
        ("d1_without_d2", "d1_without_d2"),
        ("score_outside_huc", "score_outside_huc"),
    )
    violations = [code for key, code in flags if state.get(key)]
    return {
        "violations": violations,
        "events": [
            {"node": "evaluate", "ok": len(violations) == 0, "violations": list(violations)}
        ],
    }


def build_graph() -> StateGraph:
    g = StateGraph(_schema(), name="white.claim_bans")

    def allow(state: dict[str, Any]) -> dict[str, Any]:
        del state
        return {"decision": "allow", "events": [{"node": "allow"}]}

    def block(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "decision": "block",
            "events": [{"node": "block", "violations": state.get("violations") or []}],
        }

    def route(state: dict[str, Any]) -> str:
        return "ok" if not (state.get("violations") or []) else "bad"

    g.add_node("evaluate", _evaluate)
    g.add_node("allow", allow)
    g.add_node("block", block)
    g.add_edge(START, "evaluate")
    g.add_conditional_edges("evaluate", route, {"ok": "allow", "bad": "block"})
    g.add_edge("allow", END)
    g.add_edge("block", END)
    return g
