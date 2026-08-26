# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Refuse a public dashboard publish that would regress live, or skip compare."""

from __future__ import annotations

from typing import Any

from whiteforge._bootstrap import ensure_paths

ensure_paths()

from graphforge import END, START, StateGraph, last_value, operator_add
from graphforge.state import ChannelSpec, StateSchema


def _schema() -> StateSchema:
    return StateSchema.from_specs(
        [
            ChannelSpec("request_site_publish", last_value, default=False),
            ChannelSpec("payload_stale_vs_live", last_value, default=False),
            ChannelSpec("live_compared", last_value, default=False),
            ChannelSpec("violations", last_value, default=[]),
            ChannelSpec("decision", last_value, default=None),
            ChannelSpec("events", operator_add, default=[]),
        ]
    )


def _evaluate(state: dict[str, Any]) -> dict[str, Any]:
    violations: list[str] = []
    publish = bool(state.get("request_site_publish"))
    if publish and bool(state.get("payload_stale_vs_live")):
        violations.append("stale_site_payload_would_regress_board")
    if publish and not bool(state.get("live_compared")):
        violations.append("publish_without_live_compare")
    return {
        "violations": violations,
        "events": [{"node": "evaluate", "ok": len(violations) == 0}],
    }


def build_graph() -> StateGraph:
    g = StateGraph(_schema(), name="white.stale_map")

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
