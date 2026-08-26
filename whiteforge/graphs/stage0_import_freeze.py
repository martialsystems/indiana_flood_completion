# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Refuse rewriting the imported occupancy freeze unless explicitly unlocked."""

from __future__ import annotations

from typing import Any

from whiteforge._bootstrap import ensure_paths

ensure_paths()

from graphforge import END, START, StateGraph, last_value, operator_add
from graphforge.state import ChannelSpec, StateSchema


def _schema() -> StateSchema:
    return StateSchema.from_specs(
        [
            ChannelSpec("stage0_packet_frozen", last_value, default=True),
            ChannelSpec("rewrite_stage0_packet", last_value, default=False),
            ChannelSpec("explicit_unfreeze", last_value, default=False),
            ChannelSpec("replace_occupancy_count", last_value, default=False),
            ChannelSpec("violations", last_value, default=[]),
            ChannelSpec("decision", last_value, default=None),
            ChannelSpec("events", operator_add, default=[]),
        ]
    )


def _evaluate(state: dict[str, Any]) -> dict[str, Any]:
    violations: list[str] = []
    if (
        bool(state.get("stage0_packet_frozen", True))
        and bool(state.get("rewrite_stage0_packet"))
        and not bool(state.get("explicit_unfreeze"))
    ):
        violations.append("rewrite_frozen_stage0_packet")
    if bool(state.get("replace_occupancy_count")):
        violations.append("replace_occupancy_count")
    return {
        "violations": violations,
        "events": [{"node": "evaluate", "ok": len(violations) == 0}],
    }


def build_graph() -> StateGraph:
    g = StateGraph(_schema(), name="white.stage0_import_freeze")

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
